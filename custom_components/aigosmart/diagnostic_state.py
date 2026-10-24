"""Passive, allowlisted diagnostic state. No requests, timers or credentials."""
from datetime import datetime, timezone
import math
import time

from .recovery import classify_failure

SENSOR_NAMES = {
    # Preserve these three keys, their class and unique IDs from stable releases.
    'session_time_remaining': 'Session time remaining',
    'last_successful_refresh': 'Last successful refresh',
    'authorization_status': 'Authorization status',
    'last_successful_cloud_read': 'Last successful cloud read',
    'last_successful_device_read': 'Last successful device read',
    'last_failed_api_operation': 'Last failed API operation',
    'last_refresh_attempt': 'Last refresh attempt',
    'last_refresh_result': 'Last refresh result',
    'failed_refresh_count': 'Failed refresh count',
    'connection_status': 'Connection status',
    'iot_token_expires_at': 'IoT token expiration',
    'refresh_token_expires_at': 'Refresh token expiration',
}
TIMESTAMP_KEYS = {'last_successful_refresh', 'last_successful_cloud_read',
    'last_successful_device_read', 'last_refresh_attempt',
    'iot_token_expires_at', 'refresh_token_expires_at'}
AUTH_STATUSES = {'authorized', 'reauth_required', 'refresh_unavailable'}


def timestamp(value):
    """Reject non-numeric, non-finite and out-of-range stored values."""
    if type(value) not in (int, float) or not 0 < value < 253402300799 or not math.isfinite(value):
        return None
    return value


def utc_datetime(value):
    value = timestamp(value)
    return datetime.fromtimestamp(value, timezone.utc) if value is not None else None


def iso_timestamp(value):
    value = utc_datetime(value)
    return value.isoformat() if value else None


class DiagnosticState:
    """Lifetime is one session manager; failures count individual failed attempts."""
    def __init__(self):
        self.last_successful_cloud_read = None
        self.last_successful_device_read = None
        self.last_failed_api_operation = None
        self.last_refresh_attempt = None
        self.last_refresh_result = None
        self.failed_refresh_count = 0
        self.connection_status = 'unknown'

    def read_succeeded(self, stage):
        self.last_successful_cloud_read = time.time()
        if stage == 'property_read':
            self.last_successful_device_read = self.last_successful_cloud_read
            self.connection_status = 'connected'

    def operation_failed(self, stage, exc):
        stage, reason = classify_failure(stage, exc)
        self.last_failed_api_operation = {'timestamp': time.time(), 'stage': stage, 'reason': reason}
        self.connection_status = 'recovering'
        return reason

    def refresh_started(self):
        self.last_refresh_attempt = time.time()
        self.last_refresh_result = 'in_progress'

    def refresh_failed(self, exc):
        self.failed_refresh_count += 1
        self.last_refresh_result = self.operation_failed('token_refresh', exc)

    def connection(self, authorization_status):
        if authorization_status in {'reauth_required', 'refresh_unavailable'}:
            return authorization_status
        if self.last_refresh_result == 'in_progress':
            return 'refreshing'
        return self.connection_status


def diagnostic_values(manager=None, stored_session=None):
    """One fixed projection used by sensors and downloads; never copy session data."""
    state = manager.diagnostics if manager is not None else DiagnosticState()
    session = manager.client.session if manager is not None else (stored_session or {})
    status = manager.status if manager is not None else 'unknown'
    status = status if status in AUTH_STATUSES else 'unknown'
    end = timestamp(session.get('iot_token_expires_at'))
    failed = state.last_failed_api_operation
    return {
        'authorization_status': status,
        'session_time_remaining': max(0, int(end - time.time())) if end is not None else None,
        'last_successful_refresh': timestamp(session.get('last_refresh')),
        'last_successful_cloud_read': state.last_successful_cloud_read,
        'last_successful_device_read': state.last_successful_device_read,
        'last_failed_api_operation': f"{failed['stage']}: {failed['reason']}" if failed else None,
        'last_refresh_attempt': state.last_refresh_attempt,
        'last_refresh_result': state.last_refresh_result,
        'failed_refresh_count': state.failed_refresh_count,
        'connection_status': state.connection(status),
        'iot_token_expires_at': end,
        'refresh_token_expires_at': timestamp(session.get('refresh_token_expires_at')),
    }
