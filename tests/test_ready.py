"""Derived water-ready events, with an injected clock."""
import unittest

from custom_components.aigosmart.ready import (
    END_GRACE, MIN_KEEP_WARM, EVENT_INTERRUPTED, EVENT_KEEP_WARM_FINISHED, EVENT_READY,
    ReadyTracker, supported)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def data(switch=None, status=None, mode=None, temp=None, target=None, time=None):
    values = {'HeatingSwitch': switch, 'status': status, 'Mode': mode,
              'temperature': temp, 'Target_temperature': target, 'Time': time}
    return {key: {'value': value} for key, value in values.items() if value is not None}


class ReadyTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.tracker = ReadyTracker(clock=self.clock)

    def feed(self, *args, after=0, **kwargs):
        self.clock.now += after
        return [event for event, _ in self.tracker.process(data(*args, **kwargs))]

    def test_mode_0_is_ready_when_heating_stops_near_the_target(self):
        self.assertEqual(self.feed(1, 2, 0, 20, 70), [])
        self.assertEqual(self.feed(1, 2, 0, 66, 70, after=15), [])  # still heating
        self.assertEqual(self.feed(0, 1, 0, 66, 70, after=15), [EVENT_READY])
        self.assertTrue(self.tracker.ready)
        self.assertEqual(self.feed(0, 1, 0, 66, 70, after=15), [])

    def test_ready_event_carries_the_cycle_values(self):
        self.tracker.process(data(1, 2, 0, 20, 70))
        events = self.tracker.process(data(0, 1, 0, 68, 70))
        self.assertEqual(events, [(EVENT_READY, {'temperature': 68, 'target_temperature': 70, 'mode': 0})])

    def test_mode_0_with_water_already_hot(self):
        self.assertEqual(self.feed(1, 1, 0, 65, 40), [EVENT_READY])

    def test_stop_below_the_target_is_interrupted_after_the_grace_period(self):
        self.feed(1, 2, 0, 30, 70)
        self.assertEqual(self.feed(0, 1, 0, 50, 70, after=5), [])
        # Identical repeated snapshots still advance the grace period.
        self.assertEqual(self.feed(0, 1, 0, 50, 70, after=END_GRACE - 10), [])
        self.assertEqual(self.feed(0, 1, 0, 50, 70, after=10), [EVENT_INTERRUPTED])
        self.assertFalse(self.tracker.ready)
        self.assertEqual(self.feed(0, 1, 0, 50, 70, after=60), [])

    def test_overshoot_after_a_stop_is_not_an_interruption(self):
        self.feed(1, 2, 0, 30, 70)
        self.assertEqual(self.feed(0, 1, 0, 60, 70, after=5), [])
        self.assertEqual(self.feed(0, 1, 0, 66, 70, after=10), [EVENT_READY])
        self.assertEqual(self.feed(0, 1, 0, 66, 70, after=60), [])

    def test_mode_2_is_ready_when_it_starts_keeping_warm(self):
        self.assertEqual(self.feed(1, 2, 2, 60, 70), [])
        self.assertEqual(self.feed(1, 2, 2, 72, 70, after=15), [])  # keeps heating
        self.assertEqual(self.feed(1, 3, 2, 72, 70, after=15, time=60), [EVENT_READY])
        self.assertEqual(self.feed(1, 4, 2, 71, 70, after=15, time=60), [])

    def test_switching_off_while_keeping_warm_has_no_finished_event(self):
        self.feed(1, 2, 2, 60, 70)
        self.feed(1, 3, 2, 72, 70, after=15, time=60)
        # The device resets Mode when it is switched off.
        self.assertEqual(self.feed(0, 1, 0, 71, 70, after=MIN_KEEP_WARM + 30, time=55), [])

    def test_natural_end_of_a_long_keep_warm_is_reported(self):
        self.feed(1, 2, 2, 60, 70)
        self.feed(1, 3, 2, 72, 70, after=15, time=5)
        self.feed(1, 4, 2, 70, 70, after=MIN_KEEP_WARM, time=1)
        self.assertEqual(self.feed(0, 1, 0, 69, 70, after=60, time=0), [EVENT_KEEP_WARM_FINISHED])
        self.assertEqual(self.feed(0, 1, 0, 69, 70, after=60, time=0), [])

    def test_a_very_short_keep_warm_is_not_reported(self):
        self.feed(1, 2, 2, 60, 70)
        self.feed(1, 3, 2, 72, 70, after=15, time=0)
        self.assertEqual(self.feed(0, 1, 0, 72, 70, after=30, time=0), [])

    def test_mode_1_is_ready_after_boiling_once_cooled_to_the_target(self):
        self.assertEqual(self.feed(1, 2, 1, 40, 70), [])
        self.assertEqual(self.feed(1, 3, 1, 90, 70, after=15), [])  # not boiled yet
        self.assertEqual(self.feed(1, 2, 1, 96, 70, after=15), [])
        self.assertEqual(self.feed(1, 3, 1, 80, 70, after=15), [])  # still too hot
        self.assertEqual(self.feed(1, 4, 1, 74, 70, after=15), [EVENT_READY])

    def test_ready_flag_drops_when_the_water_cools_down(self):
        self.feed(1, 1, 0, 70, 70)
        self.assertTrue(self.tracker.ready)
        self.feed(0, 1, 0, 66, 70, after=60)
        self.assertTrue(self.tracker.ready)
        self.feed(0, 1, 0, 64, 70, after=60)
        self.assertFalse(self.tracker.ready)

    def test_a_new_cycle_starts_from_scratch(self):
        self.feed(1, 1, 0, 70, 70)
        self.feed(0, 1, 0, 70, 70, after=15)
        self.assertEqual(self.feed(1, 2, 0, 70, 90, after=15), [])
        self.assertFalse(self.tracker.ready)
        self.assertEqual(self.feed(0, 1, 0, 88, 90, after=15), [EVENT_READY])

    def test_missing_or_invalid_values_never_produce_events(self):
        for values in ({}, None, {'status': {'value': 'x'}}, {'status': 5}):
            self.assertEqual(self.tracker.process(values), [])
        self.assertEqual(self.feed(1, 2, 0, None, 70), [])
        self.assertEqual(self.feed(0, 1, 0, None, 70, after=60), [])
        self.assertFalse(self.tracker.ready)

    def test_supported_needs_the_four_properties(self):
        def model(*names):
            return {'properties': [{'identifier': name} for name in names]}
        needed = ('status', 'temperature', 'Target_temperature', 'HeatingSwitch')
        self.assertTrue(supported(model(*needed, 'Mode')))
        for missing in needed:
            self.assertFalse(supported(model(*(n for n in needed if n != missing))))
        self.assertFalse(supported(None))
        self.assertFalse(supported({}))
