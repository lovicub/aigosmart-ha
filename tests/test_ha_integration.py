"""Offline integration checks against installed Home Assistant classes."""
import asyncio
import json
import time
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch
from custom_components.aigosmart.api import AigoClient
from custom_components.aigosmart.protocol import APIError

def setUpModule():
    import socket
    guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
    guard.start()
    unittest.addModuleCleanup(guard.stop)

MODEL = json.loads(Path('tests/fixtures/kettle_capabilities.json').read_text())

class ApiTests(unittest.TestCase):
    def test_dry_run_has_no_transport(self):
        send = Mock()
        client = AigoClient(send)
        for key,value in [('Target_temperature',80),('Mode',1),('HeatingSwitch',0),('HeatingSwitch',1),('heatpreservation',0),('heatpreservation',13)]:
            self.assertFalse(client.write({'iotId':'fake'},MODEL,key,value,dry_run=True)['executed'])
        send.assert_not_called()

    def test_blocked_and_invalid(self):
        send = Mock()
        c = AigoClient(send)
        for key,value in [('HeatingSwitch',2),('HeatingSwitch',True),('HeatingSwitch',1.0),('heatpreservation',14),('heatpreservation',-1),('heatpreservation',1.5),('status',1),('Time',2),('Mode',99),('Target_temperature',101),('Target_temperature',True),('Target_temperature',80.5)]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                c.write({'iotId':'fake'},MODEL,key,value)
        send.assert_not_called()

    def test_exactly_one_attempt(self):
        send = Mock(side_effect=APIError('Timeout'))
        c = AigoClient(send)
        with self.assertRaises(APIError): c.write({'iotId':'fake'},MODEL,'Target_temperature',80)
        self.assertEqual(send.call_count,1)
        self.assertIsNone(c._permission)

    def test_accepted_unconfirmed(self):
        send = Mock(return_value={'code':200})
        self.assertEqual(AigoClient(send).write({'iotId':'fake'},MODEL,'Mode',1),'accepted_unconfirmed')
        self.assertEqual(send.call_count,1)

    def test_all_controls_send_one_validated_payload(self):
        for key, value in [('HeatingSwitch', 0), ('HeatingSwitch', 1),
                           ('heatpreservation', 0), ('heatpreservation', 13),
                           ('Target_temperature', 0), ('Target_temperature', 100),
                           ('Mode', 0), ('Mode', 1), ('Mode', 2)]:
            with self.subTest(key=key, value=value):
                send = Mock(return_value={'code': 200})
                client = AigoClient(send)
                self.assertEqual(client.write({'iotId':'fake'}, MODEL, key, value), 'accepted_unconfirmed')
                send.assert_called_once()
                method, url, headers, body = send.call_args.args
                self.assertEqual(method, 'POST')
                self.assertTrue(url.endswith('/thing/properties/set'))
                self.assertEqual(json.loads(body)['params'], {'iotId':'fake', 'items':{key:value}})

    def test_heating_timeout_consumes_permission(self):
        send = Mock(side_effect=APIError('Timeout'))
        client = AigoClient(send)
        with self.assertRaises(APIError):
            client.write({'iotId':'fake'}, MODEL, 'HeatingSwitch', 1)
        send.assert_called_once()
        self.assertIsNone(client._permission)

    def test_new_controls_require_writable_live_tsl(self):
        from copy import deepcopy
        for key in ('HeatingSwitch', 'heatpreservation'):
            for invalid in ('source', 'read_only', 'missing'):
                model = deepcopy(MODEL)
                if invalid == 'source':
                    model['source'] = 'telemetry-only'
                elif invalid == 'read_only':
                    next(r for r in model['properties'] if r['identifier'] == key)['access'] = 'read-only'
                else:
                    model['properties'] = [r for r in model['properties'] if r['identifier'] != key]
                send = Mock()
                with self.assertRaises(ValueError):
                    AigoClient(send).write({'iotId':'fake'}, model, key, 1)
                send.assert_not_called()

