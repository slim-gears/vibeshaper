"""Run outside Fusion: python test_dsl.py"""
import json
import os
import pathlib
import tempfile

# Settings and logs go to a throwaway folder, never the user's real ones
os.environ['VIBESHAPER_HOME'] = tempfile.mkdtemp(prefix='vibeshaper-test-')

from dsl import validate

here = pathlib.Path(__file__).parent
validate(json.loads((here / 'sample.json').read_text()))
for ex_file in (here / 'examples').glob('*.json'):
    validate(json.loads(ex_file.read_text()))

advanced_sample = {
    "parameters": {
        "width": "60 mm",
        "length": "80 mm",
        "height": "40 mm",
        "wall": "3 mm",
        "corner_r": "5 mm",
        "bolt_dia": "6 mm",
        "bolt_qty": "4"
    },
    "timeline": [
        {"op": "sketch", "id": "base", "plane": "xy",
         "entities": [{"type": "center_rectangle", "center": [0, 0], "width": "width", "height": "length"}]},
        {"op": "extrude", "id": "body", "sketch": "base", "distance": "height", "mode": "new_body"},
        {"op": "fillet", "edges": "vertical", "radius": "corner_r"},
        {"op": "shell", "remove_faces": "top", "thickness": "wall"},
        {"op": "sketch", "id": "hole", "plane": "xy",
         "entities": [{"type": "circle", "center": [15, 0], "diameter": "bolt_dia"}]},
        {"op": "extrude", "id": "hole_cut", "sketch": "hole", "distance": "wall", "mode": "cut"},
        {"op": "circular_pattern", "feature": "hole_cut", "axis": "z", "quantity": "bolt_qty"},
        {"op": "linear_pattern", "feature": "hole_cut", "direction": "x", "distance": "10 mm", "quantity": 2},
        {"op": "thread", "feature": "hole_cut", "target": "internal", "modeled": True}
    ]
}
validate(advanced_sample)

revolve_sample = {
    "parameters": {"radius": "20 mm", "height": "50 mm"},
    "timeline": [
        {"op": "sketch", "id": "rev_prof", "plane": "xz",
         "entities": [{"type": "polygon", "points": [[0, 0], [20, 0], [15, 50], [0, 50]]}]},
        {"op": "revolve", "sketch": "rev_prof", "axis": "z", "angle": "360 deg", "mode": "new_body"},
        {"op": "chamfer", "edges": "circular", "distance": "2 mm"}
    ]
}
validate(revolve_sample)

bolt_sample = {
    "parameters": {"head_dia": "16 mm", "head_h": "8 mm", "shank_dia": "10 mm", "shank_len": "40 mm"},
    "timeline": [
        {"op": "sketch", "id": "head_sk", "plane": "xy",
         "entities": [{"type": "circle", "center": [0, 0], "diameter": "head_dia"}]},
        {"op": "extrude", "id": "head", "sketch": "head_sk", "distance": "head_h", "mode": "new_body"},
        {"op": "sketch", "id": "shank_sk", "plane": "xy", "offset": "head_h",
         "entities": [{"type": "circle", "center": [0, 0], "diameter": "shank_dia"}]},
        {"op": "extrude", "id": "shank", "sketch": "shank_sk", "distance": "shank_len", "mode": "join"},
        {"op": "thread", "feature": "shank", "target": "external", "modeled": True, "designation": "M10x1.5"}
    ]
}
validate(bolt_sample)

sweep_mirror_combine_sample = {
    "parameters": {"pipe_dia": "10 mm", "sweep_h": "50 mm"},
    "timeline": [
        {"op": "sketch", "id": "prof", "plane": "xy",
         "entities": [{"type": "circle", "center": [0, 0], "diameter": "pipe_dia"}]},
        {"op": "sketch", "id": "path_sk", "plane": "xz",
         "entities": [{"type": "polyline", "points": [[0, 0], [0, 30], [20, "sweep_h"]]}]},
        {"op": "sweep", "id": "pipe_body", "sketch": "prof", "path": "path_sk", "mode": "new_body"},
        {"op": "mirror", "id": "mirrored_pipe", "feature": "pipe_body", "plane": "xz"},
        {"op": "sketch", "id": "cutter_sk", "plane": "xy",
         "entities": [{"type": "center_rectangle", "center": [0, 0], "width": "5 mm", "height": "5 mm"}]},
        {"op": "extrude", "id": "cutter_tool", "sketch": "cutter_sk", "distance": "20 mm", "mode": "new_body"},
        {"op": "combine", "target": "pipe_body", "tools": ["cutter_tool"], "mode": "cut"}
    ]
}
validate(sweep_mirror_combine_sample)

bad = [
    ({}, 'timeline'),
    ({'timeline': [{'op': 'extrude', 'sketch': 'nope', 'distance': 1}]}, 'unknown sketch'),
    ({'timeline': [{'op': 'revolve', 'sketch': 'nope'}]}, 'unknown sketch'),
    ({'timeline': [{'op': 'fillet'}]}, 'missing radius'),
    ({'timeline': [{'op': 'chamfer'}]}, 'missing distance'),
    ({'timeline': [{'op': 'shell'}]}, 'missing thickness'),
    ({'timeline': [{'op': 'circular_pattern'}]}, 'missing quantity'),
    ({'timeline': [{'op': 'linear_pattern'}]}, 'missing distance'),
    ({'timeline': [{'op': 'fillet', 'edges': 'sideways', 'radius': '2 mm'}]}, 'edge selector'),
    ({'timeline': [{'op': 'circular_pattern', 'axis': 'w', 'quantity': 4}]}, 'axis'),
    ({'timeline': [{'op': 'thread', 'target': 'diagonal'}]}, 'target must be one of'),
    ({'timeline': [{'op': 'thread', 'feature': 'missing_feat'}]}, 'feature'),
    ({'timeline': [{'op': 'sweep', 'sketch': 'nope', 'path': 'nope'}]}, 'unknown profile sketch'),
    ({'timeline': [{'op': 'combine'}]}, 'missing tools'),
    ({'timeline': [{'op': 'mirror', 'feature': 'missing_feat'}]}, 'feature'),
    ({'timeline': [{'op': 'coil'}]}, 'missing diameter'),
    ({'timeline': [{'op': 'coil', 'diameter': '20 mm'}]}, 'missing section_size'),
    ({'timeline': [{'op': 'coil', 'diameter': '20 mm', 'section_size': '2 mm', 'axis': 'w'}]}, 'axis must be one of'),
]
for d, msg in bad:
    try:
        validate(d)
    except ValueError as e:
        assert msg in str(e), (msg, str(e))
    else:
        raise AssertionError(f'expected failure: {msg}')

# Test chamfer fallback from parameters
chamfer_fallback_sample = {
    'parameters': {'chamfer_dist': '2 mm'},
    'timeline': [{'op': 'chamfer', 'edges': 'circular'}]
}
validate(chamfer_fallback_sample)
assert chamfer_fallback_sample['timeline'][0]['distance'] == 'chamfer_dist'

# Test coil validation and fallback
spring_sample = {
    "parameters": {
        "spring_dia": "20 mm",
        "wire_dia": "2 mm",
        "spring_pitch": "6 mm",
        "turns": "8"
    },
    "timeline": [
        {
            "op": "coil",
            "id": "spring",
            "diameter": "spring_dia",
            "section_size": "wire_dia",
            "pitch": "spring_pitch",
            "revolutions": "turns",
            "axis": "z",
            "mode": "new_body"
        }
    ]
}
validate(spring_sample)

coil_fallback_sample = {
    "parameters": {
        "coil_dia": "25 mm",
        "wire_thickness": "3 mm"
    },
    "timeline": [
        {"op": "coil"}
    ]
}
validate(coil_fallback_sample)
assert coil_fallback_sample['timeline'][0]['diameter'] == 'coil_dia'
assert coil_fallback_sample['timeline'][0]['section_size'] == 'wire_thickness'

# Test _eval_count for turns/revolutions evaluation
from dsl import _eval_count
assert _eval_count(8) == 8.0
assert _eval_count("8") == 8.0
assert _eval_count("8.5") == 8.5
assert _eval_count("coil_turns", params={"coil_turns": "12"}) == 12.0
assert _eval_count("turns", params={"turns": 7}) == 7.0
assert _eval_count("unknown_param", default=5.0) == 5.0

class MockUnitsManager:
    def evaluateExpression(self, expr, unit):
        if expr == "turns * 2":
            return 16.0
        raise ValueError()

mock_um = MockUnitsManager()
assert _eval_count("turns * 2", um=mock_um) == 16.0

import dsl as dsl_mod
# ----- Provider plugins and the provider-neutral core -----
import io
import os
import re as _re
import threading
import unittest.mock
import urllib.error
import llm
import providers
from providers.base import SettingDef, ModelInfo, GenerateOptions, clean_values

# Discovery: every plugin module is found the same way, ordered by its own `order`, then name
all_provs = providers.get_all_providers()
assert all_provs and all(p.id and p.name for p in all_provs)
assert [(p.order, p.name) for p in all_provs] == sorted((p.order, p.name) for p in all_provs)

# The core knows no provider: no provider id or provider-specific setting key appears in core files
_HERE = pathlib.Path(__file__).parent
_core_py = ('VibeShaper.py', 'llm.py', 'chat.py', 'dsl.py', 'providers/__init__.py', 'providers/base.py',
            'tools/__init__.py', 'tools/base.py', 'features/__init__.py', 'features/base.py',
            'features/entities/__init__.py', 'features/entities/base.py')
_panel = (_HERE / 'palette/app.js').read_text(encoding='utf-8')
_panel = _panel[:_panel.index('// MockBackend:')]  # the browser-preview mock may use sample providers
_core_src = {f: (_HERE / f).read_text(encoding='utf-8') for f in _core_py}
_core_src['palette/app.js'] = _panel
_core_src['palette/index.html'] = (_HERE / 'palette/index.html').read_text(encoding='utf-8')
for core_file, src in _core_src.items():
    for p in all_provs:
        for word in {p.id, p.name, p.short_name}:
            assert not _re.search(rf'\b{_re.escape(word)}\b', src, _re.I), f'{core_file} mentions provider {word!r}'
    for key in ('api_key', 'values.think', "values['think']", 'GEMINI', 'OLLAMA'):
        assert key not in src, f'{core_file} knows the provider setting {key!r}'

# The version isn't written by hand: the build works it out from git tags and writes it into the manifest
assert json.loads((_HERE / 'VibeShaper.manifest').read_text(encoding='utf-8'))['version'] == '0.0.0-dev'

# Settings values are cleaned against the provider's own field list
_schema = [SettingDef('url', 'URL', 'string', 'http://x', required=True, refreshes_models=True),
           SettingDef('key', 'Key', 'secret', ''),
           SettingDef('fast', 'Fast', 'boolean', False),
           SettingDef('temp', 'Temperature', 'number', 0.2, minimum=0, maximum=1),
           SettingDef('size', 'Size', 'select', 'm', options=(('s', 'Small'), ('m', 'Medium')))]
assert clean_values(_schema, {}) == {'url': 'http://x', 'key': '', 'fast': False, 'temp': 0.2, 'size': 'm'}
assert clean_values(_schema, {'url': ' http://h ', 'fast': 1, 'temp': '7', 'size': 'xl', 'junk': 1}) == \
    {'url': 'http://h', 'key': '', 'fast': True, 'temp': 1, 'size': 'm'}
assert clean_values(_schema, {'temp': 'warm', 'size': 's'})['temp'] == 0.2
assert clean_values(_schema, {'size': 's'})['size'] == 's'
_view = SettingDef('size', 'Size', 'select', 'm', options=(('s', 'Small'),)).to_view()
assert _view['options'] == [{'value': 's', 'label': 'Small'}] and 'default' not in _view


class _ReqProvider(providers.BaseProvider):
    id, name = 'req_test', 'Req Test'

    def get_settings_schema(self):
        return _schema


assert _ReqProvider().is_configured(clean_values(_schema, {}))
assert not _ReqProvider().is_configured(clean_values(_schema, {'url': '  '}))
assert _ReqProvider().short_name == 'Req Test'  # defaults to the name
assert ModelInfo('m1').to_view() == {'id': 'm1', 'label': 'm1', 'images': False, 'thinking': False, 'tools': False}

assert llm.clean_json('{"a": 1}') == '{"a": 1}'
assert llm.clean_json('```json\n{"a": 1}\n```') == '{"a": 1}'
assert llm.clean_json('```\n{"a": 1}\n```') == '{"a": 1}'

# llm.generate hands the provider its values, the model and the options; the DSL schema comes from the core
_seen = {}
_DISC = {'parameters': {}, 'timeline': [{'op': 'sketch', 'id': 's', 'plane': 'xy',
                                          'entities': [{'type': 'circle', 'center': [0, 0], 'diameter': 10}]}]}


class _LlmFake(providers.BaseProvider):
    id, name = 'llm_fake', 'LLM Fake'

    def generate(self, model, messages, values, options=None, on_chunk=None, stop_event=None, on_open=None, log=print):
        _seen.update(model=model, values=dict(values), options=options)
        return json.dumps(_DISC)


providers.register_provider(_LlmFake())
assert llm.generate('llm_fake', {'k': 1}, 'm', llm.new_conversation('x'), think=True, log=lambda *_: None) == _DISC
assert _seen['values'] == {'k': 1} and _seen['model'] == 'm'
assert _seen['options'].think is True and _seen['options'].response_schema is dsl_mod.JSON_SCHEMA
try:
    llm.generate('no_such_provider', {}, 'm', llm.new_conversation('x'))
    raise AssertionError('expected unknown provider error')
except ValueError as e:
    assert 'no_such_provider' in str(e)


# --- helpers for plugin tests: fake HTTP
class _Resp:
    def __init__(self, lines=None, body=None):
        self.lines, self.body = lines or [], body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def __iter__(self):
        return iter(self.lines)

    def read(self):
        return json.dumps(self.body).encode('utf-8')

    def close(self):
        pass


def _http_error(url, code, body):
    return urllib.error.HTTPError(url, code, 'err', {}, io.BytesIO(json.dumps(body).encode('utf-8')))


# --- Ollama plugin
ollama = providers.get_provider('ollama')
_tags = {'models': [{'name': 'qwen3:8b'}, {'name': 'coder:7b'}, {'name': 'embed:1'}]}
_caps = {'qwen3:8b': ['completion', 'thinking', 'vision'], 'coder:7b': ['completion', 'tools'], 'embed:1': ['embedding']}


def _ollama_http(req, timeout=None):
    if req.full_url.endswith('/api/tags'):
        return _Resp(body=_tags)
    if req.full_url.endswith('/api/show'):
        return _Resp(body={'capabilities': _caps[json.loads(req.data)['model']]})
    raise AssertionError(req.full_url)


with unittest.mock.patch('urllib.request.urlopen', side_effect=_ollama_http):
    models = ollama.list_models({'url': 'http://mock'})
assert [m.to_view() for m in models] == [
    {'id': 'coder:7b', 'label': 'coder:7b', 'images': False, 'thinking': False, 'tools': True},
    {'id': 'qwen3:8b', 'label': 'qwen3:8b', 'images': True, 'thinking': True, 'tools': False}], models
with unittest.mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('refused')):
    try:
        ollama.list_models({'url': 'http://mock'})
        raise AssertionError('expected a connection error')
    except RuntimeError as e:
        assert 'refused' in str(e)

_stream = [json.dumps(x).encode('utf-8') for x in [
    {'message': {'thinking': 'Thinking 1...'}}, {'message': {'content': '{"parameters": {}, "timeline": []}'}}, {'done': True}]]
_sent = []


def _ollama_chat(req, timeout=None):
    _sent.append(json.loads(req.data))
    return _Resp(lines=_stream)


thoughts = []
with unittest.mock.patch('urllib.request.urlopen', side_effect=_ollama_chat):
    res = ollama.generate('qwen3:8b', [{'role': 'user', 'content': 'hi'}], {'url': 'http://mock'},
                          GenerateOptions(think=True, response_schema={'type': 'object'}),
                          on_chunk=lambda k, c: thoughts.append(c) if k == 'thought' else None, log=lambda *_: None)
assert res == '{"parameters": {}, "timeline": []}' and thoughts == ['Thinking 1...']
assert _sent[-1]['think'] is True and _sent[-1]['format'] == {'type': 'object'}
with unittest.mock.patch('urllib.request.urlopen', side_effect=_ollama_chat):
    ollama.generate('m', [], {'url': 'http://mock'}, None, log=lambda *_: None)
assert _sent[-1]['think'] is False and 'format' not in _sent[-1]

stop_ev = threading.Event()
stop_ev.set()
try:
    with unittest.mock.patch('urllib.request.urlopen', side_effect=_ollama_chat):
        ollama.generate('m', [], {'url': 'http://mock'}, GenerateOptions(), stop_event=stop_ev, log=lambda *_: None)
    raise AssertionError('expected InterruptedError')
except InterruptedError:
    pass

# --- Gemini plugin
gemini = providers.get_provider('gemini')
_env_keys = {k: os.environ.pop(k) for k in ('GEMINI_API_KEY', 'GOOGLE_API_KEY') if k in os.environ}
assert not gemini.is_configured({'api_key': ''})
os.environ['GEMINI_API_KEY'] = 'from-env'
assert gemini.is_configured({'api_key': ''})
del os.environ['GEMINI_API_KEY']
try:
    gemini.list_models({'api_key': ''})
    raise AssertionError('expected a missing key error')
except ValueError:
    pass

_gm = {'models': [
    {'name': 'models/gemini-x', 'displayName': 'Gemini X', 'supportedGenerationMethods': ['generateContent'], 'thinking': True},
    {'name': 'models/text-embedding-4', 'supportedGenerationMethods': ['embedContent']},
    {'name': 'models/gemini-old', 'displayName': 'Gemini Old', 'supportedGenerationMethods': ['generateContent']}]}
with unittest.mock.patch('urllib.request.urlopen', return_value=_Resp(body=_gm)):
    gm = [m.to_view() for m in gemini.list_models({'api_key': 'k'})]
assert gm == [{'id': 'gemini-old', 'label': 'Gemini Old', 'images': True, 'thinking': False, 'tools': True},
              {'id': 'gemini-x', 'label': 'Gemini X', 'images': True, 'thinking': True, 'tools': True}], gm
with unittest.mock.patch('urllib.request.urlopen',
                         side_effect=_http_error('u', 400, {'error': {'message': 'API key not valid'}})):
    try:
        gemini.list_models({'api_key': 'bad'})
        raise AssertionError('expected an API error')
    except RuntimeError as e:
        assert 'API key not valid' in str(e)

_gsent = []
_sse = [b'data: ' + json.dumps({'candidates': [{'content': {'parts': [
    {'thought': True, 'text': 'hmm'}, {'text': '{"parameters": {}, "timeline": []}'}]}}]}).encode('utf-8')]


def _gemini_chat(req, timeout=None):
    _gsent.append(json.loads(req.data))
    return _Resp(lines=_sse)


thoughts = []
with unittest.mock.patch('urllib.request.urlopen', side_effect=_gemini_chat):
    res = gemini.generate('gemini-x', [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'hi'}],
                          {'api_key': 'k'}, GenerateOptions(think=True),
                          on_chunk=lambda k, c: thoughts.append(c) if k == 'thought' else None, log=lambda *_: None)
assert res == '{"parameters": {}, "timeline": []}' and thoughts == ['hmm']
assert _gsent[-1]['generationConfig']['thinkingConfig'] == {'includeThoughts': True}
assert _gsent[-1]['systemInstruction'] == {'parts': [{'text': 'sys'}]}
with unittest.mock.patch('urllib.request.urlopen', side_effect=_gemini_chat):
    gemini.generate('gemini-x', [], {'api_key': 'k'}, GenerateOptions(think=False), log=lambda *_: None)
assert _gsent[-1]['generationConfig']['thinkingConfig'] == {'thinkingBudget': 0}
os.environ.update(_env_keys)

# ----- Tool plugins: discovered like providers; the core knows none of them -----
import tools as toolbox
from tools import design as dt
from types import SimpleNamespace as _NS

_kits = toolbox.get_all_toolkits()
assert _kits and all(k.id for k in _kits)
assert [(k.order, k.id) for k in _kits] == sorted((k.order, k.id) for k in _kits)
assert not (_HERE / 'design_tools.py').exists()
for core_file, src in _core_src.items():
    for k in _kits:
        for word in [k.id] + [t['name'] for t in k.tools()]:
            for quoted in (f"'{word}'", f'"{word}"'):
                assert quoted not in src, f'{core_file} mentions tool {quoted}'
    assert 'design_tools' not in src and 'from .tools.' not in src, f'{core_file} imports a tool plugin'


class _ShotKit(toolbox.BaseToolkit):  # a made-up plugin: needs images, clashes on one name
    id, order, needs, prompt = 'zz_shots', 99, ('images',), 'SHOTS: take pictures.'

    def tools(self):
        return [{'name': 'snap', 'description': 'A picture.', 'parameters': {'type': 'object', 'properties': {}}},
                {'name': 'get_overview', 'description': 'clash', 'parameters': {'type': 'object', 'properties': {}}}]

    def run(self, name, args, ctx):
        if args.get('boom'):
            raise RuntimeError('lens cap')
        if args.get('bad'):
            raise toolbox.ToolError('bad angle')
        ctx.state['shots'] = ctx.state.get('shots', 0) + 1
        return {'shots': ctx.state['shots']}


toolbox.register_toolkit(_ShotKit())
assert 'zz_shots' not in [k.id for k in toolbox.usable(set())]
assert 'zz_shots' in [k.id for k in toolbox.usable({'images', 'tools'})]
_all_names = [t['name'] for t in toolbox.specs(toolbox.get_all_toolkits())]
assert _all_names.count('get_overview') == 1 and 'snap' in _all_names  # a taken name is left out
_shots = toolbox.get_toolkit('zz_shots')
assert toolbox.owner('get_overview', toolbox.get_all_toolkits()).id == 'design'
assert toolbox.owner('snap', toolbox.get_all_toolkits()) is _shots and toolbox.owner('nope', _kits) is None
assert 'SHOTS' in toolbox.prompt(toolbox.get_all_toolkits()) and 'get_overview' in toolbox.prompt(_kits)
_st = {}
assert toolbox.run(_shots, 'snap', {}, toolbox.ToolContext(None, None, _st)) == {'shots': 1} and _st == {'shots': 1}
assert toolbox.run(_shots, 'snap', {'bad': 1}, toolbox.ToolContext(None, None)) == {'error': 'bad angle'}
assert 'lens cap' in toolbox.run(_shots, 'snap', {'boom': 1}, toolbox.ToolContext(None, None))['error']
assert toolbox.label(_shots, 'snap', {}, {'error': 'x'}) == 'Called snap (failed: x)'
assert toolbox.summary(_shots, toolbox.ToolContext(None, None)) == ''
toolbox.unregister_toolkit('zz_shots')

# ----- Design tools: read-only views of the user's design, on a fake Fusion design -----


class _Coll(list):
    @property
    def count(self):
        return len(self)

    def item(self, i):
        return self[i]


class _P:  # Point3D / Vector3D in cm
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z

    def asArray(self):
        return [self.x, self.y, self.z]


class _Ent:
    def __init__(self, reg, token, objectType, **kw):
        self.entityToken, self.objectType = token, objectType
        self.__dict__.update(kw)
        reg[token] = self


