"""UI login, explicit email challenge, device selection and reauthentication."""
import hashlib
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .api import AigoClient, is_auth_error
from .protocol import NeedSecurityCodeError
from .const import DOMAIN, DEFAULT_INTERVAL

class AigoFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self):
        self.client = AigoClient()
        self.credentials = {}
        self.devices = []

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            self.credentials = dict(user_input)
            return await self._login()
        return self.async_show_form(step_id='user', data_schema=vol.Schema({
            vol.Required('email'): str, vol.Required('password'): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}), errors=errors)

    async def _login(self, code=None):
        try:
            await self.hass.async_add_executor_job(self.client.login_with_code,
                self.credentials['email'], self.credentials['password'], code)
            self.devices = await self.hass.async_add_executor_job(self.client.devices)
        except NeedSecurityCodeError:
            if code:
                return self.async_show_form(step_id='security_code',
                    data_schema=self._code_schema(), errors={'base': 'invalid_code'})
            return await self.async_step_security_code()
        except Exception as exc:
            return self.async_show_form(step_id='security_code' if code else 'user',
                data_schema=self._code_schema() if code else vol.Schema({vol.Required('email'): str,
                    vol.Required('password'): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}),
                errors={'base': ('invalid_code' if code else 'invalid_auth') if is_auth_error(exc) else 'cannot_connect'})
        if self.source == config_entries.SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if (self.credentials['email'].strip().casefold() != entry.data['email'].strip().casefold()
                    or not any(d.get('iotId') == entry.data['device_id'] for d in self.devices)):
                return self.async_abort(reason='wrong_account')
            runtime = getattr(entry, 'runtime_data', None)
            if runtime is not None:
                # Drain the old rotating refresh before replacing persisted credentials.
                await runtime.session.close()
            data = {'email': self.credentials['email'], 'iot_token': self.client.token, **self.client.session}
            self.credentials.clear()
            self.client.token = None
            self.client.session.clear()
            return self.async_update_reload_and_abort(entry, data_updates=data)
        return await self.async_step_device()

    def _code_schema(self):
        return vol.Schema({vol.Optional('send_code', default=False): bool,
            vol.Optional('security_code'): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})

    async def async_step_security_code(self, user_input=None):
        errors = {}
        if user_input:
            if user_input.get('security_code'):
                return await self._login(user_input['security_code'])
            if user_input.get('send_code'):
                try:
                    await self.hass.async_add_executor_job(self.client.send_security_code, self.credentials['email'])
                except Exception:
                    errors['base'] = 'cannot_send_code'
        return self.async_show_form(step_id='security_code', data_schema=self._code_schema(), errors=errors)

    async def async_step_device(self, user_input=None):
        choices = {str(i): f'AigoSmart device {i+1}' for i,d in enumerate(self.devices) if d.get('iotId')}
        if not choices:
            return self.async_abort(reason='no_devices')
        if user_input:
            index = user_input['device']
            if index not in choices:
                return self.async_abort(reason='no_devices')
            device_id = self.devices[int(index)]['iotId']
            await self.async_set_unique_id(hashlib.sha256(device_id.encode()).hexdigest())
            self._abort_if_unique_id_configured()
            data = {'email': self.credentials['email'], 'iot_token': self.client.token, 'device_id': device_id, **self.client.session}
            self.credentials.clear()
            self.client.token = None
            self.client.session.clear()
            return self.async_create_entry(title='AigoSmart kettle', data=data)
        return self.async_show_form(step_id='device', data_schema=vol.Schema({vol.Required('device'): vol.In(choices)}))

    async def async_step_reconfigure(self, user_input=None):
        """Expose the menu action, delegating credentials to HA's reauth flow."""
        entry = self._get_reconfigure_entry()
        # async_start_reauth deliberately ignores entries with an active
        # reconfigure flow. Start/reuse reauth explicitly and hand it to the UI.
        result = next(entry.async_get_active_flows(
            self.hass, {config_entries.SOURCE_REAUTH}), None)
        if result is None:
            result = await self.hass.config_entries.flow.async_init(DOMAIN, context={
                'source': config_entries.SOURCE_REAUTH, 'entry_id': entry.entry_id,
                'unique_id': entry.unique_id, 'title_placeholders': {'name': entry.title},
            }, data=dict(entry.data))
        return self.async_abort(reason='reauth_started',
            next_flow=(config_entries.FlowType.CONFIG_FLOW, result['flow_id']))

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        if user_input is not None:
            return await self.async_step_user()
        return self.async_show_form(step_id='reauth_confirm', data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AigoOptions()

class AigoOptions(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title='', data=user_input)
        return self.async_show_form(step_id='init', data_schema=vol.Schema({
            vol.Required('scan_interval', default=self.config_entry.options.get('scan_interval', DEFAULT_INTERVAL)):
                vol.All(vol.Coerce(int), vol.Range(min=15, max=3600))}))
