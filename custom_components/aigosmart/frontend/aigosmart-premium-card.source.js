/* AigoSmart Premium Card v0.1.1-beta.1 — Lovelace custom card, no external dependencies */
const AIGOSMART_PREMIUM_CARD_VERSION = '0.1.1-beta.1';
// Stable semantic identifiers are internal only; HA services receive real options.
function enumAlias(value) {
  if (!['string', 'number'].includes(typeof value)) return '';
  return String(value).trim().toLowerCase().replace(/[–—_-]/g, ' ').replace(/\s+/g, ' ');
}
function normalizeMode(value, labels = {}) {
  const key = String(value);
  if (labels && Object.hasOwn(labels, key)) return normalizeMode(labels[key]);
  const modes = {'0':'one_click_boil', 'one click boil':'one_click_boil', 'ein klick kochen':'one_click_boil',
    '1':'boil_keep_warm', 'boil and keep warm':'boil_keep_warm', 'boil keep warm':'boil_keep_warm', 'kochen & warmhalten':'boil_keep_warm',
    '2':'heat_keep_warm', 'heating and keep warm':'heat_keep_warm', 'heat keep warm':'heat_keep_warm', 'erwärmen & warmhalten':'heat_keep_warm'};
  const alias = enumAlias(value);
  return Object.hasOwn(modes, alias) ? modes[alias] : null;
}
function normalizeStatus(value, labels = {}) {
  const key = String(value);
  if (labels && Object.hasOwn(labels, key)) return normalizeStatus(labels[key]);
  const statuses = {'1':'standby', 'standby':'standby', 'stand by':'standby',
    '2':'heating', 'heating':'heating', 'heizt':'heating',
    '3':'cooling', 'cooling':'cooling', 'kühlt ab':'cooling',
    '4':'keeping_warm', 'keeping warm':'keeping_warm', 'hält warm':'keeping_warm'};
  const alias = enumAlias(value);
  return Object.hasOwn(statuses, alias) ? statuses[alias] : null;
}
class AigoSmartPremiumCard extends HTMLElement {
  static getStubConfig() {
    return {
      type: 'custom:aigosmart-premium-card', name: 'Aigostar Wasserkocher',
      power_entity: '', target_entity: '', status_entity: '', mode_entity: '',
      keep_warm_entity: '', time_entity: '', heating_sensor: '',
      animate: true, confirm_start: true, min_temperature: 40,
      presets: [40, 70, 80, 90, 100]
    };
  }
  setConfig(config) {
    this.config = {...AigoSmartPremiumCard.getStubConfig(), ...config};
    this._signature = '';
    this._draft = null;
    this._busy = false;
    this._message = '';
    if (this._hass) this.render();
  }
  set hass(hass) {
    this._hass = hass;
    if (!this.config) return;
    const names = this.entities();
    const sig = JSON.stringify(Object.entries(names).map(([role, id]) => {
      const item = hass.states[id], attrs = item?.attributes || {};
      return [role, id, item?.state ?? null,
        role === 'mode' ? [attrs.options, attrs.mode_labels] :
        role === 'status' ? [attrs.status_labels, attrs.status_label] :
        ['target', 'warm'].includes(role) ? [attrs.min, attrs.max, attrs.step] : null];
    })) + `|${this._busy}|${this._message}`;
    if (sig !== this._signature) { this._signature = sig; this.render(); }
  }
  getCardSize() { return 8; }
  esc(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }
  entities() {
    const states = this._hass?.states || {};
    const find = (domain, needle, exclude = []) => {
      const matches = Object.keys(states).filter(id => id.startsWith(domain + '.') &&
        /aigo|kettle|wasserkocher/i.test(id) && id.toLowerCase().includes(needle) &&
        !exclude.some(fragment => id.includes(fragment)) &&
        !(domain === 'sensor' && Object.hasOwn(states[id]?.attributes || {}, 'raw_value')));
      return matches.length === 1 ? matches[0] : '';
    };
    return {
      power: this.config.power_entity || find('switch', 'heatingswitch'),
      target: this.config.target_entity || find('number', 'target_temperature'),
      status: this.config.status_entity || find('sensor', 'status', ['authorization_status', 'connection_status', 'status_description']),
      mode: this.config.mode_entity || find('select', 'mode'),
      warm: this.config.keep_warm_entity || find('number', 'heatpreservation'),
      time: this.config.time_entity || find('sensor', 'time', ['session_time_remaining', 'refresh', 'last_successful', 'expires_at']),
      heating: this.config.heating_sensor || find('binary_sensor', 'heatingswitch')
    };
  }
  state(id) { return id ? this._hass?.states?.[id] : null; }
  num(id) { const s = this.state(id)?.state; if (!s || ['unknown','unavailable'].includes(s)) return NaN; const n = Number(String(s).replace(',','.')); return Number.isFinite(n) ? n : NaN; }
  more(id) { if (id) this.dispatchEvent(new CustomEvent('hass-more-info', {detail:{entityId:id}, bubbles:true, composed:true})); }
  normalizeMode(value, labels) { return normalizeMode(value, labels); }
  normalizeStatus(value, labels) { return normalizeStatus(value, labels); }
  modeOptions() {
    const options = this.state(this.entities().mode)?.attributes?.options;
    return Array.isArray(options) ? options.filter(opt => typeof opt === 'string' || typeof opt === 'number' && Number.isFinite(opt)) : [];
  }
  modeText(option, labels) {
    if (labels && typeof labels[String(option)] === 'string') return labels[String(option)];
    return ({one_click_boil:'Ein-Klick-Kochen', boil_keep_warm:'Kochen & Warmhalten',
      heat_keep_warm:'Erwärmen & Warmhalten'})[normalizeMode(option)] || String(option);
  }
  statusText(raw, powerOn, labels) {
    const names = {standby:'Standby', heating:'Heizt', cooling:'Kühlt ab', keeping_warm:'Hält warm'};
    const status = normalizeStatus(raw, labels);
    if (status) return names[status];
    if (labels && typeof labels[String(raw)] === 'string') return labels[String(raw)];
    if (!enumAlias(raw) || ['unknown','unavailable'].includes(enumAlias(raw))) return powerOn ? 'Heizt' : 'Nicht verfügbar';
    return `Status ${raw}`;
  }
  glow(target, active) {
    // Target temperature governs warmth, but standby gets a restrained blue aura.
    if (!active) return {color:'#60a5fa', soft:'rgba(72,136,244,.20)', level:.30};
    const value = Number.isFinite(target) ? Math.min(100, Math.max(40,target)) : 80;
    if (value < 60) return {color:'#62baff',soft:'rgba(57,158,255,.24)',level:.54};
    if (value < 80) return {color:'#ffc17c',soft:'rgba(255,168,74,.28)',level:.70};
    if (value < 90) return {color:'#ff9a55',soft:'rgba(255,123,44,.31)',level:.86};
    return {color:'#ff704b',soft:'rgba(255,93,44,.36)',level:1};
  }
  async service(domain, action, data) {
    if (this._busy) return;
    this._busy = true; this._message = ''; this._signature = ''; this.render();
    try { await this._hass.callService(domain, action, data); this._message = 'Befehl gesendet · Status wird aktualisiert'; }
    catch (error) { this._message = 'Befehl fehlgeschlagen. Verbindung und HA-Protokoll prüfen.'; console.error('AigoSmart card service failure'); }
    finally { this._busy = false; this._signature = ''; this.render(); }
  }
  power() {
    const e = this.entities(), state = this.state(e.power)?.state;
    if (!e.power || !['on','off'].includes(state)) return;
    if (state === 'off' && this.config.confirm_start !== false && !window.confirm('Wasserkocher einschalten? Bitte sicherstellen, dass genügend Wasser eingefüllt ist und das Gerät beaufsichtigt wird.')) return;
    this.service('switch', state === 'on' ? 'turn_off' : 'turn_on', {entity_id:e.power});
  }
  setTemperature(value) {
    const id = this.entities().target, item = this.state(id);
    if (!item || ['unavailable','unknown'].includes(item.state)) return;
    const min = Number.isFinite(Number(item.attributes?.min)) ? Number(item.attributes.min) : Number(this.config.min_temperature);
    const max = Number.isFinite(Number(item.attributes?.max)) ? Number(item.attributes.max) : 100;
    const temp = Number(value);
    if (!Number.isInteger(temp) || temp < min || temp > max) return;
    this._draft = null;
    this.service('number','set_value',{entity_id:id,value:temp});
  }
  supportedMode(requested) {
    if (!['string','number'].includes(typeof requested)) return undefined;
    const item = this.state(this.entities().mode), options = this.modeOptions();
    const exact = options.find(opt => String(opt) === String(requested));
    if (exact !== undefined) return exact;
    const labels = item?.attributes?.mode_labels, mode = normalizeMode(requested, labels);
    const matches = mode ? options.filter(opt => normalizeMode(opt, labels) === mode) : [];
    return matches.length === 1 ? matches[0] : undefined;
  }
  setMode(requested) {
    const id = this.entities().mode, item = this.state(id);
    if (!id || !item || !enumAlias(item.state) || ['unknown', 'unavailable'].includes(enumAlias(item.state))) return;
    const option = this.supportedMode(requested);
    if (option !== undefined) this.service('select','select_option',{entity_id:id,option:String(option)});
  }
  setWarm(delta) {
    const id = this.entities().warm, n = this.num(id);
    if (!id || !Number.isFinite(n)) return;
    const item = this.state(id), min = Number(item.attributes.min ?? 0), max = Number(item.attributes.max ?? 13), step = Number(item.attributes.step ?? 1);
    this.service('number','set_value',{entity_id:id,value:Math.max(min,Math.min(max,n+delta*step))});
  }
  kettleSvg(active, color) {
    return `<svg class="kettle-svg" viewBox="0 0 320 340" role="img" aria-label="Aigostar Wasserkocher">
      <defs>
        <linearGradient id="kBody" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0b111a"/><stop offset=".15" stop-color="#343943"/><stop offset=".44" stop-color="#181e29"/><stop offset=".76" stop-color="#0b1019"/><stop offset="1" stop-color="#252a33"/></linearGradient>
        <linearGradient id="kLid" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#818995"/><stop offset="1" stop-color="#292d36"/></linearGradient>
        <linearGradient id="kHandle" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#454b54"/><stop offset=".55" stop-color="#141922"/><stop offset="1" stop-color="#363c46"/></linearGradient>
        <radialGradient id="kHalo"><stop offset="0" stop-color="${color}" stop-opacity=".62"/><stop offset=".5" stop-color="${color}" stop-opacity=".20"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient>
        <filter id="kShadow" x="-40%" y="-40%" width="180%" height="190%"><feDropShadow dx="0" dy="15" stdDeviation="14" flood-color="#000" flood-opacity=".62"/></filter>
      </defs>
      <ellipse class="halo" cx="160" cy="186" rx="148" ry="145" fill="url(#kHalo)"/>
      <ellipse class="floor-glow" cx="158" cy="307" rx="107" ry="19" fill="${color}" opacity=".20"/>
      <g class="steam ${active?'steam-on':''}" stroke="${color}" stroke-linecap="round" fill="none">
        <path d="M105 55 C86 31 120 24 104 -4"/><path d="M155 47 C136 21 169 14 156 -18"/><path d="M205 55 C188 33 219 20 207 -7"/>
      </g>
      <g filter="url(#kShadow)">
        <path d="M231 86 L259 89 Q302 95 301 131 L299 240 Q298 268 273 269 L243 268 L243 242 L269 243 Q277 244 278 230 L278 133 Q278 118 260 116 L232 117 Z" fill="url(#kHandle)" stroke="#8c949d" stroke-opacity=".27" stroke-width="2"/>
        <path d="M79 94 L47 89 Q43 88 40 99 L78 118Z" fill="#454b55" stroke="#b3bac4" stroke-opacity=".22"/>
        <path d="M81 90 Q82 76 96 74 L218 74 Q235 76 237 92 L235 275 Q234 292 220 298 Q162 313 95 298 Q79 293 79 276Z" fill="url(#kBody)" stroke="#84909e" stroke-opacity=".26" stroke-width="1.8"/>
        <ellipse cx="157" cy="81" rx="77" ry="17" fill="#10151d" stroke="#939ba6" stroke-opacity=".35" stroke-width="2"/>
        <ellipse cx="156" cy="75" rx="72" ry="12" fill="url(#kLid)"/>
        <ellipse cx="156" cy="71" rx="20" ry="3.5" fill="#ced2d9" opacity=".75"/>
        <path d="M92 96 L92 284" stroke="#c5d1e5" stroke-opacity=".09" stroke-width="3"/>
        <path d="M229 103 L229 276" stroke="#000" stroke-opacity=".43" stroke-width="6"/>
        <path d="M98 290 Q162 308 220 290" fill="none" stroke="#7e8791" stroke-opacity=".2"/>
        <text x="157" y="258" text-anchor="middle" fill="#c2c9d2" font-size="14" font-family="Arial, sans-serif" letter-spacing="2.5">AIGOSTAR</text>
        <rect x="292" y="151" width="3" height="54" rx="1.5" fill="${color}" class="led"/>
      </g>
    </svg>`;
  }
  render() {
    if (!this.config || !this._hass) return;
    if (!this.shadowRoot) this.attachShadow({mode:'open'});
    const e = this.entities(), power = this.state(e.power)?.state,
      active = power === 'on', offline = !['on','off'].includes(power),
      status = this.state(e.status)?.state, statusLabels = this.state(e.status)?.attributes?.status_labels,
      semanticStatus = normalizeStatus(status, statusLabels),
      activity = offline ? 'unavailable' : semanticStatus || (active ? 'heating' : 'standby'),
      visualActive = !offline && active && ['heating', 'keeping_warm'].includes(activity), target = this.num(e.target), warm = this.num(e.warm),
      time = this.num(e.time), modeState = this.state(e.mode), options = this.modeOptions(),
      mood = this.glow(target,visualActive), tMin = Math.max(0,Number(this.state(e.target)?.attributes?.min ?? this.config.min_temperature)),
      tMax = Math.min(100,Number(this.state(e.target)?.attributes?.max ?? 100)),
      displayed = Number.isFinite(this._draft) ? this._draft : (Number.isFinite(target) ? target : tMin),
      modeLabels = modeState?.attributes?.mode_labels, selectedMode = this.supportedMode(modeState?.state),
      optionsHtml = options.map(opt => `<option value="${this.esc(opt)}" ${String(opt)===String(selectedMode)?'selected':''}>${this.esc(this.modeText(opt, modeLabels))}</option>`).join('');
    this.shadowRoot.innerHTML = `<style>${this.css()}</style>
      <ha-card style="--heat:${mood.color};--heat-soft:${mood.soft};--heat-power:${mood.level}" class="${visualActive?'on':'off'} state-${activity} ${offline?'offline':''} ${this.config.animate===false?'no-animation':''}">
        <header><div class="brand"><ha-icon icon="mdi:kettle-steam"></ha-icon></div><div class="heading"><div class="name">${this.esc(this.config.name)}</div><div class="status"><i></i>${this.esc(offline?'Nicht verfügbar':this.statusText(status,active,statusLabels))}</div></div><button class="icon-button" data-a="more" title="Gerätedetails"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button><button class="power ${active?'engaged':''}" data-a="power" aria-label="${active?'Ausschalten':'Einschalten'}" ${offline||this._busy?'disabled':''}><ha-icon icon="mdi:power"></ha-icon></button></header>
        <section class="hero"><div class="heater-ring"></div><div class="device">${this.kettleSvg(visualActive && activity === 'heating',mood.color)}</div><div class="readout"><small>ZIElTEMPERATUR</small><div class="big">${Number.isFinite(target)?target.toFixed(0):'–'}<em>°C</em></div><div class="tag">${'● '+this.esc(this.statusText(status,active,statusLabels))}</div><div class="caption">${active?'Temperaturziel · nicht die aktuelle Wassertemperatur':'Bereit für den nächsten Start'}</div></div></section>
        <section class="temperature"><div class="section-top"><div><small>TEMPERATUR</small><strong>Temperatur einstellen</strong></div><span class="draft-value">${Math.round(displayed)}°C</span></div><input class="temp-range" data-a="temp-range" type="range" min="${tMin}" max="${tMax}" step="${this.state(e.target)?.attributes?.step || 1}" value="${Math.min(tMax,Math.max(tMin,displayed))}" ${!e.target||offline||this._busy?'disabled':''} aria-label="Zieltemperatur"/><div class="temp-actions"><div class="presets">${this.config.presets.filter(x=>x>=tMin&&x<=tMax).map(n=>`<button data-temp="${Number(n)}" class="${Math.round(displayed)===n?'selected':''}" ${offline||this._busy?'disabled':''}>${n}°</button>`).join('')}</div><button class="apply" data-a="apply-temp" ${offline||this._busy||!e.target?'disabled':''}>Übernehmen <ha-icon icon="mdi:check"></ha-icon></button></div></section>
        <div class="controls"><section class="control"><div class="control-heading"><ha-icon icon="mdi:creation"></ha-icon><div><small>BETRIEBSMODUS</small><strong>Modus auswählen</strong></div></div><select data-a="mode" ${!e.mode||!modeState||!options.length||['unknown','unavailable'].includes(enumAlias(modeState.state))||offline||this._busy?'disabled':''}>${optionsHtml || '<option value="">Nicht verfügbar</option>'}</select></section>
        <section class="control"><div class="control-heading"><ha-icon icon="mdi:clock-outline"></ha-icon><div><small>WARMHALTEN</small><strong>Warmhaltezeit</strong></div></div><div class="stepper"><button data-a="warm-down" ${!e.warm||offline||this._busy?'disabled':''} aria-label="Zeit verringern"><ha-icon icon="mdi:minus"></ha-icon></button><span>${Number.isFinite(warm)?warm+' h':'–'}</span><button data-a="warm-up" ${!e.warm||offline||this._busy?'disabled':''} aria-label="Zeit erhöhen"><ha-icon icon="mdi:plus"></ha-icon></button></div></section></div>
        <section class="stats"><button data-more="${this.esc(e.status)}"><ha-icon icon="mdi:information-outline"></ha-icon><span>Status</span><b>${this.esc(this.statusText(status,active,statusLabels))}</b></button><button data-more="${this.esc(e.time)}"><ha-icon icon="mdi:timer-outline"></ha-icon><span>Zeit</span><b>${Number.isFinite(time)?time+' min':'–'}</b></button></section>
        ${!e.power||!e.target||!e.mode?`<div class="notice"><ha-icon icon="mdi:alert-circle-outline"></ha-icon>Entitäten nicht vollständig erkannt. Bitte Entity-IDs in der Kartenkonfiguration angeben.</div>`:''}
        <div class="message" role="status" aria-live="polite">${this.esc(this._message)}</div><footer>AIGOSMART <span>·</span> PREMIUM CONTROL <span>·</span> ${AIGOSMART_PREMIUM_CARD_VERSION}</footer>
      </ha-card>`;
    this.bind();
  }
  bind() {
    const root = this.shadowRoot, $ = selector => root.querySelector(selector);
    $('[data-a="power"]')?.addEventListener('click',()=>this.power());
    $('[data-a="more"]')?.addEventListener('click',()=>this.more(this.entities().power));
    const slider = $('[data-a="temp-range"]');
    slider?.addEventListener('input',()=>{this._draft=Number(slider.value); const el=$('.draft-value');if(el)el.textContent=`${slider.value}°C`;root.querySelectorAll('[data-temp]').forEach(b=>b.classList.toggle('selected',Number(b.dataset.temp)===this._draft));});
    root.querySelectorAll('[data-temp]').forEach(b=>b.addEventListener('click',()=>{this._draft=Number(b.dataset.temp);if(slider)slider.value=this._draft;$('.draft-value').textContent=`${this._draft}°C`;root.querySelectorAll('[data-temp]').forEach(x=>x.classList.toggle('selected',x===b));}));
    $('[data-a="apply-temp"]')?.addEventListener('click',()=>this.setTemperature(Number.isFinite(this._draft)?this._draft:this.num(this.entities().target)));
    $('[data-a="mode"]')?.addEventListener('change',event=>this.setMode(event.target.value));
    $('[data-a="warm-down"]')?.addEventListener('click',()=>this.setWarm(-1));
    $('[data-a="warm-up"]')?.addEventListener('click',()=>this.setWarm(1));
    root.querySelectorAll('[data-more]').forEach(b=>b.addEventListener('click',()=>this.more(b.dataset.more)));
  }
  css() { return `
    :host{display:block;min-width:0;container-type:inline-size;font-family:var(--paper-font-body1_-_font-family,Inter,system-ui,sans-serif)}*{box-sizing:border-box}ha-card{display:block;position:relative;isolation:isolate;overflow:hidden;padding:23px;color:#e9f0fa;border-radius:27px;background:radial-gradient(ellipse at 33% 25%,var(--heat-soft),transparent 58%),linear-gradient(145deg,#131c2c,#080d18 78%);border:1px solid #b6d5ff1c;box-shadow:0 22px 60px #0005,inset 0 1px #ffffff0b}button,select,input{font:inherit}button{cursor:pointer;color:inherit;touch-action:manipulation}button:disabled,select:disabled,input:disabled{opacity:.38;cursor:not-allowed}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--heat);outline-offset:3px}header{display:flex;align-items:center;gap:11px}.brand{width:46px;height:46px;display:grid;place-items:center;flex-shrink:0;border-radius:15px;background:linear-gradient(145deg,#253951,#0f1d30);border:1px solid #95c9ff23;color:#93cbff}.brand ha-icon{--mdc-icon-size:25px}.heading{min-width:0;flex:1}.name{font-size:21px;font-weight:650;letter-spacing:-.65px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.status{display:flex;align-items:center;gap:7px;margin-top:4px;color:#97a8bf;font-size:11px}.status i{width:6px;height:6px;border-radius:50%;background:#6799cc;box-shadow:0 0 8px #408bd77a}.on .status i{background:var(--heat);box-shadow:0 0 12px var(--heat)}.power,.icon-button{width:39px;height:39px;display:grid;place-items:center;border:1px solid #9acaff27;border-radius:12px;background:#9bbdff09}.power ha-icon{color:var(--heat)}.power.engaged{background:var(--heat-soft);border-color:var(--heat)}.icon-button ha-icon{color:#a3b4ca}.hero{position:relative;min-height:315px;margin:19px 0 15px;border-radius:21px;overflow:hidden;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,.88fr);align-items:center;padding:11px 19px 12px 6px;background:radial-gradient(ellipse at 28% 80%,var(--heat-soft),transparent 70%),linear-gradient(125deg,#050a1399,#0a101abb);border:1px solid #a6caff14}.heater-ring{position:absolute;left:3%;top:4%;width:56%;height:90%;border-radius:50%;background:radial-gradient(ellipse,var(--heat-soft),transparent 70%);filter:blur(15px);opacity:.8;pointer-events:none}.on .heater-ring{animation:ringPulse 3s ease-in-out infinite}.device{position:relative;min-width:0;height:297px;display:grid;place-items:center}.kettle-svg{height:100%;width:110%;max-width:350px;overflow:visible}.halo{opacity:.3;transition:opacity .7s}.on .halo{opacity:1;animation:haloPulse 3.5s ease-in-out infinite}.floor-glow{filter:blur(8px);transition:opacity .5s}.led{filter:drop-shadow(0 0 6px var(--heat));opacity:.6}.on .led{opacity:1}.steam{opacity:0;stroke-width:3;filter:drop-shadow(0 0 7px var(--heat))}.steam path{stroke-dasharray:30 18;stroke-dashoffset:0}.steam-on{opacity:.7}.steam-on path{animation:steamRise 3s linear infinite}.steam-on path:nth-child(2){animation-duration:3.6s;animation-delay:-1.1s}.steam-on path:nth-child(3){animation-duration:4s;animation-delay:-1.7s}.readout{position:relative;z-index:1;min-width:0}.readout small,.section-top small,.control-heading small{display:block;color:#95a8c2;font-size:9px;letter-spacing:1.25px}.big{white-space:nowrap;margin:9px 0 11px;font-size:52px;letter-spacing:-2.8px;font-weight:420;font-variant-numeric:tabular-nums}.big em{font-size:20px;font-style:normal;letter-spacing:-.3px;color:var(--heat)}.tag{display:inline-block;padding:7px 10px;border-radius:8px;background:var(--heat-soft);border:1px solid #ffffff17;color:var(--heat);font-size:10px;font-weight:650}.caption{font-size:10px;line-height:1.6;color:#8699b1;margin-top:12px;max-width:190px}.temperature,.control{border:1px solid #a6caff16;background:linear-gradient(140deg,#8baaff09,#8baaff03);border-radius:16px}.temperature{padding:16px}.section-top{display:flex;justify-content:space-between;align-items:center;gap:10px}.section-top strong{display:block;margin-top:6px;font-size:14px;font-weight:550}.draft-value{font-size:28px;font-weight:550;letter-spacing:-1px;color:var(--heat);font-variant-numeric:tabular-nums}.temp-range{appearance:none;-webkit-appearance:none;display:block;width:100%;height:8px;border-radius:100px;margin:21px 0 20px;outline:none;background:linear-gradient(to right,#57acff,#7cb9ff 26%,#ffbf75 62%,#ff684f 100%)}.temp-range::-webkit-slider-thumb{-webkit-appearance:none;width:23px;height:23px;border-radius:50%;background:#e9f5ff;border:4px solid var(--heat);box-shadow:0 0 0 5px var(--heat-soft),0 4px 12px #0008;cursor:pointer}.temp-range::-moz-range-thumb{width:17px;height:17px;border-radius:50%;background:#e9f5ff;border:4px solid var(--heat);box-shadow:0 0 0 5px var(--heat-soft);cursor:pointer}.temp-actions{display:flex;gap:8px;align-items:center;justify-content:space-between}.presets{display:flex;gap:5px;flex-wrap:wrap}.presets button,.apply{border:1px solid #a4c8ee20;background:#abcfff09;border-radius:9px;padding:9px 10px;font-size:11px}.presets button.selected{color:var(--heat);background:var(--heat-soft);border-color:var(--heat)}.apply{display:flex;align-items:center;gap:5px;white-space:nowrap;color:var(--heat);border-color:var(--heat)}.apply ha-icon{--mdc-icon-size:15px}.controls{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.control{padding:14px;min-width:0}.control-heading{display:flex;align-items:center;gap:10px;margin-bottom:14px}.control-heading ha-icon{color:var(--heat);--mdc-icon-size:22px}.control-heading strong{font-size:11px;font-weight:550;display:block;margin-top:5px}.control select{width:100%;max-width:100%;padding:10px 7px;border-radius:9px;border:1px solid #b4cbe52b;color:#d5e4f7;background:#101b2b;font-size:11px;outline:none}.stepper{display:flex;align-items:center;justify-content:space-between;gap:5px}.stepper button{display:grid;place-items:center;flex-shrink:0;width:34px;height:34px;border-radius:9px;background:#9bbfff0c;border:1px solid #9bbfff22}.stepper ha-icon{--mdc-icon-size:17px;color:var(--heat)}.stepper span{font-size:16px;font-weight:550;white-space:nowrap}.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.stats button{display:flex;gap:8px;align-items:center;min-width:0;border:1px solid #a6caff12;background:#9bbfff05;border-radius:13px;padding:12px;text-align:left}.stats ha-icon{color:var(--heat);--mdc-icon-size:17px}.stats span{font-size:10px;color:#9baec5;flex:1}.stats b{font-size:11px;font-weight:600;white-space:nowrap}.notice{display:flex;align-items:center;gap:8px;color:#f5c287;background:#ffbd720c;padding:11px;margin-top:12px;border-radius:11px;font-size:11px}.notice ha-icon{--mdc-icon-size:17px;flex-shrink:0}.message{font-size:10px;margin-top:11px;color:#b9cce2;min-height:0}.message:empty{display:none}footer{text-align:center;color:#667b96;font-size:8px;letter-spacing:2px;padding-top:17px;margin-top:17px;border-top:1px solid #aac4e51a}footer span{color:var(--heat)}.offline .device{opacity:.43}.no-animation *,.no-animation *::before,.no-animation *::after{animation:none!important;transition:none!important}@keyframes steamRise{to{stroke-dashoffset:-96;transform:translateY(-10px)}}@keyframes haloPulse{0%,100%{opacity:.7}50%{opacity:1}}@keyframes ringPulse{0%,100%{opacity:.55}50%{opacity:1}}@container(max-width:440px){ha-card{padding:16px;border-radius:23px}.brand{width:40px;height:40px}.name{font-size:18px}.power,.icon-button{width:35px;height:35px}.hero{min-height:252px;padding:8px 11px 9px 0;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr)}.device{height:244px}.kettle-svg{width:120%}.big{font-size:38px;letter-spacing:-2px}.big em{font-size:15px}.readout small{font-size:8px}.caption{font-size:9px}.temperature{padding:13px}.presets button{padding:8px 7px}.apply{padding:8px 7px}.controls{gap:8px}.control{padding:10px}.control-heading{gap:7px}.control-heading ha-icon{--mdc-icon-size:18px}.control-heading strong{font-size:10px}.control-heading small{font-size:8px}.stepper button{width:29px;height:32px}}@container(max-width:310px){.hero{grid-template-columns:1fr}.device{height:220px}.kettle-svg{width:95%}.readout{text-align:center;padding-bottom:15px}.caption{max-width:none}.controls{grid-template-columns:1fr}.temp-actions{flex-direction:column;align-items:stretch}.apply{justify-content:center}.stats{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
  `; }
}
if (!customElements.get('aigosmart-premium-card')) customElements.define('aigosmart-premium-card', AigoSmartPremiumCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(c => c.type === 'aigosmart-premium-card')) window.customCards.push({type:'aigosmart-premium-card',name:'AigoSmart Premium Card',description:'Animierte Premium-Steuerung für Aigostar Wasserkocher',preview:true});
console.info(`AigoSmart Premium Card v${AIGOSMART_PREMIUM_CARD_VERSION}`);
