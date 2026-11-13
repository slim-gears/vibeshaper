"""Polygon sketch entity."""
from ..base import JS_POINT
from .. import _helpers as h
from .base import BaseEntity


class PolygonEntity(BaseEntity):
    type = 'polygon'
    name = 'Polygon'
    order = 30
    required = ('points',)
    schema = {'points': {'type': 'array', 'items': JS_POINT}, 'closed': {'type': 'boolean'}}
    prompt = '{"type": "polygon", "points": [[a, b], ...], "closed": true}   at least 3 points'

    def validate(self, entity, where, ent_ids):
        if not isinstance(entity['points'], list) or len(entity['points']) < 3:
            raise ValueError(f'{where}: polygon needs at least 3 points')
        for p in entity['points']:
            h.xy(p, where)

    def draw(self, sk, e, ctx):
        h.draw_chain(ctx, e, default_closed=True)
