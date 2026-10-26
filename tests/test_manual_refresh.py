"""Offline manual session action regressions; never contact a provider."""
import asyncio
import hashlib
import json
import unittest
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from custom_components.aigosmart.button import AigoRefreshTokenButton, async_setup_entry
from custom_components.aigosmart.const import PLATFORMS
from custom_components.aigosmart.diagnostics import async_get_config_entry_diagnostics
from custom_components.aigosmart.protocol import APIError, REFRESH
from custom_components.aigosmart.recovery import RecoveryError
import test_diagnostics_beta as diagnostic_fixtures
import test_session_refresh as fixtures
import test_reconnect_flow as registry_fixtures

setUpModule = fixtures.setUpModule


class ManualRefreshTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SessionTests.asyncSetUp
    asyncTearDown = fixtures.SessionTests.asyncTearDown

    async def test_timer_trigger(self):
        self.client.session['iot_token_expires_at'] = time.time() - 1
        await self.manager._timer(None)
        self.assertEqual(self.client.refresh_diagnostics['trigger'], 'timer')

    async def test_force_valid_rotation_and_rate_limit(self):
        await self.manager.ensure()
        self.send.assert_not_called()
        old_end = self.client.session['iot_token_expires_at']
        await self.manager.manual_force_refresh()
        self.send.assert_called_once()
        self.assertEqual(self.client.refresh_diagnostics['trigger'], 'manual')
        self.assertEqual(self.entry.data['iot_token'], 'NEW_IOT_SECRET')
        self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')
        self.assertEqual(self.entry.data, {**self.entry.data, **self.client.session})
        self.assertNotEqual(old_end, self.entry.data['iot_token_expires_at'])
        self.assertGreater(self.entry.data['last_refresh'], 0)
        with self.assertRaises(RecoveryError):
            await self.manager.manual_force_refresh()
        self.send.assert_called_once()

    async def test_concurrent_manual_timer_and_cancelled_waiter(self):
        started, finish = asyncio.Event(), asyncio.Event()
        executor = self.hass.async_add_executor_job
        async def blocked(fn, *args):
            started.set()
            await finish.wait()
            return await executor(fn, *args)
        self.hass.async_add_executor_job = blocked
        first = asyncio.create_task(self.manager.manual_force_refresh())
        await started.wait()
        others = [asyncio.create_task(self.manager.manual_force_refresh()) for _ in range(10)]
        timer = asyncio.create_task(self.manager._timer(None))
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        finish.set()
        await asyncio.gather(*others, timer)
        self.send.assert_called_once()
        self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')

    async def test_login_guard_blocks_manual_and_waits_for_rotation(self):
        async with self.manager.login_guard():
            with self.assertRaises(RecoveryError):
                await self.manager.manual_force_refresh()
            self.send.assert_not_called()
        started, finish, entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
        executor = self.hass.async_add_executor_job
        async def blocked(fn, *args):
            started.set()
            await finish.wait()
            return await executor(fn, *args)
        self.hass.async_add_executor_job = blocked
        task = asyncio.create_task(self.manager.manual_force_refresh())
        await started.wait()
        async def login():
            async with self.manager.login_guard():
                self.assertEqual(self.entry.data['refresh_token'], 'NEW_REFRESH_SECRET')
                entered.set()
        login_task = asyncio.create_task(login())
        await asyncio.sleep(0)
        self.assertFalse(entered.is_set())
        finish.set()
        await asyncio.gather(task, login_task)
        self.assertTrue(entered.is_set())

    async def test_failure_strict_but_background_retains_valid_credentials(self):
        for exc in (TimeoutError('PRIVATE'), OSError('PRIVATE'), APIError('PRIVATE', validation='missing_ttl')):
            with self.subTest(kind=type(exc).__name__):
                self.manager._retry_at = self.manager._manual_retry_at = 0
                before = dict(self.client.session)
                stored = dict(self.entry.data)
                self.send.side_effect = exc
                with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
                    with self.assertRaises(RecoveryError):
                        await self.manager.manual_force_refresh()
                self.assertEqual(self.client.session, before)
                self.assertEqual(self.entry.data, stored)
                count = self.send.call_count
                self.manager._manual_retry_at = 0
                with self.assertRaises(RecoveryError):
                    await self.manager.manual_force_refresh()
                await self.manager.ensure()
                self.assertEqual(self.send.call_count, count)
                self.assertGreater(self.manager.diagnostics.failed_refresh_count, 0)

    async def test_auth_rejected_and_closed_refuse_requests(self):
        for status in (401, 403):
            self.manager.status = 'authorized'
            self.manager._manual_retry_at = 0
            self.send.side_effect = APIError('PRIVATE', status=status)
            with self.assertRaises(ConfigEntryAuthFailed):
                await self.manager.manual_force_refresh()
            count = self.send.call_count
            with self.assertRaises(ConfigEntryAuthFailed):
                await self.manager.manual_force_refresh()
            self.assertEqual(self.send.call_count, count)
        await self.manager.close()
        with self.assertRaises(APIError):
            await self.manager.manual_force_refresh()
        self.assertEqual(self.send.call_count, count)

    async def test_manual_join_surfaces_background_failure(self):
        self.client.session['iot_token_expires_at'] = time.time() + 100
        started, finish = asyncio.Event(), asyncio.Event()
        executor = self.hass.async_add_executor_job
        async def blocked(fn, *args):
            started.set()
            await finish.wait()
            return await executor(fn, *args)
        self.hass.async_add_executor_job = blocked
        self.send.side_effect = APIError('PRIVATE', validation='missing_ttl')
        background = asyncio.create_task(self.manager.ensure())
        await started.wait()
        manual = asyncio.create_task(self.manager.manual_force_refresh())
        await asyncio.sleep(0)
        finish.set()
        await background
        with self.assertRaises(RecoveryError):
            await manual
        self.send.assert_called_once()

    async def test_expired_refresh_credentials_refused(self):
        self.client.session['refresh_token_expires_at'] = 1
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.manager.manual_force_refresh()
        self.send.assert_not_called()


class ButtonTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SessionTests.asyncSetUp
    asyncTearDown = fixtures.SessionTests.asyncTearDown
    coordinator = diagnostic_fixtures.DiagnosticTests.coordinator
    download = diagnostic_fixtures.DiagnosticTests.download

    def button(self):
        coordinator = self.coordinator()
        coordinator.entry = self.entry
        button = AigoRefreshTokenButton(coordinator)
        button.hass = self.hass
        return button

    async def test_button_identity_availability_translations_and_setup(self):
        button = self.button()
        add = Mock()
        self.entry.runtime_data = button.coordinator
        await async_setup_entry(self.hass, self.entry, add)
        self.assertEqual(add.call_args.args[0][0].unique_id, button.unique_id)
        self.assertIn('button', PLATFORMS)
        self.assertEqual(button.unique_id, hashlib.sha256(b'PRIVATE_DEVICE_ID').hexdigest() + '_AigoRefreshTokenButton_refresh_iot_token')
        self.assertEqual(button.device_info['identifiers'], {('aigosmart', hashlib.sha256(b'PRIVATE_DEVICE_ID').hexdigest())})
        self.assertEqual(button.entity_category.value, 'diagnostic')
        self.assertEqual(button.translation_key, 'refresh_iot_token')
        self.assertIsNone(button.extra_state_attributes)
        self.assertTrue(button.available)
        self.manager._login_active = True
        self.assertFalse(button.available)
        self.manager._login_active = False
        self.manager.status = 'reauth_required'
        self.assertFalse(button.available)
        self.manager.status = 'authorized'
        await self.manager.close()
        self.assertFalse(button.available)
        for lang in ('en', 'de', 'pl'):
            data = json.loads(Path(f'custom_components/aigosmart/translations/{lang}.json').read_text())
            self.assertTrue(data['entity']['button']['refresh_iot_token']['name'])

    async def test_button_failures_never_report_success_or_export_secrets(self):
        button = self.button()
        self.send.side_effect = TimeoutError('PRIVATE_SECRET')
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            with self.assertRaisesRegex(HomeAssistantError, 'timed out'):
                await button.async_press()
        with self.assertRaisesRegex(HomeAssistantError, 'cooling down'):
            await button.async_press()
        self.assertNotIn('SECRET', json.dumps(await self.download()))
        self.assertNotIn('refresh_iot_token', json.dumps(await self.download()))
        self.manager._manual_retry_at = self.manager._retry_at = 0
        self.send.side_effect = APIError('PRIVATE', status=403)
        with self.assertRaisesRegex(HomeAssistantError, 'reauthentication'):
            await button.async_press()
        self.entry.async_start_reauth.assert_called_once_with(self.hass)

    async def test_button_success_uses_only_refresh(self):
        await self.button().async_press()
        self.send.assert_called_once()
        self.assertTrue(self.send.call_args.args[1].endswith(REFRESH))
        data = await self.download()
        self.assertEqual(data['refresh']['last_result'], 'success')
        self.assertIsNotNone(data['last_successful_refresh'])
        self.assertNotIn('SECRET', json.dumps(data))


class ButtonRegistryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = registry_fixtures.ReconnectFlowTests.asyncSetUp
    asyncTearDown = registry_fixtures.ReconnectFlowTests.asyncTearDown

    async def test_registry_identity_and_user_choices_survive(self):
        from unittest.mock import Mock
        coordinator = Mock(device={'iotId': 'fake'})
        button = AigoRefreshTokenButton(coordinator)
        old = self.entities.async_get_or_create('button', 'aigosmart', button.unique_id,
            config_entry=self.entry, device_id=self.device.id)
        self.entities.async_update_entity(old.entity_id, name='My refresh', area_id=self.area.id)
        new = self.entities.async_get_or_create('button', 'aigosmart',
            AigoRefreshTokenButton(coordinator).unique_id,
            config_entry=self.entry, device_id=self.device.id)
        self.assertEqual(old.id, new.id)
        self.assertEqual(new.name, 'My refresh')
        self.assertEqual(new.area_id, self.area.id)
