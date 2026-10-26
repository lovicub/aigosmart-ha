"""Local experimental session diagnostic action; never sends device commands."""
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .entity import AigoEntity
from .recovery import RecoveryError, classify_failure


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AigoRefreshTokenButton(entry.runtime_data)])


class AigoRefreshTokenButton(AigoEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = 'refresh_iot_token'
    _attr_icon = 'mdi:refresh'

    def __init__(self, coordinator):
        super().__init__(coordinator, 'refresh_iot_token')
        self._attr_name = None

    @property
    def available(self):
        return self.coordinator.session.manual_refresh_available

    @property
    def extra_state_attributes(self):
        return None

    async def async_press(self):
        try:
            await self.coordinator.session.manual_force_refresh()
        except ConfigEntryAuthFailed:
            self.coordinator.entry.async_start_reauth(self.hass)
            raise HomeAssistantError('IoT token refresh requires Home Assistant reauthentication.') from None
        except Exception as exc:
            if isinstance(exc, RecoveryError) and exc.cooldown:
                message = 'IoT token refresh is busy or cooling down. Wait at least 60 seconds and retry.'
            else:
                reason = classify_failure('token_refresh', exc)[1]
                message = {
                    'cloud_timeout': 'IoT token refresh timed out. Retry after the cooldown.',
                    'cloud_unavailable': 'IoT token refresh service is unavailable. Retry after the cooldown.',
                    'response_validation': 'IoT token refresh failed or the session manager is stopped. Check session diagnostics.',
                }.get(reason, 'IoT token refresh failed. Check session diagnostics.')
            raise HomeAssistantError(message) from None
