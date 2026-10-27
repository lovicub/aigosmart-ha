"""Offline frontend lifecycle and storage data-loss regressions."""
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from custom_components.aigosmart import frontend as f


class FrontendTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, mode='storage', loaded=False):
        items = [{'id': 'old', 'url': '/hacsfiles/aigosmart-premium-card/aigosmart-premium-card.js', 'type': 'module'},
                 {'id': 'other', 'url': '/local/other.js', 'type': 'module'}]
        resources = SimpleNamespace(loaded=loaded)
        async def load():
            resources.loaded = True
        def inspect():
            self.assertTrue(resources.loaded)
            return items
        async def create(data):
            self.assertTrue(resources.loaded)
            items.append({'id': 'new', 'url': data['url'], 'type': data['res_type']})
        async def update(id, data):
            self.assertTrue(resources.loaded)
            next(i for i in items if i['id'] == id).update(url=data['url'], type=data['res_type'])
        resources.async_get_info = AsyncMock(side_effect=load)
        resources.async_items = Mock(side_effect=inspect)
        resources.async_create_item = AsyncMock(side_effect=create)
        resources.async_update_item = AsyncMock(side_effect=update)
        hass = SimpleNamespace(data={'lovelace': SimpleNamespace(resource_mode=mode, resources=resources)},
                               config=SimpleNamespace(components={'frontend', 'lovelace'}),
                               http=SimpleNamespace(async_register_static_paths=AsyncMock()))
        return hass, resources, items

    async def test_upgrade_multiple_entries_reload_and_restart(self):
        hass, r, items = self.fixture()
        original = [dict(i) for i in items]
        await asyncio.gather(*(f.async_register_frontend(hass) for _ in range(4)))
        self.assertEqual(items[:2], original)
        self.assertEqual(len(items), 3)
        r.async_create_item.assert_awaited_once()
        hass.http.async_register_static_paths.assert_awaited_once()
        items[2]['url'] = f.PATH + '?v=old'
        await f.async_register_frontend(hass)
        r.async_update_item.assert_awaited_once_with('new', {'url': f.URL, 'res_type': 'module'})
        self.assertEqual(items[:2], original)
        # Device unload must not remove global resources; a fresh HA runtime
        # re-registers the route and loads persisted resources without adding one.
        hass.data.pop(f._DATA)
        r.loaded = False
        await f.async_register_frontend(hass)
        self.assertEqual(len(items), 3)
        self.assertEqual(hass.http.async_register_static_paths.await_count, 2)

    async def test_new_install_and_foreign_similar_url(self):
        hass, r, items = self.fixture()
        items[:] = [{'id':'foreign', 'url':'https://example.invalid' + f.PATH, 'type':'module'}]
        await f.async_register_frontend(hass)
        self.assertEqual(len(items), 2)
        r.async_update_item.assert_not_called()

    async def test_no_read_or_write_if_load_failed_or_unconfirmed(self):
        for failure in (True, False):
            hass, r, items = self.fixture()
            if failure:
                r.async_get_info.side_effect = RuntimeError('private payload must not be logged')
            else:
                r.async_get_info.side_effect = None
            with self.assertLogs(f.__name__, level='WARNING') as logs:
                await f.async_register_frontend(hass)
            self.assertNotIn('private payload', str(logs.output))
            r.async_items.assert_not_called()
            r.async_create_item.assert_not_called()
            r.async_update_item.assert_not_called()
            self.assertEqual(len(items), 2)

    async def test_yaml_missing_components_and_static_failure(self):
        hass, r, _ = self.fixture('yaml')
        await f.async_register_frontend(hass)
        r.async_get_info.assert_not_called()
        hass.config.components.clear()
        await f.async_register_frontend(hass)
        r.async_get_info.assert_not_called()
        hass, r, _ = self.fixture()
        hass.http.async_register_static_paths.side_effect = RuntimeError('secret')
        await f.async_register_frontend(hass)
        r.async_get_info.assert_not_called()
        hass, r, _ = self.fixture()
        del hass.data['lovelace']
        await f.async_register_frontend(hass)
        r.async_get_info.assert_not_called()

    async def test_schedule_once_and_defer_until_lovelace(self):
        hass, r, _ = self.fixture()
        with patch('homeassistant.setup.async_when_setup_or_start') as schedule:
            for _ in range(3):
                f.async_schedule_frontend(hass)
            schedule.assert_called_once()
            r.async_get_info.assert_not_called()
            await schedule.call_args.args[2](hass, 'lovelace')
        r.async_get_info.assert_awaited_once()

    async def test_real_startup_event_and_late_entry_setup(self):
        from homeassistant.core import HomeAssistant
        from homeassistant.const import EVENT_COMPONENT_LOADED, EVENT_HOMEASSISTANT_START
        import tempfile
        with tempfile.TemporaryDirectory(prefix='issue7-frontend-') as directory:
            hass = HomeAssistant(directory)
            with patch.object(f, 'async_register_frontend', new_callable=AsyncMock) as register:
                f.async_schedule_frontend(hass)
                f.async_schedule_frontend(hass)
                await hass.async_block_till_done()
                register.assert_not_awaited()
                hass.bus.async_fire(EVENT_COMPONENT_LOADED, {'component':'frontend'})
                await hass.async_block_till_done()
                register.assert_not_awaited()
                hass.bus.async_fire(EVENT_COMPONENT_LOADED, {'component':'lovelace'})
                await hass.async_block_till_done()
                register.assert_awaited_once_with(hass)
                hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
                await hass.async_block_till_done()
                register.assert_awaited_once()
            # Fresh runtime with Lovelace already loaded (entry added/reloaded).
            hass.data.pop(f._DATA)
            hass.config.components.add('lovelace')
            with patch.object(f, 'async_register_frontend', new_callable=AsyncMock) as register:
                f.async_schedule_frontend(hass)
                await hass.async_block_till_done()
                register.assert_awaited_once_with(hass)

    async def test_resource_write_failures_are_sanitized_and_optional(self):
        for update in (False, True):
            hass, r, items = self.fixture()
            if update:
                items.append({'id':'new', 'url':f.PATH + '?v=old', 'type':'module'})
                r.async_update_item.side_effect = RuntimeError('PRIVATE_BACKEND_VALUE')
            else:
                r.async_create_item.side_effect = RuntimeError('PRIVATE_BACKEND_VALUE')
            with self.assertLogs(f.__name__, level='WARNING') as logs:
                await f.async_register_frontend(hass)
            self.assertNotIn('PRIVATE_BACKEND_VALUE', str(logs.output))

    async def test_real_ha_lazy_collection_preserves_existing_storage(self):
        from homeassistant.components.lovelace.resources import ResourceStorageCollection
        with patch('homeassistant.components.lovelace.resources.storage.Store'):
            resources = ResourceStorageCollection(Mock(), Mock())
        existing = {'items': [{'id':'old', 'url':'/local/old.js', 'type':'module'}]}
        resources.store = Mock(async_load=AsyncMock(return_value=existing), async_delay_save=Mock())
        hass, _, _ = self.fixture()
        hass.data['lovelace'].resources = resources
        self.assertFalse(resources.loaded)
        await f.async_register_frontend(hass)
        resources.store.async_load.assert_awaited_once()
        self.assertTrue(resources.loaded)
        self.assertIn(existing['items'][0], resources.async_items())
        self.assertEqual(len(resources.async_items()), 2)