class _FakeFusion:
    """Root 'Assy' with body Base (40x20x10 mm, a 6 mm hole) and Sketch1; occurrence Bracket:1 at x=50 mm
    holding body Plate; timeline Sketch1, Extrude1, Bracket:1, Extrude2 (failing)."""

    def __init__(self):
        reg = self.reg = {}
        self.timeline_items = _Coll()

        def face_plane(area, normal, point):
            return _NS(geometry=_NS(surfaceType=0), area=area, pointOnFace=_P(*point),
                       evaluator=_NS(getNormalAtPoint=lambda p, n=normal: (True, _P(*n))))

        hole = _NS(geometry=_NS(surfaceType=1, radius=0.3, axis=_P(0, 0, 1), origin=_P(1, 1, 0)),
                   area=1.9, pointOnFace=_P(1.3, 1, 0.5),
                   evaluator=_NS(getNormalAtPoint=lambda p: (True, _P(-1, 0, 0))))  # faces the axis: a hole
        base = _Ent(reg, 'tok-base', 'adsk::fusion::BRepBody', name='Base', isSolid=True, isVisible=True,
                    boundingBox=_NS(minPoint=_P(0, 0, 0), maxPoint=_P(4, 2, 1)), volume=7.9, area=30.0,
                    material=_NS(name='Steel'), edges=_Coll([1] * 15),
                    faces=_Coll([face_plane(8, (0, 0, 1), (2, 1, 1)), face_plane(8, (0, 0, -1), (2, 1, 0)),
                                 face_plane(2, (1, 0, 0), (4, 1, 0.5)), hole]))
        line = _NS(startSketchPoint=_NS(geometry=_P(0, 0, 0)), endSketchPoint=_NS(geometry=_P(4, 0, 0)), isConstruction=False)
        circ = _NS(centerSketchPoint=_NS(geometry=_P(1, 1, 0)), radius=0.3, isConstruction=False)
        curves = _Coll([line, circ])
        curves.sketchLines, curves.sketchCircles, curves.sketchArcs = _Coll([line]), _Coll([circ]), _Coll()
        d1 = _NS(name='d1', expression='6 mm', role='Diameter')
        sketch = _Ent(reg, 'tok-sk1', 'adsk::fusion::Sketch', name='Sketch1', isVisible=True,
                      referencePlane=_NS(objectType='adsk::fusion::ConstructionPlane', name='XY'),
                      profiles=_Coll([1, 2]), sketchCurves=curves, sketchDimensions=_Coll([_NS(parameter=d1)]),
                      geometricConstraints=_Coll([1, 2, 3]), isFullyConstrained=False)
        root = _Ent(reg, 'tok-root', 'adsk::fusion::Component', name='Assy', bRepBodies=_Coll([base]),
                    sketches=_Coll([sketch]), constructionPlanes=_Coll([_NS(name='Mid plane')]))
        sketch.parentComponent = root
        plate_native = _NS(name='Plate', entityToken='tok-plate-native')
        bracket = _Ent(reg, 'tok-bracket-comp', 'adsk::fusion::Component', name='Bracket',
                       bRepBodies=_Coll([plate_native]), sketches=_Coll(), constructionPlanes=_Coll())
        occ = _Ent(reg, 'tok-occ1', 'adsk::fusion::Occurrence', name='Bracket:1', component=bracket,
                   isLightBulbOn=True, isVisible=True, childOccurrences=_Coll(),
                   transform2=_NS(translation=_P(5, 0, 0)))
        plate = _Ent(reg, 'tok-plate@occ1', 'adsk::fusion::BRepBody', name='Plate', isSolid=True, isVisible=True,
                     boundingBox=_NS(minPoint=_P(5, 0, 0), maxPoint=_P(7, 2, 0.5)), volume=2.0, material=None,
                     faces=_Coll(), edges=_Coll())
        plate_native.createForAssemblyContext = lambda o: plate
        root.occurrences = root.allOccurrences = _Coll([occ])
        profile = _NS(parentSketch=sketch)
        extrude1 = _Ent(reg, 'tok-ext1', 'adsk::fusion::ExtrudeFeature', name='Extrude1', parentComponent=root,
                        operation=3, bodies=_Coll([base]), profile=profile)
        extrude2 = _Ent(reg, 'tok-ext2', 'adsk::fusion::ExtrudeFeature', name='Extrude2', parentComponent=bracket,
                        operation=0, bodies=_Coll(), profile=None)
        for i, (e, health, msg) in enumerate([(sketch, 0, ''), (extrude1, 0, ''), (occ, 0, ''),
                                              (extrude2, 2, 'Profile is no longer valid')]):
            item = _NS(index=i, name=e.name, entity=e, isGroup=False, healthState=health, errorOrWarningMessage=msg,
                       isSuppressed=False, isRolledBack=False, parentGroup=None)
            e.timelineObject = item
            self.timeline_items.append(item)
        width = _NS(name='width', expression='40 mm', unit='mm', comment='overall', createdBy=None)
        d2 = _NS(name='d2', expression='10 mm', unit='mm', role='AlongDistance', createdBy=extrude1)
        d1.createdBy = sketch
        self.design = _NS(rootComponent=root, timeline=self.timeline_items, userParameters=_Coll([width]),
                          allParameters=_Coll([width, d1, d2]), designIntent=1,
                          unitsManager=_NS(defaultLengthUnits='mm'), parentDocument=_NS(name='Fixture v3'),
                          findEntityByToken=lambda tok: _Coll([reg[tok]] if tok in reg else []))
        self.base, self.plate, self.occ, self.sketch = base, plate, occ, sketch


FF = _FakeFusion()
KIT = toolbox.get_toolkit('design')
_app_fake = _NS(userInterface=_NS(activeSelections=_Coll([_NS(entity=FF.base)])),
                measureManager=_NS(measureMinimumDistance=lambda a, b: _NS(value=1.0)))
STATE = {}
tctx = toolbox.ToolContext(_app_fake, FF.design, STATE)
ctx = dt.Context.from_tool_context(tctx)
refs = ctx.refs
R = lambda name, **a: toolbox.run(KIT, name, a, tctx)

ov = R('get_overview')
assert ov['document'] == 'Fixture v3' and ov['type'] == 'Assembly' and ov['units'] == 'mm'
assert ov['counts'] == {'occurrences': 1, 'bodies': 2, 'sketches': 1, 'timeline': 4, 'user_parameters': 1}, ov['counts']
assert ov['selection'][0]['kind'] == 'body' and ov['selection'][0]['name'] == 'Base'
base_id = ov['selection'][0]['id']

comps = R('list_components')
assert comps['total'] == 1
occ_id = comps['items'][0]['id']
assert occ_id.startswith('o') and comps['items'][0]['position'] == [50.0, 0.0, 0.0]
assert comps['items'][0]['component'] == 'Bracket'

bodies = R('list_bodies')
assert bodies['items'][0]['id'] == base_id  # the same thing keeps its id
assert bodies['items'][0]['bbox']['size'] == [40.0, 20.0, 10.0] and bodies['items'][0]['volume'] == 7900.0
plate_list = R('list_bodies', component=occ_id)  # bodies of an occurrence: world coordinates
assert plate_list['items'][0]['name'] == 'Plate' and plate_list['items'][0]['bbox']['min'] == [50.0, 0.0, 0.0]

body = R('get_body', id=base_id)
assert body['faces'] == {'total': 4, 'by_type': {'plane': 3, 'cylinder': 1}}
assert body['largest_flat_faces'][0]['normal'] == [0.0, 0.0, 1.0] and body['largest_flat_faces'][0]['area'] == 800.0
assert body['round_features'] == [{'kind': 'hole', 'diameter': 6.0, 'axis': [0.0, 0.0, 1.0],
                                   'axis_point': [10.0, 10.0, 0.0], 'area': 190.0}], body['round_features']

comp = R('get_component', id='root')
assert comp['name'] == 'Assy' and comp['timeline_features'] == 2 and comp['construction_planes'] == ['Mid plane']
assert R('get_component', id=occ_id)['timeline_features'] == 1

sk_id = R('list_sketches')['items'][0]['id']
sk = R('get_sketch', id=sk_id)
assert sk['on'] == 'XY' and sk['profiles'] == 2 and sk['constraints'] == 3 and sk['fully_constrained'] is False
assert sk['curves']['items'] == [{'type': 'line', 'start': [0.0, 0.0, 0.0], 'end': [40.0, 0.0, 0.0]},
                                 {'type': 'circle', 'center': [10.0, 10.0, 0.0], 'diameter': 6.0}]
assert sk['dimensions'] == [{'name': 'd1', 'expression': '6 mm'}]

tl = R('get_timeline')
assert [i['type'] for i in tl['items']] == ['Sketch', 'Extrude', 'Occurrence', 'Extrude'], tl
assert tl['items'][3]['health'] == 'error' and tl['items'][3]['message'] == 'Profile is no longer valid'
assert tl['items'][0]['id'] == sk_id and tl['items'][2]['id'] == occ_id
assert [i['name'] for i in R('get_timeline', component=occ_id)['items']] == ['Extrude2']
page = R('get_timeline', limit=2)
assert len(page['items']) == 2 and page['more'] == 2 and page['next_offset'] == 2
assert R('get_timeline', offset=2, limit=2)['items'][0]['name'] == 'Bracket:1'

feat = R('get_feature', id=tl['items'][1]['id'])
assert feat['type'] == 'Extrude' and feat['operation'] == 'new body' and feat['component'] == 'Assy'
assert feat['bodies'] == [{'id': base_id, 'name': 'Base'}] and feat['sketch'] == {'id': sk_id, 'name': 'Sketch1'}
assert feat['dimensions'] == [{'name': 'd2', 'expression': '10 mm', 'role': 'AlongDistance'}]

assert R('list_parameters')['items'] == [{'name': 'width', 'expression': '40 mm', 'unit': 'mm', 'comment': 'overall'}]
assert [p['name'] for p in R('list_parameters', kind='model')['items']] == ['d1', 'd2']

assert [h['name'] for h in R('find', text='PLATE')['items']] == ['Plate']
assert {h['kind'] for h in R('find', text='e')['items']} >= {'body', 'sketch', 'feature'}
assert R('find', text='bracket', kind='component')['items'][0]['id'] == occ_id
assert R('get_selection')['items'][0]['id'] == base_id
assert R('measure', a=base_id, b=occ_id) == {'a': base_id, 'b': occ_id, 'distance': 10.0}

# Problems come back as messages for the model, never as exceptions
assert 'Unknown id' in R('get_body', id='b99')['error']
assert 'is a sketch' in R('get_body', id=sk_id)['error']
assert 'Unknown tool' in R('delete_everything')['error']
assert 'kind must be' in R('list_parameters', kind='nope')['error']
FF.design.findEntityByToken = lambda tok: _Coll()
assert 'no longer exists' in R('get_body', id=base_id)['error']
FF.design.findEntityByToken = lambda tok: _Coll([FF.reg[tok]] if tok in FF.reg else [])
assert 'failed' in toolbox.run(KIT, 'get_body', {'id': base_id}, toolbox.ToolContext(_app_fake, _NS(findEntityByToken=None), STATE))['error']

# Ids live in the toolkit's own saved state, and survive a save and load
assert STATE['refs']['ids'][base_id] == 'tok-base'
refs2 = dt.Refs(json.loads(json.dumps(STATE))['refs'])
assert refs2.token(base_id) == 'tok-base' and refs2.id_for('body', 'tok-base') == base_id
assert refs2.id_for('body', 'tok-new') not in refs.ids

# Every tool has a spec the model sees, and a label for the panel
assert set(dt.TOOL_NAMES) == set(dt._TOOLS)
for spec in dt.TOOL_SPECS:
    assert spec['parameters']['type'] == 'object' and spec['description']
assert [t['name'] for t in KIT.tools()] == dt.TOOL_NAMES
assert toolbox.label(KIT, 'get_body', {'id': base_id}, body) == f'Inspected body {base_id} · Base'
assert dt.label('get_timeline', {}, tl) == 'Read the timeline · 4'
assert dt.label('get_body', {'id': 'b99'}, {'error': 'Unknown id'}).endswith('(failed: Unknown id)')

text = toolbox.summary(KIT, tctx)
assert 'Fixture v3' in text and 'Bracket:1' in text and 'width = 40 mm' in text and 'Extrude2 (Extrude)' in text, text
assert 'Selected: body Base' in text
_empty_root = _NS(bRepBodies=_Coll(), allOccurrences=_Coll())
assert toolbox.summary(KIT, toolbox.ToolContext(_app_fake, _NS(rootComponent=_empty_root, timeline=_Coll()))) == ''

# ----- The tool loop in llm.generate -----
_tool_runs = []


class _ToolUser(providers.BaseProvider):
    id, name = 'tool_user', 'Tool User'
    script = []
    seen = []

    def generate(self, model, messages, values, options=None, on_chunk=None, stop_event=None, on_open=None, log=print):
        self.seen.append(([dict(m) for m in messages], options))
        step = self.script.pop(0)
        return step if isinstance(step, providers.Reply) else json.dumps(step)


providers.register_provider(_ToolUser())
TU = _ToolUser
_call = lambda i, name, **a: providers.ToolCall(i, name, a, {'sig': 'x' + i})
TU.script = [providers.Reply('Let me look.', [_call('c1', 'get_overview'), _call('c2', 'list_bodies', component='root')]),
             providers.Reply('', [_call('c3', 'get_body', id='b1')]),
             _DISC]
TU.seen = []
msgs = llm.new_conversation('a lid for the base')
out = llm.generate('tool_user', {}, 'm', msgs, tools=dt.TOOL_SPECS, log=lambda *_: None,
                   run_tool=lambda n, a: _tool_runs.append((n, a)) or {'ok': n})
assert out == _DISC
assert _tool_runs == [('get_overview', {}), ('list_bodies', {'component': 'root'}), ('get_body', {'id': 'b1'})]
assert [m['role'] for m in msgs] == ['system', 'user', 'assistant', 'tool', 'tool', 'assistant', 'tool', 'assistant']
assert msgs[2]['tool_calls'][0] == {'id': 'c1', 'name': 'get_overview', 'arguments': {}, 'extra': {'sig': 'xc1'}}
assert msgs[3] == {'role': 'tool', 'tool_call_id': 'c1', 'name': 'get_overview', 'content': '{"ok": "get_overview"}'}
assert [t.name for t in TU.seen[0][1].tools] == dt.TOOL_NAMES

# A model that keeps calling tools is cut off: after the limit it must answer
TU.script = [providers.Reply('', [_call(f'k{i}', 'get_overview')]) for i in range(3)] + [_DISC]
TU.seen = []
_tool_runs.clear()
assert llm.generate('tool_user', {}, 'm', llm.new_conversation('x'), tools=dt.TOOL_SPECS, max_tool_calls=2,
                    run_tool=lambda n, a: _tool_runs.append(n) or {}, log=lambda *_: None) == _DISC
assert len(_tool_runs) == 2 and TU.seen[-1][1].tools is None
# Without run_tool, no tools are offered
TU.script, TU.seen = [_DISC], []
llm.generate('tool_user', {}, 'm', llm.new_conversation('x'), tools=dt.TOOL_SPECS, log=lambda *_: None)
assert TU.seen[0][1].tools is None
# Prose around the JSON (models often explain after using tools) is tolerated
assert json.loads(llm.clean_json('Here it is:\n{"a": {"b": 1}}\nDone.')) == {'a': {'b': 1}}
assert 'get_overview' not in llm.system_prompt(tools=True)  # the core prompt names no tool
assert 'TOOLS' in llm.system_prompt(tools=True) and 'TOOLS' not in llm.system_prompt(notes='x')
assert llm.system_prompt(tools=True, notes=dt.PROMPT).endswith(dt.PROMPT)
assert llm.with_design_context('hi', '') == 'hi' and llm.with_design_context('hi', 'S').endswith('S')

# ----- Plugins: tools in each API's own format -----
_tools = [providers.ToolDef(s['name'], s['description'], s['parameters']) for s in dt.TOOL_SPECS[:2]]
_hist = [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'hi'},
         {'role': 'assistant', 'content': 'Looking', 'tool_calls': [
             {'id': 'c1', 'name': 'get_overview', 'arguments': {}, 'extra': {'thoughtSignature': 'SIG'}},
             {'id': 'c2', 'name': 'list_components', 'arguments': {'depth': 2}, 'extra': {}}]},
         {'role': 'tool', 'tool_call_id': 'c1', 'name': 'get_overview', 'content': '{"document": "D"}'},
         {'role': 'tool', 'tool_call_id': 'c2', 'name': 'list_components', 'content': '{"total": 0}'}]

_sent.clear()
_stream_tc = [json.dumps(x).encode('utf-8') for x in [
    {'message': {'content': '', 'tool_calls': [{'function': {'name': 'get_body', 'arguments': {'id': 'b1'}}}]}},
    {'done': True}]]
with unittest.mock.patch('urllib.request.urlopen', side_effect=lambda req, timeout=None: _sent.append(json.loads(req.data)) or _Resp(lines=_stream_tc)):
    r = ollama.generate('m', _hist, {'url': 'http://mock'}, GenerateOptions(response_schema={'x': 1}, tools=_tools),
                        log=lambda *_: None)
assert isinstance(r, providers.Reply) and r.tool_calls[0].name == 'get_body' and r.tool_calls[0].arguments == {'id': 'b1'}
body = _sent[-1]
assert 'format' not in body and body['tools'][0]['function']['name'] == 'get_overview'
assert body['messages'][2] == {'role': 'assistant', 'content': 'Looking', 'tool_calls': [
    {'function': {'name': 'get_overview', 'arguments': {}}}, {'function': {'name': 'list_components', 'arguments': {'depth': 2}}}]}
assert body['messages'][3] == {'role': 'tool', 'content': '{"document": "D"}', 'tool_name': 'get_overview'}

_gsent.clear()
_sse_tc = [b'data: ' + json.dumps({'candidates': [{'content': {'parts': [
    {'functionCall': {'name': 'get_body', 'args': {'id': 'b1'}}, 'thoughtSignature': 'SIG2'}]}}]}).encode('utf-8')]
with unittest.mock.patch('urllib.request.urlopen', side_effect=lambda req, timeout=None: _gsent.append(json.loads(req.data)) or _Resp(lines=_sse_tc)):
    r = gemini.generate('gemini-x', _hist, {'api_key': 'k'}, GenerateOptions(tools=_tools), log=lambda *_: None)
assert isinstance(r, providers.Reply) and r.tool_calls[0].arguments == {'id': 'b1'}
assert r.tool_calls[0].extra == {'thoughtSignature': 'SIG2'}  # sent back with the call next time
g = _gsent[-1]
assert 'responseMimeType' not in g['generationConfig']
decls = g['tools'][0]['functionDeclarations']
assert decls[0] == {'name': 'get_overview', 'description': dt.TOOL_SPECS[0]['description']}  # no empty parameters
assert decls[1]['parameters']['properties']['depth']['type'] == 'integer'
assert g['systemInstruction'] == {'parts': [{'text': 'sys'}]}
assert g['contents'][1] == {'role': 'model', 'parts': [
    {'text': 'Looking'}, {'functionCall': {'name': 'get_overview', 'args': {}}, 'thoughtSignature': 'SIG'},
    {'functionCall': {'name': 'list_components', 'args': {'depth': 2}}}]}
assert g['contents'][2] == {'role': 'user', 'parts': [  # both results of the round in one turn
    {'functionResponse': {'name': 'get_overview', 'response': {'result': {'document': 'D'}}}},
    {'functionResponse': {'name': 'list_components', 'response': {'result': {'total': 0}}}}]}

# Test log_transcript
test_log_txt = '{"parameters": {}, "timeline": []}'
llm.log_transcript('TestProvider', 'test-model', 'test prompt', test_log_txt, 'some thoughts', error='test error', attempt=1)
assert llm.LOG_FILE.exists()
assert 'TestProvider' in llm.LOG_FILE.read_text(encoding='utf-8')
assert llm.LAST_RESPONSE_FILE.read_text(encoding='utf-8') == test_log_txt

# Test parameter disambiguation
from dsl import disambiguate_parameters

test_d = {
    'parameters': {'width': '50 mm', 'height': 'width * 2', 'wall': '3 mm'},
    'timeline': [
        {'op': 'sketch', 'plane': 'xy', 'entities': [{'type': 'center_rectangle', 'center': [0, 0], 'width': 'width', 'height': 'height'}]},
        {'op': 'extrude', 'distance': 'height - wall'}
    ]
}

# No collision
assert disambiguate_parameters(test_d, {'foo', 'bar'}) == test_d

# Collision on width
renamed = disambiguate_parameters(test_d, {'width', 'other'})
assert 'part2_width' in renamed['parameters']
assert renamed['parameters']['part2_height'] == 'part2_width * 2'
assert renamed['timeline'][0]['entities'][0]['width'] == 'part2_width'
assert renamed['timeline'][1]['distance'] == 'part2_height - part2_wall'

# Collision on part2 as well -> part3
renamed3 = disambiguate_parameters(test_d, {'width', 'part2_width'})
assert 'part3_width' in renamed3['parameters']
assert renamed3['parameters']['part3_height'] == 'part3_width * 2'

# Test _select_edges Line3D direction logic (Fusion 360 API compatibility)
class MockVector3D:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
    def normalize(self):
        mag = (self.x**2 + self.y**2 + self.z**2)**0.5 or 1.0
        self.x, self.y, self.z = self.x / mag, self.y / mag, self.z / mag

class MockPoint3D:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
    @staticmethod
    def create(x, y, z):
        return MockPoint3D(x, y, z)
    def vectorTo(self, other):
        return MockVector3D(other.x - self.x, other.y - self.y, other.z - self.z)

class MockInfiniteLine3D:
    def __init__(self, dir_vec):
        self.direction = dir_vec

class MockLine3D:
    # No .direction attribute, matching Fusion 360 Line3D!
    def __init__(self, start, end):
        self.startPoint = start
        self.endPoint = end
        self.curveType = 1

    def asInfiniteLine(self):
        v = self.startPoint.vectorTo(self.endPoint)
        v.normalize()
        return MockInfiniteLine3D(v)

class MockEdge:
    def __init__(self, geo):
        self.geometry = geo
        self.pointOnEdge = geo.startPoint

class MockEdgeCollection:
    def __init__(self, edges):
        self.edges = edges
        self.count = len(edges)
    def item(self, k):
        return self.edges[k]

class MockBody:
    def __init__(self, edges):
        self.edges = MockEdgeCollection(edges)
        class BB:
            class Pt:
                def __init__(self, z): self.z = z
            maxPoint = Pt(10)
            minPoint = Pt(0)
        self.boundingBox = BB()

import sys, types
mock_adsk = types.ModuleType('adsk')
mock_core = types.ModuleType('adsk.core')
class Curve3DTypes:
    Line3DCurveType = 1
    Circle3DCurveType = 2
mock_core.Curve3DTypes = Curve3DTypes
mock_adsk.core = mock_core
sys.modules['adsk'] = mock_adsk
sys.modules['adsk.core'] = mock_core

from features._helpers import select_edges as _select_edges
vert_line = MockLine3D(MockPoint3D(0, 0, 0), MockPoint3D(0, 0, 10))
horiz_line = MockLine3D(MockPoint3D(0, 0, 0), MockPoint3D(10, 0, 0))
test_body = MockBody([MockEdge(vert_line), MockEdge(horiz_line)])
matched = _select_edges(test_body, 'vertical')
assert len(matched) == 1
assert matched[0].geometry is vert_line

# Test shell input collection when remove_faces is 'none' (hollow body without removed faces)
class MockObjectCollection:
    def __init__(self):
        self.items = []
    def add(self, item):
        self.items.append(item)
    @property
    def count(self):
        return len(self.items)

class MockShellFeatures:
    def createInput(self, input_entities, is_tangent_chain):
        if not isinstance(input_entities, MockObjectCollection):
            raise TypeError("Wrong number or type of arguments for overloaded function 'ShellFeatures_createInput'")
        return "mock_shell_input"

mock_body_obj = "mock_body_instance"
faces_empty = []
shell_col = MockObjectCollection()
for f in faces_empty:
    shell_col.add(f)
if shell_col.count == 0:
    shell_col.add(mock_body_obj)

assert shell_col.count == 1
assert shell_col.items[0] == mock_body_obj
mock_shells = MockShellFeatures()
inp = mock_shells.createInput(shell_col, False)
assert inp == "mock_shell_input"

# Test sketch constraint logic
from features.entities import draw as _draw

class MockSKPt:
    def __init__(self, x=0, y=0):
        self.geometry = MockPoint3D(x, y, 0)
        self.isFullyConstrained = False
        self.isFixed = False

class MockSKLine:
    def __init__(self, p1, p2):
        self.startSketchPoint = p1 if isinstance(p1, MockSKPt) else MockSKPt(p1.x, p1.y)
        self.endSketchPoint = p2 if isinstance(p2, MockSKPt) else MockSKPt(p2.x, p2.y)
        self.isFullyConstrained = False
        self.isFixed = False
        self.isConstruction = False

