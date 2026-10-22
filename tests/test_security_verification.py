"""Security flow regressions with all socket connections forbidden."""
import contextlib
import io
import json
import socket
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from scripts import kettle_readonly as k
import test_kettle_readonly as existing


def setUpModule():
    guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
    guard.start()
    unittest.addModuleCleanup(guard.stop)


class SecurityFlow(unittest.TestCase):
    def run_flow(self, replies, answer='tak', code='OTP_SECRET'):
        replies = iter(replies)
        calls = []
        def send(*args):
            calls.append(args)
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            return k.APIResponse(reply, 200)
        client = k.Client(send, debug=True)
        output = io.StringIO()
        with patch('builtins.input', return_value=answer), \
                patch.object(k.getpass, 'getpass', return_value=code), \
                contextlib.redirect_stderr(output):
            try:
                client.login('user@example.com', 'PASSWORD_SECRET', interactive=True)
                devices = client.devices()
                client.properties(devices[0])
                error = None
            except k.APIError as exc:
                error = exc
        for secret in ('OTP_SECRET', 'PASSWORD_SECRET', 'user@example.com', 'ACCESS', 'TOKEN'):
            self.assertNotIn(secret, output.getvalue())
        return calls, error

    def test_complete_flow(self):
        calls, error = self.run_flow([{'code': 'UC/NEED_SECURITY_CODE'},
                                     {'code': 200}] + existing.Tests().flow())
        self.assertIsNone(error)
        self.assertEqual(len(calls), 9)
        self.assertEqual([call[1] for call in calls[:3]],
                         [k.UC+k.LOGIN, k.SMART+k.SEND_CODE, k.UC+k.LOGIN])
        self.assertEqual(json.loads(calls[1][3]), {
            'send_to': 'user@example.com', 'account_type': 'email', 'action': 'LoginSecurity',
            're_send_count': 0, 'captcha_token': ''})
        first = k.urllib.parse.parse_qs(calls[0][3].decode())
        retry = k.urllib.parse.parse_qs(calls[2][3].decode())
        self.assertNotIn('security_code', first)
        self.assertEqual(retry.pop('security_code'), ['OTP_SECRET'])
        self.assertEqual(first, retry)
        for _, url, headers, _ in calls[1:2]:
            canonical = 'smart-android-v1'+k.AES_KEY+headers['Timestamp']+'POST'+url
            self.assertEqual(headers['Signature'], k.hashlib.md5(canonical.encode()).hexdigest().upper())
            self.assertEqual(headers['Content-Type'], k.CONTENT)

    def test_decline_and_empty_code(self):
        for answer, code, count in [('nie', 'OTP_SECRET', 1), ('', 'OTP_SECRET', 1), ('tak', '', 2)]:
            calls, error = self.run_flow([{'code': 'UC/NEED_SECURITY_CODE'}, {'code': 200}], answer, code)
            self.assertIsInstance(error, k.APIError)
            self.assertEqual(len(calls), count)

    def test_errors_never_retry(self):
        for code in ('SENDCODE_INTERVAL_IS_TOO_SHORT', 'CAPTCHA_REQUIRED',
                     'INVALID_SECURITY_CODE', 'SECURITY_CODE_EXPIRED', 'UNKNOWN'):
            for stage in (1, 2):
                for http_error in (False, True):
                    with self.subTest(code=code, stage=stage, http=http_error):
                        error = k.APIError('Rejected', status=429 if stage == 1 else 400, code=code)
                        replies = [{'code': 'UC/NEED_SECURITY_CODE'}] + [{'code': 200}]*(stage-1)
                        replies += [error if http_error else {'code': code, 'message': 'OTP_SECRET'}]
                        calls, error = self.run_flow(replies)
                        self.assertIsInstance(error, k.APIError)
                        self.assertEqual(len(calls), stage+1)

    def test_repeated_challenge_stops(self):
        calls, error = self.run_flow([{'code': 'UC/NEED_SECURITY_CODE'}, {'code': 200},
                                     {'code': 'UC/NEED_SECURITY_CODE'}])
        self.assertIsInstance(error, k.NeedSecurityCodeError)
        self.assertEqual(len(calls), 3)

    def test_stable_across_processes(self):
        value = subprocess.check_output([sys.executable, '-c',
            'from scripts.kettle_readonly import DEVICE_ID; print(DEVICE_ID)'], text=True).strip()
        self.assertEqual(value, k.DEVICE_ID)

    def test_verify_endpoint_is_forbidden(self):
        send = Mock()
        with self.assertRaises(k.APIError):
            k.Client(send).uc('/message/v1.1/security/verify/anonymous', {}, smart=True)
        send.assert_not_called()

    def test_uc_must_accept_code_and_return_token(self):
        for reply in ({}, {'success': True}, {'code': 200}, {'access_token': ''},
                      {'access_token': 123}, {'error': 'invalid_grant', 'access_token': 'ACCESS'},
                      {'code': 'UC/INVALID_SECURITY_CODE', 'access_token': 'ACCESS'},
                      {'code': 'UC/SECURITY_CODE_EXPIRED'}, {'code': 'UC/NEED_CAPTCHA'}):
            with self.subTest(reply=reply):
                calls, error = self.run_flow([
                    {'code': 'UC/NEED_SECURITY_CODE'}, {'code': 200}, reply])
                self.assertIsInstance(error, k.APIError)
                self.assertEqual(len(calls), 3)
                self.assertEqual(calls[-1][1], k.UC + k.LOGIN)

    def test_smart_http_errors_sanitized(self):
        for path in (k.SEND_CODE,):
            error = k.urllib.error.HTTPError(k.SMART+path, 400, 'OTP_SECRET', {},
                io.BytesIO(b'{"code":"CAPTCHA_REQUIRED","message":"OTP_SECRET"}'))
            opener = Mock()
            opener.open.side_effect = error
            output = io.StringIO()
            with patch.object(k.urllib.request, 'build_opener', return_value=opener), \
                    contextlib.redirect_stderr(output), self.assertRaises(k.APIError) as caught:
                k.Client(debug=True).uc(path, {'input_code': 'OTP_SECRET'}, smart=True)
            self.assertEqual(caught.exception.code, 'CAPTCHA_REQUIRED')
            self.assertNotIn('OTP_SECRET', output.getvalue()+str(caught.exception))
