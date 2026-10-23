"""AigoSmart protocol; session persistence is owned by the HA integration.

Protocol reviewed against MarcoM1993/ha-aigostar commit
39f7bab1edd36161e41430ed1e01439e4e8b51ab (alibaba_api.py, const.py).
No upstream code is imported or executed.
"""
import argparse
import base64
from email.utils import formatdate
import getpass
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import warnings

APP_KEY = '28770785'
APP_SECRET = '41fd4a1eb18fa7ace5e2abbbe3867f93'  # Public APK signing constant.
AES_KEY = 'tCx8BA0yKVr+NbBChH928URAV90=0000'
CLIENT_ID = 'C28098DEE9664BABBB9AE8E6E47505B0'
CLIENT_SECRET = 'C3575D1E-7A5F-411F-920D-5C469AA53AB7'
UC = 'https://uc.aigostar.com'
SMART = 'https://smartapi.aigostar.com'
SEND_CODE = '/message/v1.1/security/sendcode/anonymous'
DEVICE_ID = uuid.uuid5(uuid.NAMESPACE_DNS, 'aigostar.homeassistant').hex
IOT = 'https://eu-central-1.api-iot.aliyuncs.com'
REGION = 'https://api.link.aliyun.com'
OA = 'living-account.eu-central-1.aliyuncs.com'
LOGIN = '/v1.0/connect/token'
AUTHORIZE = '/v1.0/connect/authorize'
REGION_PATH = '/living/account/region/get'
OA_PATH = '/api/prd/loginbyoauth.json'
SESSION = '/account/createSessionByAuthCode'
REFRESH = '/account/checkOrRefreshSession'
DEVICES = '/uc/listBindingByAccount'
PROPERTIES = '/thing/properties/get'
TSL = '/thing/tsl/get'
CONTENT = 'application/json; charset=UTF-8'
REPORT = Path(__file__).resolve().parents[2] / 'reports/kettle_properties.json'


# Only exact reviewed literals may leave the response parser. OAuth authorization
# "code" is a secret, so it must never be printed as a generic API code.
SAFE_CODES = frozenset({'UC/NEED_SECURITY_CODE', 'invalid_grant', 'invalid_client',
                        'invalid_request', 'unauthorized_client', 'access_denied',
                        'unsupported_grant_type', 'SENDCODE_INTERVAL_IS_TOO_SHORT',
                        'INVALID_SECURITY_CODE', 'SECURITY_CODE_EXPIRED', 'UC/INVALID_SECURITY_CODE',
                        'UC/SECURITY_CODE_EXPIRED', 'CAPTCHA_REQUIRED', 'NEED_CAPTCHA',
                        'UC/NEED_CAPTCHA', 'VERIFY_CODE_ERROR', 'VERIFY_CODE_EXPIRED',
                        '2062', '100001', '100003', '100004', '100005',
                        '200', '400', '401', '403', '404', '429', '500', '502', '503'})
MAX_RESPONSE = 2_000_000


def response_diagnostics(data):
    """Fixed vocabulary only: even JSON field names can contain secrets."""
    if not isinstance(data, dict):
        return {'json_fields': '-', 'code_type': 'unavailable', 'code_category': 'unavailable'}
    reviewed = {'code', 'error', 'success', 'data', 'message', 'ok',
                'error_description', 'already_sent'}
    fields = sorted(key for key in data if key in reviewed)
    unknown = len(data) - len(fields)
    if unknown:
        fields.append(f'redacted_fields:{unknown}')
    value = data.get('code')
    kind = ('missing' if 'code' not in data else
            {str: 'string', int: 'integer', float: 'number', bool: 'boolean',
             type(None): 'null', dict: 'object', list: 'array'}.get(type(value), 'other'))
    if kind == 'missing':
        category = 'missing'
    elif type(value) not in (int, str):
        category = 'invalid_type'
    elif value in (200, '200'):
        category = 'success'
    elif safe_code({'code': value}) != 'UNKNOWN':
        category = 'known_error'
    else:
        category = 'unknown'
    return {'json_fields': ','.join(fields) or '-', 'code_type': kind,
            'code_category': category}


def safe_code(data):
    if not isinstance(data, dict):
        return 'UNKNOWN'
    for key in ('code', 'error'):
        value = data.get(key)
        if type(value) is int:
            value = str(value)
        if type(value) is str and value in SAFE_CODES:
            return value
    return 'UNKNOWN'