class MockSKCircle:
    def __init__(self, center, r):
        self.centerSketchPoint = MockSKPt(center.x, center.y)
        self.radius = r
        self.isFullyConstrained = False
        self.isFixed = False

class MockParam:
    def __init__(self):
        self.expression = ''

class MockDim:
    def __init__(self):
        self.parameter = MockParam()

class MockSKDims:
    def __init__(self):
        self.dims = []
    def addDiameterDimension(self, circle, pt):
        d = MockDim()
        self.dims.append(('diameter', d))
        return d
    def addDistanceDimension(self, p1, p2, orientation, pt):
        d = MockDim()
        self.dims.append(('distance', d, orientation))
        return d

class MockGeoConstraints:
    def __init__(self):
        self.constraints = []
    def addCoincident(self, p1, p2):
        self.constraints.append(('coincident', p1, p2))
    def addHorizontal(self, line):
        self.constraints.append(('horizontal', line))
    def addVertical(self, line):
        self.constraints.append(('vertical', line))
    def addHorizontalPoints(self, p1, p2):
        self.constraints.append(('horizontal_points', p1, p2))
    def addVerticalPoints(self, p1, p2):
        self.constraints.append(('vertical_points', p1, p2))
    def addMidPoint(self, p, line):
        self.constraints.append(('midpoint', p, line))
    def addPerpendicular(self, l1, l2):
        self.constraints.append(('perpendicular', l1, l2))
    def addParallel(self, l1, l2):
        self.constraints.append(('parallel', l1, l2))
    def addConcentric(self, c1, c2):
        self.constraints.append(('concentric', c1, c2))
    def addTangent(self, e1, e2):
        self.constraints.append(('tangent', e1, e2))
    def addEqual(self, e1, e2):
        self.constraints.append(('equal', e1, e2))
    def addSymmetry(self, e1, e2, sym):
        self.constraints.append(('symmetry', e1, e2, sym))

class MockSKLinesList:
    def __init__(self, lines):
        self._lines = lines
        self.count = len(lines)
    def item(self, k):
        return self._lines[k]

class MockSKCurves:
    def __init__(self):
        self.lines_list = []
        self.circles_list = []
        class LinesHelper:
            def __init__(self, outer): self.outer = outer
            def addByTwoPoints(self, p1, p2):
                l = MockSKLine(p1, p2)
                self.outer.lines_list.append(l)
                return l
            def addCenterPointRectangle(self, c, corner):
                dx = abs(corner.x - c.x)
                dy = abs(corner.y - c.y)
                p1 = MockSKPt(c.x - dx, c.y - dy)
                p2 = MockSKPt(c.x + dx, c.y - dy)
                p3 = MockSKPt(c.x + dx, c.y + dy)
                p4 = MockSKPt(c.x - dx, c.y + dy)
                rect_lines = [
                    MockSKLine(p1, p2),
                    MockSKLine(p2, p3),
                    MockSKLine(p3, p4),
                    MockSKLine(p4, p1)
                ]
                self.outer.lines_list.extend(rect_lines)
                return MockSKLinesList(rect_lines)
        class CirclesHelper:
            def __init__(self, outer): self.outer = outer
            def addByCenterRadius(self, c, r):
                circ = MockSKCircle(c, r)
                self.outer.circles_list.append(circ)
                return circ
        self.sketchLines = LinesHelper(self)
        self.sketchCircles = CirclesHelper(self)

    @property
    def count(self):
        return len(self.lines_list) + len(self.circles_list)
    def item(self, k):
        all_curves = self.lines_list + self.circles_list
        return all_curves[k]

class MockSKPoints:
    def __init__(self):
        self._pts = []
    def add(self, pt):
        p = MockSKPt(pt.x, pt.y)
        self._pts.append(p)
        return p
    @property
    def count(self):
        return len(self._pts)
    def item(self, k):
        return self._pts[k]

class MockSketchObj:
    def __init__(self):
        self.originPoint = MockSKPt(0, 0)
        self.originPoint.isFullyConstrained = True
        self.sketchCurves = MockSKCurves()
        self.sketchDimensions = MockSKDims()
        self.geometricConstraints = MockGeoConstraints()
        self.sketchPoints = MockSKPoints()
        self.isFullyConstrained = False

# Setup adsk.fusion DimensionOrientations
mock_fusion = types.ModuleType('adsk.fusion')
class MockDimOrientations:
    HorizontalDimensionOrientation = 0
    VerticalDimensionOrientation = 1
    AlignedDimensionOrientation = 2
mock_fusion.DimensionOrientations = MockDimOrientations
mock_adsk.fusion = mock_fusion
sys.modules['adsk.fusion'] = mock_fusion
mock_core.Point3D = MockPoint3D

def dummy_cm(v):
    if isinstance(v, (int, float)): return float(v) / 10.0
    import re
    m = re.match(r'([\d.]+)', str(v))
    return float(m.group(1)) / 10.0 if m else 1.0

def dummy_ex(v):
    return str(v)

def dummy_pt(a, b):
    return MockPoint3D(a, b, 0)

# Test 1: Polyline sweep path with [0,0] corner
sk1 = MockSketchObj()
sweep_poly = {
    "type": "polyline",
    "points": [[0, "80 mm"], [0, 0], ["80 mm", 0]],
    "closed": False
}
_draw(sk1, sweep_poly, dummy_ex, dummy_cm, dummy_pt)
# Check coincident to origin
coincident_types = [c[0] for c in sk1.geometricConstraints.constraints if c[0] == 'coincident']
assert 'coincident' in coincident_types
# Check horizontal and vertical constraints applied to segments
h_or_v = [c[0] for c in sk1.geometricConstraints.constraints if c[0] in ('horizontal', 'vertical')]
assert 'vertical' in h_or_v
assert 'horizontal' in h_or_v
# Check dimensions applied
assert len(sk1.sketchDimensions.dims) >= 2

# Test 2: Center rectangle
sk2 = MockSketchObj()
rect_ent = {"type": "center_rectangle", "center": [0, 0], "width": "50 mm", "height": "30 mm"}
_draw(sk2, rect_ent, dummy_ex, dummy_cm, dummy_pt)
rect_h_or_v = [c[0] for c in sk2.geometricConstraints.constraints if c[0] in ('horizontal', 'vertical')]
assert 'horizontal' in rect_h_or_v
assert 'vertical' in rect_h_or_v

# Test 3: Circle with offset center
sk3 = MockSketchObj()
circ_ent = {"type": "circle", "center": ["30 mm", 0], "diameter": "8 mm"}
_draw(sk3, circ_ent, dummy_ex, dummy_cm, dummy_pt)
assert len(sk3.sketchDimensions.dims) >= 1
assert any(c[0] == 'horizontal_points' for c in sk3.geometricConstraints.constraints)

# Test 4: Sketches never fix geometry; a rectangle gets what Fusion's own tool gives it
def _kinds(sk, kind):
    return [c for c in sk.geometricConstraints.constraints if c[0] == kind]

def _dim_exprs(sk):
    return [d[1].parameter.expression for d in sk.sketchDimensions.dims]

def _all_free(sk):
    curves = [sk.sketchCurves.item(k) for k in range(sk.sketchCurves.count)]
    points = [sk.sketchPoints.item(k) for k in range(sk.sketchPoints.count)]
    ends = [p for c in curves for p in (getattr(c, 'startSketchPoint', None), getattr(c, 'endSketchPoint', None)) if p]
    return not any(o.isFixed for o in curves + points + ends)

assert len(_kinds(sk2, 'horizontal')) == 2 and len(_kinds(sk2, 'vertical')) == 2
assert _kinds(sk2, 'midpoint') and _kinds(sk2, 'coincident')  # center on the diagonal, at the origin
assert sorted(_dim_exprs(sk2)) == ['30 mm', '50 mm']
assert not _kinds(sk2, 'perpendicular')  # H + V already make the corners square
for _sk in (sk1, sk2, sk3):
    assert _all_free(_sk)

# Off-origin center: placed by one dimension per axis from the origin
sk4 = MockSketchObj()
_draw(sk4, {"type": "center_rectangle", "center": [20, 10], "width": 40, "height": 30}, dummy_ex, dummy_cm, dummy_pt)
assert sorted(_dim_exprs(sk4)) == ['10 mm', '20 mm', '30', '40']
assert _all_free(sk4)

# On a plane whose first coordinate runs along the sketch's vertical axis, width goes vertical
sk4s = MockSketchObj()
_draw(sk4s, {"type": "center_rectangle", "center": [0, 0], "width": "50 mm", "height": "30 mm"},
      dummy_ex, dummy_cm, lambda a, b: MockPoint3D(b, a, 0))
by_orient = {d[2]: d[1].parameter.expression for d in sk4s.sketchDimensions.dims}
assert by_orient[MockDimOrientations.VerticalDimensionOrientation] == '50 mm'
assert by_orient[MockDimOrientations.HorizontalDimensionOrientation] == '30 mm'

# Test 5: Orthogonal polylines get H/V and one length per segment, no redundant perpendicular
sk5 = MockSketchObj()
_draw(sk5, {"type": "polyline", "points": [[0, 50], [0, 0], [50, 0]], "closed": False},
      dummy_ex, dummy_cm, dummy_pt)
assert not _kinds(sk5, 'perpendicular')
assert len(_kinds(sk5, 'horizontal')) == 1 and len(_kinds(sk5, 'vertical')) == 1
assert len(_kinds(sk5, 'coincident')) == 1
assert sorted(_dim_exprs(sk5)) == ['50 mm', '50 mm']
assert _all_free(sk5)

# A closed rectangle away from the origin: 2 side lengths + 2 distances from the origin, nothing doubled
sk5b = MockSketchObj()
_draw(sk5b, {"type": "polygon", "points": [[10, 10], [40, 10], [40, 30], [10, 30]]}, dummy_ex, dummy_cm, dummy_pt)
assert len(_kinds(sk5b, 'horizontal')) == 2 and len(_kinds(sk5b, 'vertical')) == 2
exprs5b = _dim_exprs(sk5b)
assert len(exprs5b) == 4, exprs5b
assert '(40 mm) - (10 mm)' in exprs5b and '(30 mm) - (10 mm)' in exprs5b
assert exprs5b.count('10 mm') == 2

# Distances are magnitudes: a negative coordinate is dimensioned as its negation
from features._helpers import span_ex as _span_ex
assert _span_ex(dummy_ex, 0, 0.0, 'a', -1.0) == '-(a)'
assert _span_ex(dummy_ex, 'a', 2.0, 'b', 1.0) == '(a) - (b)'

# Regular polygon: construction circle, vertices on it, equal sides, one flat side, a diameter
sk5c = MockSketchObj()
_draw(sk5c, {"type": "regular_polygon", "id": "hex", "center": [0, 0], "sides": 6, "across_flats": "nut_af"},
      dummy_ex, dummy_cm, dummy_pt, {})
assert len(sk5c.sketchCurves.lines_list) == 6
assert sk5c.sketchCurves.circles_list[0].isConstruction
assert len(_kinds(sk5c, 'equal')) == 5
assert len([c for c in _kinds(sk5c, 'coincident') if c[2] is sk5c.sketchCurves.circles_list[0]]) == 6
assert len(_kinds(sk5c, 'horizontal')) == 1
assert _dim_exprs(sk5c) == ['(nut_af) / cos(180 deg / 6)']
assert _all_free(sk5c)

# Test 5d: Edges picked by the step that made them, minus edges touching another step's faces
class _FEdge:
    def __init__(self, geo):
        self.geometry, self.pointOnEdge, self.faces = geo, geo.startPoint, MockEdgeCollection([])

class _FFace:
    def __init__(self, edges):
        self.edges = MockEdgeCollection(edges)
        for e in edges:
            e.faces = MockEdgeCollection(e.faces.edges + [self])

class _Feat:
    def __init__(self, faces, side=None):
        self.faces = MockEdgeCollection(faces)
        self.sideFaces = MockEdgeCollection(side if side is not None else faces)

rim_out = _FEdge(MockLine3D(MockPoint3D(0, 0, 5), MockPoint3D(0, 0, 5)))
rim_out.geometry.curveType = 2
rim_in = _FEdge(MockLine3D(MockPoint3D(0, 0, 5), MockPoint3D(0, 0, 5)))
rim_in.geometry.curveType = 2
seam = _FEdge(MockLine3D(MockPoint3D(0, 0, 0), MockPoint3D(0, 0, 10)))
bore = _FFace([rim_out, rim_in, seam])
pocket_wall = _FFace([rim_in])
feats = {'screw_cut': _Feat([bore]), 'pocket_cut': _Feat([pocket_wall])}
any_body = MockBody([])
assert _select_edges(any_body, {'feature': 'screw_cut'}, feats) == [rim_out, rim_in, seam]
assert _select_edges(any_body, {'feature': 'screw_cut', 'type': 'circle', 'exclude': 'pocket_cut'}, feats) == [rim_out]
try:
    _select_edges(any_body, {'feature': 'nope'}, feats)
    assert False, 'unknown feature should fail'
except ValueError as err:
    assert 'nope' in str(err)

def _fails(d, words):
    try:
        validate(d)
    except ValueError as err:
        assert words in str(err), str(err)
        return
    assert False, f'expected failure: {words}'

_sk = {"op": "sketch", "id": "s", "plane": "xy", "entities": [{"type": "circle", "center": [0, 0], "diameter": 10}]}
validate({"parameters": {}, "timeline": [_sk, {"op": "extrude", "sketch": "s", "distance": 5},
          {"op": "chamfer", "distance": 1, "edges": {"feature": "s", "faces": "side", "type": "circle"}}]})
_fails({"parameters": {}, "timeline": [_sk, {"op": "extrude", "id": "e", "sketch": "s", "distance": 5},
        {"op": "chamfer", "distance": 1, "edges": {"feature": "e", "exclude": "ghost"}}]}, "'ghost'")
_fails({"parameters": {}, "timeline": [_sk, {"op": "extrude", "id": "e", "sketch": "s", "distance": 5},
        {"op": "fillet", "radius": 1, "edges": {"feature": "e", "colour": "red"}}]}, 'unknown edge selector keys')
_poly = lambda **kw: {"parameters": {}, "timeline": [{"op": "sketch", "id": "p", "plane": "xy", "entities": [
    dict({"type": "regular_polygon", "center": [0, 0]}, **kw)]}]}
validate(_poly(sides=6, across_flats="8 mm"))
_fails(_poly(sides=2, diameter=10), 'sides')
_fails(_poly(sides=6, diameter=10, across_flats=8), 'either diameter')

# Test 5e: A circular pattern around an off-origin center gets a parametric axis
from features.circular_pattern import _axis_through

class _AxisRoot:
    def __init__(self):
        self.sketch_list, self.axis_inputs = [], []
        root = self
        class Planes:
            def createInput(self):
                return types.SimpleNamespace(setByOffset=lambda plane, v: None)
            def add(self, inp):
                return types.SimpleNamespace(isLightBulbOn=True)
        class Sketches:
            def add(self, plane):
                sk = MockSketchObj()
                sk.modelToSketchSpace = lambda p: MockPoint3D(p.x, p.y, p.z)
                root.sketch_list.append(sk)
                return sk
        class Axes:
            def createInput(self):
                inp = types.SimpleNamespace()
                inp.setByTwoPoints = lambda a, b: setattr(inp, 'points', (a, b))
                root.axis_inputs.append(inp)
                return inp
            def add(self, inp):
                return types.SimpleNamespace(points=inp.points, isLightBulbOn=True)
        self.constructionPlanes, self.sketches, self.constructionAxes = Planes(), Sketches(), Axes()

mock_core.ValueInput = types.SimpleNamespace(createByString=lambda v: v)
_ar = _AxisRoot()
_axis = _axis_through(_ar, 'XY', lambda a, b: (a, b, 0), ['center_dist', 0], 'gear2_axis', dummy_ex, lambda v: 4.0 if v == 'center_dist' else dummy_cm(v))
assert len(_ar.sketch_list) == 2 and not _axis.isLightBulbOn
for _sk, _p in zip(_ar.sketch_list, _axis.points):
    assert _p in _sk.sketchPoints._pts and not _sk.isVisible
    assert _dim_exprs(_sk) == ['center_dist']                       # x driven by the parameter
    assert _kinds(_sk, 'horizontal_points')                         # y = 0: aligned with the origin
    assert not _p.isFixed

_pat = lambda **kw: {"parameters": {}, "timeline": [_sk_c, {"op": "extrude", "id": "t", "sketch": "s", "distance": 5},
    dict({"op": "circular_pattern", "feature": "t", "quantity": 4}, **kw)]}
_sk_c = {"op": "sketch", "id": "s", "plane": "xy", "entities": [{"type": "circle", "center": [40, 0], "diameter": 10}]}
validate(_pat(center=["center_dist", 0]))
_fails(_pat(center=[1, 2, 3]), 'center')

# Test 5f: profile = lines and three-point arcs sharing corners, every point placed, nothing fixed
class MockSKArc:
    def __init__(self, a, b, mid=None):  # Fusion may start an arc at either end; start at b to test matching
        self.startSketchPoint, self.endSketchPoint = MockSKPt(b.x, b.y), MockSKPt(a.x, a.y)
        self.isFixed = False
        self.geometry = types.SimpleNamespace(evaluator=types.SimpleNamespace(
            getParameterExtents=lambda: (True, 0.0, 1.0), getPointAtParameter=lambda t: (True, mid)))

def _add_arc(curves, a, mid, b):
    arc = MockSKArc(a, b, mid)
    curves.arcs_list.append(arc)
    return arc

MockSKCurves.sketchArcs = property(
    lambda self: types.SimpleNamespace(addByThreePoints=lambda a, m, b: _add_arc(self, a, m, b)))

sk5f = MockSketchObj()
sk5f.sketchCurves.arcs_list = []
_slot = {"type": "profile", "id": "slot", "start": [0, 0], "segments": [
    {"to": [40, 0]}, {"to": [40, 20], "through": [50, 10]}, {"to": [0, 20]}, {"to": [0, 0], "through": [-10, 10]}]}
_ents = {}
_draw(sk5f, _slot, dummy_ex, dummy_cm, dummy_pt, _ents)
_arcs = sk5f.sketchCurves.arcs_list
assert len(_arcs) == 2 and len(sk5f.sketchCurves.lines_list) == 2 and len(_ents['slot']) == 4
_l1, _l2 = sk5f.sketchCurves.lines_list
_co = [(c[1], c[2]) for c in _kinds(sk5f, 'coincident')]
assert (_arcs[0].endSketchPoint, _l1.endSketchPoint) in _co or (_arcs[0].startSketchPoint, _l1.endSketchPoint) in _co
assert _l2.startSketchPoint in (_arcs[0].startSketchPoint, _arcs[0].endSketchPoint)  # next line starts at the arc's end
assert any(b is _l1.startSketchPoint for _, b in _co)            # the closing arc meets the first corner
assert sum(1 for a, b in _co if b in _arcs) == 2                  # each arc's middle point is on it
assert len(_kinds(sk5f, 'horizontal')) == 2                       # both straight sides
assert all(not o.isFixed for o in sk5f.sketchCurves.lines_list + _arcs + sk5f.sketchPoints._pts)
validate({"parameters": {}, "timeline": [{"op": "sketch", "id": "s", "plane": "xy", "entities": [_slot]}]})
_fails({"parameters": {}, "timeline": [{"op": "sketch", "id": "s", "plane": "xy", "entities": [
    {"type": "profile", "start": [0, 0], "segments": [{"through": [1, 1]}]}]}]}, 'missing to')

# Test 5f2: mirror = copies of earlier entities across a construction line, tied by symmetry
import math
from dsl import JSON_SCHEMA
sk5m = MockSketchObj()
sk5m.sketchCurves.arcs_list = []
_ents = {}
for _e in [{"type": "profile", "id": "half", "closed": False, "start": [0, 0], "segments": [
               {"to": [30, 0]}, {"to": [40, 10], "through": [30 + 10 * math.sin(math.pi / 4), 10 - 10 * math.cos(math.pi / 4)]},
               {"to": [40, 20]}, {"to": [0, 20]}]},
           {"type": "circle", "id": "hole", "center": [20, 10], "diameter": 6},
           {"type": "circle", "id": "middle", "center": [0, 10], "diameter": 4},
           {"type": "mirror", "id": "whole", "entities": ["half", "hole", "middle"], "line": [[0, -10], [0, 30]]}]:
    _draw(sk5m, _e, dummy_ex, dummy_cm, dummy_pt, _ents)
_lines, _arcs5, _circs = sk5m.sketchCurves.lines_list, sk5m.sketchCurves.arcs_list, sk5m.sketchCurves.circles_list
_axis = next(l for l in _lines if l.isConstruction)
assert len(_lines) == 3 + 1 + 3 and len(_arcs5) == 2 and len(_circs) == 2 + 1   # the middle circle is its own mirror
assert len(_ents['whole']) == 6 + 5
_xy = lambda p: (round(p.geometry.x, 6), round(p.geometry.y, 6))
_copies = _ents['whole'][6:]
assert _xy(_copies[0].startSketchPoint) == (0, 0) and _xy(_copies[0].endSketchPoint) == (-3, 0)
assert _copies[0].startSketchPoint is _ents['half'][0].startSketchPoint  # on the line: shared, so the halves join
assert _xy(_copies[-1].centerSketchPoint) == (-2, 1)
_sym = _kinds(sk5m, 'symmetry')
assert len(_sym) == 4 and all(c[3] is _axis for c in _sym)          # one per point off the line: 30,0 40,10 40,20 20,10
assert sorted(_xy(c[2]) for c in _sym) == [(-4, 1), (-4, 2), (-3, 0), (-2, 1)]
assert len(_kinds(sk5m, 'equal')) == 2                               # the arc and the circle keep their size
_new_lines = _copies[0:1] + _copies[2:4]
assert _new_lines[1].startSketchPoint in [p for a in _arcs5[1:] for p in (a.startSketchPoint, a.endSketchPoint)] \
    or any(c[1] is _new_lines[1].startSketchPoint for c in _kinds(sk5m, 'coincident'))
assert _new_lines[1].endSketchPoint is _new_lines[2].startSketchPoint   # a shared corner gets one mirrored point
assert _new_lines[2].endSketchPoint is _ents['half'][3].endSketchPoint  # ...and the other end is on the line
# A copy that comes out looser than its fully constrained original gets the curves tied too
from features.entities.mirror import _mirror_curves
sk5n = MockSketchObj()
_ents = {}
for _e in [{"type": "polyline", "id": "p", "points": [[10, 0], [20, 0], [20, 10]]},
           {"type": "line", "id": "ax", "start": [0, -10], "end": [0, 30]}]:
    _draw(sk5n, _e, dummy_ex, dummy_cm, dummy_pt, _ents)
_src = list(_ents['p'])
_src[0].isFullyConstrained = True                     # the second line stays loose like its copy
_made = _mirror_curves(sk5n, _src, _ents['ax'])
_curve_sym = [c for c in _kinds(sk5n, 'symmetry') if c[1] in _src]
assert len(_made) == 2 and len(_curve_sym) == 1 and _curve_sym[0][1:] == (_src[0], _made[0], _ents['ax'])
_mv = lambda **kw: {"parameters": {}, "timeline": [{"op": "sketch", "id": "s", "plane": "xy", "entities": [
    {"type": "polyline", "id": "p", "points": [[0, 0], [10, 0], [10, 10]]}, dict({"type": "mirror"}, **kw)]}]}
validate(_mv(entities=["p"], line=[[0, 0], [0, 1]]))
_fails(_mv(entities=["q"], line=[[0, 0], [0, 1]]), 'not an entity id defined earlier')
_fails(_mv(entities=["p"], line=[[0, 0]]), 'line must be two points')
_fails(_mv(entities=[], line=[[0, 0], [0, 1]]), 'non-empty list')
assert 'mirror' in JSON_SCHEMA['properties']['timeline']['items']['properties']['entities']['items'][
    'properties']['type']['enum']

