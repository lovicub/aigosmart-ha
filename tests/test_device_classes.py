"""Sensors and numbers declare device classes whose units Home Assistant accepts."""
import unittest
from unittest.mock import Mock

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.number.const import DEVICE_CLASS_UNITS as NUMBER_UNITS
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor.const import DEVICE_CLASS_UNITS as SENSOR_UNITS

from custom_components.aigosmart.number import PreservationNumber, TemperatureNumber
from custom_components.aigosmart.sensor import AigoSensor

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
