from homeassistant.components.sensor import SensorEntity
from .entity import AigoEntity

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AigoSensor(entry.runtime_data, key) for key in
        ('status', 'Target_temperature', 'Time', 'heatpreservation')])

class AigoSensor(AigoEntity, SensorEntity):
    @property
    def native_value(self):
        return self.value

    @property
    def native_unit_of_measurement(self):
        return {'Target_temperature': '°C', 'Time': 'min', 'heatpreservation': 'h'}.get(self.key)
