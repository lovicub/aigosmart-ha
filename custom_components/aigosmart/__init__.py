"""AigoSmart HA integration; protocol imports also work without HA installed."""
async def async_setup_entry(hass, entry):
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
    from .api import AigoClient, is_auth_error
    from .const import PLATFORMS
    from .coordinator import AigoCoordinator
    client = AigoClient()
    try:
        client.token = entry.data['iot_token']
        coordinator = AigoCoordinator(hass, entry, client)
        coordinator.model = await hass.async_add_executor_job(client.model, coordinator.device)
    except Exception as exc:
        if is_auth_error(exc):
            raise ConfigEntryAuthFailed('Authentication required') from None
        raise ConfigEntryNotReady('API unavailable') from None
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    from .const import PLATFORMS
    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if result:
        entry.runtime_data.client.token = None
    return result
