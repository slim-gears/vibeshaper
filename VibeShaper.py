"""VibeShaper add-in for Autodesk Fusion 360.
Builds parametric design history from natural language prompts using pluggable AI providers.

UI: a docked HTML palette (palette/) with a chat per part. Each chat owns one timeline group;
a new version replaces the previous one inside a single command, so a failed rebuild is rolled
back by Fusion and the previous version stays.

Threads: Fusion's API is main-thread only. The model call runs on a worker thread and reports
back through custom events; builds run inside a hidden command (a transaction).
"""
import importlib
import itertools
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import traceback

import adsk.core
import adsk.fusion

from . import chat, dsl, llm, providers, shapes, userdata
from . import tools as toolbox

def _reload_plugins(package):
    """Reload a plugin package's interface (base), every plugin, then the registry (which re-discovers
    them). Reloading only the package would leave old plugin code in place after Stop/Run."""
    prefix = package.__name__ + '.'
    subs = sorted((n for n in list(sys.modules) if n.startswith(prefix)), key=lambda n: n != prefix + 'base')
    for name in subs:
        importlib.reload(sys.modules[name])
    importlib.reload(package)


def _reload_providers():
    _reload_plugins(providers)


_reload_plugins(shapes)  # before dsl, which reads the shapes when it loads
importlib.reload(dsl)  # pick up edits on add-in Stop/Run without restarting Fusion
importlib.reload(userdata)
_reload_providers()
_reload_plugins(toolbox)
importlib.reload(llm)
importlib.reload(chat)

CMD_ID = 'VibeShaper_Generate'
BUILD_ID = 'VibeShaper_Build'
PALETTE_ID = 'VibeShaper_Palette'
EVENT_ID = 'VibeShaper_Result'
PROGRESS_EVENT_ID = 'VibeShaper_Progress'
MODELS_EVENT_ID = 'VibeShaper_Models'
SAVE_EVENT_ID = 'VibeShaper_Save'
TOOL_EVENT_ID = 'VibeShaper_Tool'  # the worker asks the main thread to run a tool
TOOL_TIMEOUT = 30
PANEL_ID = 'SolidCreatePanel'
# auto_fix: automatic fixes after a failed build; default_mode: where new chats build
GENERAL_DEFAULTS = {'theme': 'system', 'auto_fix': 2, 'default_mode': 'component'}
THEMES = ('system', 'light', 'dark')
BUILD_MODES = ('component', 'new_body')
MAX_AUTO_FIX = 5
ATTR_GROUP, ATTR_NAME = 'VibeShaper', 'chats'
HERE = pathlib.Path(__file__).parent
SETTINGS = userdata.path('settings.json')  # outside the add-in folder: see userdata.py
SETTINGS_VERSION = 1  # layout of settings.json; bump (and upgrade old files) when it changes
PALETTE_HTML = HERE / 'palette' / 'index.html'

_handlers = []  # Fusion needs handler references kept alive
_job = {}  # the one generation/build in flight (see _new_job)
_job_ids = itertools.count(1)
_ctx = {'store': None}  # chats of the active design
_models_cache = {}  # provider id -> last fetched models: [{id, label, images, thinking, tools}]
_tool_waits = {}  # tool request key -> {'event', 'result'}: worker threads waiting on the main thread
_tool_keys = itertools.count(1)


def _app():
    return adsk.core.Application.get()


def _log(msg):
    _app().log(msg)


# ---------------------------------------------------------------- settings

# settings.json layout (version 1):
#   {"version": 1, "general": {...}, "selection": {"provider": id},
#    "providers": {id: {"values": {...}, "model": str, "model_options": {model: {"think": bool}}}}}
# "values" belong to the provider and are all it ever sees; the rest is VibeShaper's own record.

def _provider_entry(prov, saved=None):
    saved = saved if isinstance(saved, dict) else {}
    opts = saved.get('model_options') if isinstance(saved.get('model_options'), dict) else {}
    return {
        'values': providers.clean_values(prov.get_settings_schema(), saved.get('values') or {}),
        'model': str(saved.get('model') or ''),
        'model_options': {str(m): {'think': bool((o or {}).get('think'))} for m, o in opts.items() if isinstance(o, dict)},
    }


def _load_settings():
    all_provs = providers.get_all_providers()
    s = {
        'version': SETTINGS_VERSION,
        'general': dict(GENERAL_DEFAULTS),
        'selection': {'provider': all_provs[0].id if all_provs else None},
        'providers': {p.id: _provider_entry(p) for p in all_provs},
    }
    try:
        saved = json.loads(SETTINGS.read_text())
    except Exception:
        return s
    if not isinstance(saved, dict) or saved.get('version') != SETTINGS_VERSION:
        return s  # a layout this version doesn't know: start from defaults (the file is left alone until a save)
    if isinstance(saved.get('general'), dict):
        s['general'].update(_clean_general(saved['general'], s['general']))
    for pid, entry in (saved.get('providers') or {}).items():
        prov = providers.get_provider(pid)
        # keep entries of providers that aren't installed right now, untouched
        s['providers'][pid] = _provider_entry(prov, entry) if prov else entry
    sel = (saved.get('selection') or {}).get('provider')
    if providers.get_provider(sel) if sel else False:
        s['selection']['provider'] = sel
    return s


