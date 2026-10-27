"""TSL enum descriptions preserve all stable raw states and service options."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock

from custom_components.aigosmart.enum_labels import enum_key, enum_label, enum_labels
from custom_components.aigosmart.model import parse_model
from custom_components.aigosmart.select import ModeSelect
from custom_components.aigosmart.sensor import AigoSensor, AigoEnumDescriptionSensor
import test_reconnect_flow as flow_fixtures
from test_session_refresh import setUpModule

MODEL = json.loads(Path('tests/fixtures/kettle_capabilities.json').read_text())


def coordinator(model=None, **values):
    return Mock(model=MODEL if model is None else model, device={'iotId': 'fake'},
        data={key: {'value': value} for key, value in values.items()},
        async_write=AsyncMock(), last_update_success=True)


class EnumTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_modes_preserve_raw_select_values_and_writes(self):
        for raw, label in {'0':'One-click boil','1':'Boil and keep warm','2':'Heating and keep warm'}.items():
            for value in (int(raw), raw):
                c = coordinator(Mode=value)
                select = ModeSelect(c, MODEL['properties'][3]['constraints'])
                self.assertEqual(select.current_option, raw)
                self.assertEqual(select.options, ['0','1','2'])
                self.assertEqual(select.extra_state_attributes['current_mode_label'], label)
                self.assertEqual(AigoEnumDescriptionSensor(c,'Mode').native_value, label)
                await select.async_select_option(raw)
                c.async_write.assert_awaited_once_with('Mode', int(raw))

    async def test_all_statuses_preserve_numeric_sensor_and_describe_tsl(self):
        for raw, label in {1:'Stand by',2:'Heating',3:'Cooling',4:'Keeping warm'}.items():
            for value in (raw, str(raw)):
                c = coordinator(status=value)
                original = AigoSensor(c,'status')
                self.assertEqual(original.native_value, value)
                self.assertEqual(original.extra_state_attributes['status_label'], label)
                self.assertEqual(AigoEnumDescriptionSensor(c,'status').native_value, label)

    async def test_other_model_definitions_override_known_numeric_mappings(self):
        model = deepcopy(MODEL)
        model['properties'][3]['constraints'] = {'0':'Tea profile','8':'Custom setting'}
        model['properties'][2]['constraints'] = {'1':'Descaling','7':'Custom status'}
        c = coordinator(model, Mode=0, status=1)
        self.assertEqual(AigoEnumDescriptionSensor(c,'Mode').native_value, 'Tea profile')
        self.assertEqual(AigoEnumDescriptionSensor(c,'status').native_value, 'Descaling')
        select = ModeSelect(c, model['properties'][3]['constraints'])
        self.assertEqual(select.options, ['0','8'])
        await select.async_select_option('8')
        c.async_write.assert_awaited_once_with('Mode',8)

    async def test_unknown_and_missing_enum_values_do_not_guess(self):
        for model in ({}, {'source':'telemetry-only'}, {'source':'live-tsl','properties':None}):
            self.assertEqual(enum_label(model,'Mode',0), 'Unknown (0)')
        for key in ('Mode','status'):
            self.assertEqual(enum_label(MODEL,key,99), 'Unknown (99)')
            for raw in (None,'unknown','unavailable','PRIVATE_EMAIL@example.test',True,{},1.5,10**1000):
                self.assertIsNone(enum_label(MODEL,key,raw))
        c = coordinator(Mode=99)
        self.assertIsNone(ModeSelect(c, {'0':'One-click boil'}).current_option)
        self.assertEqual(AigoEnumDescriptionSensor(c,'Mode').extra_state_attributes, {'raw_value':'99'})

    async def test_live_tsl_parser_retains_device_enum_descriptions(self):
        wire = {'properties':[{'identifier':r['identifier'], 'accessMode':'rw',
            'dataType':{'type':r['data_type'],'specs':r['constraints']}} for r in MODEL['properties']]}
        model = {'source':'live-tsl','properties':parse_model(wire)}
        self.assertEqual(enum_labels(model,'Mode'), MODEL['properties'][3]['constraints'])
        self.assertEqual(enum_labels(model,'status'), MODEL['properties'][2]['constraints'])

    async def test_sensitive_and_invalid_descriptions_are_not_exposed(self):
        for label in ('private@example.test','token SECRET_VALUE','https://private.test','x'*256,True,None):
            model=deepcopy(MODEL);model['properties'][3]['constraints']={'0':label}
            self.assertEqual(enum_labels(model,'Mode'), {})
            self.assertEqual(enum_label(model,'Mode',0),'Unknown (0)')

    async def test_stable_unique_ids_and_new_sensor_ids_are_distinct(self):
        c = coordinator(Mode=0,status=1)
        prefix = hashlib.sha256(b'fake').hexdigest()
        self.assertEqual(ModeSelect(c,{'0':'One-click boil'}).unique_id, f'{prefix}_ModeSelect_Mode')
        self.assertEqual(AigoSensor(c,'status').unique_id, f'{prefix}_AigoSensor_status')
        for key in ('Mode','status'):
            sensor=AigoEnumDescriptionSensor(c,key)
            self.assertEqual(sensor.unique_id, f'{prefix}_AigoEnumDescriptionSensor_{key}')
            self.assertEqual(sensor.translation_key, f'{key.lower()}_description')
            self.assertFalse(sensor.should_poll)
        c.async_write.assert_not_awaited()


class EnumRegistryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = flow_fixtures.ReconnectFlowTests.asyncSetUp
    asyncTearDown = flow_fixtures.ReconnectFlowTests.asyncTearDown

    async def test_description_sensors_do_not_replace_old_entities(self):
        c=coordinator(Mode=0,status=1)
        for domain, sensor in [('select',ModeSelect(c,{'0':'One-click boil'})), ('sensor',AigoSensor(c,'status'))]:
            old=self.entities.async_get_or_create(domain,'aigosmart',sensor.unique_id,
                config_entry=self.entry,device_id=self.device.id,suggested_object_id='custom_'+domain)
            self.entities.async_update_entity(old.entity_id,name='My label',area_id=self.area.id)
            same=self.entities.async_get_or_create(domain,'aigosmart',sensor.unique_id,
                config_entry=self.entry,device_id=self.device.id)
            self.assertEqual(same.id,old.id)
            self.assertEqual(same.entity_id,old.entity_id)
            self.assertEqual(same.area_id,self.area.id)
            self.assertEqual(same.name,'My label')
        for key in ('Mode','status'):
            sensor=AigoEnumDescriptionSensor(c,key)
            self.entities.async_get_or_create('sensor','aigosmart',sensor.unique_id,
                config_entry=self.entry,device_id=self.device.id)
        self.assertEqual(len(self.devices.devices),1)
        self.assertEqual(len(self.hass.config_entries.async_entries('aigosmart')),1)
        self.assertEqual(len(self.entities.entities),5)
