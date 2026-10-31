"""Read-only tools the model can call to look at the user's Fusion design.

Each tool takes JSON arguments and returns JSON-friendly data. Things are referred to by short
ids ('o3' occurrence, 'b5' body, 's2' sketch, 'f12' timeline feature, 'root' the root component)
that map to Fusion entity tokens; the ids are kept in this toolkit's saved state, so they stay
stable for the document.

Nothing here imports Fusion: it only reads attributes of the objects it is given, so it can be
tested with simple fakes. Lengths are mm, areas mm², volumes mm³, in world coordinates (the same
frame the design JSON uses) unless a result says otherwise.
"""
import math

from .base import BaseToolkit, ToolError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
CM = 10.0  # Fusion's internal length unit is cm

SURFACE_TYPES = {0: 'plane', 1: 'cylinder', 2: 'cone', 3: 'sphere', 4: 'torus',
                 5: 'elliptical cylinder', 6: 'elliptical cone', 7: 'freeform'}
HEALTH = {0: 'ok', 1: 'warning', 2: 'error', 3: 'unknown'}
OPERATIONS = {0: 'join', 1: 'cut', 2: 'intersect', 3: 'new body', 4: 'new component'}

_PAGING = {
    'offset': {'type': 'integer', 'description': 'Skip this many items (default 0).'},
    'limit': {'type': 'integer', 'description': f'At most this many items (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).'},
}


def _obj(props=None, required=()):
    s = {'type': 'object', 'properties': dict(props or {})}
    if required:
        s['required'] = list(required)
    return s


def _id_param(what):
    return {'type': 'string', 'description': f'Id of the {what}, from another tool (e.g. "o2", "b5", or "root").'}


TOOL_SPECS = [
    {'name': 'get_overview',
     'description': 'Start here. The document: name, units, Part or Assembly, the root component, counts of '
                    'components, bodies, sketches and timeline features, and what the user has selected.',
     'parameters': _obj()},
    {'name': 'list_components',
     'description': 'The component tree (occurrences) under a parent, with ids, positions, visibility and '
                    'how many children each has.',
     'parameters': _obj({'parent': _id_param('parent occurrence; default "root"'),
                         'depth': {'type': 'integer', 'description': 'Levels to include (default 1, max 5).'},
                         **_PAGING})},
    {'name': 'get_component',
     'description': 'What a component (or occurrence) contains: bodies, sketches, child occurrences, '
                    'construction planes, and how many timeline features belong to it.',
     'parameters': _obj({'id': _id_param('occurrence, or "root"')}, ['id'])},
    {'name': 'list_bodies',
     'description': 'Bodies directly in a component, with ids, size (bounding box), volume, material and visibility.',
     'parameters': _obj({'component': _id_param('occurrence, or "root" (default)'), **_PAGING})},
    {'name': 'get_body',
     'description': 'Details of one body: bounding box, volume, area, faces by type, its largest flat faces '
                    '(with direction), and round holes and bosses (diameter, axis, position).',
     'parameters': _obj({'id': _id_param('body')}, ['id'])},
    {'name': 'list_sketches',
     'description': 'Sketches directly in a component, with ids, what they are drawn on, profile and curve counts.',
     'parameters': _obj({'component': _id_param('occurrence, or "root" (default)'), **_PAGING})},
    {'name': 'get_sketch',
     'description': 'Contents of one sketch: what it is on, its lines, circles and arcs (in sketch '
                    'coordinates, mm), dimensions, constraint count and closed profiles.',
     'parameters': _obj({'id': _id_param('sketch'), **_PAGING}, ['id'])},
    {'name': 'get_timeline',
     'description': 'Timeline features in order (the design history), with ids, type, health and group. '
                    'Optionally only those belonging to one component.',
     'parameters': _obj({'component': _id_param('occurrence, or "root"; omit for the whole design'), **_PAGING})},
    {'name': 'get_feature',
     'description': 'Details of one timeline feature: type, component, health, bodies it affects, the '
                    'sketch it uses, its operation, and its dimensions with their expressions.',
     'parameters': _obj({'id': _id_param('feature')}, ['id'])},
    {'name': 'list_parameters',
     'description': 'Parameters with their expressions and values. kind "user" (default): the user\'s named '
                    'parameters; "model": dimensions of features; "all".',
     'parameters': _obj({'kind': {'type': 'string', 'enum': ['user', 'model', 'all']}, **_PAGING})},
    {'name': 'find',
     'description': 'Search components, bodies, sketches, features and parameters by name (case-insensitive).',
     'parameters': _obj({'text': {'type': 'string', 'description': 'Part of a name.'},
                         'kind': {'type': 'string', 'enum': ['component', 'body', 'sketch', 'feature', 'parameter']}},
                        ['text'])},
    {'name': 'get_selection',
     'description': 'What the user has selected in the canvas right now, with ids.',
     'parameters': _obj()},
    {'name': 'measure',
     'description': 'Minimum distance between two things (bodies or occurrences), in mm.',
     'parameters': _obj({'a': _id_param('first body or occurrence'), 'b': _id_param('second body or occurrence')},
                        ['a', 'b'])},
]
TOOL_NAMES = [t['name'] for t in TOOL_SPECS]


