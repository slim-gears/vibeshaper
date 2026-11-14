"""JSON DSL -> Fusion 360 parametric timeline.

validate() is pure stdlib (testable outside Fusion); execute() needs Fusion's adsk modules.
All lengths default to mm. Any length may be a number, a literal ("20 mm") or an
expression over user parameters ("box_width - 2 * wall_thick").
"""
import json
import re

try:
    from . import features, shapes
    from .features._helpers import need as _need
except ImportError:  # run as a plain script (tests)
    import features
    import shapes
    from features._helpers import need as _need

PLANES = features.PLANES
AXES = features.AXES
MODES = features.MODES
NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# JSON schema of the DSL, for providers that can constrain their reply to a schema.
# validate() below is still the authority.
_JS_LEN = {'type': ['string', 'number']}
_BASE_STEP_PROPERTIES = {
    'op': {'enum': []},
    'id': {'type': 'string'},
}

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
                'properties': dict(_BASE_STEP_PROPERTIES),
                'required': ['op']
            }
        }
    },
    'required': ['parameters', 'timeline'],
}


def refresh_schema():
    """Rebuild the timeline step op enum and properties in place from feature + shape plugins."""
    step = JSON_SCHEMA['properties']['timeline']['items']
    props = step['properties']
    props.clear()
    props.update(_BASE_STEP_PROPERTIES)
    ops_enum = []
    props['op'] = {'enum': ops_enum}
    for feat in features.get_all_features():
        if feat.op not in ops_enum:
            ops_enum.append(feat.op)
        for key, spec in feat.get_schema().items():
            props.setdefault(key, spec)
    for shape in shapes.get_all_shapes():
        if shape.op not in ops_enum:
            ops_enum.append(shape.op)
        for key, spec in shape.schema.items():
            props.setdefault(key, spec)


refresh_schema()
features.on_change(refresh_schema)
shapes.on_change(refresh_schema)

BOM_UNITS_LENGTH = {'mm': 1.0, 'cm': 10.0, 'm': 1000.0}
BOM_KEYS = ('category', 'item', 'qty', 'unit', 'length', 'stock', 'round', 'whole', 'note', 'link')
_JS_BOM = {'type': 'array', 'items': {'type': 'object', 'properties': {
    'category': {'type': 'string'}, 'item': {'type': 'string'}, 'qty': _JS_LEN, 'unit': {'type': 'string'},
    'length': _JS_LEN, 'stock': {'type': 'array', 'items': {'type': 'number'}}, 'round': {'type': 'number'},
    'whole': {'type': 'boolean'}, 'note': {'type': 'string'}, 'link': {'type': 'string'},
}, 'required': ['category', 'item']}}
JSON_SCHEMA['properties']['bom'] = _JS_BOM
JSON_SCHEMA['properties']['components'] = {
    'type': 'array',
    'items': {'type': 'object', 'properties': {
        'id': {'type': 'string'},
        'name': {'type': 'string'},
        'material': {'type': 'string'},
        'bom': _JS_BOM,
        'timeline': JSON_SCHEMA['properties']['timeline'],
    }, 'required': ['id', 'timeline']},
}
JSON_SCHEMA['properties']['instances'] = {
    'type': 'array',
    'items': {'type': 'object', 'properties': {
        'component': {'type': 'string'},
        'id': {'type': 'string'},
        'position': {'type': 'array', 'items': _JS_LEN, 'minItems': 3, 'maxItems': 3},
        'rotate': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'axis': {'enum': list(AXES)}, 'angle': _JS_LEN}, 'required': ['axis', 'angle']}},
    }, 'required': ['component']},
}


