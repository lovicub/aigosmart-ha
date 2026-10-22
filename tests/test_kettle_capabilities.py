import json
import socket
import unittest
from unittest.mock import patch
from scripts import kettle_capabilities as c, kettle_control as control, kettle_readonly as k


class CapabilitiesTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        guard.start()
        self.addCleanup(guard.stop)

    def model(self):
        # Synthetic contract, not a claim about the real kettle.
        return {'profile': {'deviceName': 'PRIVATE'}, 'properties': [
            {'identifier': key, 'accessMode': mode, 'dataType': {'type': kind, 'specs': limits},
             'desc': 'Model description'} for key, mode, kind, limits in [
                ('HeatingSwitch', 'rw', 'bool', {'0': 'off', '1': 'on'}),
                ('Target_temperature', 'rw', 'int', {'min': '40', 'max': '100', 'step': '5'}),
                ('heatpreservation', 'rw', 'bool', {'0': 'off', '1': 'on'}),
                ('Mode', 'rw', 'enum', {'0': 'boil', '2': 'keep'}),
                ('Time', 'rw', 'int', {'min': '0', 'max': '60', 'step': '1'}),
                ('status', 'r', 'enum', {'1': 'idle'})]]}

    def report(self):
        return c.build_report(c.parse_model(self.model()))

    def test_object_and_string_model(self):
        self.assertEqual(c.parse_model(self.model()), c.parse_model(json.dumps(self.model())))
        self.assertNotIn('PRIVATE', json.dumps(self.report()))
        self.assertEqual(self.report()['missing_focus'], [])

    def test_metadata_request_only(self):
        calls = []
        def send(method, url, headers, body):
            calls.append((url, json.loads(body)))
            return {'code': 200, 'data': json.dumps(self.model())}
        client = k.Client(send=send)
        client.token = 'PRIVATE'
        self.assertEqual(c.fetch(client, {'iotId': 'PRIVATE'})['source'], 'live-tsl')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], k.IOT + k.TSL)
        self.assertEqual(calls[0][1]['request']['apiVer'], '1.0.4')
        with self.assertRaises(k.APIError):
            client.signed(k.IOT, '/thing/properties/set', {'items': {'HeatingSwitch': 1}})
        self.assertEqual(len(calls), 1)

    def test_valid_commands(self):
        for key, value in [('HeatingSwitch', 0), ('HeatingSwitch', 1),
                           ('Target_temperature', 40), ('Target_temperature', 100),
                           ('heatpreservation', 1), ('Mode', 2), ('Time', 60)]:
            with self.subTest(key=key, value=value):
                result = control.plan(self.report(), key, value)
                self.assertFalse(result['executed'])
                self.assertEqual(result['params']['items'], {key: value})

    def test_rejections(self):
        for key, value in [('HeatingSwitch', True), ('HeatingSwitch', 2),
                           ('HeatingSwitch', 1.0), ('Target_temperature', '80'),
                           ('Target_temperature', 39), ('Target_temperature', 101),
                           ('Target_temperature', 42), ('Target_temperature', float('nan')),
                           ('Mode', 1), ('Time', -1), ('status', 1), ('unknown', 1)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                control.plan(self.report(), key, value)
        with self.assertRaises(ValueError):
            control.plan(c.build_report(), 'HeatingSwitch', 1)

    def test_incomplete_and_unsupported_models(self):
        for mutation in [{'access': None}, {'constraints': {}}, {'data_type': 'struct'},
                         {'constraints': {'min': 0, 'max': 100, 'step': 0}}, {'evidence': 'telemetry-only'}]:
            report = self.report()
            report['properties'][1].update(mutation)
            with self.assertRaises(ValueError):
                control.plan(report, 'Target_temperature', 80)
        model = self.model()
        model['properties'].append(model['properties'][0])
        with self.assertRaises(ValueError):
            c.parse_model(model)


if __name__ == '__main__':
    unittest.main()
