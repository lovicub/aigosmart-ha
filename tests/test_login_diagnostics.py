"""Offline diagnostics regressions. Every network connection is forbidden."""
import contextlib
import io
import json
import socket
import unittest
from unittest.mock import Mock, patch
from scripts import kettle_readonly as k
import test_kettle_readonly as existing


def setUpModule():
    guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
    guard.start()
    unittest.addModuleCleanup(guard.stop)


class Diagnostics(unittest.TestCase):
    secrets = ('user@example.com', 'PASSWORD_SECRET', 'ACCESS_SECRET', 'AUTH_SECRET',
               'SID_SECRET', 'TOKEN_SECRET', 'COOKIE_SECRET', 'Authorization', 'Traceback')

    def assert_private(self, output):
        for secret in self.secrets:
            self.assertNotIn(secret, output)

    def response(self, payload, status=200):
        response = Mock()
        response.status = status
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def http_error(self, payload, status=400):
        raw = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
        return k.urllib.error.HTTPError(k.UC + k.LOGIN + '?PASSWORD_SECRET', status,
                                      'PASSWORD_SECRET', {'Set-Cookie': 'COOKIE_SECRET'}, io.BytesIO(raw))

    def run_transport_login(self, reply):
        opener = Mock()
        if isinstance(reply, Exception):
            opener.open.side_effect = reply
        else:
            opener.open.return_value = reply
        output = io.StringIO()
        with patch.object(k.urllib.request, 'build_opener', return_value=opener), \
                contextlib.redirect_stderr(output), self.assertRaises(k.APIError) as error:
            k.Client(debug=True).login('user@example.com', 'PASSWORD_SECRET')
        self.assert_private(output.getvalue())
        self.assert_private(str(error.exception))
        return output.getvalue(), error.exception

    def test_success_all_stages_real_transport_metadata(self):
        flow = existing.Tests().flow()
        flow[0]['access_token'] = 'ACCESS_SECRET'
        flow[1]['code'] = 'AUTH_SECRET'
        opener = Mock()
        opener.open.side_effect = [self.response(item) for item in flow[:5]]
        output = io.StringIO()
        with patch.object(k.urllib.request, 'build_opener', return_value=opener), \
                patch.object(k.time, 'perf_counter', side_effect=[1, 1.125]*5), \
                contextlib.redirect_stderr(output):
            k.Client(debug=True).login('user@example.com', 'PASSWORD_SECRET')
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 5)
        for line, stage in zip(lines, ('UC', 'OAuth', 'region', 'OA', 'IoT')):
            self.assertIn('stage=' + stage + ' ', line)
            self.assertIn('http=200', line)
            self.assertIn('elapsed_ms=125.0', line)
            self.assertIn('exception=-', line)
            self.assertNotIn('?', line)
            self.assertNotIn('/v1.0/', line)
        self.assertIn('host=uc.aigostar.com', lines[0])
        self.assert_private(output.getvalue())

    def test_security_code_http_error(self):
        output, error = self.run_transport_login(self.http_error({
            'code': 'UC/NEED_SECURITY_CODE', 'message': 'PASSWORD_SECRET'}))
        self.assertIsInstance(error, k.NeedSecurityCodeError)
        self.assertIn('http=400', output)
        self.assertIn('api_code=UC/NEED_SECURITY_CODE', output)
        self.assertIn('exception=NeedSecurityCodeError', output)

    def test_security_code_http_success_stops_without_retry(self):
        calls = Mock(return_value=k.APIResponse({'code': 'UC/NEED_SECURITY_CODE'}, 200))
        with self.assertRaises(k.NeedSecurityCodeError):
            k.Client(calls).login('user', 'password')
        self.assertEqual(calls.call_count, 1)

    def test_http_allowlist_and_unknown_codes(self):
        for code, safe in [('invalid_grant', 'invalid_grant'), ('PASSWORD_SECRET', 'UNKNOWN'),
                           (401, '401'), ({'secret': 'PASSWORD_SECRET'}, 'UNKNOWN'),
                           (['PASSWORD_SECRET'], 'UNKNOWN')]:
            with self.subTest(code=code):
                output, _ = self.run_transport_login(self.http_error({
                    'code': code, 'message': 'TOKEN_SECRET', 'error_description': 'PASSWORD_SECRET'}))
                self.assertIn('api_code=' + safe, output)
                self.assertIn('exception=HTTPError', output)

    def test_http_non_json_and_size_limit(self):
        for raw in (b'<html>PASSWORD_SECRET</html>', b'x' * (k.MAX_RESPONSE + 1)):
            output, _ = self.run_transport_login(self.http_error(raw, 503))
            self.assertIn('http=503', output)
            self.assertIn('api_code=UNKNOWN', output)

    def test_network_and_parse_errors(self):
        for reply, exception, status in (
                (k.urllib.error.URLError('PASSWORD_SECRET'), 'URLError', '-'),
                (TimeoutError('PASSWORD_SECRET'), 'TimeoutError', '-'),
                (self.response([]), 'APIError', '200')):
            with self.subTest(exception=exception):
                output, _ = self.run_transport_login(reply)
                self.assertIn('exception=' + exception, output)
                self.assertIn('http=' + status, output)
        response = self.response({})
        response.read.return_value = b'PASSWORD_SECRET'
        output, _ = self.run_transport_login(response)
        self.assertIn('exception=JSONDecodeError', output)
        self.assertIn('http=200', output)

    def test_oauth_code_never_logged_even_if_allowlisted(self):
        for auth_code in ('AUTH_SECRET', '401'):
            flow = existing.Tests().flow()[:5]
            flow[1]['code'] = auth_code
            responses = iter(flow)
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                k.Client(lambda *args: next(responses), debug=True).login('user', 'password')
            oauth = output.getvalue().splitlines()[1]
            self.assertIn('api_code=UNKNOWN', oauth)
            self.assertNotIn(auth_code, oauth)

    def test_stage_for_each_failed_login_response(self):
        for index, stage in enumerate(('UC', 'OAuth', 'region', 'OA', 'IoT')):
            with self.subTest(stage=stage):
                flow = existing.Tests().flow()[:index] + [{'code': 'PASSWORD_SECRET', 'message': 'TOKEN_SECRET',
                                                           'error': 'invalid_grant'}]
                responses = iter(flow)
                output = io.StringIO()
                with contextlib.redirect_stderr(output), self.assertRaises(k.APIError):
                    k.Client(lambda *args: next(responses), debug=True).login('user', 'password')
                self.assertEqual(len(output.getvalue().splitlines()), index + 1)
                self.assertIn('stage=' + stage + ' ', output.getvalue().splitlines()[-1])
                self.assertIn('exception=APIError', output.getvalue().splitlines()[-1])
                self.assert_private(output.getvalue())

    def test_nested_oa_error_allowlist(self):
        flow = existing.Tests().flow()[:3] + [{'data': {'code': 401, 'message': 'PASSWORD_SECRET'}}]
        responses = iter(flow)
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(k.APIError):
            k.Client(lambda *args: next(responses), debug=True).login('user', 'password')
        self.assertIn('api_code=401', output.getvalue().splitlines()[-1])
        self.assert_private(output.getvalue())

    def test_debug_off_is_silent(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(k.APIError):
            k.Client(lambda *args: {'code': 'PASSWORD_SECRET'}).login('user', 'password')
        self.assertEqual(output.getvalue(), '')

    def test_cli_security_code_and_unexpected_exception_no_report(self):
        for debug in (False, True):
            for error in (k.NeedSecurityCodeError('PASSWORD_SECRET'), RuntimeError('TOKEN_SECRET')):
                client = k.Client()
                client.login = Mock(side_effect=error)
                output = io.StringIO()
                with patch.object(k, 'Client', return_value=client) as factory, \
                        patch('sys.argv', ['kettle_readonly.py', '--read-only'] + (['--debug'] if debug else [])), \
                        patch.object(k.getpass, 'getpass', side_effect=['user@example.com', 'PASSWORD_SECRET']), \
                        patch.object(k.Path, 'write_text') as write, \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    self.assertEqual(k.main(), 1)
                factory.assert_called_once_with(debug=debug)
                write.assert_not_called()
                self.assertIsNone(client.token)
                self.assert_private(output.getvalue())
                if isinstance(error, k.NeedSecurityCodeError):
                    self.assertIn('UC/NEED_SECURITY_CODE', output.getvalue())

    def test_untrusted_region_is_not_logged_or_contacted(self):
        flow = existing.Tests().flow()[:2] + [{'code': 200, 'data': {'oaApiGatewayEndpoint': 'PASSWORD_SECRET.evil'}}]
        responses = iter(flow)
        send = Mock(side_effect=lambda *args: next(responses))
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(k.APIError):
            k.Client(send, debug=True).login('user', 'password')
        self.assertEqual(send.call_count, 3)
        self.assertIn('stage=region', output.getvalue().splitlines()[-1])
        self.assert_private(output.getvalue())

    def test_redirect_diagnostics(self):
        output, _ = self.run_transport_login(k.APIError('Odrzucono przekierowanie.', status=302))
        self.assertIn('http=302', output)


if __name__ == '__main__':
    unittest.main()