def check_bom(items, where):
    """Structural check of bill-of-materials items (a design's, a component's or a shape's)."""
    if not isinstance(items, list):
        raise ValueError(f'{where}: must be a list of items')
    for k, it in enumerate(items):
        w = f'{where}[{k}]'
        _need(it, w, 'category', 'item')
        extra = [key for key in it if key not in BOM_KEYS]
        if extra:
            raise ValueError(f'{w}: unknown keys {extra}; allowed: {BOM_KEYS}')
        for key in ('category', 'item'):
            if not isinstance(it[key], str) or not it[key].strip():
                raise ValueError(f'{w}: {key} must be a non-empty string')
        for key in ('unit', 'note', 'link'):
            if key in it and not isinstance(it[key], str):
                raise ValueError(f'{w}: {key} must be a string')
        for key in ('qty', 'length'):
            if key in it and (isinstance(it[key], bool) or not isinstance(it[key], (str, int, float))):
                raise ValueError(f'{w}: {key} must be a number or an expression')
        if '{length' in it['item'] and 'length' not in it:
            raise ValueError(f'{w}: item uses {{length}} but has no length')
        stock = it.get('stock', [])
        if not (isinstance(stock, list) and all(isinstance(s, (int, float)) and not isinstance(s, bool) and s > 0
                                                for s in stock)):
            raise ValueError(f'{w}: stock must be a list of lengths in mm')
        if stock and 'length' not in it:
            raise ValueError(f'{w}: stock needs a length')
        if 'round' in it and (isinstance(it['round'], bool) or not isinstance(it['round'], (int, float))
                              or it['round'] <= 0):
            raise ValueError(f'{w}: round must be a positive number')
        if 'whole' in it and not isinstance(it['whole'], bool):
            raise ValueError(f'{w}: whole must be true or false')


def features_prompt():
    """What the feature plugins tell the model about their step syntax."""
    return features.prompt()


def feature_rules_prompt():
    """Feature-specific CAD rules contributed by feature plugins."""
    return features.rules_prompt()


def shapes_prompt():
    """What the shape plugins tell the model about themselves ('' when there are none)."""
    return shapes.prompt()


def expand_shapes(d):
    """Replace each shape step (an op a shape plugin adds) with the parameters and plain steps
    that build it. Other steps are kept as the same objects. Returns d itself when there are none."""
    def has_shape(tl):
        return isinstance(tl, list) and any(isinstance(s, dict) and shapes.get_shape(s.get('op')) for s in tl)

    if not isinstance(d, dict):
        return d
    comps = d.get('components')
    comps = comps if isinstance(comps, list) else []
    if not has_shape(d.get('timeline')) and not any(isinstance(c, dict) and has_shape(c.get('timeline'))
                                                    for c in comps):
        return d
    params = dict(d.get('parameters') or {})

    def expand(tl, label):
        cur = tl
        for _ in range(8):
            if not has_shape(cur):
                return cur
            steps = []
            for i, s in enumerate(cur):
                shape = shapes.get_shape(s.get('op')) if isinstance(s, dict) else None
                if not shape:
                    steps.append(s)
                    continue
                where = f'{label}[{i}] ({s["op"]})'
                shape.validate(s, where)
                new_params, new_steps = shape.expand(s)
                clash = [k for k in new_params if k in params]
                if clash:
                    raise ValueError(f'{where}: parameters {clash} already exist; give this step another id')
                params.update(new_params)
                steps.extend(new_steps)
            cur = steps
        raise ValueError(f'{label}: nested shapes exceed maximum depth')

    out = dict(d)
    if 'timeline' in d:
        out['timeline'] = expand(d['timeline'], 'timeline')
    if 'components' in d:
        out['components'] = [dict(c, timeline=expand(c.get('timeline'), f'components[{k}].timeline'))
                             if isinstance(c, dict) else c for k, c in enumerate(comps)]
    out['parameters'] = params
    return out


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
    if 'bom' in d:
        check_bom(d['bom'], 'bom')
    tl = d.get('timeline', [])
    if 'components' in d:
        _validate_assembly(d, params)
        if not isinstance(tl, list):
            raise ValueError('timeline must be a list')
    elif not isinstance(tl, list) or not tl:
        raise ValueError('timeline must be a non-empty list')
    elif 'instances' in d:
        raise ValueError('instances need components: place copies of a component listed in "components"')
    if tl:
        _validate_steps(tl, 'timeline', params)


