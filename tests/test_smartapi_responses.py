"""Real response parser and interactive flow, with network connections forbidden."""
import contextlib
import io
import json
import socket
import unittest
from unittest.mock import Mock, patch

from scripts import kettle_readonly as k


def setUpModule():
    guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
    guard.start()
    unittest.addModuleCleanup(guard.stop)


def response(raw, status=200, content_type='application/json'):
    reply = Mock()
    reply.status = status
    reply.headers = {'Content-Type': content_type}
    reply.read.return_value = raw
    reply.__enter__ = Mock(return_value=reply)
    reply.__exit__ = Mock(return_value=False)
    return reply


class SmartResponses(unittest.TestCase):
    def request(self, reply, path=k.SEND_CODE):
        opener = Mock()
        if isinstance(reply, Exception):
            opener.open.side_effect = reply
        else:
            opener.open.return_value = reply
        output = io.StringIO()
        with patch.object(k.urllib.request, 'build_opener', return_value=opener), contextlib.redirect_stderr(output):
            try:
                result = k.Client(debug=True).uc(path, {}, smart=True)
                error = None
            except k.APIError as exc:
                result, error = None, exc
        self.assertEqual(opener.open.call_count, 1)
        return result, error, output.getvalue()

    def test_empty_200_and_204(self):
        for path in (k.SEND_CODE,):
            for status in (200, 204):
                for raw in (b'', b' \r\n\t'):
                    with self.subTest(path=path, status=status, raw=raw):
                        result, error, output = self.request(response(raw, status), path)
                        self.assertIsNone(error)
                        self.assertEqual(result, {'code': 200})
                        self.assertIn(f'http={status}', output)
                        self.assertIn(f'response_length={len(raw)}', output)

    def test_valid_json_is_validated(self):
        for path in (k.SEND_CODE,):
            for raw, accepted in ((b'{"code":200}', True), (b'{"code":"200"}', True),
                                  (b'{}', False), (b'{"ok":true}', False),
                                  (b'{"code":200,"success":false}', False), (b'[]', False)):
                with self.subTest(path=path, raw=raw):
                    _, error, _ = self.request(response(raw), path)
                    self.assertEqual(error is None, accepted)

    def test_code_types_categories_and_rejection_rules(self):
        cases = [
            ({'code': 200}, 'integer', 'success', 'passed'),
            ({'code': '200'}, 'string', 'success', 'passed'),
            ({'success': True}, 'missing', 'missing', 'smart_code_missing'),
            ({'ok': True}, 'missing', 'missing', 'smart_code_missing'),
            ({'code': 401}, 'integer', 'known_error', 'smart_code_known_error'),
            ({'code': '401'}, 'string', 'known_error', 'smart_code_known_error'),
            ({'code': 'INVALID_SECURITY_CODE'}, 'string', 'known_error', 'smart_code_known_error'),
            ({'code': 'SECURITY_CODE_EXPIRED'}, 'string', 'known_error', 'smart_code_known_error'),
            ({'code': 'CAPTCHA_REQUIRED'}, 'string', 'known_error', 'smart_code_known_error'),
            ({'code': 'OTP_SECRET'}, 'string', 'unknown', 'smart_code_unknown'),
            ({'code': 201}, 'integer', 'unknown', 'smart_code_unknown'),
            ({'code': ' 200'}, 'string', 'unknown', 'smart_code_unknown'),
            ({'code': '0200'}, 'string', 'unknown', 'smart_code_unknown'),
            ({'code': 200.0}, 'number', 'invalid_type', 'smart_code_invalid_type'),
            ({'code': True}, 'boolean', 'invalid_type', 'smart_code_invalid_type'),
            ({'code': None}, 'null', 'invalid_type', 'smart_code_invalid_type'),
            ({'code': {}}, 'object', 'invalid_type', 'smart_code_invalid_type'),
            ({'code': []}, 'array', 'invalid_type', 'smart_code_invalid_type'),
            ({'code': 200, 'success': False}, 'integer', 'success', 'smart_success'),
            ({'code': '200', 'data': False}, 'string', 'success', 'smart_data'),
            ({'code': 200, 'error': 'OTP_SECRET'}, 'integer', 'success', 'smart_error'),
        ]
        for path in (k.SEND_CODE,):
            for payload, kind, category, validation in cases:
                with self.subTest(path=path, kind=kind, validation=validation, payload=payload):
                    _, error, output = self.request(response(json.dumps(payload).encode()), path)
                    self.assertEqual(error is None, validation == 'passed')
                    self.assertIn('code_type=' + kind + ' ', output)
                    self.assertIn('code_category=' + category + ' ', output)
                    self.assertIn('validation=' + validation, output)
                    if error:
                        self.assertEqual(error.validation, validation)
                    self.assertIn('json_fields=' + ','.join(sorted(payload)), output)
                    self.assertNotIn('OTP_SECRET', output)

    def test_response_field_names_are_untrusted(self):
        payload = {'success': True, 'user@example.com\nOTP_SECRET': 'PASSWORD_SECRET',
                   'token': 'TOKEN_SECRET'}
        _, error, output = self.request(response(json.dumps(payload).encode()), k.SEND_CODE)
        self.assertIsInstance(error, k.APIError)
        self.assertIn('json_fields=success,redacted_fields:2', output)
        self.assertEqual(len(output.splitlines()), 1)
        for secret in ('user@example.com', 'OTP_SECRET', 'PASSWORD_SECRET', 'TOKEN_SECRET'):
            self.assertNotIn(secret, output + str(error))

    def test_parser_and_http_rejection_diagnostics(self):
        for raw, rule in ((b'[]', 'json_object'), (b'not JSON', 'json_decode'),
                          (b'x' * (k.MAX_RESPONSE + 1), 'response_size')):
            _, error, output = self.request(response(raw), k.SEND_CODE)
            self.assertIsInstance(error, k.APIError)
            self.assertIn('validation=' + rule, output)
        reply = k.urllib.error.HTTPError(k.SMART + k.SEND_CODE, 400, 'OTP_SECRET',
                                        {'Content-Type': 'application/json'},
                                        io.BytesIO(b'{"code":"200"}'))
        _, error, output = self.request(reply, k.SEND_CODE)
        self.assertIsInstance(error, k.APIError)
        for detail in ('validation=http_status', 'json_fields=code', 'code_type=string',
                       'code_category=success'):
            self.assertIn(detail, output)

    def test_invalid_json_is_safe_failure(self):
        for path in (k.SEND_CODE,):
            for raw in (b'<html>OTP_SECRET</html>', b'{"token":"OTP_SECRET"', b'\xffOTP_SECRET'):
                _, error, output = self.request(response(raw, content_type='text/html; secret=OTP_SECRET'), path)
                self.assertIsInstance(error, k.APIError)
                self.assertIn('JSON', str(error))
                self.assertIn(f'response_length={len(raw)}', output)
                self.assertIn('content_type=text/html', output)
                self.assertNotIn('OTP_SECRET', output + str(error))

    def test_untrusted_content_type_is_redacted(self):
        _, error, output = self.request(response(b'OTP_SECRET', content_type='OTP_SECRET\nInjected'))
        self.assertIsInstance(error, k.APIError)
        self.assertIn('content_type=other', output)
        self.assertNotIn('OTP_SECRET', output)
        self.assertEqual(len(output.splitlines()), 1)

    def test_http_400_never_succeeds(self):
        for path in (k.SEND_CODE,):
            for raw in (b'', b'OTP_SECRET', b'{"code":200}', b'{"code":"CAPTCHA_REQUIRED"}'):
                reply = k.urllib.error.HTTPError(k.SMART + path, 400, 'OTP_SECRET',
                                                 {'Content-Type': 'application/json'}, io.BytesIO(raw))
                _, error, output = self.request(reply, path)
                self.assertIsInstance(error, k.APIError)
                self.assertEqual(error.status, 400)
                self.assertIn(f'response_length={len(raw)}', output)
                self.assertNotIn('OTP_SECRET', output + str(error))

    def test_empty_response_rejected_elsewhere(self):
        for url in (k.UC + k.LOGIN, k.IOT + k.PROPERTIES, k.UC + k.SEND_CODE,
                    'https://evil.example' + k.SEND_CODE):
            opener = Mock()
            opener.open.return_value = response(b'')
            with patch.object(k.urllib.request, 'build_opener', return_value=opener), self.assertRaises(k.APIError):
                k.transport('POST', url, {}, b'{}')

    def test_size_limit_preserved(self):
        _, error, _ = self.request(response(b' ' * (k.MAX_RESPONSE + 1)))
        self.assertIsInstance(error, k.APIError)

    def test_empty_send_prompts_once_without_resending(self):
        opener = Mock()
        opener.open.side_effect = [response(b'', 200)]
        with patch.object(k.urllib.request, 'build_opener', return_value=opener), \
                patch('builtins.input', return_value='tak'), \
                patch.object(k.getpass, 'getpass', return_value='OTP_SECRET') as prompt:
            self.assertEqual(k.Client().security_verification('user@example.com'), 'OTP_SECRET')
        prompt.assert_called_once()
        self.assertEqual([call.args[0].full_url for call in opener.open.call_args_list],
                         [k.SMART + k.SEND_CODE])
