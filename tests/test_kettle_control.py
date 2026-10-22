import contextlib
import io
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from scripts import kettle_control as c, kettle_readonly as k


class ControlTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        guard.start()
        self.addCleanup(guard.stop)
        self.report = json.loads((Path(__file__).resolve().parents[1] / 'tests/fixtures/kettle_capabilities.json').read_text())
        self.calls = []
        self.device = {'iotId': 'DEVICE_SECRET', 'status': 1}
        self.values = {'HeatingSwitch': 0, 'status': 1, 'Target_temperature': 100}
        self.after = 80
        self.failure = None
        self.read_failure = False
        self.client = c.ControlledClient(send=self.send, debug=True)
        self.client.token = 'TOKEN_SECRET'

    def send(self, method, url, headers, body):
        data = json.loads(body)
        self.calls.append((url, data))
        if url == k.IOT + k.DEVICES:
            return {'code': 200, 'data': {'data': [self.device]}}
        if url == k.IOT + k.PROPERTIES:
            if self.client.write_attempted and self.read_failure:
                raise k.APIError('BODY_SECRET')
            values = dict(self.values)
            if self.client.write_attempted:
                values['Target_temperature'] = self.after
            return {'code': 200, 'data': {key: {'value': value} for key, value in values.items()}}
        if url == k.IOT + c.SET:
            if self.failure:
                raise self.failure
            return {'code': 200, 'data': {}}
        raise AssertionError('Unexpected endpoint')

    def run_test(self, answer=c.CONFIRM):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = c.controlled_test(self.client, self.device, self.report,
                                       ask=lambda _: answer)
        for secret in ('DEVICE_SECRET', 'TOKEN_SECRET', 'BODY_SECRET'):
            self.assertNotIn(secret, output.getvalue())
        return result, output.getvalue()

    def writes(self):
        return [body for url, body in self.calls if url == k.IOT + c.SET]

    def test_success_exact_payload_and_order(self):
        result, output = self.run_test()
        self.assertEqual(result, 0)
        self.assertIn('Zweryfikowano', output)
        self.assertEqual([url for url, _ in self.calls], [k.IOT + p for p in
                         [k.DEVICES, k.PROPERTIES, k.DEVICES, k.PROPERTIES, c.SET, k.PROPERTIES]])
        self.assertEqual(self.writes()[0]['params'], {'iotId': 'DEVICE_SECRET', 'items': {'Target_temperature': 80}})
        with self.assertRaises(ValueError):
            self.run_test()
        self.assertEqual(len(self.writes()), 1)

    def test_cancel(self):
        for answer in ('', 'tak', 'USTAW 80 ', 'yes'):
            self.assertEqual(self.run_test(answer)[0], 0)
        self.assertEqual(self.writes(), [])

    def test_unsafe_or_unknown_properties(self):
        for key, value in [('HeatingSwitch', 1), ('HeatingSwitch', '0'), ('status', 2),
                           ('status', True), ('Target_temperature', 80),
                           ('Target_temperature', 100.0), ('status', None)]:
            self.values = {'HeatingSwitch': 0, 'status': 1, 'Target_temperature': 100}
            self.values[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.run_test()
        self.assertFalse(self.writes())

    def test_offline_unknown_or_ambiguous_availability(self):
        for value in (0, None, '1', True, 1.0):
            self.device['status'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_test()
        self.assertFalse(self.writes())

    def test_change_during_confirmation(self):
        def answer(_):
            self.values['HeatingSwitch'] = 1
            return c.CONFIRM
        with self.assertRaises(ValueError):
            c.controlled_test(self.client, self.device, self.report, ask=answer, emit=lambda _: None)
        self.assertFalse(self.writes())

    def test_failed_or_uncertain_write_is_never_retried(self):
        self.failure = k.APIError('BODY_SECRET', exception='TimeoutError')
        self.after = 100
        self.assertEqual(self.run_test()[0], 1)
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.calls[-1][0], k.IOT + k.PROPERTIES)
        with self.assertRaises(k.APIError):
            self.client.signed(k.IOT, c.SET, {'iotId': 'DEVICE_SECRET', 'items': {'Target_temperature': 80}})
        self.assertEqual(len(self.writes()), 1)

    def test_verification_failure(self):
        for after in (100, '80', 80.0, None, True):
            self.client = c.ControlledClient(send=self.send)
            self.after = after
            self.assertEqual(self.run_test()[0], 1)
        self.client = c.ControlledClient(send=self.send)
        self.read_failure = True
        self.assertEqual(self.run_test()[0], 1)

    def test_transport_allowlist_is_narrow(self):
        for items in ({'HeatingSwitch': 1}, {'Mode': 0}, {'status': 1},
                      {'Target_temperature': 80, 'HeatingSwitch': 0},
                      {'Target_temperature': 81}, {'Target_temperature': 80.0}):
            self.client._write_device = 'DEVICE_SECRET'
            with self.subTest(items=items), self.assertRaises(k.APIError):
                self.client.signed(k.IOT, c.SET, {'iotId': 'DEVICE_SECRET', 'items': items})
        self.assertEqual(self.calls, [])
        for client in (k.Client(send=self.send), self.client):
            with self.assertRaises(k.APIError):
                client.signed(k.IOT, c.SET, {'iotId': 'DEVICE_SECRET', 'items': {'Target_temperature': 80}})
        self.assertEqual(self.calls, [])

    def test_cli_rejects_other_writes_before_login(self):
        for key, value in [('HeatingSwitch', '1'), ('Mode', '0'), ('status', '1'),
                           ('Target_temperature', '100'), ('Target_temperature', '80.0')]:
            with patch('sys.argv', ['kettle_control', '--write', key, value]), patch.object(c, 'live_main') as live:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(c.main(), 1)
                live.assert_not_called()

    def test_read_failure_blocks_write(self):
        with patch.object(self.client, 'properties', side_effect=k.APIError('BODY_SECRET')):
            with self.assertRaises(k.APIError):
                self.run_test()
        self.assertFalse(self.writes())

    def test_offline_during_confirmation(self):
        def answer(_):
            self.device['status'] = 0
            return c.CONFIRM
        with self.assertRaises(ValueError):
            c.controlled_test(self.client, self.device, self.report, ask=answer, emit=lambda _: None)
        self.assertFalse(self.writes())

    def test_missing_tsl_blocks_before_network(self):
        self.report['source'] = 'not_collected'
        with self.assertRaises(ValueError):
            self.run_test()
        self.assertFalse(self.calls)

    def test_dry_run_offline(self):
        with patch('sys.argv', ['kettle_control', '--dry-run', '--capabilities', str(Path(__file__).resolve().parent / 'fixtures/kettle_capabilities.json'), 'Target_temperature', '80']), patch.object(c, 'live_main') as live:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(c.main(), 0)
            self.assertEqual(json.loads(output.getvalue())['params']['items'], {'Target_temperature': 80})
            live.assert_not_called()


if __name__ == '__main__':
    unittest.main()
