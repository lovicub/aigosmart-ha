"""Export only reviewed non-sensitive diagnostic values."""
import time


async def async_get_config_entry_diagnostics(hass, entry):
    manager = entry.runtime_data.session
    session = manager.client.session
    end = session.get('iot_token_expires_at')
    return {
        'authorization_status': manager.status,
        'session_time_remaining': max(0, int(end - time.time())) if end else None,
        'last_successful_refresh': session.get('last_refresh'),
    }
