"""JSON DSL -> Fusion 360 parametric timeline.

validate() is pure stdlib (testable outside Fusion); execute() needs Fusion's adsk modules.
All lengths default to mm. Any length may be a number, a literal ("20 mm") or an
expression over user parameters ("box_width - 2 * wall_thick").
"""
import math
import re

try:
    from . import shapes
except ImportError:  # run as a plain script (tests)
    import shapes

PLANES = ('xy', 'xz', 'yz')
AXES = ('x', 'y', 'z')
MODES = ('new_body', 'join', 'cut', 'intersect')
VALID_OPS = ('sketch', 'extrude', 'revolve', 'fillet', 'chamfer', 'shell', 'circular_pattern', 'linear_pattern', 'thread', 'mirror', 'combine', 'sweep', 'coil')
EDGE_SELECTORS = ('vertical', 'top', 'bottom', 'circular', 'all')
FACE_SELECTORS = ('top', 'bottom', 'none', 'all')
FEATURE_FACE_SETS = {'all': 'faces', 'side': 'sideFaces', 'start': 'startFaces', 'end': 'endFaces'}

ENTITY_KEYS = {
    'center_rectangle': ('center', 'width', 'height'),
    'circle': ('center', 'diameter'),
    'polygon': ('points',),
    'line': ('start', 'end'),
    'polyline': ('points',),
    'regular_polygon': ('center', 'sides'),
    'profile': ('start', 'segments'),
    'mirror': ('entities', 'line'),
}
NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# JSON schema of the DSL, for providers that can constrain their reply to a schema.
# validate() below is still the authority.
_JS_LEN = {'type': ['string', 'number']}
_JS_POINT = {'type': 'array', 'items': _JS_LEN, 'minItems': 2, 'maxItems': 2}

JSON_SCHEMA = {
    'type': 'object',
    'properties': {
        'name': {'type': 'string'},
        'parameters': {
            'type': 'object',
            'additionalProperties': _JS_LEN
        },
        'timeline': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'op': {'enum': [
                        'sketch', 'extrude', 'revolve', 'fillet', 'chamfer', 'shell',
                        'circular_pattern', 'linear_pattern', 'thread', 'mirror', 'combine',
                        'sweep', 'coil'
                    ]},
                    'id': {'type': 'string'},
                    'plane': {'enum': ['xy', 'xz', 'yz']},
                    'offset': _JS_LEN,
                    'entities': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'type': {'enum': ['center_rectangle', 'circle', 'polygon', 'line', 'polyline', 'regular_polygon', 'profile', 'mirror']},
                                'id': {'type': 'string'},
                                'center': _JS_POINT,
                                'width': _JS_LEN,
                                'height': _JS_LEN,
                                'diameter': _JS_LEN,
                                'points': {'type': 'array', 'items': _JS_POINT},
                                'start': _JS_POINT,
                                'end': _JS_POINT,
                                'closed': {'type': 'boolean'},
                                'sides': {'type': ['integer', 'string']},
                                'segments': {'type': 'array', 'items': {
                                    'type': 'object',
                                    'properties': {'to': _JS_POINT, 'through': _JS_POINT},
                                    'required': ['to']}},
                                'across_flats': _JS_LEN,
                                'entities': {'type': 'array', 'items': {'type': 'string'}},
                                'line': {'type': 'array', 'items': _JS_POINT, 'minItems': 2, 'maxItems': 2}
                            },
                            'required': ['type']
                        }
                    },
                    'constraints': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'type': {'enum': ['perpendicular', 'parallel', 'concentric', 'tangent', 'equal', 'coincident', 'midpoint', 'symmetry']},
                                'entities': {'type': 'array', 'items': {'type': 'string'}},
                                'point': {'type': 'string'},
                                'entity': {'type': 'string'},
                                'symmetry_line': {'type': 'string'}
                            },
                            'required': ['type']
                        }
                    },
                    'sketch': {'type': 'string'},
                    'distance': _JS_LEN,
                    'mode': {'enum': ['new_body', 'join', 'cut', 'intersect']},
                    'axis': {'enum': ['x', 'y', 'z']},
                    'center': {'type': 'array', 'items': _JS_LEN, 'minItems': 2, 'maxItems': 3},
                    'angle': _JS_LEN,
                    'radius': _JS_LEN,
                    'edges': {'anyOf': [
                        {'enum': ['vertical', 'top', 'bottom', 'circular', 'all']},
                        {'type': 'object', 'properties': {
                            'feature': {'type': 'string'},
                            'faces': {'enum': ['all', 'side', 'start', 'end']},
                            'exclude': {'type': ['string', 'array'], 'items': {'type': 'string'}},
                            'type': {'enum': ['circle', 'line']},
                            'at': {'enum': ['top', 'bottom']},
                            'direction': {'enum': ['x', 'y', 'z']},
                            'on': {'type': 'string'}
                        }}
                    ]},
                    'thickness': _JS_LEN,
                    'remove_faces': {'enum': ['top', 'bottom', 'none']},
                    'feature': {'type': 'string'},
                    'quantity': _JS_LEN,
                    'direction': {'enum': ['x', 'y', 'z']},
                    'direction2': {'enum': ['x', 'y', 'z']},
                    'quantity2': _JS_LEN,
                    'distance2': _JS_LEN,
                    'target': {'type': 'string'},
                    'modeled': {'type': 'boolean'},
                    'designation': {'type': 'string'},
                    'combine': {'type': 'boolean'},
                    'tools': {'type': 'array', 'items': {'type': 'string'}},
                    'keep_tools': {'type': 'boolean'},
                    'path': {'type': 'string'},
                    'thread_class': {'type': 'string'},
                    'diameter': _JS_LEN,
                    'pitch': _JS_LEN,
                    'revolutions': _JS_LEN,
                    'section_size': _JS_LEN,
                    'section': {'enum': ['circle', 'square', 'rectangle']},
                    'clockwise': {'type': 'boolean'},
                },
                'required': ['op']
            }
        }
    },
    'required': ['parameters', 'timeline'],
}


def _add_shapes_to_schema(schema):
    """Let the reply schema offer every shape plugin's step type and keys."""
    step = schema['properties']['timeline']['items']
    for shape in shapes.get_all_shapes():
        if shape.op not in step['properties']['op']['enum']:
            step['properties']['op']['enum'].append(shape.op)
        for key, spec in shape.schema.items():
            step['properties'].setdefault(key, spec)


_add_shapes_to_schema(JSON_SCHEMA)


def shapes_prompt():
    """What the shape plugins tell the model about themselves ('' when there are none)."""
    return shapes.prompt()


def expand_shapes(d):
    """Replace each shape step (an op a shape plugin adds) with the parameters and plain steps
    that build it. Other steps are kept as the same objects. Returns d itself when there are none."""
    tl = d.get('timeline') if isinstance(d, dict) else None
    if not isinstance(tl, list) or not any(isinstance(s, dict) and shapes.get_shape(s.get('op')) for s in tl):
        return d
    params = dict(d.get('parameters') or {})
    steps = []
    for i, s in enumerate(tl):
        shape = shapes.get_shape(s.get('op')) if isinstance(s, dict) else None
        if not shape:
            steps.append(s)
            continue
        where = f'timeline[{i}] ({s["op"]})'
        shape.validate(s, where)
        new_params, new_steps = shape.expand(s)
        clash = [k for k in new_params if k in params]
        if clash:
            raise ValueError(f'{where}: parameters {clash} already exist; give this step another id')
        params.update(new_params)
        steps.extend(new_steps)
    out = dict(d)
    out['parameters'], out['timeline'] = params, steps
    return out


def _need(obj, where, *keys):
    if not isinstance(obj, dict):
        raise ValueError(f'{where}: must be an object')
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValueError(f'{where}: missing {", ".join(missing)}')


def _xy(v, where):
    if not (isinstance(v, list) and len(v) == 2):
        raise ValueError(f'{where}: point must be [x, y]')


EDGE_SELECTOR_KEYS = ('feature', 'faces', 'exclude', 'type', 'at', 'direction', 'on')


def _check_edges(edges, where, features, sketches=()):
    if isinstance(edges, str):
        if edges not in EDGE_SELECTORS:
            raise ValueError(f'{where}: edge selector must be one of {EDGE_SELECTORS} or an object')
        return
    if not isinstance(edges, dict):
        raise ValueError(f'{where}: edges must be a string or an object')
    extra = [k for k in edges if k not in EDGE_SELECTOR_KEYS]
    if extra:
        raise ValueError(f'{where}: unknown edge selector keys {extra}; allowed: {EDGE_SELECTOR_KEYS}')
    excl = edges.get('exclude', [])
    refs = ([edges['feature']] if 'feature' in edges else []) + ([excl] if isinstance(excl, str) else list(excl))
    for fid in refs:
        if fid not in features:
            raise ValueError(f'{where}: edges refer to feature {fid!r}, which is not defined earlier')
    if 'on' in edges and edges['on'] not in sketches:
        raise ValueError(f'{where}: edges.on refers to sketch {edges["on"]!r}, which is not defined earlier')
    if edges.get('faces', 'all') not in FEATURE_FACE_SETS:
        raise ValueError(f'{where}: edges.faces must be one of {tuple(FEATURE_FACE_SETS)}')
    if 'faces' in edges and 'feature' not in edges:
        raise ValueError(f'{where}: edges.faces needs edges.feature')
    if edges.get('type', 'circle') not in ('circle', 'line'):
        raise ValueError(f'{where}: edges.type must be "circle" or "line"')
    if edges.get('at', 'top') not in ('top', 'bottom'):
        raise ValueError(f'{where}: edges.at must be "top" or "bottom"')
    if edges.get('direction', 'z') not in AXES:
        raise ValueError(f'{where}: edges.direction must be one of {AXES}')