class HATests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from homeassistant.core import HomeAssistant
        self.hass = HomeAssistant('/tmp/aigosmart-offline-ha')
        async def executor(target, *args):
            return target(*args)
        self.hass.async_add_executor_job = executor
        self.client = Mock()
        self.client.token = 'fake-token'
        self.client.session = {'iot_token': 'fake-token', 'refresh_token': 'fake-refresh',
            'identity_id': 'fake-identity', 'iot_token_ttl': 7200,
            'iot_token_expires_at': time.time() + 7200,
            'refresh_token_expires_at': time.time() + 86400}
        self.client.devices.return_value = [{'iotId':'fake','status':1}]
        self.client.properties.return_value = {'Target_temperature':{'value':80}, 'Mode':{'value':1},'HeatingSwitch':{'value':0}}
        self.entry = Mock(data={'device_id':'fake'},options={},entry_id='fake')
        from custom_components.aigosmart.coordinator import AigoCoordinator
        self.c = AigoCoordinator(self.hass,self.entry,self.client)
        self.c.model = MODEL
        self.c.async_set_updated_data(self.client.properties.return_value)

    async def asyncTearDown(self):
        await self.c.session.close()
        await self.c.async_shutdown()
        await self.hass.async_stop(force=True)

    async def test_update_and_offline(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        self.assertEqual((await self.c._async_update_data())['Mode']['value'],1)
        self.client.devices.return_value=[]
        with self.assertRaises(UpdateFailed): await self.c._async_update_data()

    async def test_auth_error(self):
        from homeassistant.exceptions import ConfigEntryAuthFailed
        self.client.devices.side_effect=APIError('Expired',status=401)
        self.client.refresh_iot_token_sync.side_effect=APIError('Rejected',status=401)
        with self.assertRaises(ConfigEntryAuthFailed): await self.c._async_update_data()

    async def test_entities(self):
        from custom_components.aigosmart.sensor import AigoSensor
        from custom_components.aigosmart.binary_sensor import HeatingSensor
        from custom_components.aigosmart.number import TemperatureNumber
        from custom_components.aigosmart.select import ModeSelect
        self.assertEqual(AigoSensor(self.c,'Target_temperature').native_value,80)
        self.assertFalse(HeatingSensor(self.c,'HeatingSwitch').is_on)
        self.assertEqual(ModeSelect(self.c,{'1':'Warm'}).current_option,'1')
        n=TemperatureNumber(self.c,{'min':0,'max':100,'step':1})
        self.assertEqual(n.native_max_value,100)
        self.c.async_write=AsyncMock()
        await n.async_set_native_value(80)
        self.c.async_write.assert_awaited_once_with('Target_temperature',80)
        self.c.last_update_success=False
        self.assertFalse(n.available)

    async def test_write_confirmed(self):
        self.assertEqual(await self.c.async_write('Target_temperature',80),'confirmed')
        self.client.write.assert_called_once()

    async def test_write_delayed_unconfirmed(self):
        with patch('custom_components.aigosmart.coordinator.asyncio.sleep',new=AsyncMock()):
            self.assertEqual(await self.c.async_write('Target_temperature',90),'accepted_unconfirmed')
        self.client.write.assert_called_once()
        self.assertEqual(self.client.properties.call_count,3)

    async def test_write_timeout_no_retry(self):
        self.client.write.side_effect=APIError('Timeout')
        self.client.properties.side_effect=APIError('Disconnected')
        with patch('custom_components.aigosmart.coordinator.asyncio.sleep',new=AsyncMock()):
            self.assertEqual(await self.c.async_write('Target_temperature',90),'outcome_unknown')
        self.client.write.assert_called_once()

    async def test_config_device(self):
        from custom_components.aigosmart.config_flow import AigoFlow
        flow=AigoFlow(); flow.hass=self.hass
        flow.devices=[{'iotId':'fake'}]; flow.credentials={'email':'a@example.test','password':'secret'}
        flow.async_set_unique_id=AsyncMock(); flow._abort_if_unique_id_configured=Mock()
        result=await flow.async_step_device({'device':'0'})
        self.assertEqual(result['data']['device_id'],'fake')
        self.assertEqual(result['type'],'create_entry')

    async def test_config_challenge(self):
        from custom_components.aigosmart.config_flow import AigoFlow
        from custom_components.aigosmart.protocol import NeedSecurityCodeError
        flow=AigoFlow();flow.hass=self.hass
        flow.client=Mock(); flow.client.login_with_code.side_effect=NeedSecurityCodeError('Challenge')
        result=await flow.async_step_user({'email':'a@example.test','password':'secret'})
        self.assertEqual(result['step_id'],'security_code')
        flow.client.send_security_code.assert_not_called()
        await flow.async_step_security_code({'send_code':True})
        flow.client.send_security_code.assert_called_once()

    async def test_reauth_updates_existing(self):
        from custom_components.aigosmart.config_flow import AigoFlow
        flow=AigoFlow();flow.hass=self.hass
        flow.context={'source':'reauth'}
        flow.client=Mock();flow.client.session={'refresh_token':'rotated', 'identity_id':'identity',
            'iot_token_expires_at': 2000000000, 'refresh_token_expires_at': 2000086400};flow.client.devices.return_value=[{'iotId':'fake'}]
        flow.credentials={'email':'a@example.test','password':'new'}
        entry=Mock(data={'email':'a@example.test','device_id':'fake'})
        flow._get_reauth_entry=Mock(return_value=entry)
        flow.async_update_reload_and_abort=Mock(return_value={'type':'abort'})
        self.assertEqual((await flow._login())['type'],'abort')
        flow.async_update_reload_and_abort.assert_called_once()
        self.assertNotIn('password', flow.async_update_reload_and_abort.call_args.kwargs['data_updates'])
        self.assertEqual(flow.async_update_reload_and_abort.call_args.kwargs['data_updates']['refresh_token'], 'rotated')
        flow.credentials={'email':'a@example.test','password':'new'}
        flow.credentials['email']='other@example.test'
        self.assertEqual((await flow._login())['reason'],'wrong_account')

    async def test_successful_login_does_not_store_password(self):
        from custom_components.aigosmart.config_flow import AigoFlow
        flow=AigoFlow();flow.hass=self.hass;flow.client=Mock();flow.client.session={'refresh_token':'rotated',
            'identity_id':'identity', 'iot_token_expires_at':2000000000, 'refresh_token_expires_at':2000086400}
        flow.client.devices.return_value=[{'iotId':'fake'}]
        flow.client.token='fake-token'
        result=await flow.async_step_user({'email':'a@example.test','password':'secret'})
        self.assertEqual(result['step_id'],'device')
        flow.async_set_unique_id=AsyncMock();flow._abort_if_unique_id_configured=Mock()
        result=await flow.async_step_device({'device':'0'})
        self.assertNotIn('password',result['data'])
        self.assertEqual(result['data']['iot_token'],'fake-token')
        self.assertEqual(result['data']['refresh_token'], 'rotated')
        self.assertEqual(result['data']['refresh_token_expires_at'], 2000086400)
        flow.client.login_with_code.assert_called_once()

    async def test_polling_reuses_session(self):
        await self.c._async_update_data()
        await self.c._async_update_data()
        self.client.login_with_code.assert_not_called()
        self.assertEqual(self.client.properties.call_count,2)

    async def test_offline_write_is_blocked(self):
        from homeassistant.exceptions import HomeAssistantError
        self.c.last_update_success=False
        with self.assertRaises(HomeAssistantError):
            await self.c.async_write('Target_temperature',80)
        self.client.write.assert_not_called()

    async def test_options_interval(self):
        from custom_components.aigosmart.config_flow import AigoOptions
        flow=AigoOptions()
        result=await flow.async_step_init({'scan_interval':30})
        self.assertEqual(result['data']['scan_interval'],30)


    async def test_switch_on_off_explicit_actions_only(self):
        from custom_components.aigosmart.switch import async_setup_entry, HeatingSwitch
        self.entry.runtime_data = self.c
        add = Mock()
        await async_setup_entry(self.hass, self.entry, add)
        switch = add.call_args.args[0][0]
        self.assertIsInstance(switch, HeatingSwitch)
        self.assertFalse(switch.is_on)
        self.client.write.assert_not_called()
        self.c.async_write = AsyncMock()
        await switch.async_turn_on()
        await switch.async_turn_off()
        self.assertEqual(self.c.async_write.await_args_list,
                         [unittest.mock.call('HeatingSwitch', 1), unittest.mock.call('HeatingSwitch', 0)])

    async def test_number_platform_preservation_range_and_action(self):
        from custom_components.aigosmart.number import async_setup_entry
        from homeassistant.exceptions import HomeAssistantError
        self.entry.runtime_data = self.c
        add = Mock()
        await async_setup_entry(self.hass, self.entry, add)
        numbers = {e.key:e for e in add.call_args.args[0]}
        self.assertEqual(set(numbers), {'Target_temperature', 'heatpreservation'})
        n = numbers['heatpreservation']
        self.assertEqual((n.native_min_value, n.native_max_value, n.native_step), (0, 13, 1))
        self.assertEqual(n.native_unit_of_measurement, 'h')
        self.c.async_write = AsyncMock()
        await n.async_set_native_value(13)
        self.c.async_write.assert_awaited_once_with('heatpreservation', 13)
        with self.assertRaises(HomeAssistantError):
            await n.async_set_native_value(1.5)

    async def test_startup_reads_without_restoring_heating(self):
        from custom_components.aigosmart import async_setup_entry
        from homeassistant.config_entries import ConfigEntryState
        self.entry.state = ConfigEntryState.SETUP_IN_PROGRESS
        self.entry.data = {'device_id':'fake', 'iot_token':'fake-token'}
        self.client.model.return_value = MODEL
        self.hass.config_entries = Mock()
        self.hass.config_entries.async_forward_entry_setups = AsyncMock()
        with patch('custom_components.aigosmart.api.AigoClient', return_value=self.client):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
        try:
            self.client.write.assert_not_called()
            self.client.signed.assert_not_called()
            self.client.login_with_code.assert_not_called()
            self.assertIn('switch', self.hass.config_entries.async_forward_entry_setups.call_args.args[1])
        finally:
            await self.entry.runtime_data.session.close()
            await self.entry.runtime_data.async_shutdown()

    async def test_heating_confirmed_and_unconfirmed(self):
        self.client.properties.return_value = {'HeatingSwitch': {'value': 1}}
        self.assertEqual(await self.c.async_write('HeatingSwitch', 1), 'confirmed')
        self.client.write.reset_mock()
        with patch('custom_components.aigosmart.coordinator.asyncio.sleep', new=AsyncMock()):
            self.assertEqual(await self.c.async_write('HeatingSwitch', 0), 'accepted_unconfirmed')
        self.client.write.assert_called_once()
