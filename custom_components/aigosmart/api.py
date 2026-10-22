"""Shared API with single-attempt writes and live TSL validation."""
import json
from . import protocol as p
from .model import parse_model, plan

class AigoClient(p.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._permission = None
        self._security_code = None

    def login_with_code(self, email, password, code=None):
        self._security_code = code
        try:
            return self.login(email, password, interactive=code is not None)
        finally:
            self._security_code = None

    def security_verification(self, username):
        return self._security_code

    def send_security_code(self, email):
        self.uc(p.SEND_CODE, {'send_to': email.strip(), 'account_type': 'email',
            'action': 'LoginSecurity', 're_send_count': 0, 'captcha_token': ''}, smart=True)

    def model(self, device):
        rows = parse_model(self.signed(p.IOT, p.TSL,
            {'iotId': p.required(device, 'iotId')}, '1.0.4')['data'])
        return {'source': 'live-tsl', 'properties': rows}

    def authorize_property_write(self, method, url, body):
        permission, self._permission = self._permission, None
        return (permission is not None and method == 'POST' and url == p.IOT + '/thing/properties/set'
                and json.loads(body).get('params') == permission)

    def write(self, device, model, identifier, value, *, dry_run=False):
        if identifier not in {'Target_temperature', 'Mode', 'HeatingSwitch', 'heatpreservation'}:
            raise ValueError('Property blocked by v0.1 safety policy')
        output = plan(model, identifier, value)
        if dry_run:
            return output
        params = {'iotId': p.required(device, 'iotId'), 'items': {identifier: value}}
        self._permission = params
        try:
            self.signed(p.IOT, '/thing/properties/set', params)
        finally:
            self._permission = None
        return 'accepted_unconfirmed'


def is_auth_error(exc):
    return isinstance(exc, p.NeedSecurityCodeError) or (
        isinstance(exc, p.APIError) and (exc.status in (401, 403) or exc.code in {
            '401', '403', 'invalid_grant', 'access_denied', 'invalid_client'}))
