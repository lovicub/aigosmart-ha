"""Passive beta diagnostics: privacy, event accounting, compatibility, no IO."""
import asyncio
from datetime import timezone
import hashlib
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.exceptions import ConfigEntryAuthFailed
from custom_components.aigosmart.diagnostic_state import (
    SENSOR_NAMES, TIMESTAMP_KEYS, diagnostic_values,
)
from custom_components.aigosmart.diagnostics import async_get_config_entry_diagnostics
from custom_components.aigosmart.protocol import APIError
from custom_components.aigosmart.sensor import AigoSessionSensor
from custom_components.aigosmart.session import SessionManager
import test_session_refresh as fixtures
import test_reconnect_flow as flow_fixtures

setUpModule = fixtures.setUpModule


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SessionTests.asyncSetUp
    asyncTearDown = fixtures.SessionTests.asyncTearDown
    expire = fixtures.SessionTests.expire

    def coordinator(self):
        return Mock(client=self.client, session=self.manager, device={'iotId': 'PRIVATE_DEVICE_ID'})

    async def download(self):
        self.entry.runtime_data = self.coordinator()
        return await async_get_config_entry_diagnostics(self.hass, self.entry)

    async def test_cloud_and_device_read_timestamps_use_existing_requests(self):
        read = Mock(return_value={'PRIVATE_PAYLOAD': 'PRIVATE_SECRET'})
        with patch('custom_components.aigosmart.diagnostic_state.time.time', return_value=1000):
            await self.manager.read(read, stage='model_tsl_fetch')
        values = diagnostic_values(self.manager)
        self.assertEqual(values['last_successful_cloud_read'], 1000)
        self.assertIsNone(values['last_successful_device_read'])
        with patch('custom_components.aigosmart.diagnostic_state.time.time', return_value=2000):
            await self.manager.read(read, stage='property_read')
        self.assertEqual(self.manager.diagnostics.last_successful_device_read, 2000)
        self.assertEqual(diagnostic_values(self.manager)['connection_status'], 'connected')
        self.assertEqual(read.call_count, 2)
        self.send.assert_not_called()
        self.assertNotIn('PRIVATE', json.dumps(await self.download()))

    async def test_recovered_transient_failure_keeps_sanitized_history(self):
        read = Mock(side_effect=[TimeoutError('PRIVATE_EMAIL_TOKEN_RESPONSE'), {'ok': True}])
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            await self.manager.read(read, stage='property_read')
        data = await self.download()
        self.assertEqual(data['last_failed_api_operation']['stage'], 'property_read')
        self.assertEqual(data['last_failed_api_operation']['reason'], 'cloud_timeout')
        self.assertEqual(data['connection_status'], 'connected')
        self.assertIsNotNone(data['reads']['last_successful_device_read'])
        self.assertNotIn('PRIVATE', json.dumps(data))

    async def test_failed_refresh_attempts_count_backoff_not_cooldown(self):
        self.expire()
        self.send.side_effect = APIError('PRIVATE_REFRESH_TOKEN', status=503)
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(APIError):
                await self.manager.ensure()
        data = await self.download()
        self.assertEqual(data['refresh']['failed_attempt_count'], 3)
        self.assertEqual(data['refresh']['last_result'], 'cloud_unavailable')
        self.assertIsNotNone(data['refresh']['last_attempt'])
        self.assertEqual(data['connection_status'], 'refresh_unavailable')
        with self.assertRaises(APIError):
            await self.manager.ensure()
        self.assertEqual(self.manager.diagnostics.failed_refresh_count, 3)
        self.assertEqual(self.send.call_count, 3)
        self.manager._retry_at = 0
        self.send.side_effect = None
        await self.manager.ensure()
        await self.manager.read(Mock(return_value={}))
        data = await self.download()
        self.assertEqual(data['refresh']['failed_attempt_count'], 3)
        self.assertEqual(data['refresh']['last_result'], 'success')
        self.assertEqual(data['connection_status'], 'connected')
        self.assertNotIn('PRIVATE', json.dumps(data))
        self.assertNotIn('SECRET', json.dumps(data))

    async def test_rejected_refresh_and_missing_credentials_are_distinct(self):
        self.expire()
        self.send.side_effect = APIError('PRIVATE', status=401)
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.manager.ensure()
        self.assertEqual(diagnostic_values(self.manager)['last_refresh_result'], 'confirmed_invalid_credentials')
        self.assertEqual(diagnostic_values(self.manager)['connection_status'], 'reauth_required')
        self.assertEqual(self.manager.diagnostics.failed_refresh_count, 1)
        await self.manager.close()
        self.client.session['refresh_token_expires_at'] = 1
        self.manager = SessionManager(self.hass, self.entry, self.client)
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.manager.ensure()
        self.assertEqual(self.manager.diagnostics.failed_refresh_count, 0)
        self.assertIsNone(self.manager.diagnostics.last_refresh_attempt)

    async def test_concurrent_refresh_and_diagnostic_reads_do_not_add_io(self):
        self.expire()
        await asyncio.gather(*(self.manager.ensure() for _ in range(30)))
        before = self.send.call_count
        coordinator = self.coordinator()
        for _ in range(10):
            await self.download()
            for key in SENSOR_NAMES:
                sensor = AigoSessionSensor(coordinator, key)
                _ = sensor.native_value
                self.assertFalse(sensor.should_poll)
        self.assertEqual(before, 1)
        self.assertEqual(self.send.call_count, before)
        self.assertEqual(self.manager.diagnostics.failed_refresh_count, 0)
        self.assertEqual(self.manager.diagnostics.last_refresh_result, 'success')

    async def test_inflight_refresh_is_visible_without_another_request(self):
        self.expire()
        started, finish = asyncio.Event(), asyncio.Event()
        executor = self.hass.async_add_executor_job
        async def blocked(fn, *args):
            started.set()
            await finish.wait()
            return await executor(fn, *args)
        self.hass.async_add_executor_job = blocked
        task = asyncio.create_task(self.manager.ensure())
        await started.wait()
        try:
            data = await self.download()
            self.assertEqual(data['refresh']['last_result'], 'in_progress')
            self.assertEqual(data['connection_status'], 'refreshing')
            self.assertIsNotNone(data['refresh']['last_attempt'])
            self.send.assert_not_called()
        finally:
            finish.set()
            await task
        self.send.assert_called_once()
        self.assertEqual(diagnostic_values(self.manager)['last_refresh_result'], 'success')

    async def test_existing_ids_and_all_diagnostic_sensor_metadata(self):
        coordinator = self.coordinator()
        digest = hashlib.sha256(b'PRIVATE_DEVICE_ID').hexdigest()
        for key in SENSOR_NAMES:
            sensor = AigoSessionSensor(coordinator, key)
            self.assertEqual(sensor.unique_id, f'{digest}_AigoSessionSensor_{key}')
            self.assertEqual(sensor.entity_category.value, 'diagnostic')
            self.assertFalse(sensor.entity_registry_enabled_default)
            self.assertIsNone(sensor.extra_state_attributes)
            self.assertTrue(sensor.available)
            self.assertEqual(sensor.device_class, SensorDeviceClass.TIMESTAMP if key in TIMESTAMP_KEYS else None)
        for key in ('session_time_remaining', 'last_successful_refresh', 'authorization_status'):
            self.assertIn(key, SENSOR_NAMES)
        self.client.session['last_refresh'] = 1000
        sensor = AigoSessionSensor(coordinator, 'last_successful_refresh')
        self.assertEqual(sensor.native_value.timestamp(), 1000)
        self.assertEqual(sensor.native_value.tzinfo, timezone.utc)
        self.assertEqual(AigoSessionSensor(coordinator, 'session_time_remaining').native_unit_of_measurement, 's')

    async def test_expiration_fields_are_validated_and_never_expose_stored_strings(self):
        coordinator = self.coordinator()
        for value in ('PRIVATE_SECRET', True, float('nan'), float('inf'), -1, 10**1000, None):
            for key in ('iot_token_expires_at', 'refresh_token_expires_at', 'last_refresh'):
                self.client.session[key] = value
                sensor_key = 'last_successful_refresh' if key == 'last_refresh' else key
                self.assertIsNone(diagnostic_values(self.manager)[sensor_key])
                self.assertIsNone(AigoSessionSensor(coordinator, sensor_key).native_value)
            data = await self.download()
            self.assertIsNone(data['session_time_remaining'])
            self.assertNotIn('PRIVATE', json.dumps(data, allow_nan=False))
        self.client.session['iot_token_expires_at'] = 2000000000
        data = await self.download()
        self.assertEqual(data['token_expiration']['iot_token'], '2033-05-18T03:33:20+00:00')

    async def test_no_runtime_download_uses_only_safe_persisted_fields(self):
        self.entry.runtime_data = None
        self.entry.data.update({'iot_token': 'PRIVATE', 'email': 'PRIVATE_EMAIL', 'last_refresh': 1000})
        data = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(data['authorization_status'], 'unknown')
        self.assertEqual(data['connection_status'], 'unknown')
        self.assertEqual(data['last_successful_refresh'], 1000)
        self.assertEqual(data['refresh']['failed_attempt_count'], 0)
        self.assertNotIn('PRIVATE', json.dumps(data))
        self.send.assert_not_called()

    async def test_unknown_failure_metadata_is_allowlisted(self):
        exc = RuntimeError('PRIVATE_PAYLOAD'); exc.headers = {'Authorization': 'PRIVATE'}
        self.manager.diagnostics.operation_failed('PRIVATE_DEVICE_ID', exc)
        self.manager.status = 'PRIVATE_EMAIL'
        data = await self.download()
        self.assertEqual(data['last_failed_api_operation']['stage'], 'property_read')
        self.assertEqual(data['last_failed_api_operation']['reason'], 'response_validation')
        self.assertEqual(data['authorization_status'], 'unknown')
        self.assertNotIn('PRIVATE', json.dumps(data))

    async def test_reload_resets_new_counters_but_keeps_persisted_refresh_time(self):
        self.manager.diagnostics.refresh_started()
        self.manager.diagnostics.refresh_failed(APIError('PRIVATE', status=503))
        self.client.session['last_refresh'] = 1000
        new = SessionManager(self.hass, self.entry, self.client)
        self.assertEqual(diagnostic_values(new)['failed_refresh_count'], 0)
        self.assertIsNone(diagnostic_values(new)['last_refresh_attempt'])
        self.assertEqual(diagnostic_values(new)['last_successful_refresh'], 1000)
        await new.close()


class CoordinatorDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.LifecycleTests.asyncSetUp
    asyncTearDown = fixtures.LifecycleTests.asyncTearDown
    setup = fixtures.LifecycleTests.setup

    async def test_offline_device_and_recovery_are_passively_observed(self):
        await self.setup()
        self.assertEqual(diagnostic_values(self.coordinator.session)['connection_status'], 'connected')
        last_device = self.coordinator.session.diagnostics.last_successful_device_read
        self.client.devices.return_value = []
        await self.coordinator.async_refresh()
        self.assertEqual(diagnostic_values(self.coordinator.session)['connection_status'], 'device_offline')
        self.assertEqual(self.coordinator.session.diagnostics.last_successful_device_read, last_device)
        self.client.devices.return_value = [{'iotId': 'fake', 'status': 1}]
        await self.coordinator.async_refresh()
        self.assertEqual(diagnostic_values(self.coordinator.session)['connection_status'], 'connected')
        self.client.write.assert_not_called()

    async def test_write_failure_is_sanitized_and_never_retried(self):
        await self.setup()
        self.client.write.side_effect = APIError('PRIVATE_WRITE_RESPONSE', status=503)
        with patch('custom_components.aigosmart.coordinator.asyncio.sleep', new=AsyncMock()):
            await self.coordinator.async_write('HeatingSwitch', 0)
        self.client.write.assert_called_once()
        data = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(data['last_failed_api_operation']['stage'], 'property_write')
        self.assertEqual(data['last_failed_api_operation']['reason'], 'cloud_unavailable')
        self.assertNotIn('PRIVATE', json.dumps(data))


class RegistryDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = flow_fixtures.ReconnectFlowTests.asyncSetUp
    asyncTearDown = flow_fixtures.ReconnectFlowTests.asyncTearDown

    async def test_existing_diagnostic_registry_ids_and_user_choices_survive(self):
        fixture = self
        old_keys = ('session_time_remaining', 'last_successful_refresh', 'authorization_status')
        for key in old_keys:
            old = fixture.entities.async_get_or_create('sensor', 'aigosmart',
                f'{fixture.entry.unique_id}_AigoSessionSensor_{key}',
                config_entry=fixture.entry, device_id=fixture.device.id,
                suggested_object_id=f'custom_{key}')
            fixture.entities.async_update_entity(old.entity_id, area_id=fixture.area.id, name='My diagnostic')
            coordinator = Mock(device={'iotId': 'fake'})
            sensor = AigoSessionSensor(coordinator, key)
            existing = fixture.entities.async_get_or_create('sensor', 'aigosmart', sensor.unique_id,
                config_entry=fixture.entry, device_id=fixture.device.id)
            self.assertEqual(existing.entity_id, old.entity_id)
            self.assertEqual(existing.id, old.id)
            self.assertEqual(existing.name, 'My diagnostic')
            self.assertEqual(existing.area_id, fixture.area.id)
        self.assertEqual(len(fixture.entities.entities), 4)
