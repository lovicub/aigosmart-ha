"""Sensors and numbers declare device classes whose units Home Assistant accepts."""
import asyncio
import unittest
from unittest.mock import Mock

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.number.const import DEVICE_CLASS_UNITS as NUMBER_UNITS
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.sensor.const import DEVICE_CLASS_UNITS as SENSOR_UNITS

from custom_components.aigosmart.number import PreservationNumber, TemperatureNumber
from custom_components.aigosmart.sensor import AigoSensor, async_setup_entry

LIMITS = {'min': 40, 'max': 90, 'step': 5}


def coordinator():
    return Mock(device={'iotId': 'fake'}, data={}, last_update_success=True)


class DeviceClassTests(unittest.TestCase):
    def test_sensor_device_classes_and_units(self):
        expected = {'Target_temperature': SensorDeviceClass.TEMPERATURE, 'Time': SensorDeviceClass.DURATION,
                    'heatpreservation': SensorDeviceClass.DURATION, 'status': None}
        for key, device_class in expected.items():
            sensor = AigoSensor(coordinator(), key)
            self.assertEqual(sensor.device_class, device_class, key)
            if device_class:
                self.assertIn(sensor.native_unit_of_measurement, SENSOR_UNITS[device_class], key)

    def test_number_device_classes_and_units(self):
        for number, device_class in ((TemperatureNumber(coordinator(), LIMITS), NumberDeviceClass.TEMPERATURE),
                                     (PreservationNumber(coordinator(), LIMITS), NumberDeviceClass.DURATION)):
            self.assertEqual(number.device_class, device_class)
            self.assertIn(number.native_unit_of_measurement, NUMBER_UNITS[device_class])


class WaterTemperatureTests(unittest.TestCase):
    def setup_keys(self, *properties):
        entry = Mock(runtime_data=Mock(device={'iotId': 'fake'}, data={},
                                       model={'properties': list(properties)}))
        add = Mock()
        asyncio.run(async_setup_entry(None, entry, add))
        return [entity.key for entity in add.call_args.args[0] if type(entity) is AigoSensor]

    def test_sensor_exists_only_when_the_tsl_declares_a_numeric_temperature(self):
        for data_type in ('int', 'float', 'double'):
            row = {'identifier': 'temperature', 'data_type': data_type}
            self.assertIn('temperature', self.setup_keys(row), data_type)
        for row in ({'identifier': 'temperature', 'data_type': 'enum'},
                    {'identifier': 'temperature', 'data_type': 'text'},
                    {'identifier': 'Target_temperature', 'data_type': 'int'}):
            self.assertNotIn('temperature', self.setup_keys(row), row)

    def test_water_temperature_is_a_measurement_in_celsius(self):
        sensor = AigoSensor(coordinator(), 'temperature')
        self.assertEqual(sensor.translation_key, 'water_temperature')
        self.assertEqual(sensor.device_class, SensorDeviceClass.TEMPERATURE)
        self.assertEqual(sensor.state_class, SensorStateClass.MEASUREMENT)
        self.assertEqual(sensor.native_unit_of_measurement, '°C')
        self.assertIsNone(AigoSensor(coordinator(), 'Target_temperature').state_class)
