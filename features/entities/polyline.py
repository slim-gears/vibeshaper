"""Polyline sketch entity."""
from ..base import JS_POINT
from .. import _helpers as h
from .base import BaseEntity


class PolylineEntity(BaseEntity):
    type = 'polyline'
    name = 'Polyline'
    order = 50
    required = ('points',)
    schema = {'points': {'type': 'array', 'items': JS_POINT}, 'closed': {'type': 'boolean'}}
    prompt = '{"type": "polyline", "points": [[a, b], ...], "closed": false}  open spine/path for sweeps or wires (or [[x, y, z], ...] in a "plane": "3d" sketch)'

    def validate(self, entity, where, ent_ids):
        pts = entity['points']
        if not isinstance(pts, list) or len(pts) < 2:
            raise ValueError(f'{where}: polyline needs at least 2 points')
        for p in pts:
            h.pt2or3(p, where)
        if len({len(p) for p in pts}) > 1:
            raise ValueError(f'{where}: polyline points must all be 2D [a, b] or all 3D [x, y, z]')

    def draw(self, sk, e, ctx):
        h.draw_chain(ctx, e, default_closed=False)