def _clean_general(values, current):
    """Keep only known general settings with valid values."""
    out = {}
    if values.get('theme') in THEMES:
        out['theme'] = values['theme']
    if values.get('default_mode') in BUILD_MODES:
        out['default_mode'] = values['default_mode']
    try:
        out['auto_fix'] = max(0, min(MAX_AUTO_FIX, int(values['auto_fix'])))
    except (KeyError, TypeError, ValueError):
        pass
    return {k: out.get(k, current.get(k, GENERAL_DEFAULTS[k])) for k in GENERAL_DEFAULTS}


def _general():
    return {**GENERAL_DEFAULTS, **(_load_settings().get('general') or {})}


def _save_settings(s):
    try:
        SETTINGS.write_text(json.dumps(s, indent=1))
    except Exception:
        pass


def _keep(handler, event):
    event.add(handler)
    _handlers.append(handler)


def _copy_to_clipboard(text):
    try:
        if sys.platform == 'darwin':
            subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=True)
        else:
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            subprocess.run(['clip'], input=text.encode('utf-16'), check=True, creationflags=flags)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- palette I/O

def _palette():
    try:
        return _app().userInterface.palettes.itemById(PALETTE_ID)
    except Exception:
        return None


def _emit(ev):
    pal = _palette()
    if not pal:
        return
    try:
        pal.sendInfoToHTML('event', json.dumps(ev))
    except Exception as e:
        _log(f'VibeShaper: could not update panel: {e}')


def _toast(text):
    _emit({'type': 'toast', 'text': text})


def _providers_view():
    s = _load_settings()
    out = []
    for p in providers.get_all_providers():
        entry = s['providers'].get(p.id) or _provider_entry(p)
        out.append({
            'id': p.id, 'name': p.name, 'short_name': p.short_name,
            'schema': [f.to_view() for f in p.get_settings_schema()],
            'values': entry['values'],
            'model': entry['model'],
            'model_options': entry['model_options'],
            'models': _models_cache.get(p.id, []),
            'configured': bool(p.is_configured(entry['values'])),
        })
    return out, s['selection']['provider']


def _model_info(prov_id, model):
    """What the model can do, if its provider has listed it this session (else None)."""
    return next((m for m in _models_cache.get(prov_id, []) if m.get('id') == model), None)


def _busy():
    return bool(_job.get('active'))


def _emit_state():
    store = _store()
    c = store.ensure_active() if store else None
    provs, active = _providers_view()
    _emit({'type': 'state', 'chats': store.summaries() if store else [],
           'chat': c.to_view() if c else None, 'providers': provs,
           'active_provider': active, 'general': _general(), 'busy': _busy(),
           'has_design': store is not None, 'components': _components_allowed()})


def _components_allowed():
    """Part Design documents hold one component, so "New component" isn't available there."""
    try:
        d = _active_design()
        return dsl.supports_components(d) if d else True
    except Exception:
        return True


def _emit_chat(c):
    store = _store()
    _emit({'type': 'chat', 'chat': c.to_view(), 'chats': store.summaries() if store else [], 'busy': _busy()})


# ---------------------------------------------------------------- chats stored in the design

def _active_design():
    prod = _app().activeProduct
    return prod if isinstance(prod, adsk.fusion.Design) else None


def _design():
    d = _active_design()
    if not d:
        raise ValueError('Open a Fusion 360 design first.')
    return d


def _store(reload=False):
    if _ctx['store'] is not None and not reload:
        return _ctx['store']
    design = _active_design()
    if not design:
        _ctx['store'] = None
        return None
    text = ''
    try:
        attr = design.attributes.itemByName(ATTR_GROUP, ATTR_NAME)
        text = attr.value if attr else ''
    except Exception as e:
        _log(f'VibeShaper: could not read saved chats: {e}')
    _ctx['store'] = chat.ChatStore.from_json(text)
    return _ctx['store']


def _save_store_later():
    """Save after the current command finishes, so a rolled-back build can't undo the save."""
    try:
        _app().fireCustomEvent(SAVE_EVENT_ID, '')
    except Exception:
        _save_store()


class _SaveLater(adsk.core.CustomEventHandler):
    def notify(self, args):
        _save_store()


def _live_version(c, design):
    """Newest version whose timeline group is still in the design.

    Usually the chat's current version; after an Undo in Fusion it can be an older one.
    """
    for v in reversed(c.versions):
        if v.get('group_name') and dsl.find_group(design, v['group_name']):
            return v
    return None


def _save_store():
    store, design = _ctx['store'], _active_design()
    if not store or not design:
        return
    try:
        payload = store.to_json()
        attr = design.attributes.itemByName(ATTR_GROUP, ATTR_NAME)
        if attr:
            if attr.value != payload:
                attr.value = payload
        elif store.chats:
            design.attributes.add(ATTR_GROUP, ATTR_NAME, payload)
    except Exception as e:
        _log(f'VibeShaper: could not save chats in the design: {e}')


# ---------------------------------------------------------------- jobs

