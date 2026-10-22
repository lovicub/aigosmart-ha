from homeassistant.components.binary_sensor import BinarySensorEntity
from .entity import AigoEntity

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HeatingSensor(entry.runtime_data, 'HeatingSwitch')])

class HeatingSensor(AigoEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return None if self.value is None else self.value == 1
