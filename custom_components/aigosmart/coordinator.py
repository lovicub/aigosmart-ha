"""Polling and serialized writes; no write retry, even after a timeout."""
import asyncio
from datetime import timedelta
import logging
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import is_auth_error
from .const import DEFAULT_INTERVAL

class AigoCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(hass, logging.getLogger(__name__), name='AigoSmart', config_entry=entry,
            update_interval=timedelta(seconds=entry.options.get('scan_interval', DEFAULT_INTERVAL)))
        self.client = client
        self.device = {'iotId': entry.data['device_id']}
        self.model = None
        self.write_result = None
        self._io_lock = asyncio.Lock()

    async def _async_update_data(self):
        async with self._io_lock:
            try:
                devices = await self.hass.async_add_executor_job(self.client.devices)
                if not any(d.get('iotId') == self.device['iotId'] and type(d.get('status')) is int
                           and d['status'] == 1 for d in devices):
                    raise UpdateFailed('Device offline')
                return await self.hass.async_add_executor_job(self.client.properties, self.device)
            except Exception as exc:
                if is_auth_error(exc):
                    raise ConfigEntryAuthFailed('Authentication required') from None
                raise UpdateFailed('Device unavailable') from None

    async def async_write(self, identifier, value):
        async with self._io_lock:
            if not self.last_update_success:
                raise HomeAssistantError('Device unavailable')
            try:
                await self.hass.async_add_executor_job(self.client.write, self.device, self.model, identifier, value)
                self.write_result = 'accepted_unconfirmed'
            except ValueError:
                raise HomeAssistantError('Value rejected by TSL or safety policy') from None
            except Exception as exc:
                self.write_result = 'outcome_unknown'
                if is_auth_error(exc):
                    raise ConfigEntryAuthFailed('Authentication required; write will not be retried') from None
            # Re-read only; never reissue the command. Bound waits keep unload simple.
            read_succeeded = False
            for delay in (0, 2, 5):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    data = await self.hass.async_add_executor_job(self.client.properties, self.device)
                    read_succeeded = True
                    self.async_set_updated_data(data)
                    if data.get(identifier, {}).get('value') == value:
                        self.write_result = 'confirmed'
                        self.async_update_listeners()
                        return self.write_result
                except Exception:
                    continue
            if not read_succeeded:
                self.async_set_update_error(UpdateFailed("Device unavailable after write"))
            self.async_update_listeners()
            return self.write_result