def safe_exception(exc):
    # Never print arbitrary class names or exception messages from dependencies.
    for cls in (NeedSecurityCodeError, APIError, urllib.error.HTTPError,
                urllib.error.URLError, json.JSONDecodeError, TimeoutError,
                UnicodeError, ValueError, OSError, KeyboardInterrupt, EOFError):
        if isinstance(exc, cls):
            return cls.__name__
    return 'Exception'


class APIError(Exception):
    """Only sanitized metadata; no server bodies, URLs or credentials."""
    def __init__(self, message, *, status=None, code='UNKNOWN', exception='APIError',
                 validation='response_validation'):
        super().__init__(message)
        self.status = status
        self.code = code if code in SAFE_CODES else 'UNKNOWN'
        self.exception = exception
        self.response_length = None
        self.content_type = '-'
        self.validation = validation
        self.diagnostics = None


class NeedSecurityCodeError(APIError):
    """Verification required; interactive flow requires explicit send consent."""


class APIResponse(dict):
    def __init__(self, data, status):
        super().__init__(data)
        self.status = status


def decode_response(response, *, allow_empty=False, metadata=None):
    raw = response.read(MAX_RESPONSE + 1)
    if metadata is not None:
        metadata['response_length'] = len(raw)
        # Server headers are untrusted. Print only reviewed media types, never
        # arbitrary parameters (which could contain credentials or newlines).
        content_type = response.headers.get('Content-Type', '')
        media_type = content_type.split(';', 1)[0].strip().lower() if isinstance(content_type, str) else ''
        metadata['content_type'] = (media_type if media_type in {
            'application/json', 'text/json', 'text/plain', 'text/html',
            'application/octet-stream'} else 'other' if media_type else '-')
    if len(raw) > MAX_RESPONSE:
        raise APIError('Przekroczono limit odpowiedzi API.', validation='response_size')
    # Matches upstream _smart_api_post's raw.strip() behavior, but only for
    # successful responses from the explicitly reviewed SmartAPI send endpoint.
    if allow_empty and not raw.strip():
        return {'code': 200}
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise APIError('Odpowiedź API nie jest prawidłowym JSON.',
                       exception=safe_exception(exc), validation='json_decode') from None
    if metadata is not None:
        metadata['diagnostics'] = response_diagnostics(result)
    if not isinstance(result, dict):
        raise APIError('Nieprawidłowy format odpowiedzi API.', validation='json_object')
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise APIError('Przekierowanie HTTP zostało odrzucone.', status=code)


def transport(method, url, headers, body):
    # Default TLS verification; no cookie processor, persistence or retries.
    opener = urllib.request.build_opener(NoRedirect())
    status = None
    metadata = {}
    parts = urllib.parse.urlsplit(url)
    smart_verification = (method == 'POST' and
                          f'{parts.scheme}://{parts.netloc}' == SMART and
                          parts.path == SEND_CODE)
    try:
        with opener.open(urllib.request.Request(url, data=body, headers=headers,
                                               method=method), timeout=20) as response:
            status = response.status
            result = APIResponse(decode_response(
                response, allow_empty=smart_verification and 200 <= status < 300,
                metadata=metadata), status)
            result.response_length = metadata.get('response_length')
            result.content_type = metadata.get('content_type', '-')
            return result
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            with exc:
                code = safe_code(decode_response(exc, metadata=metadata))
        except Exception:
            code = 'UNKNOWN'
        error = NeedSecurityCodeError if code == 'UC/NEED_SECURITY_CODE' else APIError
        failure = error('API odrzuciło żądanie.', status=status, code=code,
                        exception='HTTPError', validation='http_status')
        failure.diagnostics = metadata.get('diagnostics')
        failure.response_length = metadata.get('response_length')
        failure.content_type = metadata.get('content_type', '-')
        raise failure from None
    except APIError as exc:
        exc.diagnostics = metadata.get('diagnostics')
        if exc.status is None:
            exc.status = status
        exc.response_length = metadata.get('response_length')
        exc.content_type = metadata.get('content_type', '-')
        raise
    except Exception as exc:
        raise APIError('Błąd połączenia lub formatu odpowiedzi API.',
                       status=status, exception=safe_exception(exc)) from None


def encrypt_password(password):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7
    padder = PKCS7(128).padder()
    padded = padder.update(password.encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(AES_KEY.encode()), modes.CBC(bytes(16))).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


