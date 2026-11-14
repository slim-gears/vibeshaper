/* VibeShaper chat panel.
 *
 * Talks to VibeShaper.py through Fusion's palette bridge:
 *   panel -> Python: adsk.fusionSendData(action, JSON)
 *   Python -> panel: fusionJavaScriptHandler.handle('event', JSON)
 * Outside Fusion (a normal browser) it runs against MockBackend so the UI can be reviewed.
 * All model/user text is inserted as text nodes, never as HTML.
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------- helpers
  const $ = (id) => document.getElementById(id);

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
        else if (k === 'text') el.textContent = v;
        else el.setAttribute(k, v === true ? '' : v);
      }
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  function icon(name, cls) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'i' + (cls ? ' ' + cls : ''));
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS(ns, 'use');
    use.setAttribute('href', '#i-' + name);
    svg.append(use);
    return svg;
  }

  const fmtChars = (n) => (n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(n || 0));
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  const firstLine = (s) => String(s || '').trim().split('\n').filter(Boolean)[0] || '';

  // Pretty JSON that keeps short arrays (points, lists of ids) on one line.
  function pretty(obj) {
    let s = JSON.stringify(obj, null, 2);
    for (let pass = 0; pass < 3; pass++) {
      s = s.replace(/\[\s*\n([^\[\]{}]*?)\n\s*\]/g, (m, inner) => {
        const flat = '[' + inner.trim().split(/,\s*\n\s*/).join(', ') + ']';
        return flat.length <= 60 ? flat : m;
      });
    }
    return s;
  }

  function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  // ---------------------------------------------------------------- state
  const S = {
    chats: [],          // [{id, title, versions}]
    chat: null,         // active chat view (see chat.py Chat.to_view)
    providers: [],      // [{id, name, short_name, schema:[field], values:{}, model, model_options:{}, models:[{id,label,images,thinking,tools}], configured}]
    activeProvider: null,
    busy: false,
    paramsOpen: false,
    paramState: {},     // name -> {status:'saving'|'ok'|'err', error}
    sheet: null,        // {version, editable}
    models: {},         // provider id -> {loading, error, checked, testing}
    pickerQuery: '',
    general: { theme: 'system', auto_fix: 2, default_mode: 'component' },
    components: true,   // false in Part Design documents (one component only)
    settings: { open: false, page: null },  // page: 'general' | provider id | null (narrow: list)
  };

  // ---------------------------------------------------------------- bridge
  let backend = null;

  function send(action, payload) {
    const data = JSON.stringify(payload || {});
    try {
      return Promise.resolve(backend(action, data));
    } catch (e) {
      console.error('VibeShaper bridge error', e);
      toast('Could not reach VibeShaper');
      return Promise.resolve('');
    }
  }

  window.fusionJavaScriptHandler = {
    handle(action, data) {
      try {
        if (action === 'event') onEvent(JSON.parse(data));
      } catch (e) {
        console.error('VibeShaper event error', e, data);
      }
      return 'OK';
    },
  };

  function connect() {
    const start = Date.now();
    const forceMock = /[?&]mock\b/.test(location.search);
    (function attempt() {
      if (!forceMock && window.adsk && typeof window.adsk.fusionSendData === 'function') {
        backend = (action, data) => window.adsk.fusionSendData(action, data);
        send('ready');
      } else if (forceMock || Date.now() - start > 1200) {
        backend = MockBackend.create(onEvent);
        send('ready');
      } else {
        setTimeout(attempt, 50);
      }
    })();
  }

  // ---------------------------------------------------------------- events from Python
  function onEvent(ev) {
    switch (ev.type) {
      case 'state':
        S.chats = ev.chats || [];
        S.chat = ev.chat || null;
        S.providers = ev.providers || S.providers;
        S.activeProvider = ev.active_provider || S.activeProvider;
        if (ev.general) { S.general = Object.assign({}, S.general, ev.general); applyTheme(); }
        S.components = ev.components !== false;
        S.busy = !!ev.busy;
        S.paramState = {};
        renderAll();
        renderSettingsView();
        break;
      case 'chat':
        S.chat = ev.chat;
        if (ev.chats) S.chats = ev.chats;
        if ('busy' in ev) S.busy = !!ev.busy;
        renderAll();
        break;
      case 'stream':
        applyStream(ev);
        break;
      case 'models': {
        const p = provider(ev.provider);
        const m = modelState(ev.provider);
        Object.assign(m, { loading: false, error: ev.error || '', checked: true });
        if (p) p.models = ev.models || [];
        renderHeader();
        if (openPop && openPop.pop === $('modelMenu')) renderModelMenu();
        renderSettingsView();
        break;
      }
      case 'provider_status': {
        const p = provider(ev.provider);
        if (!p || p.configured === !!ev.configured) break;
        p.configured = !!ev.configured;
        renderHeader();
        patchProviderStatus(p);
        break;
      }
      case 'param':
        S.paramState[ev.name] = ev.ok ? { status: 'ok' }
          : { status: 'err', error: ev.error, draft: (S.paramState[ev.name] || {}).draft };
        if (ev.ok && ev.chat) S.chat = ev.chat;
        renderParams();
        if (ev.ok) setTimeout(() => { if (S.paramState[ev.name]?.status === 'ok') { delete S.paramState[ev.name]; renderParams(); } }, 1600);
        break;
      case 'json_check':
        showJsonCheck(ev);
        break;
      case 'toast':
        toast(ev.text);
        break;
    }
  }

  function applyStream(ev) {
    if (!S.chat || S.chat.id !== ev.chat_id) return;
    const t = S.chat.turns.find((x) => x.id === ev.turn_id);
    if (!t) return;
    const statusChanged = ev.status && ev.status !== t.status;
    if (ev.status) t.status = ev.status;
    if (ev.thought_append) t.thought = (t.thought || '') + ev.thought_append;
    if (ev.chars !== undefined) t.chars = ev.chars;
    if (ev.attempt_error) (t.attempts = t.attempts || []).push({ error: ev.attempt_error });
    if (ev.tool) (t.tools = t.tools || []).push(ev.tool);
    if (ev.progress) t.progress = ev.progress;
    if (statusChanged || ev.attempt_error || ev.tool) {
      patchTurn(t);
    } else {
      // Cheap path: only touch the bits that change while streaming.
      const node = document.querySelector(`[data-turn="${t.id}"]`);
      if (!node) return patchTurn(t);
      const stick = nearBottom();
      const pre = node.querySelector('.thought-text');
      if (ev.thought_append) {
        if (!pre) return patchTurn(t);
        pre.textContent = t.thought;
        pre.scrollTop = pre.scrollHeight;
        const sum = node.querySelector('.thinking summary .count');
        if (sum) sum.textContent = fmtChars(t.thought.length) + ' chars';
      }
      const w = node.querySelector('.writing-count');
      if (w && ev.chars !== undefined) w.textContent = fmtChars(ev.chars) + ' chars';
      if (ev.progress) {
        const old = node.querySelector('.build-progress');
        const count = old && old.querySelector('.count');
        if (!old || !count) return patchTurn(t);
        const p = t.progress;
        old.querySelector('.fill').style.width = (p.total ? Math.min(100, Math.round((100 * p.done) / p.total)) : 0) + '%';
        old.querySelector('.bar').setAttribute('aria-valuenow', String(p.done));
        old.querySelector('.label').textContent = p.label || '';
        count.textContent = `${p.done} / ${p.total}`;
      }
      if (stick) scrollToBottom();
    }
  }

  // ---------------------------------------------------------------- derived
  const provider = (id) => S.providers.find((p) => p.id === id);
  const activeProv = () => provider(S.activeProvider) || S.providers[0];
  const versionOf = (n) => (S.chat ? S.chat.versions.find((v) => v.n === n) : null);
  const currentVersion = () => (S.chat && S.chat.current != null ? versionOf(S.chat.current) : null);
  const nextVersionNumber = () => (S.chat && S.chat.versions.length ? S.chat.versions[S.chat.versions.length - 1].n + 1 : 1);

  // ---------------------------------------------------------------- rendering
  function renderAll() {
    renderHeader();
    renderThread();
    renderParams();
    renderComposer();
  }

  function renderHeader() {
    $('chatTitle').textContent = S.chat && S.chat.turns.length ? S.chat.title : 'New chat';
    const p = activeProv();
    const model = p && p.model;
    const ok = !!(p && p.configured && model);
    const label = model ? modelLabel(p, model) : '';
    $('modelName').textContent = !p ? 'Choose a model' : !p.configured ? `${shortProv(p)} · set up` : model ? `${shortProv(p)} · ${label}` : `${shortProv(p)} · choose model`;
    $('modelChip').title = ok ? `${p.name} · ${model} (change model)` : 'Choose a model';
    $('modelDot').className = 'dot ' + (ok ? 'ok' : 'warn');
  }

  const shortProv = (p) => p.short_name || p.name || p.id;
  const modelInfo = (p, id) => (p.models || []).find((m) => m.id === id) || null;
  const modelLabel = (p, id) => { const m = modelInfo(p, id); return (m && m.label) || id; };

  // Follow new content only while the user is at the bottom; tracked from their own scrolling
  // so re-renders (which change scrollHeight) can't flip it.
  let stuckToBottom = true;
  const nearBottom = () => stuckToBottom;

  function scrollToBottom() {
    const el = $('thread');
    el.scrollTop = el.scrollHeight;
  }

  function renderThread() {
    const root = $('threadInner');
    const stick = nearBottom();
    root.replaceChildren();
    if (!S.chat || !S.chat.turns.length) {
      root.append(renderEmpty());
      return;
    }
    for (const t of S.chat.turns) root.append(renderTurn(t));
    $('thread').setAttribute('aria-busy', S.busy ? 'true' : 'false');
    if (stick) requestAnimationFrame(scrollToBottom);
  }

  function patchTurn(t) {
    const old = document.querySelector(`[data-turn="${t.id}"]`);
    const stick = nearBottom();
    if (old) old.replaceWith(renderTurn(t));
    else renderThread();
    if (stick) requestAnimationFrame(scrollToBottom);
  }

  const EXAMPLES = [
    ['Mounting bracket', 'A heavy-duty mounting bracket with a 50x80mm base, 5mm thickness, 4 corner bolt holes of 6mm diameter, and a central vertical lug with a 12mm hole.'],
    ['Flanged pipe elbow', 'A 90-degree pipe elbow with 30mm outer diameter, 3mm wall, swept over an 80mm radius, with an 80mm round mounting flange with 6 bolt holes on a 60mm bolt circle.'],
    ['Compression spring', 'A compression spring with 25mm outer diameter, 3mm wire diameter, 6 active turns, and 8mm pitch.'],
    ['Enclosure', 'A hollow electronics enclosure 80x120x40mm with 3mm walls, 6mm rounded vertical corners, and an open top.'],
  ];

  function renderEmpty() {
    return h('div', { class: 'empty' },
      h('div', { class: 'hero' }, icon('cube')),
      h('h1', { text: 'What should we make?' }),
      h('p', { text: 'Describe a part. VibeShaper builds it as an editable, parametric timeline, and you can refine it by chatting.' }),
      h('div', { class: 'examples' }, EXAMPLES.map(([title, text]) =>
        h('button', { class: 'example', onclick: () => { setInput(text); $('input').focus(); } },
          h('b', { text: title }), h('span', { text: text.length > 78 ? text.slice(0, 76) + '…' : text })))),
      h('div', { class: 'tip', text: 'Tip: paste DSL JSON starting with { to build it directly.' }));
  }

  function renderTurn(t) {
    if (t.role === 'user') return renderUser(t);
    return renderAssistant(t);
  }

  function renderUser(t) {
    if (t.is_json) {
      let steps = '';
      let name = 'Design JSON';
      try {
        const d = JSON.parse(t.text);
        steps = plural((d.timeline || []).length, 'step');
        if (d.name) name = String(d.name).replace(/_/g, ' ');
      } catch (e) { steps = 'not valid JSON'; }
      return h('div', { class: 'msg-user', 'data-turn': t.id },
        h('div', { class: 'json-pill' }, icon('code'), h('span', null, h('strong', { text: name }), ' · ', steps)));
    }
    return h('div', { class: 'msg-user', 'data-turn': t.id }, h('div', { class: 'bubble', text: t.text }));
  }

  const STEPS = { model: [['thinking', 'Thinking'], ['writing', 'Writing design'], ['building', 'Building']], json: [['building', 'Building']], restore: [['building', 'Building']] };

  function renderSteps(t) {
    const steps = STEPS[t.kind] || STEPS.json;
    const idx = steps.findIndex(([k]) => k === t.status);
    const wrap = h('div', { class: 'steps' });
    steps.forEach(([key, label], i) => {
      if (i) wrap.append(h('span', { class: 'step-sep', 'aria-hidden': 'true' }));
      const cls = i < idx ? 'step done' : i === idx ? 'step active' : 'step';
      const el = h('span', { class: cls }, i === idx ? h('span', { class: 'shimmer', text: label }) : label);
      if (key === 'writing' && i === idx && t.chars) el.append(h('span', { class: 'writing-count', text: ' · ' + fmtChars(t.chars) + ' chars' }));
      wrap.append(el);
    });
    return wrap;
  }

  // How far a build has got: Fusion builds on its main thread, so this arrives in bursts
  function renderProgress(p) {
    const pct = p.total ? Math.min(100, Math.round((100 * p.done) / p.total)) : 0;
    return h('div', { class: 'build-progress' },
      h('div', { class: 'bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': String(p.total), 'aria-valuenow': String(p.done) },
        h('div', { class: 'fill', style: `width:${pct}%` })),
      h('div', { class: 'build-step' },
        h('span', { class: 'label', text: p.label || '' }),
        p.total ? h('span', { class: 'count', text: `${p.done} / ${p.total}` }) : null));
  }

  function renderThinking(t, live) {
    if (!t.thought) return null;
    const d = h('details', { class: 'thinking' },
      h('summary', null, icon('chevron', 'i-sm chev'), live ? 'Thinking' : 'Thought process', ' · ', h('span', { class: 'count', text: fmtChars(t.thought.length) + ' chars' })),
      h('pre', { class: 'thought-text', text: t.thought }));
    if (live && t.status === 'thinking') d.open = true;
    return d;
  }

  // What the model looked at in the user's design (read-only tool calls)
  const openTools = new Set();  // turns whose list the user opened; kept across re-renders
  function renderTools(t, live) {
    const tools = t.tools || [];
    if (!tools.length) return null;
    const failed = tools.filter((x) => /\(failed:/.test(x.label)).length;
    const label = live && t.status === 'thinking' ? `Looking at your design · ${plural(tools.length, 'step')}`
      : `Looked at your design · ${plural(tools.length, 'step')}` + (failed ? ` · ${failed} failed` : '');
    const d = h('details', { class: 'tools' },
      h('summary', null, icon('chevron', 'i-sm chev'), icon('search', 'i-sm'), h('span', { text: label })),
      h('ol', { class: 'tool-list' }, tools.map((x) => h('li', { class: /\(failed:/.test(x.label) ? 'err' : '', text: x.label }))));
    d.open = openTools.has(t.id);
    d.addEventListener('toggle', () => { if (d.open) openTools.add(t.id); else openTools.delete(t.id); });
    return d;
  }

  function renderAssistant(t) {
    const live = ['thinking', 'writing', 'building'].includes(t.status);
    const body = h('div', { class: 'ai-body' });

    if (live) body.append(h('div', { class: 'status-line' }, renderSteps(t)));
    if (t.status === 'building' && t.progress) body.append(renderProgress(t.progress));
    const looked = renderTools(t, live);
    if (looked) body.append(looked);
    const th = renderThinking(t, live);
    if (th) body.append(th);
    if (live && th) requestAnimationFrame(() => { const p = th.querySelector('.thought-text'); if (p) p.scrollTop = p.scrollHeight; });

    if (t.status === 'done') body.append(renderResult(t));
    if (t.attempts && t.attempts.length) body.append(renderAttempts(t, live));
    if (t.status === 'confirm') body.append(renderConfirm(t));
    if (t.status === 'error') body.append(renderError(t));
    if (t.status === 'stopped') {
      body.append(h('div', { class: 'row', style: 'display:flex;gap:8px;align-items:center' },
        h('span', { class: 'muted-line', text: 'Stopped.' }),
        t.kind === 'model' && t.request ? h('button', { class: 'mini-btn', onclick: () => send('retry', { turn_id: t.id }), disabled: S.busy }, icon('refresh'), 'Retry') : null));
    }

    return h('div', { class: 'msg-ai', 'data-turn': t.id }, h('div', { class: 'avatar', 'aria-hidden': 'true' }, icon('cube')), body);
  }

  function renderResult(t) {
    const v = versionOf(t.version);
    const isCurrent = S.chat.current === t.version;
    const fc = v ? v.feature_count : 0;
    let how = 'Built';
    if (t.kind === 'json') how = 'Built from your JSON';
    if (t.kind === 'restore') how = `Restored v${t.restored_from}`;
    const meta = [];
    const pl = v && v.placement;
    if (pl && pl.mode === 'component' && pl.label) meta.push(`in ${pl.label}`);
    if (fc) meta.push(plural(fc, 'feature'));
    if (t.replaced) meta.push(`replaced v${t.replaced}`);

    return h('div', { class: 'result' + (isCurrent ? ' is-current' : '') },
      h('span', { class: 'badge' + (isCurrent ? ' ok' : ''), title: isCurrent ? 'This version is in your timeline' : 'Earlier version' },
        isCurrent ? icon('check', 'i-sm') : null, `v${t.version}`),
      h('span', { class: 'result-text' }, h('b', { text: how }), meta.length ? ' · ' + meta.join(' · ') : ''),
      h('span', { class: 'result-actions' },
        v ? h('button', { class: 'mini-btn', title: isCurrent ? 'View or edit this design' : 'View this design', onclick: () => openSheet(t.version) }, icon(isCurrent ? 'code' : 'eye'), 'JSON') : null,
        v ? h('button', { class: 'mini-btn', title: `Open Bill of Materials for v${t.version}`, onclick: () => send('open_bom', { n: t.version }) }, icon('table'), 'BOM') : null,
        v && !isCurrent ? h('button', { class: 'mini-btn', title: `Rebuild v${t.version} as the current version`, disabled: S.busy, onclick: () => send('restore_version', { n: t.version }) }, icon('restore'), 'Restore') : null));
  }

  function renderAttempts(t, live) {
    const n = t.attempts.length;
    const label = live ? `Fixing ${plural(n, 'build error')}…` : t.status === 'done' ? `Fixed ${plural(n, 'build error')} automatically` : `${plural(n, 'build attempt')} failed`;
    return h('div', { class: 'note' },
      h('details', null,
        h('summary', null, icon('wrench'), label),
        t.attempts.map((a, i) => h('pre', { text: `Attempt ${i + 1}: ${firstLine(a.error)}` }))));
  }

  function renderConfirm(t) {
    const n = (t.confirm && t.confirm.count) || 0;
    return h('div', { class: 'callout warn' },
      h('div', { class: 'callout-head' }, icon('alert'), `You added ${plural(n, 'feature')} after this part`),
      h('p', { text: `Replacing v${S.chat.current} may break ${n === 1 ? 'it' : 'them'}. You can replace it anyway, or keep v${S.chat.current} and add this as a separate part.` }),
      h('div', { class: 'row' },
        h('button', { class: 'btn primary', onclick: () => send('confirm_replace', { turn_id: t.id, choice: 'replace' }) }, 'Replace anyway'),
        h('button', { class: 'btn ghost', onclick: () => send('confirm_replace', { turn_id: t.id, choice: 'new' }) }, 'Add as new part'),
        h('button', { class: 'btn ghost', onclick: () => send('confirm_replace', { turn_id: t.id, choice: 'cancel' }) }, 'Cancel')));
  }

  function renderError(t) {
    const lastAi = S.chat.turns.filter((x) => x.role === 'assistant').pop();
    const cur = lastAi && lastAi.id === t.id ? S.chat.current : null;
    const summary = firstLine(t.error) || 'Something went wrong';
    return h('div', { class: 'callout error', role: 'alert' },
      h('div', { class: 'callout-head' }, icon('alert'), h('span', { text: summary.length > 160 ? summary.slice(0, 158) + '…' : summary })),
      cur ? h('p', { text: `Your timeline still has v${cur}, unchanged.` }) : null,
      t.error && t.error.includes('\n') ? h('details', null, h('summary', { class: 'note', style: 'cursor:pointer' }, 'Details'), h('pre', { text: t.error })) : null,
      h('div', { class: 'row' },
        t.kind === 'model' && t.request ? h('button', { class: 'btn ghost', disabled: S.busy, onclick: () => send('retry', { turn_id: t.id }) }, icon('refresh', 'i-sm'), 'Retry') : null,
        h('button', { class: 'btn ghost', onclick: () => copyText(t.error) }, icon('copy', 'i-sm'), 'Copy error')));
  }

  // ---------------------------------------------------------------- parameters tray
  function renderParams() {
    const v = currentVersion();
    const params = v && v.dsl && v.dsl.parameters ? Object.entries(v.dsl.parameters) : [];
    const box = $('params');
    if (!params.length) { box.hidden = true; return; }
    box.hidden = false;
    $('paramsHead').setAttribute('aria-expanded', String(S.paramsOpen));
    $('paramsMeta').textContent = `${params.length} · v${v.n}`;
    const body = $('paramsBody');
    const focusedName = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.param : null;
    if (focusedName) return; // don't yank the field out from under the user
    body.replaceChildren(...params.map(([name, expr]) => paramRow(name, String(expr), v)));
    const err = body.querySelector('.param-err');
    if (err && S.paramsOpen) err.scrollIntoView({ block: 'nearest' });
  }

  function paramRow(name, expr, v) {
    const st = S.paramState[name] || {};
    const fusionName = (v.param_map && v.param_map[name]) || name;
    const shown = st.status === 'err' && st.draft !== undefined ? st.draft : expr;
    const input = h('input', {
      class: 'param-input' + (st.status === 'err' ? ' bad' : ''), value: shown, 'data-param': name,
      'aria-label': `${name} value`, spellcheck: 'false', disabled: S.busy,
      title: fusionName !== name ? `Fusion parameter: ${fusionName}` : null,
    });
    const commit = () => {
      const val = input.value.trim();
      const cur = S.paramState[name] || {};
      if (!val || val === expr) {
        if (cur.status === 'err') { delete S.paramState[name]; }
        input.value = expr;
        return;
      }
      if (cur.status === 'saving' || (cur.status === 'err' && cur.draft === val)) return; // nothing new to send
      S.paramState[name] = { status: 'saving', draft: val };
      send('set_param', { name, expr: val });
    };
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); commit(); input.blur(); }
      if (e.key === 'Escape') { e.stopPropagation(); delete S.paramState[name]; input.value = expr; input.blur(); }
    });
    input.addEventListener('blur', () => { commit(); setTimeout(renderParams, 0); });
    const stateEl = h('span', { class: 'param-state' + (st.status === 'err' ? ' err' : '') },
      st.status === 'ok' ? icon('check') : st.status === 'err' ? icon('alert') : null);
    const row = h('div', { class: 'param-row', role: 'listitem' }, h('span', { class: 'param-name', text: name, title: name }), input, stateEl);
    if (st.status === 'err') row.append(h('div', { class: 'param-err', text: st.error || 'Invalid value' }));
    return row;
  }

  // ---------------------------------------------------------------- composer
  function setInput(text) {
    const ta = $('input');
    ta.value = text;
    autosize();
    renderComposer();
  }

  function autosize() {
    const ta = $('input');
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 180) + 'px';
  }

  function renderComposer() {
    const btn = $('send');
    const has = $('input').value.trim().length > 0;
    btn.classList.toggle('stop', S.busy);
    btn.replaceChildren(icon(S.busy ? 'stop' : 'arrow-up'));
    btn.disabled = !S.busy && !has;
    renderBuildChip();
    btn.setAttribute('aria-label', S.busy ? 'Stop' : 'Send');
    btn.title = S.busy ? 'Stop (Esc)' : 'Send (Enter)';
    const built = S.chat && S.chat.versions && S.chat.versions.length;
    $('input').placeholder = built ? 'Describe a change…' : 'Describe a part…';
    $('hint').replaceChildren(...(S.busy
      ? [h('kbd', { text: 'Esc' }), ' stop']
      : [h('kbd', { text: 'Enter' }), ' send · ', h('kbd', { text: 'Shift' }), '+', h('kbd', { text: 'Enter' }), ' new line']));
  }

  function submit() {
    if (S.busy) { send('stop'); return; }
    const text = $('input').value.trim();
    if (!text) return;
    stuckToBottom = true;
    send('send', { text });
    setInput('');
  }

  // ---------------------------------------------------------------- popovers
  let openPop = null;

  function placePopover(pop, anchor, align) {
    const r = anchor.getBoundingClientRect();
    pop.style.top = r.bottom + 6 + 'px';
    pop.hidden = false;
    const ph = pop.offsetHeight;
    if (r.bottom + 6 + ph > window.innerHeight - 8 && r.top - 6 - ph >= 8) pop.style.top = r.top - 6 - ph + 'px';
    const w = pop.offsetWidth;
    let left = align === 'right' ? r.right - w : r.left;
    left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
    pop.style.left = left + 'px';
  }

  function closePopover() {
    if (!openPop) return;
    openPop.pop.hidden = true;
    openPop.anchor.setAttribute('aria-expanded', 'false');
    const a = openPop.anchor;
    openPop = null;
    a.focus({ preventScroll: true });
  }

  function togglePopover(pop, anchor, align, render) {
    if (openPop && openPop.pop === pop) return closePopover();
    closePopover();
    render();
    placePopover(pop, anchor, align);
    anchor.setAttribute('aria-expanded', 'true');
    openPop = { pop, anchor };
    const first = pop.querySelector('button, input, select');
    if (first) first.focus({ preventScroll: true });
  }

  let deletingChat = null;  // chat id waiting for "Delete?" to be confirmed

  function chatRow(c) {
    if (deletingChat === c.id) {
      return h('div', { class: 'menu-confirm', role: 'group', 'aria-label': 'Delete chat' },
        h('div', { class: 'q', text: `Delete “${c.title}”?` }),
        h('div', { class: 'sub', text: 'Removes the conversation and its versions from this design. The parts it built stay in your timeline.' }),
        h('div', { class: 'row' },
          h('button', { class: 'btn danger sm', onclick: () => { deletingChat = null; closePopover(); send('delete_chat', { id: c.id }); } }, 'Delete'),
          h('button', { class: 'btn ghost sm', onclick: () => { deletingChat = null; renderChatMenu(); focusChatRow(c.id); } }, 'Cancel')));
    }
    return h('div', { class: 'menu-row', 'data-chat': c.id },
      h('button', {
        class: 'menu-item' + (S.chat && c.id === S.chat.id ? ' active' : ''), role: 'menuitem',
        onclick: () => { closePopover(); send('switch_chat', { id: c.id }); },
      }, h('span', { class: 't', text: c.title }), h('span', { class: 'meta', text: c.versions ? `v${c.versions}` : '—' })),
      h('button', {
        class: 'icon-btn row-del', title: 'Delete chat', 'aria-label': `Delete chat “${c.title}”`, disabled: S.busy,
        onclick: (e) => {
          e.stopPropagation();
          const menu = $('chatMenu');
          menu.style.width = menu.offsetWidth + 'px';  // the question shouldn't resize the menu
          deletingChat = c.id;
          renderChatMenu();
          const btn = $('chatMenu').querySelector('.menu-confirm .btn.danger');
          if (btn) btn.focus({ preventScroll: true });
        },
      }, icon('trash', 'i-sm')));
  }

  function focusChatRow(id) {
    const b = $('chatMenu').querySelector(`.menu-row[data-chat="${CSS.escape(id)}"] .row-del`);
    if (b) b.focus({ preventScroll: true });
  }

  function renderChatMenu() {
    const menu = $('chatMenu');
    const items = S.chats.slice().reverse();
    menu.replaceChildren(...[
      h('div', { class: 'menu-label', text: 'Chats in this design' }),
      ...(items.length ? items.map(chatRow) : [h('div', { class: 'menu-empty', text: 'No chats yet.' })]),
      h('div', { class: 'menu-sep' }),
      h('button', { class: 'menu-item', role: 'menuitem', onclick: () => { closePopover(); newChat(); } }, icon('plus', 'i-sm'), 'New chat')]);
  }

  // ---------------------------------------------------------------- model picker (main view)
  // Frequent choice: which provider + model. Connection details live on the Settings page.
  const modelState = (pid) => (S.models[pid] = S.models[pid] || { loading: false, error: '', checked: false });

  function fetchModels(p, values) {
    const m = modelState(p.id);
    m.loading = true; m.error = '';
    send('get_models', values ? { provider: p.id, values } : { provider: p.id });
  }

  function chooseModel(p, model) {
    S.activeProvider = p.id;
    p.model = model;
    send('select_model', { provider: p.id, model });
    closePopover();
    renderHeader();
  }

  function renderModelMenu() {
    const menu = $('modelMenu');
    const focusedId = document.activeElement && menu.contains(document.activeElement) ? document.activeElement.id : null;
    const ready = S.providers.filter((p) => p.configured);
    const notReady = S.providers.filter((p) => !p.configured);
    const q = S.pickerQuery.trim().toLowerCase();
    const totalModels = ready.reduce((n, p) => n + (p.models || []).length, 0);
    const matches = (p, m) => [m.id, m.label, p.name].some((x) => String(x || '').toLowerCase().includes(q));
    const kids = [];

    if (totalModels > 8 || q) {
      const search = h('input', { id: 'modelSearch', class: 'input search', type: 'search', placeholder: 'Search models', value: S.pickerQuery,
        'aria-label': 'Search models', autocomplete: 'off', spellcheck: 'false' });
      search.addEventListener('input', () => { S.pickerQuery = search.value; renderModelMenu(); });
      kids.push(h('div', { class: 'picker-search' }, icon('search', 'i-sm'), search));
    }

    const list = h('div', { class: 'picker-list', role: 'group' });
    for (const p of ready) {
      const m = modelState(p.id);
      const models = (p.models && p.models.length ? p.models : (p.model ? [{ id: p.model, label: p.model }] : []));
      const shown = q ? models.filter((m) => matches(p, m)) : models;
      if (q && !shown.length) continue;
      const refresh = h('button', { class: 'icon-btn sm', id: `pick_refresh_${p.id}`, title: `Refresh ${p.name} models`, 'aria-label': `Refresh ${p.name} models`,
        onclick: () => { fetchModels(p); renderModelMenu(); } }, icon('refresh', 'i-sm' + (m.loading ? ' spin' : '')));
      list.append(h('div', { class: 'picker-head' }, h('span', { text: p.name }), refresh));
      for (const m of shown) {
        const on = p.id === S.activeProvider && m.id === p.model;
        const caps = [m.images && 'Reads images', m.thinking && 'Can think before answering'].filter(Boolean);
        list.append(h('button', { class: 'menu-item pick' + (on ? ' active' : ''), role: 'menuitemradio', 'aria-checked': String(on),
          title: [m.id, ...caps].join(' · '), onclick: () => chooseModel(p, m.id) },
        h('span', { class: 't', text: m.label || m.id }),
        caps.length ? h('span', { class: 'caps', 'aria-label': caps.join(', ') },
          m.images ? icon('image', 'i-sm') : null, m.thinking ? icon('bulb', 'i-sm') : null) : null,
        on ? icon('check', 'i-sm check') : null));
      }
      if (q) continue;
      if (m.loading && !models.length) list.append(h('div', { class: 'menu-empty', text: 'Loading models…' }));
      else if (m.error) list.append(h('div', { class: 'menu-empty err' }, h('span', { text: m.error + ' ' }),
        h('button', { class: 'link', onclick: () => { closePopover(); openSettings(p.id); } }, 'Check settings')));
      else if (!models.length) list.append(h('div', { class: 'menu-empty', text: 'No models found.' }));
    }
    if (!ready.length) {
      list.append(h('div', { class: 'picker-empty' },
        h('strong', { text: 'Connect a model provider' }),
        h('span', { text: 'Add a server URL or API key to start generating.' })));
    }
    if (q && !list.querySelector('.pick')) list.append(h('div', { class: 'menu-empty', text: `No models match “${S.pickerQuery}”.` }));
    kids.push(list);

    if (notReady.length && !q) {
      kids.push(h('div', { class: 'menu-sep' }), h('div', { class: 'menu-label', text: 'Not set up' }));
      for (const p of notReady) {
        kids.push(h('button', { class: 'menu-item', role: 'menuitem', id: `pick_setup_${p.id}`, onclick: () => { closePopover(); openSettings(p.id); } },
          h('span', { class: 't muted', text: p.name }), h('span', { class: 'meta link-meta', text: 'Set up' }), icon('chevron', 'i-sm chev-r')));
      }
    }

    const p = activeProv();
    // Think: offered only when the provider says the selected model can do it; remembered per model.
    const info = p && p.configured && p.model ? modelInfo(p, p.model) : null;
    kids.push(h('div', { class: 'menu-sep' }));
    if (info && info.thinking) {
      const opts = (p.model_options = p.model_options || {});
      const cb = h('input', { type: 'checkbox', id: 'pick_think', checked: !!(opts[p.model] && opts[p.model].think) });
      cb.addEventListener('change', () => {
        opts[p.model] = { think: cb.checked };
        send('set_model_option', { provider: p.id, model: p.model, think: cb.checked });
      });
      kids.push(h('label', { class: 'toggle menu-toggle', for: 'pick_think' },
        h('span', { class: 'toggle-text' }, h('span', { class: 'field-label', text: 'Think before answering' }),
          h('small', { text: `${info.label || info.id} · slower, usually better designs` })),
        cb, h('span', { class: 'track', 'aria-hidden': 'true' })));
    }
    kids.push(h('button', { class: 'menu-item', role: 'menuitem', id: 'pick_settings', onclick: () => { closePopover(); openSettings(); } },
      icon('gear', 'i-sm'), h('span', { class: 't', text: 'Settings' }), h('span', { class: 'meta', text: 'Ctrl+,' })));

    menu.replaceChildren(...kids);
    const f = focusedId && $(focusedId);
    if (f) { f.focus({ preventScroll: true }); if (f.id === 'modelSearch') f.setSelectionRange(f.value.length, f.value.length); }
  }

  function openModelMenu() {
    S.pickerQuery = '';
    togglePopover($('modelMenu'), $('modelChip'), 'right', renderModelMenu);
    if (!openPop) return;
    for (const p of S.providers) {
      const m = modelState(p.id);
      if (p.configured && !m.loading && !m.checked) fetchModels(p);
    }
    renderModelMenu();
    const sel = $('modelMenu').querySelector('.pick.active') || $('modelSearch');
    if (sel) sel.focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- build menu (where designs go)
  const MODES = [
    ['component', 'New component', 'component', 'Its own component. Regenerating keeps its position and joints.'],
    ['new_body', 'New body', 'cube', 'Bodies in the root component.'],
  ];
  const chosenMode = () => (S.chat && S.chat.target && S.chat.target.mode) || S.general.default_mode || 'component';
  // Part Design documents can't hold another component: builds go in as new bodies there.
  const effectiveMode = () => (S.components ? chosenMode() : 'new_body');
  const PART_DOC_NOTE = 'Part documents hold one component. Use an Assembly document to build into components.';
  const modeDef = (m) => MODES.find((x) => x[0] === m) || MODES[0];

  function renderBuildChip() {
    const chip = $('buildChip');
    const def = modeDef(effectiveMode());
    chip.replaceChildren(icon(def[2], 'i-sm'), h('span', { class: 'build-label', text: def[1] }), icon('chevron', 'i-sm'));
    chip.disabled = S.busy;
    chip.title = S.components ? `Build into: ${def[1].toLowerCase()}` : `Build into: new body. ${PART_DOC_NOTE}`;
  }

  function renderBuildMenu() {
    const m = effectiveMode();
    $('buildMenu').replaceChildren(
      h('div', { class: 'menu-label', text: 'Build into' }),
      ...MODES.map(([id, label, ic, desc]) => h('button', {
        class: 'menu-item mode-item' + (id === m ? ' active' : ''), role: 'menuitemradio', 'aria-checked': String(id === m), id: `mode_${id}`,
        disabled: id === 'component' && !S.components,
        onclick: () => {
          if (id !== m && S.chat) {
            S.chat.target = Object.assign({}, S.chat.target, { mode: id });
            send('set_target', { mode: id });
            renderBuildChip();
          }
          closePopover();
        },
      }, icon(ic, 'i-sm mode-ico'), h('span', { class: 'mode-text' }, h('span', { class: 't', text: label }),
        h('small', { text: id === 'component' && !S.components ? PART_DOC_NOTE : desc })),
      id === m ? icon('check', 'i-sm check') : null)),
      h('div', { class: 'menu-sep' }),
      h('div', { class: 'menu-note' }, `New chats use ${modeDef(S.general.default_mode)[1].toLowerCase()}. `,
        h('button', { class: 'link', onclick: () => { closePopover(); openSettings('general'); } }, 'Change default')));
  }

  function openBuildMenu() {
    if (S.busy) return;
    togglePopover($('buildMenu'), $('buildChip'), 'left', renderBuildMenu);
    const cur = $('buildMenu').querySelector('.mode-item.active');
    if (openPop && cur) cur.focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- settings page
  // A full-panel page: navigation (General + one entry per provider) and a content area.
  // Wide panels show both side by side; narrow ones drill down (list -> page -> back).
  const WIDE = 560;
  const isWide = () => window.innerWidth >= WIDE;

  function openSettings(page) {
    closePopover();
    S.settings = { open: true, page: page || (isWide() ? 'general' : null) };
    $('settingsView').hidden = false;
    renderSettingsView();
    const target = $('settingsView').querySelector(page ? '.set-content input, .set-content button' : '.nav-item');
    (target || $('settingsBack')).focus({ preventScroll: true });
  }

  function closeSettings() {
    S.settings.open = false;
    $('settingsView').hidden = true;
    renderHeader();
    $('input').focus();
  }

  function settingsBack() {
    if (!isWide() && S.settings.page) {
      const from = S.settings.page;
      S.settings.page = null;
      renderSettingsView();
      const el = $(`nav_${from}`) || $('settingsView').querySelector('.nav-item');
      if (el) el.focus({ preventScroll: true });
    } else closeSettings();
  }

  function setPage(page) {
    S.settings.page = page;
    renderSettingsView();
    const first = $('settingsView').querySelector('.set-content input, .set-content button');
    if (!isWide() && first) first.focus({ preventScroll: true });
  }

  const statusOf = (p) => (p.configured ? { cls: 'ok', text: p.id === S.activeProvider ? 'In use' : 'Ready' } : { cls: 'warn', text: 'Not set up' });

  function renderSettingsView() {
    if (!S.settings.open) return;
    const view = $('settingsView');
    const wide = isWide();
    const page = S.settings.page || (wide ? 'general' : null);
    const p = page && page !== 'general' ? provider(page) : null;
    view.classList.toggle('wide', wide);
    const focusedId = document.activeElement && view.contains(document.activeElement) ? document.activeElement.id : null;

    const top = wide || !page;
    $('settingsTitle').textContent = 'Settings';
    $('settingsBack').setAttribute('aria-label', top ? 'Close settings' : 'Back to settings');
    $('settingsBack').title = top ? 'Close (Esc)' : 'Back (Esc)';
    $('settingsBack').replaceChildren(icon(top ? 'x' : 'arrow-left'));
    $('settingsBack').classList.toggle('end', top);

    const navItem = (id, label, iconName, status) => h('button', {
      class: 'nav-item' + (page === id ? ' current' : ''), 'aria-current': page === id ? 'page' : null, id: `nav_${id}`,
      onclick: () => setPage(id),
    }, iconName ? icon(iconName, 'i-sm nav-ico') : h('span', { class: 'dot ' + status.cls, 'aria-hidden': 'true' }),
      h('span', { class: 'nav-text' }, h('span', { class: 't', text: label }), status ? h('small', { text: status.text }) : null),
      wide ? null : icon('chevron', 'i-sm chev-r'));

    const nav = h('nav', { class: 'set-nav', 'aria-label': 'Settings sections' },
      navItem('general', 'General', 'sliders', null),
      h('div', { class: 'nav-label', text: 'Model providers' }),
      S.providers.map((x) => navItem(x.id, x.name, null, statusOf(x))));

    const content = page === 'general' ? renderGeneralPage() : p ? renderProviderPage(p) : null;
    const body = $('settingsBody');
    if (wide) body.replaceChildren(nav, h('div', { class: 'set-content' }, content));
    else body.replaceChildren(page ? h('div', { class: 'set-content' }, content) : nav);
    if (focusedId && $(focusedId)) $(focusedId).focus({ preventScroll: true });
  }

  function patchProviderStatus(p) {
    const st = statusOf(p);
    const nav = $(`nav_${p.id}`);
    if (nav) {
      const dot = nav.querySelector('.dot');
      if (dot) dot.className = 'dot ' + st.cls;
      const small = nav.querySelector('small');
      if (small) small.textContent = st.text;
    }
    const pill = $(`pill_${p.id}`);
    if (pill) { pill.className = 'pill ' + st.cls; pill.textContent = st.text; }
  }

  const saveGeneral = debounce(() => send('save_general', { values: S.general }), 250);

  function renderGeneralPage() {
    const theme = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': 'Theme' },
      [['system', 'Match system'], ['light', 'Light'], ['dark', 'Dark']].map(([v, label]) => h('button', {
        role: 'radio', 'aria-checked': String(S.general.theme === v), id: `theme_${v}`,
        onclick: () => { S.general.theme = v; applyTheme(); saveGeneral(); renderSettingsView(); },
      }, label)));

    const defMode = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': 'New chats build into' },
      [['component', 'New component'], ['new_body', 'New body']].map(([v, label]) => h('button', {
        role: 'radio', 'aria-checked': String((S.general.default_mode || 'component') === v), id: `defmode_${v}`,
        onclick: () => { S.general.default_mode = v; saveGeneral(); renderSettingsView(); renderBuildChip(); },
      }, label)));

    const fix = h('select', { id: 'set_auto_fix', class: 'select' },
      [[0, 'Off'], [1, '1 attempt'], [2, '2 attempts'], [3, '3 attempts'], [5, '5 attempts']].map(([v, label]) =>
        h('option', { value: v, selected: Number(S.general.auto_fix) === v }, label)));
    fix.addEventListener('change', () => { S.general.auto_fix = Number(fix.value); saveGeneral(); });

    return [
      h('h2', { class: 'page-title', text: 'General' }),
      h('section', { class: 'set-group' },
        h('h3', { text: 'Appearance' }),
        h('div', { class: 'field' }, h('span', { class: 'field-label', text: 'Theme' }), theme,
          h('span', { class: 'help', text: 'Fusion doesn’t tell add-ins which theme it uses, so pick the one that matches yours.' }))),
      h('section', { class: 'set-group' },
        h('h3', { text: 'Building' }),
        h('div', { class: 'field' }, h('span', { class: 'field-label', text: 'New chats build into' }), defMode,
          h('span', { class: 'help', text: 'Each chat can switch with the button under the message box.' })),
        h('div', { class: 'field' }, h('label', { for: 'set_auto_fix', text: 'Fix failed builds automatically' }), fix,
          h('span', { class: 'help', text: 'When a build fails, VibeShaper sends the error to the model and asks for a corrected design.' }))),
    ];
  }

  const saveProvider = debounce((p) => send('save_provider', { provider: p.id, values: p.values }), 350);

  function renderProviderPage(p) {
    const m = modelState(p.id);
    const st = statusOf(p);
    const changed = (f) => {
      if (f.refreshes_models) {
        Object.assign(m, { checked: false, error: '', testing: false });
        const res = $(`test_result_${p.id}`);
        if (res) res.remove();
      }
      saveProvider(p);
    };
    const fields = p.schema.map((f) => {
      const id = `set_${p.id}_${f.key}`;
      const wrap = (control) => h('div', { class: 'field' }, h('label', { for: id, text: f.label }), control,
        f.tooltip ? h('span', { class: 'help', text: f.tooltip }) : null);
      if (f.type === 'boolean') {
        const cb = h('input', { type: 'checkbox', id, checked: !!p.values[f.key] });
        cb.addEventListener('change', () => { p.values[f.key] = cb.checked; changed(f); });
        return h('label', { class: 'toggle', for: id },
          h('span', { class: 'toggle-text' }, h('span', { class: 'field-label', text: f.label }), f.tooltip ? h('small', { text: f.tooltip }) : null),
          cb, h('span', { class: 'track', 'aria-hidden': 'true' }));
      }
      if (f.type === 'select') {
        const sel = h('select', { id, class: 'select' }, ...(f.options || []).map((o) =>
          h('option', { value: o.value, text: o.label, selected: String(p.values[f.key]) === String(o.value) })));
        sel.addEventListener('change', () => { p.values[f.key] = sel.value; changed(f); });
        return wrap(sel);
      }
      if (f.type === 'number') {
        const num = h('input', { id, class: 'input', type: 'number', value: p.values[f.key] ?? '', step: 'any',
          ...(f.minimum != null ? { min: f.minimum } : {}), ...(f.maximum != null ? { max: f.maximum } : {}) });
        num.addEventListener('input', () => { if (num.value !== '') { p.values[f.key] = Number(num.value); changed(f); } });
        return wrap(num);
      }
      const input = h('input', {
        id, class: 'input', type: f.type === 'secret' ? 'password' : 'text', value: p.values[f.key] ?? '',
        placeholder: f.type === 'secret' ? 'Paste your key' : '', autocomplete: 'off', spellcheck: 'false',
      });
      input.addEventListener('input', () => { p.values[f.key] = input.value; changed(f); });
      const row = h('div', { class: 'field-row' }, input);
      if (f.type === 'secret') {
        const eye = h('button', { class: 'icon-btn', type: 'button', id: `${id}_eye`, 'aria-label': 'Show key', title: 'Show key', onclick: () => {
          input.type = input.type === 'password' ? 'text' : 'password';
          eye.setAttribute('aria-label', input.type === 'password' ? 'Show key' : 'Hide key');
        } }, icon('eye'));
        row.append(eye);
      }
      return wrap(row);
    });

    const test = h('button', { class: 'btn ghost', id: `test_${p.id}`, disabled: m.loading,
      onclick: () => { m.testing = true; fetchModels(p, p.values); renderSettingsView(); } },
    icon('refresh', 'i-sm' + (m.loading ? ' spin' : '')), m.loading ? 'Testing…' : 'Test connection');
    let result = null;
    if (m.testing && !m.loading) {
      result = m.error
        ? h('span', { class: 'test-result err', id: `test_result_${p.id}`, role: 'status' }, icon('alert', 'i-sm'), h('span', { text: m.error }))
        : h('span', { class: 'test-result ok', id: `test_result_${p.id}`, role: 'status' }, icon('check', 'i-sm'), h('span', { text: `Connected · ${plural((p.models || []).length, 'model')}` }));
    }

    return [
      h('div', { class: 'page-head' }, h('h2', { class: 'page-title', text: p.name }), h('span', { class: 'pill ' + st.cls, id: `pill_${p.id}`, text: st.text })),
      h('section', { class: 'set-group' }, h('h3', { text: 'Connection' }), ...fields,
        h('div', { class: 'test-row' }, test, result)),
      h('p', { class: 'help foot', text: 'Changes are saved as you type. Choose the model from the menu at the top of the chat.' }),
    ];
  }

  function applyTheme() {
    const forced = /[?&]theme=(dark|light)/.exec(location.search);
    const t = forced ? forced[1] : S.general.theme;
    if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t;
    else delete document.documentElement.dataset.theme;
  }

  // ---------------------------------------------------------------- JSON sheet
  function openSheet(n) {
    const v = versionOf(n);
    if (!v) return;
    const editable = S.chat.current === n && !S.busy;
    S.sheet = { version: n, editable };
    const ed = $('jsonEditor');
    ed.value = pretty(v.dsl);
    ed.readOnly = !editable;
    $('sheetTitle').textContent = editable ? `Edit v${n}` : `v${n} · read only`;
    $('jsonApply').textContent = editable ? `Build as v${nextVersionNumber()}` : `Restore as v${nextVersionNumber()}`;
    $('jsonApply').disabled = false;
    $('jsonFormat').hidden = !editable;
    $('sheetBackdrop').hidden = false;
    $('sheet').hidden = false;
    updateGutter();
    setJsonStatus(editable ? 'Edit the design, then build it as a new version.' : `This is an earlier version. Restore it to make it current.`, '');
    ed.focus();
    ed.setSelectionRange(0, 0);
    ed.scrollTop = 0;
  }

  function closeSheet() {
    S.sheet = null;
    $('sheet').hidden = true;
    $('sheetBackdrop').hidden = true;
    $('input').focus();
  }

  function updateGutter() {
    const lines = $('jsonEditor').value.split('\n').length;
    let s = '';
    for (let i = 1; i <= lines; i++) s += i + '\n';
    $('gutter').textContent = s;
    $('gutter').scrollTop = $('jsonEditor').scrollTop;
  }

  function setJsonStatus(text, kind) {
    const el = $('jsonStatus');
    el.className = 'json-status' + (kind ? ' ' + kind : '');
    el.replaceChildren(kind === 'ok' ? icon('check') : kind === 'err' ? icon('alert') : '', h('span', { text }));
  }

  const checkJson = debounce(() => {
    if (!S.sheet || !S.sheet.editable) return;
    const text = $('jsonEditor').value;
    try {
      JSON.parse(text);
    } catch (e) {
      setJsonStatus(e.message.replace(/^JSON\.parse: /, ''), 'err');
      $('jsonApply').disabled = true;
      return;
    }
    send('validate_json', { text });
  }, 300);

  function showJsonCheck(ev) {
    if (!S.sheet) return;
    $('jsonApply').disabled = !ev.ok;
    setJsonStatus(ev.ok ? `Valid · ${plural(ev.steps || 0, 'step')}` : ev.error, ev.ok ? 'ok' : 'err');
  }

  function applySheet() {
    if (!S.sheet) return;
    if (S.sheet.editable) send('apply_json', { text: $('jsonEditor').value });
    else send('restore_version', { n: S.sheet.version });
    closeSheet();
  }

  // ---------------------------------------------------------------- misc actions
  function newChat() {
    if (S.busy) { toast('Wait for the current build, or stop it first'); return; }
    send('new_chat');
    setInput('');
    $('input').focus();
  }

  function copyText(text) {
    send('copy', { text: text || '' });
  }

  let toastTimer;
  function toast(text) {
    const el = $('toast');
    el.textContent = text;
    el.hidden = false;
    el.style.animation = 'none';
    void el.offsetWidth;
    el.style.animation = '';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 1800);
  }

  // ---------------------------------------------------------------- wiring
  function wire() {
    const ta = $('input');
    ta.addEventListener('input', () => { autosize(); renderComposer(); });
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
    });
    $('send').addEventListener('click', submit);
    $('newChat').addEventListener('click', newChat);
    $('chatSwitch').addEventListener('click', () => togglePopover($('chatMenu'), $('chatSwitch'), 'left', () => { deletingChat = null; $('chatMenu').style.width = ''; renderChatMenu(); }));
    $('modelChip').addEventListener('click', openModelMenu);
    $('buildChip').addEventListener('click', openBuildMenu);
    $('openSettings').addEventListener('click', () => openSettings());
    $('settingsBack').addEventListener('click', settingsBack);
    $('modelMenu').addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      const items = [...$('modelMenu').querySelectorAll('.menu-item, #modelSearch')];
      const i = items.indexOf(document.activeElement);
      const next = items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length];
      if (next) { e.preventDefault(); next.focus(); }
    });
    $('paramsHead').addEventListener('click', () => { S.paramsOpen = !S.paramsOpen; renderParams(); });
    const thread = $('thread');
    const onUserScroll = () => { stuckToBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 60; };
    thread.addEventListener('wheel', () => requestAnimationFrame(onUserScroll), { passive: true });
    thread.addEventListener('touchmove', () => requestAnimationFrame(onUserScroll), { passive: true });
    thread.addEventListener('keyup', onUserScroll);
    thread.addEventListener('mouseup', onUserScroll);

    const ed = $('jsonEditor');
    ed.addEventListener('input', () => { updateGutter(); checkJson(); });
    ed.addEventListener('scroll', () => { $('gutter').scrollTop = ed.scrollTop; });
    ed.addEventListener('keydown', (e) => {
      if (e.key === 'Tab' && !ed.readOnly) {
        e.preventDefault();
        const { selectionStart: s, selectionEnd: en } = ed;
        ed.setRangeText('  ', s, en, 'end');
        updateGutter(); checkJson();
      }
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!$('jsonApply').disabled) applySheet(); }
    });
    $('jsonFormat').addEventListener('click', () => {
      try { ed.value = pretty(JSON.parse(ed.value)); updateGutter(); checkJson(); } catch (e) { setJsonStatus('Fix the JSON before formatting', 'err'); }
    });
    $('jsonCopy').addEventListener('click', () => copyText(ed.value));
    $('jsonApply').addEventListener('click', applySheet);
    $('sheetClose').addEventListener('click', closeSheet);
    $('sheetBackdrop').addEventListener('click', closeSheet);

    document.addEventListener('mousedown', (e) => {
      if (openPop && !openPop.pop.contains(e.target) && !openPop.anchor.contains(e.target)) closePopover();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (S.sheet) { e.preventDefault(); closeSheet(); return; }
        if (openPop) { e.preventDefault(); closePopover(); return; }
        if (S.settings.open) { e.preventDefault(); settingsBack(); return; }
        if (S.busy) { e.preventDefault(); send('stop'); }
      }
      if (e.key.toLowerCase() === 'o' && e.ctrlKey && e.shiftKey) { e.preventDefault(); newChat(); }
      if (e.key === ',' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (S.settings.open) closeSettings(); else openSettings(); }
    });
    let lastWide = isWide();
    window.addEventListener('resize', () => {
      closePopover();
      if (isWide() !== lastWide) { lastWide = isWide(); renderSettingsView(); }
    });
    applyTheme();
  }

  // ======================================================================
  // MockBackend: stands in for VibeShaper.py when the panel runs in a browser.
  // Mirrors the event shapes the add-in sends.
  // ======================================================================
  const MockBackend = {
    create(emit) {
      const uid = () => Math.random().toString(16).slice(2, 10);
      const now = () => Date.now() / 1000;
      const providers = [
        { id: 'ollama', name: 'Ollama (Local)', short_name: 'Ollama', schema: [
          { key: 'url', label: 'Ollama URL', type: 'string', tooltip: 'Your local or remote Ollama server', required: true, refreshes_models: true }],
          values: { url: 'http://localhost:11434' }, model: 'qwen3:8b', model_options: { 'qwen3:8b': { think: true } }, models: [], configured: true },
        { id: 'gemini', name: 'Google Gemini', short_name: 'Gemini', schema: [
          { key: 'api_key', label: 'Gemini API key', type: 'secret', tooltip: 'From Google AI Studio, or set GEMINI_API_KEY', required: true, refreshes_models: true }],
          values: { api_key: '' }, model: '', model_options: {}, models: [], configured: false },
        { id: 'openai_compat', name: 'OpenAI-compatible', short_name: 'OpenAI-compatible', schema: [
          { key: 'url', label: 'Base URL', type: 'string', tooltip: 'e.g. LM Studio or vLLM: http://localhost:1234/v1', required: true, refreshes_models: true },
          { key: 'api_key', label: 'API key', type: 'secret', tooltip: 'Leave empty if the server needs none', required: false, refreshes_models: true },
          { key: 'temperature', label: 'Temperature', type: 'number', tooltip: 'Lower is more predictable', minimum: 0, maximum: 2 },
          { key: 'effort', label: 'Reasoning effort', type: 'select', tooltip: 'For reasoning models', options: [
            { value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }] }],
          values: { url: '', api_key: '', temperature: 0.2, effort: 'medium' }, model: '', model_options: {}, models: [], configured: false },
      ];
      const mm = (id, caps = '', label = id) => ({ id, label, images: caps.includes('i'), thinking: caps.includes('t'), tools: caps.includes('f') });
      const MODELS = {
        ollama: [mm('deepseek-r1:8b', 't'), mm('gemma3:12b', 'i'), mm('llama3.1:8b', 'f'), mm('mistral-small3.2:24b', 'if'),
          mm('qwen2.5-coder:7b', 'f'), mm('qwen2.5vl:7b', 'i'), mm('qwen3:14b', 'tf'), mm('qwen3:8b', 'tf')],
        gemini: [mm('gemini-2.0-flash', 'if', 'Gemini 2.0 Flash'), mm('gemini-2.5-flash', 'itf', 'Gemini 2.5 Flash'), mm('gemini-2.5-pro', 'itf', 'Gemini 2.5 Pro')],
        openai_compat: [mm('local-model')],
      };
      const isReady = (p) => p.schema.every((f) => !f.required || String(p.values[f.key] ?? '').trim());
      const general = { theme: 'system', auto_fix: 2, default_mode: 'component' };
      let active = 'ollama';
      let chats = [];
      let cur = null;
      let busy = false;
      let timers = [];

      const elbow = (thick) => ({
        name: 'pipe_elbow',
        parameters: { pipe_od: '30 mm', pipe_wall: '3 mm', bend_r: '80 mm', flange_dia: '80 mm', flange_thick: thick, bolt_dia: '6 mm', bolt_circle: '60 mm', bolt_qty: '6' },
        timeline: [
          { op: 'sketch', id: 'path_sk', plane: 'xz', entities: [{ type: 'polyline', points: [[0, 'bend_r'], [0, 0], ['bend_r', 0]] }] },
          { op: 'sketch', id: 'outer_sk', plane: 'xy', offset: 'bend_r', entities: [{ type: 'circle', center: [0, 0], diameter: 'pipe_od' }] },
          { op: 'sweep', id: 'pipe', sketch: 'outer_sk', path: 'path_sk', mode: 'new_body' },
          { op: 'sketch', id: 'flange_sk', plane: 'xy', offset: 'bend_r - flange_thick', entities: [{ type: 'circle', center: [0, 0], diameter: 'flange_dia' }] },
          { op: 'extrude', id: 'flange', sketch: 'flange_sk', distance: 'flange_thick', mode: 'join' },
          { op: 'circular_pattern', feature: 'flange', axis: 'z', quantity: 'bolt_qty' },
        ],
      });

      const THOUGHT = 'The user wants a 90° elbow. I will sweep a 30 mm circle along an L-shaped path with an 80 mm leg, then hollow it with a second cut sweep for the bore. ' +
        'The flange sits on the vertical leg: an 80 mm disc, extruded by flange_thick. Bolt holes: one 6 mm hole at 30 mm radius, then a circular pattern of 6. ' +
        'All dimensions become parameters so they can be changed later.';

      const view = () => cur && JSON.parse(JSON.stringify(cur));
      const summaries = () => chats.filter((c) => c.turns.length).map((c) => ({ id: c.id, title: c.title, versions: c.versions.length }));
      const pushChat = () => emit({ type: 'chat', chat: view(), chats: summaries(), busy });
      const later = (ms, fn) => timers.push(setTimeout(fn, ms));
      const newChat = () => { cur = { id: uid(), title: 'New chat', turns: [], versions: [], current: null, target: { mode: null, occ: null } }; chats.push(cur); };
      const placement = (dsl) => {
        const m = cur.target.mode || general.default_mode;
        if (m === 'component') return { mode: m, label: String((cur.versions[0] || { dsl }).dsl.name || cur.title).replace(/_/g, ' ').slice(0, 40) };
        return { mode: 'new_body', label: null };
      };

      function addVersion(dsl, source) {
        const n = cur.versions.length ? cur.versions[cur.versions.length - 1].n + 1 : 1;
        const pm = {};
        Object.keys(dsl.parameters || {}).forEach((k) => { pm[k] = k; });
        cur.versions.push({ n, dsl, source, param_map: pm, feature_count: dsl.timeline.length + 2, placement: placement(dsl) });
        const replaced = cur.current;
        cur.current = n;
        return { n, replaced };
      }

      function finish(turn, dsl, source) {
        const { n, replaced } = addVersion(dsl, source);
        turn.status = 'done'; turn.version = n; turn.replaced = replaced;
        busy = false;
        pushChat();
      }

      const MOCK_TOOLS = [
        { name: 'get_overview', label: 'Looked at the design overview' },
        { name: 'get_selection', label: 'Checked your selection · 1' },
        { name: 'get_body', label: 'Inspected body b3 · Housing' },
        { name: 'get_timeline', label: 'Read the timeline · 14' },
      ];

      function runModel(turn, text) {
        busy = true;
        turn.status = 'thinking';
        pushChat();
        const words = THOUGHT.split(/(\s+)/);
        let i = 0;
        let looked = 0;
        const tick = () => {
          if (!busy) return;
          if (looked < MOCK_TOOLS.length) {  // the model looks at the design first
            const tool = MOCK_TOOLS[looked++];
            (turn.tools = turn.tools || []).push(tool);
            emit({ type: 'stream', chat_id: cur.id, turn_id: turn.id, tool });
            later(350, tick);
            return;
          }
          if (i < words.length) {
            const chunk = words.slice(i, i + 6).join('');
            i += 6;
            turn.thought += chunk;
            emit({ type: 'stream', chat_id: cur.id, turn_id: turn.id, thought_append: chunk });
            later(70, tick);
          } else {
            turn.status = 'writing';
            emit({ type: 'stream', chat_id: cur.id, turn_id: turn.id, status: 'writing', chars: 0 });
            let chars = 0;
            const demoBuild = (then) => {  // the build reports each step, as the add-in does
              const names = ['Creating parameters', 'sketch flange_sk', 'extrude flange_body', 'sketch path_sk',
                'sweep pipe', 'fillet', 'circular_pattern bolt_cut', 'thread port_cut', 'Done'];
              let k = 0;
              const step = () => {
                if (!busy) return;
                emit({ type: 'stream', chat_id: cur.id, turn_id: turn.id, progress: { done: k, total: names.length - 1, label: names[k] } });
                if (k++ < names.length - 1) later(260, step); else later(200, then);
              };
              step();
            };
            const write = () => {
              if (!busy) return;
              chars += 180;
              if (chars < 1400) { emit({ type: 'stream', chat_id: cur.id, turn_id: turn.id, chars }); later(90, write); return; }
              turn.status = 'building';
              emit({ type: 'stream', chat_id: cur.id, turn_id: turn.id, status: 'building' });
              demoBuild(() => {
                if (/fail/i.test(text)) {
                  turn.status = 'error'; busy = false;
                  turn.attempts = [{ error: "timeline[2] (sweep): profile is not perpendicular to the path" }, { error: 'timeline[2] (sweep): profile is not perpendicular to the path' }];
                  turn.error = 'VibeShaper: build failed 3 times\ntimeline[2] (sweep): profile is not perpendicular to the path\nTraceback (most recent call last):\n  File "dsl.py", line 1001, in execute';
                  pushChat();
                } else if (/fix/i.test(text)) {
                  turn.attempts = [{ error: 'timeline[4] (extrude): sketch "flange_sk" has no closed profiles' }];
                  emit({ type: 'stream', chat_id: cur.id, turn_id: turn.id, attempt_error: turn.attempts[0].error });
                  later(900, () => finish(turn, elbow('10 mm'), 'model'));
                } else if (/after/i.test(text) && cur.current) {
                  turn.status = 'confirm'; turn.confirm = { count: 2 };
                  pushChat();
                } else {
                  finish(turn, elbow(cur.versions.length ? '12 mm' : '8 mm'), 'model');
                }
              });
            };
            later(120, write);
          }
        };
        later(350, tick);
      }

      function sendText(text) {
        if (!cur) newChat();
        if (!cur.turns.length) cur.title = text.trim().startsWith('{') ? 'Imported design' : (text.length > 46 ? text.slice(0, 45) + '…' : text);
        const isJson = text.trim().startsWith('{');
        cur.turns.push({ id: uid(), role: 'user', text, is_json: isJson, ts: now() });
        const turn = { id: uid(), role: 'assistant', kind: isJson ? 'json' : 'model', status: isJson ? 'building' : 'thinking', thought: '', version: null, replaced: null, attempts: [], error: null, request: text, ts: now() };
        cur.turns.push(turn);
        if (isJson) {
          busy = true; pushChat();
          let d;
          try { d = JSON.parse(text); } catch (e) { turn.status = 'error'; turn.error = 'Invalid JSON: ' + e.message; busy = false; pushChat(); return; }
          later(600, () => finish(turn, d, 'json'));
        } else {
          runModel(turn, text);
        }
      }

      function seedDemo() {
        newChat();
        cur.title = 'A 90-degree pipe elbow with 30mm outer diameter…';
        cur.turns.push({ id: uid(), role: 'user', text: 'A 90-degree pipe elbow with 30mm outer diameter, 3mm wall, swept over an 80mm radius, with an 80mm round mounting flange with 6 bolt holes on a 60mm bolt circle.', ts: now() });
        const a1 = { id: uid(), role: 'assistant', kind: 'model', status: 'done', thought: THOUGHT, attempts: [{ error: 'timeline[4] (extrude): sketch "flange_sk" has no closed profiles' }], request: 'x', ts: now() };
        cur.turns.push(a1);
        Object.assign(a1, { version: addVersion(elbow('8 mm'), 'model').n, replaced: null });
        cur.turns.push({ id: uid(), role: 'user', text: 'Make the flange thicker, about 12 mm.', ts: now() });
        const a2 = { id: uid(), role: 'assistant', kind: 'model', status: 'done', thought: 'Only flange_thick changes.', attempts: [], request: 'x', ts: now(),
          tools: [{ name: 'list_parameters', label: 'Listed user parameters · 8' }, { name: 'get_feature', label: 'Inspected feature f4 · flange' }] };
        cur.turns.push(a2);
        const r2 = addVersion(elbow('12 mm'), 'model');
        Object.assign(a2, { version: r2.n, replaced: r2.replaced });
        cur.turns.push({ id: uid(), role: 'user', text: 'Add a 45° gusset between the flange and the pipe. Make it fail please.', ts: now() });
        cur.turns.push({ id: uid(), role: 'assistant', kind: 'model', status: 'error', thought: '', request: 'x',
          attempts: [{ error: 'timeline[7] (extrude): no closed profiles' }, { error: 'timeline[7] (extrude): no closed profiles' }],
          error: "Gemini: 429 Resource has been exhausted (e.g. check quota).", ts: now() });
      }

      const handlers = {
        ready() {
          if (/[?&]demo\b/.test(location.search)) seedDemo();
          if (!cur) newChat();
          emit({ type: 'state', chats: summaries(), chat: view(), providers, active_provider: active, general, busy, components: !/[?&]part\b/.test(location.search) });
        },
        send({ text }) { if (!busy) sendText(text); },
        retry({ turn_id }) {
          const t = cur.turns.find((x) => x.id === turn_id);
          if (!t || busy) return;
          Object.assign(t, { status: 'thinking', thought: '', attempts: [], error: null });
          runModel(t, t.request.replace(/fail/gi, ''));
        },
        stop() {
          busy = false; timers.forEach(clearTimeout); timers = [];
          const t = cur.turns[cur.turns.length - 1];
          if (t && ['thinking', 'writing', 'building'].includes(t.status)) t.status = 'stopped';
          pushChat();
        },
        new_chat() {
          if (!cur || cur.turns.length) newChat();
          pushChat();
        },
        switch_chat({ id }) { cur = chats.find((c) => c.id === id) || cur; pushChat(); },
        delete_chat({ id }) {
          if (busy) return;
          const gone = chats.find((c) => c.id === id);
          if (!gone) return;
          chats = chats.filter((c) => c !== gone);
          if (cur === gone) {
            const rest = chats.filter((c) => c.turns.length);
            if (rest.length) cur = rest[rest.length - 1]; else newChat();
          }
          pushChat();
          emit({ type: 'toast', text: 'Chat deleted' });
        },
        confirm_replace({ turn_id, choice }) {
          const t = cur.turns.find((x) => x.id === turn_id);
          if (choice === 'cancel') { t.status = 'stopped'; pushChat(); return; }
          t.status = 'building'; busy = true; pushChat();
          later(600, () => finish(t, elbow('14 mm'), 'model'));
        },
        apply_json({ text }) {
          cur.turns.push({ id: uid(), role: 'user', text, is_json: true, ts: now() });
          const t = { id: uid(), role: 'assistant', kind: 'json', status: 'building', thought: '', attempts: [], ts: now() };
          cur.turns.push(t); busy = true; pushChat();
          later(600, () => finish(t, JSON.parse(text), 'json'));
        },
        restore_version({ n }) {
          const v = cur.versions.find((x) => x.n === n);
          const t = { id: uid(), role: 'assistant', kind: 'restore', status: 'building', thought: '', attempts: [], restored_from: n, ts: now() };
          cur.turns.push(t); busy = true; pushChat();
          later(600, () => finish(t, JSON.parse(JSON.stringify(v.dsl)), 'restore'));
        },
        set_param({ name, expr }) {
          later(250, () => {
            if (!/\d/.test(expr)) { emit({ type: 'param', name, ok: false, error: `"${expr}" is not a valid expression` }); return; }
            const v = cur.versions.find((x) => x.n === cur.current);
            v.dsl.parameters[name] = expr;
            emit({ type: 'param', name, ok: true, chat: view() });
          });
        },
        validate_json({ text }) {
          try {
            const d = JSON.parse(text);
            if (!Array.isArray(d.timeline) || !d.timeline.length) throw new Error('timeline must be a non-empty list');
            emit({ type: 'json_check', ok: true, steps: d.timeline.length });
          } catch (e) { emit({ type: 'json_check', ok: false, error: e.message }); }
        },
        get_models({ provider, values }) {
          later(600, () => {
            const p = providers.find((x) => x.id === provider);
            const v = values || p.values;
            if (provider === 'gemini' && !/^AIza/.test(v.api_key || '')) { emit({ type: 'models', provider, models: [], error: 'Gemini: API key not valid. Please pass a valid API key.' }); return; }
            if (provider === 'openai_compat' && !/^https?:\/\//.test(v.url || '')) { emit({ type: 'models', provider, models: [], error: 'Could not connect: URL must start with http:// or https://' }); return; }
            p.models = MODELS[provider].slice();
            emit({ type: 'models', provider, models: p.models, selected: p.model });
          });
        },
        select_model({ provider, model }) {
          active = provider;
          providers.find((x) => x.id === provider).model = model;
        },
        set_model_option({ provider, model, think }) {
          const p = providers.find((x) => x.id === provider);
          p.model_options[model] = { think: !!think };
        },
        save_provider({ provider, values }) {
          const p = providers.find((x) => x.id === provider);
          for (const f of p.schema) if (f.key in values) p.values[f.key] = values[f.key];
          p.configured = isReady(p);
          emit({ type: 'provider_status', provider, configured: p.configured });
        },
        set_target({ mode }) {
          if (['component', 'new_body'].includes(mode)) cur.target.mode = mode;
          pushChat();
        },
        save_general({ values }) {
          if (['component', 'new_body'].includes(values.default_mode)) general.default_mode = values.default_mode;
          if (['system', 'light', 'dark'].includes(values.theme)) general.theme = values.theme;
          if (values.auto_fix !== undefined) general.auto_fix = Math.max(0, Math.min(5, Number(values.auto_fix) || 0));
        },
        copy({ text }) {
          (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).catch(() => {});
          emit({ type: 'toast', text: 'Copied to clipboard' });
        },
        open_bom({ n }) {
          const v = cur.versions.find((x) => x.n === n) || cur.versions.find((x) => x.n === cur.current);
          const rows = v ? [
            { category: 'Made', item: cur.title || 'Main part', qty: '1', unit: 'pcs', note: '6061 Aluminum', link: '', made: true },
            { category: 'Fasteners', item: 'M4 x 12 socket head cap screw', qty: '4', unit: 'pcs', note: 'Stainless', link: 'https://example.com/m4', made: false },
          ] : [];
          const csv = 'Category,Item,Qty,Unit,Note,Link\n' + rows.map((r) => [r.category, r.item, r.qty, r.unit, r.note, r.link].join(',')).join('\n') + '\n';
          try {
            localStorage.setItem('vibeshaper_mock_bom', JSON.stringify({
              type: 'bom', theme: general.theme, empty: !v, title: cur.title, version: v ? v.n : null,
              is_current: Boolean(v && v.n === cur.current), rows, csv, buy_count: 1, make_count: 1,
            }));
          } catch (_) {}
          window.open('bom.html?mock', 'VibeShaper_BOM', 'width=820,height=560,resizable=yes');
        },
      };

      return (action, data) => {
        const fn = handlers[action];
        if (fn) setTimeout(() => fn(JSON.parse(data || '{}')), 30);
        return 'OK';
      };
    },
  };

  // ---------------------------------------------------------------- boot
  wire();
  renderAll();
  autosize();
  $('input').focus();
  connect();
})();
