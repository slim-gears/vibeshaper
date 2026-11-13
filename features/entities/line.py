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
        h.xy(entity['start'], where)
        h.xy(entity['end'], where)

    def draw(self, sk, e, ctx):
        p1 = ctx.pt(ctx.cm(e['start'][0]), ctx.cm(e['start'][1]))
        p2 = ctx.pt(ctx.cm(e['end'][0]), ctx.cm(e['end'][1]))
        line = sk.sketchCurves.sketchLines.addByTwoPoints(p1, p2)
        ctx.place([line.startSketchPoint, line.endSketchPoint], [e['start'], e['end']], [(0, 1, line)])
        ctx.register(e, line, start=line.startSketchPoint, end=line.endSketchPoint)