def required(data, key):
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, str) or not value:
        raise APIError('Brak wymaganego pola odpowiedzi API.')
    return value


class Client:
    def __init__(self, send=transport, debug=False):
        self.send = send
        self.debug = debug
        self.token = None
        self.session = {}

    def authorize_property_write(self, method, url, body):
        """Read-only clients never authorize writes."""
        return False

    def request(self, method, url, headers, body=None):
        parts = urllib.parse.urlsplit(url)
        allowed = {(UC, LOGIN, 'POST'), (UC, AUTHORIZE, 'GET'),
                   (REGION, REGION_PATH, 'POST'), ('https://' + OA, OA_PATH, 'POST'),
                   (IOT, SESSION, 'POST'), (IOT, REFRESH, 'POST'), (IOT, DEVICES, 'POST'),
                   (IOT, PROPERTIES, 'POST'), (IOT, TSL, 'POST'),
                   (SMART, SEND_CODE, 'POST')}
        if ((f'{parts.scheme}://{parts.netloc}', parts.path, method) not in allowed
                and not self.authorize_property_write(method, url, body)):
            raise APIError('Żądanie poza listą dozwolonych operacji.')
        stage = {LOGIN: 'UC', AUTHORIZE: 'OAuth', REGION_PATH: 'region',
                 OA_PATH: 'OA', SEND_CODE: 'sendcode'}.get(parts.path, 'IoT')
        started = time.perf_counter()
        status, code, exception = None, 'UNKNOWN', '-'
        response_length, content_type = None, '-'
        diagnostics = response_diagnostics(None)
        validation = '-'
        try:
            result = self.send(method, url, headers, body)
            status = getattr(result, 'status', None)
            response_length = getattr(result, 'response_length', None)
            content_type = getattr(result, 'content_type', '-')
            code = safe_code(result)
            if parts.path == SEND_CODE:
                diagnostics = response_diagnostics(result)
                if type(status) is int and not 200 <= status < 300:
                    raise APIError('API odrzuciło żądanie.', validation='http_status')
            if parts.path == OA_PATH and isinstance(result, dict) and code in {'UNKNOWN', '200'}:
                code = safe_code(result.get('data'))
            # Successful OAuth "code" is an authorization credential.
            if parts.path == AUTHORIZE and isinstance(result, dict) and not result.get('error'):
                code = 'UNKNOWN'
            self.validate_response(parts.path, result)
            validation = 'passed'
            return result
        except BaseException as exc:
            exception = safe_exception(exc)
            if isinstance(exc, APIError):
                validation = exc.validation
                if exc.diagnostics is not None:
                    diagnostics = exc.diagnostics
                response_length = exc.response_length if exc.response_length is not None else response_length
                content_type = exc.content_type if exc.content_type != '-' else content_type
                status = exc.status if exc.status is not None else status
                if exc.code != 'UNKNOWN':
                    code = exc.code
                exception = exc.exception if type(exc) is APIError else exception
            raise
        finally:
            if self.debug:
                # Host comes from the request allowlist, never a server response.
                http = status if type(status) is int and 100 <= status <= 599 else '-'
                elapsed = (time.perf_counter() - started) * 1000
                detail = ''
                if parts.path == SEND_CODE:
                    detail = (' ' + ' '.join(f'{key}={value}' for key, value in diagnostics.items())
                              + f' validation={validation}')
                print(f'[debug] stage={stage} host={parts.hostname} http={http} '
                      f'api_code={code} exception={exception} elapsed_ms={elapsed:.1f} '
                      f'response_length={response_length if response_length is not None else "-"} '
                      f'content_type={content_type}{detail}',
                      file=sys.stderr)

    @staticmethod
    def validate_response(path, result):
        if not isinstance(result, dict):
            raise APIError('Nieprawidłowy format odpowiedzi API.')
        code = safe_code(result)
        if code == 'UC/NEED_SECURITY_CODE':
            raise NeedSecurityCodeError('Wymagana dodatkowa weryfikacja.', code=code)
        if path == SEND_CODE:
            # Explicit local contract. Upstream passes arbitrary parsed JSON
            # through; that is not evidence that success:true or ok:true is a
            # positive verification. Never coerce floats, booleans or strings.
            category = response_diagnostics(result)['code_category']
            if category != 'success':
                raise APIError('Weryfikacja odrzucona.', code=code,
                               validation='smart_code_' + category)
            for field in ('error', 'success', 'data'):
                if ((field == 'error' and result.get(field)) or
                        (field != 'error' and result.get(field) is False)):
                    raise APIError('Weryfikacja odrzucona.', code=code,
                                   validation='smart_' + field)
        elif path == LOGIN:
            if result.get('error') or code not in {'UNKNOWN', '200'}:
                raise APIError('UC odrzuciło logowanie.', code=code)
            required(result, 'access_token')
        elif path == AUTHORIZE:
            if result.get('error'):
                raise APIError('OAuth odrzuciło żądanie.')
            required(result, 'code')
        elif path == OA_PATH:
            try:
                required(result['data']['data']['loginSuccessResult'], 'sid')
            except (KeyError, TypeError):
                raise APIError('Nieprawidłowa odpowiedź logowania OA.') from None
        else:
            if result.get('code') != 200:
                raise APIError('API odrzuciło żądanie.', code=code)
            data = result.get('data')
            if path == REGION_PATH and required(data, 'oaApiGatewayEndpoint') != OA:
                raise APIError('Nieobsługiwany region konta.')
            if path == SESSION:
                required(data, 'iotToken')
            if path == PROPERTIES and not isinstance(data, dict):
                raise APIError('Nieprawidłowe właściwości urządzenia.')
            if path == DEVICES:
                batch = data.get('data') if isinstance(data, dict) else None
                if not isinstance(batch, list) or any(not isinstance(d, dict) for d in batch):
                    raise APIError('Nieprawidłowa lista urządzeń.')

    def uc(self, path, params=None, token=None, *, smart=False):
        method = 'POST' if params is not None else 'GET'
        url = (SMART if smart else UC) + path
        ts = str(int(time.time() * 1000))
        base, _, query = url.partition('?')
        pairs = dict(p.split('=', 1) for p in query.split('&') if '=' in p)
        canonical = 'smart-android-v1' + AES_KEY + ts + method + base
        canonical += ','.join(k + v for k, v in sorted(pairs.items()))
        headers = {'AppKey': 'smart-android-v1', 'TenantId': '1000', 'Timestamp': ts,
                   'Signature': hashlib.md5(canonical.encode()).hexdigest().upper()}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if params is not None:
            headers['Content-Type'] = CONTENT if smart else 'application/x-www-form-urlencoded'
        return self.request(method, url, headers,
                            (json.dumps(params, separators=(',', ':'), ensure_ascii=False).encode() if smart
                             else urllib.parse.urlencode(params).encode()) if params is not None else None)

    def signed(self, host, path, params, version='1.0.0', form=False):
        date = formatdate(usegmt=True)
        signed = {'x-ca-key': APP_KEY, 'x-ca-nonce': str(uuid.uuid4()).upper(),
                  'x-ca-stage': 'RELEASE', 'x-ca-timestamp': str(int(time.time()*1000)),
                  'x-ca-version': '1'}
        if form:
            fields = {'loginByOauthRequest': json.dumps(params, separators=(',', ':'))}
            body = urllib.parse.urlencode(fields).encode()
            content = 'application/x-www-form-urlencoded; charset=UTF-8'
            md5 = ''
            resource = path + '?' + '&'.join(k + '=' + v for k, v in sorted(fields.items()))
        else:
            request = {'language': 'en-US', 'appKey': APP_KEY, 'apiVer': version}
            if self.token and path != REFRESH:
                request['iotToken'] = self.token
            body = json.dumps({'id': str(uuid.uuid4()).upper(), 'version': '1.0.0',
                               'params': params, 'request': request},
                              separators=(',', ':'), ensure_ascii=False).encode()
            content = CONTENT
            md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
            resource = path
        canonical = f'POST\n{CONTENT}\n{md5}\n{content}\n{date}\n'
        canonical += '\n'.join(k + ':' + v for k, v in sorted(signed.items())) + '\n' + resource
        headers = dict(signed, **{'Content-Type': content, 'Accept': CONTENT, 'Date': date,
            'X-Ca-Signature-Headers': ','.join(sorted(signed)),
            'X-Ca-Signature-Method': 'HmacSHA1',
            'X-Ca-Signature': base64.b64encode(hmac.new(APP_SECRET.encode(), canonical.encode(), hashlib.sha1).digest()).decode()})
        if md5:
            headers['Content-MD5'] = md5
        result = self.request('POST', host + path, headers, body)
        if not form and result.get('code') != 200:
            raise APIError('API odrzuciło żądanie; możliwa wymagana weryfikacja konta.')
        return result

    def security_verification(self, username):
        """Send once and collect the code; only UC login can validate it."""
        answer = input('UC/NEED_SECURITY_CODE: wysłać kod weryfikacyjny? [tak/N]: ')
        if answer.strip().lower() != 'tak':
            raise APIError('Anulowano wysyłkę kodu.')
        fields = {'send_to': username.strip(),
                  'account_type': 'email' if '@' in username else 'phone_number',
                  'action': 'LoginSecurity'}
        self.uc(SEND_CODE, dict(fields, re_send_count=0, captcha_token=''), smart=True)
        # Refuse getpass fallback, which would echo a verification secret.
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            code = getpass.getpass('Kod weryfikacyjny (ukryty): ').strip()
        try:
            if not code:
                raise APIError('Nie podano kodu.')
            return code
        finally:
            del code

    def login(self, username, password, *, interactive=False):
        self.token = None
        self.session = {}
        fields = {'account_type': 'email' if '@' in username else 'phone_number',
            'username': username.strip(), 'password': encrypt_password(password),
            'grant_type': 'password', 'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
            'cuid': DEVICE_ID}
        try:
            result = self.uc(LOGIN, fields)
        except NeedSecurityCodeError:
            if not interactive:
                raise
            security_code = self.security_verification(username)
            try:
                result = self.uc(LOGIN, dict(fields, security_code=security_code))
            finally:
                del security_code
        access = required(result, 'access_token')
        query = urllib.parse.urlencode({'response_type': 'code', 'client_id': 'smartapp',
            'redirect_uri': 'none', 'scope': 'openid profile', 'response_mode': 'json'})
        code = required(self.uc(AUTHORIZE + '?' + query, token=access), 'code')
        region = self.signed(REGION, REGION_PATH, {'type': 'THIRD_AUTHCODE', 'authCode': code}, '1.0.2')
        if required(region.get('data'), 'oaApiGatewayEndpoint') != OA:
            raise APIError('Nieobsługiwany region konta; zatrzymano logowanie.')
        result = self.signed('https://' + OA, OA_PATH, {'oauthPlateform': 23,
            'accessToken': None, 'openId': None, 'oauthAppKey': APP_KEY, 'tokenType': None,
            'authCode': code, 'userData': None}, form=True)
        try:
            sid = required(result['data']['data']['loginSuccessResult'], 'sid')
        except (KeyError, TypeError):
            raise APIError('Nieprawidłowa odpowiedź logowania OA.') from None
        session = self.signed(IOT, SESSION, {'request': {'authCode': sid,
            'appKey': APP_KEY, 'accountType': 'OA_SESSION'}}, '1.0.4')
        self.accept_session(session.get('data'))

    def accept_session(self, data, *, refresh=False):
        """API expiry fields are durations in seconds, never absolute timestamps."""
        now = time.time()
        previous = self.session if refresh else {}
        session = dict(previous)
        if not refresh:
            session['last_refresh'] = None
        session['iot_token'] = required(data, 'iotToken')
        for wire, local in (('refreshToken', 'refresh_token'), ('identityId', 'identity_id')):
            if wire in data or not refresh:
                session[local] = required(data, wire)
        for wire, local in (('iotTokenExpire', 'iot_token'), ('refreshTokenExpire', 'refresh_token')):
            if wire not in data:
                if not refresh or wire == 'iotTokenExpire' or (refresh and 'refreshToken' in data
                        and data['refreshToken'] != previous.get('refresh_token')):
                    raise APIError('Missing session lifetime')
                continue
            value = data[wire]
            try:
                ttl = float(value) if not isinstance(value, bool) else float('nan')
            except (ValueError, TypeError):
                ttl = float('nan')
            if not math.isfinite(ttl) or ttl <= 0:
                raise APIError('Invalid session lifetime')
            session[local + '_ttl'] = ttl
            session[local + '_expires_at'] = now + ttl
        if refresh:
            session['last_refresh'] = now
        self.session = session
        self.token = session['iot_token']

    def restore_session(self, data):
        keys = ('iot_token', 'refresh_token', 'identity_id', 'iot_token_ttl',
                'refresh_token_ttl', 'iot_token_expires_at', 'refresh_token_expires_at', 'last_refresh')
        self.session = {key: data[key] for key in keys if key in data}
        self.token = self.session.get('iot_token')

    def refresh_iot_token_sync(self):
        result = self.signed(IOT, REFRESH, {
            'refreshToken': required(self.session, 'refresh_token'),
            'identityId': required(self.session, 'identity_id')}, '1.0.4')
        self.accept_session(result.get('data'), refresh=True)

    def devices(self):
        devices = []
        for page in range(1, 1001):
            result = self.signed(IOT, DEVICES, {'pageNo': page, 'pageSize': 100}, '1.0.8')
            data = result.get('data')
            batch = data.get('data') if isinstance(data, dict) else None
            if not isinstance(batch, list) or any(not isinstance(d, dict) for d in batch):
                raise APIError('Nieprawidłowa lista urządzeń.')
            devices.extend(batch)
            if len(batch) < 100:
                return devices
        raise APIError('Przekroczono limit stron urządzeń.')

    def properties(self, device):
        result = self.signed(IOT, PROPERTIES, {'iotId': required(device, 'iotId')})
        data = result.get('data')
        if not isinstance(data, dict):
            raise APIError('Nieprawidłowe właściwości urządzenia.')
        return data


