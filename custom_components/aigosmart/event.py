"""Derived kettle events: water ready, heating interrupted, keep-warm finished."""
from homeassistant.components.event import EventEntity
from homeassistant.core import callback

from .entity import AigoEntity
from .ready import EVENT_TYPES, supported


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    if supported(c.model):
        async_add_entities([WaterEvent(c)])


class WaterEvent(AigoEntity, EventEntity):
    _attr_event_types = EVENT_TYPES

    def __init__(self, coordinator):
        super().__init__(coordinator, 'water_event', translation_key='water')

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        return None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_subscribe_ready(self._handle_ready))

    @callback
    def _handle_ready(self, events):
        for event_type, attributes in events:
            self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