def _validate_assembly(d, params):
    """components: each its own timeline (own sketch and feature ids); instances: where copies go."""
    comps = d['components']
    if not isinstance(comps, list) or not comps:
        raise ValueError('components must be a non-empty list')
    ids = set()
    for k, c in enumerate(comps):
        where = f'components[{k}]'
        if not isinstance(c, dict):
            raise ValueError(f'{where}: must be an object')
        _need(c, where, 'id', 'timeline')
        if not isinstance(c['id'], str) or not NAME_RE.match(c['id']):
            raise ValueError(f'{where}: id must be a snake_case name')
        if c['id'] in ids:
            raise ValueError(f'{where}: duplicate component id {c["id"]!r}')
        ids.add(c['id'])
        if 'name' in c and (not isinstance(c['name'], str) or not c['name'].strip()):
            raise ValueError(f'{where}: name must be a non-empty string')
        if 'material' in c and (not isinstance(c['material'], str) or not c['material'].strip()):
            raise ValueError(f'{where}: material must be a non-empty string')
        if 'bom' in c:
            check_bom(c['bom'], f'{where}.bom')
        if not isinstance(c['timeline'], list) or not c['timeline']:
            raise ValueError(f'{where}: timeline must be a non-empty list')
        _validate_steps(c['timeline'], f'{where}.timeline', params)
    insts = d.get('instances', [])
    if not isinstance(insts, list):
        raise ValueError('instances must be a list')
    inst_ids = set()
    for j, inst in enumerate(insts):
        where = f'instances[{j}]'
        if not isinstance(inst, dict):
            raise ValueError(f'{where}: must be an object')
        _need(inst, where, 'component')
        if inst['component'] not in ids:
            raise ValueError(f'{where}: component {inst["component"]!r} is not in components; '
                             f'known: {sorted(ids)}')
        if 'id' in inst:
            if not isinstance(inst['id'], str) or not NAME_RE.match(inst['id']):
                raise ValueError(f'{where}: id must be a snake_case name')
            if inst['id'] in inst_ids:
                raise ValueError(f'{where}: duplicate instance id {inst["id"]!r}')
            inst_ids.add(inst['id'])
        pos = inst.get('position', [0, 0, 0])
        if not (isinstance(pos, list) and len(pos) == 3 and all(isinstance(v, (str, int, float)) for v in pos)):
            raise ValueError(f'{where}: position must be [x, y, z]')
        rot = inst.get('rotate', [])
        if not isinstance(rot, list):
            raise ValueError(f'{where}: rotate must be a list of {{"axis": "x"|"y"|"z", "angle": angle}}')
        for r in rot:
            if not (isinstance(r, dict) and r.get('axis') in AXES and isinstance(r.get('angle'), (str, int, float))):
                raise ValueError(f'{where}: rotate must be a list of {{"axis": "x"|"y"|"z", "angle": angle}}')


def _validate_steps(tl, label, params):
    """Check one timeline. Sketch and feature ids are its own (each component has its own)."""
    ctx = features.ValidationContext(params=params)

    for i, s in enumerate(tl):
        where = f'{label}[{i}]'
        _need(s, where, 'op')
        op = s['op']
        feat = features.get_feature(op)
        if feat is None:
            known = tuple(f.op for f in features.get_all_features()) + tuple(sh.op for sh in shapes.get_all_shapes())
            raise ValueError(f'{where}: unknown op {op!r}; known: {known}')
        feat.validate(s, where, ctx)


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

    out = {**d, 'parameters': {param_map[k]: remap_val(v) for k, v in params.items()}}
    if 'timeline' in d:
        out['timeline'] = [remap_val(step) for step in d['timeline']]
    if 'components' in d:  # ids are kept: only timelines and positions hold expressions
        out['components'] = [dict(c, timeline=[remap_val(step) for step in c['timeline']])
                             for c in d['components']]
    if 'instances' in d:
        out['instances'] = [dict(inst, **{k: remap_val(inst[k]) for k in ('position', 'rotate') if k in inst})
                            for inst in d['instances']]
    return out


