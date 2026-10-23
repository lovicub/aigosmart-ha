from datetime import datetime, timezone
import time

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import EntityCategory
from .entity import AigoEntity

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AigoSensor(entry.runtime_data, key) for key in
        ('status', 'Target_temperature', 'Time', 'heatpreservation')] + [
        AigoSessionSensor(entry.runtime_data, key) for key in
        ('session_time_remaining', 'last_successful_refresh', 'authorization_status')])

class AigoSensor(AigoEntity, SensorEntity):
    @property
    def native_value(self):
        return self.value

    @property
    def native_unit_of_measurement(self):
        return {'Target_temperature': '°C', 'Time': 'min', 'heatpreservation': 'h'}.get(self.key)


class AigoSessionSensor(AigoEntity, SensorEntity):
    """Fixed diagnostic vocabulary, never tokens or identity IDs."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._attr_name = {'session_time_remaining': 'Session time remaining',
            'last_successful_refresh': 'Last successful refresh',
            'authorization_status': 'Authorization status'}[key]
        if key == 'last_successful_refresh':
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        session = self.coordinator.client.session
        if self.key == 'authorization_status':
            return self.coordinator.session.status
        if self.key == 'last_successful_refresh':
            value = session.get('last_refresh')
            return datetime.fromtimestamp(value, timezone.utc) if value else None
        end = session.get('iot_token_expires_at')
        return max(0, int(end - time.time())) if end else None

    @property
    def native_unit_of_measurement(self):
        return 's' if self.key == 'session_time_remaining' else None

    @property
    def extra_state_attributes(self):
        return None
