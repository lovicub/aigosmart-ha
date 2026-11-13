"""Diagnostics export the declared model and reported values without private data."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.aigosmart import api
from custom_components.aigosmart.diagnostics import async_get_config_entry_diagnostics
from custom_components.aigosmart.model import parse_identifiers

TSL = {
    'properties': [{'identifier': 'Target_temperature', 'accessMode': 'rw', 'name': 'MY_PRIVATE_LABEL',
                    'dataType': {'type': 'int', 'specs': {'min': 40, 'max': 90, 'step': 5, 'unit': '°C'}}}],
    'events': [{'identifier': 'post', 'type': 'info', 'name': 'PRIVATE_EVENT_NAME',
                'outputData': [{'identifier': 'Mode', 'name': 'x'}, {'identifier': 'api_token'}, 'junk']},
               {'identifier': 'hardwareReset', 'type': 'alert'},
               {'identifier': 'user_email'}, {'identifier': 7}, 'junk'],
    'services': [{'identifier': 'set', 'outputData': 'not-a-list'}, {'identifier': 'get', 'desc': 'PRIVATE_DESC'}],
}


class ParseIdentifierTests(unittest.TestCase):
    def test_keeps_identifier_type_and_output_fields_only(self):
        self.assertEqual(parse_identifiers(TSL, 'events'), [
            {'identifier': 'post', 'type': 'info', 'output': ['Mode']},
            {'identifier': 'hardwareReset', 'type': 'alert', 'output': []}])
        self.assertEqual(parse_identifiers(TSL, 'services'), [
            {'identifier': 'set', 'type': None, 'output': []},
            {'identifier': 'get', 'type': None, 'output': []}])
        self.assertNotIn('PRIVATE', json.dumps([parse_identifiers(TSL, s) for s in ('events', 'services')]))

    def test_accepts_json_text_and_never_raises(self):
        self.assertEqual(len(parse_identifiers(json.dumps(TSL), 'events')), 2)
        for data in ('not json', None, [], {}, {'events': 'x'}, {'events': None}):
            self.assertEqual(parse_identifiers(data, 'events'), [])

    def test_lists_are_bounded(self):
        data = {'events': [{'identifier': f'e{i}', 'outputData': [{'identifier': f'f{j}'} for j in range(40)]}
                           for i in range(80)]}
        result = parse_identifiers(data, 'events')
        self.assertEqual(len(result), 50)
        self.assertEqual(len(result[0]['output']), 20)


class ModelTests(unittest.TestCase):
    def test_model_carries_events_and_services(self):
        client = api.AigoClient(Mock())
        with patch.object(client, 'signed', return_value={'data': json.dumps(TSL)}):
            model = client.model({'iotId': 'fake'})
        self.assertEqual(model['source'], 'live-tsl')
        self.assertEqual([row['identifier'] for row in model['properties']], ['Target_temperature'])
        self.assertEqual([row['identifier'] for row in model['events']], ['post', 'hardwareReset'])
        self.assertEqual([row['identifier'] for row in model['services']], ['set', 'get'])


def export(runtime):
    entry = SimpleNamespace(runtime_data=runtime, data={})
    return asyncio.run(async_get_config_entry_diagnostics(None, entry))


class DiagnosticsTests(unittest.TestCase):
    def runtime(self):
        client = api.AigoClient(Mock())
        with patch.object(client, 'signed', return_value={'data': json.dumps(TSL)}):
            model = client.model({'iotId': 'fake'})
        data = {'Target_temperature': {'value': 80}, 'ssid_name': {'value': 'PRIVATE_WIFI'},
                'Mode': {'value': 'PRIVATE_TEXT'}, 'access_token': {'value': 5}}
        return SimpleNamespace(session=None, model=model, data=data)

    def test_declared_and_reported_properties_are_exported(self):
        summary = export(self.runtime())['model']
        self.assertEqual(summary['declared_properties'], [{
            'identifier': 'Target_temperature', 'access': 'read-write', 'data_type': 'int',
            'constraints': {'min': 40, 'max': 90, 'step': 5, 'unit': '°C'}}])
        self.assertEqual([row['identifier'] for row in summary['events']], ['post', 'hardwareReset'])
        self.assertEqual([row['identifier'] for row in summary['services']], ['set', 'get'])
        reported = {row['property']: row['value'] for row in summary['reported_properties']}
        self.assertEqual(reported['Target_temperature'], 80)
        self.assertEqual(reported['Mode'], '[REDACTED]')

    def test_private_values_are_never_exported(self):
        exported = json.dumps(export(self.runtime()))
        for private in ('MY_PRIVATE_LABEL', 'PRIVATE_EVENT_NAME', 'PRIVATE_DESC', 'PRIVATE_WIFI',
                        'PRIVATE_TEXT', 'ssid_name', 'access_token', 'user_email'):
            self.assertNotIn(private, exported)

    def test_entry_without_runtime_or_model_still_exports(self):
        empty = {'declared_properties': [], 'events': [], 'services': [], 'reported_properties': []}
        self.assertEqual(export(None)['model'], empty)
        self.assertEqual(export(SimpleNamespace(session=None, model=None, data=None))['model'], empty)
