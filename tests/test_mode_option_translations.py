"""Native Mode labels retain raw select/service keys and require matching TSL."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import translation
from custom_components.aigosmart.select import ModeSelect
import test_enum_labels as enums
import test_reconnect_flow as flows
from test_session_refresh import setUpModule

ROOT = Path('custom_components/aigosmart')


class ModeTranslationTests(unittest.IsolatedAsyncioTestCase):
    async def test_known_modes_keep_numeric_state_options_and_old_services(self):
        for key in ('0','1','2'):
            c=enums.coordinator(Mode=int(key))
            select=ModeSelect(c,enums.MODEL['properties'][3]['constraints'])
            self.assertEqual(select.translation_key,'mode')
            self.assertEqual(select.current_option,key)
            self.assertEqual(select.options,['0','1','2'])
            self.assertEqual(select.extra_state_attributes['mode_labels'],enums.MODEL['properties'][3]['constraints'])
            self.assertEqual(select.extra_state_attributes['current_mode_label'],enums.MODEL['properties'][3]['constraints'][key])
            await select.async_select_option(key)
            c.async_write.assert_awaited_once_with('Mode',int(key))

    async def test_model_mismatch_unknown_missing_or_subset_never_get_fixed_labels(self):
        for choices in ({'0':'Tea profile','1':'Boil and keep warm','2':'Heating and keep warm'},
                        {'0':'One-click boil','1':'Boil and keep warm'},
                        {'0':'One-click boil','1':'Boil and keep warm','2':'Heating and keep warm','9':'Other mode'},
                        {'9':'Other mode'},{}):
            model=deepcopy(enums.MODEL);model['properties'][3]['constraints']=choices
            c=enums.coordinator(model,Mode=9)
            select=ModeSelect(c,choices)
            self.assertIsNone(select.translation_key)
            self.assertEqual(select.options,list(choices))
            self.assertEqual(select.extra_state_attributes['mode_labels'],choices)
            if '9' in choices:
                await select.async_select_option('9')
                c.async_write.assert_awaited_once_with('Mode',9)
        select=ModeSelect(enums.coordinator({},Mode=0),enums.MODEL['properties'][3]['constraints'])
        self.assertIsNone(select.translation_key)

    async def test_choices_must_match_the_live_model(self):
        c=enums.coordinator(Mode=0)
        select=ModeSelect(c,{'0':'Different','1':'Boil and keep warm','2':'Heating and keep warm'})
        self.assertIsNone(select.translation_key)
        c.async_write.assert_not_awaited()

    async def test_case_spacing_and_hyphen_variants_preserve_known_meanings(self):
        model=deepcopy(enums.MODEL)
        choices={'0':' ONE CLICK BOIL ','1':'Boil  and keep warm','2':'heating and keep warm'}
        model['properties'][3]['constraints']=choices
        self.assertEqual(ModeSelect(enums.coordinator(model,Mode=0),choices).translation_key,'mode')


class TranslationLoaderTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = flows.ReconnectFlowTests.asyncSetUp
    asyncTearDown = flows.ReconnectFlowTests.asyncTearDown

    async def test_core_loader_and_translate_state_accept_numeric_keys(self):
        self.hass.config.components.add('aigosmart')
        integration=SimpleNamespace(file_path=ROOT.resolve(),has_translations=True,name='AigoSmart HA')
        with patch('homeassistant.helpers.translation.async_get_integrations',new=AsyncMock(return_value={'aigosmart':integration})):
            for language in ('en','de','pl'):
                resources=await translation.async_get_translations(self.hass,language,'entity',{'aigosmart'})
                expected=json.loads((ROOT/'translations'/f'{language}.json').read_text())['entity']['select']['mode']['state']
                for raw,label in expected.items():
                    self.assertEqual(resources[f'component.aigosmart.entity.select.mode.state.{raw}'],label)
                    self.hass.config.language=language
                    self.assertEqual(translation.async_translate_state(self.hass,raw,'select','aigosmart','mode',None),label)

    async def test_registry_metadata_updates_in_place_and_can_disable_translation(self):
        select=ModeSelect(enums.coordinator(Mode=0),enums.MODEL['properties'][3]['constraints'])
        old=self.entities.async_get_or_create('select','aigosmart',select.unique_id,
            config_entry=self.entry,device_id=self.device.id,suggested_object_id='custom_mode',translation_key=None)
        self.entities.async_update_entity(old.entity_id,name='My mode',area_id=self.area.id)
        same=self.entities.async_get_or_create('select','aigosmart',select.unique_id,
            config_entry=self.entry,device_id=self.device.id,translation_key=select.translation_key)
        self.assertEqual(same.entity_id,old.entity_id)
        self.assertEqual(same.id,old.id)
        self.assertEqual(same.unique_id,old.unique_id)
        self.assertEqual(same.name,'My mode')
        self.assertEqual(same.area_id,self.area.id)
        self.assertEqual(same.translation_key,'mode')
        same=self.entities.async_get_or_create('select','aigosmart',select.unique_id,
            config_entry=self.entry,device_id=self.device.id,translation_key=None)
        self.assertIsNone(same.translation_key)
        self.assertEqual(same.id,old.id)