# Test 5f3: assemblies. Components have their own timelines (own sketch ids); instances place copies
import copy as _copy
_part = lambda size: [
    {"op": "sketch", "id": "base_sk", "plane": "xy",
     "entities": [{"type": "center_rectangle", "center": [0, 0], "width": size, "height": size}]},
    {"op": "extrude", "id": "base", "sketch": "base_sk", "distance": size, "mode": "new_body"}]
_asm = {"parameters": {"leg": "40 mm", "top": "300 mm", "half": "top / 2 - leg", "turn": "90 deg"},
        "timeline": [],
        "components": [{"id": "leg", "name": "Leg", "timeline": _part("leg")},
                       {"id": "top", "timeline": _part("top")}],   # same sketch id in both: fine
        "instances": [{"component": "leg", "id": "leg_a", "position": ["half", "half", 0]},
                      {"component": "leg", "position": ["-half", 0, 0], "rotate": [{"axis": "z", "angle": "turn"}]}]}
validate(_copy.deepcopy(_asm))
_bad = lambda **kw: dict(_copy.deepcopy(_asm), **kw)
_fails(_bad(components=[]), 'components must be a non-empty list')
_fails(_bad(components=[{"id": "leg", "timeline": _part("leg")}, {"id": "leg", "timeline": _part("leg")}]),
       'duplicate component id')
_fails(_bad(components=[{"id": "leg", "timeline": []}]), 'components[0]: timeline must be a non-empty list')
_fails(_bad(components=[{"id": "leg", "timeline": [{"op": "extrude", "sketch": "nope", "distance": 1}]}]),
       'components[0].timeline[0]')
_fails(_bad(instances=[{"component": "shelf"}]), "component 'shelf' is not in components")
_fails(_bad(instances=[{"component": "leg", "position": [0, 0]}]), 'position must be [x, y, z]')
_fails(_bad(instances=[{"component": "leg", "rotate": [{"axis": "w", "angle": 90}]}]), 'rotate must be a list')
_fails(_bad(instances=[{"component": "leg", "id": "a"}, {"component": "leg", "id": "a"}]), 'duplicate instance id')
_fails({"parameters": {}, "timeline": _part(10), "instances": [{"component": "leg"}]}, 'instances need components')
_fails({"parameters": {}, "timeline": []}, 'timeline must be a non-empty list')
_js = JSON_SCHEMA['properties']
assert _js['components']['items']['properties']['timeline'] is _js['timeline'] and 'rotate' in _js['instances']['items']['properties']
assert 'ASSEMBLIES' in llm.SYSTEM and '"instances"' in llm.SYSTEM

# Shapes expand inside components too; their parameters are shared, so two shape ids can't clash
_rail = {"op": "tslot_profile", "id": "rail", "series": "2020", "length": 100}
_x = dsl_mod.expand_shapes({"parameters": {}, "timeline": [], "components": [{"id": "r", "timeline": [_rail]}]})
assert 'rail_slot' in _x['parameters'] and all(s['op'] != 'tslot_profile' for s in _x['components'][0]['timeline'])
validate({"parameters": {}, "timeline": [], "components": [{"id": "r", "timeline": [_rail]}]})
_fails({"parameters": {}, "timeline": [], "components": [{"id": "a", "timeline": [_rail]}, {"id": "b", "timeline": [_rail]}]},
       'components[1].timeline[0] (tslot_profile): parameters')

# Renamed parameters (they already exist in the design) are renamed in components and positions too
_r = dsl_mod.disambiguate_parameters(_copy.deepcopy(_asm), {'leg'})
assert _r['components'][0]['timeline'][0]['entities'][0]['width'].startswith('part2_leg')
assert _r['instances'][0]['position'][0] == 'part2_half' and _r['instances'][1]['rotate'][0]['angle'] == 'part2_turn'
assert _r['instances'][0]['component'] == 'leg' and _r['components'][0]['id'] == 'leg'

# The parameters that move copies, directly or through other parameters
assert dsl_mod.placement_parameters(_asm) == {'half', 'top', 'leg', 'turn'}
assert dsl_mod.placement_parameters(dict(_asm, instances=[{"component": "top"}])) == set()

# Placement: turns about the world axes in order, then the position
_turns, _pos = dsl_mod._placement(_asm['instances'][1], lambda v: f'L({v})', lambda a: f'A({a})')
assert _turns == [('z', 'A(turn)')] and _pos == ('L(-half)', 'L(0)', 'L(0)')
assert dsl_mod._placement({"component": "x"}, str, str) == ([], ('0', '0', '0'))

# Occurrences: the first instance makes the component, the others are copies of it
class _Occs:
    def __init__(self):
        self.made = []

    def addNewComponent(self, m):
        o = SimpleNamespace(component=SimpleNamespace(name=None), name=None, entityToken=f'occ{len(self.made)}', m=m)
        self.made.append(('new', o))
        return o

    def addExistingComponent(self, comp, m):
        o = SimpleNamespace(component=comp, name=None, entityToken=f'occ{len(self.made)}', m=m)
        self.made.append(('copy', o))
        return o

from types import SimpleNamespace
_parent = SimpleNamespace(occurrences=_Occs())
_made, _occs = dsl_mod._add_occurrences(_parent, _asm['components'], _asm['instances'],
                                         lambda inst: inst.get('position'))
assert [k for k, _ in _parent.occurrences.made] == ['new', 'copy', 'new']
_legs = [o for _, o in _parent.occurrences.made[:2]]
assert _legs[0].component is _legs[1].component and _legs[0].component.name == 'Leg' and _legs[0].name == 'leg_a'
assert _legs[1].m == ['-half', 0, 0] and _parent.occurrences.made[2][1].m is None   # no instances: where modeled
assert _made[1][1].name == 'top' and [c['id'] for c, _ in _made] == ['leg', 'top'] and len(_occs) == 3

# Angle parameters: by name, or deg/rad in something that isn't a length
from dsl import _is_angle_param
assert _is_angle_param('draft_angle', '5', False)
assert _is_angle_param('tilt', '5 deg', False)
assert not _is_angle_param('gear_base_r', 'gear_pitch_r * cos(20 deg)', True)
assert not _is_angle_param('gear_radius', '10 mm', True)
assert not _is_angle_param('angle_t', '2 mm', True)                    # a rack angle's thickness
assert not _is_angle_param('angle_back', 'angle_face + angle_t', True)  # works out as a length
assert _is_angle_param('tilt_angle', 'base_angle * 2', False)           # doesn't: an angle
assert _is_angle_param('cone_angle', '30 deg', False)

# Test 5g: Shape plugins. The core names none of them; a shape step expands into plain DSL
import math
import shapes as shape_registry
_ops = [s.op for s in shape_registry.get_all_shapes()]
assert 'spur_gear' in _ops
for _f in ('dsl.py', 'llm.py', 'VibeShaper.py', 'bom.py', 'shapes/__init__.py', 'shapes/base.py', 'shapes/_json.py',
           'features/__init__.py', 'features/base.py', 'features/entities/__init__.py', 'features/entities/base.py'):
    _src = (_HERE / _f).read_text(encoding='utf-8')
    for _op in _ops:
        assert not _re.search(rf'\b{_re.escape(_op)}\b', _src), f'{_f} mentions the shape {_op!r}'
_step_props = dsl_mod.JSON_SCHEMA['properties']['timeline']['items']['properties']
assert set(_ops) <= set(_step_props['op']['enum']) and 'teeth' in _step_props
assert 'spur_gear' in llm.SYSTEM

_gears = {"parameters": {"gear_module": "2 mm", "gear1_teeth": "15", "gear2_teeth": "26", "gear_thick": "8 mm"},
          "timeline": [
              {"op": "spur_gear", "id": "gear1", "module": "gear_module", "teeth": "gear1_teeth",
               "thickness": "gear_thick", "bore": "8 mm"},
              {"op": "spur_gear", "id": "gear2", "module": "gear_module", "teeth": "gear2_teeth",
               "thickness": "gear_thick", "center": ["gear_module * (gear1_teeth + gear2_teeth) / 2", 0],
               "rotate": "180 deg / gear2_teeth"},
              {"op": "fillet", "radius": "0.5 mm", "edges": {"feature": "gear2", "at": "top"}}]}
validate(_gears)
_x = dsl_mod.expand_shapes(_gears)
assert _gears['timeline'][0]['op'] == 'spur_gear'                 # the original is left as written
assert dsl_mod.expand_shapes(_x) is _x                            # nothing left to expand
_by_id = {s.get('id'): s for s in _x['timeline']}
assert _by_id['gear2']['op'] == 'circular_pattern' and _by_id['gear2']['quantity'] == 'gear2_teeth'
assert _by_id['gear2']['center'] == ["gear_module * (gear1_teeth + gear2_teeth) / 2", 0]
assert _by_id['gear1_bore']['mode'] == 'cut' and 'gear2_bore' not in _by_id
assert _by_id['gear2_tooth']['mode'] == 'join' and _x['timeline'][-1]['op'] == 'fillet'


def _eval_params(params):
    """Evaluate the generated formulas in plain Python (radians, mm)."""
    vals, env = {}, {'cos': math.cos, 'sin': math.sin, 'tan': math.tan, 'acos': math.acos, 'abs': abs,
                       'floor': math.floor, 'sqrt': math.sqrt}

    def ev(x):
        x = _re.sub(r'(\d+(?:\.\d+)?)\s*deg', r'(\1*%r)' % (math.pi / 180), str(x))
        x = _re.sub(r'(\d+(?:\.\d+)?)\s*(mm|rad)\b', r'\1', x)
        return eval(x, env, vals)
    for k, v in params.items():
        vals[k] = ev(v)
    return vals, ev


# The tooth's points really lie on the involute
_vals, _ev = _eval_params(_x['parameters'])
for _gid, _z in (('gear1', 15), ('gear2', 26)):
    _m, _pa = 2.0, math.radians(20)
    _rb = _m * _z / 2 * math.cos(_pa)
    _inv = lambda a: math.tan(a) - a
    _true = lambda r: math.pi / (2 * _z) + _inv(_pa) - _inv(math.acos(_rb / r))
    assert abs(_vals[f'{_gid}_tip_angle'] - _true(_m * _z / 2 + _m)) < 1e-9
    assert abs(_vals[f'{_gid}_flank_angle'] - _true(max(_rb, _m * _z / 2 - 1.25 * _m) + 0.001)) < 1e-6
    _prof = _by_id[f'{_gid}_tooth_sk']['entities'][0]
    _cx = _ev(_prof['start'][0])
    _rot = _vals[f'{_gid}_rotate_angle']
    _px, _py = (_ev(c) for c in _prof['segments'][1]['through'])  # flank point on the pitch circle
    assert abs(math.hypot(_px - _cx, _py) - _m * _z / 2) < 1e-9
    assert abs(abs(math.atan2(_py, _px - _cx) - _rot) * _m * _z / 2 - math.pi * _m / 4) < 1e-9  # half a tooth
assert abs(_vals['gear2_rotate_angle'] - math.pi / 26) < 1e-12

_g = lambda **kw: {"parameters": {}, "timeline": [dict({"op": "spur_gear", "id": "g", "module": 2, "teeth": 20,
                                                        "thickness": 5}, **kw)]}
validate(_g())
_fails(_g(teeth=6), 'teeth')
_fails(_g(id='my gear'), 'snake_case')
_fails(_g(mode='cut'), 'mode')
_fails({"parameters": {"g_pitch_r": "1 mm"}, "timeline": _g()['timeline']}, 'already exist')
_fails({"parameters": {}, "timeline": [{"op": "spur_gear", "id": "g", "module": 2, "thickness": 5}]}, 'missing teeth')

_sk1 = {"op": "sketch", "id": "s", "plane": "xy", "entities": [{"type": "circle", "center": [0, 0], "diameter": 10}]}

# Edges lying in a sketch's plane ("on"): the rim where a hole meets the face it was sketched on
class _V:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z

class _OnEdge:
    def __init__(self, z, circle=True):
        self.pointOnEdge = _V(1, 0, z)
        self.startVertex = types.SimpleNamespace(geometry=_V(1, 0, z))
        self.endVertex = self.startVertex
        self.geometry = types.SimpleNamespace(curveType=2 if circle else 1, center=_V(0, 0, z))
        self.faces = MockEdgeCollection([])

from features._helpers import edge_on_sketch_plane as _edge_on_sketch_plane
_top_sk = types.SimpleNamespace(origin=_V(0, 0, 0.5), xDirection=_V(1, 0, 0), yDirection=_V(0, 1, 0))
_rim_top, _rim_bottom = _OnEdge(0.5), _OnEdge(0.0)
assert _edge_on_sketch_plane(_rim_top, _top_sk) and not _edge_on_sketch_plane(_rim_bottom, _top_sk)
_side_sk = types.SimpleNamespace(origin=_V(1, 0, 0), xDirection=_V(0, 1, 0), yDirection=_V(0, 0, 1))  # the x = 1 plane
assert _edge_on_sketch_plane(_rim_top, _side_sk) is False  # its center is off that plane
_hole_face = _FFace([_rim_top, _rim_bottom])
assert _select_edges(any_body, {'feature': 'h', 'on': 'top_sk'}, {'h': _Feat([_hole_face])},
                     {'top_sk': _top_sk}) == [_rim_top]
_fails({"parameters": {}, "timeline": [_sk1, {"op": "extrude", "id": "e", "sketch": "s", "distance": 5},
                                       {"op": "chamfer", "distance": 1, "edges": {"feature": "e", "on": "nope"}}]},
       'edges.on')

# linear_pattern in two directions
_lp = lambda **kw: {"parameters": {}, "timeline": [_sk1, {"op": "extrude", "id": "e", "sketch": "s", "distance": 5},
                                                   dict({"op": "linear_pattern", "feature": "e", "direction": "x",
                                                         "distance": 10, "quantity": 3}, **kw)]}
validate(_lp(direction2="y", quantity2=2, distance2=8))
_fails(_lp(direction2="x", quantity2=2, distance2=8), 'direction2')
_fails(_lp(direction2="y"), 'missing quantity2')
assert 'direction2' in _step_props and 'on' in _step_props['edges']['anyOf'][1]['properties']


def _shape(op, **kw):
    return {"parameters": {}, "timeline": [dict({"op": op}, **kw)]}


def _expand(op, **kw):
    d = _shape(op, **kw)
    validate(d)
    x = dsl_mod.expand_shapes(d)
    return x, {s.get('id'): s for s in x['timeline']}, _eval_params(x['parameters'])


for _op in ('bolt_hole', 'vent_grid', 'tslot_profile'):
    assert _op in _ops and _op in llm.SYSTEM

# Bolt holes: ISO sizes, pockets from the entry face in the hole's direction
_corners = [["-hole_off", "-hole_off"], ["hole_off", "hole_off"]]
_x, _by, (_v, _ev) = _expand('bolt_hole', id='b', size='M5', plane='xy', offset='9 mm', depth='-9 mm',
                             head='nut_trap', points=[[-17.5, -17.5], [17.5, 17.5]])
assert _x['parameters']['b_hole_d'] == '5.5 mm'
assert abs(_v['b_nut_af'] - 8.6) < 1e-9 and abs(_v['b_nut_depth'] - 5.0) < 1e-9  # 8 + 2 x 0.3, 4.7 + 0.3
assert _by['b']['mode'] == 'cut' and _by['b']['distance'] == 'b_depth'
assert abs(_ev(_by['b_nut']['distance']) + 5.0) < 1e-9                 # same way as the hole: down
assert len(_by['b_sk']['entities']) == 2 and _by['b_nut_sk']['entities'][0]['sides'] == 6
assert _by['b_sk']['offset'] == '9 mm'
_x, _by, (_v, _ev) = _expand('bolt_hole', id='c', size='M3', depth=6, head='counterbore', fit='close',
                             tolerance=0.2, center=[0, 0])
assert _x['parameters']['c_hole_d'] == '3.2 mm' and abs(_v['c_head_d'] - 5.9) < 1e-9
assert abs(_ev(_by['c_head']['distance']) - 3.2) < 1e-9                 # 3 + 0.2, up like the hole
_x, _by, (_v, _ev) = _expand('bolt_hole', id='k', size='M4', depth=-5, head='countersink')
_ch = _by['k_head']
assert _ch['op'] == 'chamfer' and _ch['edges'] == {'feature': 'k', 'type': 'circle', 'on': 'k_sk'}
assert abs(_ev(_ch['distance']) - (8.96 + 0.6 - 4.5) / 2) < 1e-9  # a 90 degree cone out to the head
_x, _by, _ = _expand('bolt_hole', id='p', size='M6', depth=-5)
assert set(_by) == {'p_sk', 'p'}
_fails(_shape('bolt_hole', id='b', size='M7', depth=5), 'size must be')
_fails(_shape('bolt_hole', id='b', size='M5', depth=5, head='cap'), 'head must be')
_fails(_shape('bolt_hole', id='b', size='M5', depth=0), 'depth')
_fails(_shape('bolt_hole', id='b', size='M5', depth=5, points=[]), 'points')

# Vent grids: the counts are formulas, the patterns start in the corner and fill the area
_x, _by, (_v, _ev) = _expand('vent_grid', id='v', width=60, height=40, size=5, wall=1, layout='grid', depth=-2)
assert _v['v_count_a'] == 10 and _v['v_count_b'] == 6       # floor((60 - 5) / 6) + 1, floor((40 - 5) / 6) + 1
_pat = _by['v']
assert _pat['op'] == 'linear_pattern' and _pat['feature'] == 'v_hole'
assert (_pat['direction'], _pat['direction2']) == ('x', 'y') and _pat['quantity'] == 'v_count_a'
_c = [_ev(c) for c in _by['v_hole_sk']['entities'][0]['center']]
assert abs(_c[0] - -27) < 1e-9 and abs(_c[1] - -15) < 1e-9  # centered: -(10 - 1) * 6 / 2, -(6 - 1) * 6 / 2
assert _by['v_hole']['distance'] == -2
_x, _by, (_v, _ev) = _expand('vent_grid', id='h', plane='xz', center=[10, 5], width=50, height=30,
                             hole='hexagon', size=5, wall=1.5, depth=3)
assert _by['h_hole_sk']['entities'][0]['type'] == 'regular_polygon' and _by['h']['feature'] == 'h_hole2'
assert (_by['h']['direction'], _by['h']['direction2']) == ('x', 'z')
assert _ev(_by['h']['quantity']) == _v['h_count_a'] - 1 and _ev(_by['h']['quantity2']) == _v['h_count_b'] - 1
_a1 = [_ev(c) for c in _by['h_hole_sk']['entities'][0]['center']]
_b1 = [_ev(c) for c in _by['h_hole2_sk']['entities'][0]['center']]
assert abs(math.hypot(_b1[0] - _a1[0], _b1[1] - _a1[1]) - 6.5) < 1e-9  # honeycomb: every neighbor 5 + 1.5 away
_last = [_a1[0] + (_v['h_count_a'] - 1) * _v['h_pitch_a'], _a1[1] + (_v['h_count_b'] - 1) * _v['h_pitch_b']]
assert abs((_a1[0] + _last[0]) / 2 - 10) < 1e-9 and abs((_a1[1] + _last[1]) / 2 - 5) < 1e-9
assert _last[0] + _v['h_ext_a'] / 2 <= 10 + 25 and _last[1] + 2.5 <= 5 + 15  # the holes stay inside the area
_x, _by, (_v, _ev) = _expand('vent_grid', id='s', width=80, height=30, hole='slot', size=4, length=20, depth=-2,
                             columns=6)
_slot = _by['s_hole_sk']['entities'][0]
assert _slot['type'] == 'profile' and sum('through' in g for g in _slot['segments']) == 2
assert _v['s_count_a'] == 6 and _v['s_count_b'] == 1
_ys = [_ev(p[1]) for p in [_slot['start']] + [g['to'] for g in _slot['segments']]]
assert abs(max(_ys) - min(_ys) - 16) < 1e-9                   # straight part: 20 - 4
_fails(_shape('vent_grid', id='v', width=5, height=40, size=5, depth=-2), 'at least 2 x 2')
_fails(_shape('vent_grid', id='v', width=60, height=40, size=5, depth=-2, hole='slot'), 'length')
_fails(_shape('vent_grid', id='v', width=60, height=40, size=5, length=4, depth=-2, hole='slot'), 'more than its width')
_fails(_shape('vent_grid', id='v', width=60, height=40, size=5, depth=-2, rows=0), 'rows')


# A join, cut or intersect changes only its own component's bodies, never a part placed against it
import features._helpers as _feat_helpers
_own = lambda bodies, mode: _feat_helpers.own_bodies(SimpleNamespace(), SimpleNamespace(bRepBodies=_FakeBodies(bodies)),
                                                     mode)
class _FakeBodies:
    def __init__(self, items):
        self.items, self.count = items, len(items)
    def item(self, k):
        return self.items[k]
assert _own(['rail_bar'], 'cut').participantBodies == ['rail_bar']
assert _own(['a', 'b'], 'join').participantBodies == ['a', 'b'] and _own(['a'], 'intersect').participantBodies == ['a']
assert not hasattr(_own(['a'], 'new_body'), 'participantBodies')
assert not hasattr(_own([], 'cut'), 'participantBodies')            # nothing of its own yet: leave Fusion's default
_feat_src = '\n'.join(
    p.read_text(encoding='utf-8') for p in (_HERE / 'features').glob('*.py')
    if p.name != 'base.py' and not p.name.startswith('_')
)
for _call in ('feats.createInput', 'revolves.createInput', 'sweeps.createInput(prof_arg', 'sweeps.createInput(prof,'):
    assert f'h.own_bodies({_call}' in _feat_src, _call                 # every feature that can cut is limited

# Bill of materials: expressions are evaluated without Fusion
import bom as bom_mod
_bev = bom_mod.Evaluator({'a': '10 mm', 'b': 'a * 2 + 1 cm', 'n': '4', 'ang': '90 deg', 'loop': 'loop + 1'})
assert _bev('b') == 30 and _bev('2 m') == 2000 and _bev('1 in') == 25.4 and _bev(7) == 7
assert _bev('n ^ 2') == 16 and _bev('floor(a / 3 mm)') == 3 and abs(_bev('sin(ang)') - 1) < 1e-12
assert _bev('max(a, 12 mm) + abs(-1)') == 13 and _bev('-a') == -10
for _bad, _words in (('nope + 1', "'nope'"), ('loop', 'depends on itself'), ('__import__("os")', 'cannot evaluate'),
                     ('a +', 'cannot read')):
    try:
        _bev(_bad)
        assert False, _bad
    except ValueError as err:
        assert _words in str(err), str(err)


def _bom(d):
    return {(r['Category'], r['Item']): r for r in bom_mod.collect(d)}


_plate = lambda **kw: dict({"id": "plate", "name": "Plate", "material": "PETG", "timeline": [
    {"op": "sketch", "id": "s", "plane": "xy", "entities": [{"type": "center_rectangle", "center": [0, 0],
                                                             "width": 60, "height": 40}]},
    {"op": "extrude", "id": "e", "sketch": "s", "distance": "t", "mode": "new_body"},
    {"op": "bolt_hole", "id": "h", "size": "M5", "offset": "t", "depth": "-t", "points": [[-20, 0], [20, 0]],
     "screw": {"length": "t + 5.5 mm", "nut": "t_nut_20", "washer": True}},
    {"op": "linear_pattern", "feature": "h", "direction": "x", "distance": 5, "quantity": 2,
     "direction2": "y", "quantity2": 3, "distance2": 5}]}, **kw)
_asm = {"parameters": {"t": "6 mm", "post_h": "200 mm", "travel": "200 mm"}, "timeline": [],
        "components": [_plate(),
                       {"id": "post", "name": "Post", "timeline": [
                           {"op": "tslot_profile", "id": "p", "series": "2040", "length": "-post_h"}]},
                       {"id": "beam", "name": "Beam", "timeline": [
                           {"op": "tslot_profile", "id": "bp", "series": "2040", "length": "post_h"}],
                        "bom": [{"category": "Fasteners", "item": "M5 T-nut for 20-series slot (6 mm)", "qty": 2}]}],
        "instances": [{"component": "plate"}, {"component": "plate"}, {"component": "post"}],
        "bom": [{"category": "Wiring", "item": "4-core cable", "qty": "travel + 400 mm", "unit": "m", "round": 0.5},
                {"category": "Wiring", "item": "Heat-shrink", "qty": 1.5, "unit": "m", "note": "3 mm"},
                {"category": "Electronics", "item": "24 V supply", "link": "https://example.com/psu"}]}
