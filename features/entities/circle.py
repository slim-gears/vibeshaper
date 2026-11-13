"""Circle sketch entity."""
from ..base import JS_LEN, JS_POINT
from .. import _helpers as h
from .base import BaseEntity


class CircleEntity(BaseEntity):
    type = 'circle'
    name = 'Circle'
    order = 20
    required = ('center', 'diameter')
    schema = {'center': JS_POINT, 'diameter': JS_LEN}
    prompt = '{"type": "circle", "center": [a, b], "diameter": d}'

    def validate(self, entity, where, ent_ids):
        h.xy(entity['center'], where)

    def draw(self, sk, e, ctx):
        import adsk.core

        P = adsk.core.Point3D.create
        curves, dims = sk.sketchCurves, sk.sketchDimensions
        r = ctx.cm(e['diameter']) / 2
        c = ctx.pt(ctx.cm(e['center'][0]), ctx.cm(e['center'][1]))
        circle = curves.sketchCircles.addByCenterRadius(c, r)
        try:
            dims.addDiameterDimension(circle, P(c.x + r, c.y + r, 0)).parameter.expression = ctx.ex(e['diameter'])
        except Exception:
            pass
        ctx.place([circle.centerSketchPoint], [e['center']])
        ctx.register(e, circle, center=circle.centerSketchPoint)