def validate(d):
    """Structural check of untrusted (LLM) output. Raises ValueError with a path to the problem."""
    if not isinstance(d, dict):
        raise ValueError('DSL must be a JSON object')
    d = expand_shapes(d)
    params = d.get('parameters', {})
    if not isinstance(params, dict):
        raise ValueError('parameters must be an object')
    for k, v in params.items():
        if not NAME_RE.match(k):
            raise ValueError(f'parameters: bad name {k!r}')
        if not isinstance(v, (str, int, float)):
            raise ValueError(f'parameters.{k}: must be a string or number')
    tl = d.get('timeline')
    if not isinstance(tl, list) or not tl:
        raise ValueError('timeline must be a non-empty list')

    sketches = set()
    features = set()

    for i, s in enumerate(tl):
        where = f'timeline[{i}]'
        _need(s, where, 'op')
        op = s['op']
        if op not in VALID_OPS:
            known = VALID_OPS + tuple(sh.op for sh in shapes.get_all_shapes())
            raise ValueError(f'{where}: unknown op {op!r}; known: {known}')

        if op == 'sketch':
            _need(s, where, 'id', 'plane', 'entities')
            if s['plane'] not in PLANES:
                raise ValueError(f'{where}: plane must be one of {PLANES}')
            if s['id'] in sketches:
                raise ValueError(f'{where}: duplicate sketch id {s["id"]!r}')
            if not isinstance(s['entities'], list) or not s['entities']:
                raise ValueError(f'{where}: entities must be a non-empty list')
            ent_ids = set()
            for j, e in enumerate(s['entities']):
                ew = f'{where}.entities[{j}]'
                _need(e, ew, 'type')
                if e['type'] not in ENTITY_KEYS:
                    raise ValueError(f'{ew}: type must be one of {tuple(ENTITY_KEYS)}')
                _need(e, ew, *ENTITY_KEYS[e['type']])
                if e['type'] == 'mirror':
                    refs = e['entities']
                    if not isinstance(refs, list) or not refs:
                        raise ValueError(f'{ew}: entities must be a non-empty list of entity ids')
                    for ref in refs:
                        if ref not in ent_ids:
                            raise ValueError(f'{ew}: entities refers to {ref!r}, which is not an entity id '
                                             f'defined earlier in this sketch')
                    line = e['line']
                    if not isinstance(line, list) or len(line) != 2:
                        raise ValueError(f'{ew}: line must be two points [[a, b], [a, b]]')
                    for p in line:
                        _xy(p, f'{ew}.line')
                if 'id' in e:
                    if not isinstance(e['id'], str) or not e['id']:
                        raise ValueError(f'{ew}: id must be a non-empty string')
                    ent_ids.add(e['id'])
                if 'center' in e:
                    _xy(e['center'], ew)
                if e['type'] == 'line':
                    _xy(e['start'], ew)
                    _xy(e['end'], ew)
                elif e['type'] == 'polyline':
                    if not isinstance(e['points'], list) or len(e['points']) < 2:
                        raise ValueError(f'{ew}: polyline needs at least 2 points')
                    for p in e['points']:
                        _xy(p, ew)
                elif e['type'] == 'profile':
                    _xy(e['start'], ew)
                    if not isinstance(e['segments'], list) or not e['segments']:
                        raise ValueError(f'{ew}: segments must be a non-empty list')
                    for k, sg in enumerate(e['segments']):
                        _need(sg, f'{ew}.segments[{k}]', 'to')
                        _xy(sg['to'], f'{ew}.segments[{k}].to')
                        if 'through' in sg:
                            _xy(sg['through'], f'{ew}.segments[{k}].through')
                elif e['type'] == 'regular_polygon':
                    try:
                        sides = float(e['sides'])
                    except (TypeError, ValueError):
                        sides = 0
                    if sides != int(sides) or not 3 <= sides <= 64:
                        raise ValueError(f'{ew}: sides must be a whole number from 3 to 64')
                    if ('diameter' in e) == ('across_flats' in e):
                        raise ValueError(f'{ew}: give either diameter (through the corners) or across_flats')
                elif e['type'] == 'polygon':
                    if not isinstance(e['points'], list) or len(e['points']) < 3:
                        raise ValueError(f'{ew}: polygon needs at least 3 points')
                    for p in e['points']:
                        _xy(p, ew)

            if 'constraints' in s:
                if not isinstance(s['constraints'], list):
                    raise ValueError(f'{where}: constraints must be a list')
                for c_idx, c in enumerate(s['constraints']):
                    cw = f'{where}.constraints[{c_idx}]'
                    _need(c, cw, 'type')
                    ctype = c['type']
                    if ctype not in ('perpendicular', 'parallel', 'concentric', 'tangent', 'equal', 'coincident', 'midpoint', 'symmetry'):
                        raise ValueError(f'{cw}: unknown constraint type {ctype!r}')
                    targets = c.get('entities') or []
                    if not isinstance(targets, list):
                        raise ValueError(f'{cw}: entities must be a list')
                    for t_name in targets:
                        base_id = t_name.split('.')[0]
                        if base_id not in ent_ids:
                            raise ValueError(f'{cw}: target entity {t_name!r} not found in sketch entities')
            sketches.add(s['id'])

        elif op == 'extrude':
            _need(s, where, 'sketch', 'distance')
            if s['sketch'] not in sketches:
                raise ValueError(f'{where}: unknown sketch {s["sketch"]!r} (must be defined earlier)')
            if s.get('mode', 'new_body') not in MODES:
                raise ValueError(f'{where}: mode must be one of {MODES}')
            features.add(s.get('id', s['sketch']))  # execute() names an id-less extrude after its sketch

        elif op == 'revolve':
            _need(s, where, 'sketch')
            if s['sketch'] not in sketches:
                raise ValueError(f'{where}: unknown sketch {s["sketch"]!r} (must be defined earlier)')
            if s.get('axis', 'z').lower() not in AXES:
                raise ValueError(f'{where}: axis must be one of {AXES}')
            if s.get('mode', 'new_body') not in MODES:
                raise ValueError(f'{where}: mode must be one of {MODES}')
            if 'id' in s:
                features.add(s['id'])

        elif op == 'fillet':
            # Ignore dummy defaults emitted by flat schemas
            if s.get('remove_faces') not in (None, 'none') and s.get('thickness') not in (None, 0, '0', '0 mm'):
                raise ValueError(f'{where}: cannot combine fillet and shell in one step; make shell a separate step')
            rad = s.get('radius') or s.get('distance')
            if not rad:
                # Look for an obvious radius parameter in d['parameters']
                for pname in params:
                    if any(w in pname.lower() for w in ('radius', 'fillet', 'corner', 'round')):
                        rad = pname
                        s['radius'] = pname
                        break
            if not rad:
                raise ValueError(f'{where}: missing radius')
            _check_edges(s.get('edges', 'all'), where, features, sketches)
            if 'id' in s:
                features.add(s['id'])

        elif op == 'chamfer':
            dist = s.get('distance') or s.get('radius')
            if not dist:
                for pname in params:
                    if any(w in pname.lower() for w in ('chamfer', 'bevel')):
                        dist = pname
                        s['distance'] = pname
                        break
            if not dist:
                raise ValueError(f'{where}: missing distance')
            _check_edges(s.get('edges', 'all'), where, features, sketches)
            if 'id' in s:
                features.add(s['id'])

        elif op == 'shell':
            _need(s, where, 'thickness')
            faces = s.get('remove_faces', 'top')
            if isinstance(faces, str) and faces not in FACE_SELECTORS:
                raise ValueError(f'{where}: remove_faces selector must be one of {FACE_SELECTORS} or an object')
            if 'id' in s:
                features.add(s['id'])

        elif op == 'circular_pattern':
            qty = s.get('quantity') or s.get('count') or s.get('num')
            if not qty:
                for pname in params:
                    if any(w in pname.lower() for w in ('qty', 'count', 'num')):
                        qty = pname
                        s['quantity'] = pname
                        break
            if not qty:
                raise ValueError(f'{where}: missing quantity')
            if s.get('axis', 'z').lower() not in AXES:
                raise ValueError(f'{where}: axis must be one of {AXES}')
            if 'center' in s:
                _xy(s['center'], f'{where}.center')
            if 'feature' in s and s['feature'] not in features:
                raise ValueError(f'{where}: feature {s["feature"]!r} not found in previous features')
            if 'id' in s:
                features.add(s['id'])

        elif op == 'linear_pattern':
            dist = s.get('distance') or s.get('spacing')
            if not dist:
                raise ValueError(f'{where}: missing distance')
            qty = s.get('quantity') or s.get('count') or s.get('num')
            if not qty:
                for pname in params:
                    if any(w in pname.lower() for w in ('qty', 'count', 'num')):
                        qty = pname
                        s['quantity'] = pname
                        break
            if not qty:
                raise ValueError(f'{where}: missing quantity')
            if s.get('direction', 'x').lower() not in AXES:
                raise ValueError(f'{where}: direction must be one of {AXES}')
            if 'direction2' in s:
                _need(s, where, 'quantity2', 'distance2')
                if str(s['direction2']).lower() not in AXES or s['direction2'] == s.get('direction', 'x'):
                    raise ValueError(f'{where}: direction2 must be another one of {AXES}')
            if 'feature' in s and s['feature'] not in features:
                raise ValueError(f'{where}: feature {s["feature"]!r} not found in previous features')
            if 'id' in s:
                features.add(s['id'])

        elif op == 'thread':
            target = s.get('target', 'all')
            if target not in ('internal', 'external', 'all'):
                raise ValueError(f'{where}: target must be one of ("internal", "external", "all")')
            if 'feature' in s and s['feature'] not in features:
                raise ValueError(f'{where}: feature {s["feature"]!r} not found in previous features')
            if 'id' in s:
                features.add(s['id'])

        elif op == 'mirror':
            if 'feature' in s and s['feature'] not in features:
                raise ValueError(f'{where}: feature {s["feature"]!r} not found in previous features')
            plane = s.get('plane', 'xz')
            if isinstance(plane, str) and plane not in PLANES and plane not in FACE_SELECTORS:
                raise ValueError(f'{where}: plane must be one of {PLANES} or a face selector')
            if 'id' in s:
                features.add(s['id'])

        elif op == 'combine':
            tools = s.get('tools') or s.get('tool_bodies')
            if not tools:
                raise ValueError(f'{where}: missing tools')
            if isinstance(tools, str):
                tools = [tools]
            if not isinstance(tools, list):
                raise ValueError(f'{where}: tools must be a list or string')
            mode = s.get('mode', 'join').lower()
            if mode not in MODES:
                raise ValueError(f'{where}: mode must be one of {MODES}')
            if 'id' in s:
                features.add(s['id'])

        elif op == 'sweep':
            _need(s, where, 'sketch', 'path')
            if s['sketch'] not in sketches:
                raise ValueError(f'{where}: unknown profile sketch {s["sketch"]!r}')
            if s['path'] not in sketches:
                raise ValueError(f'{where}: unknown path sketch {s["path"]!r}')
            mode = s.get('mode', 'new_body').lower()
            if mode not in MODES:
                raise ValueError(f'{where}: mode must be one of {MODES}')
            if 'id' in s:
                features.add(s['id'])

        elif op == 'coil':
            dia = s.get('diameter') or s.get('radius') or s.get('coil_dia')
            if not dia:
                for pname in params:
                    if any(w in pname.lower() for w in ('coil_dia', 'spring_dia', 'helix_dia', 'diameter', 'outer_dia', 'od')):
                        dia = pname
                        s['diameter'] = pname
                        break
            if not dia:
                raise ValueError(f'{where}: missing diameter (coil diameter)')

            sec = s.get('section_size') or s.get('wire_dia') or s.get('wire_diameter') or s.get('thickness') or s.get('wire_radius')
            if not sec:
                for pname in params:
                    if any(w in pname.lower() for w in ('wire', 'section', 'thickness', 'filament')):
                        sec = pname
                        s['section_size'] = pname
                        break
            if not sec:
                raise ValueError(f'{where}: missing section_size (wire diameter)')

            if s.get('axis', 'z').lower() not in AXES:
                raise ValueError(f'{where}: axis must be one of {AXES}')
            if s.get('mode', 'new_body') not in MODES:
                raise ValueError(f'{where}: mode must be one of {MODES}')
            if 'id' in s:
                features.add(s['id'])


