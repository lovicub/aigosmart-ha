"""Friendly enum descriptions from sanitized live TSL; never guess model mappings."""
import re
from .model import text


def enum_key(value):
    if type(value) is int:
        if not -10**20 < value < 10**20:
            return None
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r'-?\d{1,20}', value):
        return None
    return value


def enum_labels(model, identifier):
    if not isinstance(model, dict) or model.get('source') != 'live-tsl':
        return {}
    properties = model.get('properties')
    if not isinstance(properties, list):
        return {}
    rows = [row for row in properties
            if isinstance(row, dict) and row.get('identifier') == identifier and row.get('data_type') == 'enum']
    if len(rows) != 1 or not isinstance(rows[0].get('constraints'), dict):
        return {}
    result = {}
    for key, value in rows[0]['constraints'].items():
        key, label = enum_key(key), text(value)
        if key is not None and label and label != '[REDACTED]' and len(label) <= 255:
            result[key] = label
    return result


def enum_label(model, identifier, value):
    key = enum_key(value)
    if key is None:
        return None
    return enum_labels(model, identifier).get(key, f'Unknown ({key})')
