import json
import re
from decimal import Decimal, InvalidOperation
def text(value):
    # Only model fields survive; profile, link, account and transport data never do.
    if not isinstance(value, str):
        return None
    if len(value) > 256 or re.search(r'token|secret|password|@|https?://|[A-Za-z0-9+/=_-]{32,}', value, re.I):
        return '[REDACTED]'
    return value


def specs(value):
    if not isinstance(value, dict):
        return None
    result = {}
    for key, val in value.items():
        if key in {'min', 'max', 'step', 'unit', 'unitName', 'length'} or re.fullmatch(r'-?\d+', key):
            if type(val) in (int, float, bool):
                result[key] = val
            elif isinstance(val, str):
                result[key] = text(val)
    return result


def parse_model(data):
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict) or not isinstance(data.get('properties'), list):
        raise ValueError('Invalid TSL properties')
    rows, seen = [], set()
    for prop in data['properties']:
        if not isinstance(prop, dict):
            raise ValueError('Invalid property')
        ident = prop.get('identifier')
        if (not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', ident)
                or re.search(r'token|secret|password|email|ssid|address', ident, re.I) or ident in seen):
            raise ValueError('Invalid or duplicate identifier')
        seen.add(ident)
        dtype = prop.get('dataType', {})
        if not isinstance(dtype, dict):
            raise ValueError('Invalid data type')
        kind = dtype.get('type')
        mode = prop.get('accessMode')
        rows.append({'identifier': ident, 'evidence': 'tsl',
                     'data_type': kind if kind in {'int', 'float', 'double', 'bool', 'enum', 'text', 'date', 'array', 'struct'} else None,
                     'access': {'r': 'read-only', 'rw': 'read-write', 'w': 'write-only'}.get(mode),
                     'constraints': specs(dtype.get('specs')),
                     'name': text(prop.get('name')), 'description': text(prop.get('desc'))})
    return rows


def number(value):
    if type(value) not in (int, float, str):
        raise ValueError('Invalid number')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Invalid number') from None
    if not result.is_finite():
        raise ValueError('Non-finite number')
    return result


def plan(report, identifier, value):
    if report.get('source') != 'live-tsl':
        raise ValueError('Live TSL metadata required')
    matches = [r for r in report['properties'] if r['identifier'] == identifier]
    if len(matches) != 1 or matches[0].get('evidence') != 'tsl':
        raise ValueError('Unknown property')
    row = matches[0]
    if row.get('access') != 'read-write':
        raise ValueError('Property is not read-write')
    kind, limits = row.get('data_type'), row.get('constraints')
    if not isinstance(limits, dict):
        raise ValueError('Missing constraints')
    if kind in {'bool', 'enum'}:
        if type(value) is not int or str(value) not in limits:
            raise ValueError('Value outside declared enumeration')
    elif kind in {'int', 'float', 'double'}:
        if type(value) not in (int, float) or (kind == 'int' and type(value) is not int):
            raise ValueError('Incorrect numeric type')
        n = number(value)
        if not {'min', 'max', 'step'} <= limits.keys():
            raise ValueError('Incomplete numeric constraints')
        low, high, step = (number(limits[key]) for key in ('min', 'max', 'step'))
        if low > high or step <= 0 or not low <= n <= high or (n - low) % step:
            raise ValueError('Value outside range or step')
    else:
        raise ValueError('Unsupported property type')
    return {'mode': 'dry-run', 'executed': False, 'method': 'POST',
            'path': '/thing/properties/set', 'api_version': '1.0.0',
            'params': {'iotId': '<selected-device>', 'items': {identifier: value}}}
