"""Read model metadata only; never infer write access from telemetry."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import json
from pathlib import Path
import re

if __package__:
    from . import kettle_readonly as k
else:
    import kettle_readonly as k

REPORT = Path(__file__).resolve().parents[1] / 'reports/kettle_capabilities.json'
FOCUS = ('HeatingSwitch', 'Target_temperature', 'heatpreservation', 'Mode', 'Time', 'status')
SOURCES = ['https://help.aliyun.com/document_detail/177847.html',
           'https://help.aliyun.com/zh/document_detail/129777.html']


from custom_components.aigosmart.model import text, specs, parse_model


def build_report(rows=None):
    return {'mode': 'read-only', 'source': 'live-tsl' if rows is not None else 'pending-live-tsl',
            'schema_version': 1, 'sources': SOURCES,
            'notes': ['TSL access is a declaration, not a tested firmware behavior.',
                      'No control commands were sent. Missing metadata stays unknown.'],
            'properties': rows if rows is not None else [
                {'identifier': key, 'evidence': 'telemetry-only', 'data_type': None,
                 'access': None, 'constraints': None, 'name': None, 'description': None}
                for key in FOCUS],
            'missing_focus': [key for key in FOCUS if rows is not None and
                              key not in {r['identifier'] for r in rows}]}


def fetch(client, device):
    return build_report(parse_model(client.signed(
        k.IOT, k.TSL, {'iotId': k.required(device, 'iotId')}, '1.0.4')['data']))


def main():
    parser = argparse.ArgumentParser(description='Read kettle TSL metadata without control commands.')
    parser.add_argument('--read-only', action='store_true', required=True)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    client = k.Client(debug=args.debug)
    try:
        username = k.getpass.getpass('Konto AigoSmart (ukryte): ')
        password = k.getpass.getpass('Hasło: ')
        try:
            client.login(username, password, interactive=True)
        finally:
            del username, password
        devices = client.devices()
        for index, device in enumerate(devices, 1):
            print(f'{index}: {ascii(str(device.get("productName") or "Urządzenie"))}')
        index = int(input('Wybierz numer czajnika: '))
        if not 1 <= index <= len(devices):
            raise ValueError('Invalid selection')
        report = fetch(client, devices[index - 1])
        encoded = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(encoded, encoding='utf-8')
        print('Zapisano reports/kettle_capabilities.json')
        return 0
    except (Exception, KeyboardInterrupt):
        print('Odczyt TSL przerwany lub odrzucony. Nie zapisano nowego raportu.')
        return 1
    finally:
        client.token = None


if __name__ == '__main__':
    raise SystemExit(main())
