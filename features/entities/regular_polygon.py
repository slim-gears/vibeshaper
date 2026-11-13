"""Regular polygon sketch entity."""
import math

from ..base import JS_LEN, JS_POINT
from .. import _helpers as h
from .base import BaseEntity


class RegularPolygonEntity(BaseEntity):
    type = 'regular_polygon'
    name = 'Regular polygon'
    order = 60
    required = ('center', 'sides')
    schema = {
        'center': JS_POINT,
        'sides': {'type': ['integer', 'string']},
        'diameter': JS_LEN,
        'across_flats': JS_LEN,
    }
    prompt = ('{"type": "regular_polygon", "center": [a, b], "sides": n, "across_flats": d}'
              '   or "diameter" (through the corners) instead of across_flats; e.g. hex nut recesses')

    def validate(self, entity, where, ent_ids):
        h.xy(entity['center'], where)
        try:
            sides = float(entity['sides'])
        except (TypeError, ValueError):
            sides = 0
        if sides != int(sides) or not 3 <= sides <= 64:
            raise ValueError(f'{where}: sides must be a whole number from 3 to 64')
        if ('diameter' in entity) == ('across_flats' in entity):
            raise ValueError(f'{where}: give either diameter (through the corners) or across_flats')

    def draw(self, sk, e, ctx):
        import adsk.core

        P = adsk.core.Point3D.create
        curves, dims, gc = sk.sketchCurves, sk.sketchDimensions, sk.geometricConstraints
        # What Fusion's polygon tool makes: vertices on a construction circle, equal sides,
        # one side horizontal (the bottom one, in DSL coordinates), and the circle's diameter.
        n = int(float(e['sides']))
        cx, cy = ctx.cm(e['center'][0]), ctx.cm(e['center'][1])
        if 'diameter' in e:
            dia_ex = ctx.ex(e['diameter'])
            r = ctx.cm(e['diameter']) / 2
        else:
            dia_ex = f'({h.len_ex(ctx.ex, e["across_flats"])}) / cos(180 deg / {n})'
            r = ctx.cm(e['across_flats']) / 2 / math.cos(math.pi / n)
        verts = []
        for k in range(n):
            ang = -math.pi / 2 - math.pi / n + 2 * math.pi * k / n
            verts.append(ctx.pt(cx + r * math.cos(ang), cy + r * math.sin(ang)))
        c = ctx.pt(cx, cy)
        circle = curves.sketchCircles.addByCenterRadius(c, r)
        circle.isConstruction = True
        lines = [curves.sketchLines.addByTwoPoints(verts[0], verts[1])]
        for v in verts[2:]:
            lines.append(curves.sketchLines.addByTwoPoints(lines[-1].endSketchPoint, v))
        lines.append(curves.sketchLines.addByTwoPoints(lines[-1].endSketchPoint, lines[0].startSketchPoint))
        for l in lines:
            h.try_call(gc.addCoincident, l.startSketchPoint, circle)
        for l in lines[1:]:
            h.try_call(gc.addEqual, lines[0], l)
        a, b = lines[0].startSketchPoint.geometry, lines[0].endSketchPoint.geometry
        h.try_call(gc.addHorizontal if abs(a.y - b.y) < abs(a.x - b.x) else gc.addVertical, lines[0])
        try:
            dims.addDiameterDimension(circle, P(c.x + r, c.y + r, 0)).parameter.expression = dia_ex
        except Exception:
            pass
        ctx.place([circle.centerSketchPoint], [e['center']])
        ctx.register(e, lines, index_curves=True, center=circle.centerSketchPoint)
