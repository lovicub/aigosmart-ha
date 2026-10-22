"""Heating control via explicit user actions; no state restoration writes."""
from homeassistant.components.switch import SwitchEntity
from .entity import AigoEntity

async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    rows = [r for r in c.model['properties'] if r['identifier'] == 'HeatingSwitch'
            and r['access'] == 'read-write' and r['data_type'] == 'bool'
            and {'0', '1'} <= (r['constraints'] or {}).keys()]
    if len(rows) == 1:
        async_add_entities([HeatingSwitch(c, 'HeatingSwitch')])

class HeatingSwitch(AigoEntity, SwitchEntity):
    @property
    def is_on(self):
        return None if self.value is None else self.value == 1

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_write(self.key, 1)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_write(self.key, 0)
