import base64
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import socket
import unittest
from unittest.mock import patch
from scripts import kettle_readonly as k


def setUpModule():
    guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
    guard.start()
    unittest.addModuleCleanup(guard.stop)


class Tests(unittest.TestCase):
    def flow(self):
        return [{'access_token': 'ACCESS'}, {'code': 'AUTH'},
                {'code': 200, 'data': {'oaApiGatewayEndpoint': k.OA}},
                {'data': {'data': {'loginSuccessResult': {'sid': 'SID'}}}},
                {'code': 200, 'data': {'iotToken': 'TOKEN', 'refreshToken': 'PRIVATE'}},
                {'code': 200, 'data': {'data': [{'iotId': 'DEVICE', 'deviceName': 'PRIVATE'}]}},
                {'code': 200, 'data': {'Temperature': {'value': 85}, 'Mode': {'value': 'boil'}}}]

    def test_full_login_list_properties_and_signatures(self):
        responses = iter(self.flow())
        calls = []
        def send(method, url, headers, body):
            calls.append((method, url, headers, body))
            return next(responses)
        client = k.Client(send)
        client.login('user@example.com', 'password')
        devices = client.devices()
        props = client.properties(devices[0])
        self.assertEqual(props['Temperature']['value'], 85)
        self.assertEqual(len(calls), 7)
        form = k.urllib.parse.parse_qs(calls[0][3].decode())
        self.assertNotEqual(form['password'][0], 'password')
        self.assertEqual(calls[1][2]['Authorization'], 'Bearer ACCESS')
        for _, url, headers, body in calls[2:]:
            path = k.urllib.parse.urlsplit(url).path
            content_md5 = headers.get('Content-MD5', '')
            if path == k.OA_PATH:
                fields = k.urllib.parse.parse_qs(body.decode())
                path += '?loginByOauthRequest=' + fields['loginByOauthRequest'][0]
            else:
                self.assertEqual(content_md5, base64.b64encode(hashlib.md5(body).digest()).decode())
            canonical = f"POST\n{k.CONTENT}\n{content_md5}\n{headers['Content-Type']}\n{headers['Date']}\n"
            canonical += '\n'.join(n + ':' + headers[n] for n in sorted(headers) if n.startswith('x-ca-')) + '\n' + path
            expected = base64.b64encode(hmac.new(k.APP_SECRET.encode(), canonical.encode(), hashlib.sha1).digest()).decode()
            self.assertEqual(headers['X-Ca-Signature'], expected)
        self.assertEqual(json.loads(calls[-1][3])['request']['iotToken'], 'TOKEN')
        self.assertEqual(json.loads(calls[-1][3])['params'], {'iotId': 'DEVICE'})

    def test_encryption_known_vector(self):
        self.assertEqual(k.encrypt_password('password'), '7lCmibubyNC0JTXoJb/V7w=='  # Independently verified with OpenSSL AES-256-CBC.
                             )

    def test_pagination(self):
        responses = iter([{'code': 200, 'data': {'data': [{'iotId': str(i)} for i in range(100)]}},
                          {'code': 200, 'data': {'data': [{'iotId': 'last'}]}}])
        calls = []
        def send(method, url, headers, body):
            calls.append(json.loads(body)['params']['pageNo'])
            return next(responses)
        self.assertEqual(len(k.Client(send).devices()), 101)
        self.assertEqual(calls, [1, 2])

    def test_deny_writes_and_untrusted_hosts(self):
        for url in [k.IOT + '/thing/properties/set', 'https://evil.example' + k.PROPERTIES]:
            with self.assertRaises(k.APIError):
                k.Client(lambda *args: self.fail('Network must not run')).request('POST', url, {}, b'{}')

    def test_bad_login_stops(self):
        for response in [{}, {'code': 'UC/NEED_SECURITY_CODE'}, {'access_token': ''}]:
            with self.subTest(response=response), self.assertRaises(k.APIError):
                k.Client(lambda *args: response).login('user', 'password')

    def test_invalid_api_payloads(self):
        for result in [{'code': 401, 'message': 'SECRET'}, {'code': 200, 'data': None},
                       {'code': 200, 'data': {'data': 'invalid'}}]:
            with self.assertRaises(k.APIError) as error:
                k.Client(lambda *args: result).devices()
            self.assertNotIn('SECRET', str(error.exception))

    def test_region_rejected_before_oauth(self):
        responses = iter(self.flow()[:2] + [{'code': 200, 'data': {'oaApiGatewayEndpoint': 'evil.example'}}])
        with self.assertRaises(k.APIError):
            k.Client(lambda *args: next(responses)).login('user', 'pw')

    def test_anonymization(self):
        props = {'Temperature': {'value': 85}, 'token': {'value': 1234},
                 'Mode': {'value': 'user@example.com'}, 'Nested': {'value': {'password': 'SECRET'}},
                 'deviceId': {'value': 789}, 'NaN': {'value': float('nan')}}
        text = json.dumps(k.anonymize(props), allow_nan=False)
        for secret in ['SECRET', 'user@example.com', '1234', '789', 'deviceId', 'token']:
            self.assertNotIn(secret, text)
        self.assertIn('85', text)

    def test_main_writes_only_anonymized_report(self):
        responses = iter(self.flow())
        client = k.Client(lambda *args: next(responses))
        with tempfile.TemporaryDirectory() as temp, patch.object(k, 'Client', return_value=client), \
             patch.object(k, 'REPORT', Path(temp) / 'report.json'), \
             patch('sys.argv', ['kettle_readonly.py', '--read-only']), \
             patch.object(k.getpass, 'getpass', side_effect=['user@example.com', 'password']), \
             patch('builtins.input', return_value='1'), patch('builtins.print'):
            self.assertEqual(k.main(), 0)
            report = k.REPORT.read_text()
            for secret in ['ACCESS', 'AUTH', 'SID', 'TOKEN', 'PRIVATE', 'DEVICE', 'password', 'user@example.com']:
                self.assertNotIn(secret, report)
            self.assertIsNone(client.token)

    def test_redirect_rejected(self):
        with self.assertRaises(k.APIError):
            k.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example')


if __name__ == '__main__':
    unittest.main()