# ---------------------------------------------------------------- ids

class Refs:
    """Short ids <-> Fusion entity tokens. Works directly on `data` (the toolkit's saved state),
    so new ids are saved with the document."""
    PREFIX = {'occurrence': 'o', 'body': 'b', 'sketch': 's', 'feature': 'f'}

    def __init__(self, data=None):
        data = data if data is not None else {}
        if not isinstance(data.get('ids'), dict):
            data['ids'] = {}
        if not isinstance(data.get('next'), dict):
            data['next'] = {}
        self.ids = data['ids']    # id -> token
        self.next = data['next']  # prefix -> next number
        self._by_token = {tok: i for i, tok in self.ids.items()}

    def to_dict(self):
        return {'ids': dict(self.ids), 'next': dict(self.next)}

    def id_for(self, kind, token):
        if not token:
            return None
        if token in self._by_token:
            return self._by_token[token]
        p = self.PREFIX[kind]
        n = self.next.get(p, 1)
        self.next[p] = n + 1
        rid = f'{p}{n}'
        self.ids[rid] = token
        self._by_token[token] = rid
        return rid

    def token(self, rid):
        return self.ids.get(rid)


class Context:
    """What the tools work on. `selection`: entities selected in the canvas. `measure(a, b)`:
    minimum distance in cm (Fusion's measure manager)."""

    def __init__(self, design, refs, selection=(), measure=None):
        self.design, self.refs = design, refs
        self.selection = list(selection)
        self.measure = measure

    @classmethod
    def from_tool_context(cls, tc):
        """Built from what PromptCAD hands every toolkit: the app, the design and our saved state."""
        return cls(tc.design, Refs(tc.state.setdefault('refs', {})), _selection(tc.app),
                   lambda a, b: tc.app.measureManager.measureMinimumDistance(a, b).value)


def _selection(app):
    try:
        sels = app.userInterface.activeSelections
        return [sels.item(i).entity for i in range(sels.count)]
    except Exception:
        return []


# ---------------------------------------------------------------- helpers

def _items(coll):
    if coll is None:
        return []
    try:
        return [coll.item(i) for i in range(coll.count)]
    except AttributeError:
        return list(coll)


def _get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _mm(v):
    return round(v * CM, 3)


def _pt(p):
    return [_mm(p.x), _mm(p.y), _mm(p.z)]


def _vec(v):
    n = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) or 1.0
    return [round(v.x / n, 4), round(v.y / n, 4), round(v.z / n, 4)]


def _token(e):
    return _get(e, 'entityToken')


