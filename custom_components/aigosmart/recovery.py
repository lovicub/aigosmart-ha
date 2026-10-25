"""Allowlisted recovery diagnostics: never format exceptions or cloud payloads."""
import logging
import time
import json

from homeassistant.exceptions import ConfigEntryAuthFailed
from .api import is_auth_error
from .protocol import APIError

_LOGGER = logging.getLogger(__name__)
_WARNINGS = {}
_WARNING_INTERVAL = 300
_REASONS = {'confirmed_invalid_credentials', 'cloud_timeout', 'cloud_unavailable', 'response_validation'}
_STAGES = {'token_refresh', 'model_tsl_fetch', 'device_list', 'property_read', 'session_restore', 'property_write'}


def classify_failure(stage, exc):
    """Return allowlisted categories without retaining the exception."""
    stage = stage if stage in _STAGES else 'property_read'
    if isinstance(exc, RecoveryError):
        stage, reason = exc.stage, exc.reason
    elif isinstance(exc, RenewalRequired):
        stage, reason = 'token_refresh', 'response_validation'
    elif isinstance(exc, ConfigEntryAuthFailed) or is_auth_error(exc):
        reason = 'confirmed_invalid_credentials'
    elif isinstance(exc, TimeoutError) or (isinstance(exc, APIError) and exc.exception in {'TimeoutError', 'timeout'}):
        reason = 'cloud_timeout'
    elif isinstance(exc, OSError) or (isinstance(exc, APIError) and exc.exception in {'URLError', 'ConnectionError', 'OSError', 'ConnectionResetError', 'ConnectionRefusedError', 'gaierror'}):
        reason = 'cloud_unavailable'
    elif isinstance(exc, APIError) and (exc.status == 429 or exc.status is not None and exc.status >= 500 or exc.code in {'429', '500', '502', '503'}):
        reason = 'cloud_unavailable'
    else:
        reason = 'response_validation'
    return stage, reason


def failure(stage, exc, *, details=None):
    stage, reason = classify_failure(stage, exc)
    # Multiple HA boundaries can report the same failure. Cooldown is not a request.
    if isinstance(exc, RecoveryError) and exc.cooldown:
        return reason
    key = (stage, reason)
    now = time.monotonic()
    last, suppressed = _WARNINGS.get(key, (float('-inf'), 0))
    if now - last >= _WARNING_INTERVAL:
        _LOGGER.warning('AigoSmart recovery stage=%s reason=%s suppressed=%s', stage, reason, suppressed)
        if stage == 'token_refresh' and details is not None:
            # Only protocol-generated shape metadata reaches here, never payloads.
            _LOGGER.warning('AigoSmart refresh response_shape=%s', json.dumps(details, sort_keys=True))
        _WARNINGS[key] = (now, 0)
    else:
        _WARNINGS[key] = (last, suppressed + 1)
    return reason


class RecoveryError(APIError):
    """Carry only categories across setup and coordinator boundaries."""
    def __init__(self, stage, reason, *, cooldown=False):
        self.cooldown = cooldown
        self.stage = stage if stage in _STAGES else 'property_read'
        self.reason = reason if reason in _REASONS else 'response_validation'
        super().__init__(f'{self.stage}: {self.reason}')


def recovered(stage):
    """Report a successful transition and flush counts once, without payloads."""
    keys = [key for key in _WARNINGS if key[0] == stage]
    if keys:
        suppressed = sum(_WARNINGS.pop(key)[1] for key in keys)
        _LOGGER.info('AigoSmart recovered stage=%s suppressed=%s', stage, suppressed)


class RenewalRequired(ConfigEntryAuthFailed):
    """Unusable renewal requires login; this is not proven credential rejection."""
