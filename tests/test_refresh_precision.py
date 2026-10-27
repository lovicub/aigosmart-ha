"""Mock-only response precision and redaction regressions."""
import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch
from custom_components.aigosmart import protocol as p
from test_session_refresh import response, setUpModule


class PrecisionTests(unittest.TestCase):
    def client(self, result):
        c = p.Client(send=Mock(return_value=result))
        c.accept_session(response())
        return c

    def test_null_success_preserves_safe_code_http_and_session(self):
        c = self.client(p.APIResponse({'code': 200, 'data': None}, 200))
        old = dict(c.session)
        with self.assertRaises(p.APIError):
            c.refresh_iot_token_sync()
        d = c.refresh_diagnostics
        self.assertEqual(d['envelope'], 'object')
        self.assertEqual(d['data_state'], 'null')
        self.assertEqual(d['vendor_code'], '200')
        self.assertEqual(d['http_category'], '2xx')
        self.assertEqual(d['validation'], 'session_data_type')
        self.assertEqual(d['code_category'], 'success')
        self.assertEqual(c.session, old)

    def test_success_and_shapes(self):
        c = self.client(p.APIResponse({'code': 200, 'data': response()}, 200))
        c.refresh_iot_token_sync()
        self.assertEqual(c.refresh_diagnostics['result'], 'success')
        for payload, state in (({'code': 200}, 'absent'), ({'data': []}, 'invalid')):
            self.assertEqual(p.session_shape(payload)['data_state'], state)

    def test_error_masking_and_safe_result_preservation(self):
        for code, safe in ((403, '403'), ('PRIVATE_CODE_SECRET', 'UNKNOWN')):
            payload = {'code': code, 'message': 'MESSAGE_SECRET',
                       'error': {'token': 'TOKEN_SECRET'}, 'status': 'ACCOUNT_SECRET',
                       'PRIVATE_KEY_SECRET': 'IDENTITY_SECRET'}
            c = self.client(p.APIResponse(payload, 200))
            with self.assertRaises(p.APIError):
                c.refresh_iot_token_sync()
            d = c.refresh_diagnostics
            self.assertEqual(d['vendor_code'], safe)
            self.assertEqual(d['root_fields']['message'], 'string')
            self.assertEqual(d['root_fields']['error'], 'object')
            self.assertNotIn('SECRET', json.dumps(d))

    def test_transport_http_and_json_distinct(self):
        http = urllib.error.HTTPError('https://invalid', 503, 'MESSAGE_SECRET',
                                      {}, io.BytesIO(b'{"code":503,"message":"SECRET"}'))
        for error, validation in ((http, 'http_status'),
                                 (TimeoutError('SECRET'), 'transport')):
            opener = Mock()
            opener.open.side_effect = error
            c = self.client(None)
            c.send = p.transport
            with patch.object(p.urllib.request, 'build_opener', return_value=opener):
                with self.assertRaises(p.APIError):
                    c.refresh_iot_token_sync()
            self.assertEqual(c.refresh_diagnostics['validation'], validation)
            self.assertEqual(c.refresh_diagnostics['error_category'],
                             'http_error' if validation == 'http_status' else 'transport')
            self.assertNotIn('SECRET', json.dumps(c.refresh_diagnostics))
        fake = Mock(status=200, headers={})
        fake.read.return_value = b'NOT_JSON_SECRET'
        fake.__enter__ = Mock(return_value=fake)
        fake.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = fake
        c.send = p.transport
        with patch.object(p.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(p.APIError):
                c.refresh_iot_token_sync()
        self.assertEqual(c.refresh_diagnostics['validation'], 'json_decode')
        self.assertEqual(c.refresh_diagnostics['error_category'], 'json_decode')
        self.assertNotIn('SECRET', json.dumps(c.refresh_diagnostics))
