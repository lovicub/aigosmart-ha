"""Mocked business rejection evidence, classification and cooldown regression."""
import json
import asyncio
import time
import unittest
from unittest.mock import Mock
from custom_components.aigosmart import protocol as p
from custom_components.aigosmart.recovery import RecoveryError, classify_failure
import test_session_refresh as fixtures
from test_session_refresh import response, setUpModule


class RejectionTests(unittest.TestCase):
    def test_root_code_types_and_redaction(self):
        for value, validation in ((987654321, 'application_rejection'),
                                  ('PRIVATE_SECRET', 'application_rejection'),
                                  ('200', 'refresh_code_string_success'),
                                  (None, 'refresh_code_type'),
                                  (True, 'refresh_code_type'),
                                  (200.0, 'refresh_code_type'),
                                  ({'SECRET': 'SECRET'}, 'refresh_code_type')):
            with self.subTest(kind=type(value).__name__):
                c = p.Client(Mock(return_value=p.APIResponse(
                    {'code': value, 'message': 'MESSAGE_SECRET'}, 200)))
                c.accept_session(response())
                old = dict(c.session)
                with self.assertRaises(p.APIError) as caught:
                    c.refresh_iot_token_sync()
                d = c.refresh_diagnostics
                self.assertEqual(d['validation'], validation)
                self.assertEqual(d['http_category'], '2xx')
                self.assertEqual(d['message_state'], 'present')
                self.assertEqual(d['data_state'], 'absent')
                self.assertEqual(d['error_category'], 'application_rejection' if validation == 'application_rejection' else 'response_validation')
                self.assertEqual(c.session, old)
                self.assertNotIn('SECRET', json.dumps(d))
                self.assertNotIn('987654321', json.dumps(d))
                self.assertEqual(classify_failure('token_refresh', caught.exception)[1],
                                 'application_rejection' if validation == 'application_rejection' else 'response_validation')

    def test_allowlist_and_missing(self):
        for payload, category, vendor in (({}, 'response_validation', 'UNKNOWN'),
                ({'code': 403}, 'auth_rejection', '403'),
                ({'code': 503}, 'application_rejection', '503'),
                ({'code': 200, 'data': None}, 'malformed_success', '200')):
            c = p.Client(Mock(return_value=p.APIResponse(payload, 200)))
            c.accept_session(response())
            with self.assertRaises(p.APIError): c.refresh_iot_token_sync()
            self.assertEqual(c.refresh_diagnostics['error_category'], category)
            self.assertEqual(c.refresh_diagnostics['vendor_code'], vendor)
            self.assertEqual(c.refresh_diagnostics['message_state'], 'absent')


class RejectionManagerTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SessionTests.asyncSetUp
    asyncTearDown = fixtures.SessionTests.asyncTearDown

    async def test_concurrent_timer_manual_rejection_is_one_attempt(self):
        started, finish = asyncio.Event(), asyncio.Event()
        executor = self.hass.async_add_executor_job
        async def blocked(fn, *args):
            started.set()
            await finish.wait()
            return await executor(fn, *args)
        self.hass.async_add_executor_job = blocked
        self.send.return_value = p.APIResponse({'code': 987654321, 'message': 'SECRET'}, 200)
        self.client.session['iot_token_expires_at'] = time.time() - 1
        timer = asyncio.create_task(self.manager._timer(None))
        await started.wait()
        manual = [asyncio.create_task(self.manager.manual_force_refresh()) for _ in range(8)]
        await asyncio.sleep(0)
        finish.set()
        results = await asyncio.gather(timer, *manual, return_exceptions=True)
        self.assertIsNone(results[0])
        self.assertTrue(all(isinstance(result, RecoveryError) for result in results[1:]))
        self.send.assert_called_once()
        self.assertEqual(self.manager.diagnostics.failed_refresh_count, 1)
        self.assertEqual(self.client.refresh_diagnostics['trigger'], 'timer')
        self.assertEqual(self.client.refresh_diagnostics['error_category'], 'application_rejection')

    async def test_rejection_survives_cooldown_without_persistence_or_retries(self):
        from custom_components.aigosmart.diagnostics import async_get_config_entry_diagnostics
        self.send.return_value = p.APIResponse({'code': 987654321, 'message': 'MESSAGE_SECRET'}, 200)
        old = dict(self.entry.data)
        with self.assertRaises(RecoveryError) as caught:
            await self.manager.manual_force_refresh()
        self.assertEqual(caught.exception.reason, 'application_rejection')
        self.assertEqual(self.entry.data, old)
        self.assertTrue(self.manager._token_valid())
        self.assertGreater(self.manager._retry_at, time.time())
        self.assertEqual(self.manager.diagnostics.last_failed_api_operation['reason'], 'application_rejection')
        self.manager._manual_retry_at = 0
        with self.assertRaises(RecoveryError) as caught:
            await self.manager.manual_force_refresh()
        self.assertEqual(caught.exception.reason, 'application_rejection')
        self.send.assert_called_once()
        self.entry.runtime_data = Mock(session=self.manager)
        exported = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(exported['refresh']['response']['error_category'], 'application_rejection')
        self.assertNotIn('SECRET', json.dumps(exported))
