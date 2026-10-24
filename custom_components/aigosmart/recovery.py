"""Allowlisted recovery diagnostics: never format exceptions or cloud payloads."""
import logging

from homeassistant.exceptions import ConfigEntryAuthFailed
from .api import is_auth_error
from .protocol import APIError

_LOGGER = logging.getLogger(__name__)
_REASONS = {'confirmed_invalid_credentials', 'cloud_timeout', 'cloud_unavailable', 'response_validation'}
_STAGES = {'token_refresh', 'model_tsl_fetch', 'device_list', 'property_read', 'session_restore'}


def failure(stage, exc):
    stage = stage if stage in _STAGES else 'property_read'
    if isinstance(exc, RecoveryError):
        stage, reason = exc.stage, exc.reason
    elif isinstance(exc, ConfigEntryAuthFailed) or is_auth_error(exc):
        reason = 'confirmed_invalid_credentials'
    elif isinstance(exc, TimeoutError) or (isinstance(exc, APIError) and exc.exception in {'TimeoutError', 'timeout'}):
        reason = 'cloud_timeout'
    elif isinstance(exc, OSError) or (isinstance(exc, APIError) and exc.exception in {'URLError', 'ConnectionError', 'OSError', 'ConnectionResetError', 'ConnectionRefusedError', 'gaierror'}):
        reason = 'cloud_unavailable'
    elif isinstance(exc, APIError) and (exc.status == 429 or exc.status is not None and exc.status >= 500):
        reason = 'cloud_unavailable'
    else:
        reason = 'response_validation'
    _LOGGER.warning('AigoSmart recovery stage=%s reason=%s', stage, reason)
    return reason


class RecoveryError(APIError):
    """Carry only categories across setup and coordinator boundaries."""
    def __init__(self, stage, reason):
        self.stage = stage if stage in _STAGES else 'property_read'
        self.reason = reason if reason in _REASONS else 'response_validation'
        super().__init__(f'{self.stage}: {self.reason}')