def _get_body(root, target, features):
    if target:
        for k in range(root.bRepBodies.count):
            b = root.bRepBodies.item(k)
            if b.name == target:
                return b
        if target in features:
            f = features[target]
            if hasattr(f, 'bodies') and f.bodies.count > 0:
                return f.bodies.item(0)
        raise ValueError(f"target body/feature {target!r} not found")
    if root.bRepBodies.count == 0:
        raise ValueError("no solid bodies found in design")
    return root.bRepBodies.item(root.bRepBodies.count - 1)




def _feature_faces(features, fid, which='all'):
    """Faces a named step produced, as they are now (later steps may have split them)."""
    if not features or fid not in features:
        raise ValueError(f'edge selector: unknown feature {fid!r}')
    coll = getattr(features[fid], FEATURE_FACE_SETS[which], None)
    if coll is None:
        raise ValueError(f'edge selector: feature {fid!r} has no {which} faces')
    return [coll.item(k) for k in range(coll.count)]


def _feature_edges(features, sel):
    """Edges of the faces made by sel['feature'], minus those touching sel['exclude'] faces."""
    edges = []
    for face in _feature_faces(features, sel['feature'], sel.get('faces', 'all')):
        for k in range(face.edges.count):
            e = face.edges.item(k)
            if not any(e == x for x in edges):  # Fusion objects compare by entity, not identity
                edges.append(e)
    excl = sel.get('exclude') or []
    for fid in [excl] if isinstance(excl, str) else excl:
        bad = _feature_faces(features, fid)
        edges = [e for e in edges
                 if not any(f == b for f in (e.faces.item(k) for k in range(e.faces.count)) for b in bad)]
    return edges


def _select_edges(body, sel, features=None, sketches=None):
    import adsk.core
    if isinstance(sel, str):
        if sel == 'vertical':
            sel = {'direction': 'z'}
        elif sel == 'top':
            sel = {'at': 'top'}
        elif sel == 'bottom':
            sel = {'at': 'bottom'}
        elif sel == 'circular':
            sel = {'type': 'circle'}
        elif sel == 'all':
            sel = {}
        else:
            raise ValueError(f"unknown edge selector '{sel}'")
    elif not isinstance(sel, dict):
        raise ValueError("edge selector must be a string or object")

    matched = []
    bb = body.boundingBox
    z_max, z_min = bb.maxPoint.z, bb.minPoint.z
    tol = 0.05  # 0.5 mm in cm

    if 'feature' in sel:
        candidates = _feature_edges(features, sel)
    else:
        candidates = [body.edges.item(k) for k in range(body.edges.count)]
    if 'on' in sel:
        if not sketches or sel['on'] not in sketches:
            raise ValueError(f"edge selector: unknown sketch {sel['on']!r}")
        candidates = [e for e in candidates if _edge_on_sketch_plane(e, sketches[sel['on']])]

    for edge in candidates:
        geo = edge.geometry

        if sel.get('type') == 'circle':
            if geo.curveType != adsk.core.Curve3DTypes.Circle3DCurveType:
                continue
        elif sel.get('type') == 'line':
            if geo.curveType != adsk.core.Curve3DTypes.Line3DCurveType:
                continue

        if 'direction' in sel:
            if geo.curveType != adsk.core.Curve3DTypes.Line3DCurveType:
                continue
            if hasattr(geo, 'asInfiniteLine'):
                dir_vec = geo.asInfiniteLine().direction
            elif hasattr(geo, 'startPoint') and hasattr(geo, 'endPoint'):
                dir_vec = geo.startPoint.vectorTo(geo.endPoint)
                dir_vec.normalize()
            else:
                dir_vec = getattr(geo, 'direction', None)
            if not dir_vec:
                continue
            val = abs(getattr(dir_vec, sel['direction'].lower(), 0))
            if val < 0.9:
                continue

        if 'at' in sel:
            at = sel['at'].lower()
            target_z = z_max if at == 'top' else z_min
            if hasattr(geo, 'startPoint') and hasattr(geo, 'endPoint'):
                if abs(geo.startPoint.z - target_z) > tol or abs(geo.endPoint.z - target_z) > tol:
                    continue
            else:
                z_val = geo.center.z if hasattr(geo, 'center') else edge.pointOnEdge.z
                if abs(z_val - target_z) > tol:
                    continue

        matched.append(edge)
    return matched


def _edge_on_sketch_plane(edge, sk, tol=1e-4):
    """True when the edge lies in the sketch's plane (checked at its ends, a middle point and,
    for arcs and circles, the center)."""
    o, xd, yd = sk.origin, sk.xDirection, sk.yDirection
    n = (xd.y * yd.z - xd.z * yd.y, xd.z * yd.x - xd.x * yd.z, xd.x * yd.y - xd.y * yd.x)
    pts = [edge.pointOnEdge]
    for v in ('startVertex', 'endVertex'):
        vert = getattr(edge, v, None)
        if vert is not None:
            pts.append(vert.geometry)
    if hasattr(edge.geometry, 'center'):
        pts.append(edge.geometry.center)
    return all(abs((p.x - o.x) * n[0] + (p.y - o.y) * n[1] + (p.z - o.z) * n[2]) < tol for p in pts)


def _select_faces(body, sel):
    import adsk.core
    if isinstance(sel, str):
        if sel == 'top':
            sel = {'normal': '+z'}
        elif sel == 'bottom':
            sel = {'normal': '-z'}
        elif sel == 'none':
            return []
        elif sel == 'all':
            return [body.faces.item(k) for k in range(body.faces.count)]
        else:
            raise ValueError(f"unknown face selector '{sel}'")
    elif not isinstance(sel, dict):
        raise ValueError("face selector must be a string or object")

    matched = []
    norm_spec = sel.get('normal', '').lower()
    for k in range(body.faces.count):
        face = body.faces.item(k)
        if face.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            continue
        try:
            _, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
        except Exception:
            normal = face.geometry.normal

        match = False
        if norm_spec == '+z' and normal.z > 0.8:
            match = True
        elif norm_spec == '-z' and normal.z < -0.8:
            match = True
        elif norm_spec == '+x' and normal.x > 0.8:
            match = True
        elif norm_spec == '-x' and normal.x < -0.8:
            match = True
        elif norm_spec == '+y' and normal.y > 0.8:
            match = True
        elif norm_spec == '-y' and normal.y < -0.8:
            match = True

        if match:
            matched.append(face)

    if norm_spec == '+z' and len(matched) > 1 and sel.get('at', 'top') == 'top':
        max_z = max(f.boundingBox.maxPoint.z for f in matched)
        matched = [f for f in matched if abs(f.boundingBox.maxPoint.z - max_z) < 0.05]
    elif norm_spec == '-z' and len(matched) > 1 and sel.get('at', 'bottom') == 'bottom':
        min_z = min(f.boundingBox.minPoint.z for f in matched)
        matched = [f for f in matched if abs(f.boundingBox.minPoint.z - min_z) < 0.05]

    return matched


def _is_cylindrical_face_internal(face):
    """Return True if cylindrical face is an internal hole/bore, False if external shaft/boss."""
    import adsk.core
    geom = face.geometry
    pt = face.pointOnFace
    orig = geom.origin
    axis = geom.axis.copy()
    axis.normalize()
    v = orig.vectorTo(pt)
    proj = axis.copy()
    proj.scaleBy(v.dotProduct(axis))
    v.subtract(proj)
    try:
        _, normal = face.evaluator.getNormalAtPoint(pt)
    except Exception:
        normal = None
    if normal and v.length > 1e-6:
        return normal.dotProduct(v) < 0
    return True


def _select_cylindrical_faces(body_or_feat, target_type='all', dia_cm=None, tol=0.05):
    import adsk.core
    matched = []
    faces = getattr(body_or_feat, 'faces', None)
    if not faces:
        return []
    for k in range(faces.count):
        face = faces.item(k)
        if face.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
            continue
        cyl = face.geometry
        face_dia_cm = cyl.radius * 2.0
        if dia_cm is not None and abs(face_dia_cm - dia_cm) > tol:
            continue
        is_int = _is_cylindrical_face_internal(face)
        if target_type == 'internal' and not is_int:
            continue
        if target_type == 'external' and is_int:
            continue
        matched.append((face, is_int, face_dia_cm))
    return matched


def disambiguate_parameters(d, existing_names):
    """If any parameter in d already exists in existing_names, prefix d's parameters to avoid collision."""
    params = d.get('parameters', {})
    if not params or not existing_names:
        return d

    colliding = set(params.keys()) & set(existing_names)
    if not colliding:
        return d

    base = d.get('name') or 'part'
    idx = 2
    while True:
        prefix = f'{base}{idx}'
        candidates = {f'{prefix}_{k}' for k in params}
        if not (candidates & set(existing_names)):
            break
        idx += 1

    param_map = {k: f'{prefix}_{k}' for k in params}
    keys_by_len = sorted(param_map.keys(), key=len, reverse=True)
    pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in keys_by_len) + r')\b')

    def remap_val(v):
        if isinstance(v, str):
            return pattern.sub(lambda m: param_map[m.group(0)], v)
        elif isinstance(v, list):
            return [remap_val(item) for item in v]
        elif isinstance(v, dict):
            return {k: remap_val(item) for k, item in v.items()}
        return v

    return {
        **d,
        'parameters': {param_map[k]: remap_val(v) for k, v in params.items()},
        'timeline': [remap_val(step) for step in d['timeline']],
    }


