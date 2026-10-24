"""Browser regression using the actual frontend pinned by HA Core 2026.10.3.

Optional test dependencies: home-assistant-frontend==20260930.5 and playwright
(with Chromium). Application bootstrap is skipped to expose the production
module loader; the native control and state formatter themselves are unmodified.
All browser requests are intercepted fixtures; all services are recorded mocks.
"""
import argparse
import asyncio
from copy import deepcopy
import importlib.metadata
import json
import mimetypes
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import hass_frontend
from homeassistant.const import __version__
from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation
from playwright.async_api import async_playwright, expect
from custom_components.aigosmart.select import ModeSelect

FRONTEND_VERSION = '20260930.5'
MODULE_PATTERN = re.compile(r'(?:[,{;])([0-9]+)\([a-zA-Z_$][\w$]*,[a-zA-Z_$][\w$]*,[a-zA-Z_$][\w$]*\)\{')


def production_chunks(root):
    """Resolve the pinned select/formatter's production module dependencies."""
    app = next(root.glob('app.*.js'))
    content, lookup = {}, {}
    for path in [app, *root.glob('*.js')]:
        source = path.read_text()
        if path != app and 'export const __rspack_esm_id' not in source[:200]:
            continue
        content[path.name] = source
        for match in MODULE_PATTERN.finditer(source):
            lookup.setdefault(int(match[1]), path.name)
    # IDs and chunk hashes are pinned to the official frontend wheel above.
    needed = {'29637.3b8045d6bdd9922f.js', '21360.ac3c312df84a30f2.js'}
    todo = list(needed)
    while todo:
        for ident in re.findall(r'\b\w+\((\d+)\)', content[todo.pop()]):
            name = lookup.get(int(ident))
            if name and name != app.name and name not in needed:
                needed.add(name)
                todo.append(name)
    assert 'state-card-select' in content['29637.3b8045d6bdd9922f.js']
    assert 'computeStateDisplay:' in content['21360.ac3c312df84a30f2.js']
    return {'app': app.name, 'chunks': sorted(needed)}


async def resources(language):
    """Use Core's real JSON loader/translation cache, including numeric keys."""
    with TemporaryDirectory(prefix='aigo-native-translations-') as directory:
        hass = HomeAssistant(directory)
        async def executor(fn, *args):
            return fn(*args)
        hass.async_add_executor_job = executor
        integration = SimpleNamespace(file_path=ROOT/'custom_components/aigosmart',
            has_translations=True, name='AigoSmart HA')
        try:
            with patch('homeassistant.helpers.translation.async_get_integrations',
                       new=AsyncMock(return_value={'aigosmart': integration})):
                return await translation.async_get_translations(hass, language, 'entity', {'aigosmart'})
        finally:
            await hass.async_stop(force=True)


