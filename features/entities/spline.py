"""Fitted spline sketch entity."""
from ..base import JS_POINT
from .. import _helpers as h
from .base import BaseEntity


class SplineEntity(BaseEntity):
    type = 'spline'
    name = 'Spline'
    order = 55
    required = ('points',)
    schema = {'points': {'type': 'array', 'items': JS_POINT}, 'closed': {'type': 'boolean'}}
    prompt = '{"type": "spline", "points": [[a, b], ...], "closed": false}   smooth fitted spline curve through points (or [[x, y, z], ...] in a "plane": "3d" sketch; periodic loop when "closed": true)'

    def validate(self, entity, where, ent_ids):
        if 'closed' in entity and not isinstance(entity['closed'], bool):
            raise ValueError(f'{where}: closed must be true or false')
        is_closed = bool(entity.get('closed', False))
        pts = entity['points']
        min_pts = 3 if is_closed else 2
        if not isinstance(pts, list) or len(pts) < min_pts:
            raise ValueError(f'{where}: spline needs at least {min_pts} points')
        for p in pts:
            h.pt2or3(p, where)
        if len({len(p) for p in pts}) > 1:
            raise ValueError(f'{where}: spline points must all be 2D [a, b] or all 3D [x, y, z]')

    def draw(self, sk, e, ctx):
        import adsk.core

        raw = list(e['points'])
        is_closed = bool(e.get('closed', False))
        if is_closed and len(raw) > 3 and h.same_pt(ctx, raw[-1], raw[0]):
            raw.pop()
        coll = adsk.core.ObjectCollection.create()
        for p in raw:
            coll.add(h.coord_pt(ctx, p))
        sp = sk.sketchCurves.sketchFittedSplines.add(coll)
        if is_closed:
            sp.isClosed = True
        fpts = [sp.fitPoints.item(i) for i in range(sp.fitPoints.count)]
        ctx.place(fpts[:len(raw)], raw)
        if is_closed:
            ctx.register(e, sp)
        else:
            ctx.register(e, sp, start=sp.startSketchPoint, end=sp.endSketchPoint)
