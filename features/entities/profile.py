"""Profile (lines, 3-point arcs, and fitted splines) sketch entity."""
import math

from ..base import JS_POINT
from .. import _helpers as h
from .base import BaseEntity


class ProfileEntity(BaseEntity):
    type = 'profile'
    name = 'Profile'
    order = 70
    required = ('start', 'segments')
    schema = {
        'start': JS_POINT,
        'closed': {'type': 'boolean'},
        'segments': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'to': JS_POINT, 'through': JS_POINT, 'spline': {'type': 'array', 'items': JS_POINT}},
            'required': ['to'],
        }},
    }
    prompt = ('{"type": "profile", "start": [a, b], "segments": [{"to": [c, d]}, {"to": [e, f], "through": [mx, my]}, '
              '{"to": [g, h], "spline": [[p1x, p1y], ...]}], "closed": true}'
              '   outline of lines, 3-point arcs ("through"), and fitted splines ("spline": intermediate fit points)')

    def validate(self, entity, where, ent_ids):
        h.pt2or3(entity['start'], where)
        dim = len(entity['start'])
        if not isinstance(entity['segments'], list) or not entity['segments']:
            raise ValueError(f'{where}: segments must be a non-empty list')
        for k, sg in enumerate(entity['segments']):
            h.need(sg, f'{where}.segments[{k}]', 'to')
            h.pt2or3(sg['to'], f'{where}.segments[{k}].to')
            if len(sg['to']) != dim:
                raise ValueError(f'{where}.segments[{k}].to: all profile points must have the same dimension ({dim}D)')
            if 'through' in sg and 'spline' in sg:
                raise ValueError(f'{where}.segments[{k}]: segment cannot have both through and spline')
            if 'through' in sg:
                h.pt2or3(sg['through'], f'{where}.segments[{k}].through')
                if len(sg['through']) != dim:
                    raise ValueError(f'{where}.segments[{k}].through: must be {dim}D')
            if 'spline' in sg:
                if not isinstance(sg['spline'], list) or not sg['spline']:
                    raise ValueError(f'{where}.segments[{k}].spline: must be a non-empty list of points')
                for p in sg['spline']:
                    h.pt2or3(p, f'{where}.segments[{k}].spline')
                    if len(p) != dim:
                        raise ValueError(f'{where}.segments[{k}].spline: must be {dim}D')

    def draw(self, sk, e, ctx):
        curves, gc = sk.sketchCurves, sk.geometricConstraints
        # Lines and three-point arcs, end to end. Shared corners are one sketch point, each
        # arc's middle point sits on the arc, and every point is placed by dimensions.
        def at(p):
            return h.coord_pt(ctx, p)

        def same(a, b):
            return h.same_pt(ctx, a, b)

        def dist(a, b):
            return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (getattr(a, 'z', 0) - getattr(b, 'z', 0)) ** 2)

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
                    h.try_call(gc.addCoincident, s_pt, prev)
                if closing:
                    h.try_call(gc.addCoincident, e_pt, verts[0])
                else:
                    verts.append(e_pt)
                    coords.append(sg['to'])
                mid = sk.sketchPoints.add(at(sg['through']))
                h.try_call(gc.addCoincident, mid, arc)
                mids.append((mid, sg['through']))
                made.append(arc)
            elif 'spline' in sg:
                import adsk.core
                coll = adsk.core.ObjectCollection.create()
                coll.add(prev if prev is not None else at(e['start']))
                for p in sg['spline']:
                    coll.add(at(p))
                coll.add(verts[0] if closing else at(sg['to']))
                sp = curves.sketchFittedSplines.add(coll)
                if prev is None:
                    verts.append(sp.startSketchPoint)
                elif sp.startSketchPoint is not prev:
                    h.try_call(gc.addCoincident, sp.startSketchPoint, prev)
                if closing:
                    if sp.endSketchPoint is not verts[0]:
                        h.try_call(gc.addCoincident, sp.endSketchPoint, verts[0])
                else:
                    verts.append(sp.endSketchPoint)
                    coords.append(sg['to'])
                for idx, p in enumerate(sg['spline'], start=1):
                    mids.append((sp.fitPoints.item(idx), p))
                made.append(sp)
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
        ctx.place(verts + [m for m, _ in mids], coords + [c for _, c in mids], links)
        ctx.register(e, made, index_curves=True)
