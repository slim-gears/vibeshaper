"""Center rectangle sketch entity."""
from ..base import JS_LEN, JS_POINT
from .. import _helpers as h
from .base import BaseEntity


class CenterRectangleEntity(BaseEntity):
    type = 'center_rectangle'
    name = 'Center rectangle'
    order = 10
    required = ('center', 'width', 'height')
    schema = {'center': JS_POINT, 'width': JS_LEN, 'height': JS_LEN}
    prompt = '{"type": "center_rectangle", "center": [a, b], "width": along a, "height": along b}'

    def validate(self, entity, where, ent_ids):
        h.xy(entity['center'], where)

    def draw(self, sk, e, ctx):
        import adsk.core
        import adsk.fusion

        P = adsk.core.Point3D.create
        O = adsk.fusion.DimensionOrientations
        curves, dims, gc = sk.sketchCurves, sk.sketchDimensions, sk.geometricConstraints
        # What Fusion's own center rectangle has: horizontal/vertical sides, a construction
        # diagonal with the center at its midpoint, and width/height dimensions.
        cx, cy = ctx.cm(e['center'][0]), ctx.cm(e['center'][1])
        w, h_val = ctx.cm(e['width']), ctx.cm(e['height'])
        c, corner = ctx.pt(cx, cy), ctx.pt(cx + w / 2, cy + h_val / 2)
        made = curves.sketchLines.addCenterPointRectangle(c, corner)
        ls = [made.item(k) for k in range(made.count)]
        ls = [l for l in ls if not getattr(l, 'isConstruction', False)] or ls
        horiz, vert = [], []
        for l in ls:
            a, b = l.startSketchPoint.geometry, l.endSketchPoint.geometry
            if abs(a.y - b.y) < 1e-6:
                horiz.append(l)
                h.try_call(gc.addHorizontal, l)
            else:
                vert.append(l)
                h.try_call(gc.addVertical, l)
        hx, vx = (e['height'], e['width']) if h.axis_swap(ctx.pt) else (e['width'], e['height'])
        sx, sy = abs(corner.x - c.x), abs(corner.y - c.y)
        if horiz:
            l = horiz[0]
            h.try_call(lambda: setattr(dims.addDistanceDimension(
                l.startSketchPoint, l.endSketchPoint, O.HorizontalDimensionOrientation,
                P(c.x, c.y + sy + 1, 0)).parameter, 'expression', ctx.ex(hx)))
        if vert:
            l = vert[0]
            h.try_call(lambda: setattr(dims.addDistanceDimension(
                l.startSketchPoint, l.endSketchPoint, O.VerticalDimensionOrientation,
                P(c.x + sx + 1, c.y, 0)).parameter, 'expression', ctx.ex(vx)))
        a = ls[0].startSketchPoint
        b = next((l.startSketchPoint for l in ls
                  if abs(l.startSketchPoint.geometry.x - a.geometry.x) > 1e-6
                  and abs(l.startSketchPoint.geometry.y - a.geometry.y) > 1e-6), None)
        center = sk.sketchPoints.add(c)
        if b:
            try:
                diag = curves.sketchLines.addByTwoPoints(a, b)
                diag.isConstruction = True
                gc.addMidPoint(center, diag)
            except Exception:
                pass
        ctx.place([center], [e['center']])
        ctx.register(e, ls, center=center)