_b = _bom(_asm)
# 2 holes x 6 pattern copies x 2 plates; 6 + 5.5 = 11.5 mm rounds up to the 12 mm stock screw
assert _b[('Fasteners', 'M5x12 socket head cap screw (ISO 4762)')]['Qty'] == 24
assert _b[('Fasteners', 'M5 washer (ISO 7089)')]['Qty'] == 24
assert _b[('Fasteners', 'M5 T-nut for 20-series slot (6 mm)')]['Qty'] == 26  # a component's own item adds to it
_ext = _b[('Frame', '2040 aluminium T-slot extrusion, cut to 200 mm')]
assert _ext['Qty'] == 2 and _ext['Unit'] == 'pcs'                     # post (signed length) + beam: one line
assert _b[('Wiring', '4-core cable')]['Qty'] == 1.0 and _b[('Wiring', '4-core cable')]['Unit'] == 'm'  # 0.6 -> 1
assert _b[('Wiring', 'Heat-shrink')]['Qty'] == 1.5                    # a plain number is in the item's unit
assert _b[('Electronics', '24 V supply')]['Link'] == 'https://example.com/psu'
assert _b[('Made', 'Plate')]['Qty'] == 2 and _b[('Made', 'Plate')]['Note'] == 'PETG'
assert ('Made', 'Post') not in _b and ('Made', 'Beam') not in _b      # a bought extrusion isn't made
_rows = bom_mod.collect(_asm)
assert [r['Category'] for r in _rows][-1] == 'Made' and _rows[0]['Category'] == 'Electronics'
_csv = bom_mod.to_csv(_rows)
assert _csv.splitlines()[0] == 'Category,Item,Qty,Unit,Note,Link' and ',24,pcs,' in _csv
_single = {"name": "Bracket", "parameters": {"t": "6 mm"}, "timeline": _plate()['timeline']}
assert _bom(_single)[('Made', 'Bracket')]['Qty'] == 1
assert _bom(_single)[('Fasteners', 'M5x12 socket head cap screw (ISO 4762)')]['Qty'] == 12
_bom_dir = pathlib.Path(tempfile.mkdtemp())
(_bom_dir / 'd.json').write_text(json.dumps(_asm))
assert bom_mod.main(['bom.py', str(_bom_dir / 'd.json'), str(_bom_dir / 'd.csv')]) == 0
assert (_bom_dir / 'd.csv').read_text(encoding='utf-8-sig') == _csv
try:
    bom_mod.collect(dict(_asm, bom=[{"category": "X", "item": "Rod {length}", "length": "5 m", "stock": [1000]}]))
    assert False
except ValueError as err:
    assert 'longer than any stock length' in str(err), str(err)

# The bom keys are checked like the rest of the design
_bad_bom = lambda items: dict(_asm, bom=items)
_fails(_bad_bom([{"item": "x"}]), 'missing category')
_fails(_bad_bom([{"category": "X", "item": "x", "price": 3}]), 'unknown keys')
_fails(_bad_bom([{"category": "X", "item": "Rod {length}"}]), 'no length')
_fails(_bad_bom([{"category": "X", "item": "x", "length": 5, "stock": [0]}]), 'stock')
_fails(_bad_bom([{"category": "X", "item": "x", "stock": [100]}]), 'stock needs a length')
_fails(_bad_bom([{"category": "X", "item": "x", "whole": "yes"}]), 'whole')
_fails(_bad_bom([{"category": "X", "item": "x", "round": 0}]), 'round')
_fails(_bad_bom({"category": "X"}), 'must be a list')
_fails(dict(_asm, components=[_plate(material="")]), 'material')
_fails(dict(_asm, components=[_plate(bom=[{"category": "X"}])]), 'components[0].bom[0]: missing item')
assert 'bom' in dsl_mod.JSON_SCHEMA['properties'] and 'bom' in \
    dsl_mod.JSON_SCHEMA['properties']['components']['items']['properties']

# Bolt hole screws: defaults follow the hole's head; bad screws are refused
_sb = lambda **kw: shape_registry.get_shape('bolt_hole').bom(dict({"id": "b", "size": "M3", "depth": 5}, **kw))
assert _sb() == []
assert [i['item'] for i in _sb(head='countersink', screw={"length": 10})] == \
    ['M3x{length_mm} countersunk screw (ISO 10642)']
assert [i['item'] for i in _sb(head='nut_trap', screw={"length": 10}, points=[[0, 0], [5, 0], [9, 0]])] == \
    ['M3x{length_mm} socket head cap screw (ISO 4762)', 'M3 hex nut (ISO 4032)']
assert _sb(head='nut_trap', screw={"length": 10, "nut": "none"})[0]['qty'] == 1 and \
    len(_sb(head='nut_trap', screw={"length": 10, "nut": "none"})) == 1
_fails(_shape('bolt_hole', id='b', size='M5', depth=5, screw={}), 'screw must be an object with a length')
_fails(_shape('bolt_hole', id='b', size='M5', depth=5, screw={"length": 8, "head": "hex"}), 'screw head')
_fails(_shape('bolt_hole', id='b', size='M5', depth=5, screw={"length": 8, "nut": "wing"}), 'screw nut')
_fails(_shape('bolt_hole', id='b', size='M5', depth=5, screw={"length": 8, "thread": 1}), 'unknown screw keys')

# Bought parts: each is its own whole bill-of-materials item, and expands into plain steps
_PARTS = {'nema_motor': dict(size='17', length=40), 'linear_rail': dict(series='MGN12', length=300),
          'rail_carriage': dict(series='MGN12'), 'lead_screw': dict(length=290), 'lead_nut': {},
          'pillow_block': {}, 'shaft_coupler': {}, 'spindle': {}}
for _op, _kw in _PARTS.items():
    assert _op in _ops and _op in llm.SYSTEM, _op
    _sh = shape_registry.get_shape(_op)
    _items = _sh.bom(dict(_kw, id='q', note='from seller A'))
    dsl_mod.check_bom(_items, _op)
    assert len(_items) == 1 and _items[0]['whole'] is True and _items[0]['note'] == 'from seller A', _op
    _x, _by, _ = _expand(_op, id='q', **_kw)
    assert _x['timeline'][-1]['id'] == 'q' and _x['timeline'][1]['mode'] == 'new_body', _op
    assert not any(shape_registry.get_shape(s['op']) for s in _x['timeline']), _op
    assert all(k.startswith('q_') for k in _x['parameters']), _op
    _fails(_shape(_op, id='bad id', **_kw), 'snake_case')
    _fails(_shape(_op, id='q', note=3, **_kw), 'note')

_m = _shape('nema_motor', id='m', size=17, length='motor_len')  # a number size works too
_m['parameters'] = {'motor_len': '48 mm'}
validate(_m)
assert dsl_mod.expand_shapes(_m)['parameters']['m_length'] == '(motor_len)'
_x, _by, (_v, _ev) = _expand('nema_motor', id='m', size='17', length=40)
assert _v['m_pitch'] == 31.0
assert _by['m_corners']['edges'] == 'vertical' and _by['m_corners']['distance'] == 'm_corner'
assert _by['m_socket_sk']['plane'] == 'xz' and _ev(_by['m_socket']['distance']) < _v['m_plug_out']
_plug_y = _ev(_by['m_plug_sk']['entities'][0]['center'][1])
assert abs(_plug_y + _ev(_by['m_plug_sk']['entities'][0]['height']) / 2 - (-42.3 / 2 + 1)) < 1e-9  # 1 mm into the body
assert {(_ev(c['center'][0]), _ev(c['center'][1])) for c in _by['m_hole_sk']['entities']} == \
    {(15.5, 15.5), (15.5, -15.5), (-15.5, 15.5), (-15.5, -15.5)}
_fails(_shape('nema_motor', id='m', size='19', length=40), 'size must be')
_fails(_shape('nema_motor', id='m', size='17', length=-40), 'length must be more than 0')
_x, _by, (_v, _ev) = _expand('linear_rail', id='r', series='MGN12', length=300)
assert _v['r_count'] == 12 and _v['r_start'] == 12.5                # holes centered: (300 - 11 x 25) / 2
assert _by['r']['op'] == 'linear_pattern' and _by['r']['quantity'] == 'r_count'
assert _by['r_sk']['plane'] == 'yz' and _by['r_bar']['distance'] == 'r_length'
assert _by['r_top_edge']['edges'] == {'feature': 'r_bar', 'type': 'line', 'direction': 'x', 'at': 'top'}
assert [_ev(e['center'][0]) for e in _by['r_groove_sk']['entities']] == [6, -6] and _by['r_grooves']['mode'] == 'cut'
_fails(_shape('linear_rail', id='r', series='MGN12', length=40), 'two hole pitches')
_fails(_shape('linear_rail', id='r', series='MGN20', length=300), 'series must be')
_x, _by, (_v, _ev) = _expand('rail_carriage', id='c', series='MGN12', block='C')
assert _v['c_length'] == 34.7 and _v['c_hole_c'] == 15 and _v['c_hole_depth'] == 4.0
assert _ev(_by['c_channel']['distance']) < _v['c_height'] - _v['c_gap']   # the channel leaves a top
assert _ev(_by['c_holes']['distance']) + _v['c_height'] - _v['c_rail_h'] > 0  # the holes stop above the rail
assert abs(_v['c_length'] - 2 * _v['c_cap'] - 21.7) < 1e-9          # MGN12C steel block: 21.7 mm
_nz = _ev(_by['c_nipple_sk']['entities'][0]['center'][1])
assert _v['c_rail_h'] + 0.2 < _nz - 1.5 and _nz + 1.5 < _v['c_height'] - 0.6  # the nipple sits on the end cap
assert shape_registry.get_shape('rail_carriage').bom({"id": "c", "series": "MGN9", "block": "C"})[0]['item'] == \
    'MGN9C carriage'
_scr = _bom({"parameters": {}, "timeline": [{"op": "lead_screw", "id": "s", "length": 290, "lead": 8}]})
assert ('Motion', 'T8 lead screw, lead 8 mm, 300 mm') in _scr        # rounded up to the stock length
assert ('Made', 'Main part') not in _scr
_fails(_shape('lead_screw', id='s', length=100, lead='fast'), 'lead must be')
_x, _by, (_v, _ev) = _expand('lead_nut', id='n', anti_backlash=False)
assert _v['n_length'] == 15 and _ev(_by['n_body_ext']['distance']) == -11.5
assert _by['n_end_edge']['edges']['feature'] == 'n_body_ext' and 'n_neck_ext' not in _by
_x, _by, (_v, _ev) = _expand('lead_nut', id='n')                    # anti-backlash: body, spring neck, second half
assert _ev(_by['n_half_sk']['offset']) + _ev(_by['n_end_ext']['distance']) == _v['n_flange_t'] - _v['n_length']
assert _v['n_neck'] < _v['n_body'] and _by['n_end_edge']['edges']['feature'] == 'n_end_ext'
_fails(_shape('lead_nut', id='n', anti_backlash='yes'), 'anti_backlash')
_x, _by, (_v, _ev) = _expand('pillow_block', id='k')
assert _by['k_housing_sk']['plane'] == 'xz' and _ev(_by['k_housing_sk']['offset']) == -6.5
assert _v['k_center_h'] + _v['k_housing'] / 2 == 29                  # KP08: 29 mm tall
assert _by['k_seal']['mode'] == 'cut' and _by['k_inner2']['mode'] == 'join' and _v['k_bore'] < _v['k_inner'] < _v['k_seal']
_fails(_shape('pillow_block', id='k', model='KP10'), 'model must be')
_x, _by, (_v, _ev) = _expand('shaft_coupler', id='cp', bore1=6.35, bore2=8)
assert _v['cp_bore1'] == 6.35 and _ev(_by['cp_bore2_cut']['distance']) == -12.5
for _k, _sign in ((0, 1), (1, -1), (2, 1)):                         # slots from alternating sides
    _sl = _by[f'cp_slot{_k}_sk']['entities'][0]
    _cx, _w = _ev(_sl['center'][0]), _ev(_sl['width'])
    _near = _cx - _sign * _w / 2                                     # the slot's end inside the coupler
    assert abs(_sign * _near - (2.5 - 19 / 2)) < 1e-9                # leaves a 2.5 mm bridge
assert _by['cp']['mode'] == 'cut' and len(_by['cp_screw_sk']['entities']) == 2
_fails(_shape('shaft_coupler', id='cp', bore2=20), 'smaller than the diameter')
_fails(_shape('shaft_coupler', id='cp', bore1='d'), 'bore1 must be')
_x, _by, (_v, _ev) = _expand('spindle', id='sp', diameter=65, collet='ER16')
assert _v['sp_diameter'] == 65 and _ev(_by['sp']['distance']) == 3
assert _ev(_by['sp_nut_sk']['offset']) + _ev(_by['sp_nut']['distance']) == -_v['sp_nose_len']  # the nose ends there
assert shape_registry.get_shape('spindle').bom({"id": "sp", "diameter": 65, "collet": "ER16"})[0]['item'] == \
    'ER16 DC spindle, 65 mm body'
_fails(_shape('spindle', id='sp', collet='ER32'), 'collet must be')


def _crosses(p, q, r, s):
    d = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return d(p, q, r) * d(p, q, s) < -1e-12 and d(r, s, p) * d(r, s, q) < -1e-12


def _sketch_loops(entities, ev):
    """What a sketch draws, numerically: its curves (mirror entities copying the curves they
    name, the way _mirror_curves does), chained into closed loops. Arcs become two chords through
    their middle point; circles 64-gons."""
    def P(q):
        return (ev(q[0]), ev(q[1]))
    ids, curves = {}, []
    for e in entities:
        t = e['type']
        if t == 'profile':
            cur, out = P(e['start']), []
            for sg in e['segments']:
                b = P(sg['to'])
                out.append([cur, P(sg['through']), b] if 'through' in sg else [cur, b])
                cur = b
            if e.get('closed', True) and math.dist(cur, P(e['start'])) > 1e-9:
                out.append([cur, P(e['start'])])
        elif t == 'circle':
            out = [('circle', P(e['center']), ev(e['diameter']) / 2)]
        elif t == 'center_rectangle':
            (cx, cy), w, h = P(e['center']), ev(e['width']) / 2, ev(e['height']) / 2
            c = [(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)]
            out = [[c[i], c[(i + 1) % 4]] for i in range(4)]
        else:  # mirror
            (ax, ay), (bx, by) = P(e['line'][0]), P(e['line'][1])
            dx, dy = bx - ax, by - ay

            def rf(p):
                f = ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)
                return (2 * (ax + f * dx) - p[0], 2 * (ay + f * dy) - p[1])

            def on(p):
                return abs((p[0] - ax) * dy - (p[1] - ay) * dx) / math.hypot(dx, dy) < 1e-9
            src = [c for r in e['entities'] for c in ids[r]]
            out = []
            for c in src:
                if c[0] == 'circle':
                    if not on(c[1]):
                        out.append(('circle', rf(c[1]), c[2]))
                elif not all(on(p) for p in c) and not (len(c) == 3 and on(c[1]) and math.dist(rf(c[0]), c[2]) < 1e-9):
                    out.append([rf(p) for p in c])
            curves += out
            if 'id' in e:
                ids[e['id']] = src + out
            continue
        curves += out
        if 'id' in e:
            ids[e['id']] = out
    loops, chains = [], []
    for c in curves:
        if c[0] == 'circle':
            loops.append([(c[1][0] + c[2] * math.cos(a * math.pi / 32), c[1][1] + c[2] * math.sin(a * math.pi / 32))
                          for a in range(64)])
        else:
            chains.append(c)

    def key(p):
        return round(p[0], 6), round(p[1], 6)
    ends = {}
    for i, c in enumerate(chains):
        for p in (c[0], c[-1]):
            ends.setdefault(key(p), []).append(i)
    assert all(len(v) == 2 for v in ends.values()), 'every point joins exactly two curves'
    used = set()
    for i in range(len(chains)):
        if i in used:
            continue
        used.add(i)
        pts = list(chains[i])
        while key(pts[-1]) != key(pts[0]):
            j = next(j for j in ends[key(pts[-1])] if j not in used)
            used.add(j)
            c = chains[j] if key(chains[j][0]) == key(pts[-1]) else chains[j][::-1]
            pts += c[1:]
        loops.append(pts[:-1])
    return loops


def _simple(pts):
    segs = list(zip(pts, pts[1:] + pts[:1]))
    return not any(_crosses(*segs[i], *segs[j]) for i in range(len(segs)) for j in range(i + 2, len(segs)))


def _inside(pt, pts):
    x, y, c = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def _has(pts, x, y):
    return any(abs(p[0] - x) < 1e-6 and abs(p[1] - y) < 1e-6 for p in pts)


# T-slot profiles: the sketch draws 1/8 (square) or 1/4 (2040 and longer) and mirrors it. Mirrored,
# it is one simple outline (counter-clockwise, the right size) with every bore, corner hole and
# hollow between cells inside it.
for _series, (_w, _h, _corner) in {'2020': (20, 20, 0), '2040': (20, 40, 0), '2060': (20, 60, 0),
                                   '3030': (30, 30, 4), '4040': (40, 40, 4), '4080': (40, 80, 4)}.items():
    _x, _by, (_v, _ev) = _expand('tslot_profile', id='t', series=_series, length=100)
    _ents = _by['t_sk']['entities']
    _drawn = [_ev(c) for e in _ents if e['type'] == 'profile' for sg in e['segments'] for c in sg['to']]
    assert all(x > -1e-9 for x in _drawn[0::2])                       # only right of the center line...
    if _w == _h:
        assert all(y <= -x + 1e-9 for x, y in zip(_drawn[0::2], _drawn[1::2]))  # ...and below the diagonal
        assert [e['type'] for e in _ents] == ['profile', 'mirror', 'mirror', 'mirror']
    else:
        assert all(y < 1e-9 for y in _drawn[1::2])                    # ...and below the middle
    _outs = _sketch_loops(_ents, _ev)
    assert len(_outs) == 1
    _out = _outs[0]
    assert _simple(_out)
    assert abs(max(p[0] for p in _out) * 2 - _w) < 1e-9 and abs(max(p[1] for p in _out) * 2 - _h) < 1e-9
    _segs = list(zip(_out, _out[1:] + _out[:1]))
    assert 0 < abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in _segs)) / 2 < _w * _h
    _cells = _h // _w
    _holes = _sketch_loops(_by['t_hole_sk']['entities'], _ev)
    assert len(_holes) == _cells + _corner + (_cells - 1)              # bores, corner holes, hollows
    for _hp in _holes:
        assert _simple(_hp) and all(_inside(p, _out) for p in _hp)

# The 2020 slot: 6.2 opening, 11 wide under the 1.8 lips, down to the 7.8 square core; 7.2 x 0.5 recess
_x, _by, (_v, _ev) = _expand('tslot_profile', id='t', series='2020', length=100)
_out = _sketch_loops(_by['t_sk']['entities'], _ev)[0]
for _sx in (-1, 1):
    assert _has(_out, _sx * 3.6, -10) and _has(_out, _sx * 3.6, -9.5) and _has(_out, _sx * 3.1, -9.5)
    assert _has(_out, _sx * 3.1, -8.2) and _has(_out, _sx * 5.5, -8.2)
    assert _has(_out, _sx * (3.9 - 1.5 * math.sqrt(0.5)), -3.9)   # where the spar meets the core
    assert _has(_out, -3.9, _sx * (3.9 - 1.5 * math.sqrt(0.5)))   # the same on the left slot
assert _has(_out, -10, 8.5) and _has(_out, -10 + 1.5 - 1.5 * math.sqrt(0.5), 10 - 1.5 + 1.5 * math.sqrt(0.5))
# The 4040's round core: the slot's floor runs over the core's edge, 12 mm in
_x, _by, (_v, _ev) = _expand('tslot_profile', id='t', series='4040', length=100)
_out = _sketch_loops(_by['t_sk']['entities'], _ev)[0]
assert _has(_out, 0, -8) and _has(_out, 8, 0) and _has(_out, 0, 8) and _has(_out, -8, 0)
_arcs = [sg for sg in _by['t_sk']['entities'][0]['segments'] if 'through' in sg]
for _sg in _arcs[:1]:                                                  # the floor's arc point is on the core
    assert abs(math.hypot(*[_ev(c) for c in _sg['through']]) - 8) < 1e-9
assert _by['t_hole_sk']['entities'][1]['type'] == 'center_rectangle'
# Overrides: no bore, no recess, square corners, moved
_x, _by, (_v, _ev) = _expand('tslot_profile', id='t', series='2020', length=50, center=[100, 0], bore=0,
                             slot=6.5, recess_width=0, fillet=0)
assert 't_hole_sk' not in _by and _x['parameters']['t_slot'] == '6.5 mm'
assert 't_recess_width' not in _x['parameters'] and 't_fillet' not in _x['parameters']
_out = _sketch_loops(_by['t_sk']['entities'], _ev)[0]
assert _has(_out, 90, -10) and _has(_out, 110, 10) and not any('through' in s for s in _by['t_sk']['entities'][0]['segments'])
_fails(_shape('tslot_profile', id='t', series='2030', length=50), 'series')
_fails(_shape('tslot_profile', id='t', series='2020', length=50, slot=12), 'slot < chamber')
_fails(_shape('tslot_profile', id='t', series='2020', length=50, lip=4), 'lip + 0.71 * spar')
_fails(_shape('tslot_profile', id='t', series='2020', length=50, core=1), '1.41 * spar < core')
_fails(_shape('tslot_profile', id='t', series='2020', length=50, bore=9), 'bore < core')
_fails(_shape('tslot_profile', id='t', series='2020', length=50, recess_depth=2), 'recess_depth < lip')
_fails(_shape('tslot_profile', id='t', series='2020', length=50, core_shape='oval'), 'core_shape')

# Test 6: Layer 2 Explicit constraints validation
dsl_with_constraints = {
    "parameters": {"len": "50 mm", "dia": "20 mm"},
    "timeline": [
        {
            "op": "sketch",
            "id": "sk_test",
            "plane": "xy",
            "entities": [
                {"type": "line", "id": "l1", "start": [0, 0], "end": ["len", 0]},
                {"type": "line", "id": "l2", "start": [0, 0], "end": [0, "len"]},
                {"type": "circle", "id": "c1", "center": [0, 0], "diameter": "dia"},
                {"type": "circle", "id": "c2", "center": [0, 0], "diameter": "dia / 2"}
            ],
            "constraints": [
                {"type": "perpendicular", "entities": ["l1", "l2"]},
                {"type": "concentric", "entities": ["c1", "c2"]},
                {"type": "equal", "entities": ["l1", "l2"]}
            ]
        }
    ]
}
validate(dsl_with_constraints)

# Test 7: Argument order tolerance in dsl.execute
class MockDesignForExec:
    class MockDT:
        ParametricDesignType = 1
    designType = 1
    userParameters = None
    unitsManager = None
    rootComponent = None

mock_fusion.DesignTypes = MockDesignForExec.MockDT

mock_des = MockDesignForExec()
mock_d = {'parameters': {}, 'timeline': []}
try:
    dsl.execute(mock_des, mock_d)
except Exception as e:
    # It passes validate(d) and proceeds to userParameters or designType without "DSL must be a JSON object"
    assert 'DSL must be a JSON object' not in str(e)

try:
    dsl.execute(mock_d, mock_des)
except Exception as e:
    assert 'DSL must be a JSON object' not in str(e)

# Test the add-in's worker thread hands provider + settings to llm.generate correctly.
# Loads VibeShaper.py as a package with a stub Fusion API and a fake provider.
import importlib
import tempfile


