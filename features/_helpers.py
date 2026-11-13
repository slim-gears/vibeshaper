"""Shared geometry selectors, validation checks, and sketch point-placement helpers."""
from .base import AXES, JS_AXIS

EDGE_SELECTORS = ('vertical', 'top', 'bottom', 'circular', 'all')
FACE_SELECTORS = ('top', 'bottom', 'none', 'all')
FEATURE_FACE_SETS = {'all': 'faces', 'side': 'sideFaces', 'start': 'startFaces', 'end': 'endFaces'}
EDGE_SELECTOR_KEYS = ('feature', 'faces', 'exclude', 'type', 'at', 'direction', 'on')

JS_EDGES = {'anyOf': [
    {'enum': list(EDGE_SELECTORS)},
    {'type': 'object', 'properties': {
        'feature': {'type': 'string'},
        'faces': {'enum': list(FEATURE_FACE_SETS)},
        'exclude': {'type': ['string', 'array'], 'items': {'type': 'string'}},
        'type': {'enum': ['circle', 'line']},
        'at': {'enum': ['top', 'bottom']},
        'direction': JS_AXIS,
        'on': {'type': 'string'},
    }},
]}

EPS = 1e-7  # cm


def need(obj, where, *keys):
    if not isinstance(obj, dict):
        raise ValueError(f'{where}: must be an object')
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValueError(f'{where}: missing {", ".join(missing)}')


def xy(v, where):
    if not (isinstance(v, list) and len(v) == 2):
        raise ValueError(f'{where}: point must be [x, y]')


def check_edges(edges, where, features, sketches=()):
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


def get_body(root, target, features):
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


def own_bodies(inp, comp, mode):
    """Let a join, cut or intersect change only the bodies of the component whose timeline it is in.
    Fusion otherwise applies it to every body it touches, including other components' parts placed
    against this one (a carriage's channel cut would cut its rail)."""
    if mode in ('join', 'cut', 'intersect'):
        bodies = [comp.bRepBodies.item(k) for k in range(comp.bRepBodies.count)]
        if bodies:
            inp.participantBodies = bodies
    return inp


def feature_faces(features, fid, which='all'):
    """Faces a named step produced, as they are now (later steps may have split them)."""
    if not features or fid not in features:
        raise ValueError(f'edge selector: unknown feature {fid!r}')
    coll = getattr(features[fid], FEATURE_FACE_SETS[which], None)
    if coll is None:
        raise ValueError(f'edge selector: feature {fid!r} has no {which} faces')
    return [coll.item(k) for k in range(coll.count)]


def feature_edges(features, sel):
    """Edges of the faces made by sel['feature'], minus those touching sel['exclude'] faces."""
    edges = []
    for face in feature_faces(features, sel['feature'], sel.get('faces', 'all')):
        for k in range(face.edges.count):
            e = face.edges.item(k)
            if not any(e == x for x in edges):  # Fusion objects compare by entity, not identity
                edges.append(e)
    excl = sel.get('exclude') or []
    for fid in [excl] if isinstance(excl, str) else excl:
        bad = feature_faces(features, fid)
        edges = [e for e in edges
                 if not any(f == b for f in (e.faces.item(k) for k in range(e.faces.count)) for b in bad)]
    return edges


def edge_on_sketch_plane(edge, sk, tol=1e-4):
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


def select_edges(body, sel, features=None, sketches=None):
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
        candidates = feature_edges(features, sel)
    else:
        candidates = [body.edges.item(k) for k in range(body.edges.count)]
    if 'on' in sel:
        if not sketches or sel['on'] not in sketches:
            raise ValueError(f"edge selector: unknown sketch {sel['on']!r}")
        candidates = [e for e in candidates if edge_on_sketch_plane(e, sketches[sel['on']])]

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


def select_faces(body, sel):
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


def try_call(fn, *args):
    try:
        fn(*args)
        return True
    except Exception:
        return False


def as_list(got):
    """An entity's curves as a list (one curve, a list, or a Fusion collection)."""
    if isinstance(got, list):
        return got
    if hasattr(got, 'count') and hasattr(got, 'item'):
        return [got.item(k) for k in range(got.count)]
    return [got]


