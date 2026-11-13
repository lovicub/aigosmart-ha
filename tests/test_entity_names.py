"""Entity names come from translations, with the raw key as the fallback."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from custom_components.aigosmart.button import AigoRefreshTokenButton
from custom_components.aigosmart.binary_sensor import HeatingSensor
from custom_components.aigosmart.diagnostic_state import SENSOR_NAMES
from custom_components.aigosmart.entity import PROPERTY_TRANSLATION_KEYS, AigoEntity
from custom_components.aigosmart.number import PreservationNumber, TemperatureNumber
from custom_components.aigosmart.select import ModeSelect
from custom_components.aigosmart.sensor import AigoEnumDescriptionSensor, AigoSensor, AigoSessionSensor
from custom_components.aigosmart.switch import HeatingSwitch

COMPONENT = Path('custom_components/aigosmart')
STRINGS = json.loads((COMPONENT / 'strings.json').read_text(encoding='utf-8'))
LANGUAGES = {path.stem: json.loads(path.read_text(encoding='utf-8'))
             for path in (COMPONENT / 'translations').glob('*.json')}
LIMITS = {'min': 40, 'max': 90, 'step': 5}


def coordinator_with_model():
    c = coordinator()
    c.model = {'properties': []}
    return c


def coordinator():
    return Mock(device={'iotId': 'fake'}, data={}, last_update_success=True)


class EntityNameTests(unittest.TestCase):
    def test_translation_key_leaves_the_name_to_home_assistant(self):
        entity = AigoEntity(coordinator(), 'status', translation_key='status_description')
        self.assertEqual(entity.translation_key, 'status_description')
        # Home Assistant only consults the translation when no `_attr_name` exists.
        self.assertFalse(hasattr(entity, '_attr_name'))

    def test_without_translation_key_the_raw_key_is_the_name(self):
        entity = AigoEntity(coordinator(), 'SomeNewProperty')
        self.assertIsNone(entity.translation_key)
        self.assertEqual(entity.name, 'SomeNewProperty')

    def test_description_sensors_and_button_are_translated(self):
        cases = [('sensor', AigoEnumDescriptionSensor(coordinator(), key)) for key in ('Mode', 'status')]
        cases.append(('button', AigoRefreshTokenButton(coordinator())))
        for platform, entity in cases:
            self.assertFalse(hasattr(entity, '_attr_name'))
            self.assertIn('name', STRINGS['entity'][platform][entity.translation_key])

    def test_untranslated_sensor_and_unique_ids_are_unchanged(self):
        sensor = AigoSensor(coordinator(), 'status')
        self.assertEqual(sensor.translation_key, 'status')
        prefix = hashlib.sha256(b'fake').hexdigest()
        self.assertEqual(sensor.unique_id, f'{prefix}_AigoSensor_status')
        self.assertEqual(AigoEnumDescriptionSensor(coordinator(), 'Mode').unique_id,
                         f'{prefix}_AigoEnumDescriptionSensor_Mode')


class PropertyNameTests(unittest.TestCase):
    def entities(self):
        c = coordinator()
        c.model = {'properties': []}
        entities = [('sensor', AigoSensor(c, key)) for key in ('status', 'Target_temperature', 'Time', 'heatpreservation')]
        entities += [('sensor', AigoSessionSensor(c, key)) for key in SENSOR_NAMES]
        entities += [('number', TemperatureNumber(c, LIMITS)), ('number', PreservationNumber(c, LIMITS)),
                     ('binary_sensor', HeatingSensor(c, 'HeatingSwitch')), ('switch', HeatingSwitch(c, 'HeatingSwitch')),
                     ('select', ModeSelect(c, {'0': 'One-click boil'}))]
        return entities

    def test_property_and_session_entities_use_their_translation(self):
        for platform, entity in self.entities():
            if platform == 'select':
                continue  # unknown mode labels keep the plain name, see below
            self.assertTrue(entity.translation_key, entity.unique_id)
            self.assertFalse(hasattr(entity, '_attr_name'), entity.unique_id)
            for language in (STRINGS, *LANGUAGES.values()):
                self.assertIn('name', language['entity'][platform][entity.translation_key], entity.unique_id)

    def test_session_names_match_the_english_strings(self):
        for key, name in SENSOR_NAMES.items():
            self.assertEqual(STRINGS['entity']['sensor'][key]['name'], name)

    def test_mapped_keys_exist_for_the_platforms_that_use_them(self):
        for key, translation_key in PROPERTY_TRANSLATION_KEYS.items():
            self.assertTrue(any(translation_key in STRINGS['entity'][p] for p in STRINGS['entity']), key)

    def test_unknown_mode_labels_keep_the_plain_name(self):
        select = ModeSelect(coordinator_with_model(), {'0': 'Something else'})
        self.assertIsNone(select.translation_key)
        self.assertEqual(select.name, 'Mode')

    def test_all_languages_define_the_same_entity_names(self):
        def names(entity):
            return {(p, k): sorted(v) for p, group in entity.items() for k, v in group.items()}

        def keys(node, path=()):
            if not isinstance(node, dict):
                return {path}
            return {leaf for key, child in node.items() for leaf in keys(child, path + (key,))}
        for code, language in LANGUAGES.items():
            self.assertEqual(keys(language), keys(STRINGS), code)
        for code, language in LANGUAGES.items():
            self.assertEqual(names(language['entity']), names(STRINGS['entity']), code)
        self.assertEqual(LANGUAGES['en'], STRINGS)