def _load_addin_with_stub_fusion(pkg_name='vibeshaper_addin', app_factory=None):
    fired = []
    fired_event = threading.Event()

    class _Stub:
        """Accepts any attribute access or call; also usable as a base class."""
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            return _Stub()

        def __call__(self, *a, **k):
            return _Stub()

    class _FakeApp(_Stub):
        def fireCustomEvent(self, event_id, info=''):
            fired.append((event_id, info))
            fired_event.set()

        def log(self, msg):
            pass

    fake_app = app_factory(_Stub) if app_factory else _FakeApp()
    stub_adsk = types.ModuleType('adsk')
    stub_core = types.ModuleType('adsk.core')
    stub_fusion = types.ModuleType('adsk.fusion')
    stub_core.__getattr__ = lambda name: _Stub
    stub_fusion.__getattr__ = lambda name: _Stub
    stub_core.Application = type('Application', (), {'get': staticmethod(lambda: fake_app)})
    stub_adsk.core, stub_adsk.fusion = stub_core, stub_fusion
    stub_adsk.doEvents = lambda: None

    saved = {k: sys.modules.get(k) for k in ('adsk', 'adsk.core', 'adsk.fusion')}
    sys.modules.update({'adsk': stub_adsk, 'adsk.core': stub_core, 'adsk.fusion': stub_fusion})
    try:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(here)]
        sys.modules[pkg_name] = pkg
        addin = importlib.import_module(pkg_name + '.VibeShaper')
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return addin, fired, fired_event, fake_app


addin, fired, fired_event, _ = _load_addin_with_stub_fusion()
tmp_log_dir = pathlib.Path(tempfile.mkdtemp())
addin.llm.LOG_FILE = tmp_log_dir / 'vibeshaper.log'
addin.llm.LAST_RESPONSE_FILE = tmp_log_dir / 'last_response.txt'

seen_by_provider = {}


class _WorkerFakeProvider(addin.providers.BaseProvider):
    id = 'worker_fake'
    name = 'Worker Fake'

    def generate(self, model, messages, values, options=None, on_chunk=None, stop_event=None, on_open=None, log=print):
        seen_by_provider.update(model=model, values=dict(values), think=options.think,
                                schema=options.response_schema is addin.dsl.JSON_SCHEMA)
        return json.dumps({'parameters': {}, 'timeline': [
            {'op': 'sketch', 'id': 's', 'plane': 'xy',
             'entities': [{'type': 'circle', 'center': [0, 0], 'diameter': 10}]}]})


addin.providers.register_provider(_WorkerFakeProvider())
addin._job.clear()
addin._job.update(provider_id='worker_fake', values={'token': 'k'}, model='m1', think=True,
                  messages=addin.llm.new_conversation('a disc'), builds=0, running=True)
addin._start_worker()
assert fired_event.wait(5), 'worker never fired a result event'
result_payloads = [json.loads(info) for eid, info in fired if eid == addin.EVENT_ID]
assert result_payloads, f'no result event fired: {fired}'
assert 'error' not in result_payloads[0], f'worker failed: {result_payloads[0]["error"]}'
assert result_payloads[0]['dsl']['timeline'][0]['op'] == 'sketch'
# The provider gets only its own values; think and the response format travel as options
assert seen_by_provider == {'model': 'm1', 'values': {'token': 'k'}, 'think': True, 'schema': True}, seen_by_provider

# ----- Settings file: the core owns the layout; providers only ever see their own values -----
SD = addin.providers.SettingDef


class _CfgA(addin.providers.BaseProvider):
    id, name, order = 'cfg_a', 'Cfg A', -20

    def get_settings_schema(self):
        return [SD('url', 'URL', 'string', 'http://a', required=True, refreshes_models=True),
                SD('retries', 'Retries', 'number', 1, minimum=0, maximum=5)]


class _CfgB(addin.providers.BaseProvider):
    id, name, short_name, order = 'cfg_b', 'Cfg B Cloud', 'Cfg B', -10

    def get_settings_schema(self):
        return [SD('token', 'Token', 'secret', '', required=True)]


addin.providers.register_provider(_CfgA())
addin.providers.register_provider(_CfgB())
addin.SETTINGS = tmp_log_dir / 'settings.json'
s = addin._load_settings()
assert s['version'] == addin.SETTINGS_VERSION == 1
assert s['general'] == {'theme': 'system', 'auto_fix': 2, 'default_mode': 'component'}, s['general']
assert s['selection'] == {'provider': 'cfg_a'}  # first provider by its own order
assert s['providers']['cfg_a'] == {'values': {'url': 'http://a', 'retries': 1}, 'model': '', 'model_options': {}}

# Picking a model from the main view sets the selected provider and its model, nothing else
addin._act_select_model({'provider': 'cfg_b', 'model': 'b-x'})
s = addin._load_settings()
assert s['selection'] == {'provider': 'cfg_b'} and s['providers']['cfg_b']['model'] == 'b-x'
addin._act_select_model({'provider': 'nope', 'model': 'm'})
assert addin._load_settings()['selection'] == {'provider': 'cfg_b'}

# Provider settings save the provider's declared values only (cleaned): never the model or the selection
addin._act_save_provider({'provider': 'cfg_a', 'values': {'url': 'http://h:1', 'retries': '9', 'model': 'evil', 'junk': 1}})
s = addin._load_settings()
assert s['providers']['cfg_a']['values'] == {'url': 'http://h:1', 'retries': 5}
assert s['providers']['cfg_a']['model'] == '' and s['selection'] == {'provider': 'cfg_b'}

# Think is a per-model choice the core keeps
addin._act_set_model_option({'provider': 'cfg_b', 'model': 'b-x', 'think': True})
assert addin._load_settings()['providers']['cfg_b']['model_options'] == {'b-x': {'think': True}}
addin._act_set_model_option({'provider': 'cfg_b', 'model': '', 'think': True})  # no model: ignored
assert addin._load_settings()['providers']['cfg_b']['model_options'] == {'b-x': {'think': True}}

# On disk: versioned, provider values kept apart from the core's own data
on_disk = json.loads(addin.SETTINGS.read_text())
assert on_disk['version'] == 1 and on_disk['providers']['cfg_b'] == \
    {'values': {'token': ''}, 'model': 'b-x', 'model_options': {'b-x': {'think': True}}}, on_disk

# General settings are validated
addin._act_save_general({'values': {'theme': 'dark', 'auto_fix': 9, 'bogus': 1, 'default_mode': 'new_body'}})
assert addin._load_settings()['general'] == {'theme': 'dark', 'auto_fix': 5, 'default_mode': 'new_body'}
addin._act_save_general({'values': {'theme': 'purple', 'auto_fix': -2, 'default_mode': 'join'}})  # unknown mode: ignored
assert addin._load_settings()['general'] == {'theme': 'dark', 'auto_fix': 0, 'default_mode': 'new_body'}

# A provider that isn't installed right now keeps its saved entry
on_disk['providers']['uninstalled'] = {'values': {'x': 1}, 'model': 'u', 'model_options': {}}
addin.SETTINGS.write_text(json.dumps(on_disk))
addin._act_save_general({'values': {'theme': 'light'}})
assert json.loads(addin.SETTINGS.read_text())['providers']['uninstalled']['model'] == 'u'

# A file in another layout version is not read (and not overwritten until something is saved)
addin.SETTINGS.write_text(json.dumps({'version': 99, 'selection': {'provider': 'cfg_b'}}))
assert addin._load_settings()['selection'] == {'provider': 'cfg_a'}
addin.SETTINGS.write_text(json.dumps({'active_provider': 'cfg_b', 'providers': {'cfg_b': {'model': 'z'}}}))
assert addin._load_settings()['providers']['cfg_b']['model'] == ''
assert json.loads(addin.SETTINGS.read_text())['active_provider'] == 'cfg_b'

# The panel gets each provider's form, values, readiness and the core's per-model choices
addin.SETTINGS.unlink()
addin._act_set_model_option({'provider': 'cfg_b', 'model': 'b-x', 'think': True})
addin._models_cache['cfg_b'] = [{'id': 'b-x', 'label': 'B X', 'images': True, 'thinking': True, 'tools': False}]
view = {p['id']: p for p in addin._providers_view()[0]}
assert view['cfg_a']['configured'] is True and view['cfg_b']['configured'] is False
assert view['cfg_b']['short_name'] == 'Cfg B' and view['cfg_a']['short_name'] == 'Cfg A'
assert view['cfg_a']['schema'][0] == {'key': 'url', 'label': 'URL', 'type': 'string', 'tooltip': '',
                                      'required': True, 'refreshes_models': True}
assert view['cfg_a']['schema'][1]['minimum'] == 0 and view['cfg_a']['schema'][1]['maximum'] == 5
assert view['cfg_b']['values'] == {'token': ''} and view['cfg_b']['model_options'] == {'b-x': {'think': True}}
assert view['cfg_b']['models'][0]['thinking'] is True
for pid in ('cfg_a', 'cfg_b'):
    addin.providers.unregister_provider(pid)
addin._models_cache.clear()

# Stop/Run reloads every provider module, not just the package: no stale plugin code survives
_plugin_mods = [n for n in sys.modules if n.startswith(addin.providers.__name__ + '.') and not n.endswith('.base')]
assert _plugin_mods, 'expected plugin modules to be loaded'
for _n in _plugin_mods:
    for _cls in vars(sys.modules[_n]).values():
        if isinstance(_cls, type) and issubclass(_cls, addin.providers.BaseProvider):
            _cls.short_name = 'STALE'
assert any(p.short_name == 'STALE' for p in addin.providers.get_all_providers())
addin._reload_providers()
assert not any(p.short_name == 'STALE' for p in addin.providers.get_all_providers())
assert addin.providers.get_all_providers()[0].__class__.__mro__[1] is addin.providers.BaseProvider
# ...and the same for tool plugins
for _k in addin.toolbox.get_all_toolkits():
    type(_k).prompt = 'STALE'
addin._reload_plugins(addin.toolbox)
assert addin.toolbox.get_all_toolkits() and not any(k.prompt == 'STALE' for k in addin.toolbox.get_all_toolkits())

# ----- User files live outside the add-in folder -----
import userdata
_home = pathlib.Path(os.environ['VIBESHAPER_HOME'])
assert addin.userdata.folder() == _home != here and llm.LOG_FILE.parent == _home
with unittest.mock.patch.dict(os.environ, {'VIBESHAPER_HOME': '', 'APPDATA': r'C:\U\AppData\Roaming'}), \
        unittest.mock.patch.object(userdata.sys, 'platform', 'win32'):
    assert userdata.folder() == pathlib.Path(r'C:\U\AppData\Roaming') / 'VibeShaper'
with unittest.mock.patch.dict(os.environ, {'VIBESHAPER_HOME': ''}), unittest.mock.patch.object(userdata.sys, 'platform', 'darwin'):
    assert userdata.folder() == pathlib.Path.home() / 'Library' / 'Application Support' / 'VibeShaper'
with unittest.mock.patch.dict(os.environ, {'VIBESHAPER_HOME': '', 'XDG_CONFIG_HOME': '/x'}),         unittest.mock.patch.object(userdata.sys, 'platform', 'linux'):
    assert userdata.folder() == pathlib.Path('/x') / 'vibeshaper'

# ----- Chat sessions -----
import chat as chat_mod

store = chat_mod.ChatStore()
c = store.ensure_active()
assert store.new_chat() is c  # an empty chat is reused, not duplicated

# First request: title comes from the prompt; history is user + final design only
u = c.add_user_turn('A 40 mm cube with a 10 mm hole through the middle and some extra words here')
assert c.title.startswith('A 40 mm cube') and len(c.title) <= chat_mod.TITLE_LEN
a = c.add_assistant_turn('model')
c.begin_model_request(u['text'], a)
assert c.model_messages('SYS')[0] == {'role': 'system', 'content': 'SYS'}
# Simulate a failed validation + self-heal inside the turn
c.messages.append({'role': 'assistant', 'content': 'bad'})
c.messages.append({'role': 'user', 'content': 'fix it'})
design_v1 = {'parameters': {'cube': '40 mm'}, 'timeline': [{'op': 'sketch'}]}
c.commit_model_success(a, design_v1)
assert [m['role'] for m in c.messages] == ['user', 'assistant']
assert json.loads(c.messages[-1]['content']) == design_v1
v1 = c.add_version(design_v1, 'model', group_name=c.group_name(1), param_map={'cube': 'cube'}, feature_count=2)
assert v1['n'] == 1 and c.current == 1

# Parameter edit is queued and folded into the next request, not sent on its own
c.set_param_in_current('cube', '50 mm')
assert c.current_dsl()['parameters']['cube'] == '50 mm'
assert c.pending_manual['parameters']['cube'] == '50 mm'
try:
    c.set_param_in_current('nope', '1 mm')
    assert False
except ValueError:
    pass
u2 = c.add_user_turn('make the hole bigger')
a2 = c.add_assistant_turn('model')
c.begin_model_request(u2['text'], a2)
assert c.pending_manual is None
assert c.messages[-1]['role'] == 'user'
assert '50 mm' in c.messages[-1]['content'] and c.messages[-1]['content'].endswith('make the hole bigger')

# A failed request is rolled back completely, restoring the queued manual change
c.rollback_model_request(a2)
assert [m['role'] for m in c.messages] == ['user', 'assistant']
assert c.pending_manual['parameters']['cube'] == '50 mm'

# Restore = new version built from an old design
v2 = c.add_version(design_v1, 'restore', group_name=c.group_name(2))
assert v2['n'] == 2 and c.current == 2 and v2['dsl'] == design_v1
# Parameter edits update the version they were made on (same build, new value)
assert c.version(1)['dsl']['parameters']['cube'] == '50 mm'

# Persistence round-trip; a turn left mid-flight comes back as stopped and rolled back
u3 = c.add_user_turn('add a chamfer')
a3 = c.add_assistant_turn('model')
c.begin_model_request(u3['text'], a3)
c2 = store.new_chat()
assert c2 is not c and store.active_id == c2.id
saved = store.to_json()
assert [x['id'] for x in json.loads(saved)['chats']] == [c.id]  # empty chats are not saved
loaded = chat_mod.ChatStore.from_json(saved)
lc = loaded.get(c.id)
assert lc and lc.current == 2 and len(lc.versions) == 2
assert lc.turn(a3['id'])['status'] == 'stopped'
assert [m['role'] for m in lc.messages] == ['user', 'assistant']
assert lc.pending_manual['parameters']['cube'] == '50 mm'
assert loaded.active() is lc  # active chat was empty, falls back to last saved chat
view = lc.to_view()
assert 'messages' not in view and not any(k.startswith('_') for t in view['turns'] for k in t)
assert chat_mod.ChatStore.from_json('not json').chats == []
assert chat_mod.make_title('{"name": "bottle_cap", "timeline": []}') == 'bottle cap'

# Deleting a chat removes it from the saved data; the newest remaining chat becomes active
ds = chat_mod.ChatStore.from_json(saved)
keep = ds.new_chat()
keep.add_user_turn('keep me')
ds.switch(c.id)
ds.delete(c.id)
assert ds.get(c.id) is None and ds.active() is keep and c.id not in ds.to_json()
other = ds.new_chat()
other.add_user_turn('other')
ds.switch(keep.id)
ds.delete(other.id)  # deleting another chat leaves the active one alone
assert ds.active() is keep
ds.delete(keep.id)
assert ds.active() is None and json.loads(ds.to_json())['chats'] == []
try:
    ds.delete('nope')
    raise AssertionError('deleting an unknown chat should fail')
except ValueError:
    pass
assert c.group_name(3).endswith(f'v3 [{c.id}]')

# Build mode ("target") is remembered per chat; None means "use the default from Settings"
nc = chat_mod.Chat()
assert nc.target == {'mode': None, 'occ': None}
nc.add_user_turn('x')
nc.target.update(mode='component', occ='occ-token')
rt = chat_mod.Chat.from_dict(json.loads(json.dumps(nc.to_dict())))
assert rt.target == nc.target and rt.to_view()['target'] == nc.target
# Chats saved before build modes existed were built as new bodies in the root: keep doing that
legacy = c.to_dict()
legacy.pop('target')
assert chat_mod.Chat.from_dict(legacy).target['mode'] == 'new_body'
legacy_empty = chat_mod.Chat().to_dict()
legacy_empty.pop('target')
assert chat_mod.Chat.from_dict(legacy_empty).target['mode'] is None
v = nc.add_version({'parameters': {}, 'timeline': []}, 'json', placement={'mode': 'component', 'label': 'Bracket'})
assert v['placement'] == {'mode': 'component', 'label': 'Bracket'}

# ----- Replacing a previous version (timeline group + parameters) -----
import dsl
from types import SimpleNamespace


class _TLItem:
    def __init__(self, index, parent=None, is_group=False, timeline=None):
        self.index, self.parentGroup, self.isGroup = index, parent, is_group
        self._tl = timeline
        self.entity = SimpleNamespace(deleteMe=self._delete_entity)
        self.refuse = False

    def _delete_entity(self):
        if self.refuse:
            raise RuntimeError('3 : could not delete')
        self._tl.items.remove(self)
        if self.parentGroup:
            self.parentGroup._items.remove(self)
        return True


class _TLGroup:
    def __init__(self, name, items, timeline):
        self.name, self._items, self._tl = name, items, timeline
        self.isGroup, self.parentGroup = True, None
        for it in items:
            it.parentGroup = self

    count = property(lambda self: len(self._items))

    def item(self, k):
        return self._items[k]

    isSuppressed = False
    refuse_delete = False  # real Fusion sometimes fails: "2 : InternalValidationError : res"

    def deleteMe(self, with_contents=True):
        if with_contents and self.refuse_delete:
            raise RuntimeError('2 : InternalValidationError : res')
        self._tl.groups.remove(self)
        if with_contents:
            for it in list(self._items):
                self._tl.items.remove(it)
        else:
            for it in self._items:
                it.parentGroup = None
        return True


class _Coll:
    def __init__(self, items):
        self._items = items

    count = property(lambda self: len(self._items))

    def item(self, k):
        return self._items[k]


class _Timeline:
    def __init__(self):
        self.items, self.groups = [], []
        self.moved_to_end = False

    def moveToEnd(self):
        self.moved_to_end = True

    count = property(lambda self: len(self.items))

    def item(self, k):
        return self.items[k]

    timelineGroups = property(lambda self: _Coll(self.groups))

    def add_group(self, name, n):
        start = len(self.items)
        its = [_TLItem(start + i, timeline=self) for i in range(n)]
        self.items.extend(its)
        g = _TLGroup(name, its, self)
        self.groups.append(g)
        return g

    def add_loose(self, n=1):
        for _ in range(n):
            self.items.append(_TLItem(len(self.items), timeline=self))


class _Param:
    def __init__(self, params, name, in_use=False):
        self._params, self.name, self.in_use = params, name, in_use

    def deleteMe(self):
        if self.in_use:
            return False
        del self._params[self.name]
        return True


class _Params:
    def __init__(self):
        self.d = {}

    def itemByName(self, name):
        return self.d.get(name)


class _Design:
    def __init__(self):
        self.timeline, self.userParameters = _Timeline(), _Params()


des = _Design()
des.timeline.add_group('VibeShaper · Cube · v1 [abc]', 3)
des.timeline.add_group('VibeShaper · Other part · v1 [zzz]', 2)
assert dsl.user_features_after(des, 'VibeShaper · Cube · v1 [abc]') == 0  # other VibeShaper parts don't count
des.timeline.add_loose(2)  # user's own features after it
assert dsl.user_features_after(des, 'VibeShaper · Cube · v1 [abc]') == 2
assert dsl.user_features_after(des, 'missing') == 0

for name, used in (('cube', False), ('hole', True)):
    des.userParameters.d[name] = _Param(des.userParameters.d, name, in_use=used)
assert dsl.delete_version(des, 'VibeShaper · Cube · v1 [abc]', ['cube', 'hole', 'gone']) == 'deleted'
assert [g.name for g in des.timeline.groups] == ['VibeShaper · Other part · v1 [zzz]']
assert des.timeline.count == 4
assert list(des.userParameters.d) == ['hole']  # in-use parameter is left alone
assert dsl.delete_version(des, 'VibeShaper · Cube · v1 [abc]', []) is False  # already gone: build fresh

# Fusion refuses to delete the whole group: delete its features one by one, newest first
des = _Design()
g = des.timeline.add_group('VibeShaper · Spring · v1 [s]', 3)
other = des.timeline.add_group('VibeShaper · Other · v1 [o]', 1)
g.refuse_delete = True
assert dsl.delete_version(des, 'VibeShaper · Spring · v1 [s]', []) == 'deleted'
assert des.timeline.moved_to_end
assert [x.name for x in des.timeline.groups] == ['VibeShaper · Other · v1 [o]'] and des.timeline.count == 1

# Nothing can be deleted: suppress the old version instead, so the new one can still be built
des = _Design()
g = des.timeline.add_group('VibeShaper · Spring · v1 [s]', 2)
g.refuse_delete = True
for it in g._items:
    it.refuse = True
assert dsl.delete_version(des, 'VibeShaper · Spring · v1 [s]', []) == 'suppressed'
assert g.isSuppressed is True

# Component copies a version placed are deleted by their tokens, if deleting its group left them
des = _Design()
des.timeline.add_group('VibeShaper · Rack · v1 [r]', 2)
_left = SimpleNamespace(isValid=True, gone=False)
_left.deleteMe = lambda: setattr(_left, 'gone', True) or True
des.findEntityByToken = lambda tok: [_left] if tok == 'occ1' else []
assert dsl.delete_version(des, 'VibeShaper · Rack · v1 [r]', [], ['occ1', 'occ_gone']) == 'deleted'
assert _left.gone

# ----- Where a build goes: the chat's own component -----
class _FComp:
    def __init__(self, design, name):
        self.design, self.name, self.occs = design, name, []
        self.occurrences = SimpleNamespace(addNewComponent=self.add_occ)

    def add_occ(self, matrix):
        comp = _FComp(self.design, f'Component{len(self.occs) + 1}')
        occ = SimpleNamespace(component=comp, isValid=True, objectType='adsk::fusion::Occurrence',
                              entityToken=f'tok{len(self.design.reg)}')
        self.design.reg[occ.entityToken] = occ
        self.occs.append(occ)
        return occ


class _FDesign(_Design):
    def __init__(self):
        super().__init__()
        self.reg = {}
        self.rootComponent = _FComp(self, 'root')

    def findEntityByToken(self, token):
        e = self.reg.get(token)
        return [e] if e is not None else []


sys.modules['adsk.core'].Matrix3D = SimpleNamespace(create=lambda: 'identity')
sys.modules['adsk.fusion'].DesignIntentTypes = SimpleNamespace(
    PartDesignIntentType=0, AssemblyDesignIntentType=1, HybridDesignIntentType=2)
fd = _FDesign()
fd.designIntent = 0  # Part Design document: one component only
assert dsl.supports_components(fd) is False
for intent in (1, 2):
    fd.designIntent = intent
    assert dsl.supports_components(fd) is True
del fd.designIntent  # older Fusion without design intents
assert dsl.supports_components(fd) is True
occ = dsl.ensure_component(fd, None, 'compression spring')
assert occ.component.name == 'compression spring' and len(fd.rootComponent.occs) == 1
assert dsl.ensure_component(fd, occ.entityToken, 'renamed') is occ  # reused, never renamed
occ.isValid = False  # the user deleted it: make a fresh one
occ2 = dsl.ensure_component(fd, occ.entityToken, 'spring')
assert occ2 is not occ and len(fd.rootComponent.occs) == 2


def _refuse(matrix):
    raise RuntimeError('3 : Failed to create component: Part Design documents can only contain one component, '
                       'please add this Part to an Assembly to add multiple components.')


fd.rootComponent.occurrences = SimpleNamespace(addNewComponent=_refuse)
try:
    dsl.ensure_component(fd, None, 'x')
    raise AssertionError('expected ComponentsNotAllowed')
except dsl.ComponentsNotAllowed:
    pass


# ----- End to end: the add-in's panel actions against a simulated Fusion -----
# Simulates: the design (timeline, parameters, attributes), the hidden build command with
# Fusion's roll-back-on-failure, custom events delivered on the "main thread", and the palette.
import queue
from types import SimpleNamespace


class _FParam:
    def __init__(self, params, name, expr):
        self._params, self.name, self.expression, self.unit = params, name, expr, 'mm'

    def deleteMe(self):
        del self._params[self.name]
        return True


