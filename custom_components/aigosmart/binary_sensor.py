from homeassistant.components.binary_sensor import BinarySensorEntity
from .entity import AigoEntity
from .ready import supported

async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    entities = [HeatingSensor(c, 'HeatingSwitch')]
    if supported(c.model):
        entities.append(WaterReadySensor(c))
    async_add_entities(entities)

class HeatingSensor(AigoEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return None if self.value is None else self.value == 1


class WaterReadySensor(AigoEntity, BinarySensorEntity):
    """On from the "ready" event until the water cools to more than 5 °C below the
    target, or a new heating cycle starts (see ready.py)."""
    _attr_icon = 'mdi:kettle-steam'

    def __init__(self, coordinator):
        super().__init__(coordinator, 'water_ready', translation_key='water_ready')

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        return None

    @property
    def is_on(self):
        return self.coordinator.ready.ready
