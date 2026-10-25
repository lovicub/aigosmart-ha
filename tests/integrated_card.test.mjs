// Adapted from AigoSmart Premium Card v0.1.1-beta.1 tests (MIT).
// Copyright (c) 2026 AigoSmart project contributors; see frontend/LICENSE.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../custom_components/aigosmart/frontend/aigosmart-ha-integrated-card.js', import.meta.url), 'utf8');
function fixture(overrides = {}, config = {}) {
  const registry = new Map(), calls = [], logs = [];
  let confirm = true;
  class Element {
    attachShadow() {
      return this.shadowRoot = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
    }
    dispatchEvent(event) { this.lastEvent = event; }
  }
  const context = vm.createContext({
    HTMLElement: Element,
    CustomEvent: class { constructor(type, options) { this.type = type; Object.assign(this, options); } },
    customElements: { get: key => registry.get(key), define: (key, value) => registry.set(key, value) },
    window: { confirm: () => confirm },
    console: { info: () => {}, error: (...args) => logs.push(args) }
  });
  vm.runInContext(source, context);
  const Card = registry.get('aigosmart-ha-integrated-card');
  const card = new Card();
  card.setConfig({ power_entity:'switch.kettle', target_entity:'number.kettle_target',
    status_entity:'sensor.kettle_status', mode_entity:'select.kettle_mode',
    keep_warm_entity:'number.kettle_warm', time_entity:'sensor.kettle_time', ...config });
  const states = {
    'switch.kettle': { state:'off', attributes:{} },
    'number.kettle_target': { state:'80', attributes:{min:0,max:100,step:1} },
    'sensor.kettle_status': { state:'1', attributes:{} },
    'select.kettle_mode': { state:'0', attributes:{options:['0','1','2']} },
    'number.kettle_warm': { state:'2', attributes:{min:0,max:13,step:1} },
    'sensor.kettle_time': { state:'5', attributes:{} }, ...overrides
  };
  card.hass = { states, callService: async (...args) => { calls.push(args); } };
  return {card, calls, context, Card, states, logs, setConfirm: value => {confirm = value;} };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const plain = value => JSON.parse(JSON.stringify(value));

test('registers once and setting HA state never sends commands', () => {
  const f=fixture();
  assert.equal(f.context.window.customCards.length,1);
  assert.equal(f.calls.length,0);
  assert.match(f.card.shadowRoot.innerHTML,/ZIElTEMPERATUR/);
  vm.runInContext(`{${source}}`,f.context);
  assert.equal(f.context.window.customCards.length,1);
});
test('heating on requires confirmation; cancellation sends nothing', async () => {
  const f=fixture();f.setConfirm(false);f.card.power();await settle();assert.equal(f.calls.length,0);
});
test('explicit heating ON sends one HA service request', async () => {
  const f=fixture();f.card.power();await settle();
  assert.deepEqual(plain(f.calls),[['switch','turn_on',{entity_id:'switch.kettle'}]]);
});
test('heating OFF does not require start confirmation', async () => {
  const f=fixture({'switch.kettle':{state:'on',attributes:{}}});f.setConfirm(false);
  f.card.power();await settle();assert.equal(f.calls.length,1);assert.equal(f.calls[0][1],'turn_off');
});
test('unavailable power prevents commands', async () => {
  const f=fixture({'switch.kettle':{state:'unavailable',attributes:{}}});f.card.power();await settle();assert.equal(f.calls.length,0);
});
test('temperature respects entity bounds and integer type', async () => {
  const f=fixture();for(const n of [-1,101,80.5,NaN])f.card.setTemperature(n);
  assert.equal(f.calls.length,0);f.card.setTemperature(100);await settle();
  assert.deepEqual(plain(f.calls),[['number','set_value',{entity_id:'number.kettle_target',value:100}]]);
});
test('unavailable temperature does not send a request', () => {
  const f=fixture({'number.kettle_target':{state:'unavailable',attributes:{}}});f.card.setTemperature(80);assert.equal(f.calls.length,0);
});
test('mode sends the selected TSL key including zero', async () => {
  const f=fixture();f.card.setMode('0');await settle();
  assert.deepEqual(plain(f.calls),[['select','select_option',{entity_id:'select.kettle_mode',option:'0'}]]);
});
test('warm adjustment clamps at the entity maximum', async () => {
  const f=fixture({'number.kettle_warm':{state:'13',attributes:{min:0,max:13,step:1}}});f.card.setWarm(1);await settle();
  assert.equal(f.calls[0][2].value,13);
});
test('warm adjustment respects the entity step and lower bound', async () => {
  const f=fixture({'number.kettle_warm':{state:'0',attributes:{min:0,max:13,step:1}}});f.card.setWarm(-1);await settle();assert.equal(f.calls[0][2].value,0);
});
test('failed service is not retried and busy state clears', async () => {
  const f=fixture();let attempts=0;
  f.card._hass.callService=async()=>{attempts++;throw new Error('offline test failure');};
  await f.card.service('switch','turn_on',{entity_id:'switch.kettle'});
  assert.equal(attempts,1);assert.equal(f.card._busy,false);assert.equal(f.logs.length,1);
});
test('busy guard prevents concurrent service calls', async () => {
  const f=fixture();let finish;f.card._hass.callService=(...args)=>{f.calls.push(args);return new Promise(resolve=>{finish=resolve;});};
  const pending=f.card.service('switch','turn_on',{entity_id:'switch.kettle'});
  await f.card.service('switch','turn_on',{entity_id:'switch.kettle'});
  assert.equal(f.calls.length,1);finish();await pending;
});
test('card name is escaped and temperature display is target state', () => {
  const f=fixture({}, {name:'<script>fixture</script>'});
  assert.ok(f.card.shadowRoot.innerHTML.includes('&lt;script&gt;fixture&lt;/script&gt;'));
  assert.ok(!f.card.shadowRoot.innerHTML.includes('<script>fixture</script>'));
  assert.match(f.card.shadowRoot.innerHTML,/80<em>°C/);
});
test('more-info event targets the selected entity', () => {
  const f=fixture();f.card.more('switch.kettle');assert.equal(f.card.lastEvent.type,'hass-more-info');assert.equal(f.card.lastEvent.detail.entityId,'switch.kettle');
});

test('normalizes every known numeric, string and English mode alias', () => {
  const {card}=fixture();
  for (const [raw,label,id] of [[0,'One-click boil','one_click_boil'],[1,'Boil and keep warm','boil_keep_warm'],[2,'Heating and keep warm','heat_keep_warm']]) {
    for (const value of [raw,String(raw),label,label.toUpperCase(),id]) assert.equal(card.normalizeMode(value),id);
  }
});
test('normalizes every known numeric, string and English status alias', () => {
  const {card}=fixture();
  for (const [raw,label,id] of [[1,'Standby','standby'],[2,'Heating','heating'],[3,'Cooling','cooling'],[4,'Keeping warm','keeping_warm']]) {
    for (const value of [raw,String(raw),label,label.toUpperCase(),id]) assert.equal(card.normalizeStatus(value),id);
  }
  assert.equal(card.normalizeStatus('Stand by'),'standby');
});
test('unknown and unavailable aliases never match object prototype properties', () => {
  const {card}=fixture();
  for (const value of [null,undefined,{},true,false,'unknown','unavailable','constructor','toString','__proto__',99,NaN]) {
    assert.equal(card.normalizeMode(value),null);
    assert.equal(card.normalizeStatus(value),null);
  }
});
test('stable 0.1.3 numeric state and beta raw state with TSL descriptions render identically', () => {
  const stable=fixture({'select.kettle_mode':{state:'0',attributes:{options:['0','1','2'],mode_labels:{'0':'One-click boil','1':'Boil and keep warm','2':'Heating and keep warm'}}}});
  const beta=fixture({
    'select.kettle_mode':{state:'0',attributes:{options:['0','1','2'],mode_labels:{'0':'One-click boil','1':'Boil and keep warm','2':'Heating and keep warm'}}},
    'sensor.kettle_status':{state:'1',attributes:{status_label:'Stand by',status_labels:{'1':'Stand by','2':'Heating','3':'Cooling','4':'Keeping warm'}}}
  });
  assert.equal(stable.card.shadowRoot.innerHTML,beta.card.shadowRoot.innerHTML);
  assert.equal(beta.calls.length,0);
});
test('numeric and text status drive the same display, animations and colors for all known values', () => {
  for (const [raw,label,id] of [[1,'Standby','standby'],[2,'Heating','heating'],[3,'Cooling','cooling'],[4,'Keeping warm','keeping_warm']]) {
    for (const power of ['on','off']) {
      const make=value=>fixture({'switch.kettle':{state:power,attributes:{}},'sensor.kettle_status':{state:value,attributes:{}}});
      const numeric=make(raw), text=make(label);
      assert.equal(numeric.card.shadowRoot.innerHTML,text.card.shadowRoot.innerHTML);
      assert.ok(text.card.shadowRoot.innerHTML.includes('state-'+id));
      assert.equal(text.calls.length,0);
    }
  }
});
test('numeric and text mode options have the same friendly display', () => {
  const {card}=fixture();
  for (const [raw,label] of [[0,'One-click boil'],[1,'Boil and keep warm'],[2,'Heating and keep warm']]) {
    assert.equal(card.modeText(raw),card.modeText(label));
  }
});
test('selecting every numeric mode sends only the option supported by HA', async () => {
  for (const options of [['0','1','2'],[0,1,2]]) {
    const f=fixture({'select.kettle_mode':{state:0,attributes:{options}}});
    for (const mode of [0,'1','Heating and keep warm']) { f.card.setMode(mode); await settle(); }
    assert.deepEqual(plain(f.calls.map(c=>c[2].option)),['0','1','2']);
  }
});
test('selecting every labeled mode sends the real label, never internal IDs', async () => {
  const options=['One-click boil','Boil and keep warm','Heating and keep warm'];
  const f=fixture({'select.kettle_mode':{state:options[0],attributes:{options}}});
  for (const mode of ['0','boil_keep_warm',2]) { f.card.setMode(mode); await settle(); }
  assert.deepEqual(plain(f.calls.map(c=>c[2].option)),options);
});
test('mixed option sets support exact selection and refuse ambiguous semantic matches', async () => {
  const f=fixture({'select.kettle_mode':{state:'0',attributes:{options:['0','One-click boil','Custom tea']}}});
  f.card.setMode('one_click_boil');await settle();assert.equal(f.calls.length,0);
  f.card.setMode('Custom tea');await settle();assert.equal(f.calls[0][2].option,'Custom tea');
  f.card.setMode('Not supported');await settle();assert.equal(f.calls.length,1);
});
test('live TSL overrides numeric assumptions for display and option resolution', async () => {
  const f=fixture({
    'select.kettle_mode':{state:'0',attributes:{options:['0','8'],mode_labels:{'0':'Tea profile','8':'Custom setting'}}},
    'sensor.kettle_status':{state:'1',attributes:{status_labels:{'1':'Descaling'}}}
  });
  assert.match(f.card.shadowRoot.innerHTML,/Tea profile/);
  assert.match(f.card.shadowRoot.innerHTML,/Descaling/);
  assert.equal(f.card.normalizeMode('0',{'0':'Tea profile'}),null);
  f.card.setMode('One-click boil');await settle();assert.equal(f.calls.length,0);
  f.card.setMode('8');await settle();assert.equal(f.calls[0][2].option,'8');
});
test('options-only changes rerender and service calls recheck current supported options', async () => {
  const f=fixture(), before=f.card.shadowRoot.innerHTML;
  f.states['select.kettle_mode'].attributes.options=['One-click boil','Boil and keep warm'];
  f.card.hass=f.card._hass;
  assert.notEqual(f.card.shadowRoot.innerHTML,before);
  assert.ok(f.card.shadowRoot.innerHTML.includes('value="One-click boil"'));
  f.card.setMode('0');await settle();assert.equal(f.calls[0][2].option,'One-click boil');
  f.card.setMode('2');await settle();assert.equal(f.calls.length,1);
});
test('labels-only changes rerender even when state and options are unchanged', () => {
  const f=fixture(), before=f.card.shadowRoot.innerHTML;
  f.states['select.kettle_mode'].attributes.mode_labels={'0':'Tea profile'};
  f.states['sensor.kettle_status'].attributes.status_labels={'1':'Descaling'};
  f.card.hass=f.card._hass;
  assert.notEqual(f.card.shadowRoot.innerHTML,before);
  assert.match(f.card.shadowRoot.innerHTML,/Tea profile/);
  assert.match(f.card.shadowRoot.innerHTML,/Descaling/);
  assert.equal(f.calls.length,0);
});
test('malformed or unavailable select states cannot send commands', async () => {
  for (const options of [undefined,null,{},'0,1,2',[]]) {
    const f=fixture({'select.kettle_mode':{state:'0',attributes:{options}}});
    f.card.setMode('0');await settle();assert.equal(f.calls.length,0);
  }
  for (const state of ['unknown','unavailable',null]) {
    const f=fixture({'select.kettle_mode':{state,attributes:{options:['0']}}});
    f.card.setMode('0');await settle();assert.equal(f.calls.length,0);
  }
});
test('unknown status and hostile option labels render safely without service calls', () => {
  const f=fixture({'sensor.kettle_status':{state:'<script>unknown</script>',attributes:{}},
    'select.kettle_mode':{state:'custom',attributes:{options:['custom','<img src=x onerror=alert(1)>']}}});
  assert.ok(!f.card.shadowRoot.innerHTML.includes('<script>'));
  assert.ok(!f.card.shadowRoot.innerHTML.includes('<img src=x'));
  assert.equal(f.calls.length,0);
});
test('auto detection ignores diagnostic and descriptive sensors when raw property sensors exist', () => {
  const f=fixture({
    'sensor.kettle_status_description':{state:'Stand by',attributes:{raw_value:'1'}},
    'sensor.kettle_statusbeschreibung':{state:'Stand by',attributes:{raw_value:'1'}},
    'sensor.kettle_authorization_status':{state:'authorized',attributes:{}},
    'sensor.kettle_connection_status':{state:'connected',attributes:{}},
    'sensor.kettle_session_time_remaining':{state:'4000',attributes:{}}
  },{status_entity:'',time_entity:''});
  assert.equal(f.card.entities().status,'sensor.kettle_status');
  assert.equal(f.card.entities().time,'sensor.kettle_time');
});
test('service failure logs contain no raw backend error details and never retry', async () => {
  const f=fixture();let attempts=0;
  f.card._hass.callService=async()=>{attempts++;throw new Error('PRIVATE_EMAIL_TOKEN_HEADER');};
  await f.card.service('select','select_option',{entity_id:'select.kettle_mode',option:'0'});
  assert.equal(attempts,1);
  assert.ok(!JSON.stringify(f.logs).includes('PRIVATE'));
});

test('mixed numeric/text state and options keep the correct mode selected', () => {
  for (const [raw,label] of [[0,'One-click boil'],[1,'Boil and keep warm'],[2,'Heating and keep warm']]) {
    const textState=fixture({'select.kettle_mode':{state:label,attributes:{options:['0','1','2']}}});
    assert.ok(textState.card.shadowRoot.innerHTML.includes(`value="${raw}" selected`));
    const numericState=fixture({'select.kettle_mode':{state:raw,attributes:{options:['One-click boil','Boil and keep warm','Heating and keep warm']}}});
    assert.ok(numericState.card.shadowRoot.innerHTML.includes(`value="${label}" selected`));
  }
});

const standalone = fs.readFileSync(new URL('../custom_components/aigosmart/frontend/aigosmart-premium-card.source.js', import.meta.url), 'utf8');
test('both card scripts coexist in either order with independent instances', async () => {
  for (const reverse of [false, true]) {
    const registry = new Map();
    class Element {
      attachShadow() { return this.shadowRoot = {innerHTML:'', querySelector:()=>null, querySelectorAll:()=>[]}; }
    }
    const context = vm.createContext({HTMLElement: Element, customElements: {
      get: key => registry.get(key), define: (key, value) => {
        assert.ok(!registry.has(key)); registry.set(key, value);
      }}, window: {}, console: {info: () => {}}});
    for (const script of reverse ? [source, standalone] : [standalone, source]) vm.runInContext(script, context);
    vm.runInContext(source, context);
    assert.equal(registry.size, 2);
    assert.deepEqual(Array.from(context.window.customCards, c => c.type).sort(),
      ['aigosmart-ha-integrated-card', 'aigosmart-premium-card']);
    assert.equal(context.window.customCards.find(c => c.type === 'aigosmart-ha-integrated-card').name, 'AigoSmart HA Integrated');
    const old = new (registry.get('aigosmart-premium-card'))();
    const integrated = new (registry.get('aigosmart-ha-integrated-card'))();
    old.setConfig({name:'old'}); integrated.setConfig({name:'new'});
    integrated.config.presets.push(55);
    assert.equal(old.config.name, 'old');
    assert.ok(!old.config.presets.includes(55));
    const fixtureState = fixture();
    const calls = [];
    const hass = {states:fixtureState.states, callService:async (...args)=>calls.push(args)};
    for (const card of [old, integrated]) {
      card.setConfig({power_entity:'switch.kettle', mode_entity:'select.kettle_mode'});
      card.hass = hass;
    }
    assert.equal(calls.length, 0);
    for (const card of [old, integrated]) { card.setMode('1'); await settle(); }
    assert.equal(calls.length, 2);
    for (const call of calls) assert.deepEqual(plain(call), ['select','select_option',{entity_id:'select.kettle_mode',option:'1'}]);
    assert.equal(old._busy, false);
    assert.equal(integrated._busy, false);
  }
});
test('readable integrated footer is always rendered without service calls', () => {
  const f = fixture();
  assert.match(f.card.shadowRoot.innerHTML, /<div class="integrated-brand">AigoSmart HA Integrated<\/div><\/footer>/);
  assert.match(f.card.css(), /integrated-brand\{color:#c7d5e8;font-size:11px/);
  assert.equal(f.calls.length, 0);
});
