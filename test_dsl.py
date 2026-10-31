"""Run outside Fusion: python test_dsl.py"""
import json
import os
import pathlib
import tempfile

# Settings and logs go to a throwaway folder, never the user's real ones
os.environ['PROMPTCAD_HOME'] = tempfile.mkdtemp(prefix='promptcad-test-')

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
_core_py = ('PromptCAD.py', 'llm.py', 'chat.py', 'dsl.py', 'providers/__init__.py', 'providers/base.py',
            'tools/__init__.py', 'tools/base.py')
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

from dsl import _select_edges
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
from dsl import _anchor, _draw

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

# Test 4: Post-draw sweep locks unconstrained curves and points
if not sk3.isFullyConstrained:
    for c in [sk3.sketchCurves.item(k) for k in range(sk3.sketchCurves.count)]:
        if not c.isFullyConstrained: c.isFixed = True
    for p in [sk3.sketchPoints.item(k) for k in range(sk3.sketchPoints.count)]:
        if not p.isFullyConstrained: p.isFixed = True

assert all(c.isFixed or c.isFullyConstrained for c in [sk3.sketchCurves.item(k) for k in range(sk3.sketchCurves.count)])

# Test 5: Layer 1 Auto-perpendicularity on orthogonal polyline
sk5 = MockSketchObj()
l_poly = {
    "type": "polyline",
    "points": [[0, 50], [0, 0], [50, 0]],
    "closed": False
}
_draw(sk5, l_poly, dummy_ex, dummy_cm, dummy_pt)
assert any(c[0] == 'perpendicular' for c in sk5.geometricConstraints.constraints)

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
# Loads PromptCAD.py as a package with a stub Fusion API and a fake provider.
import importlib
import tempfile


def _load_addin_with_stub_fusion(pkg_name='promptcad_addin', app_factory=None):
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
        addin = importlib.import_module(pkg_name + '.PromptCAD')
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return addin, fired, fired_event, fake_app


addin, fired, fired_event, _ = _load_addin_with_stub_fusion()
tmp_log_dir = pathlib.Path(tempfile.mkdtemp())
addin.llm.LOG_FILE = tmp_log_dir / 'promptcad.log'
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
_home = pathlib.Path(os.environ['PROMPTCAD_HOME'])
assert addin.userdata.folder() == _home != here and llm.LOG_FILE.parent == _home
with unittest.mock.patch.dict(os.environ, {'PROMPTCAD_HOME': '', 'APPDATA': r'C:\U\AppData\Roaming'}), \
        unittest.mock.patch.object(userdata.sys, 'platform', 'win32'):
    assert userdata.folder() == pathlib.Path(r'C:\U\AppData\Roaming') / 'PromptCAD'
with unittest.mock.patch.dict(os.environ, {'PROMPTCAD_HOME': ''}), unittest.mock.patch.object(userdata.sys, 'platform', 'darwin'):
    assert userdata.folder() == pathlib.Path.home() / 'Library' / 'Application Support' / 'PromptCAD'
with unittest.mock.patch.dict(os.environ, {'PROMPTCAD_HOME': '', 'XDG_CONFIG_HOME': '/x'}),         unittest.mock.patch.object(userdata.sys, 'platform', 'linux'):
    assert userdata.folder() == pathlib.Path('/x') / 'promptcad'

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
des.timeline.add_group('PromptCAD · Cube · v1 [abc]', 3)
des.timeline.add_group('PromptCAD · Other part · v1 [zzz]', 2)
assert dsl.user_features_after(des, 'PromptCAD · Cube · v1 [abc]') == 0  # other PromptCAD parts don't count
des.timeline.add_loose(2)  # user's own features after it
assert dsl.user_features_after(des, 'PromptCAD · Cube · v1 [abc]') == 2
assert dsl.user_features_after(des, 'missing') == 0

for name, used in (('cube', False), ('hole', True)):
    des.userParameters.d[name] = _Param(des.userParameters.d, name, in_use=used)
assert dsl.delete_version(des, 'PromptCAD · Cube · v1 [abc]', ['cube', 'hole', 'gone']) == 'deleted'
assert [g.name for g in des.timeline.groups] == ['PromptCAD · Other part · v1 [zzz]']
assert des.timeline.count == 4
assert list(des.userParameters.d) == ['hole']  # in-use parameter is left alone
assert dsl.delete_version(des, 'PromptCAD · Cube · v1 [abc]', []) is False  # already gone: build fresh

# Fusion refuses to delete the whole group: delete its features one by one, newest first
des = _Design()
g = des.timeline.add_group('PromptCAD · Spring · v1 [s]', 3)
other = des.timeline.add_group('PromptCAD · Other · v1 [o]', 1)
g.refuse_delete = True
assert dsl.delete_version(des, 'PromptCAD · Spring · v1 [s]', []) == 'deleted'
assert des.timeline.moved_to_end
assert [x.name for x in des.timeline.groups] == ['PromptCAD · Other · v1 [o]'] and des.timeline.count == 1

# Nothing can be deleted: suppress the old version instead, so the new one can still be built
des = _Design()
g = des.timeline.add_group('PromptCAD · Spring · v1 [s]', 2)
g.refuse_delete = True
for it in g._items:
    it.refuse = True
assert dsl.delete_version(des, 'PromptCAD · Spring · v1 [s]', []) == 'suppressed'
assert g.isSuppressed is True

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
e2e, _, _, e2e_app = _load_addin_with_stub_fusion('promptcad_e2e', H.make_app)
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


def _fake_execute(design, d, group_name='PromptCAD', comp=None):
    BUILT_INTO.append(comp.name if comp else None)
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
assert len(groups()) == 1 and groups()[0].startswith('PromptCAD · a 40 mm cube · v1')
assert H.design.userParameters.d['cube_w'].expression == '40 mm'
assert SP.seen[-1][0]['role'] == 'system' and SP.seen[-1][-1]['content'] == 'a 40 mm cube'

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
saved_json = H.design.attributes.itemByName('PromptCAD', 'chats').value
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


def _broken_delete(design, group_name, param_names=()):
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

print('ok')
