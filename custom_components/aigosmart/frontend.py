"""Optional, local-only Lovelace resource registration for the bundled card."""
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlsplit

_LOGGER = logging.getLogger(__name__)
_DATA = 'aigosmart_integrated_frontend'
ASSETS = Path(__file__).parent / 'frontend'
PATH = '/aigosmart-ha-integrated/aigosmart-ha-integrated-card.js'
CARD_VERSION = 'card-0.1.1-beta.1'


async def _async_resource_url(hass):
    """Cache-busting URL; the version comes from HA's loader, not a file read."""
    from homeassistant.loader import async_get_integration
    integration = await async_get_integration(hass, 'aigosmart')
    return f'{PATH}?v={integration.version}-{CARD_VERSION}'


def async_schedule_frontend(hass):
    """Install once per HA runtime, after optional Lovelace setup or HA start.

    Assets/resources belong to the integration, not a device entry. Retain them
    on unload so existing dashboards continue working; restart recreates state.
    """
    from homeassistant.setup import async_when_setup_or_start

    if _DATA in hass.data:
        return
    hass.data[_DATA] = {'lock': asyncio.Lock(), 'static': False}

    async def ready(hass, _component):
        await async_register_frontend(hass)

    async_when_setup_or_start(hass, 'lovelace', ready)


async def async_register_frontend(hass):
    """Fail closed on resource loading errors; never log exception payloads."""
    state = hass.data.setdefault(_DATA, {'lock': asyncio.Lock(), 'static': False})
    async with state['lock']:
        try:
            resource_url = await _async_resource_url(hass)
            from homeassistant.components.http import StaticPathConfig
            from homeassistant.components.lovelace.const import LOVELACE_DATA

            if 'frontend' not in hass.config.components or not getattr(hass, 'http', None):
                _LOGGER.warning('Integrated card unavailable: frontend is not loaded')
                return
            if not state['static']:
                await hass.http.async_register_static_paths([
                    StaticPathConfig(PATH, str(ASSETS / 'aigosmart-ha-integrated-card.js'), True)
                ])
                state['static'] = True
            lovelace = hass.data.get(LOVELACE_DATA)
            if lovelace is None:
                _LOGGER.warning('Integrated card resource skipped: Lovelace is not loaded')
                return
            if lovelace.resource_mode != 'storage':
                return  # YAML resources remain entirely user-managed.
            resources = lovelace.resources
            # Public API ensures lazy storage load (Core issue #165767). Do not
            # inspect async_items or write until HA explicitly confirms loaded.
            await resources.async_get_info()
            if getattr(resources, 'loaded', False) is not True:
                _LOGGER.warning('Integrated card resource skipped: storage load unconfirmed')
                return
            for item in resources.async_items():
                url = urlsplit(item.get('url', ''))
                if not url.scheme and not url.netloc and url.path == PATH:
                    if item['url'] != resource_url or item.get('type') != 'module':
                        await resources.async_update_item(item['id'], {'url': resource_url, 'res_type': 'module'})
                    return
            await resources.async_create_item({'url': resource_url, 'res_type': 'module'})
        except Exception:
            _LOGGER.warning('Integrated card registration failed; cloud integration remains available')
