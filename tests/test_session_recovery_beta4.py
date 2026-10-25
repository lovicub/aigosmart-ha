"""Offline regressions for recovery and the naturally occurring refresh probe."""
import asyncio
import io
import json
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import test_session_refresh as fixtures
from custom_components.aigosmart import protocol as p
from custom_components.aigosmart import recovery
from custom_components.aigosmart.diagnostics import async_get_config_entry_diagnostics
from custom_components.aigosmart.session import SessionManager
from homeassistant.exceptions import ConfigEntryAuthFailed

setUpModule = fixtures.setUpModule


class ShapeTests(unittest.TestCase):
    def test_shape_never_copies_unknown_keys_or_values(self):
        shape = p.session_shape({'code': 200, 'SECRET_EMAIL': 'SECRET', 'data': {
            'iotToken': 'SECRET_TOKEN', 'refreshTokenExpire': 'SECRET',
            'identityId': {'SECRET_ID': 'SECRET'}, 'SECRET': 'SECRET'}})
        self.assertNotIn('SECRET', json.dumps(shape))
        self.assertEqual(shape['fields']['iotToken'], 'string')
        self.assertEqual(shape['expiry_representation']['refreshTokenExpire'], 'invalid_numeric')
        self.assertEqual(shape['fields']['iotTokenExpire'], 'missing')

    def test_unsupported_envelopes_rejected_with_safe_shape(self):
        for data in (None, [], 'SECRET', {'data': fixtures.response()}):
            client = p.Client(Mock(return_value={'code': 200, 'data': data}))
            client.accept_session(fixtures.response())
            old = dict(client.session)
            with self.assertRaises(p.APIError):
                client.refresh_iot_token_sync()
            self.assertEqual(old, client.session)
            self.assertNotIn('SECRET', json.dumps(client.refresh_diagnostics))

    def test_missing_lifetime_never_invents_deadline(self):
        client = p.Client(Mock())
        client.accept_session(fixtures.response())
        old = dict(client.session)
        with self.assertRaises(p.APIError) as error:
            client.accept_session({'iotToken': 'NEXT'}, refresh=True)
        self.assertEqual(error.exception.validation, 'missing_iotTokenExpire')
        self.assertEqual(client.session, old)

    def test_missing_required_token_names_field(self):
        client = p.Client(Mock(return_value={'code': 200, 'data': {'iotTokenExpire': 100}}))
        client.accept_session(fixtures.response())
        with self.assertRaises(p.APIError):
            client.refresh_iot_token_sync()
        self.assertEqual(client.refresh_diagnostics['validation'], 'missing_iotToken')

    def test_unchanged_refresh_omissions_preserve_deadlines(self):
        client = p.Client(Mock())
        client.accept_session(fixtures.response())
        old = dict(client.session)
        client.accept_session({'iotToken': 'NEXT', 'iotTokenExpire': 100}, refresh=True)
        for key in ('refresh_token', 'identity_id', 'refresh_token_expires_at'):
            self.assertEqual(client.session[key], old[key])

    def test_rate_limit_summary_and_cooldown_does_not_log(self):
        with patch.dict(recovery._WARNINGS, {}, clear=True), patch.object(recovery.time, 'monotonic', return_value=100):
            with self.assertLogs(recovery._LOGGER, level='INFO') as output:
                for _ in range(100):
                    recovery.failure('token_refresh', p.APIError('SECRET', status=503))
                recovery.failure('token_refresh', recovery.RecoveryError('token_refresh', 'cloud_unavailable', cooldown=True))
                recovery.recovered('token_refresh')
            self.assertEqual(len(output.output), 2)
            self.assertIn('suppressed=99', output.output[-1])
            self.assertNotIn('SECRET', str(output.output))

    def test_warning_reappears_after_interval(self):
        with patch.dict(recovery._WARNINGS, {}, clear=True):
            with self.assertLogs(recovery._LOGGER, level='WARNING') as output:
                for now in (100, 101, 401):
                    with patch.object(recovery.time, 'monotonic', return_value=now):
                        recovery.failure('property_read', p.APIError('SECRET', status=503))
            self.assertEqual(len(output.output), 2)
            self.assertIn('suppressed=1', output.output[-1])


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SessionTests.asyncSetUp
    asyncTearDown = fixtures.SessionTests.asyncTearDown
    expire = fixtures.SessionTests.expire

    async def test_proactive_outage_keeps_valid_reads_and_original_deadline(self):
        self.client.session['iot_token_expires_at'] = time.time() + 100
        old = dict(self.client.session)
        self.send.side_effect = p.APIError('SECRET', status=503)
        read = Mock(return_value={'ok': True})
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            self.assertEqual(await self.manager.read(read), {'ok': True})
        self.assertEqual(old, self.client.session)
        self.assertEqual(await self.manager.read(read), {'ok': True})
        self.assertEqual(self.send.call_count, 3)
        self.assertEqual(read.call_count, 2)
        self.expire()
        with self.assertRaises(recovery.RecoveryError) as error:
            await self.manager.read(read)
        self.assertTrue(error.exception.cooldown)
        self.assertEqual(read.call_count, 2)

    async def test_concurrent_proactive_waiters_all_keep_valid_token(self):
        self.client.session['iot_token_expires_at'] = time.time() + 100
        self.send.side_effect = p.APIError('SECRET', status=503)
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            await asyncio.gather(*(self.manager.ensure() for _ in range(20)))
        self.assertEqual(self.send.call_count, 3)

    async def test_known_rejected_token_never_uses_proactive_fallback(self):
        self.send.side_effect = p.APIError('SECRET', status=503)
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(recovery.RecoveryError):
                await self.manager.ensure(rejected_token=self.client.token)

    async def test_cooldown_preserves_validation_category(self):
        self.expire()
        self.send.return_value = {'code': 200, 'data': {'iotToken': 'NEXT'}}
        with self.assertRaises(recovery.RecoveryError):
            await self.manager.ensure()
        self.send.assert_called_once()
        with self.assertRaises(recovery.RecoveryError) as error:
            await self.manager.ensure()
        self.assertEqual(error.exception.reason, 'response_validation')
        self.assertTrue(error.exception.cooldown)
        self.send.assert_called_once()

    async def test_read_outage_cooldown_recovers_without_refresh_or_writes(self):
        read = Mock(side_effect=p.APIError('SECRET', status=503))
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(recovery.RecoveryError):
                await self.manager.read(read)
        for _ in range(20):
            with self.assertRaises(recovery.RecoveryError):
                await self.manager.read(read)
        self.assertEqual(read.call_count, 3)
        self.manager._read_retry_at = 0
        read.side_effect = None
        read.return_value = {'ok': True}
        self.assertEqual(await self.manager.read(read), {'ok': True})
        self.send.assert_not_called()

    async def test_exponential_cooldown_is_bounded_with_jitter(self):
        self.expire()
        self.send.side_effect = p.APIError('SECRET', status=503)
        with patch('custom_components.aigosmart.session.asyncio.sleep', new=AsyncMock()):
            for cycle in range(7):
                self.manager._retry_at = 0
                before = time.time()
                with self.assertRaises(recovery.RecoveryError):
                    await self.manager.ensure()
                delay = self.manager._retry_at - before
                base = min(900, 60 * 2 ** cycle)
                self.assertTrue(.8 * base <= delay <= 1.2 * base + 1)

    async def test_diagnostics_include_failed_shape_and_cooldown_without_values(self):
        self.expire()
        self.send.return_value = {'code': 200, 'data': {'iotToken': 'SECRET', 'iotTokenExpire': 'SECRET'}}
        with self.assertRaises(recovery.RecoveryError):
            await self.manager.ensure()
        self.entry.runtime_data = Mock(session=self.manager)
        data = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertNotIn('SECRET', json.dumps(data))
        self.assertEqual(data['refresh']['response']['validation'], 'invalid_iotTokenExpire')
        self.assertTrue(data['refresh']['cooldown_active'])
        self.assertEqual(data['refresh']['full_login_fallback'], 'unavailable_no_stored_password')

    async def test_failed_manual_login_does_not_close_old_session(self):
        async with self.manager.login_guard():
            with self.assertRaises(recovery.RecoveryError):
                await self.manager.ensure()
        self.assertFalse(self.manager._closed)
        await self.manager.ensure()
        self.send.assert_not_called()

    async def test_two_manual_logins_are_serialized(self):
        entered = []
        async def login():
            async with self.manager.login_guard():
                entered.append('start')
                await asyncio.sleep(0)
                entered.append('end')
        await asyncio.gather(login(), login())
        self.assertEqual(entered, ['start', 'end', 'start', 'end'])

    async def test_email_verification_requires_reauth_without_sending_code(self):
        self.expire()
        self.send.side_effect = p.NeedSecurityCodeError('SECRET', code='UC/NEED_SECURITY_CODE')
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.manager.ensure()
        self.send.assert_called_once()
        self.assertTrue(self.send.call_args.args[1].endswith(p.REFRESH))
        self.assertNotIn('password', self.entry.data)

    async def test_malformed_saved_deadline_requests_reauth_safely(self):
        self.client.session['refresh_token_expires_at'] = 'SECRET'
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.manager.ensure()
        self.send.assert_not_called()

    async def test_malformed_iot_deadline_refreshes_instead_of_crashing(self):
        self.client.session['iot_token_expires_at'] = 'SECRET'
        self.client.session['iot_token_ttl'] = None
        await self.manager.ensure()
        self.send.assert_called_once()

    async def test_repeated_unusable_renewal_requires_interactive_login(self):
        self.expire()
        self.send.return_value = {'code': 200, 'data': {'iotToken': 'NEXT'}}
        for _ in range(2):
            with self.assertRaises(recovery.RecoveryError):
                await self.manager.ensure()
            self.manager._retry_at = 0
        with self.assertRaises(ConfigEntryAuthFailed) as error:
            await self.manager.ensure()
        self.assertEqual(self.manager.status, 'reauth_required')
        self.assertEqual(recovery.classify_failure('property_read', error.exception),
                         ('token_refresh', 'response_validation'))
        self.assertEqual(self.send.call_count, 3)
        self.assertNotIn('password', self.entry.data)

class TransportDiagnosticTests(unittest.TestCase):
    def test_http_error_shape_survives_without_body_or_values(self):
        import urllib.error
        from email.message import Message
        headers = Message()
        headers['Content-Type'] = 'application/json'
        error = urllib.error.HTTPError('https://example.invalid/SECRET', 503, 'SECRET', headers,
            io.BytesIO(json.dumps({'code': 503, 'data': {'iotToken': 'SECRET'}}).encode()))
        opener = Mock()
        opener.open.side_effect = error
        client = p.Client()
        client.accept_session(fixtures.response())
        with patch.object(p.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(p.APIError):
                client.refresh_iot_token_sync()
        data = client.refresh_diagnostics
        self.assertNotIn('SECRET', json.dumps(data))
        self.assertEqual(data['http_category'], '5xx')
        self.assertEqual(data['vendor_code'], '503')
        self.assertEqual(data['fields']['iotToken'], 'string')
