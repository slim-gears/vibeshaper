"""Line sketch entity."""
from ..base import JS_POINT
from .. import _helpers as h
from .base import BaseEntity


class LineEntity(BaseEntity):
    type = 'line'
    name = 'Line'
    order = 40
    required = ('start', 'end')
    schema = {'start': JS_POINT, 'end': JS_POINT}
    prompt = '{"type": "line", "start": [a, b], "end": [c, d]}'

    def validate(self, entity, where, ent_ids):
        h.pt2or3(entity['start'], where)
        h.pt2or3(entity['end'], where)
        if len(entity['start']) != len(entity['end']):
            raise ValueError(f'{where}: start and end must both be 2D [a, b] or both 3D [x, y, z]')

    def draw(self, sk, e, ctx):
        p1 = h.coord_pt(ctx, e['start'])
        p2 = h.coord_pt(ctx, e['end'])
        line = sk.sketchCurves.sketchLines.addByTwoPoints(p1, p2)
        ctx.place([line.startSketchPoint, line.endSketchPoint], [e['start'], e['end']], [(0, 1, line)])
        ctx.register(e, line, start=line.startSketchPoint, end=line.endSketchPoint)
