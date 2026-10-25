"""AigoSmart HA integration; protocol imports also work without HA installed."""
async def async_setup_entry(hass, entry):
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
    from .api import AigoClient, is_auth_error
    from .const import PLATFORMS
    from .coordinator import AigoCoordinator
    from .recovery import RecoveryError, failure
    client = AigoClient()
    stage = 'session_restore'
    try:
        client.restore_session(entry.data)
        coordinator = AigoCoordinator(hass, entry, client)
        coordinator.session.require_credentials()
        stage = 'model_tsl_fetch'
        coordinator.model = await coordinator.session.read(client.model, coordinator.device, stage=stage)
    except BaseException as exc:
        if 'coordinator' in locals():
            await coordinator.session.close()
        if not isinstance(exc, Exception):
            raise
        reason = failure(stage, exc)
        stage = exc.stage if isinstance(exc, RecoveryError) else stage
        if isinstance(exc, ConfigEntryAuthFailed):
            raise
        if is_auth_error(exc):
            raise ConfigEntryAuthFailed('Authentication required') from None
        raise ConfigEntryNotReady(f'{stage}: {reason}') from None
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await coordinator.session.close()
        raise
    coordinator.session.schedule()
    coordinator._entry_options = dict(entry.options)
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.session.close()
        raise
    try:
        from .frontend import async_schedule_frontend
        async_schedule_frontend(hass)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            'Integrated card setup failed; cloud integration remains available'
        )
    return True

async def _reload(hass, entry):
    if dict(entry.options) != entry.runtime_data._entry_options:
        await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    from .const import PLATFORMS
    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if result:
        await entry.runtime_data.session.close()
        entry.runtime_data.client.token = None
        entry.runtime_data.client.session.clear()
    return result


async def async_migrate_entry(hass, entry):
    """Keep legacy device/options; setup requests one-time reauth for missing fields."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2)
    return True
