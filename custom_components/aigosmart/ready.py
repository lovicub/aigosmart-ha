"""Derived "water ready" logic.

The kettle's TSL has no "boil finished" or "ready" event, only the generic
property report. Readiness is therefore derived from the status, mode, water
temperature and target temperature of every update. This module is pure logic
without Home Assistant imports, so it can be tested offline with an injected
clock.

Observed behaviour (model 300104UTV, cloud control):
- Mode 0 "One-click boil" heats to the target temperature, then HeatingSwitch
  becomes 0 and the status becomes 1 (Stand by).
- Mode 2 "Heating and keep warm" heats to the target, then the status is 3
  (Cooling, above the target) or 4 (Keeping warm); `Time` is the remaining
  keep-warm time in minutes.
- Mode 1 "Boil and keep warm" boils first, then keeps warm at the target.
- When heating is switched off the device resets Mode and heatpreservation to 0,
  so the mode of the running cycle is remembered while HeatingSwitch is on.
- Cloud polling is coarse and the water overshoots, so readings are compared
  with a tolerance instead of exact equality.
"""
import time

TOLERANCE = 5        # °C around the target temperature
BOILING = 95         # °C at which mode 1 counts as boiled
END_GRACE = 20       # s to wait before a stop below target counts as interrupted
MIN_KEEP_WARM = 300  # s of keeping warm before its end is worth an event

REQUIRED_PROPERTIES = frozenset({'status', 'temperature', 'Target_temperature', 'HeatingSwitch'})

STATUS_STANDBY, STATUS_HEATING, STATUS_COOLING, STATUS_KEEPING_WARM = 1, 2, 3, 4
KEEP_WARM_STATES = (STATUS_COOLING, STATUS_KEEPING_WARM)

EVENT_READY = 'ready'
EVENT_INTERRUPTED = 'interrupted'
EVENT_KEEP_WARM_FINISHED = 'keep_warm_finished'
EVENT_TYPES = [EVENT_READY, EVENT_INTERRUPTED, EVENT_KEEP_WARM_FINISHED]


def supported(model):
    """True when the TSL declares everything the derivation needs."""
    return REQUIRED_PROPERTIES <= {row['identifier'] for row in (model or {}).get('properties', [])}


def _value(data, key):
    item = (data or {}).get(key)
    value = item.get('value') if isinstance(item, dict) else None
    return value if type(value) in (int, float) else None


class _Cycle:
    """One heating cycle, from switching on until it is over."""

    def __init__(self):
        self.mode = None
        self.ready_fired = False
        self.boiled = False
        self.keep_warm_since = None
        self.stopped_since = None


class ReadyTracker:
    def __init__(self, tolerance=TOLERANCE, clock=time.monotonic):
        self.tolerance = tolerance
        self.ready = False
        self._clock = clock
        self._cycle = None
        self._last = None

    def _is_ready(self, cycle, status, temp, target):
        if temp is None or target is None:
            return False
        if cycle.mode == 1:
            # After boiling, ready once the water has cooled down to the target.
            return cycle.boiled and status in KEEP_WARM_STATES and temp <= target + self.tolerance
        if cycle.mode == 2:
            return status in KEEP_WARM_STATES and temp >= target - self.tolerance
        # Mode 0 and unknown modes: heating has finished and the target is reached.
        return status != STATUS_HEATING and temp >= target - self.tolerance

    def process(self, data):
        """Return the (event_type, attributes) pairs produced by this update."""
        switch, status = _value(data, 'HeatingSwitch'), _value(data, 'status')
        mode, temp = _value(data, 'Mode'), _value(data, 'temperature')
        target, remaining = _value(data, 'Target_temperature'), _value(data, 'Time')
        snapshot = (switch, status, mode, temp, target, remaining)
        waiting = self._cycle is not None and self._cycle.stopped_since is not None
        if snapshot == self._last and not waiting:
            return []  # Listeners are also notified about changes that are not new data.
        self._last = snapshot

        if self._cycle is None and (switch == 1 or status == STATUS_HEATING):
            self._cycle = _Cycle()
            self.ready = False
        events = self._advance(switch, status, mode, temp, target, remaining) if self._cycle else []
        if self.ready and (temp is None or target is None or temp < target - self.tolerance):
            self.ready = False
        return events

    def _advance(self, switch, status, mode, temp, target, remaining):
        cycle, now, events = self._cycle, self._clock(), []
        if switch == 1 and mode is not None:
            cycle.mode = int(mode)
        if temp is not None and temp >= BOILING:
            cycle.boiled = True
        if status in KEEP_WARM_STATES and cycle.keep_warm_since is None:
            cycle.keep_warm_since = now
        attributes = {'temperature': temp, 'target_temperature': target, 'mode': cycle.mode}

        if not cycle.ready_fired and self._is_ready(cycle, status, temp, target):
            cycle.ready_fired = True
            self.ready = True
            events.append((EVENT_READY, attributes))

        if switch == 0 and status == STATUS_STANDBY:
            if cycle.ready_fired:
                kept_warm = cycle.keep_warm_since is not None and now - cycle.keep_warm_since >= MIN_KEEP_WARM
                if kept_warm and remaining in (0, None):
                    events.append((EVENT_KEEP_WARM_FINISHED, attributes))
                self._cycle = None
            elif cycle.stopped_since is None:
                cycle.stopped_since = now
            elif now - cycle.stopped_since >= END_GRACE:
                events.append((EVENT_INTERRUPTED, attributes))
                self._cycle = None
        else:
            cycle.stopped_since = None
        return events
