"""Entity names come from translations, with the raw key as the fallback."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from custom_components.aigosmart.button import AigoRefreshTokenButton
from custom_components.aigosmart.entity import AigoEntity
from custom_components.aigosmart.sensor import AigoEnumDescriptionSensor, AigoSensor

STRINGS = json.loads(Path('custom_components/aigosmart/strings.json').read_text(encoding='utf-8'))


def coordinator():
    return Mock(device={'iotId': 'fake'}, data={}, last_update_success=True)


class EntityNameTests(unittest.TestCase):
    def test_translation_key_leaves_the_name_to_home_assistant(self):
        entity = AigoEntity(coordinator(), 'status', translation_key='status_description')
        self.assertEqual(entity.translation_key, 'status_description')
        # Home Assistant only consults the translation when no `_attr_name` exists.
        self.assertFalse(hasattr(entity, '_attr_name'))

    def test_without_translation_key_the_raw_key_is_the_name(self):
        entity = AigoEntity(coordinator(), 'Target_temperature')
        self.assertIsNone(entity.translation_key)
        self.assertEqual(entity.name, 'Target_temperature')

    def test_description_sensors_and_button_are_translated(self):
        cases = [('sensor', AigoEnumDescriptionSensor(coordinator(), key)) for key in ('Mode', 'status')]
        cases.append(('button', AigoRefreshTokenButton(coordinator())))
        for platform, entity in cases:
            self.assertFalse(hasattr(entity, '_attr_name'))
            self.assertIn('name', STRINGS['entity'][platform][entity.translation_key])

    def test_untranslated_sensor_and_unique_ids_are_unchanged(self):
        sensor = AigoSensor(coordinator(), 'status')
        self.assertEqual(sensor.name, 'status')
        prefix = hashlib.sha256(b'fake').hexdigest()
        self.assertEqual(sensor.unique_id, f'{prefix}_AigoSensor_status')
        self.assertEqual(AigoEnumDescriptionSensor(coordinator(), 'Mode').unique_id,
                         f'{prefix}_AigoEnumDescriptionSensor_Mode')