def _is_angle_param(name, expr, valid_as_length):
    """An angle parameter: it mentions deg/rad and isn't a length ("pitch_r * cos(20 deg)" is a
    length), or its name says so and it isn't clearly a length ("draft_angle": "5" is an angle;
    a rack angle's "angle_t": "2 mm" or "angle_face + angle_t" are lengths)."""
    low = expr.lower()
    if re.search(r'\d\s*(mm|cm|m|in)\b', low):
        return False
    if 'angle' in name.lower():
        try:
            float(low)
            return True  # a bare number
        except ValueError:
            return not valid_as_length
    mentions = re.search(r'\b(deg|rad)\b', low) is not None
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


def _timeline_index(obj, default=-1):
    """Timeline slot index of `obj`, or `default` when Fusion refuses (expanded group or collapsed child)."""
    try:
        return obj.index
    except (AttributeError, RuntimeError):
        return default


def _group_end_index(g):
    idx = _timeline_index(g)
    try:
        count = g.count
    except Exception:
        count = 0
    for i in range(count):
        try:
            it = g.item(i)
        except Exception:
            continue
        idx = max(idx, _timeline_index(it))
    return idx


def find_groups(design, group_name):
    """All timeline groups belonging to `group_name` (itself or `group_name / ...`), in timeline order."""
    if not group_name:
        return []
    prefix = f'{group_name} / '
    tl = design.timeline
    found = []
    for k in range(tl.timelineGroups.count):
        g = tl.timelineGroups.item(k)
        try:
            gname = g.name
        except Exception:
            continue
        if gname == group_name or str(gname).startswith(prefix):
            pos = _group_end_index(g)
            found.append((pos if pos >= 0 else k, k, g))
    found.sort(key=lambda x: (x[0], x[1]))
    return [g for _, _, g in found]


def find_group(design, group_name):
    """The first timeline group belonging to `group_name`, or None."""
    gs = find_groups(design, group_name)
    return gs[0] if gs else None


_find_group = find_group


def user_features_after(design, group_name):
    """Count timeline items after `group_name` that VibeShaper didn't make (they may depend on it).

    Returns 0 when the group is missing or the timeline can't be inspected.
    """
    try:
        gs = find_groups(design, group_name)
        last_index = max((_group_end_index(g) for g in gs), default=-1)
        if last_index < 0:
            return 0
        tl = design.timeline
        n = 0
        for k in range(tl.count):
            obj = tl.item(k)
            idx = _timeline_index(obj)
            if getattr(obj, 'isGroup', False) or idx <= last_index:
                continue
            try:
                parent = obj.parentGroup
                pname = str(parent.name) if parent else ''
            except Exception:
                pname = ''
            if pname.startswith('VibeShaper'):
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


