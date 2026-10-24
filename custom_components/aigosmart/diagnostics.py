"""Export only reviewed non-sensitive diagnostic values, including offline entries."""
from .diagnostic_state import diagnostic_values, iso_timestamp


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = getattr(entry, 'runtime_data', None)
    manager = runtime.session if runtime is not None else None
    values = diagnostic_values(manager, entry.data)
    failed = manager.diagnostics.last_failed_api_operation if manager is not None else None
    return {
        # Keep the original download fields and numeric timestamp compatibility.
        'authorization_status': values['authorization_status'],
        'session_time_remaining': values['session_time_remaining'],
        'last_successful_refresh': values['last_successful_refresh'],
        'reads': {
            'last_successful_cloud_read': iso_timestamp(values['last_successful_cloud_read']),
            'last_successful_device_read': iso_timestamp(values['last_successful_device_read']),
        },
        'last_failed_api_operation': ({
            'timestamp': iso_timestamp(failed['timestamp']),
            'stage': failed['stage'], 'reason': failed['reason'],
        } if failed else None),
        'refresh': {
            'last_attempt': iso_timestamp(values['last_refresh_attempt']),
            'last_result': values['last_refresh_result'],
            'failed_attempt_count': values['failed_refresh_count'],
            'counter_scope': 'since_session_start',
        },
        'connection_status': values['connection_status'],
        'token_expiration': {
            'iot_token': iso_timestamp(values['iot_token_expires_at']),
            'refresh_token': iso_timestamp(values['refresh_token_expires_at']),
        },
    }