def _new_job(c, turn, **fields):
    _job.clear()
    _job.update(id=next(_job_ids), active=True, chat_id=c.id, turn_id=turn['id'], builds=0, **fields)
    return _job


def _job_target():
    """(chat, turn) for the running job, or (None, None) if it no longer applies."""
    store = _ctx['store']
    if not _job.get('active') or not store:
        return None, None
    c = store.get(_job['chat_id'])
    t = c.turn(_job['turn_id']) if c else None
    return c, t


def _finish_job():
    _job['active'] = False


def _fail_turn(c, t, err):
    t['status'] = 'error'
    t['error'] = err
    if t.get('kind') == 'model':
        c.rollback_model_request(t)
    _finish_job()
    _save_store_later()
    _emit_chat(c)


def _stop_worker():
    se = _job.get('stop_event')
    if se:
        se.set()
    resp = _job.get('active_resp')
    if resp:
        try:
            resp.close()
        except Exception:
            pass


def _start_worker():
    """Run llm.generate off the main thread; the result comes back via EVENT_ID."""
    prov_id = _job['provider_id']
    values = _job['values']
    model = _job['model']
    job_id = _job.get('id')
    stop_event = threading.Event()
    _job['stop_event'] = stop_event
    _job['active_resp'] = None


    lock = threading.Lock()
    buf = {'thought': [], 'chars': 0, 'last': 0.0, 'writing': False}

    def flush(force=False):
        with lock:
            now = time.time()
            if not force and now - buf['last'] < 0.12:
                return
            buf['last'] = now
            thought = ''.join(buf['thought'])
            buf['thought'].clear()
            payload = {'job': job_id, 'thought': thought, 'chars': buf['chars'], 'writing': buf['writing']}
        _app().fireCustomEvent(PROGRESS_EVENT_ID, json.dumps(payload))

    def on_chunk(kind, text):
        if stop_event.is_set():
            return
        with lock:
            if kind == 'thought':
                buf['thought'].append(text)
            else:
                buf['chars'] += len(text)
                buf['writing'] = True
        flush()

    def work():
        try:
            d = llm.generate(prov_id, values, model, _job['messages'], think=_job.get('think', False),
                             tools=toolbox.specs(_job_toolkits()) or None,
                             run_tool=lambda name, args: _call_tool_on_main(job_id, name, args, stop_event),
                             on_chunk=on_chunk,
                             stop_event=stop_event,
                             on_open=lambda resp: _job.update(active_resp=resp),
                             log=_log)
            flush(force=True)
            payload = {'dsl': d}
        except InterruptedError:
            payload = {'stopped': True}
        except Exception as e:
            payload = {'stopped': True} if stop_event.is_set() else {'error': f'{type(e).__name__}: {e}'}
        payload['job'] = job_id
        _app().fireCustomEvent(EVENT_ID, json.dumps(payload))

    threading.Thread(target=work, daemon=True).start()


def _call_tool_on_main(job_id, name, args, stop_event):
    """Worker thread: Fusion's API only works on the main thread, so ask it to run the tool and wait."""
    key = next(_tool_keys)
    slot = {'event': threading.Event(), 'result': None}
    _tool_waits[key] = slot
    _app().fireCustomEvent(TOOL_EVENT_ID, json.dumps({'key': key, 'job': job_id, 'name': name, 'args': args}))
    end = time.time() + TOOL_TIMEOUT
    while not slot['event'].wait(0.05):
        if stop_event.is_set():
            _tool_waits.pop(key, None)
            raise InterruptedError('Generation cancelled by user')
        if time.time() > end:
            _tool_waits.pop(key, None)
            return {'error': 'Fusion did not answer in time.'}
    return slot['result']


def _capabilities(info):
    """What a model can do, as names ('images', 'tools', ...) from its entry in the model list."""
    return {k for k, v in (info or {}).items() if v is True}


def _job_toolkits():
    """The toolkits offered to the current job's model."""
    return [k for k in (toolbox.get_toolkit(i) for i in _job.get('toolkits') or ()) if k]


def _tool_context(toolkit, design, store):
    """A toolkit's view: the app, the design, and its own saved state for this document."""
    state = store.tool_state.setdefault(toolkit.id, {}) if store is not None else {}
    return toolbox.ToolContext(_app(), design, state)


class _ToolRequest(adsk.core.CustomEventHandler):
    """Main thread: run a tool for the worker and record it on the turn."""

    def notify(self, args):
        result = {'error': 'The tool could not run.'}
        slot = None
        try:
            r = json.loads(args.additionalInfo)
            slot = _tool_waits.pop(r.get('key'), None)
            if slot is None:
                return  # the worker gave up (stopped or timed out)
            name, targs = r.get('name', ''), r.get('args') or {}
            design, store = _active_design(), _store()
            if r.get('job') != _job.get('id'):
                result = {'error': 'This request was cancelled.'}
            elif not design:
                result = {'error': 'No design is open.'}
            elif not (kit := toolbox.owner(name, _job_toolkits())):
                result = {'error': f'There is no tool called "{name}".'}
            else:
                result = toolbox.run(kit, name, targs, _tool_context(kit, design, store))
                c, t = _job_target()
                if t:
                    entry = {'name': name, 'label': toolbox.label(kit, name, targs, result)}
                    t.setdefault('tools', []).append(entry)
                    _emit({'type': 'stream', 'chat_id': c.id, 'turn_id': t['id'], 'tool': entry})
                    _save_store_later()
        except Exception:
            _log('VibeShaper: tool error\n' + traceback.format_exc())
        finally:
            if slot is not None:
                slot['result'] = result
                slot['event'].set()


