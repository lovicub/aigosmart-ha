"""Persisted sessions, bounded read retries and one shared refresh task."""
import asyncio
from datetime import datetime, timezone
import time
import random
from contextlib import asynccontextmanager

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_point_in_utc_time

from .diagnostic_state import DiagnosticState, timestamp
from .api import is_auth_error
from .protocol import APIError
from .recovery import RecoveryError, RenewalRequired, failure, recovered


def transient(exc):
    return (isinstance(exc, (OSError, TimeoutError)) or isinstance(exc, APIError)
            and not is_auth_error(exc) and ((exc.status is None and exc.validation in {"response_validation", "transport"}) or exc.status == 429
                or exc.status is not None and exc.status >= 500 or exc.code in {'429', '500', '502', '503'}))


class SessionManager:
    def __init__(self, hass, entry, client):
        self.hass, self.entry, self.client = hass, entry, client
        self.diagnostics = DiagnosticState()
        self.status = 'authorized'
        self._task = None
        self._retry_at = 0
        self._failure_cycles = 0
        self._unusable_cycles = 0
        self._retry_reason = "response_validation"
        self._cancel_timer = None
        self._closed = False
        self._login_lock = asyncio.Lock()
        self._login_active = False
        self._manual_retry_at = 0
        self._read_retry_at = 0
        self._read_failure_cycles = 0
        self._read_failure = ("property_read", "cloud_unavailable")
        self.on_change = lambda: None

    @property
    def refresh_at(self):
        s = self.client.session
        end = timestamp(s.get('iot_token_expires_at')) or 0
        # Short API TTLs get a proportional margin, avoiding an immediate loop.
        return end - min(600, (timestamp(s.get('iot_token_ttl')) or 0) * 0.1)

    def require_credentials(self):
        s = self.client.session
        if (self.status == 'reauth_required' or not s.get('refresh_token') or not s.get('identity_id') or
                (timestamp(s.get('refresh_token_expires_at')) or 0) <= time.time()):
            self.status = 'reauth_required'
            self.on_change()
            raise ConfigEntryAuthFailed('Session renewal requires reauthentication')

    async def manual_force_refresh(self):
        """Force renewal, sharing rotation but never suppressing its failures."""
        await self.ensure(_manual=True)

    @property
    def manual_refresh_available(self):
        """Availability depends on renewal credentials, not kettle connectivity."""
        s = self.client.session
        return (not self._closed and not self._login_active
                and self.status != 'reauth_required'
                and bool(s.get('refresh_token')) and bool(s.get('identity_id'))
                and (timestamp(s.get('refresh_token_expires_at')) or 0) > time.time())

    async def ensure(self, *, rejected_token=None, _manual=False, _trigger='proactive'):
        if self._closed:
            raise APIError('Session manager stopped')
        if self._login_active:
            raise RecoveryError('token_refresh', 'response_validation', cooldown=True)
        if self._task is not None:
            if _manual:
                self._manual_retry_at = time.monotonic() + 60
            return await self._await_refresh(self._task, rejected_token, strict=_manual)
        self.require_credentials()
        if _manual and time.monotonic() < self._manual_retry_at:
            raise RecoveryError('token_refresh', 'response_validation', cooldown=True)
        if rejected_token is not None and rejected_token != self.client.token:
            return
        if not _manual and rejected_token is None and time.time() < self.refresh_at:
            return
        if time.time() < self._retry_at:
            if not _manual and rejected_token is None and self._token_valid():
                return
            raise RecoveryError('token_refresh', self._retry_reason, cooldown=True)
        if _manual:
            self._manual_retry_at = time.monotonic() + 60
        self._task = self.hass.async_create_task(self._refresh(trigger='manual' if _manual else 'rejected_token' if rejected_token is not None else _trigger))
        self._task.add_done_callback(self._refresh_done)
        # A cancelled waiter must not cancel an in-flight rotating refresh.
        await self._await_refresh(self._task, rejected_token, strict=_manual)

    async def _await_refresh(self, task, rejected_token, *, strict=False):
        try:
            await asyncio.shield(task)
        except RecoveryError:
            # A failed proactive renewal does not invalidate the current token.
            # A rejected token never takes this path.
            if strict or rejected_token is not None or not self._token_valid():
                raise

    def _token_valid(self):
        return bool(self.client.token) and (timestamp(self.client.session.get('iot_token_expires_at')) or 0) > time.time()

    def _refresh_done(self, task):
        if self._task is task:
            self._task = None
        # Retrieve failures even when all waiters were cancelled (safe messages only).
        if not task.cancelled():
            task.exception()

    async def _refresh(self, *, trigger='proactive'):
        try:
            for attempt, delay in enumerate((0, 1, 3)):
                if delay:
                    await asyncio.sleep(delay * random.uniform(0.8, 1.2))
                self.diagnostics.refresh_started()
                try:
                    await self.hass.async_add_executor_job(self.client.refresh_iot_token_sync)
                    if isinstance(self.client.refresh_diagnostics, dict):
                        self.client.refresh_diagnostics['trigger'] = trigger
                    # Persist the complete rotated session before exposing success.
                    self.hass.config_entries.async_update_entry(self.entry,
                        data={**self.entry.data, **self.client.session})
                    self._retry_at = 0
                    self._failure_cycles = 0
                    self._unusable_cycles = 0
                    recovered("token_refresh")
                    self.status = 'authorized'
                    self.diagnostics.last_refresh_result = 'success'
                    return
                except Exception as exc:
                    if isinstance(self.client.refresh_diagnostics, dict):
                        self.client.refresh_diagnostics['trigger'] = trigger
                    self.diagnostics.refresh_failed(exc)
                    reason = failure('token_refresh', exc, details=self.client.refresh_diagnostics)
                    if is_auth_error(exc):
                        self.status = 'reauth_required'
                        raise ConfigEntryAuthFailed('Session renewal rejected; reauthenticate') from None
                    if not transient(exc) or attempt == 2:
                        self.status = 'refresh_unavailable'
                        self._failure_cycles += 1
                        # Repeated structurally unusable renewal needs interactive login;
                        # temporary transport failures keep retrying automatically.
                        if isinstance(exc, APIError) and exc.validation != 'response_validation' and reason == 'response_validation':
                            self._unusable_cycles += 1
                            if self._unusable_cycles >= 3 and not self._token_valid():
                                self.status = 'reauth_required'
                                raise RenewalRequired('Unusable renewal; interactive reauthentication required') from None
                        else:
                            self._unusable_cycles = 0
                        self._retry_reason = reason
                        self._retry_at = time.time() + min(900, 60 * 2 ** min(self._failure_cycles - 1, 4)) * random.uniform(0.8, 1.2)
                        raise RecoveryError('token_refresh', reason) from None
        finally:
            self.on_change()
            self.schedule()

    @asynccontextmanager
    async def login_guard(self):
        """Serialize interactive login with renewal without discarding a usable session."""
        async with self._login_lock:
            self._login_active = True
            try:
                if self._task is not None:
                    try:
                        await asyncio.shield(self._task)
                    except Exception:
                        pass
                yield
            finally:
                self._login_active = False
                self.schedule()

    async def read(self, method, *args, stage="property_read"):
        if time.time() < self._read_retry_at:
            raise RecoveryError(*self._read_failure, cooldown=True)
        await self.ensure()
        refreshed = False
        attempt = 0
        while attempt < 3:
            token = self.client.token
            try:
                result = await self.hass.async_add_executor_job(method, *args)
                self._read_retry_at = 0
                self._read_failure_cycles = 0
                self.diagnostics.read_succeeded(stage)
                recovered(stage)
                return result
            except Exception as exc:
                self.diagnostics.operation_failed(stage, exc)
                if is_auth_error(exc) and not refreshed:
                    await self.ensure(rejected_token=token)
                    refreshed = True
                elif is_auth_error(exc):
                    failure(stage, exc)
                    self.status = 'reauth_required'
                    self.on_change()
                    self.schedule()
                    raise ConfigEntryAuthFailed('Confirmed invalid credentials after token refresh') from None
                elif not transient(exc) or attempt == 2:
                    reason = failure(stage, exc)
                    if transient(exc):
                        self._read_failure_cycles += 1
                        self._read_failure = (stage, reason)
                        self._read_retry_at = time.time() + min(900, 60 * 2 ** min(self._read_failure_cycles - 1, 4)) * random.uniform(0.8, 1.2)
                    raise RecoveryError(stage, reason) from None
                else:
                    await asyncio.sleep((1, 3)[attempt])
                    attempt += 1
        raise APIError('Read temporarily unavailable')

    def schedule(self):
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        if self._closed or self._login_active or self.status == 'reauth_required':
            return
        due = max(time.time() + 1, self.refresh_at, self._retry_at)
        self._cancel_timer = async_track_point_in_utc_time(
            self.hass, self._timer, datetime.fromtimestamp(due, timezone.utc))

    async def _timer(self, _now):
        self._cancel_timer = None
        try:
            await self.ensure(_trigger='timer')
        except ConfigEntryAuthFailed:
            self.entry.async_start_reauth(self.hass)
        except APIError:
            pass
        finally:
            self.schedule()

    async def close(self):
        self._closed = True
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        if self._task:
            try:
                await asyncio.shield(self._task)
            except Exception:
                pass
