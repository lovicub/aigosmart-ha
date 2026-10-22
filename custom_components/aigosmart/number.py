from homeassistant.components.number import NumberEntity
from .entity import AigoEntity

async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    entities = []
    for key, cls in (('Target_temperature', TemperatureNumber), ('heatpreservation', PreservationNumber)):
        rows = [r for r in c.model['properties'] if r['identifier'] == key
                and r['access'] == 'read-write' and r['data_type'] == 'int']
        if len(rows) == 1 and all(k in (rows[0]['constraints'] or {}) for k in ('min', 'max', 'step')):
            entities.append(cls(c, rows[0]['constraints']))
    async_add_entities(entities)

class TemperatureNumber(AigoEntity, NumberEntity):
    _attr_native_unit_of_measurement = '°C'
    property_key = 'Target_temperature'
    def __init__(self, coordinator, limits):
        super().__init__(coordinator, self.property_key)
        self._attr_native_min_value = float(limits['min'])
        self._attr_native_max_value = float(limits['max'])
        self._attr_native_step = float(limits['step'])

    @property
    def native_value(self):
        return self.value

    async def async_set_native_value(self, value):
        from homeassistant.exceptions import HomeAssistantError
        if not float(value).is_integer():
            raise HomeAssistantError('Integer value required')
        await self.coordinator.async_write(self.key, int(value))


class PreservationNumber(TemperatureNumber):
    property_key = 'heatpreservation'
    _attr_native_unit_of_measurement = 'h'
