import hashlib
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN

class AigoEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        ident = hashlib.sha256(coordinator.device['iotId'].encode()).hexdigest()
        self._attr_unique_id = f'{ident}_{self.__class__.__name__}_{key}'
        self._attr_name = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, ident)}, name='AigoSmart kettle', manufacturer='Aigostar')

    @property
    def available(self):
        return super().available and self.key in (self.coordinator.data or {})

    @property
    def value(self):
        return (self.coordinator.data or {}).get(self.key, {}).get('value')

    @property
    def extra_state_attributes(self):
        return {'last_write_result': self.coordinator.write_result}
