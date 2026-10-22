"""Read-only polling monitor. Reuses the existing in-memory IoT session."""
import argparse
from datetime import datetime, timezone
import json
import math
import sys
import time

if __package__:
    from . import kettle_readonly as kettle
else:
    import kettle_readonly as kettle


def interval_seconds(text):
    value = float(text)
    if not math.isfinite(value) or value < 1:
        raise argparse.ArgumentTypeError('Interwał musi być skończoną liczbą >= 1 s.')
    return value


def snapshot(properties):
    # Keep the same terminal/secret redaction policy as the existing reader.
    return {row['property']: row['value'] for row in kettle.anonymize(properties)}


def changes(previous, current):
    if previous is None:
        return {'initial': True}
    return {key: {'before': previous.get(key), 'after': current.get(key),
                  'kind': 'added' if key not in previous else
                          'removed' if key not in current else 'changed'}
            for key in sorted(previous.keys() | current.keys())
            if key not in previous or key not in current or
            type(previous[key]) is not type(current[key]) or previous[key] != current[key]}


def monitor(client, device, interval=10, *, sleep=time.sleep, emit=print,
            now=lambda: datetime.now(timezone.utc).isoformat(timespec='seconds')):
    previous = None
    failures = 0
    while True:
        try:
            current = snapshot(client.properties(device))
        except kettle.APIError as exc:
            if exc.status in (401, 403) or exc.code in {
                    '401', '403', 'invalid_grant', 'access_denied',
                    'UC/NEED_SECURITY_CODE'}:
                emit('Utrata autoryzacji. Monitor zatrzymany; zaloguj się ponownie ręcznie.')
                return 1
            if exc.status == 429 or exc.code in {'429', 'SENDCODE_INTERVAL_IS_TOO_SHORT'}:
                emit('Limit API. Monitor zatrzymany; odczekaj przed ręcznym uruchomieniem.')
                return 1
            if (exc.exception not in {'URLError', 'TimeoutError', 'OSError'} and
                    exc.status not in (500, 502, 503, 504) and
                    exc.code not in {'500', '502', '503'}):
                emit('API odrzuciło odczyt lub zwróciło nieprawidłowe dane. Monitor zatrzymany.')
                return 1
            failures = min(failures + 1, 5)
            delay = max(interval, min(300, 30 * 2 ** (failures - 1)))
            emit(f'Błąd sieci lub niedostępność API. Kolejny odczyt za {delay:g} s.')
            sleep(delay)
            continue
        failures = 0
        emit(json.dumps({'time': now(), 'properties': current,
                         'changes': changes(previous, current)},
                        ensure_ascii=False, allow_nan=False), flush=True)
        previous = current
        # Wait after completion: slow requests never cause catch-up bursts.
        sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='Monitor AigoSmart: cykliczny odczyt bez sterowania.')
    parser.add_argument('--read-only', action='store_true', required=True)
    parser.add_argument('--interval', type=interval_seconds, default=10,
                        help='Przerwa między odczytami w sekundach (>=1; domyślnie 10).')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    client = kettle.Client(debug=args.debug)
    try:
        username = kettle.getpass.getpass('Konto AigoSmart (ukryte): ')
        password = kettle.getpass.getpass('Hasło: ')
        try:
            client.login(username, password, interactive=True)
        finally:
            del username, password
        devices = client.devices()
        if not devices:
            raise kettle.APIError('Brak urządzeń.')
        for index, device in enumerate(devices, 1):
            name = str(device.get('deviceName') or device.get('productName') or 'Urządzenie')
            print(f'{index}: {ascii(name)}')
        index = int(input('Wybierz numer czajnika: '))
        if not 1 <= index <= len(devices):
            raise ValueError
        return monitor(client, devices[index - 1], args.interval)
    except KeyboardInterrupt:
        print('\nMonitor zatrzymany.')
        return 0
    except kettle.APIError:
        print('Logowanie lub wybór urządzenia odrzucone. Monitor zatrzymany; brak automatycznego logowania.')
        return 1
    except Exception as exc:
        if args.debug:
            print(f'[debug] local_exception={kettle.safe_exception(exc)}', file=sys.stderr)
        print('Błąd lokalny. Monitor zatrzymany.')
        return 1
    finally:
        client.token = None


if __name__ == '__main__':
    raise SystemExit(main())