def _kind_name(e):
    t = str(_get(e, 'objectType', '') or type(e).__name__)
    t = t.split('::')[-1]
    for suffix in ('Feature', 'Proxy'):
        if t.endswith(suffix) and t != suffix:
            t = t[: -len(suffix)]
    return t


def _page(items, args):
    try:
        offset = max(0, int(args.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(args.get('limit') or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(MAX_LIMIT, limit))
    shown = items[offset:offset + limit]
    out = {'items': shown, 'total': len(items)}
    more = len(items) - offset - len(shown)
    if more > 0:
        out['more'] = more
        out['next_offset'] = offset + len(shown)
    return out


def _bbox(body):
    bb = _get(body, 'boundingBox')
    if not bb:
        return None
    lo, hi = _pt(bb.minPoint), _pt(bb.maxPoint)
    return {'min': lo, 'max': hi, 'size': [round(h - l, 3) for l, h in zip(lo, hi)]}


def _visible(e):
    v = _get(e, 'isVisible')
    return bool(v) if v is not None else bool(_get(e, 'isLightBulbOn', True))


# ---------------------------------------------------------------- resolving ids

def _root(ctx):
    return ctx.design.rootComponent


def _resolve(ctx, rid, kinds):
    """The entity behind an id; kinds: which of 'root', 'occurrence', 'body', 'sketch', 'feature' are allowed."""
    rid = str(rid or '').strip()
    if rid in ('', 'root'):
        if 'root' in kinds:
            return 'root', _root(ctx)
        raise ToolError(f'"{rid or "root"}" is not a {"/".join(kinds)} id.')
    tok = ctx.refs.token(rid)
    if not tok:
        raise ToolError(f'Unknown id "{rid}". Use get_overview, list_* or find to get ids.')
    kind = next((k for k, p in Refs.PREFIX.items() if rid.startswith(p)), None)
    if kind not in kinds:
        raise ToolError(f'"{rid}" is a {kind}; this tool needs a {"/".join(kinds)} id.')
    found = _items(ctx.design.findEntityByToken(tok))
    if not found:
        raise ToolError(f'"{rid}" no longer exists in the design.')
    return kind, found[0]


def _component_of(ctx, rid):
    """(component, occurrence or None) for 'root' or an occurrence id."""
    kind, e = _resolve(ctx, rid, ('root', 'occurrence'))
    return (e, None) if kind == 'root' else (e.component, e)


def _in_context(e, occ):
    """The entity as seen in the assembly (world coordinates) when it lives in an occurrence."""
    if occ is None:
        return e
    try:
        return e.createForAssemblyContext(occ)
    except Exception:
        return e


# ---------------------------------------------------------------- describing things

def _occ_info(ctx, occ):
    tr = _get(occ, 'transform2') or _get(occ, 'transform')
    pos = None
    try:
        pos = [_mm(v) for v in tr.translation.asArray()]
    except Exception:
        pass
    comp = occ.component
    return {'id': ctx.refs.id_for('occurrence', _token(occ)), 'name': occ.name, 'component': comp.name,
            'position': pos, 'visible': _visible(occ),
            'children': len(_items(_get(occ, 'childOccurrences'))),
            'bodies': len(_items(comp.bRepBodies))}


def _body_info(ctx, body):
    vol = _get(body, 'volume')
    mat = _get(body, 'material')
    return {'id': ctx.refs.id_for('body', _token(body)), 'name': body.name,
            'solid': bool(_get(body, 'isSolid', True)), 'visible': _visible(body),
            'bbox': _bbox(body), 'volume': round(vol * CM ** 3, 1) if vol is not None else None,
            'material': _get(mat, 'name') if mat else None}


def _sketch_on(sk):
    ref = _get(sk, 'referencePlane')
    if ref is None:
        return None
    kind = _kind_name(ref)
    if kind in ('BRepFace',):
        body = _get(ref, 'body')
        return f'face of {_get(body, "name", "a body")}'
    return _get(ref, 'name') or kind


def _sketch_info(ctx, sk):
    curves = _get(sk, 'sketchCurves')
    return {'id': ctx.refs.id_for('sketch', _token(sk)), 'name': sk.name, 'on': _sketch_on(sk),
            'profiles': len(_items(_get(sk, 'profiles'))), 'curves': len(_items(curves)),
            'visible': _visible(sk)}


def _feature_component(e):
    comp = _get(e, 'parentComponent')
    return _get(comp, 'name') if comp else None


def _timeline_info(ctx, item):
    e = _get(item, 'entity')
    info = {'index': _get(item, 'index'), 'name': _get(item, 'name') or _get(e, 'name'),
            'type': 'Group' if _get(item, 'isGroup') else _kind_name(e)}
    if e is not None and _token(e):
        kind = 'occurrence' if info['type'] == 'Occurrence' else 'sketch' if info['type'] == 'Sketch' else 'feature'
        info['id'] = ctx.refs.id_for(kind, _token(e))
        info['component'] = _feature_component(e)
    health = HEALTH.get(_get(item, 'healthState'), None)
    if health and health != 'ok':
        info['health'] = health
        msg = _get(item, 'errorOrWarningMessage')
        if msg:
            info['message'] = msg
    if _get(item, 'isSuppressed'):
        info['suppressed'] = True
    if _get(item, 'isRolledBack'):
        info['rolled_back'] = True
    grp = _get(item, 'parentGroup')
    if grp is not None:
        info['group'] = _get(grp, 'name')
    return info


def _param_info(p):
    out = {'name': p.name, 'expression': _get(p, 'expression'), 'unit': _get(p, 'unit')}
    by = _get(p, 'createdBy')
    if by is not None:
        out['feature'] = _get(by, 'name')
    comment = _get(p, 'comment')
    if comment:
        out['comment'] = comment
    return out


def _describe(ctx, e):
    kind = _kind_name(e)
    if kind == 'Occurrence':
        return {'kind': 'occurrence', **_occ_info(ctx, e)}
    if kind == 'BRepBody':
        return {'kind': 'body', **_body_info(ctx, e)}
    if kind == 'Sketch':
        return {'kind': 'sketch', **_sketch_info(ctx, e)}
    if kind in ('BRepFace', 'BRepEdge'):
        body = _get(e, 'body')
        out = {'kind': 'face' if kind == 'BRepFace' else 'edge',
               'body': _body_info(ctx, body)['id'] if body else None, 'body_name': _get(body, 'name')}
        if kind == 'BRepFace':
            out.update(_face_info(e))
        return out
    return {'kind': kind, 'name': _get(e, 'name')}


def _face_info(face):
    geo = _get(face, 'geometry')
    st = SURFACE_TYPES.get(_get(geo, 'surfaceType'), 'other')
    out = {'surface': st, 'area': round((_get(face, 'area') or 0) * CM * CM, 2)}
    try:
        p = face.pointOnFace
        out['point'] = _pt(p)
        ok, n = face.evaluator.getNormalAtPoint(p)
        if ok:
            out['normal'] = _vec(n)
    except Exception:
        pass
    if st == 'cylinder':
        out['diameter'] = round(geo.radius * 2 * CM, 3)
        out['axis'] = _vec(geo.axis)
        out['axis_point'] = _pt(geo.origin)
    return out


# ---------------------------------------------------------------- tools

def get_overview(ctx, args):
    d = ctx.design
    root = _root(ctx)
    intent = _get(d, 'designIntent')
    doc = _get(_get(d, 'parentDocument'), 'name')
    occs = _items(_get(root, 'allOccurrences'))
    bodies = len(_items(root.bRepBodies)) + sum(len(_items(o.component.bRepBodies)) for o in occs)
    sketches = len(_items(root.sketches)) + sum(len(_items(o.component.sketches)) for o in occs)
    um = _get(d, 'unitsManager')
    return {
        'document': doc,
        'type': {0: 'Part', 1: 'Assembly', 2: 'Hybrid'}.get(intent, 'Design'),
        'units': _get(um, 'defaultLengthUnits'),
        'note': 'Tool results use mm and world coordinates; ids work with every tool.',
        'root': {'id': 'root', 'name': root.name},
        'counts': {'occurrences': len(occs), 'bodies': bodies, 'sketches': sketches,
                   'timeline': len(_items(_get(d, 'timeline'))), 'user_parameters': len(_items(d.userParameters))},
        'selection': [_describe(ctx, e) for e in ctx.selection][:20],
    }


def list_components(ctx, args):
    comp, occ = _component_of(ctx, args.get('parent'))
    try:
        depth = max(1, min(5, int(args.get('depth') or 1)))
    except (TypeError, ValueError):
        depth = 1

    def walk(children, level):
        out = []
        for o in children:
            info = _occ_info(ctx, o)
            info['depth'] = level
            out.append(info)
            if level < depth:
                out.extend(walk(_items(_get(o, 'childOccurrences')), level + 1))
        return out

    kids = _items(occ.childOccurrences) if occ is not None else _items(comp.occurrences)
    return _page(walk(kids, 1), args)


def get_component(ctx, args):
    comp, occ = _component_of(ctx, args.get('id'))
    token = _token(comp)
    features = 0
    for item in _items(_get(ctx.design, 'timeline')):
        pc = _get(_get(item, 'entity'), 'parentComponent')
        if pc is not None and _token(pc) == token:
            features += 1
    out = {'name': comp.name,
           'bodies': [_body_info(ctx, _in_context(b, occ)) for b in _items(comp.bRepBodies)][:DEFAULT_LIMIT],
           'sketches': [_sketch_info(ctx, _in_context(s, occ)) for s in _items(comp.sketches)][:DEFAULT_LIMIT],
           'occurrences': [_occ_info(ctx, o) for o in
                           (_items(occ.childOccurrences) if occ is not None else _items(comp.occurrences))][:DEFAULT_LIMIT],
           'construction_planes': [_get(p, 'name') for p in _items(_get(comp, 'constructionPlanes'))][:DEFAULT_LIMIT],
           'timeline_features': features}
    if occ is not None:
        out.update(id=args.get('id'), occurrence=occ.name)
    else:
        out['id'] = 'root'
    return out


def list_bodies(ctx, args):
    comp, occ = _component_of(ctx, args.get('component'))
    return _page([_body_info(ctx, _in_context(b, occ)) for b in _items(comp.bRepBodies)], args)


def get_body(ctx, args):
    _, body = _resolve(ctx, args.get('id'), ('body',))
    info = _body_info(ctx, body)
    area = _get(body, 'area')
    info['area'] = round(area * CM * CM, 1) if area is not None else None
    faces = [_face_info(f) for f in _items(body.faces)]
    by_type = {}
    for f in faces:
        by_type[f['surface']] = by_type.get(f['surface'], 0) + 1
    info['faces'] = {'total': len(faces), 'by_type': by_type}
    info['edges'] = len(_items(_get(body, 'edges')))
    flat = sorted((f for f in faces if f['surface'] == 'plane'), key=lambda f: -f['area'])
    info['largest_flat_faces'] = [{k: f[k] for k in ('area', 'normal', 'point') if k in f} for f in flat[:6]]
    round_feats = []
    for f in faces:
        if f['surface'] != 'cylinder' or 'normal' not in f:
            continue
        # A hole's surface faces its axis; a boss's faces away from it.
        p, a, c, n = f['point'], f['axis'], f['axis_point'], f['normal']
        t = sum((p[i] - c[i]) * a[i] for i in range(3))
        radial = [p[i] - c[i] - t * a[i] for i in range(3)]
        kind = 'hole' if sum(radial[i] * n[i] for i in range(3)) < 0 else 'boss'
        round_feats.append({'kind': kind, 'diameter': f['diameter'], 'axis': a, 'axis_point': c, 'area': f['area']})
    info['round_features'] = round_feats[:30]
    if len(round_feats) > 30:
        info['round_features_more'] = len(round_feats) - 30
    return info


def list_sketches(ctx, args):
    comp, occ = _component_of(ctx, args.get('component'))
    return _page([_sketch_info(ctx, _in_context(s, occ)) for s in _items(comp.sketches)], args)


def get_sketch(ctx, args):
    _, sk = _resolve(ctx, args.get('id'), ('sketch',))
    info = _sketch_info(ctx, sk)
    curves = []
    sc = _get(sk, 'sketchCurves')
    for ln in _items(_get(sc, 'sketchLines')):
        curves.append({'type': 'line', 'start': _pt(ln.startSketchPoint.geometry), 'end': _pt(ln.endSketchPoint.geometry),
                       **({'construction': True} if _get(ln, 'isConstruction') else {})})
    for c in _items(_get(sc, 'sketchCircles')):
        curves.append({'type': 'circle', 'center': _pt(c.centerSketchPoint.geometry), 'diameter': _mm(c.radius * 2),
                       **({'construction': True} if _get(c, 'isConstruction') else {})})
    for a in _items(_get(sc, 'sketchArcs')):
        curves.append({'type': 'arc', 'center': _pt(a.centerSketchPoint.geometry), 'radius': _mm(a.radius),
                       'start': _pt(a.startSketchPoint.geometry), 'end': _pt(a.endSketchPoint.geometry)})
    other = len(_items(sc)) - len(curves)
    info['curves'] = _page(curves, args)
    if other > 0:
        info['other_curves'] = other  # splines, ellipses...
    dims = []
    for dim in _items(_get(sk, 'sketchDimensions')):
        prm = _get(dim, 'parameter')
        if prm is not None:
            dims.append({'name': prm.name, 'expression': _get(prm, 'expression')})
    info['dimensions'] = dims[:DEFAULT_LIMIT]
    info['constraints'] = len(_items(_get(sk, 'geometricConstraints')))
    fc = _get(sk, 'isFullyConstrained')
    if fc is not None:
        info['fully_constrained'] = bool(fc)
    return info


def get_timeline(ctx, args):
    items = _items(_get(ctx.design, 'timeline'))
    if args.get('component'):
        comp, _occ = _component_of(ctx, args['component'])
        token = _token(comp)
        items = [i for i in items if _token(_get(_get(i, 'entity'), 'parentComponent')) == token]
    return _page([_timeline_info(ctx, i) for i in items], args)


def get_feature(ctx, args):
    rid = str(args.get('id') or '')
    kinds = ('feature', 'sketch', 'occurrence')
    _, e = _resolve(ctx, rid, kinds)
    out = {'id': rid, 'name': _get(e, 'name'), 'type': _kind_name(e), 'component': _feature_component(e)}
    item = _get(e, 'timelineObject')
    if item is not None:
        t = _timeline_info(ctx, item)
        out.update({k: t[k] for k in ('index', 'health', 'message', 'suppressed', 'rolled_back', 'group') if k in t})
    op = _get(e, 'operation')
    if op is not None:
        out['operation'] = OPERATIONS.get(op, op)
    bodies = _items(_get(e, 'bodies'))
    if bodies:
        out['bodies'] = [{'id': ctx.refs.id_for('body', _token(b)), 'name': b.name} for b in bodies][:DEFAULT_LIMIT]
    prof = _get(e, 'profile')  # one profile, or a collection of them
    profiles = [] if prof is None else [prof] if _get(prof, 'parentSketch') is not None else _items(prof)
    for p in profiles:
        sk = _get(p, 'parentSketch')
        if sk is not None:
            out['sketch'] = {'id': ctx.refs.id_for('sketch', _token(sk)), 'name': sk.name}
            break
    params = [p for p in _items(_get(ctx.design, 'allParameters')) if _get(p, 'createdBy') is not None
              and _token(_get(p, 'createdBy')) == _token(e)]
    out['dimensions'] = [{'name': p.name, 'expression': _get(p, 'expression'), 'role': _get(p, 'role')}
                         for p in params][:DEFAULT_LIMIT]
    return out


def list_parameters(ctx, args):
    kind = args.get('kind') or 'user'
    if kind not in ('user', 'model', 'all'):
        raise ToolError('kind must be "user", "model" or "all".')
    users = _items(ctx.design.userParameters)
    if kind == 'user':
        params = users
    else:
        user_names = {p.name for p in users}
        everything = _items(_get(ctx.design, 'allParameters'))
        params = [p for p in everything if p.name not in user_names] if kind == 'model' else everything
    return _page([_param_info(p) for p in params], args)


def find(ctx, args):
    text = str(args.get('text') or '').strip().lower()
    if not text:
        raise ToolError('text is required.')
    kind = args.get('kind')
    root = _root(ctx)
    hits = []

    def want(k):
        return kind in (None, '', k)

    occs = _items(_get(root, 'allOccurrences'))
    contexts = [(root, None)] + [(o.component, o) for o in occs]
    if want('component'):
        hits += [{'kind': 'occurrence', **_occ_info(ctx, o)} for o in occs
                 if text in o.name.lower() or text in o.component.name.lower()]
    for comp, occ in contexts:
        if want('body'):
            hits += [{'kind': 'body', **_body_info(ctx, _in_context(b, occ))} for b in _items(comp.bRepBodies)
                     if text in b.name.lower()]
        if want('sketch'):
            hits += [{'kind': 'sketch', **_sketch_info(ctx, _in_context(s, occ))} for s in _items(comp.sketches)
                     if text in s.name.lower()]
    if want('feature'):
        hits += [{'kind': 'feature', **_timeline_info(ctx, i)} for i in _items(_get(ctx.design, 'timeline'))
                 if text in str(_get(i, 'name') or '').lower()]
    if want('parameter'):
        hits += [{'kind': 'parameter', **_param_info(p)} for p in _items(ctx.design.userParameters)
                 if text in p.name.lower()]
    return _page(hits, {'limit': DEFAULT_LIMIT})


def get_selection(ctx, args):
    sel = [_describe(ctx, e) for e in ctx.selection]
    return {'items': sel[:DEFAULT_LIMIT], 'total': len(sel),
            **({} if sel else {'note': 'Nothing is selected.'})}


def measure(ctx, args):
    if ctx.measure is None:
        raise ToolError('Measuring is not available.')
    _, a = _resolve(ctx, args.get('a'), ('body', 'occurrence'))
    _, b = _resolve(ctx, args.get('b'), ('body', 'occurrence'))
    return {'a': args.get('a'), 'b': args.get('b'), 'distance': _mm(ctx.measure(a, b))}


_TOOLS = {f.__name__: f for f in (get_overview, list_components, get_component, list_bodies, get_body,
                                  list_sketches, get_sketch, get_timeline, get_feature, list_parameters,
                                  find, get_selection, measure)}


def label(name, args, result):
    """A short line for the panel: what the model looked at."""
    a = args or {}
    err = isinstance(result, dict) and result.get('error')
    what = {
        'get_overview': 'Looked at the design overview',
        'list_components': f'Listed components{"" if a.get("parent") in (None, "", "root") else " in " + a["parent"]}',
        'get_component': f'Opened component {a.get("id", "")}',
        'list_bodies': f'Listed bodies{"" if a.get("component") in (None, "", "root") else " in " + a["component"]}',
        'get_body': f'Inspected body {a.get("id", "")}',
        'list_sketches': f'Listed sketches{"" if a.get("component") in (None, "", "root") else " in " + a["component"]}',
        'get_sketch': f'Read sketch {a.get("id", "")}',
        'get_timeline': f'Read the timeline{" of " + a["component"] if a.get("component") else ""}',
        'get_feature': f'Inspected feature {a.get("id", "")}',
        'list_parameters': f'Listed {a.get("kind") or "user"} parameters',
        'find': f'Searched for “{a.get("text", "")}”',
        'get_selection': 'Checked your selection',
        'measure': f'Measured {a.get("a", "")} to {a.get("b", "")}',
    }.get(name, f'Called {name}')
    if err:
        return f'{what} (failed: {err})'
    name_of = isinstance(result, dict) and result.get('name')
    if name_of and name in ('get_component', 'get_body', 'get_sketch', 'get_feature'):
        what += f' · {name_of}'
    if isinstance(result, dict) and 'total' in result and name != 'get_selection':
        what += f' · {result["total"]}'
    return what


def summary(ctx, max_lines=60):
    """A compact text picture of the design, for models that can't call tools ('' for an empty design)."""
    if not _items(_get(ctx.design, 'timeline')) and not _items(_root(ctx).bRepBodies) \
            and not _items(_get(_root(ctx), 'allOccurrences')):
        return ''
    lines = []
    ov = get_overview(ctx, {})
    lines.append(f'Document "{ov["document"]}" ({ov["type"]}, units {ov["units"]}); lengths below in mm, world coordinates.')
    c = ov['counts']
    lines.append(f'{c["occurrences"]} components, {c["bodies"]} bodies, {c["sketches"]} sketches, '
                 f'{c["timeline"]} timeline features.')
    for s in ov['selection']:
        lines.append(f'Selected: {s.get("kind")} {s.get("name") or s.get("body_name") or ""}'.rstrip())
    for o in list_components(ctx, {'depth': 3, 'limit': 30})['items']:
        lines.append(f'{"  " * (o["depth"] - 1)}- component {o["name"]} at {o["position"]}, {o["bodies"]} bodies')
    for comp, occ in [(_root(ctx), None)] + [(o.component, o) for o in _items(_get(_root(ctx), 'allOccurrences'))]:
        for b in _items(comp.bRepBodies)[:10]:
            info = _body_info(ctx, _in_context(b, occ))
            bb = info['bbox'] or {}
            lines.append(f'- body {info["name"]} in {comp.name}: size {bb.get("size")} from {bb.get("min")} to {bb.get("max")}')
    users = _items(ctx.design.userParameters)
    if users:
        lines.append('User parameters: ' + ', '.join(f'{p.name} = {_get(p, "expression")}' for p in users[:30]))
    tl = get_timeline(ctx, {'limit': 25})
    if tl['total']:
        lines.append('Timeline: ' + ', '.join(f'{i["name"]} ({i["type"]})' for i in tl['items'])
                     + (f', … {tl["more"]} more' if tl.get('more') else ''))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f'… {len(lines) - max_lines} more lines']
    return '\n'.join(lines)


PROMPT = """LOOKING AT THE USER'S DESIGN
- You have read-only tools to look at the user's existing Fusion design: components, bodies, sketches,
  the timeline, parameters, what they selected, and distances. Start with get_overview.
- Use them whenever the request mentions or depends on existing geometry ("fits this plate", "on top of the
  housing", "matches the selected hole"). Don't guess sizes or positions you can look up.
- Tool results are in mm and world coordinates, the same frame as the design JSON.
- Your design is built as NEW geometry: you can't change existing bodies yet, and existing parameters can't
  be referenced, so copy the values you need into your own parameters."""


class DesignToolkit(BaseToolkit):
    """Read-only views of the open design: hierarchy, geometry, history, parameters, selection."""
    id = 'design'
    name = 'Design inspection'
    order = 10
    prompt = PROMPT

    def tools(self):
        return [dict(t) for t in TOOL_SPECS]

    def run(self, name, args, ctx):
        fn = _TOOLS.get(name)
        if not fn:
            raise ToolError(f'Unknown tool "{name}".')
        return fn(Context.from_tool_context(ctx), args)

    def label(self, name, args, result):
        return label(name, args, result)

    def summary(self, ctx):
        return summary(Context.from_tool_context(ctx))
