"""Persisted sessions, bounded read retries and one shared refresh task."""
import asyncio
from datetime import datetime, timezone
import time

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_point_in_utc_time

from .diagnostic_state import DiagnosticState
from .api import is_auth_error
from .protocol import APIError
from .recovery import RecoveryError, failure


def transient(exc):
    return (isinstance(exc, (OSError, TimeoutError)) or isinstance(exc, APIError)
            and not is_auth_error(exc) and (exc.status is None or exc.status == 429
                or exc.status >= 500 or exc.code in {'429', '500', '502', '503'}))


class SessionManager:
    def __init__(self, hass, entry, client):
        self.hass, self.entry, self.client = hass, entry, client
        self.diagnostics = DiagnosticState()
        self.status = 'authorized'
        self._task = None
        self._retry_at = 0
        self._cancel_timer = None
        self._closed = False
        self.on_change = lambda: None

    @property
    def refresh_at(self):
        s = self.client.session
        end = s.get('iot_token_expires_at', 0)
        # Short API TTLs get a proportional margin, avoiding an immediate loop.
        return end - min(600, s.get('iot_token_ttl', 0) * 0.1)

    def require_credentials(self):
        s = self.client.session
        if (self.status == 'reauth_required' or not s.get('refresh_token') or not s.get('identity_id') or
                s.get('refresh_token_expires_at', 0) <= time.time()):
            self.status = 'reauth_required'
            self.on_change()
            raise ConfigEntryAuthFailed('Session renewal requires reauthentication')

    async def ensure(self, *, rejected_token=None):
        if self._closed:
            raise APIError('Session manager stopped')
        if self._task is not None:
            return await asyncio.shield(self._task)
        self.require_credentials()
        if rejected_token is not None and rejected_token != self.client.token:
            return
        if rejected_token is None and time.time() < self.refresh_at:
            return
        if time.time() < self._retry_at:
            raise RecoveryError('token_refresh', 'cloud_unavailable')
        self._task = self.hass.async_create_task(self._refresh())
        self._task.add_done_callback(self._refresh_done)
        # A cancelled waiter must not cancel an in-flight rotating refresh.
        await asyncio.shield(self._task)

    def _refresh_done(self, task):
        if self._task is task:
            self._task = None
        # Retrieve failures even when all waiters were cancelled (safe messages only).
        if not task.cancelled():
            task.exception()

    async def _refresh(self):
        try:
            for attempt, delay in enumerate((0, 1, 3)):
                if delay:
                    await asyncio.sleep(delay)
                self.diagnostics.refresh_started()
                try:
                    await self.hass.async_add_executor_job(self.client.refresh_iot_token_sync)
                    # Persist the complete rotated session before exposing success.
                    self.hass.config_entries.async_update_entry(self.entry,
                        data={**self.entry.data, **self.client.session})
                    self._retry_at = 0
                    self.status = 'authorized'
                    self.diagnostics.last_refresh_result = 'success'
                    return
                except Exception as exc:
                    self.diagnostics.refresh_failed(exc)
                    reason = failure('token_refresh', exc)
                    if is_auth_error(exc):
                        self.status = 'reauth_required'
                        raise ConfigEntryAuthFailed('Session renewal rejected; reauthenticate') from None
                    if not transient(exc) or attempt == 2:
                        self.status = 'refresh_unavailable'
                        self._retry_at = time.time() + 60
                        raise RecoveryError('token_refresh', reason) from None
        finally:
            self.on_change()
            self.schedule()

    async def read(self, method, *args, stage="property_read"):
        await self.ensure()
        refreshed = False
        attempt = 0
        while attempt < 3:
            token = self.client.token
            try:
                result = await self.hass.async_add_executor_job(method, *args)
                self.diagnostics.read_succeeded(stage)
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
                    raise RecoveryError(stage, reason) from None
                else:
                    await asyncio.sleep((1, 3)[attempt])
                    attempt += 1
        raise APIError('Read temporarily unavailable')

    def schedule(self):
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        if self._closed or self.status == 'reauth_required':
            return
        due = max(time.time() + 1, self.refresh_at, self._retry_at)
        self._cancel_timer = async_track_point_in_utc_time(
            self.hass, self._timer, datetime.fromtimestamp(due, timezone.utc))

    async def _timer(self, _now):
        self._cancel_timer = None
        try:
            await self.ensure()
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
