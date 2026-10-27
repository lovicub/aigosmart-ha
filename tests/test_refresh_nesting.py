"""Wire-body regressions: synthetic credentials and blocked sockets only."""
import base64
import hashlib
import hmac
import json
import unittest
import uuid
from unittest.mock import Mock, patch
from custom_components.aigosmart import protocol as p
from test_session_refresh import response, setUpModule
import test_kettle_readonly as existing


class WireTests(unittest.TestCase):
    def verify_signature(self, call):
        method, url, headers, body = call.args
        self.assertEqual(method, 'POST')
        digest = base64.b64encode(hashlib.md5(body).digest()).decode()
        self.assertEqual(headers['Content-MD5'], digest)
        keys = headers['X-Ca-Signature-Headers'].split(',')
        self.assertEqual(keys, sorted(keys))
        uuid.UUID(headers['x-ca-nonce'])
        self.assertGreater(int(headers['x-ca-timestamp']), 0)
        canonical = f"POST\n{headers['Accept']}\n{digest}\n{headers['Content-Type']}\n{headers['Date']}\n"
        canonical += '\n'.join(k + ':' + headers[k] for k in keys)
        canonical += '\n/' + url.split('/', 3)[3]
        expected = base64.b64encode(hmac.new(b'synthetic-signing-key', canonical.encode(), hashlib.sha1).digest()).decode()
        self.assertEqual(headers['X-Ca-Signature'], expected)
        return json.loads(body)

    def test_refresh_final_body_signature_and_rotation(self):
        send = Mock(return_value=p.APIResponse({'code': 200, 'data': response()}, 200))
        client = p.Client(send)
        with patch.object(p.time, 'time', return_value=1000):
            client.accept_session(response(iotToken='OLD', refreshToken='SAVED_REFRESH', identityId='SAVED_ID'))
        with patch.object(p, 'APP_SECRET', 'synthetic-signing-key'), patch.object(p.time, 'time', return_value=2000):
            client.refresh_iot_token_sync()
        body = self.verify_signature(send.call_args)
        self.assertEqual(set(body), {'id', 'version', 'params', 'request'})
        self.assertEqual(body['version'], '1.0.0')
        self.assertEqual(body['params'], {'request': {'refreshToken': 'SAVED_REFRESH', 'identityId': 'SAVED_ID'}})
        self.assertEqual(body['request'], {'language': 'en-US', 'appKey': p.APP_KEY, 'apiVer': '1.0.4'})
        self.assertEqual(client.token, 'NEW_IOT_SECRET')
        self.assertEqual(client.session['refresh_token'], 'NEW_REFRESH_SECRET')
        self.assertEqual(client.session['iot_token_expires_at'], 5600)
        self.assertEqual(client.session['refresh_token_expires_at'], 88400)

    def test_login_session_and_device_wire_payloads_unchanged(self):
        send = Mock(side_effect=[p.APIResponse(r, 200) for r in existing.Tests().flow()])
        client = p.Client(send)
        with patch.object(p, 'APP_SECRET', 'synthetic-signing-key'):
            client.login('synthetic@example.invalid', 'synthetic-password')
            devices = client.devices()
            client.properties(devices[0])
        calls = {c.args[1]: c for c in send.call_args_list}
        session = self.verify_signature(calls[p.IOT + p.SESSION])
        self.assertEqual(session['params'], {'request': {'authCode': 'SID', 'appKey': p.APP_KEY, 'accountType': 'OA_SESSION'}})
        self.assertEqual(session['request']['apiVer'], '1.0.4')
        self.assertNotIn('iotToken', session['request'])
        devices_body = self.verify_signature(calls[p.IOT + p.DEVICES])
        self.assertEqual(devices_body['params'], {'pageNo': 1, 'pageSize': 100})
        self.assertEqual(devices_body['request']['apiVer'], '1.0.8')
        props = self.verify_signature(calls[p.IOT + p.PROPERTIES])
        self.assertEqual(props['params'], {'iotId': devices[0]['iotId']})
        self.assertEqual(props['request']['apiVer'], '1.0.0')
        self.assertEqual(props['request']['iotToken'], client.token)
