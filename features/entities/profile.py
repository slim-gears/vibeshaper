"""Profile (lines + 3-point arcs) sketch entity."""
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
            'properties': {'to': JS_POINT, 'through': JS_POINT},
            'required': ['to'],
        }},
    }
    prompt = ('{"type": "profile", "start": [a, b], "segments": [{"to": [c, d]}, {"to": [e, f], "through": [mx, my]}], "closed": true}'
              '   outline of lines and 3-point arcs ("through": mid-arc point)')

    def validate(self, entity, where, ent_ids):
        h.xy(entity['start'], where)
        if not isinstance(entity['segments'], list) or not entity['segments']:
            raise ValueError(f'{where}: segments must be a non-empty list')
        for k, sg in enumerate(entity['segments']):
            h.need(sg, f'{where}.segments[{k}]', 'to')
            h.xy(sg['to'], f'{where}.segments[{k}].to')
            if 'through' in sg:
                h.xy(sg['through'], f'{where}.segments[{k}].through')

    def draw(self, sk, e, ctx):
        curves, gc = sk.sketchCurves, sk.geometricConstraints
        # Lines and three-point arcs, end to end. Shared corners are one sketch point, each
        # arc's middle point sits on the arc, and every point is placed by dimensions.
        def at(xy):
            return ctx.pt(ctx.cm(xy[0]), ctx.cm(xy[1]))

        def same(a, b):
            return abs(ctx.cm(a[0]) - ctx.cm(b[0])) < h.EPS and abs(ctx.cm(a[1]) - ctx.cm(b[1])) < h.EPS

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
