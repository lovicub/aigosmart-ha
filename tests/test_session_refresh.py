"""Offline failure/restart/race tests; no cloud or device connections allowed."""
import asyncio
from contextlib import redirect_stderr
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from custom_components.aigosmart.api import AigoClient
from custom_components.aigosmart import protocol as p
from custom_components.aigosmart.session import SessionManager


def setUpModule():
    import socket
    guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
    guard.start()
    unittest.addModuleCleanup(guard.stop)


def response(**overrides):
    return {'iotToken': 'NEW_IOT_SECRET', 'refreshToken': 'NEW_REFRESH_SECRET',
            'identityId': 'IDENTITY_SECRET', 'iotTokenExpire': '3600',
            'refreshTokenExpire': '86400', **overrides}


class ProtocolTests(unittest.TestCase):
    def test_ttl_is_seconds_and_all_fields_survive(self):
        c = AigoClient(Mock())
        with patch.object(p.time, 'time', return_value=1000):
            c.accept_session(response())
        self.assertEqual(c.session, {'iot_token': 'NEW_IOT_SECRET',
            'refresh_token': 'NEW_REFRESH_SECRET', 'identity_id': 'IDENTITY_SECRET',
            'iot_token_ttl': 3600, 'refresh_token_ttl': 86400,
            'iot_token_expires_at': 4600, 'refresh_token_expires_at': 87400, 'last_refresh': None})

    def test_bad_ttl_does_not_partially_rotate(self):
        c = AigoClient(Mock())
        c.accept_session(response())
        old = dict(c.session)
        for value in (None, 0, -1, True, 'secret', float('inf'), 'nan'):
            with self.subTest(value=value), self.assertRaises(p.APIError):
                c.accept_session(response(iotToken='ROTATED', iotTokenExpire=value), refresh=True)
            self.assertEqual(c.session, old)
            self.assertEqual(c.token, old['iot_token'])

    def test_refresh_envelope_and_no_expired_iot_token(self):
        send = Mock(return_value={'code': 200, 'data': response()})
        c = AigoClient(send)
        c.accept_session(response(iotToken='EXPIRED', refreshToken='OLD_REFRESH'))
        c.refresh_iot_token_sync()
        body = json.loads(send.call_args.args[3])
        self.assertEqual(send.call_args.args[1], p.IOT + p.REFRESH)
        self.assertEqual(body['params'], {'refreshToken': 'OLD_REFRESH', 'identityId': 'IDENTITY_SECRET'})
        self.assertEqual(body['request']['apiVer'], '1.0.4')
        self.assertNotIn('iotToken', body['request'])
        self.assertEqual(c.session['refresh_token'], 'NEW_REFRESH_SECRET')

    def test_omitted_refresh_keeps_original_absolute_deadline(self):
        c = AigoClient(Mock())
        with patch.object(p.time, 'time', return_value=1000):
            c.accept_session(response())
        data = {'iotToken': 'NEXT', 'iotTokenExpire': 1200}
        with patch.object(p.time, 'time', return_value=2000):
            c.accept_session(data, refresh=True)
        self.assertEqual(c.session['refresh_token_expires_at'], 87400)
        self.assertEqual(c.session['refresh_token'], 'NEW_REFRESH_SECRET')
        self.assertEqual(c.session['last_refresh'], 2000)

    def test_rotated_refresh_requires_its_own_ttl(self):
        c = AigoClient(Mock())
        c.accept_session(response())
        with self.assertRaises(p.APIError):
            c.accept_session({'iotToken': 'NEXT', 'iotTokenExpire': 1200,
                'refreshToken': 'ROTATED'}, refresh=True)
        self.assertEqual(c.session['refresh_token'], 'NEW_REFRESH_SECRET')

    def test_no_credentials_in_debug_on_success_or_failure(self):
        for reply in ({'code': 200, 'data': response()},
                      {'code': 100003, 'message': 'NEW_REFRESH_SECRET', 'data': response()}):
            c = AigoClient(Mock(return_value=reply), debug=True)
            c.accept_session(response())
            output = io.StringIO()
            with redirect_stderr(output):
                try:
                    c.refresh_iot_token_sync()
                except p.APIError as exc:
                    self.assertNotIn('SECRET', str(exc))
            self.assertNotIn('SECRET', output.getvalue())


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def executor(fn, *args):
            await asyncio.sleep(0)
            return fn(*args)
        self.entry = Mock(data={'device_id': 'fake', 'email': 'private@example.test'}, options={}, version=2)
        def update(entry, **kwargs):
            for key, value in kwargs.items():
                setattr(entry, key, value)
        self.hass = SimpleNamespace(async_add_executor_job=executor,
            async_create_task=asyncio.create_task,
            config_entries=SimpleNamespace(async_update_entry=Mock(side_effect=update)))
        self.send = Mock(return_value={'code': 200, 'data': response()})
        self.client = AigoClient(self.send)
        self.client.accept_session(response(iotToken='OLD_IOT', refreshToken='OLD_REFRESH'))
        self.entry.data.update(self.client.session)
        self.manager = SessionManager(self.hass, self.entry, self.client)
        self.timer = patch('custom_components.aigosmart.session.async_track_point_in_utc_time', return_value=Mock())
        self.track = self.timer.start()
        self.addCleanup(self.timer.stop)

    async def asyncTearDown(self):
        await self.manager.close()

    def expire(self):
        self.client.session['iot_token_expires_at'] = time.time() - 1

    async def test_expired_iot_refreshes_and_persists_rotation(self):
        self.expire()
        await self.manager.ensure()
        self.assertEqual(self.entry.data['iot_token'], 'NEW_IOT_SECRET')
        self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')
        self.assertEqual(self.entry.data['identity_id'], 'IDENTITY_SECRET')
        self.assertGreater(self.entry.data['last_refresh'], 0)
        self.assertEqual(self.entry.data['device_id'], 'fake')
        self.assertEqual(self.entry.data['iot_token_expires_at'], self.client.session['iot_token_expires_at'])
        self.assertEqual(self.send.call_count, 1)

    async def test_restart_retains_deadlines_without_extending_ttl(self):
        restored = AigoClient(self.send)
        restored.restore_session(self.entry.data)
        manager = SessionManager(self.hass, self.entry, restored)
        self.assertEqual(restored.session, self.client.session)
        await manager.ensure()
        self.send.assert_not_called()
        restored.session['iot_token_expires_at'] = time.time() - 1
        await manager.ensure()
        self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')
        await manager.close()

    async def test_short_and_long_ttl_schedule(self):
        for ttl in (100, 3600, 43200):
            self.client.accept_session(response(iotTokenExpire=ttl))
            self.manager.schedule()
            due = self.track.call_args.args[2].timestamp()
            self.assertAlmostEqual(due, self.client.session['iot_token_expires_at'] - min(600, ttl * .1), places=5)
        self.assertLess(self.manager.refresh_at, self.client.session['iot_token_expires_at'])

    async def test_proactive_refresh_before_expiry(self):
        self.client.session['iot_token_expires_at'] = time.time() + 100
        await self.manager.ensure()
        self.send.assert_called_once()

    async def test_network_loss_bounded_backoff_and_recovery(self):
        self.expire()
        old = dict(self.entry.data)
        self.send.side_effect = p.APIError('Network unavailable')
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()) as sleep:
            with self.assertRaises(p.APIError):
                await self.manager.ensure()
            self.assertEqual([c.args[0] for c in sleep.await_args_list if c.args[0]], [1, 3])
        self.assertEqual(self.send.call_count, 3)
        self.assertEqual(self.entry.data, old)
        self.assertEqual(self.manager.status, 'refresh_unavailable')
        with self.assertRaises(p.APIError):
            await self.manager.ensure()
        self.assertEqual(self.send.call_count, 3)
        self.entry.async_start_reauth.assert_not_called()
        self.manager._retry_at = 0
        self.send.side_effect = None
        await self.manager.ensure()
        self.assertEqual(self.manager.status, 'authorized')

    async def test_server_503_then_success(self):
        self.expire()
        self.send.side_effect = [p.APIError('Unavailable', status=503), {'code': 200, 'data': response()}]
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            await self.manager.ensure()
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(self.manager.status, 'authorized')

    async def test_business_503_retries(self):
        self.expire()
        self.send.side_effect = [{'code': 503}, {'code': 200, 'data': response()}]
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            await self.manager.ensure()
        self.assertEqual(self.send.call_count, 2)

    async def test_expired_refresh_needs_reauth_without_network(self):
        self.client.session['refresh_token_expires_at'] = time.time() - 1
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.manager.ensure()
        self.send.assert_not_called()
        self.assertEqual(self.manager.status, 'reauth_required')

    async def test_refresh_rejected_no_retry(self):
        for reply in ({'code': 100003}, {'code': 401}, {'code': 403}):
            self.manager.status = 'authorized'
            self.expire()
            self.send.reset_mock()
            self.send.return_value = reply
            with self.assertRaises(ConfigEntryAuthFailed):
                await self.manager.ensure()
            self.send.assert_called_once()
            self.assertEqual(self.manager.status, 'reauth_required')

    async def test_timer_starts_standard_reauth(self):
        self.expire()
        self.send.return_value = {'code': 100003}
        await self.manager._timer(datetime.now(timezone.utc))
        self.entry.async_start_reauth.assert_called_once_with(self.hass)

    async def test_concurrent_entities_issue_one_refresh(self):
        self.expire()
        await asyncio.gather(*(self.manager.ensure() for _ in range(30)))
        self.send.assert_called_once()
        self.hass.config_entries.async_update_entry.assert_called_once()

    async def test_concurrent_rejected_reads_issue_one_refresh(self):
        old = self.client.token
        await asyncio.gather(*(self.manager.ensure(rejected_token=old) for _ in range(30)))
        self.send.assert_called_once()
        await self.manager.ensure(rejected_token=old)
        self.send.assert_called_once()

    async def test_cancelled_waiter_still_persists_rotating_token(self):
        started, finish = asyncio.Event(), asyncio.Event()
        original = self.hass.async_add_executor_job
        async def executor(fn, *args):
            started.set()
            await finish.wait()
            return await original(fn, *args)
        self.hass.async_add_executor_job = executor
        self.expire()
        waiter = asyncio.create_task(self.manager.ensure())
        await started.wait()
        task = self.manager._task
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        finish.set()
        await task
        self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')
        self.send.assert_called_once()

    async def test_read_rejected_token_refreshes_and_retries_read(self):
        read = Mock(side_effect=[p.APIError('Expired', code='100001'), {'ok': True}])
        self.assertEqual(await self.manager.read(read), {'ok': True})
        self.assertEqual(read.call_count, 2)
        self.send.assert_called_once()

    async def test_read_network_retry_bound(self):
        read = Mock(side_effect=p.APIError('No network'))
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(p.APIError):
                await self.manager.read(read)
        self.assertEqual(read.call_count, 3)
        self.send.assert_not_called()

    async def test_legacy_entry_requires_one_time_reauth(self):
        from custom_components.aigosmart import async_migrate_entry
        self.entry.version = 1
        self.entry.data = {'device_id': 'fake', 'iot_token': 'LEGACY'}
        self.assertTrue(await async_migrate_entry(self.hass, self.entry))
        self.assertEqual(self.entry.version, 2)
        self.client.restore_session(self.entry.data)
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.manager.ensure()
        self.send.assert_not_called()
        self.assertEqual(self.entry.data['device_id'], 'fake')

    async def test_diagnostics_and_disabled_entities_contain_no_secrets(self):
        from custom_components.aigosmart.diagnostics import async_get_config_entry_diagnostics
        from custom_components.aigosmart.sensor import AigoSessionSensor
        coordinator = Mock(client=self.client, session=self.manager, device={'iotId': 'PRIVATE_ID'})
        self.entry.runtime_data = coordinator
        data = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(set(data), {'authorization_status', 'session_time_remaining', 'last_successful_refresh'})
        self.assertNotIn('SECRET', json.dumps(data))
        for key in data:
            sensor = AigoSessionSensor(coordinator, key)
            self.assertFalse(sensor.entity_registry_enabled_default)
            self.assertEqual(sensor.entity_category.value, 'diagnostic')
            self.assertIsNone(sensor.extra_state_attributes)
            self.assertNotIn('SECRET', str(sensor.native_value))

    async def test_token_persistence_does_not_reload_entry(self):
        from custom_components.aigosmart import _reload
        self.entry.runtime_data = Mock(_entry_options={})
        self.hass.config_entries.async_reload = AsyncMock()
        await _reload(self.hass, self.entry)
        self.hass.config_entries.async_reload.assert_not_called()
        self.entry.options = {'scan_interval': 30}
        await _reload(self.hass, self.entry)
        self.hass.config_entries.async_reload.assert_awaited_once()


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from homeassistant.core import HomeAssistant
        from homeassistant.config_entries import ConfigEntryState
        self.hass = HomeAssistant('/tmp/aigosmart-refresh-offline-ha')
        async def executor(fn, *args):
            await asyncio.sleep(0)
            return fn(*args)
        self.hass.async_add_executor_job = executor
        self.hass.config_entries = Mock()
        self.hass.config_entries.async_forward_entry_setups = AsyncMock()
        self.hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        self.entry = Mock(data={'device_id': 'fake'}, options={}, entry_id='fake',
            state=ConfigEntryState.SETUP_IN_PROGRESS)
        def update(entry, **kwargs):
            for key, value in kwargs.items():
                setattr(entry, key, value)
        self.hass.config_entries.async_update_entry.side_effect = update
        self.send = Mock(return_value={'code': 200, 'data': response()})
        self.client = AigoClient(self.send)
        self.client.accept_session(response())
        self.entry.data.update(self.client.session)
        self.client.model = Mock(return_value=json.loads(Path('tests/fixtures/kettle_capabilities.json').read_text()))
        self.client.devices = Mock(return_value=[{'iotId': 'fake', 'status': 1}])
        self.client.properties = Mock(return_value={'HeatingSwitch': {'value': 0}})
        self.client.write = Mock()
        self.coordinator = None

    async def asyncTearDown(self):
        if self.coordinator:
            await self.coordinator.session.close()
            await self.coordinator.async_shutdown()
        await self.hass.async_stop(force=True)

    async def setup(self):
        from custom_components.aigosmart import async_setup_entry
        with patch('custom_components.aigosmart.api.AigoClient', return_value=self.client):
            result = await async_setup_entry(self.hass, self.entry)
        self.coordinator = self.entry.runtime_data
        return result

    async def test_restart_expired_token_refreshes_before_model_read(self):
        self.entry.data['iot_token_expires_at'] = time.time() - 1
        self.assertTrue(await self.setup())
        self.send.assert_called_once()
        self.client.model.assert_called_once()
        self.client.write.assert_not_called()
        self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')
        self.assertIsNotNone(self.coordinator.session._cancel_timer)

    async def test_offline_startup_requests_retry_instead_of_reauth(self):
        self.entry.data['iot_token_expires_at'] = time.time() - 1
        self.send.side_effect = p.APIError('No network')
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(ConfigEntryNotReady):
                await self.setup()
        self.assertEqual(self.send.call_count, 3)
        self.entry.async_start_reauth.assert_not_called()
        self.client.write.assert_not_called()

    async def test_legacy_setup_requests_standard_reauth(self):
        self.entry.data = {'iot_token': 'OLD_ONLY', 'device_id': 'fake'}
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.setup()
        self.send.assert_not_called()
        self.client.model.assert_not_called()

    async def test_write_auth_rejection_refreshes_only_reads(self):
        await self.setup()
        self.client.write.side_effect = p.APIError('Expired', status=401)
        self.client.properties.side_effect = [p.APIError('Expired', status=401),
            {'HeatingSwitch': {'value': 0}}]
        with patch('custom_components.aigosmart.coordinator.asyncio.sleep', new=AsyncMock()):
            result = await self.coordinator.async_write('HeatingSwitch', 1)
        self.assertEqual(result, 'outcome_unknown')
        self.client.write.assert_called_once()
        self.send.assert_called_once()
        self.assertTrue(self.send.call_args.args[1].endswith(p.REFRESH))
        self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')

    async def test_refresh_outage_blocks_command_before_send(self):
        await self.setup()
        self.client.session['iot_token_expires_at'] = time.time() - 1
        self.send.side_effect = p.APIError('Server unavailable', status=503)
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(HomeAssistantError):
                await self.coordinator.async_write('HeatingSwitch', 1)
        self.client.write.assert_not_called()
        self.assertEqual(self.send.call_count, 3)
        self.entry.async_start_reauth.assert_not_called()

    async def test_refresh_rejection_during_command_starts_reauth(self):
        await self.setup()
        self.client.session['iot_token_expires_at'] = time.time() - 1
        self.send.return_value = {'code': 100003}
        with self.assertRaises(HomeAssistantError):
            await self.coordinator.async_write('HeatingSwitch', 1)
        self.entry.async_start_reauth.assert_called_once_with(self.hass)
        self.client.write.assert_not_called()

    async def test_unload_cancels_timer_and_clears_memory(self):
        from custom_components.aigosmart import async_unload_entry
        await self.setup()
        self.assertTrue(await async_unload_entry(self.hass, self.entry))
        self.assertTrue(self.coordinator.session._closed)
        self.assertIsNone(self.coordinator.session._cancel_timer)
        self.assertIsNone(self.client.token)
        self.assertEqual(self.client.session, {})
