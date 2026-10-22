"""Offline planner and explicitly confirmed, single-use temperature test."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys
import warnings

if __package__:
    from . import kettle_readonly as kettle
else:
    import kettle_readonly as kettle

SET = "/thing/properties/set"
CONFIRM = "USTAW 80"


from custom_components.aigosmart.model import number, plan


class ControlledClient(kettle.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._write_device = None
        self.write_attempted = False

    def authorize_property_write(self, method, url, body):
        if method != 'POST' or url != kettle.IOT + SET:
            return False
        device_id = self._write_device
        self._write_device = None  # Consume permission even on an invalid attempt.
        if device_id is None or self.write_attempted:
            return False
        payload = json.loads(body)
        params = payload.get('params')
        if (not isinstance(params, dict) or set(params) != {'iotId', 'items'}
                or params['iotId'] != device_id
                or params['items'] != {'Target_temperature': 80}
                or type(params['items']['Target_temperature']) is not int):
            return False
        self.write_attempted = True  # A timeout also consumes the sole attempt.
        return True


def preflight(client, device):
    device_id = kettle.required(device, 'iotId')
    matches = [d for d in client.devices() if d.get('iotId') == device_id]
    # Alibaba binding status: 1 online, 0 offline. Unknown is never online.
    if (len(matches) != 1 or type(matches[0].get('status')) is not int
            or matches[0]['status'] != 1):
        raise ValueError('unavailable')
    properties = client.properties(device)
    for key, expected in [('HeatingSwitch', 0), ('status', 1), ('Target_temperature', 100)]:
        item = properties.get(key)
        value = item.get('value') if isinstance(item, dict) else None
        valid_type = type(value) is int or (key == 'HeatingSwitch' and type(value) is bool)
        if not valid_type or value != expected:
            raise ValueError('unsafe state')


def controlled_test(client, device, report, *, ask=input, emit=print):
    output = plan(report, 'Target_temperature', 80)
    if client.write_attempted:
        raise ValueError('already attempted')
    preflight(client, device)
    emit(json.dumps(output, indent=2, allow_nan=False))
    emit('Warunki: online, HeatingSwitch=0, status=1, Target_temperature=100. '
         'Jedyny zapis: Target_temperature=80°C.')
    if ask('Aby wykonać jeden zapis, wpisz dokładnie USTAW 80: ') != CONFIRM:
        emit('Anulowano. Nie wysłano zapisu.')
        return 0
    preflight(client, device)  # Refresh after potentially long human confirmation.
    client._write_device = kettle.required(device, 'iotId')
    try:
        client.signed(kettle.IOT, SET, {'iotId': client._write_device,
                                     'items': {'Target_temperature': 80}})
    except Exception:
        emit('Wynik próby zapisu niepotwierdzony. Brak ponowienia; nastąpi odczyt kontrolny.')
    finally:
        client._write_device = None
    try:
        properties = client.properties(device)
        value = properties.get('Target_temperature', {}).get('value')
        if type(value) is int and value == 80:
            emit('Zweryfikowano odczytem: Target_temperature=80°C. Zapis nie będzie ponawiany.')
            return 0
    except Exception:
        pass
    emit('Nie potwierdzono Target_temperature=80°C. Brak ponowienia; sprawdź stan ręcznie.')
    return 1


def live_main(args, report):
    client = ControlledClient(debug=args.debug)
    try:
        if not sys.stdin.isatty():
            raise ValueError('interactive terminal required')
        with warnings.catch_warnings():
            warnings.simplefilter('error', kettle.getpass.GetPassWarning)
            username = kettle.getpass.getpass('Konto AigoSmart (ukryte): ')
            password = kettle.getpass.getpass('Hasło: ')
        try:
            client.login(username, password, interactive=True)
        finally:
            del username, password
        devices = client.devices()
        for index, device in enumerate(devices, 1):
            name = str(device.get('deviceName') or device.get('productName') or 'Urządzenie')
            print(f'{index}: {ascii(name)}')
        index = int(input('Wybierz numer czajnika: '))
        if not 1 <= index <= len(devices):
            raise ValueError('invalid selection')
        return controlled_test(client, devices[index - 1], report)
    except (Exception, KeyboardInterrupt) as exc:
        if args.debug:
            print(f'[debug] local_exception={kettle.safe_exception(exc)}', file=sys.stderr)
        print('Test przerwany: błąd API, brak zgody lub niespełnione warunki bezpieczeństwa. '
              'Brak automatycznego ponowienia zapisu.')
        return 1
    finally:
        client._write_device = None
        client.token = None


def main():
    parser = argparse.ArgumentParser(description='Plan offline lub kontrolowany test 100 → 80°C.')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--dry-run', action='store_true', help='Offline, bez sieci.')
    modes.add_argument('--write', action='store_true', help='Odczyt online, dry-run i jawne potwierdzenie zapisu.')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--capabilities', type=Path, default=Path(__file__).resolve().parents[1] / 'reports/kettle_capabilities.json')
    parser.add_argument('identifier')
    parser.add_argument('value', help='JSON value, e.g. 80')
    args = parser.parse_args()
    try:
        report = json.loads(args.capabilities.read_text())
        value = json.loads(args.value)
        output = plan(report, args.identifier, value)
        if args.write:
            if args.identifier != 'Target_temperature' or type(value) is not int or value != 80:
                raise ValueError('Only Target_temperature=80 may be written')
            return live_main(args, report)
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError):
        print('Command rejected: invalid value or unconfirmed model constraints.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