def anonymize(properties):
    # Preserve numeric telemetry only. Unknown strings, nested values and names
    # can contain credentials, personal labels or identifiers and are redacted.
    output = []
    for index, (key, item) in enumerate(properties.items(), 1):
        safe_key = (key if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', key)
                    and not re.search(r'token|secret|pass|cookie|id|name|email|mac|ssid|address', key, re.I)
                    else f'redacted_property_{index}')
        value = item.get('value') if isinstance(item, dict) else None
        safe = isinstance(value, (bool, int, float)) and (not isinstance(value, float) or math.isfinite(value))
        output.append({'property': safe_key, 'value': value if safe and safe_key == key else '[REDACTED]'})
    return output


def main():
    parser = argparse.ArgumentParser(description='Interaktywny odczyt AigoSmart; bez komend sterujących.')
    parser.add_argument('--read-only', action='store_true', required=True)
    parser.add_argument('--debug', action='store_true', help='Bezpieczna diagnostyka na stderr.')
    args = parser.parse_args()
    client = Client(debug=args.debug)
    try:
        username = getpass.getpass('Konto AigoSmart (ukryte): ')
        password = getpass.getpass('Hasło: ')
        try:
            client.login(username, password, interactive=True)
        finally:
            del username, password
        devices = client.devices()
        if not devices:
            raise APIError('Brak urządzeń na koncie.')
        # Names appear only in the interactive terminal, never in the report.
        for i, device in enumerate(devices, 1):
            name = str(device.get('deviceName') or device.get('productName') or 'Urządzenie')
            print(f'{i}: {ascii(name)}')
        index = int(input('Wybierz numer czajnika: '))
        if not 1 <= index <= len(devices):
            raise APIError('Nieprawidłowy numer urządzenia.')
        report = {'mode': 'read-only', 'source': 'live', 'device_count': len(devices),
                  'properties': anonymize(client.properties(devices[index - 1]))}
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
        print('Zapisano zanonimizowany raport reports/kettle_properties.json')
        return 0
    except NeedSecurityCodeError:
        print('UC/NEED_SECURITY_CODE: wymagany kod dodatkowej weryfikacji konta. '
              'Weryfikacja nie została zakończona; odczyt zatrzymano. '
              'Nie zapisano nowego raportu.')
        return 1
    except APIError as exc:
        if exc.code == 'SENDCODE_INTERVAL_IS_TOO_SHORT' or exc.status == 429:
            print('Limit wysyłki lub żądań. Odczekaj przed ręcznym ponownym uruchomieniem.')
        elif 'CAPTCHA' in exc.code:
            print('Wymagana CAPTCHA. Zakończ weryfikację w oficjalnej aplikacji.')
        else:
            print('API odrzuciło żądanie; kod może być błędny lub wygasły, albo wymagana jest '
                  'CAPTCHA. Sprawdź konto w oficjalnej aplikacji. Nie zapisano nowego raportu.')
        return 1
    except (Exception, KeyboardInterrupt) as exc:
        if args.debug:
            print(f'[debug] local_exception={safe_exception(exc)}', file=sys.stderr)
        print('Odczyt przerwany lub API odrzuciło żądanie. Nie zapisano nowego raportu.')
        return 1
    finally:
        client.token = None


if __name__ == '__main__':
    raise SystemExit(main())
