"""Exercise real HA flow management and registries without cloud or hardware."""
import hashlib
from tempfile import TemporaryDirectory
from types import MappingProxyType
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntries, ConfigEntry, SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from custom_components.aigosmart.config_flow import AigoFlow
from custom_components.aigosmart.protocol import APIError, NeedSecurityCodeError
from test_session_refresh import response, setUpModule


class ReconnectFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory(prefix='aigosmart-flow-')
        self.hass = HomeAssistant(self.directory.name)
        async def executor(fn, *args):
            return fn(*args)
        self.hass.async_add_executor_job = executor
        self.hass.config_entries = ConfigEntries(self.hass, {})
        await self.hass.config_entries.async_initialize()
        await ar.async_load(self.hass, load_empty=True)
        dr.async_setup(self.hass)
        await dr.async_load(self.hass, load_empty=True)
        await er.async_load(self.hass, load_empty=True)
        self.entry = ConfigEntry(domain='aigosmart', version=2, minor_version=1,
            source='user', title='Original kettle', unique_id=hashlib.sha256(b'fake').hexdigest(),
            data={'email': 'private@example.test', 'device_id': 'fake'}, options={'scan_interval': 45},
            discovery_keys=MappingProxyType({}), subentries_data=[])
        with patch.object(self.hass.config_entries, 'async_setup', new=AsyncMock(return_value=True)):
            await self.hass.config_entries.async_add(self.entry)
        self.area = ar.async_get(self.hass).async_create('Kitchen')
        self.devices = dr.async_get(self.hass)
        self.device = self.devices.async_get_or_create(config_entry_id=self.entry.entry_id,
            identifiers={('aigosmart', self.entry.unique_id)}, name='Original kettle')
        self.devices.async_update_device(self.device.id, area_id=self.area.id)
        self.entities = er.async_get(self.hass)
        self.entity = self.entities.async_get_or_create('sensor', 'aigosmart',
            self.entry.unique_id + '_AigoSensor_Target_temperature',
            config_entry=self.entry, device_id=self.device.id, suggested_object_id='kettle_temperature')
        self.entities.async_update_entity(self.entity.entity_id, area_id=self.area.id, name='My temperature')
        self.handler = patch('homeassistant.config_entries._async_get_flow_handler',
            new=AsyncMock(return_value=AigoFlow))
        self.handler.start(); self.addCleanup(self.handler.stop)
        self.reload = patch.object(self.hass.config_entries, 'async_schedule_reload')
        self.reload_mock = self.reload.start(); self.addCleanup(self.reload.stop)
        self.device_call = patch('custom_components.aigosmart.api.AigoClient.devices',
            return_value=[{'iotId': 'fake'}])
        self.device_call.start(); self.addCleanup(self.device_call.stop)
        def accept(client, email, password, code=None):
            client.accept_session(response())
        self.client_login = patch('custom_components.aigosmart.api.AigoClient.login_with_code', autospec=True, side_effect=accept)
        self.login_mock = self.client_login.start(); self.addCleanup(self.client_login.stop)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def begin(self):
        result = await self.hass.config_entries.flow.async_init('aigosmart', context={
            'source': 'reconfigure', 'entry_id': self.entry.entry_id})
        self.assertEqual(result['reason'], 'reauth_started')
        flow_id = result['next_flow'][1]
        flow = self.hass.config_entries.flow.async_get(flow_id)
        self.assertEqual(flow['context']['source'], SOURCE_REAUTH)
        self.assertEqual(flow['step_id'], 'reauth_confirm')
        return flow_id

    async def complete(self, flow_id):
        form = await self.hass.config_entries.flow.async_configure(flow_id, {})
        self.assertEqual(form['step_id'], 'user')
        return await self.hass.config_entries.flow.async_configure(flow_id,
            {'email': 'PRIVATE@example.test', 'password': 'SECRET'})

    def assert_preserved(self):
        self.assertEqual(self.hass.config_entries.async_entries('aigosmart'), [self.entry])
        self.assertEqual(self.entry.data['device_id'], 'fake')
        self.assertEqual(self.entry.options, {'scan_interval': 45})
        self.assertEqual(self.entry.unique_id, hashlib.sha256(b'fake').hexdigest())
        self.assertEqual(len(self.devices.devices), 1)
        self.assertEqual(len(self.entities.entities), 1)
        self.assertEqual(self.entities.async_get(self.entity.entity_id).device_id, self.device.id)
        self.assertEqual(self.entities.async_get(self.entity.entity_id).area_id, self.area.id)
        self.assertEqual(self.devices.async_get(self.device.id).area_id, self.area.id)
        self.assertEqual(self.entities.async_get(self.entity.entity_id).name, 'My temperature')

    async def test_manual_handoff_updates_existing_entry_and_registries(self):
        result = await self.complete(await self.begin())
        self.assertEqual(result['reason'], 'reauth_successful')
        self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')
        self.reload_mock.assert_called_once_with(self.entry.entry_id)
        self.assert_preserved()

    async def test_manual_handoff_reuses_existing_reauth(self):
        first = await self.begin()
        self.assertEqual(await self.begin(), first)
        self.assertEqual(len(self.hass.config_entries.flow.async_progress()), 1)

    async def test_automatic_reauth_updates_entry_and_preserves_registries(self):
        self.entry.async_start_reauth(self.hass)
        await self.hass.async_block_till_done()
        flows = self.hass.config_entries.flow.async_progress()
        self.assertEqual(len(flows), 1)
        result = await self.complete(flows[0]['flow_id'])
        self.assertEqual(result['reason'], 'reauth_successful')
        self.assert_preserved()

    async def test_failed_automatic_reauth_keeps_registries_and_does_not_reload(self):
        self.login_mock.side_effect = APIError('PRIVATE', status=401)
        self.entry.async_start_reauth(self.hass)
        await self.hass.async_block_till_done()
        result = await self.complete(self.hass.config_entries.flow.async_progress()[0]['flow_id'])
        self.assertEqual(result['errors']['base'], 'invalid_auth')
        self.reload_mock.assert_not_called()
        self.assert_preserved()

    async def test_verification_flow_preserves_registries(self):
        def challenge(client, email, password, code=None):
            if code is None:
                raise NeedSecurityCodeError('PRIVATE')
            if code != 'good':
                raise APIError('PRIVATE', status=401)
            client.accept_session(response())
        self.login_mock.side_effect = challenge
        flow_id = await self.begin()
        result = await self.complete(flow_id)
        self.assertEqual(result['step_id'], 'security_code')
        with patch('custom_components.aigosmart.api.AigoClient.send_security_code') as send:
            await self.hass.config_entries.flow.async_configure(flow_id, {'send_code': True})
            send.assert_called_once()
        result = await self.hass.config_entries.flow.async_configure(flow_id, {'security_code': 'bad'})
        self.assertEqual(result['errors']['base'], 'invalid_code')
        result = await self.hass.config_entries.flow.async_configure(flow_id, {'security_code': 'good'})
        self.assertEqual(result['reason'], 'reauth_successful')
        self.assert_preserved()