def len_ex(ex, v):
    """A length expression for a dimension; a bare number means mm."""
    if isinstance(v, (int, float)):
        return f'{v} mm'
    s = str(v).strip()
    try:
        float(s)
        return f'{s} mm'
    except ValueError:
        return ex(s)


def span_ex(ex, ea, va, eb, vb):
    """Expression for the distance |b - a| along one axis. Sketch distances are never negative."""
    if abs(va) < EPS:
        e, v = len_ex(ex, eb), vb
    elif abs(vb) < EPS:
        e, v = len_ex(ex, ea), va
    elif vb >= va:
        return f'({len_ex(ex, eb)}) - ({len_ex(ex, ea)})'
    else:
        return f'({len_ex(ex, ea)}) - ({len_ex(ex, eb)})'
    return e if v >= 0 else f'-({e})'


def axis_swap(pt):
    """True when the DSL's first coordinate runs along the sketch's vertical axis."""
    o, u = pt(0, 0), pt(1, 0)
    return abs(u.x - o.x) < abs(u.y - o.y)


def place_points(sk, pts, coords, links, ex, cm, pt):
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
    idx = (1, 0) if axis_swap(pt) else (0, 1)  # sketch axis k -> DSL coordinate index
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
        same = [abs(vals[i][k] - vals[j][k]) < EPS for k in (0, 1)]
        if all(same):
            continue
        if same[1]:  # same y: horizontal
            try_call(gc.addHorizontal, line)
            par[1][find(1, i)] = find(1, j)
            spans[0].append((i, j))
        elif same[0]:  # same x: vertical
            try_call(gc.addVertical, line)
            par[0][find(0, i)] = find(0, j)
            spans[1].append((i, j))

    placed = (set(), set())
    for i in range(n):
        if abs(vals[i][0]) < EPS and abs(vals[i][1]) < EPS and try_call(gc.addCoincident, pts[i], origin):
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
        try_call(setattr, d.parameter, 'expression', expr)
        return True

    for k in (0, 1):
        align = gc.addHorizontalPoints if k else gc.addVerticalPoints
        for i in range(n):
            if find(k, i) not in placed[k] and abs(vals[i][k]) < EPS and try_call(align, pts[i], origin):
                placed[k].add(find(k, i))
        while True:
            progress = True
            while progress:
                progress = False
                for i, j in spans[k]:
                    gi, gj = find(k, i), find(k, j)
                    if (gi in placed[k]) == (gj in placed[k]):
                        continue
                    if dim(k, pts[i], pts[j], span_ex(ex, exprs[i][k], vals[i][k], exprs[j][k], vals[j][k])):
                        placed[k].update((gi, gj))
                        progress = True
            rest = [i for i in range(n) if find(k, i) not in placed[k]]
            if not rest:
                break
            i = rest[0]
            dim(k, pts[i], origin, span_ex(ex, 0, 0.0, exprs[i][k], vals[i][k]))
            placed[k].add(find(k, i))  # even if it failed, so the loop ends


def draw_chain(ctx, e, default_closed):
    """Draw a closed polygon or open/closed polyline of straight segments."""
    curves = ctx.sk.sketchCurves
    raw = e['points']
    pts = [ctx.pt(ctx.cm(x), ctx.cm(y)) for x, y in raw]
    is_closed = e.get('closed', default_closed)
    lines = [curves.sketchLines.addByTwoPoints(pts[0], pts[1])]
    for p in pts[2:]:
        lines.append(curves.sketchLines.addByTwoPoints(lines[-1].endSketchPoint, p))
    if is_closed:
        lines.append(curves.sketchLines.addByTwoPoints(lines[-1].endSketchPoint, lines[0].startSketchPoint))
    n = len(raw)
    vpts = [lines[0].startSketchPoint] + [l.endSketchPoint for l in lines[:n - 1]]
    links = [(k, (k + 1) % n, lines[k]) for k in range(len(lines))]
    ctx.place(vpts, raw, links)
    ctx.register(e, lines, index_curves=True)