class VendorTests(unittest.TestCase):
    def test_pin_license_hashes_and_reproducible_transform(self):
        from tools.vendor_integrated_card import transform, COMMIT
        p = f.ASSETS
        provenance = json.loads((p / 'PROVENANCE.json').read_text())
        self.assertEqual(provenance['commit'], COMMIT)
        for name, digest in provenance['sha256'].items():
            self.assertEqual(hashlib.sha256((p / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(transform((p / 'aigosmart-premium-card.source.js').read_text()),
                         (p / 'aigosmart-ha-integrated-card.js').read_text())
        self.assertIn('Copyright (c) 2026 AigoSmart project contributors', (p / 'LICENSE').read_text())
        self.assertEqual(f.VERSION, '0.1.4')
        self.assertNotIn('http', (p / 'aigosmart-ha-integrated-card.js').read_text())

    def test_package(self):
        import subprocess
        from zipfile import ZipFile
        import sys
        subprocess.run([sys.executable, 'tools/build_zip.py'], check=True, capture_output=True)
        with ZipFile(f'dist/aigosmart-ha-{f.VERSION}.zip') as archive:
            for name in ('aigosmart-ha-integrated-card.js', 'aigosmart-premium-card.source.js', 'LICENSE', 'PROVENANCE.json'):
                self.assertEqual(archive.read('custom_components/aigosmart/frontend/' + name), (f.ASSETS / name).read_bytes())
            self.assertFalse(any('.storage' in name or '__pycache__' in name for name in archive.namelist()))