class _Attrs:
    def __init__(self):
        self.d = {}

    def itemByName(self, group, name):
        return self.d.get((group, name))

    def add(self, group, name, value):
        self.d[(group, name)] = SimpleNamespace(value=value)


class _Harness:
    def __init__(self):
        self.events = queue.Queue()
        self.panel = []  # events sent to the palette
        self.builds = 0
        self.progress_bar = []  # Fusion's status-bar progress: covers the docked panel, so never used
        self.addin = None
        self.design = None

    def make_app(self, Stub):
        h = self

        class Design(Stub):
            def __init__(self):
                self.timeline, self.userParameters = _Timeline(), _Params()
                self.attributes = _Attrs()
                self.unitsManager = SimpleNamespace(isValidExpression=lambda e, u: any(ch.isdigit() for ch in e))
                self.reg = {}
                self.rootComponent = _FComp(self, 'root')

            findEntityByToken = _FDesign.findEntityByToken

        class Palette(Stub):
            def sendInfoToHTML(self, action, data):
                h.panel.append(json.loads(data))

        class CmdDef(Stub):
            def __init__(self, cid):
                self.cid = cid

            def execute(self):
                h.run_build()

        class UI(Stub):
            palettes = SimpleNamespace(itemById=lambda pid: Palette())
            progressBar = SimpleNamespace(showBusy=lambda *a: h.progress_bar.append(a), hide=lambda: None)
            commandDefinitions = SimpleNamespace(itemById=lambda cid: CmdDef(cid))

        class App(Stub):
            userInterface = UI()

            def fireCustomEvent(self, eid, info=''):
                h.events.put((eid, info))

            def log(self, msg):
                pass

        self.Design = Design
        app = App()
        app.activeProduct = None
        return app

    def run_build(self):
        """The hidden build command: a transaction Fusion rolls back if execute fails."""
        self.builds += 1
        tl, params = self.design.timeline, self.design.userParameters
        root = self.design.rootComponent
        snap = (list(tl.items), list(tl.groups), dict(params.d), list(root.occs), dict(self.design.reg))
        args = SimpleNamespace(executeFailed=False, executeFailedMessage='')
        self.addin._BuildExecute().notify(args)
        if args.executeFailed:
            tl.items[:], tl.groups[:] = snap[0], snap[1]
            params.d.clear()
            params.d.update(snap[2])
            root.occs[:] = snap[3]
            self.design.reg.clear()
            self.design.reg.update(snap[4])
            self.addin._BuildFailed().notify(args)

    def pump(self, until, timeout=5):
        """Deliver custom events on this (main) thread until `until()` is true."""
        a = self.addin
        handlers = {a.EVENT_ID: a._Result, a.PROGRESS_EVENT_ID: a._Progress,
                    a.SAVE_EVENT_ID: a._SaveLater, a.MODELS_EVENT_ID: a._ModelsReady,
                    a.TOOL_EVENT_ID: a._ToolRequest}
        end = time.time() + timeout
        while time.time() < end:
            try:
                eid, info = self.events.get(timeout=0.05)
                handlers[eid]().notify(SimpleNamespace(additionalInfo=info))
            except queue.Empty:
                pass
            if until():
                # drain whatever is already queued (e.g. deferred saves)
                while not self.events.empty():
                    eid, info = self.events.get()
                    handlers[eid]().notify(SimpleNamespace(additionalInfo=info))
                return
        raise AssertionError('timed out waiting for the add-in')

    def act(self, action, **data):
        self.addin.ACTIONS[action](data)

    def chat_view(self):
        views = [e for e in self.panel if e.get('type') in ('chat', 'state') and e.get('chat')]
        return views[-1]['chat']

    def last_ai(self):
        return [t for t in self.chat_view()['turns'] if t['role'] == 'assistant'][-1]

    def idle(self):
        return not self.addin._busy()


import time
H = _Harness()
e2e, _, _, e2e_app = _load_addin_with_stub_fusion('vibeshaper_e2e', H.make_app)
H.addin = e2e
H.design = H.Design()
e2e_app.activeProduct = H.design
e2e.importlib = SimpleNamespace(reload=lambda m: m)  # keep the fake dsl.execute below
e2e.llm.LOG_FILE = tmp_log_dir / 'e2e.log'
e2e.llm.LAST_RESPONSE_FILE = tmp_log_dir / 'e2e_last.txt'
E2E_GENERAL = {'auto_fix': 2}
E2E_OPTS = {}  # per-model choices (think) for the scripted provider's model
e2e._load_settings = lambda: {'version': 1, 'selection': {'provider': 'scripted'}, 'general': dict(E2E_GENERAL),
                              'providers': {'scripted': {'values': {}, 'model': 'm', 'model_options': dict(E2E_OPTS)}}}
e2e._save_settings = lambda s: None


BUILT_INTO = []  # component name (None = root) per execute


def _fake_execute(design, d, group_name='VibeShaper', comp=None, progress=None):
    BUILT_INTO.append(comp.name if comp else None)
    if progress:
        progress(0, len(d['timeline']), 'Creating parameters')
        progress(len(d['timeline']), len(d['timeline']), 'Done')
    if d.get('name') == 'bad':
        raise ValueError('timeline[1] (extrude): sketch has no closed profiles')
    for k, v in d['parameters'].items():
        assert k not in design.userParameters.d, f'parameter {k} still exists: old version not deleted first'
        design.userParameters.d[k] = _FParam(design.userParameters.d, k, v)
    design.timeline.add_group(group_name, len(d['timeline']))
    return {'group_name': group_name, 'param_map': {k: k for k in d['parameters']},
            'feature_count': len(d['timeline'])}


e2e.dsl.execute = _fake_execute


def _design_dsl(size, name='cube'):
    return {'name': name, 'parameters': {'cube_w': f'{size} mm'}, 'timeline': [
        {'op': 'sketch', 'id': 's', 'plane': 'xy',
         'entities': [{'type': 'center_rectangle', 'center': [0, 0], 'width': 'cube_w', 'height': 'cube_w'}]},
        {'op': 'extrude', 'sketch': 's', 'distance': 'cube_w', 'mode': 'new_body'}]}


class _ScriptedProvider(e2e.providers.BaseProvider):
    id = 'scripted'
    name = 'Scripted'
    replies = []
    seen = []
    opts = []

    def generate(self, model, messages, values, options=None, on_chunk=None, stop_event=None, on_open=None, log=print):
        self.seen.append([dict(m) for m in messages])
        self.opts.append(options)
        reply = self.replies.pop(0)
        if isinstance(reply, e2e.providers.Reply):
            return reply
        if reply == 'BLOCK':
            stop_event.wait(5)
            raise InterruptedError('stopped')
        if on_chunk:
            on_chunk('thought', 'pondering ')
            on_chunk('text', '{')
        return json.dumps(reply)


e2e.providers.register_provider(_ScriptedProvider())
SP = _ScriptedProvider
groups = lambda: [g.name for g in H.design.timeline.groups]

H.act('ready')
assert H.panel[-1]['type'] == 'state' and H.panel[-1]['chat']['turns'] == []

# 1. First prompt builds v1 in its own timeline group
SP.replies = [_design_dsl(40)]
H.act('send', text='a 40 mm cube')
H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'done' and t['version'] == 1 and t['replaced'] is None, t
assert 'pondering' in t['thought']
assert len(groups()) == 1 and groups()[0].startswith('VibeShaper · a 40 mm cube · v1')
assert H.design.userParameters.d['cube_w'].expression == '40 mm'
assert SP.seen[-1][0]['role'] == 'system' and SP.seen[-1][-1]['content'] == 'a 40 mm cube'
_prog = [e['progress'] for e in H.panel if e.get('type') == 'stream' and 'progress' in e and e['turn_id'] == t['id']]
assert _prog and _prog[-1] == {'done': 2, 'total': 2, 'label': 'Done'}  # the build's progress reached the panel

# 2. A follow-up replaces v1 (one group, old parameters deleted first) and the model sees the history
SP.replies = [_design_dsl(60)]
H.act('send', text='make it 60 mm')
H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'done' and t['version'] == 2 and t['replaced'] == 1, t
assert len(groups()) == 1 and ' v2 ' in groups()[0], groups()
assert H.design.userParameters.d['cube_w'].expression == '60 mm'
assert [m['role'] for m in SP.seen[-1]] == ['system', 'user', 'assistant', 'user']
assert json.loads(SP.seen[-1][2]['content'])['parameters']['cube_w'] == '40 mm'

# 3. A rebuild that keeps failing self-heals twice, then gives up; Fusion's rollback keeps v2
builds_before = H.builds
SP.replies = [_design_dsl(1, name='bad')] * 3
H.act('send', text='break it')
H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'error' and len(t['attempts']) == 2, t
assert 'no closed profiles' in t['error'].splitlines()[0]
assert H.builds - builds_before == 3  # default: 2 automatic fixes
assert len(groups()) == 1 and ' v2 ' in groups()[0], groups()
assert H.design.userParameters.d['cube_w'].expression == '60 mm'
store = e2e._store()
assert [m['role'] for m in store.active().messages] == ['user', 'assistant', 'user', 'assistant']  # failed turn rolled back

# 4. Retry the failed turn after the model behaves
SP.replies = [_design_dsl(70)]
H.act('retry', turn_id=t['id'])
H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'done' and t['version'] == 3 and t['replaced'] == 2 and t['attempts'] == [], t

# 5. User features after our group: ask first; "replace" keeps their features
H.design.timeline.add_loose(2)
SP.replies = [_design_dsl(80)]
H.act('send', text='80 mm please')
H.pump(lambda: H.last_ai()['status'] == 'confirm')
assert H.last_ai()['confirm'] == {'count': 2}
assert e2e._busy()
H.act('confirm_replace', turn_id=H.last_ai()['id'], choice='replace')
H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'done' and t['version'] == 4 and t['replaced'] == 3
assert len(groups()) == 1 and H.design.timeline.count == 2 + 2  # their 2 features + our 2

# 6. Parameter edit goes straight to Fusion, and the model hears about it on the next message
H.act('set_param', name='cube_w', expr='85 mm')
assert H.panel[-1] == {**H.panel[-1], 'type': 'param', 'name': 'cube_w', 'ok': True}
assert H.design.userParameters.d['cube_w'].expression == '85 mm'
H.act('set_param', name='cube_w', expr='lots')
assert H.panel[-1]['ok'] is False and 'valid' in H.panel[-1]['error']
assert H.design.userParameters.d['cube_w'].expression == '85 mm'

# 7. Undo in Fusion removed v4 and brought back v3: the next build replaces v3, not "nothing"
H.design.timeline.groups[0].name = H.design.timeline.groups[0].name.replace(' v4 ', ' v3 ')
SP.replies = [_design_dsl(90)]
H.act('send', text='90 mm')
H.pump(lambda: H.last_ai()['status'] in ('confirm', 'done', 'error'))
if H.last_ai()['status'] == 'confirm':
    H.act('confirm_replace', turn_id=H.last_ai()['id'], choice='replace')
    H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'done' and t['replaced'] == 3 and len(groups()) == 1, (t, groups())
assert 'I changed the design manually' in SP.seen[-1][-1]['content'] and '85 mm' in SP.seen[-1][-1]['content']

# 8. Restore an old version and apply edited JSON: both replace, no model call
calls = len(SP.seen)
H.act('restore_version', n=1)
H.pump(H.idle)
t = H.last_ai()
assert t['kind'] == 'restore' and t['restored_from'] == 1 and t['status'] == 'done'
assert H.design.userParameters.d['cube_w'].expression == '40 mm' and len(groups()) == 1
H.act('apply_json', text=json.dumps(_design_dsl(33)))
H.pump(H.idle)
assert H.last_ai()['kind'] == 'json' and H.design.userParameters.d['cube_w'].expression == '33 mm'
assert len(SP.seen) == calls and len(groups()) == 1
H.act('apply_json', text='{"timeline": []}')
assert H.panel[-1]['type'] == 'toast' and 'non-empty' in H.panel[-1]['text']

# 9. Stop while the model is thinking: turn marked stopped, request removed from history
msgs_before = len(e2e._store().active().messages)
SP.replies = ['BLOCK']
H.act('send', text='something slow')
assert e2e._busy()
H.act('stop')
assert not e2e._busy() and H.last_ai()['status'] == 'stopped'
assert len(e2e._store().active().messages) == msgs_before
H.pump(lambda: H.events.empty(), timeout=2)  # the worker's late "stopped" result is ignored
assert H.last_ai()['status'] == 'stopped'

# 10. Chats are saved in the design and come back after reopening it
H.pump(lambda: True)
saved_json = H.design.attributes.itemByName('VibeShaper', 'chats').value
reloaded = chat_mod.ChatStore.from_json(saved_json)
assert reloaded.active().title == 'a 40 mm cube' and len(reloaded.active().versions) == 7
assert 'api_key' not in saved_json
H.act('new_chat')
assert H.chat_view()['turns'] == []
H.act('ready')
st = H.panel[-1]
assert st['type'] == 'state' and len(st['chats']) == 1 and st['chats'][0]['versions'] == 7
H.act('switch_chat', id=st['chats'][0]['id'])
assert H.chat_view()['title'] == 'a 40 mm cube'

# 11. With automatic fixes turned off in Settings, the first failed build is final
E2E_GENERAL['auto_fix'] = 0
builds_before = H.builds
SP.replies = [_design_dsl(1, name='bad')]
H.act('send', text='break it again')
H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'error' and t['attempts'] == [] and H.builds - builds_before == 1, t
E2E_GENERAL['auto_fix'] = 2

# 12b. Removing the previous version fails for a reason the model can't fix: no self-healing
_real_delete = e2e.dsl.delete_version


def _broken_delete(design, group_name, param_names=(), occurrences=()):
    raise RuntimeError('2 : InternalValidationError : res')


e2e.dsl.delete_version = _broken_delete
calls_before = len(SP.seen)
builds_before = H.builds
SP.replies = [_design_dsl(90)]
H.act('send', text='make it 90 mm')
H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'error' and t['attempts'] == [], t
assert len(SP.seen) - calls_before == 1 and H.builds - builds_before == 1  # model asked once, built once
assert 'previous version' in t['error'].splitlines()[0], t['error']
e2e.dsl.delete_version = _real_delete

# 13. Build modes. New chats default to their own component, reused by every version.
def _ring(size):
    d = _design_dsl(size, name='spacer_ring')
    d['parameters'] = {'ring_w': f'{size} mm'}
    return d


H.act('new_chat')
BUILT_INTO.clear()
occs_before = len(H.design.rootComponent.occs)
SP.replies = [_ring(10), _ring(12)]
H.act('send', text='a spacer ring')
H.pump(H.idle)
assert H.last_ai()['status'] == 'done', H.last_ai()
H.act('send', text='a bit bigger')
H.pump(H.idle)
assert H.last_ai()['status'] == 'done' and H.last_ai()['replaced'] is not None, H.last_ai()
assert BUILT_INTO == ['spacer ring', 'spacer ring'], BUILT_INTO
occs = H.design.rootComponent.occs
assert len(occs) == occs_before + 1 and H.chat_view()['target']['occ'] == occs[-1].entityToken
v = H.chat_view()['versions'][-1]
assert v['placement'] == {'mode': 'component', 'label': 'spacer ring'}, v

# New body: built in the root component
H.act('set_target', mode='new_body')
assert H.chat_view()['target']['mode'] == 'new_body'
SP.replies = [_ring(14)]
H.act('send', text='bigger again')
H.pump(H.idle)
assert BUILT_INTO[-1] is None and H.chat_view()['versions'][-1]['placement']['mode'] == 'new_body'

# Back to component mode: the chat's existing component is reused, not a new one
H.act('set_target', mode='component')
SP.replies = [_ring(16)]
H.act('send', text='back into its component')
H.pump(H.idle)
assert H.last_ai()['status'] == 'done', H.last_ai()
assert BUILT_INTO[-1] == 'spacer ring' and len(H.design.rootComponent.occs) == occs_before + 1
H.act('set_target', mode='join')  # unknown modes are ignored
assert H.chat_view()['target']['mode'] == 'component'

# Part Design documents hold one component: build as new bodies, tell the panel the option is unavailable
H.design.designIntent = 0
H.act('ready')
assert [e for e in H.panel if e['type'] == 'state'][-1]['components'] is False
occs_now = len(H.design.rootComponent.occs)
SP.replies = [_ring(20)]
H.act('send', text='in a part document')
H.pump(H.idle)
assert H.last_ai()['status'] == 'done', H.last_ai()
assert BUILT_INTO[-1] is None and len(H.design.rootComponent.occs) == occs_now
assert H.chat_view()['versions'][-1]['placement']['mode'] == 'new_body'
assert H.chat_view()['target']['mode'] == 'component'  # the chat's choice is kept for assembly documents
del H.design.designIntent

# Progress is shown in the panel only; Fusion's own progress bar would sit on top of it
assert H.progress_bar == [], H.progress_bar

# 12. Saving a provider's settings tells the panel whether it is ready to use
_e2e_saved = {}
e2e._save_settings = lambda s: _e2e_saved.update(s)
H.act('save_provider', provider='scripted', values={})
assert H.panel[-1] == {'type': 'provider_status', 'provider': 'scripted', 'configured': True}, H.panel[-1]
st = [e for e in H.panel if e['type'] == 'state'][-1]
assert st['general'] == {'theme': 'system', 'auto_fix': 2, 'default_mode': 'component'}
assert {p['id']: p['configured'] for p in st['providers']}['scripted'] is True

# 14. Think is sent only to models that report they can think; unknown models get the user's choice
E2E_OPTS['m'] = {'think': True}
H.act('new_chat')
_think_dsl = {'parameters': {'think_w': '12 mm'}, 'timeline': [{'op': 'sketch', 'id': 's', 'plane': 'xy', 'entities': [{'type': 'circle', 'center': [0, 0], 'diameter': 'think_w'}]}]}
for caps, expect in (({'thinking': False}, False), ({'thinking': True}, True), (None, True)):
    if caps is None:
        e2e._models_cache.pop('scripted', None)
    else:
        e2e._models_cache['scripted'] = [dict({'id': 'm', 'label': 'm', 'images': False, 'tools': False}, **caps)]
    SP.replies = [_think_dsl]
    H.act('send', text='again')
    H.pump(H.idle)
    assert H.last_ai()['status'] == 'done', H.last_ai()
    assert SP.opts[-1].think is expect, (caps, SP.opts[-1])
E2E_OPTS.clear()
e2e._models_cache.clear()

# 15. A model that can use tools looks at the design first; the panel shows what it looked at,
#     and the saved chat keeps only the request and the final design
_caps = lambda tools: [{'id': 'm', 'label': 'm', 'images': False, 'thinking': False, 'tools': tools}]
e2e._models_cache['scripted'] = _caps(True)
H.act('new_chat')
_lid = {'parameters': {'lid_w': '30 mm'}, 'timeline': [{'op': 'sketch', 'id': 's', 'plane': 'xy',
        'entities': [{'type': 'circle', 'center': [0, 0], 'diameter': 'lid_w'}]}]}
SP.replies = [e2e.providers.Reply('Checking what you selected.', [e2e.providers.ToolCall('t1', 'get_selection', {})]), _lid]
SP.seen.clear()
SP.opts.clear()
H.act('send', text='a lid for the selected box')
H.pump(H.idle)
t = H.last_ai()
assert t['status'] == 'done', t
assert t['tools'] == [{'name': 'get_selection', 'label': 'Checked your selection'}], t.get('tools')
assert any(e.get('tool') for e in H.panel if e.get('type') == 'stream')
assert SP.opts[0].tools is not None and 'get_overview' in [x.name for x in SP.opts[0].tools]
assert 'get_overview' in SP.seen[0][0]['content']  # the toolkit's note is in the system prompt
assert SP.seen[1][-1]['role'] == 'tool' and json.loads(SP.seen[1][-1]['content'])['total'] == 0
_c = e2e._store().active()
assert [m['role'] for m in _c.messages] == ['user', 'assistant'] and 'tool_calls' not in _c.messages[-1]
assert 'design' in e2e._store().tool_state  # each toolkit's state is kept with the document
assert 'tool_state' in json.loads(e2e._store().to_json())

# 15b. A toolkit that needs images is offered only to models that can see them
class _NeedsEyes(e2e.toolbox.BaseToolkit):
    id, needs = 'zz_eyes', ('images',)

    def tools(self):
        return [{'name': 'zz_look', 'description': 'Look.', 'parameters': {'type': 'object', 'properties': {}}}]


e2e.toolbox.register_toolkit(_NeedsEyes())
for _imgs in (False, True):
    e2e._models_cache['scripted'] = [dict(_caps(True)[0], images=_imgs)]
    SP.replies = [dict(_lid, parameters={'lid_w': f'{31 + _imgs} mm'})]
    SP.opts.clear()
    H.act('send', text='again')
    H.pump(H.idle)
    assert ('zz_look' in [x.name for x in SP.opts[0].tools]) == _imgs
e2e.toolbox.unregister_toolkit('zz_eyes')
e2e._models_cache['scripted'] = _caps(True)

# 16. A model without tools gets a picture of the design with its request (only for that request)
e2e._models_cache['scripted'] = _caps(False)
_real_summary = e2e._design_summary
e2e._design_summary = lambda kits: 'SUMMARY-OF-DESIGN' if any(k.id == 'design' for k in kits) else ''
SP.replies = [dict(_lid, parameters={'lid_w': '32 mm'})]
SP.seen.clear()
SP.opts.clear()
H.act('send', text='a bit wider')
H.pump(H.idle)
assert H.last_ai()['status'] == 'done', H.last_ai()
assert SP.opts[0].tools is None and 'get_overview' not in SP.seen[0][0]['content']
assert SP.seen[0][-1]['content'].startswith('a bit wider') and SP.seen[0][-1]['content'].endswith('SUMMARY-OF-DESIGN')
assert _c.messages[-2] == {'role': 'user', 'content': 'a bit wider'}  # not saved into the chat
e2e._design_summary = _real_summary
assert e2e._design_summary(e2e.toolbox.get_all_toolkits()) == ''  # nothing to tell about the stub design
e2e._models_cache.clear()


# 17. Deleting a chat removes the conversation from the design but leaves its geometry alone
_deleted_versions = []
_real_delete_version = e2e.dsl.delete_version
e2e.dsl.delete_version = lambda *a, **k: _deleted_versions.append(a)
H.act('ready')
_chats = H.panel[-1]['chats']
assert len(_chats) >= 2
_gone, _shown = _chats[0]['id'], H.chat_view()['id']
e2e._job['active'] = True  # not while something is running
H.act('delete_chat', id=_gone)
e2e._job['active'] = False
assert H.panel[-1]['type'] == 'toast' and e2e._store().get(_gone)
H.act('delete_chat', id=_gone)
H.pump(lambda: True)
assert e2e._store().get(_gone) is None and _deleted_versions == []
_last_chat = [e for e in H.panel if e.get('type') == 'chat'][-1]
assert _gone not in [x['id'] for x in _last_chat['chats']]
assert {'type': 'toast', 'text': 'Chat deleted'} in H.panel[-3:]
assert _gone not in H.design.attributes.itemByName('VibeShaper', 'chats').value
assert H.chat_view()['id'] == (_shown if _shown != _gone else e2e._store().active().id)
H.act('delete_chat', id='no-such-chat')  # nothing happens
e2e.dsl.delete_version = _real_delete_version

# 18. Assemblies: a parameter that moves copies rebuilds the design (Fusion wouldn't move them);
# any other parameter goes straight to Fusion as before
H.act('new_chat')
_asm = {'name': 'table', 'parameters': {'tbl_leg': '40 mm', 'tbl_x': '100 mm'}, 'timeline': [], 'components': [
    {'id': 'leg', 'timeline': [
        {'op': 'sketch', 'id': 's', 'plane': 'xy',
         'entities': [{'type': 'center_rectangle', 'center': [0, 0], 'width': 'tbl_leg', 'height': 'tbl_leg'}]},
        {'op': 'extrude', 'sketch': 's', 'distance': 'tbl_leg', 'mode': 'new_body'}]}],
    'instances': [{'component': 'leg', 'position': ['tbl_x', 0, 0]}, {'component': 'leg', 'position': ['-tbl_x', 0, 0]}]}