async def run(output):
    assert __version__ == '2026.10.3', __version__
    assert importlib.metadata.version('home-assistant-frontend') == FRONTEND_VERSION
    root = Path(hass_frontend.__file__).parent/'frontend_latest'
    chunks = production_chunks(root)
    model = json.loads((ROOT/'tests/fixtures/kettle_capabilities.json').read_text())
    output.mkdir(parents=True, exist_ok=True)
    results = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for language, custom in [('en', False), ('de', False), ('pl', False), ('en', True)]:
                current_model = deepcopy(model)
                choices = current_model['properties'][3]['constraints']
                if custom:
                    choices['0'] = 'Tea profile'
                    choices['9'] = 'Other mode'
                select = ModeSelect(Mock(model=current_model, device={'iotId': 'fixture'},
                    data={'Mode': {'value': 2}}), choices)
                raw_options = select.options
                strings = await resources(language)
                labels = [strings[f'component.aigosmart.entity.select.mode.state.{raw}']
                          if select.translation_key else raw for raw in raw_options]
                page = await browser.new_page(viewport={'width': 900, 'height': 600})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                async def route(request):
                    url = urlsplit(request.request.url)
                    if url.netloc != 'fixture.test':
                        await request.abort()
                        return
                    if url.path == '/':
                        await request.fulfill(content_type='text/html', body='''<html><body style="font:16px system-ui;padding:32px;color:#212121;--primary-text-color:#212121;--primary-background-color:#fff;--secondary-background-color:#fff;--wa-color-neutral-on-normal:#212121;--wa-font-size-m:16px;--ha-font-size-m:16px;--ha-font-size-body-m:16px;--wa-color-text-normal:#212121"><h2>Home Assistant native Mode select</h2><div id="host" style="width:540px"></div></body></html>''')
                        return
                    path = root/Path(url.path).name
                    if not path.is_file():
                        await request.fulfill(status=404, body='')
                        return
                    data = path.read_bytes()
                    if path.name == chunks['app']:
                        source = data.decode()
                        assert source.count('o(26544);') == 1
                        data = source.replace('o(26544);', 'window.__aigo_require=o;').encode()
                    await request.fulfill(body=data, content_type='application/javascript'
                        if path.suffix == '.js' else mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                await page.route('**/*', route)
                await page.goto('http://fixture.test/')
                actual = await page.evaluate('''async data => {
                    await import('/frontend_latest/'+data.app);
                    const req=window.__aigo_require;
                    for(const chunk of await Promise.all(data.chunks.map(f=>import('/frontend_latest/'+f))))
                        Object.assign(req.m, chunk.__webpack_modules__);
                    await req(83889);
                    const formatter=await req(8019);
                    const localize=key=>data.strings[key] || '';
                    const id='select.fixture_mode';
                    const stateObj={entity_id:id,state:'2',attributes:{friendly_name:'Mode',options:data.options}};
                    const entities={[id]:{platform:'aigosmart',translation_key:data.translationKey}};
                    const locale={language:data.language,number_format:'language',time_format:'language',time_zone:'local'};
                    window.testCalls=[];
                    const element=document.createElement('state-card-select');
                    element.hass={states:{[id]:stateObj},entities,locale,config:{time_zone:'UTC'},localize,
                        formatEntityState:(obj,state)=>formatter.computeStateDisplay(localize,obj,locale,{time_zone:'UTC'},entities,state),
                        callService:async(...args)=>{window.testCalls.push(args);element.stateObj={...stateObj,state:args[2].option};}};
                    element.stateObj=stateObj;
                    document.querySelector('#host').append(element);
                    await element.updateComplete;
                    return element.shadowRoot.querySelector('ha-control-select-menu').options;
                }''', {**chunks, 'language': language, 'strings': strings,
                      'translationKey': select.translation_key, 'options': raw_options})
                assert actual == [{'value': raw, 'label': label} for raw, label in zip(raw_options, labels)]
                for index, label in enumerate(labels):
                    await page.locator('ha-control-select-menu button').click()
                    for visible_label in labels:
                        await expect(page.get_by_role('menuitem', name=visible_label, exact=True)).to_be_visible()
                    if index == 0:
                        await page.screenshot(path=str(output/f'native-mode-{language}{"-custom" if custom else ""}.png'), animations='disabled')
                    await page.get_by_role('menuitem', name=label, exact=True).click()
                    await page.wait_for_function('(n)=>window.testCalls.length===n', arg=index+1)
                calls = await page.evaluate('window.testCalls')
                assert calls == [['select', 'select_option', {'option': raw}, {'entity_id': 'select.fixture_mode'}]
                                 for raw in raw_options], calls
                assert not errors, errors
                results.append({'language': language, 'custom_model': custom,
                    'translation_key': select.translation_key, 'options': actual,
                    'service_options': [call[2]['option'] for call in calls]})
                await page.close()
            report = {'core': __version__, 'frontend': FRONTEND_VERSION,
                'browser': browser.version, 'cases': results, 'all_services_mocked': True}
            (output/'native-mode-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
            print(json.dumps(report, ensure_ascii=False))
        finally:
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/aigosmart-native-mode'))
    asyncio.run(run(parser.parse_args().output))
