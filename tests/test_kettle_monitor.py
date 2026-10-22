import argparse
import json
import socket
import unittest
from unittest.mock import Mock, patch

from scripts import kettle_monitor as m
from scripts import kettle_readonly as k


def setUpModule():
    guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
    guard.start()
    unittest.addModuleCleanup(guard.stop)


class Tests(unittest.TestCase):
    def test_interval(self):
        self.assertEqual(m.interval_seconds('10'), 10)
        for value in ['0', '-1', 'nan', 'inf', '0.5']:
            with self.assertRaises(argparse.ArgumentTypeError):
                m.interval_seconds(value)

    def test_snapshots_changes_and_session(self):
        values = dict(HeatingSwitch=0, heatpreservation=0, Target_temperature=100,
                      Mode=0, Time=0, status=1)
        first = {key: {'value': value, 'time': 123} for key, value in values.items()}
        second = dict(first, HeatingSwitch={'value': 1, 'time': 456})
        calls = []
        def send(method, url, headers, body):
            calls.append((url, json.loads(body)))
            return {'code': 200, 'data': first if len(calls) == 1 else second}
        client = k.Client(send)
        client.token = 'SESSION_SECRET'
        sleeps = Mock(side_effect=[None, KeyboardInterrupt])
        output = Mock()
        with self.assertRaises(KeyboardInterrupt):
            m.monitor(client, {'iotId': 'DEVICE'}, sleep=sleeps, emit=output, now=lambda: 'UTC')
        rows = [json.loads(call.args[0]) for call in output.call_args_list]
        self.assertEqual(rows[0]['properties'], values)
        self.assertEqual(rows[0]['time'], 'UTC')
        self.assertEqual(rows[0]['changes'], {'initial': True})
        self.assertEqual(rows[1]['changes']['HeatingSwitch'],
                         {'before': 0, 'after': 1, 'kind': 'changed'})
        self.assertEqual(sleeps.call_args_list[0].args, (10,))
        self.assertTrue(all(url == k.IOT + k.PROPERTIES for url, _ in calls))
        self.assertTrue(all(body['request']['iotToken'] == 'SESSION_SECRET' for _, body in calls))
        self.assertNotIn('SESSION_SECRET', str(output.call_args_list))

    def test_added_removed_unchanged_redaction(self):
        self.assertEqual(m.changes({'Mode': 0}, {'Mode': 0}), {})
        diff = m.changes({'Old': 1}, {'New': 2})
        self.assertEqual(diff['Old']['kind'], 'removed')
        self.assertEqual(diff['New']['kind'], 'added')
        self.assertNotIn('SECRET', json.dumps(m.snapshot({'token': {'value': 'SECRET'}})))

    def test_auth_rate_and_unknown_stop_without_retry(self):
        errors = [k.APIError('secret', status=status) for status in (401, 403, 429)]
        errors += [k.APIError('secret', code=code) for code in ('401', '429', 'UNKNOWN')]
        for error in errors:
            with self.subTest(error=error):
                client = Mock()
                client.properties.side_effect = error
                sleep, emit = Mock(), Mock()
                self.assertEqual(m.monitor(client, {}, sleep=sleep, emit=emit), 1)
                sleep.assert_not_called()
                client.properties.assert_called_once()
                client.login.assert_not_called()
                self.assertNotIn('secret', str(emit.call_args_list))

    def test_backoff_cap_reset_and_previous_success(self):
        client = Mock()
        network = k.APIError('private', exception='URLError')
        client.properties.side_effect = ([{'Mode': {'value': 0}}] + [network] * 6 +
                                         [{'Mode': {'value': 1}}, network])
        sleep = Mock(side_effect=[None] * 8 + [KeyboardInterrupt])
        emit = Mock()
        with self.assertRaises(KeyboardInterrupt):
            m.monitor(client, {}, sleep=sleep, emit=emit)
        self.assertEqual([call.args[0] for call in sleep.call_args_list],
                         [10, 30, 60, 120, 240, 300, 300, 10, 30])
        rows = [json.loads(call.args[0]) for call in emit.call_args_list
                if call.args[0].startswith('{')]
        self.assertEqual(rows[1]['changes']['Mode']['before'], 0)

    def test_api_payload_error_code_retained(self):
        for code in (401, 403, 429):
            client = k.Client(lambda *args: {'code': code})
            with self.assertRaises(k.APIError) as error:
                client.properties({'iotId': 'DEVICE'})
            self.assertEqual(error.exception.code, str(code))

    def test_main_single_login_and_cleanup(self):
        client = Mock(token='secret')
        client.devices.return_value = [{'iotId': 'DEVICE'}]
        with patch.object(k, 'Client', return_value=client), \
             patch.object(k.getpass, 'getpass', side_effect=['user', 'pw']), \
             patch('builtins.input', return_value='1'), patch('builtins.print'), \
             patch.object(m, 'monitor', side_effect=KeyboardInterrupt) as monitor, \
             patch('sys.argv', ['monitor', '--read-only', '--interval', '12']):
            self.assertEqual(m.main(), 0)
            client.login.assert_called_once_with('user', 'pw', interactive=True)
            monitor.assert_called_once_with(client, {'iotId': 'DEVICE'}, 12)
            self.assertIsNone(client.token)
