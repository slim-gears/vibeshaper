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
    prompt = '{"type": "polyline", "points": [[a, b], ...], "closed": false}  open spine/path for sweeps or wires'

    def validate(self, entity, where, ent_ids):
        if not isinstance(entity['points'], list) or len(entity['points']) < 2:
            raise ValueError(f'{where}: polyline needs at least 2 points')
        for p in entity['points']:
            h.xy(p, where)

    def draw(self, sk, e, ctx):
        h.draw_chain(ctx, e, default_closed=False)
