from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from .entity import AigoEntity
from .enum_labels import enum_label

async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    rows = [r for r in c.model['properties'] if r['identifier'] == 'Mode'
            and r['access'] == 'read-write' and r['data_type'] == 'enum']
    if len(rows) == 1 and rows[0]['constraints']:
        async_add_entities([ModeSelect(c, rows[0]['constraints'])])

class ModeSelect(AigoEntity, SelectEntity):
    def __init__(self, coordinator, choices):
        super().__init__(coordinator, 'Mode')
        self.choices = {str(k): str(v) for k,v in choices.items()}
        self._attr_options = list(self.choices)  # Stable TSL values; labels are attributes.

    @property
    def current_option(self):
        key = str(self.value)
        return key if key in self.choices else None

    @property
    def extra_state_attributes(self):
        return {**super().extra_state_attributes, 'mode_labels': self.choices,
                'current_mode_label': enum_label(self.coordinator.model, 'Mode', self.value)}

    async def async_select_option(self, option):
        if option not in self.choices:
            raise HomeAssistantError('Unknown TSL mode')
        await self.coordinator.async_write(self.key, int(option))