def _is_angle_param(name, expr, valid_as_length):
    """An angle parameter: its name says so, or it mentions deg/rad and isn't a length
    ("pitch_r * cos(20 deg)" is a length)."""
    if 'angle' in name.lower():
        return True
    mentions = re.search(r'\b(deg|rad)\b', expr.lower()) is not None
    return mentions and not valid_as_length


def _eval_count(v, um=None, params=None, default=5.0):
    """Evaluate a unitless number, parameter name, or expression into a float count."""
    if v is None:
        return default
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        pass
    if um is not None:
        try:
            return float(um.evaluateExpression(s, ''))
        except Exception:
            pass
    if params and s in params:
        raw = params[s]
        try:
            return float(re.sub(r'[^\d.]', '', str(raw)).strip() or default)
        except Exception:
            pass
    clean = re.sub(r'[^\d.]', '', s).strip()
    return float(clean) if clean else default


def find_group(design, group_name):
    """The timeline group with this exact name, or None."""
    tl = design.timeline
    for k in range(tl.timelineGroups.count):
        g = tl.timelineGroups.item(k)
        if g.name == group_name:
            return g
    return None


_find_group = find_group


def user_features_after(design, group_name):
    """Count timeline items after `group_name` that VibeShaper didn't make (they may depend on it).

    Returns 0 when the group is missing or the timeline can't be inspected.
    """
    try:
        g = _find_group(design, group_name)
        if not g or g.count == 0:
            return 0
        last_index = g.item(g.count - 1).index
        tl = design.timeline
        n = 0
        for k in range(tl.count):
            obj = tl.item(k)
            if obj.isGroup or obj.index <= last_index:
                continue
            parent = obj.parentGroup
            if parent and str(parent.name).startswith('VibeShaper'):
                continue
            n += 1
        return n
    except Exception:
        return 0


def _find_entity(design, token):
    """The still-valid entity for a saved token, or None."""
    if not token:
        return None
    try:
        for e in design.findEntityByToken(token):
            if e is not None and getattr(e, 'isValid', True):
                return e
    except Exception:
        pass
    return None


class ComponentsNotAllowed(RuntimeError):
    """This document can't hold another component (a Part Design document)."""


def supports_components(design):
    """False for Part Design documents, which hold a single component."""
    try:
        import adsk.fusion
        part = adsk.fusion.DesignIntentTypes.PartDesignIntentType
    except Exception:
        return True  # Fusion versions without design intents allow components
    try:
        return design.designIntent != part
    except Exception:
        return True


def ensure_component(design, occ_token, name):
    """The chat's own component occurrence: the saved one if it still exists, else a new one.

    Created outside the version's timeline group, so replacing a version keeps the
    component (and its position, joints and appearance).
    Raises ComponentsNotAllowed when the document can't hold another component.
    """
    occ = _find_entity(design, occ_token)
    if occ is not None:
        return occ
    import adsk.core
    try:
        occ = design.rootComponent.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    except RuntimeError as e:
        if 'only contain one component' in str(e):
            raise ComponentsNotAllowed(str(e)) from e
        raise
    try:
        occ.component.name = name
    except Exception:
        pass
    return occ


class ReplaceError(RuntimeError):
    """The previous version couldn't be removed. Not the design's fault, so not for the model to fix."""


def _delete_group_contents(design, g):
    """Delete a timeline group and everything in it. Returns False if Fusion refuses."""
    try:
        if g.deleteMe(True):
            return True
    except Exception:
        pass  # Fusion sometimes fails here ("InternalValidationError : res"); go item by item
    items = [g.item(k) for k in range(g.count)]
    try:
        for it in reversed(items):  # newest first, so nothing still depends on what we delete
            ent = it.entity
            if ent is None or not ent.deleteMe():
                return False
    except Exception:
        return False
    try:
        if _find_group(design, g.name):
            g.deleteMe(False)  # drop the now-empty group if Fusion kept it
    except Exception:
        pass
    return True


def delete_version(design, group_name, param_names=()):
    """Remove a previous build: its timeline group (with contents) and its user parameters.

    Call inside the same command as the rebuild so a failed rebuild rolls this back too.
    Returns 'deleted', 'suppressed' (Fusion wouldn't delete it, so it is switched off
    instead) or False when the group no longer exists. Raises ReplaceError if neither works.
    """
    found = False
    g = _find_group(design, group_name) if group_name else None
    if g:
        try:
            design.timeline.moveToEnd()  # deleting with the marker rolled back can fail
        except Exception:
            pass
        if _delete_group_contents(design, g):
            found = 'deleted'
        else:
            g = _find_group(design, group_name)
            try:
                if g:
                    g.isSuppressed = True
            except Exception as e:
                raise ReplaceError(f'could not remove the previous version {group_name!r}: {e}')
            found = 'suppressed'
    for name in param_names:
        try:
            p = design.userParameters.itemByName(name)
            if p:
                p.deleteMe()  # returns False if still used elsewhere; that's fine
        except Exception:
            pass
    return found