class _Progress(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            r = json.loads(args.additionalInfo)
            if r.get('job') != _job.get('id'):
                return
            c, t = _job_target()
            if not t:
                return
            ev = {'type': 'stream', 'chat_id': c.id, 'turn_id': t['id']}
            if r.get('thought'):
                t['thought'] = (t.get('thought') or '') + r['thought']
                ev['thought_append'] = r['thought']
            if r.get('writing') and t.get('status') == 'thinking':
                t['status'] = ev['status'] = 'writing'
            if r.get('writing'):
                t['chars'] = ev['chars'] = r.get('chars', 0)
            _emit(ev)
        except Exception:
            _log('VibeShaper: progress error\n' + traceback.format_exc())


class _Result(adsk.core.CustomEventHandler):
    """Model reply arrived (main thread)."""

    def notify(self, args):
        try:
            r = json.loads(args.additionalInfo)
            if r.get('job') is not None and r.get('job') != _job.get('id'):
                return  # a stopped/replaced job finishing late
            c, t = _job_target()
            if not t:
                _finish_job()
                return
            if r.get('stopped'):
                t['status'] = 'stopped'
                c.rollback_model_request(t)
                _finish_job()
                _save_store()
                _emit_chat(c)
                return
            if 'error' in r:
                _fail_turn(c, t, r['error'])
                return
            _job['dsl'] = r['dsl']
            _log('VibeShaper DSL:\n' + json.dumps(r['dsl']))
            _prepare_build(c, t)
        except Exception:
            c, t = _job_target()
            if t:
                _fail_turn(c, t, traceback.format_exc())


class _ModelsReady(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            r = json.loads(args.additionalInfo)
            if r.get('models'):
                _models_cache[r['provider']] = r['models']
            _emit({'type': 'models', **r})
        except Exception:
            pass


# ---------------------------------------------------------------- building

def _prepare_build(c, t, confirmed=False):
    """Decide whether the new design replaces the chat's current version, then build."""
    design = _design()
    prev = _live_version(c, design)
    if prev and not confirmed:
        n_after = dsl.user_features_after(design, prev['group_name'])
        if n_after:
            t['status'] = 'confirm'
            t['confirm'] = {'count': n_after}
            _save_store()
            _emit_chat(c)
            return
    if _job.get('replace') is None:
        _job['replace'] = prev is not None
    t['status'] = 'building'
    t.pop('confirm', None)
    _emit({'type': 'stream', 'chat_id': c.id, 'turn_id': t['id'], 'status': 'building'})
    try:
        cmd_def = _app().userInterface.commandDefinitions.itemById(BUILD_ID)
        if not cmd_def:
            raise RuntimeError(f"Command definition '{BUILD_ID}' not found")
        cmd_def.execute()
    except Exception:
        _handle_build_failure(traceback.format_exc())


class _BuildCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        cmd = args.command
        _keep(_BuildExecute(), cmd.execute)
        _keep(_BuildFailed(), cmd.executeFailed)


def _build_progress(c, t):
    """progress(done, total, label) for dsl.execute: the panel shows a bar with the current step.
    The build runs on Fusion's main thread, and the panel only receives messages while Fusion's
    event loop runs, so each step lets it run a few times."""
    def progress(done, total, label):
        _emit({'type': 'stream', 'chat_id': c.id, 'turn_id': t['id'],
               'progress': {'done': done, 'total': total, 'label': str(label)}})
        try:
            for _ in range(3):
                adsk.doEvents()
        except Exception:
            pass
    return progress


class _BuildExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        importlib.reload(dsl)  # live hot-load dsl.py edits without restarting add-in
        c, t = _job_target()
        d = _job.get('dsl')
        if not t or not d:
            return
        _job['build_failed_handled'] = False
        stage = 'replace'
        occ = None
        progress = _build_progress(c, t)
        try:
            design = _design()
            prev = _live_version(c, design)
            replaced = None
            if _job.get('replace') and prev:
                progress(0, 1, f'Removing v{prev["n"]}')
                removed = dsl.delete_version(design, prev['group_name'], list(prev.get('param_map', {}).values()),
                                             prev.get('occurrences', []))
                if removed:
                    replaced = prev['n']
                if removed == 'suppressed':
                    _log(f'VibeShaper: Fusion would not delete v{prev["n"]}; suppressed it instead')
            stage = 'place'
            mode = _mode(c)
            comp = None
            placement = {'mode': 'new_body', 'label': None}
            if mode == 'component' and dsl.supports_components(design):
                try:
                    occ = dsl.ensure_component(design, c.target.get('occ'), _component_name(c, d))
                    comp = occ.component
                    placement = {'mode': mode, 'label': comp.name}
                except dsl.ComponentsNotAllowed:
                    _log('VibeShaper: this document holds one component; building as new bodies')
            stage = 'build'
            n = (c.versions[-1]['n'] + 1) if c.versions else 1
            info = dsl.execute(design, d, group_name=c.group_name(n), comp=comp, progress=progress)
        except Exception:
            _job['build_failed_handled'] = True
            err = traceback.format_exc()
            args.executeFailed = True  # Fusion rolls back the whole command, including the delete
            args.executeFailedMessage = err
            # Not the design's fault: asking the model to "fix" these would only waste attempts.
            if isinstance(sys.exc_info()[1], dsl.ComponentsNotAllowed):
                _handle_build_failure(err, heal=False, title='This document holds one component (a Part Design), '
                                                             'so a design with components can’t be built here')
            elif stage == 'replace':
                _handle_build_failure(err, heal=False, title='Could not remove the previous version')
            elif stage == 'place':
                _handle_build_failure(err, heal=False, title='Could not place the design')
            else:
                _handle_build_failure(err)
            return

        source = {'model': 'model', 'json': 'json', 'restore': 'restore'}.get(t.get('kind'), 'model')
        if occ is not None:
            c.target['occ'] = occ.entityToken
        v = c.add_version(d, source, group_name=info['group_name'], param_map=info['param_map'],
                          feature_count=info['feature_count'], placement=placement,
                          occurrences=info.get('occurrences'))
        t.update(status='done', version=v['n'], replaced=replaced)
        if t.get('kind') == 'model':
            c.commit_model_success(t, d)
        else:
            c.note_manual_design(d)
        _log(f'VibeShaper: built v{v["n"]} (attempt {_job.get("builds", 0) + 1})')
        _log_transcript(d, None)
        _finish_job()
        _save_store_later()
        _emit_chat(c)


class _BuildFailed(adsk.core.CommandEventHandler):
    """Fusion rolled back the failed transaction."""

    def notify(self, args):
        if _job.get('build_failed_handled'):
            _job['build_failed_handled'] = False
            return
        _handle_build_failure(traceback.format_exc().strip() or 'Build failed')


def _log_transcript(d, err):
    try:
        msgs = _job.get('messages') or []
        prompt = next((m['content'] for m in reversed(msgs) if m['role'] == 'user'), '[JSON]')
        c, t = _job_target()
        llm.log_transcript(_job.get('provider_id', '-'), _job.get('model', ''), prompt, json.dumps(d or {}),
                           (t or {}).get('thought', ''), error=err, attempt=_job.get('builds', 0) + 1)
    except Exception as e:
        _log(f'VibeShaper: log_transcript error: {e}')


def _short_error(err):
    lines = [ln for ln in str(err).strip().splitlines() if ln.strip()]
    return lines[-1] if lines else 'Build failed'


def _handle_build_failure(err, heal=True, title='Build failed'):
    err = str(err).strip()
    c, t = _job_target()
    if not t:
        _finish_job()
        return
    _job['builds'] = _job.get('builds', 0) + 1
    attempt = _job['builds']
    _log(f'VibeShaper: build failed (attempt {attempt}):\n{err}')
    _log_transcript(_job.get('dsl'), err)

    can_heal = heal and t.get('kind') == 'model' and attempt <= int(_general()['auto_fix']) and _job.get('messages')
    if not can_heal:
        _fail_turn(c, t, f'{title}: {_short_error(err)}\n\n{err}')
        return

    # Self-healing: show the error to the model and ask for a corrected design.
    t.setdefault('attempts', []).append({'error': _short_error(err)})
    t['status'] = 'thinking'
    _job['messages'].append({'role': 'assistant', 'content': json.dumps(_job.get('dsl', {}))})
    _job['messages'].append({'role': 'user', 'content': (
        f'The design produced an error in Autodesk Fusion 360:\n{err}\n'
        'Fix the error and output the complete corrected JSON DSL.')})
    _job['dsl'] = None
    _save_store_later()
    _emit({'type': 'stream', 'chat_id': c.id, 'turn_id': t['id'], 'status': 'thinking',
           'attempt_error': _short_error(err)})
    _start_worker()


# ---------------------------------------------------------------- actions from the panel

def _mode(c):
    """The chat's build mode, or the default from Settings."""
    m = c.target.get('mode')
    return m if m in BUILD_MODES else _general().get('default_mode', 'component')


def _component_name(c, d):
    name = str(d.get('name') or '').replace('_', ' ').strip() or c.title
    return name[:40].strip() or 'VibeShaper part'


def _start_model_turn(c, t, text):
    s = _load_settings()
    prov_id = s['selection']['provider']
    prov = providers.get_provider(prov_id) if prov_id else None
    if not prov:
        return _fail_turn(c, t, 'No model provider is selected. Pick a model from the menu at the top of the panel.')
    entry = s['providers'][prov_id]
    values, model = entry['values'], entry['model']
    if not prov.is_configured(values):
        return _fail_turn(c, t, f'{prov.name} is not set up yet. Open Settings (gear icon) → {prov.name}.')
    if not model:
        return _fail_turn(c, t, 'No model selected. Pick one from the model menu at the top of the panel.')

    think = entry['model_options'].get(model, {}).get('think', False)
    info = _model_info(prov_id, model)
    if info is not None and not info.get('thinking'):
        think = False  # the provider says this model can't
    caps = _capabilities(info)
    kits = toolbox.usable(caps)
    use_tools = 'tools' in caps and bool(toolbox.specs(kits))
    c.begin_model_request(text, t)
    messages = c.model_messages(llm.system_prompt(tools=use_tools, notes=toolbox.prompt(kits) if use_tools else ''))
    if not use_tools:
        messages[-1] = dict(messages[-1], content=llm.with_design_context(messages[-1]['content'], _design_summary(kits)))
    _new_job(c, t, provider_id=prov_id, values=values, model=model, think=think,
             toolkits=[k.id for k in kits] if use_tools else [], messages=messages, replace=None)
    _save_store()
    _emit_chat(c)
    _start_worker()


def _design_summary(toolkits):
    """For models that can't call tools: what the toolkits can tell about the open design ('' if nothing)."""
    design, store = _active_design(), _store()
    if not design:
        return ''
    parts = [toolbox.summary(k, _tool_context(k, design, store)) for k in toolkits]
    return '\n\n'.join(p for p in parts if p)


def _parse_dsl(text):
    d = json.loads(text)
    dsl.validate(json.loads(text))  # validate a copy; validate() may fill in defaults
    return d


def _start_json_turn(c, t, d):
    _new_job(c, t, provider_id='-', model='', messages=None, dsl=d, replace=None)
    _emit_chat(c)
    _prepare_build(c, t)


def _act_send(data):
    text = str(data.get('text', '')).strip()
    if not text or _busy():
        return
    _design()
    store = _store()
    c = store.ensure_active()
    c.add_user_turn(text)
    if chat.looks_like_json(text):
        t = c.add_assistant_turn('json')
        try:
            d = _parse_dsl(text)
        except Exception as e:
            t.update(status='error', error=f'This JSON can’t be built: {e}')
            _save_store()
            _emit_chat(c)
            return
        _start_json_turn(c, t, d)
    else:
        t = c.add_assistant_turn('model')
        _start_model_turn(c, t, text)


def _act_retry(data):
    if _busy():
        return
    store = _store()
    c = store.active() if store else None
    t = c.turn(data.get('turn_id')) if c else None
    if not t or t.get('kind') != 'model' or not t.get('request'):
        return
    t.update(status='thinking', thought='', attempts=[], error=None, chars=0)
    _start_model_turn(c, t, t['request'])


def _act_stop(_data):
    if not _busy():
        return
    _stop_worker()
    c, t = _job_target()
    _job['id'] = None  # ignore anything the worker still sends
    if t:
        t['status'] = 'stopped'
        if t.get('kind') == 'model':
            c.rollback_model_request(t)
    _finish_job()
    _save_store()
    if c:
        _emit_chat(c)


def _act_confirm_replace(data):
    c, t = _job_target()
    if not t or t.get('id') != data.get('turn_id') or t.get('status') != 'confirm':
        return
    choice = data.get('choice')
    if choice == 'cancel':
        return _act_stop({})
    _job['replace'] = choice == 'replace'
    _prepare_build(c, t, confirmed=True)


def _act_apply_json(data):
    if _busy():
        return
    text = str(data.get('text', ''))
    _design()
    store = _store()
    c = store.ensure_active()
    try:
        d = _parse_dsl(text)
    except Exception as e:
        _toast(f'Can’t build this JSON: {e}')
        return
    c.add_user_turn(json.dumps(d))
    t = c.add_assistant_turn('json')
    _start_json_turn(c, t, d)


def _act_restore_version(data):
    if _busy():
        return
    _design()
    store = _store()
    c = store.active() if store else None
    v = c.version(int(data.get('n'))) if c else None
    if not v:
        return
    t = c.add_assistant_turn('restore', restored_from=v['n'])
    _start_json_turn(c, t, json.loads(json.dumps(v['dsl'])))


def _act_set_param(data):
    name, expr = str(data.get('name', '')), str(data.get('expr', '')).strip()

    def reply(ok, error=None, c=None):
        ev = {'type': 'param', 'name': name, 'ok': ok}
        if error:
            ev['error'] = error
        if c:
            ev['chat'] = c.to_view()
        _emit(ev)

    if _busy():
        return reply(False, 'Wait for the current build to finish.')
    design = _design()
    store = _store()
    c = store.active() if store else None
    v = c.current_version() if c else None
    if not v:
        return reply(False, 'There is no built design yet.')
    fusion_name = v.get('param_map', {}).get(name, name)
    p = design.userParameters.itemByName(fusion_name)
    if not p:
        return reply(False, f'Parameter {fusion_name} is no longer in the design.')
    if not design.unitsManager.isValidExpression(expr, p.unit):
        return reply(False, f'“{expr}” isn’t a valid {p.unit or "number"} expression.')
    try:
        p.expression = expr
    except Exception as e:
        return reply(False, f'Fusion rejected it: {e}')
    moves_parts = name in dsl.placement_parameters(v['dsl'])
    d = c.set_param_in_current(name, expr)
    _save_store()
    reply(True, c=c)
    if moves_parts:  # Fusion doesn't move a placed copy when a parameter changes; rebuild to move it
        _start_json_turn(c, c.add_assistant_turn('json'), json.loads(json.dumps(d)))


def _act_validate_json(data):
    try:
        d = _parse_dsl(str(data.get('text', '')))
        _emit({'type': 'json_check', 'ok': True, 'steps': len(d.get('timeline', []))})
    except Exception as e:
        _emit({'type': 'json_check', 'ok': False, 'error': str(e)})


def _act_new_chat(_data):
    if _busy():
        return
    store = _store()
    if not store:
        return _toast('Open a design first')
    c = store.new_chat()
    _save_store()
    _emit_chat(c)


def _act_switch_chat(data):
    if _busy():
        return _toast('Wait for the current build, or stop it first')
    store = _store()
    if not store:
        return
    c = store.switch(data.get('id'))
    _save_store()
    _emit_chat(c)


def _act_delete_chat(data):
    if _busy():
        return _toast('Wait for the current build, or stop it first')
    store = _store()
    if not store or not store.get(data.get('id')):
        return
    store.delete(data['id'])
    c = store.ensure_active()
    _save_store()
    _emit_chat(c)
    _toast('Chat deleted')


def _provider_and_entry(prov_id):
    prov = providers.get_provider(prov_id) if prov_id else None
    if not prov:
        return None, None, None
    s = _load_settings()
    return prov, s, s['providers'].setdefault(prov.id, _provider_entry(prov))


def _act_get_models(data):
    """List a provider's models: with the values typed on its Settings page (Test connection) or the saved ones."""
    prov, _s, entry = _provider_and_entry(data.get('provider'))
    if not prov:
        return
    values = providers.clean_values(prov.get_settings_schema(), data['values']) if isinstance(data.get('values'), dict) \
        else entry['values']
    current = entry['model']

    def work():
        try:
            models = [m.to_view() for m in prov.list_models(values, timeout=5)]
            ids = [m['id'] for m in models]
            payload = {'provider': prov.id, 'models': models, 'selected': current or (ids[0] if ids else '')}
            if not models:
                payload['error'] = 'No models found. Check the connection settings.'
        except Exception as e:
            payload = {'provider': prov.id, 'models': [], 'error': str(e)}
        _app().fireCustomEvent(MODELS_EVENT_ID, json.dumps(payload))

    threading.Thread(target=work, daemon=True).start()


def _act_select_model(data):
    """Model menu in the main view: choose provider + model."""
    prov, s, entry = _provider_and_entry(data.get('provider'))
    model = str(data.get('model') or '')
    if not prov or not model:
        return
    s['selection']['provider'] = prov.id
    entry['model'] = model
    _save_settings(s)


def _act_save_provider(data):
    """Settings page: the provider's own values. Never the model or the selection."""
    prov, s, entry = _provider_and_entry(data.get('provider'))
    if not prov:
        return
    incoming = data.get('values') if isinstance(data.get('values'), dict) else {}
    entry['values'] = providers.clean_values(prov.get_settings_schema(), {**entry['values'], **incoming})
    _save_settings(s)
    _emit({'type': 'provider_status', 'provider': prov.id, 'configured': bool(prov.is_configured(entry['values']))})


def _act_set_model_option(data):
    """Per-model choices VibeShaper keeps (think on/off)."""
    prov, s, entry = _provider_and_entry(data.get('provider'))
    model = str(data.get('model') or '')
    if not prov or not model:
        return
    entry['model_options'][model] = {'think': bool(data.get('think'))}
    _save_settings(s)


def _act_save_general(data):
    s = _load_settings()
    s['general'] = _clean_general(dict(data.get('values') or {}), s.get('general') or GENERAL_DEFAULTS)
    _save_settings(s)


def _act_copy(data):
    _toast('Copied to clipboard' if _copy_to_clipboard(str(data.get('text', ''))) else 'Could not copy')


def _act_ready(_data):
    _store(reload=not _busy())  # keep the in-memory chat if a build is running
    _emit_state()
    sel = _load_settings()['selection']['provider']
    prov = providers.get_provider(sel) if sel else None
    if prov and sel not in _models_cache and prov.is_configured(_load_settings()['providers'][sel]['values']):
        _act_get_models({'provider': sel})  # in the background; capabilities decide tools and Think


def _act_set_target(data):
    """Build menu: build into the chat's own component, or new bodies in the root."""
    if _busy():
        return _toast('Wait for the current build, or stop it first')
    store = _store()
    if not store:
        return _toast('Open a design first')
    c = store.ensure_active()
    if data.get('mode') in BUILD_MODES:
        c.target['mode'] = data['mode']
    _save_store()
    _emit_chat(c)


ACTIONS = {
    'set_target': _act_set_target,
    'ready': _act_ready, 'send': _act_send, 'retry': _act_retry, 'stop': _act_stop,
    'confirm_replace': _act_confirm_replace, 'apply_json': _act_apply_json,
    'restore_version': _act_restore_version, 'set_param': _act_set_param,
    'validate_json': _act_validate_json, 'new_chat': _act_new_chat, 'switch_chat': _act_switch_chat,
    'delete_chat': _act_delete_chat,
    'get_models': _act_get_models, 'select_model': _act_select_model,
    'save_provider': _act_save_provider, 'set_model_option': _act_set_model_option,
    'save_general': _act_save_general, 'copy': _act_copy,
}


class _PaletteHTML(adsk.core.HTMLEventHandler):
    def notify(self, args):
        html_args = adsk.core.HTMLEventArgs.cast(args)
        action = html_args.action
        fn = ACTIONS.get(action)
        if not fn:
            return  # Fusion's own internal messages
        try:
            fn(json.loads(html_args.data or '{}'))
        except ValueError as e:
            _toast(str(e))
        except Exception:
            err = traceback.format_exc()
            _log(f'VibeShaper: {action} failed\n{err}')
            _toast(f'Something went wrong ({action}). Details are in the Text Commands window.')
        try:
            html_args.returnData = 'OK'
        except Exception:
            pass


class _DocumentActivated(adsk.core.DocumentEventHandler):
    def notify(self, args):
        try:
            if _busy():
                _act_stop({})
            _store(reload=True)
            _emit_state()
        except Exception:
            _log('VibeShaper: document switch error\n' + traceback.format_exc())


def _show_palette():
    ui = _app().userInterface
    pal = _palette()
    if pal:
        pal.isVisible = True
        return pal
    url = str(PALETTE_HTML).replace('\\', '/')
    try:
        pal = ui.palettes.add(PALETTE_ID, 'VibeShaper', url, True, True, True, 380, 720, True)
    except Exception:
        pal = ui.palettes.add(PALETTE_ID, 'VibeShaper', url, True, True, True, 380, 720)
    try:
        pal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
    except Exception:
        pass
    _keep(_PaletteHTML(), pal.incomingFromHTML)
    return pal


class _OpenPanelCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        _keep(_OpenPanelExecute(), args.command.execute)


class _OpenPanelExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            _show_palette()
        except Exception:
            _app().userInterface.messageBox('VibeShaper could not open its panel:\n' + traceback.format_exc())


def run(context):
    app = _app()
    ui = app.userInterface
    try:
        defs = ui.commandDefinitions
        panel = ui.allToolbarPanels.itemById(PANEL_ID)

        # Remove buttons left by older names of this add-in
        for legacy_id in ('PromptCAD_Generate', 'PromptCAD_Build', 'PromptCAD_Settings',
                          'OllamaCAD_Settings', 'OllamaCAD_Generate'):
            old_ctrl = panel.controls.itemById(legacy_id)
            if old_ctrl:
                old_ctrl.deleteMe()
            old_def = defs.itemById(legacy_id)
            if old_def:
                old_def.deleteMe()

        cmd_def = defs.itemById(CMD_ID) or defs.addButtonDefinition(
            CMD_ID, 'VibeShaper', 'Chat with an AI to build and refine a parametric design')
        _keep(_OpenPanelCreated(), cmd_def.commandCreated)
        build_def = defs.itemById(BUILD_ID) or defs.addButtonDefinition(BUILD_ID, 'VibeShaper Build', '')
        _keep(_BuildCreated(), build_def.commandCreated)

        for eid in (EVENT_ID, PROGRESS_EVENT_ID, MODELS_EVENT_ID, SAVE_EVENT_ID, TOOL_EVENT_ID):
            app.unregisterCustomEvent(eid)
        _keep(_Result(), app.registerCustomEvent(EVENT_ID))
        _keep(_ToolRequest(), app.registerCustomEvent(TOOL_EVENT_ID))
        _keep(_Progress(), app.registerCustomEvent(PROGRESS_EVENT_ID))
        _keep(_ModelsReady(), app.registerCustomEvent(MODELS_EVENT_ID))
        _keep(_SaveLater(), app.registerCustomEvent(SAVE_EVENT_ID))
        _keep(_DocumentActivated(), app.documentActivated)

        ctrl = panel.controls.itemById(CMD_ID) or panel.controls.addCommand(cmd_def)
        ctrl.isPromoted = True
        app.log('VibeShaper: loaded (Solid > Create)')
    except Exception:
        ui.messageBox(traceback.format_exc())


def stop(context):
    app = _app()
    ui = app.userInterface
    try:
        _stop_worker()
        _job.clear()
        for eid in (EVENT_ID, PROGRESS_EVENT_ID, MODELS_EVENT_ID, SAVE_EVENT_ID, TOOL_EVENT_ID):
            app.unregisterCustomEvent(eid)
        pal = _palette()
        if pal:
            pal.deleteMe()
        panel = ui.allToolbarPanels.itemById(PANEL_ID)
        ctrl = panel.controls.itemById(CMD_ID)
        if ctrl:
            ctrl.deleteMe()
        defs = ui.commandDefinitions
        for cid in (CMD_ID, BUILD_ID):
            d = defs.itemById(cid)
            if d:
                d.deleteMe()
        _handlers.clear()
        _ctx['store'] = None
        app.log('VibeShaper: unloaded')
        # Purge modules so subsequent 'Run' loads fresh edits from disk
        for mod_name in list(sys.modules.keys()):
            if mod_name == 'VibeShaper' or mod_name.startswith('VibeShaper.'):
                sys.modules.pop(mod_name, None)
    except Exception:
        ui.messageBox(traceback.format_exc())