def placement_parameters(d):
    """Parameters that an instance's position or turn depends on, directly or through other
    parameters. Fusion doesn't move an occurrence when they change, so the design is rebuilt."""
    params = d.get('parameters') or {}
    names = set(params)

    def refs(v):
        return {w for w in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', json.dumps(v)) if w in names}

    todo = refs([[i.get('position'), i.get('rotate')] for i in d.get('instances') or []])
    found = set()
    while todo:
        n = todo.pop()
        if n not in found:
            found.add(n)
            todo |= refs(params[n])
    return found


def _placement(inst, length, angle):
    """An instance's turns [(axis, radians)] and its position (x, y, z), evaluated with
    length(expr) and angle(expr). Turns are about the world axes through the component's own
    origin, in order; then the component is moved to the position."""
    turns = [(r['axis'], angle(r['angle'])) for r in inst.get('rotate', [])]
    return turns, tuple(length(v) for v in inst.get('position', [0, 0, 0]))


def _placement_matrix(inst, length, angle):
    import adsk.core
    turns, (x, y, z) = _placement(inst, length, angle)
    m = adsk.core.Matrix3D.create()
    origin = adsk.core.Point3D.create(0, 0, 0)
    vec = {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}
    for axis, a in turns:
        r = adsk.core.Matrix3D.create()
        r.setToRotation(a, adsk.core.Vector3D.create(*vec[axis]), origin)
        m.transformBy(r)  # applied after the turns so far
    m.translation = adsk.core.Vector3D.create(x, y, z)
    return m


def _add_occurrences(parent, components, instances, placement):
    """One occurrence per instance in `parent` (a component with no instances gets one where it
    was modeled). Copies share their component, so editing it changes them all.
    Returns ([(component spec, Component)] in the order of `components`, [occurrences])."""
    made, occs = [], []
    for c in components:
        insts = [x for x in instances if x['component'] == c['id']] or [{}]
        comp = None
        for inst in insts:
            if comp is None:
                occ = parent.occurrences.addNewComponent(placement(inst))
                comp = occ.component
                try:
                    comp.name = c.get('name') or c['id']
                except Exception:
                    pass
            else:
                occ = parent.occurrences.addExistingComponent(comp, placement(inst))
            occs.append(occ)
            if inst.get('id'):
                try:
                    occ.name = inst['id']
                except Exception:
                    pass  # some Fusion versions name occurrences themselves ("post:2")
        made.append((c, comp))
    return made, occs


class ReplaceError(RuntimeError):
    """The previous version couldn't be removed. Not the design's fault, so not for the model to fix."""


def _delete_group_contents(design, g):
    """Delete a timeline group and everything in it. Returns False if Fusion refuses."""
    try:
        if g.deleteMe(True):
            return True
    except Exception:
        pass  # Fusion sometimes fails here ("InternalValidationError : res"); go item by item
    try:
        items = [g.item(k) for k in range(g.count)]
        for it in reversed(items):  # newest first, so nothing still depends on what we delete
            ent = it.entity
            if ent is None or not ent.deleteMe():
                return False
    except Exception:
        return False
    try:
        tgs = design.timeline.timelineGroups
        if any(tgs.item(k) == g or tgs.item(k).name == g.name for k in range(tgs.count)):
            g.deleteMe(False)  # drop the now-empty group if Fusion kept it
    except Exception:
        pass
    return True


def delete_version(design, group_name, param_names=(), occurrences=()):
    """Remove a previous build: its timeline groups (with contents), the component occurrences it
    placed (by entity token; deleting the group usually removes them already) and its user parameters.

    Call inside the same command as the rebuild so a failed rebuild rolls this back too.
    Returns 'deleted', 'suppressed' (Fusion wouldn't delete it, so it is switched off
    instead) or False when the group no longer exists. Raises ReplaceError if neither works.
    """
    found = False
    groups = find_groups(design, group_name) if group_name else []
    if groups:
        try:
            design.timeline.moveToEnd()  # deleting with the marker rolled back can fail
        except Exception:
            pass
        found = 'deleted'
        for g in reversed(groups):
            try:
                if not getattr(g, 'isValid', True):
                    continue
                g_name = g.name
            except Exception:
                continue
            if not _delete_group_contents(design, g):
                still = next((x for x in find_groups(design, group_name)
                              if getattr(x, 'name', None) == g_name), None)
                if still:
                    try:
                        still.isSuppressed = True
                    except Exception as e:
                        raise ReplaceError(f'could not remove the previous version {group_name!r}: {e}')
                    found = 'suppressed'
    for token in occurrences:
        occ = _find_entity(design, token)
        try:
            if occ is not None:
                occ.deleteMe()
        except Exception:
            pass
    for name in param_names:
        try:
            p = design.userParameters.itemByName(name)
            if p:
                p.deleteMe()  # returns False if still used elsewhere; that's fine
        except Exception:
            pass
    return found


def execute(design, d, group_name='VibeShaper', comp=None, progress=None):
    """Build parameters + timeline in `design`, grouped per component for assemblies.

    comp: component to build in (default: the root component).
    progress: optional progress(done, total, label), called before each step and once at the end
    (done == total). It may raise to stop the build.

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
    target_comp = comp or design.rootComponent

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
    total = len(d.get('timeline') or []) + sum(len(c['timeline']) for c in d.get('components') or [])
    report = progress or (lambda done, total, label: None)
    report(0, total, 'Creating parameters')

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

    ops = {
        'new_body': adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
        'cut': adsk.fusion.FeatureOperations.CutFeatureOperation,
        'intersect': adsk.fusion.FeatureOperations.IntersectFeatureOperation,
    }
    world = {'xy': lambda a, b: (a, b, 0), 'xz': lambda a, b: (a, 0, b), 'yz': lambda a, b: (0, a, b)}

    # What to build where: top-level timeline (if any) in target_comp, then each component's
    # occurrences and timeline together so they form one contiguous timeline group per part.
    def run_unit(unit_root, label, steps_list, done, prefix=None):
        base = {'xy': unit_root.xYConstructionPlane, 'xz': unit_root.xZConstructionPlane,
                'yz': unit_root.yZConstructionPlane}
        axes_map = {'x': unit_root.xConstructionAxis, 'y': unit_root.yConstructionAxis,
                    'z': unit_root.zConstructionAxis}
        sk_map = {}
        feat_map = {}
        last_feature = None
        for i, s in enumerate(steps_list):
            op = s['op']
            feat = features.get_feature(op)
            what = feat.label(s) if feat is not None else f"{op} {s.get('id') or ''}".strip()
            report(done + i, total, f'{prefix}: {what}' if prefix else what)
            try:
                if feat is None:
                    known = tuple(f.op for f in features.get_all_features())
                    raise ValueError(f'unknown op {op!r}; known: {known}')
                ctx = features.BuildContext(
                    root=unit_root, index=i, params=d.get('parameters', {}), um=um,
                    sketches=sk_map, features=feat_map, last_feature=last_feature,
                    base_planes=base, axes_map=axes_map, ops=ops, world=world,
                    ex=ex, cm=cm, angle_ex=angle_ex, eval_count=eval_count,
                )
                feat.execute(s, ctx)
                last_feature = ctx.last_feature
            except Exception as e:
                raise ValueError(f'{label}[{i}] ({s["op"]}): {e}') from e
        return done + len(steps_list)

    has_components = 'components' in d
    occs = []
    ranges = []
    done = 0

    top_steps = d.get('timeline') or []
    if top_steps:
        u_start = tl.markerPosition
        done = run_unit(target_comp, 'timeline', top_steps, done)
        ranges.append((u_start, tl.markerPosition - 1, f'{group_name} / Root' if has_components else group_name))

    if has_components:
        def placement(inst):
            return _placement_matrix(inst, cm, lambda a: um.evaluateExpression(angle_ex(a), 'deg'))

        comps = d['components']
        raw_titles = [c.get('name') or c['id'] for c in comps]
        comp_titles = [f"{t} ({c['id']})" if raw_titles.count(t) > 1 else t
                       for t, c in zip(raw_titles, comps)]
        insts = d.get('instances', [])
        for k, (c, title) in enumerate(zip(comps, comp_titles)):
            report(done, total, f'Placing {title}')
            u_start = tl.markerPosition
            try:
                made_one, new_occs = _add_occurrences(target_comp, [c], insts, placement)
            except RuntimeError as e:
                if 'only contain one component' in str(e):
                    raise ComponentsNotAllowed(str(e)) from e
                raise
            occs.extend(new_occs)
            comp_k = made_one[0][1]
            done = run_unit(comp_k, f'components[{k}].timeline', c['timeline'], done, prefix=title)
            ranges.append((u_start, tl.markerPosition - 1, f'{group_name} / {title}'))

    report(total, total, 'Done')
    feature_count = max(0, tl.markerPosition - start)
    made_group = None
    for u_start, u_end, g_title in reversed(ranges):
        if u_end >= u_start:
            try:
                grp = tl.timelineGroups.add(u_start, u_end)
                if grp is not None:
                    grp.name = g_title
                    try:
                        grp.isCollapsed = True
                    except Exception:
                        pass
                    made_group = group_name
            except Exception:
                pass  # a single item can't always be grouped
    tokens = []
    for o in occs:
        try:
            tokens.append(o.entityToken)
        except Exception:
            pass
    return {'group_name': made_group, 'param_map': param_map, 'feature_count': feature_count,
            'occurrences': tokens}