def execute(design, d, group_name='VibeShaper', comp=None):
    """Build parameters + timeline in `design`, grouped as one timeline group.

    comp: component to build in (default: the root component).

    Returns {'group_name', 'param_map' (DSL name -> Fusion name), 'feature_count'}.
    """
    import adsk.core
    import adsk.fusion

    if isinstance(design, dict):
        d, design = design, d

    d = expand_shapes(d)
    validate(d)
    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        raise ValueError('Design must be parametric (Capture Design History on)')

    try:
        user_params = design.userParameters
        existing_names = {user_params.item(k).name for k in range(user_params.count)}
    except Exception:
        existing_names = set()
    orig_param_names = list(d.get('parameters', {}))
    d = disambiguate_parameters(d, existing_names)
    param_map = dict(zip(orig_param_names, d.get('parameters', {})))

    um = design.unitsManager
    root = comp or design.rootComponent
    P = adsk.core.Point3D.create

    def ex(v, unit='mm'):
        s = str(v).strip()
        for u in (unit, 'deg', '', 'mm'):
            if um.isValidExpression(s, u):
                return s
        raise ValueError(f'invalid expression {s!r}')

    def cm(v):
        return um.evaluateExpression(ex(v), 'mm')

    def angle_ex(v):
        s = str(v).strip()
        if s.replace('.', '', 1).lstrip('-').isdigit():
            s = f'{s} deg'
        return ex(s, 'deg')

    def eval_count(v, default=5.0):
        return _eval_count(v, um=um, params=d.get('parameters', {}), default=default)

    tl = design.timeline
    start = tl.markerPosition

    for name, expr in d.get('parameters', {}).items():
        try:
            s_expr = str(expr).strip()
            is_count = any(w in name.lower() for w in ('qty', 'count', 'num', 'instances', 'copies', 'repeat'))
            is_angle = _is_angle_param(name, s_expr, um.isValidExpression(s_expr, 'mm'))

            if is_angle:
                u = 'deg'
                val_expr = angle_ex(s_expr)
            elif is_count:
                u = ''
                val_expr = re.sub(r'\s*(mm|cm|in|deg)\b', '', s_expr).strip()
            elif any(s_expr.lower().endswith(un) for un in ('mm', 'cm', 'm', 'in')):
                u = 'mm'
                val_expr = ex(s_expr, 'mm')
            else:
                if um.isValidExpression(s_expr, 'deg') and not um.isValidExpression(s_expr, 'mm'):
                    u = 'deg'
                    val_expr = ex(s_expr, 'deg')
                elif is_count or (um.isValidExpression(s_expr, '') and not any(c.isalpha() for c in s_expr)):
                    u = ''
                    val_expr = s_expr
                else:
                    u = 'mm'
                    val_expr = ex(s_expr, 'mm')

            p = design.userParameters.itemByName(name)
            if p and p.unit != u:
                p.deleteMe()
                p = None
            if p:
                p.expression = val_expr
            else:
                design.userParameters.add(name, adsk.core.ValueInput.createByString(val_expr), u, '')
        except Exception as e:
            raise ValueError(f'parameters.{name}: {e}') from e

    base = {'xy': root.xYConstructionPlane, 'xz': root.xZConstructionPlane, 'yz': root.yZConstructionPlane}
    axes_map = {'x': root.xConstructionAxis, 'y': root.yConstructionAxis, 'z': root.zConstructionAxis}
    ops = {
        'new_body': adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
        'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
        'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    }
    world = {'xy': lambda a, b: (a, b, 0), 'xz': lambda a, b: (a, 0, b), 'yz': lambda a, b: (0, a, b)}


    sketches = {}
    features = {}
    last_feature = None

    for i, s in enumerate(d['timeline']):
        try:
            op = s['op']
            if op == 'sketch':
                plane = base[s['plane']]
                off = s.get('offset')
                if off not in (None, 0, '0', '0 mm'):
                    pi = root.constructionPlanes.createInput()
                    pi.setByOffset(plane, adsk.core.ValueInput.createByString(ex(off)))
                    plane = root.constructionPlanes.add(pi)
                sk = root.sketches.add(plane)
                sk.name = str(s['id'])
                to_world = world[s['plane']]

                def pt(a, b, sk=sk, to_world=to_world):
                    p = sk.modelToSketchSpace(P(*to_world(a, b)))
                    p.z = 0
                    return p

                ent_map = {}
                for e in s['entities']:
                    _draw(sk, e, ex, cm, pt, ent_map)

                # Process explicit sketch constraints
                for c in s.get('constraints', []):
                    ctype = c.get('type')
                    ents = c.get('entities', [])
                    try:
                        if ctype == 'perpendicular' and len(ents) >= 2:
                            sk.geometricConstraints.addPerpendicular(ent_map[ents[0]], ent_map[ents[1]])
                        elif ctype == 'parallel' and len(ents) >= 2:
                            sk.geometricConstraints.addParallel(ent_map[ents[0]], ent_map[ents[1]])
                        elif ctype == 'concentric' and len(ents) >= 2:
                            sk.geometricConstraints.addConcentric(ent_map[ents[0]], ent_map[ents[1]])
                        elif ctype == 'tangent' and len(ents) >= 2:
                            sk.geometricConstraints.addTangent(ent_map[ents[0]], ent_map[ents[1]])
                        elif ctype == 'equal' and len(ents) >= 2:
                            sk.geometricConstraints.addEqual(ent_map[ents[0]], ent_map[ents[1]])
                        elif ctype == 'coincident':
                            e1 = ent_map.get(c.get('entity1') or (ents[0] if ents else None))
                            e2 = ent_map.get(c.get('entity2') or (ents[1] if len(ents) > 1 else None))
                            if e1 and e2:
                                sk.geometricConstraints.addCoincident(e1, e2)
                        elif ctype == 'midpoint':
                            pt_ent = ent_map.get(c.get('point') or (ents[0] if ents else None))
                            crv_ent = ent_map.get(c.get('entity') or (ents[1] if len(ents) > 1 else None))
                            if pt_ent and crv_ent:
                                sk.geometricConstraints.addMidPoint(pt_ent, crv_ent)
                        elif ctype == 'symmetry' and len(ents) >= 2:
                            sym_line = ent_map.get(c.get('symmetry_line') or c.get('line'))
                            if sym_line:
                                sk.geometricConstraints.addSymmetry(ent_map[ents[0]], ent_map[ents[1]], sym_line)
                    except Exception:
                        pass

                # Never fix geometry: fixed curves ignore later parameter changes.
                sketches[s['id']] = sk

            elif op == 'extrude':
                sk = sketches[s['sketch']]
                if sk.profiles.count == 0:
                    raise ValueError(f'sketch {s["sketch"]!r} has no closed profiles')
                profs = adsk.core.ObjectCollection.create()
                for k in range(sk.profiles.count):
                    profs.add(sk.profiles.item(k))
                feats = root.features.extrudeFeatures
                inp = feats.createInput(profs, ops[s.get('mode', 'new_body')])
                inp.setDistanceExtent(False, adsk.core.ValueInput.createByString(ex(s['distance'])))
                feat = feats.add(inp)
                feat_id = s.get('id', s['sketch'])
                features[feat_id] = feat
                last_feature = feat

            elif op == 'revolve':
                sk = sketches[s['sketch']]
                if sk.profiles.count == 0:
                    raise ValueError(f'sketch {s["sketch"]!r} has no closed profiles')
                profs = adsk.core.ObjectCollection.create()
                for k in range(sk.profiles.count):
                    profs.add(sk.profiles.item(k))
                revolves = root.features.revolveFeatures
                axis = axes_map[s.get('axis', 'z').lower()]
                inp = revolves.createInput(profs, axis, ops[s.get('mode', 'new_body')])
                angle_str = str(s.get('angle', '360 deg'))
                inp.setAngleExtent(False, adsk.core.ValueInput.createByString(angle_ex(angle_str)))
                feat = revolves.add(inp)
                feat_id = s.get('id', s['sketch'])
                features[feat_id] = feat
                last_feature = feat

            elif op == 'fillet':
                body = _get_body(root, s.get('target'), features)
                edges = _select_edges(body, s.get('edges', 'all'), features, sketches)
                if not edges:
                    raise ValueError(f"no edges matched selector {s.get('edges')!r}")
                col = adsk.core.ObjectCollection.create()
                for e in edges:
                    col.add(e)
                fillets = root.features.filletFeatures
                rad = s.get('radius') or s.get('distance')
                inp = fillets.createInput()
                inp.addConstantRadiusEdgeSet(col, adsk.core.ValueInput.createByString(ex(rad)), True)
                feat = fillets.add(inp)
                feat_id = s.get('id', f'_fillet_{i}')
                features[feat_id] = feat
                last_feature = feat

            elif op == 'chamfer':
                body = _get_body(root, s.get('target'), features)
                edges = _select_edges(body, s.get('edges', 'all'), features, sketches)
                if not edges:
                    raise ValueError(f"no edges matched selector {s.get('edges')!r}")
                col = adsk.core.ObjectCollection.create()
                for e in edges:
                    col.add(e)
                dist = s.get('distance') or s.get('radius')
                chamfers = root.features.chamferFeatures
                if hasattr(chamfers, 'createInput2'):
                    inp = chamfers.createInput2()
                    inp.chamferEdgeSets.addEqualDistanceChamferEdgeSet(col, adsk.core.ValueInput.createByString(ex(dist)), True)
                else:
                    inp = chamfers.createInput(col, True)
                    inp.setToEqualDistance(adsk.core.ValueInput.createByString(ex(dist)))
                feat = chamfers.add(inp)
                feat_id = s.get('id', f'_chamfer_{i}')
                features[feat_id] = feat
                last_feature = feat

            elif op == 'shell':
                body = _get_body(root, s.get('target'), features)
                faces = _select_faces(body, s.get('remove_faces', 'top'))
                col = adsk.core.ObjectCollection.create()
                for f in faces:
                    col.add(f)
                if col.count == 0:
                    col.add(body)
                shells = root.features.shellFeatures
                inp = shells.createInput(col, False)
                inp.insideThickness = adsk.core.ValueInput.createByString(ex(s['thickness']))
                feat = shells.add(inp)
                feat_id = s.get('id', f'_shell_{i}')
                features[feat_id] = feat
                last_feature = feat

            elif op == 'circular_pattern':
                target_feat = features.get(s['feature']) if 'feature' in s else last_feature
                if not target_feat:
                    raise ValueError('no target feature found for circular_pattern')
                input_entities = adsk.core.ObjectCollection.create()
                input_entities.add(target_feat)
                circ_patterns = root.features.circularPatternFeatures
                axis_name = s.get('axis', 'z').lower()
                center = s.get('center')
                if center and not (abs(cm(center[0])) < _EPS and abs(cm(center[1])) < _EPS):
                    plane_name = {'z': 'xy', 'x': 'yz', 'y': 'xz'}[axis_name]
                    axis = _axis_through(root, base[plane_name], world[plane_name], center,
                                         f'{s.get("id", f"pattern_{i}")}_axis', ex, cm)
                else:
                    axis = axes_map[axis_name]
                inp = circ_patterns.createInput(input_entities, axis)
                qty_clean = re.sub(r'\s*(mm|cm|in|deg)\b', '', str(s['quantity']).strip()).strip()
                inp.quantity = adsk.core.ValueInput.createByString(qty_clean)
                angle_str = str(s.get('angle', '360 deg'))
                inp.totalAngle = adsk.core.ValueInput.createByString(angle_ex(angle_str))
                inp.isSymmetric = False
                feat = circ_patterns.add(inp)
                feat_id = s.get('id', f'_circ_pat_{i}')
                features[feat_id] = feat
                last_feature = feat

            elif op == 'linear_pattern':
                target_feat = features.get(s['feature']) if 'feature' in s else last_feature
                if not target_feat:
                    raise ValueError('no target feature found for linear_pattern')
                input_entities = adsk.core.ObjectCollection.create()
                input_entities.add(target_feat)
                rect_patterns = root.features.rectangularPatternFeatures
                axis = axes_map[s.get('direction', 'x').lower()]
                qty_clean = re.sub(r'\s*(mm|cm|in|deg)\b', '', str(s['quantity']).strip()).strip()
                qty_val = adsk.core.ValueInput.createByString(qty_clean)
                dist_val = adsk.core.ValueInput.createByString(ex(s['distance']))
                inp = rect_patterns.createInput(input_entities, axis, qty_val, dist_val, adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
                if 'direction2' in s:
                    qty2 = re.sub(r'\s*(mm|cm|in|deg)\b', '', str(s['quantity2']).strip()).strip()
                    inp.setDirectionTwo(axes_map[s['direction2'].lower()],
                                        adsk.core.ValueInput.createByString(qty2),
                                        adsk.core.ValueInput.createByString(ex(s['distance2'])))
                feat = rect_patterns.add(inp)
                feat_id = s.get('id', f'_lin_pat_{i}')
                features[feat_id] = feat
                last_feature = feat

            elif op == 'thread':
                target_type = s.get('target', 'all')
                target_obj = features.get(s['feature']) if 'feature' in s else _get_body(root, s.get('target_body'), features)
                target_dia_cm = cm(s['diameter']) if 'diameter' in s else None

                # Derive target diameter from designation (e.g. M20x2.5 -> 2.0 cm) if not explicitly set
                desig_req = str(s.get('designation', '')).strip()
                if target_dia_cm is None and desig_req:
                    m_desig = re.search(r'M(\d+(?:\.\d+)?)', desig_req, re.IGNORECASE)
                    if m_desig:
                        target_dia_cm = float(m_desig.group(1)) / 10.0

                matches = _select_cylindrical_faces(target_obj, target_type, target_dia_cm, tol=0.3 if target_dia_cm else 0.05)
                if not matches:
                    raise ValueError(f"no cylindrical faces matched for thread (target={target_type})")

                groups = {}
                for face, is_int, dia_cm in matches:
                    key = (is_int, round(dia_cm, 3))
                    groups.setdefault(key, []).append((face, dia_cm))

                thread_feats = root.features.threadFeatures
                try:
                    tdq = adsk.fusion.ThreadDataQuery.create(False)
                except Exception:
                    tdq = thread_feats.threadDataQuery

                def_thread_type = tdq.defaultMetricThreadType if hasattr(tdq, 'defaultMetricThreadType') else 'ISO Metric profile'
                req_thread_type = s.get('thread_type') or def_thread_type
                is_modeled = s.get('modeled', True)

                created_any = False
                for (is_int, _), face_list in groups.items():
                    sample_dia = face_list[0][1]
                    desig = s.get('designation')
                    t_class = s.get('thread_class')

                    # If designation specified, skip cylinders that do not match its nominal size
                    if desig:
                        m_desig = re.search(r'M(\d+(?:\.\d+)?)', str(desig), re.IGNORECASE)
                        if m_desig:
                            nominal_cm = float(m_desig.group(1)) / 10.0
                            if abs(sample_dia - nominal_cm) > 0.35:
                                continue
                    if not desig:
                        try:
                            rec = tdq.recommendThreadData(sample_dia, is_int, req_thread_type)
                            if rec and rec[0]:
                                desig = rec[1]
                                if not t_class:
                                    t_class = rec[2]
                        except Exception:
                            pass

                    if not desig:
                        try:
                            sizes = tdq.allSizes(req_thread_type)
                            if sizes:
                                best_s = min(sizes, key=lambda sz: abs(um.evaluateExpression(sz, 'mm') - sample_dia * 10))
                                desigs = tdq.allDesignations(req_thread_type, best_s)
                                if desigs:
                                    desig = desigs[0]
                        except Exception:
                            pass

                    if not desig:
                        nominal_mm = int(round(sample_dia * 10))
                        desig = f"M{nominal_mm}x1" if nominal_mm < 10 else f"M{nominal_mm}x1.5"

                    if not t_class:
                        try:
                            classes = tdq.allClasses(is_int, req_thread_type, desig)
                            if classes:
                                t_class = classes[0]
                        except Exception:
                            pass
                    if not t_class:
                        t_class = "6H" if is_int else "6g"

                    thread_info = thread_feats.createThreadInfo(is_int, req_thread_type, desig, t_class)
                    faces_coll = adsk.core.ObjectCollection.create()
                    for f, _ in face_list:
                        faces_coll.add(f)

                    inp = thread_feats.createInput(faces_coll, thread_info)
                    inp.isFullLength = True
                    inp.isModeled = bool(is_modeled)
                    feat = thread_feats.add(inp)
                    feat_id = s.get('id', f'_thread_{i}')
                    features[feat_id] = feat
                    last_feature = feat
                    created_any = True

                if not created_any:
                    raise ValueError(f"no matching cylindrical faces found for thread designation {s.get('designation')!r}")

            elif op == 'mirror':
                mirrors = root.features.mirrorFeatures
                input_entities = adsk.core.ObjectCollection.create()
                is_body = False
                if 'feature' in s:
                    f = features.get(s['feature'])
                    if not f:
                        raise ValueError(f"feature {s['feature']!r} not found for mirror")
                    input_entities.add(f)
                else:
                    body = _get_body(root, s.get('target') or s.get('target_body'), features)
                    input_entities.add(body)
                    is_body = True

                plane_spec = s.get('plane', 'xz')
                if isinstance(plane_spec, str) and plane_spec.lower() in base:
                    mirror_plane = base[plane_spec.lower()]
                else:
                    ref_body = _get_body(root, None, features)
                    matched_faces = _select_faces(ref_body, plane_spec)
                    if not matched_faces:
                        raise ValueError(f"no plane or face matched for mirror plane {plane_spec!r}")
                    mirror_plane = matched_faces[0]

                inp = mirrors.createInput(input_entities, mirror_plane)
                if is_body:
                    inp.isCombine = bool(s.get('combine', True))
                feat = mirrors.add(inp)
                feat_id = s.get('id', f'_mirror_{i}')
                features[feat_id] = feat
                last_feature = feat

            elif op == 'combine':
                combines = root.features.combineFeatures
                target_body = _get_body(root, s.get('target') or s.get('target_body'), features)
                raw_tools = s.get('tools') or s.get('tool_bodies')
                if isinstance(raw_tools, str):
                    raw_tools = [raw_tools]
                tool_bodies = adsk.core.ObjectCollection.create()
                for t_name in raw_tools:
                    tool_b = _get_body(root, t_name, features)
                    if tool_b != target_body:
                        tool_bodies.add(tool_b)
                if tool_bodies.count == 0:
                    raise ValueError("no tool bodies found for combine")

                mode = s.get('mode', 'join').lower()
                op_mode = ops.get(mode, adsk.fusion.FeatureOperations.JoinFeatureOperation)
                inp = combines.createInput(target_body, tool_bodies)
                inp.operation = op_mode
                inp.isKeepToolBodies = bool(s.get('keep_tools', False))
                feat = combines.add(inp)
                feat_id = s.get('id', f'_combine_{i}')
                features[feat_id] = feat
                last_feature = feat

            elif op == 'sweep':
                prof_sk = sketches[s['sketch']]
                path_sk = sketches[s['path']]
                if prof_sk.profiles.count == 0:
                    raise ValueError(f"profile sketch {s['sketch']!r} has no closed profiles")
                profs = adsk.core.ObjectCollection.create()
                for k in range(prof_sk.profiles.count):
                    profs.add(prof_sk.profiles.item(k))
                prof_arg = prof_sk.profiles.item(0) if prof_sk.profiles.count == 1 else profs

                curves = path_sk.sketchCurves
                if curves.count == 0:
                    raise ValueError(f"path sketch {s['path']!r} has no curves")
                try:
                    path = root.features.createPath(curves.item(0), True)
                except Exception:
                    path_coll = adsk.core.ObjectCollection.create()
                    for k in range(curves.count):
                        path_coll.add(curves.item(k))
                    path = root.features.createPath(path_coll, False)

                sweeps = root.features.sweepFeatures
                mode = s.get('mode', 'new_body').lower()
                op_mode = ops.get(mode, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                inp = sweeps.createInput(prof_arg, path, op_mode)
                feat = sweeps.add(inp)
                feat_id = s.get('id', f'_sweep_{i}')
                features[feat_id] = feat
                last_feature = feat

            elif op == 'coil':
                axis_name = str(s.get('axis', 'z')).lower()
                mode = s.get('mode', 'new_body').lower()
                op_mode = ops.get(mode, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

                dia_val = s.get('diameter') or s.get('coil_dia')
                if dia_val is None and 'radius' in s:
                    R_start_cm = cm(s['radius'])
                else:
                    R_start_cm = cm(dia_val) / 2.0

                dia2_val = s.get('diameter2') or s.get('end_diameter')
                if dia2_val is not None:
                    R_end_cm = cm(dia2_val) / 2.0
                elif 'radius2' in s:
                    R_end_cm = cm(s['radius2'])
                else:
                    R_end_cm = R_start_cm

                sec_val = s.get('section_size') or s.get('wire_dia') or s.get('wire_diameter') or s.get('thickness')
                if sec_val is None and 'wire_radius' in s:
                    wire_r_cm = cm(s['wire_radius'])
                else:
                    wire_r_cm = cm(sec_val) / 2.0

                has_rev = ('revolutions' in s) or ('turns' in s)
                has_pitch = 'pitch' in s
                has_h = ('height' in s) or ('length' in s)

                num_rev = eval_count(s.get('revolutions') or s.get('turns')) if has_rev else None
                pitch_cm = cm(s['pitch']) if has_pitch else None
                height_cm = cm(s.get('height') or s.get('length')) if has_h else None

                if num_rev is not None and pitch_cm is not None:
                    height_cm = num_rev * pitch_cm
                elif num_rev is not None and height_cm is not None:
                    pitch_cm = height_cm / num_rev if num_rev > 0 else height_cm
                elif pitch_cm is not None and height_cm is not None:
                    num_rev = height_cm / pitch_cm if pitch_cm > 0 else 5.0
                elif num_rev is not None:
                    pitch_cm = max(wire_r_cm * 2.5, 0.2)
                    height_cm = num_rev * pitch_cm
                elif height_cm is not None:
                    num_rev = 5.0
                    pitch_cm = height_cm / num_rev
                else:
                    num_rev = 5.0
                    pitch_cm = max(wire_r_cm * 3.0, 0.5)
                    height_cm = num_rev * pitch_cm

                num_rev = max(0.1, num_rev)
                center = s.get('center', [0, 0, 0])
                cx = cm(center[0]) if len(center) > 0 else 0.0
                cy = cm(center[1]) if len(center) > 1 else 0.0
                cz = cm(center[2]) if len(center) > 2 else 0.0

                points_per_rev = 24
                total_points = max(16, int(round(num_rev * points_per_rev)))
                pt_coll = adsk.core.ObjectCollection.create()
                clockwise = bool(s.get('clockwise', True))
                sign = 1.0 if clockwise else -1.0

                for j in range(total_points + 1):
                    t = j / total_points
                    angle = sign * t * (2.0 * math.pi * num_rev)
                    R = R_start_cm + t * (R_end_cm - R_start_cm)
                    axial = t * height_cm

                    if axis_name == 'x':
                        px = cx + axial
                        py = cy + R * math.cos(angle)
                        pz = cz + R * math.sin(angle)
                    elif axis_name == 'y':
                        px = cx + R * math.cos(angle)
                        py = cy + axial
                        pz = cz + R * math.sin(angle)
                    else:  # 'z'
                        px = cx + R * math.cos(angle)
                        py = cy + R * math.sin(angle)
                        pz = cz + axial

                    pt_coll.add(P(px, py, pz))

                sk_path = root.sketches.add(root.xYConstructionPlane)
                sk_path.name = f"{s.get('id', f'_coil_{i}')}_path"
                spline = sk_path.sketchCurves.sketchFittedSplines.add(pt_coll)
                try:
                    spline.isFixed = True
                except Exception:
                    pass

                sweeps = root.features.sweepFeatures
                try:
                    path = root.features.createPath(spline, True)
                except Exception:
                    path = root.features.createPath(spline)

                pi = root.constructionPlanes.createInput()
                try:
                    pi.setByDistanceOnPath(path, adsk.core.ValueInput.createByReal(0.0))
                except Exception:
                    pi.setByDistanceOnPath(spline, adsk.core.ValueInput.createByReal(0.0))
                cplane = root.constructionPlanes.add(pi)

                sk_prof = root.sketches.add(cplane)
                sk_prof.name = f"{s.get('id', f'_coil_{i}')}_prof"
                sec_shape = str(s.get('section', 'circle')).lower()
                if sec_shape in ('square', 'rectangle'):
                    w = wire_r_cm
                    rect_lines = sk_prof.sketchCurves.sketchLines.addTwoPointRectangle(P(-w, -w, 0), P(w, w, 0))
                    try:
                        for k in range(rect_lines.count):
                            rect_lines.item(k).isFixed = True
                    except Exception:
                        pass
                else:
                    prof_circle = sk_prof.sketchCurves.sketchCircles.addByCenterRadius(P(0, 0, 0), wire_r_cm)
                    try:
                        sk_prof.geometricConstraints.addCoincident(prof_circle.centerSketchPoint, sk_prof.originPoint)
                        sk_prof.sketchDimensions.addDiameterDimension(prof_circle, P(wire_r_cm, wire_r_cm, 0)).parameter.expression = ex(s.get('wire_dia', str(wire_r_cm * 20) + ' mm'))
                    except Exception:
                        try:
                            prof_circle.isFixed = True
                        except Exception:
                            pass
                try:
                    if not sk_prof.isFullyConstrained:
                        for c in [sk_prof.sketchCurves.item(k) for k in range(sk_prof.sketchCurves.count)]:
                            if not c.isFullyConstrained:
                                c.isFixed = True
                except Exception:
                    pass

                prof = sk_prof.profiles.item(0)
                inp = sweeps.createInput(prof, path, op_mode)
                feat = sweeps.add(inp)
                feat_id = s.get('id', f'_coil_{i}')
                features[feat_id] = feat
                last_feature = feat

        except Exception as e:
            raise ValueError(f'timeline[{i}] ({s["op"]}): {e}') from e

    end = tl.markerPosition - 1
    made_group = None
    if end >= start:
        try:
            tl.timelineGroups.add(start, end).name = group_name
            made_group = group_name
        except Exception:
            pass  # a single item can't always be grouped
    return {'group_name': made_group, 'param_map': param_map, 'feature_count': max(0, end - start + 1)}


_EPS = 1e-7  # cm


def _try(fn, *args):
    try:
        fn(*args)
        return True
    except Exception:
        return False


def _as_list(got):
    """An entity's curves as a list (one curve, a list, or a Fusion collection)."""
    if isinstance(got, list):
        return got
    if hasattr(got, 'count') and hasattr(got, 'item'):
        return [got.item(k) for k in range(got.count)]
    return [got]


def _arc_mid(arc):
    """The point halfway along a sketch arc, in sketch space."""
    ev = arc.geometry.evaluator
    _, t0, t1 = ev.getParameterExtents()
    _, p = ev.getPointAtParameter((t0 + t1) / 2)
    return p


def _mirror_curves(sk, src, axis):
    """Copy lines, arcs and circles across the construction line `axis`; returns the copies.

    Points on the axis are shared with the copy, so a chain that ends on the axis joins its
    mirror image. A point shared by two curves gets one mirrored point. Each new point is tied
    to its original by a symmetry constraint (a circle's or arc's size by an equal constraint).
    Curves that are their own mirror image are left alone.
    """
    import adsk.core
    P = adsk.core.Point3D.create
    curves, gc = sk.sketchCurves, sk.geometricConstraints
    a, b = axis.startSketchPoint.geometry, axis.endSketchPoint.geometry
    dx, dy = b.x - a.x, b.y - a.y
    n2 = dx * dx + dy * dy

    def refl(p):
        t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / n2
        return P(2 * (a.x + t * dx) - p.x, 2 * (a.y + t * dy) - p.y, 0)

    def on_axis(p):
        return abs((p.x - a.x) * dy - (p.y - a.y) * dx) / math.sqrt(n2) < _EPS

    def key(p):
        return round(p.x / _EPS), round(p.y / _EPS)

    def near(p, q):
        return abs(p.x - q.x) < _EPS and abs(p.y - q.y) < _EPS

    copies = {}  # an original point's position -> its mirrored sketch point

    def image(sp):
        """The sketch point that mirrors sp, if there is one already."""
        return sp if on_axis(sp.geometry) else copies.get(key(sp.geometry))

    def tie(orig, new):
        copies[key(orig.geometry)] = new
        _try(gc.addSymmetry, orig, new, axis)

    def settle(c, new):
        """If the copy came out looser than its original, tie the curves themselves too (and an
        arc's center), as Fusion's own Mirror does. Fusion refuses a constraint that adds nothing."""
        if not getattr(c, 'isFullyConstrained', False) or getattr(new, 'isFullyConstrained', True):
            return
        _try(gc.addSymmetry, c, new, axis)
        if not new.isFullyConstrained and hasattr(c, 'centerSketchPoint'):
            _try(gc.addSymmetry, c.centerSketchPoint, new.centerSketchPoint, axis)

    made = []
    for c in src:
        if c is axis or getattr(c, 'isConstruction', False):
            continue
        kind = getattr(c, 'objectType', type(c).__name__)
        if 'Circle' in kind:
            cp = c.centerSketchPoint
            if on_axis(cp.geometry):
                continue
            new = curves.sketchCircles.addByCenterRadius(refl(cp.geometry), c.radius)
            tie(cp, new.centerSketchPoint)
            _try(gc.addEqual, c, new)
        elif 'Arc' in kind:
            s0, s1 = c.startSketchPoint, c.endSketchPoint
            mid = _arc_mid(c)
            if on_axis(mid) and near(refl(s0.geometry), s1.geometry):
                continue
            ims = [image(s0), image(s1)]
            new = curves.sketchArcs.addByThreePoints(refl(s0.geometry), refl(mid), refl(s1.geometry))
            n0, n1 = new.startSketchPoint, new.endSketchPoint
            if not near(n0.geometry, refl(s0.geometry)):  # Fusion may start the arc at either end
                n0, n1 = n1, n0
            for orig, im, np_ in ((s0, ims[0], n0), (s1, ims[1], n1)):
                if im is None:
                    tie(orig, np_)
                else:
                    _try(gc.addCoincident, np_, im)
            _try(gc.addEqual, c, new)
        elif 'Line' in kind:
            s0, s1 = c.startSketchPoint, c.endSketchPoint
            if on_axis(s0.geometry) and on_axis(s1.geometry):
                continue
            ims = [image(s0), image(s1)]
            new = curves.sketchLines.addByTwoPoints(*[im if im is not None else refl(sp.geometry)
                                                      for sp, im in zip((s0, s1), ims)])
            for orig, im, np_ in ((s0, ims[0], new.startSketchPoint), (s1, ims[1], new.endSketchPoint)):
                if im is None:
                    tie(orig, np_)
        else:
            continue
        settle(c, new)
        made.append(new)
    return made


def _len_ex(ex, v):
    """A length expression for a dimension; a bare number means mm."""
    if isinstance(v, (int, float)):
        return f'{v} mm'
    s = str(v).strip()
    try:
        float(s)
        return f'{s} mm'
    except ValueError:
        return ex(s)


def _span_ex(ex, ea, va, eb, vb):
    """Expression for the distance |b - a| along one axis. Sketch distances are never negative."""
    if abs(va) < _EPS:
        e, v = _len_ex(ex, eb), vb
    elif abs(vb) < _EPS:
        e, v = _len_ex(ex, ea), va
    elif vb >= va:
        return f'({_len_ex(ex, eb)}) - ({_len_ex(ex, ea)})'
    else:
        return f'({_len_ex(ex, ea)}) - ({_len_ex(ex, eb)})'
    return e if v >= 0 else f'-({e})'


def _axis_swap(pt):
    """True when the DSL's first coordinate runs along the sketch's vertical axis."""
    o, u = pt(0, 0), pt(1, 0)
    return abs(u.x - o.x) < abs(u.y - o.y)


def _place_points(sk, pts, coords, links, ex, cm, pt):
    """Constrain sketch points the way a person would, without fixing anything.

    pts are sketch points, coords their DSL [a, b] expressions, links the (i, j, line)
    segments between them. Axis-aligned segments get horizontal/vertical constraints.
    On each sketch axis, points joined by such a segment share a coordinate and form a
    group; each group gets exactly one dimension: the length of a segment from a group
    that is already placed, or else its distance from the origin (alignment when 0).
    """
    import adsk.core
    import adsk.fusion

    gc, dims = sk.geometricConstraints, sk.sketchDimensions
    O = adsk.fusion.DimensionOrientations
    P = adsk.core.Point3D.create
    origin = sk.originPoint
    n = len(pts)
    idx = (1, 0) if _axis_swap(pt) else (0, 1)  # sketch axis k -> DSL coordinate index
    vals = [[cm(c[idx[k]]) for k in (0, 1)] for c in coords]
    exprs = [[c[idx[k]] for k in (0, 1)] for c in coords]

    par = [list(range(n)), list(range(n))]

    def find(k, i):
        while par[k][i] != i:
            par[k][i] = par[k][par[k][i]]
            i = par[k][i]
        return i

    spans = ([], [])  # spans[k]: segments that measure a length along sketch axis k
    for i, j, line in links:
        same = [abs(vals[i][k] - vals[j][k]) < _EPS for k in (0, 1)]
        if all(same):
            continue
        if same[1]:  # same y: horizontal
            _try(gc.addHorizontal, line)
            par[1][find(1, i)] = find(1, j)
            spans[0].append((i, j))
        elif same[0]:  # same x: vertical
            _try(gc.addVertical, line)
            par[0][find(0, i)] = find(0, j)
            spans[1].append((i, j))

    placed = (set(), set())
    for i in range(n):
        if abs(vals[i][0]) < _EPS and abs(vals[i][1]) < _EPS and _try(gc.addCoincident, pts[i], origin):
            placed[0].add(find(0, i))
            placed[1].add(find(1, i))

    def dim(k, a, b, expr):
        ga, gb = a.geometry, b.geometry
        tp = P((ga.x + gb.x) / 2 + (0.5 if k else 0), (ga.y + gb.y) / 2 + (0 if k else 0.5), 0)
        orient = O.VerticalDimensionOrientation if k else O.HorizontalDimensionOrientation
        try:
            d = dims.addDistanceDimension(a, b, orient, tp)
        except Exception:
            return False
        _try(setattr, d.parameter, 'expression', expr)
        return True

    for k in (0, 1):
        align = gc.addHorizontalPoints if k else gc.addVerticalPoints
        for i in range(n):
            if find(k, i) not in placed[k] and abs(vals[i][k]) < _EPS and _try(align, pts[i], origin):
                placed[k].add(find(k, i))
        while True:
            progress = True
            while progress:
                progress = False
                for i, j in spans[k]:
                    gi, gj = find(k, i), find(k, j)
                    if (gi in placed[k]) == (gj in placed[k]):
                        continue
                    if dim(k, pts[i], pts[j], _span_ex(ex, exprs[i][k], vals[i][k], exprs[j][k], vals[j][k])):
                        placed[k].update((gi, gj))
                        progress = True
            rest = [i for i in range(n) if find(k, i) not in placed[k]]
            if not rest:
                break
            i = rest[0]
            dim(k, pts[i], origin, _span_ex(ex, 0, 0.0, exprs[i][k], vals[i][k]))
            placed[k].add(find(k, i))  # even if it failed, so the loop ends


def _axis_through(root, plane, to_world, center, name, ex, cm):
    """A hidden construction axis normal to `plane` through `center` (plane coordinates).

    It runs through a dimensioned point on the plane and on a parallel plane, so it moves
    when the parameters in `center` change.
    """
    import adsk.core

    P = adsk.core.Point3D.create
    points = []
    for off in (None, '10 mm'):
        sk_plane = plane
        if off:
            pi = root.constructionPlanes.createInput()
            pi.setByOffset(plane, adsk.core.ValueInput.createByString(off))
            sk_plane = root.constructionPlanes.add(pi)
            _try(setattr, sk_plane, 'isLightBulbOn', False)
        sk = root.sketches.add(sk_plane)
        sk.name = name

        def pt(a, b, sk=sk):
            p = sk.modelToSketchSpace(P(*to_world(a, b)))
            p.z = 0
            return p

        point = sk.sketchPoints.add(pt(cm(center[0]), cm(center[1])))
        _place_points(sk, [point], [center], [], ex, cm, pt)
        _try(setattr, sk, 'isVisible', False)
        points.append(point)
    ai = root.constructionAxes.createInput()
    ai.setByTwoPoints(points[0], points[1])
    axis = root.constructionAxes.add(ai)
    _try(setattr, axis, 'isLightBulbOn', False)
    return axis


def _draw(sk, e, ex, cm, pt, ent_map=None):
    """pt(a, b): DSL plane coords (cm, world-aligned) -> sketch-space Point3D."""
    import adsk.core
    import adsk.fusion

    P = adsk.core.Point3D.create
    curves, dims, gc = sk.sketchCurves, sk.sketchDimensions, sk.geometricConstraints
    O = adsk.fusion.DimensionOrientations
    t = e['type']
    eid = e.get('id') if ent_map is not None else None

    def place(points, coords, links=()):
        _place_points(sk, points, coords, list(links), ex, cm, pt)

    if t == 'circle':
        r = cm(e['diameter']) / 2
        c = pt(cm(e['center'][0]), cm(e['center'][1]))
        circle = curves.sketchCircles.addByCenterRadius(c, r)
        try:
            dims.addDiameterDimension(circle, P(c.x + r, c.y + r, 0)).parameter.expression = ex(e['diameter'])
        except Exception:
            pass
        place([circle.centerSketchPoint], [e['center']])
        if eid:
            ent_map[eid] = circle
            ent_map[f'{eid}.center'] = circle.centerSketchPoint

    elif t == 'center_rectangle':
        # What Fusion's own center rectangle has: horizontal/vertical sides, a construction
        # diagonal with the center at its midpoint, and width/height dimensions.
        cx, cy = cm(e['center'][0]), cm(e['center'][1])
        w, h = cm(e['width']), cm(e['height'])
        c, corner = pt(cx, cy), pt(cx + w / 2, cy + h / 2)
        made = curves.sketchLines.addCenterPointRectangle(c, corner)
        ls = [made.item(k) for k in range(made.count)]
        ls = [l for l in ls if not getattr(l, 'isConstruction', False)] or ls
        horiz, vert = [], []
        for l in ls:
            a, b = l.startSketchPoint.geometry, l.endSketchPoint.geometry
            if abs(a.y - b.y) < 1e-6:
                horiz.append(l)
                _try(gc.addHorizontal, l)
            else:
                vert.append(l)
                _try(gc.addVertical, l)
        hx, vx = (e['height'], e['width']) if _axis_swap(pt) else (e['width'], e['height'])
        sx, sy = abs(corner.x - c.x), abs(corner.y - c.y)
        if horiz:
            l = horiz[0]
            _try(lambda: setattr(dims.addDistanceDimension(
                l.startSketchPoint, l.endSketchPoint, O.HorizontalDimensionOrientation,
                P(c.x, c.y + sy + 1, 0)).parameter, 'expression', ex(hx)))
        if vert:
            l = vert[0]
            _try(lambda: setattr(dims.addDistanceDimension(
                l.startSketchPoint, l.endSketchPoint, O.VerticalDimensionOrientation,
                P(c.x + sx + 1, c.y, 0)).parameter, 'expression', ex(vx)))
        a = ls[0].startSketchPoint
        b = next((l.startSketchPoint for l in ls
                  if abs(l.startSketchPoint.geometry.x - a.geometry.x) > 1e-6
                  and abs(l.startSketchPoint.geometry.y - a.geometry.y) > 1e-6), None)
        center = sk.sketchPoints.add(c)
        if b:
            try:
                diag = curves.sketchLines.addByTwoPoints(a, b)
                diag.isConstruction = True
                gc.addMidPoint(center, diag)
            except Exception:
                pass
        place([center], [e['center']])
        if eid:
            ent_map[eid] = ls
            ent_map[f'{eid}.center'] = center

    elif t == 'regular_polygon':
        # What Fusion's polygon tool makes: vertices on a construction circle, equal sides,
        # one side horizontal (the bottom one, in DSL coordinates), and the circle's diameter.
        n = int(float(e['sides']))
        cx, cy = cm(e['center'][0]), cm(e['center'][1])
        if 'diameter' in e:
            dia_ex = ex(e['diameter'])
            r = cm(e['diameter']) / 2
        else:
            dia_ex = f'({_len_ex(ex, e["across_flats"])}) / cos(180 deg / {n})'
            r = cm(e['across_flats']) / 2 / math.cos(math.pi / n)
        verts = []
        for k in range(n):
            ang = -math.pi / 2 - math.pi / n + 2 * math.pi * k / n
            verts.append(pt(cx + r * math.cos(ang), cy + r * math.sin(ang)))
        c = pt(cx, cy)
        circle = curves.sketchCircles.addByCenterRadius(c, r)
        circle.isConstruction = True
        lines = [curves.sketchLines.addByTwoPoints(verts[0], verts[1])]
        for v in verts[2:]:
            lines.append(curves.sketchLines.addByTwoPoints(lines[-1].endSketchPoint, v))
        lines.append(curves.sketchLines.addByTwoPoints(lines[-1].endSketchPoint, lines[0].startSketchPoint))
        for l in lines:
            _try(gc.addCoincident, l.startSketchPoint, circle)
        for l in lines[1:]:
            _try(gc.addEqual, lines[0], l)
        a, b = lines[0].startSketchPoint.geometry, lines[0].endSketchPoint.geometry
        _try(gc.addHorizontal if abs(a.y - b.y) < abs(a.x - b.x) else gc.addVertical, lines[0])
        try:
            dims.addDiameterDimension(circle, P(c.x + r, c.y + r, 0)).parameter.expression = dia_ex
        except Exception:
            pass
        place([circle.centerSketchPoint], [e['center']])
        if eid:
            ent_map[eid] = lines
            ent_map[f'{eid}.center'] = circle.centerSketchPoint
            for idx, l in enumerate(lines):
                ent_map[f'{eid}.{idx}'] = l

    elif t == 'line':
        p1 = pt(cm(e['start'][0]), cm(e['start'][1]))
        p2 = pt(cm(e['end'][0]), cm(e['end'][1]))
        line = curves.sketchLines.addByTwoPoints(p1, p2)
        place([line.startSketchPoint, line.endSketchPoint], [e['start'], e['end']], [(0, 1, line)])
        if eid:
            ent_map[eid] = line
            ent_map[f'{eid}.start'] = line.startSketchPoint
            ent_map[f'{eid}.end'] = line.endSketchPoint

    elif t == 'profile':
        # Lines and three-point arcs, end to end. Shared corners are one sketch point, each
        # arc's middle point sits on the arc, and every point is placed by dimensions.
        def at(xy):
            return pt(cm(xy[0]), cm(xy[1]))

        def same(a, b):
            return abs(cm(a[0]) - cm(b[0])) < _EPS and abs(cm(a[1]) - cm(b[1])) < _EPS

        def dist(a, b):
            return math.hypot(a.x - b.x, a.y - b.y)

        segs = e['segments']
        verts, coords, mids, links, made = [], [e['start']], [], [], []
        prev = None
        for k, sg in enumerate(segs):
            closing = k == len(segs) - 1 and same(sg['to'], e['start'])
            a = prev if prev is not None else at(e['start'])
            if 'through' in sg:
                ag = a.geometry if prev is not None else a
                bg = verts[0].geometry if closing else at(sg['to'])
                arc = curves.sketchArcs.addByThreePoints(ag, at(sg['through']), bg)
                s_pt, e_pt = arc.startSketchPoint, arc.endSketchPoint
                if dist(s_pt.geometry, ag) > dist(e_pt.geometry, ag):
                    s_pt, e_pt = e_pt, s_pt
                if prev is None:
                    verts.append(s_pt)
                else:
                    _try(gc.addCoincident, s_pt, prev)
                if closing:
                    _try(gc.addCoincident, e_pt, verts[0])
                else:
                    verts.append(e_pt)
                    coords.append(sg['to'])
                mid = sk.sketchPoints.add(at(sg['through']))
                _try(gc.addCoincident, mid, arc)
                mids.append((mid, sg['through']))
                made.append(arc)
            else:
                line = curves.sketchLines.addByTwoPoints(a, verts[0] if closing else at(sg['to']))
                if prev is None:
                    verts.append(line.startSketchPoint)
                i = len(verts) - 1
                if closing:
                    links.append((i, 0, line))
                else:
                    verts.append(line.endSketchPoint)
                    coords.append(sg['to'])
                    links.append((i, i + 1, line))
                made.append(line)
            prev = verts[0] if closing else verts[-1]
        if e.get('closed', True) and not same(segs[-1]['to'], e['start']):
            line = curves.sketchLines.addByTwoPoints(prev, verts[0])
            links.append((len(verts) - 1, 0, line))
            made.append(line)
        place(verts + [m for m, _ in mids], coords + [c for _, c in mids], links)
        if eid:
            ent_map[eid] = made
            for idx, c in enumerate(made):
                ent_map[f'{eid}.{idx}'] = c

    elif t == 'mirror':
        # The mirror line is a construction line placed like any other; the copies are tied to
        # their originals by symmetry constraints, so they follow every parameter change.
        a_xy, b_xy = e['line']
        axis = curves.sketchLines.addByTwoPoints(pt(cm(a_xy[0]), cm(a_xy[1])), pt(cm(b_xy[0]), cm(b_xy[1])))
        axis.isConstruction = True
        place([axis.startSketchPoint, axis.endSketchPoint], [a_xy, b_xy], [(0, 1, axis)])
        src = [c for ref in e['entities'] for c in _as_list(ent_map[ref])]
        made = _mirror_curves(sk, src, axis)
        if eid:
            ent_map[eid] = src + made

    else:  # polyline or polygon
        raw = e['points']
        pts = [pt(cm(x), cm(y)) for x, y in raw]
        is_closed = e.get('closed', t == 'polygon')
        lines = [curves.sketchLines.addByTwoPoints(pts[0], pts[1])]
        for p in pts[2:]:
            lines.append(curves.sketchLines.addByTwoPoints(lines[-1].endSketchPoint, p))
        if is_closed:
            lines.append(curves.sketchLines.addByTwoPoints(lines[-1].endSketchPoint, lines[0].startSketchPoint))
        n = len(raw)
        vpts = [lines[0].startSketchPoint] + [l.endSketchPoint for l in lines[:n - 1]]
        links = [(k, (k + 1) % n, lines[k]) for k in range(len(lines))]
        place(vpts, raw, links)
        if eid:
            ent_map[eid] = lines
            for idx, l in enumerate(lines):
                ent_map[f'{eid}.{idx}'] = l
