"""Offline reconnect, sanitization and post-refresh rejection regressions."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import test_session_refresh as fixtures

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from custom_components.aigosmart.protocol import APIError, NeedSecurityCodeError
from custom_components.aigosmart.config_flow import AigoFlow


setUpModule = fixtures.setUpModule


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SessionTests.asyncSetUp
    asyncTearDown = fixtures.SessionTests.asyncTearDown
    expire = fixtures.SessionTests.expire
    async def test_repeated_rejections_request_reauth(self):
        for status in (401, 403):
            self.manager.status = 'authorized'
            read = Mock(side_effect=APIError('SECRET', status=status))
            with self.assertRaises(ConfigEntryAuthFailed):
                await self.manager.read(read)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(self.manager.status, 'reauth_required')

    async def test_reconnect_drains_refresh_and_preserves_identity(self):
        flow = AigoFlow(); flow.hass = self.hass
        flow.context = {'source': 'reauth'}
        self.entry.runtime_data = SimpleNamespace(session=self.manager)
        self.entry.unique_id = 'original_unique'; self.entry.entry_id = 'original_entry'
        self.entry.options = {'scan_interval': 45}
        flow._get_reauth_entry = Mock(return_value=self.entry)
        flow.credentials = {'email': 'PRIVATE@example.test', 'password': 'SECRET'}
        flow.client = Mock(token='RECONNECTED', session={'refresh_token': 'RECONNECTED_REFRESH'})
        flow.client.devices.return_value = [{'iotId': 'fake'}]
        def update(entry, *, data_updates):
            self.hass.config_entries.async_update_entry(entry, data={**entry.data, **data_updates})
            return {'type': 'abort'}
        flow.async_update_reload_and_abort = Mock(side_effect=update)
        started, finish = asyncio.Event(), asyncio.Event()
        executor = self.hass.async_add_executor_job
        async def blocked(fn, *args):
            if fn == self.client.refresh_iot_token_sync:
                started.set(); await finish.wait()
            return await executor(fn, *args)
        self.hass.async_add_executor_job = blocked
        self.expire()
        refresh = asyncio.create_task(self.manager.ensure())
        await started.wait()
        login = asyncio.create_task(flow._login())
        await asyncio.sleep(0); await asyncio.sleep(0)
        flow.async_update_reload_and_abort.assert_not_called()
        finish.set(); await refresh; await login
        self.assertEqual(self.entry.data['iot_token'], 'RECONNECTED')
        self.assertEqual(self.entry.data['refresh_token'], 'RECONNECTED_REFRESH')
        self.assertEqual(self.entry.data['device_id'], 'fake')
        self.assertEqual(self.entry.unique_id, 'original_unique')
        self.assertEqual(self.entry.entry_id, 'original_entry')
        self.assertEqual(self.entry.options, {'scan_interval': 45})
        self.assertNotIn('password', self.entry.data)

    async def test_reconnect_code_rejection_and_success(self):
        flow = AigoFlow(); flow.hass = self.hass; flow.context = {'source': 'reauth'}
        flow.client = Mock(token='NEW', session={})
        flow.client.login_with_code.side_effect = [NeedSecurityCodeError('SECRET'), APIError('SECRET', status=401), None]
        flow.client.devices.return_value = [{'iotId': 'fake'}]
        self.entry.runtime_data = None
        flow._get_reauth_entry = Mock(return_value=self.entry)
        flow.async_update_reload_and_abort = Mock(return_value={'type': 'abort'})
        result = await flow.async_step_user({'email': 'private@example.test', 'password': 'SECRET'})
        self.assertEqual(result['step_id'], 'security_code')
        result = await flow.async_step_security_code({'security_code': 'bad'})
        self.assertEqual(result['errors']['base'], 'invalid_code')
        self.assertEqual((await flow.async_step_security_code({'security_code': 'good'}))['type'], 'abort')
        flow.client.send_security_code.assert_not_called()

    async def test_wrong_kettle_cannot_replace_session(self):
        flow = AigoFlow(); flow.hass = self.hass; flow.context = {'source': 'reauth'}
        flow.client = Mock(); flow.client.devices.return_value = [{'iotId': 'different'}]
        flow.credentials = {'email': 'private@example.test', 'password': 'SECRET'}
        flow._get_reauth_entry = Mock(return_value=self.entry)
        flow.async_update_reload_and_abort = Mock()
        self.assertEqual((await flow._login())['reason'], 'wrong_account')
        flow.async_update_reload_and_abort.assert_not_called()

    async def test_login_rejection_and_outage_leave_entry_unchanged(self):
        for exc, expected in ((APIError('SECRET', status=401), 'invalid_auth'),
                              (APIError('SECRET', status=503), 'cannot_connect')):
            flow = AigoFlow(); flow.hass = self.hass; flow.context = {'source': 'reauth'}
            flow.client = Mock(); flow.client.login_with_code.side_effect = exc
            old = dict(self.entry.data)
            flow.async_update_reload_and_abort = Mock()
            result = await flow.async_step_user({'email': 'private@example.test', 'password': 'SECRET'})
            self.assertEqual(result['errors']['base'], expected)
            self.assertEqual(self.entry.data, old)
            flow.async_update_reload_and_abort.assert_not_called()

    async def test_last_transient_attempt_still_confirms_refreshed_token(self):
        read = Mock(side_effect=[APIError('Temporary', status=503),
            APIError('Temporary', status=503), APIError('Expired', status=401), {'ok': True}])
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            self.assertEqual(await self.manager.read(read), {'ok': True})
        self.assertEqual(read.call_count, 4)
        self.send.assert_called_once()

    async def test_real_ha_update_helper_merges_and_schedules_reload(self):
        from homeassistant.config_entries import UNDEFINED
        flow = AigoFlow(); flow.hass = self.hass; flow.context = {'source': 'reauth'}
        entry = SimpleNamespace(data={**self.entry.data, 'future_field': 'preserved'},
            runtime_data=None, entry_id='original', unique_id='unchanged', options={'scan_interval': 90},
            update_listeners=[])
        flow._get_reauth_entry = Mock(return_value=entry)
        flow.credentials = {'email': 'private@example.test', 'password': 'SECRET'}
        flow.client = Mock(token='new', session={'refresh_token': 'new_refresh'})
        flow.client.devices.return_value = [{'iotId': 'fake'}]
        def update(entry, **kwargs):
            for key, value in kwargs.items():
                if value is not UNDEFINED:
                    setattr(entry, key, value)
            return True
        self.hass.config_entries.async_update_entry.side_effect = update
        self.hass.config_entries.async_schedule_reload = Mock()
        result = await flow._login()
        self.assertEqual(result['reason'], 'reauth_successful')
        self.assertEqual(entry.data['future_field'], 'preserved')
        self.assertEqual(entry.data['device_id'], 'fake')
        self.assertEqual(entry.unique_id, 'unchanged')
        self.assertEqual(entry.options, {'scan_interval': 90})
        self.hass.config_entries.async_schedule_reload.assert_called_once_with('original')


class SetupRecoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.LifecycleTests.asyncSetUp
    asyncTearDown = fixtures.LifecycleTests.asyncTearDown
    setup = fixtures.LifecycleTests.setup
    async def test_tsl_failure_is_sanitized_and_retryable(self):
        self.client.model.side_effect = APIError('email SECRET device-id', status=503)
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            with self.assertLogs('custom_components.aigosmart.recovery', level='WARNING') as logs:
                with self.assertRaises(ConfigEntryNotReady) as error:
                    await self.setup()
        self.assertIn('model_tsl_fetch', str(error.exception))
        self.assertIn('cloud_unavailable', str(error.exception))
        self.assertNotIn('SECRET', str(logs.output))
        self.client.model.side_effect = None
        self.assertTrue(await self.setup())
        self.client.write.assert_not_called()

    async def test_poll_outage_and_offline_device_recover_without_restart(self):
        await self.setup()
        self.client.properties.side_effect = APIError('PRIVATE', status=503)
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            await self.coordinator.async_refresh()
        self.assertFalse(self.coordinator.last_update_success)
        self.entry.async_start_reauth.assert_not_called()
        self.client.properties.side_effect = None
        await self.coordinator.async_refresh()
        self.assertTrue(self.coordinator.last_update_success)
        self.client.devices.return_value = []
        await self.coordinator.async_refresh()
        self.assertFalse(self.coordinator.last_update_success)
        self.client.devices.return_value = [{'iotId': 'fake', 'status': 1}]
        await self.coordinator.async_refresh()
        self.assertTrue(self.coordinator.last_update_success)
        self.client.write.assert_not_called()