H.act('send', text=json.dumps(_asm))
H.pump(H.idle)
_c = e2e._store().active()
assert H.last_ai()['status'] == 'done' and _c.current_version()['n'] == 1, H.last_ai()
H.act('set_param', name='tbl_leg', expr='45 mm')
H.pump(H.idle)
assert H.panel[-1]['ok'] is True and _c.current_version()['n'] == 1     # only the leg's size: no rebuild
_v1_group = _c.current_version()['group_name']
H.act('set_param', name='tbl_x', expr='120 mm')
H.pump(H.idle)
assert _c.current_version()['n'] == 2 and H.last_ai()['status'] == 'done', H.last_ai()
assert _c.current_version()['dsl']['parameters'] == {'tbl_leg': '45 mm', 'tbl_x': '120 mm'}
assert H.design.userParameters.d['tbl_x'].expression == '120 mm'
assert _v1_group not in [g.name for g in H.design.timeline.groups]  # v1 replaced

# 19. Feature & sketch entity plugins: core stays plugin-neutral and dynamic registration updates
# JSON_SCHEMA (preserving object identity) and llm.SYSTEM / llm.system_prompt() live.
import features as _feat_reg
import features.entities as _ent_reg

_all_feats = _feat_reg.get_all_features()
_feat_ops = [f.op for f in _all_feats]
assert len(_feat_ops) == 13
assert [(f.order, f.op) for f in _all_feats] == sorted((f.order, f.op) for f in _all_feats)

_all_ents = _ent_reg.get_all_entities()
_ent_types = [e.type for e in _all_ents]
assert len(_ent_types) == 8
assert [(e.order, e.type) for e in _all_ents] == sorted((e.order, e.type) for e in _all_ents)

for _f in ('dsl.py', 'VibeShaper.py', 'bom.py', 'chat.py', 'userdata.py',
           'features/__init__.py', 'features/base.py', 'features/entities/__init__.py',
           'features/entities/base.py', 'shapes/__init__.py', 'shapes/base.py', 'shapes/_json.py'):
    _src = (_HERE / _f).read_text(encoding='utf-8')
    for _op in _feat_ops:
        assert f"'{_op}'" not in _src and f'"{_op}"' not in _src, f'{_f} hardcodes feature op {_op!r}'
for _f in ('dsl.py', 'VibeShaper.py', 'bom.py', 'chat.py', 'userdata.py',
           'features/__init__.py', 'features/base.py', 'features/sketch.py',
           'features/entities/__init__.py', 'features/entities/base.py',
           'shapes/__init__.py', 'shapes/base.py', 'shapes/_json.py'):
    _src = (_HERE / _f).read_text(encoding='utf-8')
    for _et in _ent_types:
        assert f"'{_et}'" not in _src and f'"{_et}"' not in _src, f'{_f} hardcodes entity type {_et!r}'

_orig_schema_id = id(dsl_mod.JSON_SCHEMA)
_orig_tl_id = id(dsl_mod.JSON_SCHEMA['properties']['timeline'])

class _DummyFeature(_feat_reg.BaseFeature):
    op = 'zz_loft'
    name = 'ZZ Loft'
    order = 999
    prompt = 'ZZ Loft: {"op": "zz_loft", "zz_rail": "rail_id"}'
    rules = '- Prefer zz_loft for smooth custom lofts.'
    schema = {'zz_rail': {'type': 'string'}}

    def pattern_copies(self, step, fid, ev):
        return 3 if step.get('feature') == fid else 1

_feat_reg.register_feature(_DummyFeature())
try:
    assert id(dsl_mod.JSON_SCHEMA) == _orig_schema_id
    assert id(dsl_mod.JSON_SCHEMA['properties']['timeline']) == _orig_tl_id
    assert dsl_mod.JSON_SCHEMA['properties']['components']['items']['properties']['timeline'] is dsl_mod.JSON_SCHEMA['properties']['timeline']
    _tl_props = dsl_mod.JSON_SCHEMA['properties']['timeline']['items']['properties']
    assert 'zz_loft' in _tl_props['op']['enum'] and 'zz_rail' in _tl_props
    assert 'zz_loft' in llm.SYSTEM and 'Prefer zz_loft' in llm.SYSTEM
    assert 'zz_loft' in llm.system_prompt()
    validate({'parameters': {}, 'timeline': [{'op': 'zz_loft', 'zz_rail': 'r1'}]})
    _custom_bom = bom_mod.collect({'parameters': {}, 'timeline': [
        {'op': 'nema_motor', 'id': 'mot1', 'size': 17, 'length': 40},
        {'op': 'zz_loft', 'feature': 'mot1'},
    ]})
    assert [r for r in _custom_bom if 'NEMA' in r['Item']][0]['Qty'] == 3
finally:
    _feat_reg.unregister_feature('zz_loft')

_tl_props_after = dsl_mod.JSON_SCHEMA['properties']['timeline']['items']['properties']
assert 'zz_loft' not in _tl_props_after['op']['enum'] and 'zz_rail' not in _tl_props_after
assert 'zz_loft' not in llm.SYSTEM

_drawn_custom = []
class _DummyEntity(_ent_reg.BaseEntity):
    type = 'zz_oval'
    name = 'ZZ Oval'
    order = 999
    required = ('zz_major',)
    prompt = '{"type": "zz_oval", "zz_major": d}'
    schema = {'zz_major': {'type': ['string', 'number']}}

    def draw(self, sk, entity, ctx):
        _drawn_custom.append(entity['zz_major'])
        ctx.register(entity, ['oval'])

_ent_reg.register_entity(_DummyEntity())
try:
    assert id(dsl_mod.JSON_SCHEMA) == _orig_schema_id
    _ent_props = dsl_mod.JSON_SCHEMA['properties']['timeline']['items']['properties']['entities']['items']['properties']
    assert 'zz_oval' in _ent_props['type']['enum'] and 'zz_major' in _ent_props
    assert 'zz_oval' in llm.SYSTEM and 'zz_oval' in llm.system_prompt()
    validate({'parameters': {}, 'timeline': [{'op': 'sketch', 'id': 's', 'plane': 'xy',
                                              'entities': [{'type': 'zz_oval', 'zz_major': 12}]}]})
    _ent_map = {}
    _ent_reg.draw(MockSketchObj(), {'type': 'zz_oval', 'id': 'ov', 'zz_major': '10 mm'},
                  dummy_ex, dummy_cm, dummy_pt, _ent_map)
    assert _drawn_custom == ['10 mm'] and _ent_map['ov'] == ['oval']
finally:
    _ent_reg.unregister_entity('zz_oval')

_ent_props_after = dsl_mod.JSON_SCHEMA['properties']['timeline']['items']['properties']['entities']['items']['properties']
assert 'zz_oval' not in _ent_props_after['type']['enum'] and 'zz_major' not in _ent_props_after
assert 'zz_oval' not in llm.SYSTEM

# ----- Declarative .json shape macros + reload -----
for _jop in ('nema_motor', 'pillow_block', 'spindle', 'lead_screw'):
    assert isinstance(shape_registry.get_shape(_jop), shape_registry.JsonShape), _jop
assert isinstance(shape_registry.get_shape('lead_nut'), shape_registry.BaseShape)
assert not isinstance(shape_registry.get_shape('lead_nut'), shape_registry.JsonShape)

# A plain single-part design JSON becomes a parametric shape by adding "op" and "prompt",
# with auto-prefixed parameters/IDs, preserved sketch-local entity IDs, caller overrides, and nested shapes.
_macro_design = {
    'op': 'zz_bracket',
    'name': 'ZZ Bracket',
    'order': 999,
    'prompt': ['{"op": "zz_bracket", "id": name}  A bracket with mirrored mounting tabs and nested bolt holes.'],
    'parameters': {'inner_w': '20 mm', 'wall': '4 mm', 'outer_w': 'inner_w + 2 * wall', 'holes_n': 2},
    'timeline': [
        {'op': 'sketch', 'id': 'sk', 'plane': 'xy', 'entities': [
            {'type': 'center_rectangle', 'center': [0, 0], 'width': 'outer_w', 'height': 'wall * 5'},
            {'type': 'circle', 'id': 'tab_hole', 'center': ['outer_w / 2 - wall', 0], 'diameter': '3 mm'},
            {'type': 'mirror', 'entities': ['tab_hole'], 'line': [[0, 0], [0, 1]]},
        ]},
        {'op': 'extrude', 'id': 'pad', 'sketch': 'sk', 'distance': 'wall', 'mode': 'new_body'},
        {'op': 'bolt_hole', 'id': 'bh', 'size': 'M5', 'depth': 'wall', 'center': ['-inner_w / 4', 0],
         'screw': {'length': 12}},
        {'op': 'linear_pattern', 'id': 'fin', 'feature': 'bh', 'axis': 'x', 'quantity': 'holes_n', 'distance': '10 mm'},
    ],
}
with tempfile.TemporaryDirectory() as _jdir:
    _jpath = pathlib.Path(_jdir) / 'zz_bracket.json'
    _jpath.write_text(json.dumps(_macro_design), encoding='utf-8')
    _jshape = shape_registry.load_json_shape(_jpath)
shape_registry.register_shape(_jshape)
try:
    _jprops = dsl_mod.JSON_SCHEMA['properties']['timeline']['items']['properties']
    assert 'zz_bracket' in _jprops['op']['enum'] and 'inner_w' in _jprops and 'holes_n' in _jprops
    assert 'zz_bracket' in llm.SYSTEM
    _jd = {'parameters': {'custom_w': '30 mm'}, 'timeline': [
        {'op': 'zz_bracket', 'id': 'b1', 'inner_w': 'custom_w'},
        {'op': 'linear_pattern', 'feature': 'b1', 'axis': 'y', 'quantity': 3, 'distance': '40 mm'},
    ]}
    validate(_jd)
    _jx = dsl_mod.expand_shapes(_jd)
    assert not any(shape_registry.get_shape(s['op']) for s in _jx['timeline'])
    assert _jx['parameters']['b1_inner_w'] == '(custom_w)'
    assert _jx['parameters']['b1_outer_w'] == 'b1_inner_w + 2 * b1_wall'
    assert _jx['parameters']['b1_holes_n'] == 2
    _jby = {s.get('id'): s for s in _jx['timeline']}
    assert _jby['b1_sk']['entities'][1]['id'] == 'tab_hole'
    assert _jby['b1_sk']['entities'][2]['entities'] == ['tab_hole']
    _jv, _jev = _eval_params(_jx['parameters'])
    assert len(_sketch_loops(_jby['b1_sk']['entities'], _jev)) == 3  # rectangle + mirrored pair of circles
    assert abs(_jv['b1_outer_w'] - 38.0) < 1e-9  # 30 + 2 * 4
    assert _jby['b1_pad']['id'] == 'b1_pad' and _jby['b1']['op'] == 'linear_pattern'
    assert _jby['b1_bh']['mode'] == 'cut' and 'b1_bh_sk' in _jby
    _jbom = _bom(_jd)
    assert ('Made', 'Main part') in _jbom
    assert _jbom[('Fasteners', 'M5x12 socket head cap screw (ISO 4762)')]['Qty'] == 6  # 2 internal x 3 outer copies
finally:
    shape_registry.unregister_shape('zz_bracket')
assert 'zz_bracket' not in dsl_mod.JSON_SCHEMA['properties']['timeline']['items']['properties']['op']['enum']
assert 'zz_bracket' not in llm.SYSTEM

# Cyclic .json shapes are rejected rather than looping indefinitely
_cyc_a = shape_registry.JsonShape({'op': 'zz_cyc_a', 'timeline': [{'op': 'zz_cyc_b', 'id': 'x'}]})
_cyc_b = shape_registry.JsonShape({'op': 'zz_cyc_b', 'timeline': [{'op': 'zz_cyc_a', 'id': 'y'}]})
shape_registry.register_shape(_cyc_a)
shape_registry.register_shape(_cyc_b)
try:
    _fails({'parameters': {}, 'timeline': [{'op': 'zz_cyc_a', 'id': 'top'}]}, 'maximum depth')
finally:
    shape_registry.unregister_shape('zz_cyc_a')
    shape_registry.unregister_shape('zz_cyc_b')

_before_ops = [s.op for s in shape_registry.get_all_shapes()]
shape_registry = importlib.reload(shape_registry)
assert [s.op for s in shape_registry.get_all_shapes()] == _before_ops

# ----- Per-component sibling timeline groups + reverse-order collapsing -----
class _SlotItem:
    def __init__(self, tag, timeline):
        self.tag, self._tl = tag, timeline
        self.isGroup, self.parentGroup = False, None
        self.index = -1
        self.refuse = False
        self.entity = SimpleNamespace(deleteMe=self._delete_entity)

    def _delete_entity(self):
        if self.refuse:
            raise RuntimeError('3 : could not delete')
        if self in self._tl.slots:
            self._tl.slots.remove(self)
        if self.parentGroup and self in self.parentGroup._items:
            self.parentGroup._items.remove(self)
        self._tl._reindex()
        return True


class _SlotGroup:
    def __init__(self, name, items, timeline):
        self.name, self._items, self._tl = name, list(items), timeline
        self.isGroup, self.parentGroup = True, None
        self.isCollapsed, self.isSuppressed, self.refuse_delete = False, False, False
        self.index = -1
        for it in self._items:
            it.parentGroup = self
            it.index = -1

    count = property(lambda self: len(self._items))

    def item(self, k):
        return self._items[k]

    def deleteMe(self, with_contents=True):
        if with_contents and self.refuse_delete:
            raise RuntimeError('2 : InternalValidationError : res')
        self._tl.deleted_order.append(self.name)
        if self in self._tl.groups:
            self._tl.groups.remove(self)
        if self in self._tl.slots:
            self._tl.slots.remove(self)
        if with_contents:
            self._items.clear()
        else:
            for it in self._items:
                it.parentGroup = None
        self._tl._reindex()
        return True


class _SlotGroupsColl:
    def __init__(self, tl):
        self._tl = tl

    count = property(lambda self: len(self._tl.groups))

    def item(self, k):
        return self._tl.groups[k]

    def add(self, start_idx, end_idx):
        slots = self._tl.slots
        # Real Fusion rejects invalid ranges, single items (sometimes), and nested groups
        if start_idx < 0 or end_idx >= len(slots) or start_idx >= end_idx:
            raise RuntimeError(f'bad group range {start_idx}..{end_idx}')
        span = slots[start_idx:end_idx + 1]
        if any(it.isGroup for it in span):
            raise RuntimeError('nested timeline group')
        g = _SlotGroup('', span, self._tl)
        slots[start_idx:end_idx + 1] = [g]
        self._tl.groups.append(g)
        self._tl._reindex()
        return g


class _SlotTimeline:
    def __init__(self):
        self.slots, self.groups, self.deleted_order = [], [], []
        self.moved_to_end = False

    count = property(lambda self: len(self.slots))
    markerPosition = property(lambda self: len(self.slots))
    timelineGroups = property(lambda self: _SlotGroupsColl(self))

    def item(self, k):
        return self.slots[k]

    def moveToEnd(self):
        self.moved_to_end = True

    def _reindex(self):
        for i, s in enumerate(self.slots):
            s.index = i

    def append_item(self, tag):
        it = _SlotItem(tag, self)
        self.slots.append(it)
        self._reindex()
        return it


class _SlotParams:
    def __init__(self):
        self.d = {}

    count = property(lambda self: len(self.d))

    def item(self, k):
        return list(self.d.values())[k]

    def itemByName(self, name):
        return self.d.get(name)

    def add(self, name, val, unit, comment):
        p = SimpleNamespace(name=name, expression=val, unit=unit)
        p.deleteMe = lambda: (self.d.pop(name, None) is not None)
        self.d[name] = p
        return p


class _SlotComp:
    xYConstructionPlane = 'xy'
    xZConstructionPlane = 'xz'
    yZConstructionPlane = 'yz'
    xConstructionAxis = 'x'
    yConstructionAxis = 'y'
    zConstructionAxis = 'z'

    def __init__(self, design, name):
        self._design, self.name = design, name
        self.occurrences = SimpleNamespace(
            addNewComponent=self._add_new,
            addExistingComponent=self._add_existing,
        )

    def _add_new(self, m):
        comp = _SlotComp(self._design, f'Comp{len(self._design._reg) + 1}')
        tok = f'occ_tok_{len(self._design._reg)}'
        occ = SimpleNamespace(component=comp, isValid=True, entityToken=tok, name='')
        self._design._reg[tok] = occ
        self._design.timeline.append_item(('occ', tok))
        return occ

    def _add_existing(self, comp, m):
        tok = f'occ_tok_{len(self._design._reg)}'
        occ = SimpleNamespace(component=comp, isValid=True, entityToken=tok, name='')
        self._design._reg[tok] = occ
        self._design.timeline.append_item(('occ', tok))
        return occ


class _SlotDesign:
    def __init__(self):
        self.designType = mock_fusion.DesignTypes.ParametricDesignType
        self.timeline = _SlotTimeline()
        self.userParameters = _SlotParams()
        self.unitsManager = SimpleNamespace(
            isValidExpression=lambda s, u: True,
            evaluateExpression=lambda s, u: 1.0,
        )
        self._reg = {}
        self.rootComponent = _SlotComp(self, 'root')

    def findEntityByToken(self, tok):
        e = self._reg.get(tok)
        return [e] if e is not None else []


class _FakeMatrix:
    @staticmethod
    def create():
        return _FakeMatrix()

    def setToRotation(self, a, v, o):
        pass

    def transformBy(self, r):
        pass

    translation = None


class _SlotStepFeature(_feat_reg.BaseFeature):
    op = 'zz_step'
    name = 'ZZ Step'
    order = 999

    def execute(self, step, ctx):
        ctx.root._design.timeline.append_item(('step', ctx.root.name, step.get('id')))


_saved_adsk = {
    'Matrix3D': getattr(mock_core, 'Matrix3D', None),
    'ValueInput': getattr(mock_core, 'ValueInput', None),
    'Vector3D': getattr(mock_core, 'Vector3D', None),
    'Point3D_create': getattr(mock_core.Point3D, 'create', None),
    'FeatureOperations': getattr(mock_fusion, 'FeatureOperations', None),
}
mock_core.Matrix3D = _FakeMatrix
mock_core.ValueInput = SimpleNamespace(createByString=lambda s: s)
mock_core.Vector3D = SimpleNamespace(create=lambda x, y, z: (x, y, z))
mock_core.Point3D.create = staticmethod(lambda x, y, z: (x, y, z))
mock_fusion.FeatureOperations = SimpleNamespace(
    NewBodyFeatureOperation=0, JoinFeatureOperation=1,
    CutFeatureOperation=2, IntersectFeatureOperation=3,
)
_feat_reg.register_feature(_SlotStepFeature())
try:
    # 1. Single-part build still produces one group named exactly `group_name`
    _sdes = _SlotDesign()
    _sinfo = dsl.execute(_sdes, {'parameters': {}, 'timeline': [
        {'op': 'zz_step', 'id': 'a'}, {'op': 'zz_step', 'id': 'b'}]}, group_name='VibeShaper · Solo · v1 [s1]')
    assert _sinfo['group_name'] == 'VibeShaper · Solo · v1 [s1]'
    assert _sinfo['feature_count'] == 2
    assert [g.name for g in dsl.find_groups(_sdes, 'VibeShaper · Solo · v1 [s1]')] == ['VibeShaper · Solo · v1 [s1]']

    # 2. Multi-component assembly creates collapsed sibling groups in reverse index order
    _mdes = _SlotDesign()
    _mdsl = {
        'parameters': {'w': '10 mm'},
        'timeline': [{'op': 'zz_step', 'id': 'r1'}, {'op': 'zz_step', 'id': 'r2'}],
        'components': [
            {'id': 'left_b', 'name': 'Bracket', 'timeline': [{'op': 'zz_step', 'id': 'b1'}]},
            {'id': 'right_b', 'name': 'Bracket', 'timeline': [{'op': 'zz_step', 'id': 'b2'}]},
            {'id': 'cap', 'name': 'Cap', 'timeline': [{'op': 'zz_step', 'id': 'c1'}, {'op': 'zz_step', 'id': 'c2'}]},
        ],
        'instances': [
            {'component': 'left_b', 'position': ['w', 0, 0]},
            {'component': 'left_b', 'position': ['-w', 0, 0]},
            {'component': 'right_b', 'position': [0, 'w', 0]},
            {'component': 'cap', 'position': [0, 0, 'w']},
        ],
    }
    _minfo = dsl.execute(_mdes, _mdsl, group_name='VibeShaper · Asm · v1 [a1]')
    _expected_groups = [
        'VibeShaper · Asm · v1 [a1] / Root',
        'VibeShaper · Asm · v1 [a1] / Bracket (left_b)',
        'VibeShaper · Asm · v1 [a1] / Bracket (right_b)',
        'VibeShaper · Asm · v1 [a1] / Cap',
    ]
    _found = dsl.find_groups(_mdes, 'VibeShaper · Asm · v1 [a1]')
    assert _minfo['group_name'] == 'VibeShaper · Asm · v1 [a1]'
    assert _minfo['feature_count'] == 10  # 2 root steps + (2 occs + 1 step) + (1 occ + 1 step) + (1 occ + 2 steps)
    assert [g.name for g in _found] == _expected_groups
    assert all(g.isCollapsed for g in _found)
    assert dsl.find_group(_mdes, 'VibeShaper · Asm · v1 [a1]') is _found[0]
    assert dsl.find_groups(_mdes, 'VibeShaper') == []  # prefix separator avoids cross-chat matches
    assert [it.tag for it in _found[0]._items] == [('step', 'root', 'r1'), ('step', 'root', 'r2')]
    assert [it.tag[0] for it in _found[1]._items] == ['occ', 'occ', 'step']
    assert [it.tag[0] for it in _found[3]._items] == ['occ', 'step', 'step']

    # user_features_after ignores later VibeShaper groups and counts only user features after all siblings
    _mdes.timeline.append_item(('other', 1))
    _mdes.timeline.append_item(('other', 2))
    _og = _mdes.timeline.timelineGroups.add(_mdes.timeline.count - 2, _mdes.timeline.count - 1)
    _og.name = 'VibeShaper · Other · v1 [o1]'
    assert dsl.user_features_after(_mdes, 'VibeShaper · Asm · v1 [a1]') == 0
    _mdes.timeline.append_item(('user', 1))
    _mdes.timeline.append_item(('user', 2))
    assert dsl.user_features_after(_mdes, 'VibeShaper · Asm · v1 [a1]') == 2

    # delete_version removes every sibling group in reverse order, leaving other groups and user items intact
    assert dsl.delete_version(_mdes, 'VibeShaper · Asm · v1 [a1]', ['w'], _minfo['occurrences']) == 'deleted'
    assert _mdes.timeline.deleted_order == list(reversed(_expected_groups))
    assert [g.name for g in _mdes.timeline.groups] == ['VibeShaper · Other · v1 [o1]']
    assert _mdes.timeline.count == 3  # _og slot + 2 loose user items
    assert 'w' not in _mdes.userParameters.d

    # Fallback suppression applies across all un-deletable sibling groups
    _fdes = _SlotDesign()
    dsl.execute(_fdes, _mdsl, group_name='VibeShaper · Lock · v1 [l1]')
    for _g in dsl.find_groups(_fdes, 'VibeShaper · Lock · v1 [l1]'):
        _g.refuse_delete = True
        for _it in _g._items:
            _it.refuse = True
    assert dsl.delete_version(_fdes, 'VibeShaper · Lock · v1 [l1]', []) == 'suppressed'
    assert all(_g.isSuppressed for _g in dsl.find_groups(_fdes, 'VibeShaper · Lock · v1 [l1]'))
finally:
    _feat_reg.unregister_feature('zz_step')
    mock_core.Matrix3D = _saved_adsk['Matrix3D']
    mock_core.ValueInput = _saved_adsk['ValueInput']
    mock_core.Vector3D = _saved_adsk['Vector3D']
    if _saved_adsk['Point3D_create'] is None:
        delattr(mock_core.Point3D, 'create')
    else:
        mock_core.Point3D.create = _saved_adsk['Point3D_create']
    mock_fusion.FeatureOperations = _saved_adsk['FeatureOperations']

print('ok')
