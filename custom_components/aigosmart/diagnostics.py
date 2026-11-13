"""Export only reviewed non-sensitive diagnostic values, including offline entries."""
import time
from .diagnostic_state import diagnostic_values, iso_timestamp
from .protocol import anonymize


def _model_summary(runtime):
    """Declared (TSL) versus reported properties, to support other kettle models.

    Declared rows come from model.parse_model, which already limits them to
    identifiers, access, type and numeric constraints (display names and
    descriptions are left out here). Reported values go through
    protocol.anonymize: numeric telemetry only, everything else is redacted.
    """
    model = getattr(runtime, 'model', None)
    model = model if isinstance(model, dict) else {}
    data = getattr(runtime, 'data', None)

    def listed(name):
        value = model.get(name)
        return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    return {
        'declared_properties': [{key: row.get(key) for key in ('identifier', 'access', 'data_type', 'constraints')}
                                for row in listed('properties')],
        'events': listed('events'),
        'services': listed('services'),
        'reported_properties': anonymize(data) if isinstance(data, dict) else [],
    }


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = getattr(entry, 'runtime_data', None)
    manager = runtime.session if runtime is not None else None
    values = diagnostic_values(manager, entry.data)
    failed = manager.diagnostics.last_failed_api_operation if manager is not None else None
    return {
        'model': _model_summary(runtime),
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
            'response': getattr(manager.client, 'refresh_diagnostics', None) if manager else None,
            'cooldown_active': bool(manager and manager._retry_at > time.time()),
            'retry_at': iso_timestamp(manager._retry_at) if manager else None,
            'failed_cycles': manager._failure_cycles if manager else 0,
            'read_retry_at': iso_timestamp(manager._read_retry_at) if manager else None,
            'full_login_fallback': 'unavailable_no_stored_password',
        },
        'connection_status': values['connection_status'],
        'token_expiration': {
            'iot_token': iso_timestamp(values['iot_token_expires_at']),
            'refresh_token': iso_timestamp(values['refresh_token_expires_at']),
        },
    }
