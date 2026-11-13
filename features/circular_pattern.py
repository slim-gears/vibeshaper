"""Circular pattern timeline feature."""
import re

from .base import AXES, BaseFeature, JS_AXIS, JS_CENTER, JS_LEN
from . import _helpers as h


def _axis_through(root, plane, to_world, center, name, ex, cm):
    """A hidden construction axis normal to `plane` through `center` (plane coordinates).

    It runs through a dimensioned point on the plane and on a parallel plane, so it moves
    when the parameters in `center` change.
    """
    import adsk.core

    P = adsk.core.Point3D.create
    points = []
    for off in (None, '10 mm'):
        sk_plane = plane
        if off:
            pi = root.constructionPlanes.createInput()
            pi.setByOffset(plane, adsk.core.ValueInput.createByString(off))
            sk_plane = root.constructionPlanes.add(pi)
            h.try_call(setattr, sk_plane, 'isLightBulbOn', False)
        sk = root.sketches.add(sk_plane)
        sk.name = name

        def pt(a, b, sk=sk):
            p = sk.modelToSketchSpace(P(*to_world(a, b)))
            p.z = 0
            return p

        point = sk.sketchPoints.add(pt(cm(center[0]), cm(center[1])))
        h.place_points(sk, [point], [center], [], ex, cm, pt)
        h.try_call(setattr, sk, 'isVisible', False)
        points.append(point)
    ai = root.constructionAxes.createInput()
    ai.setByTwoPoints(points[0], points[1])
    axis = root.constructionAxes.add(ai)
    h.try_call(setattr, axis, 'isLightBulbOn', False)
    return axis


class CircularPatternFeature(BaseFeature):
    op = 'circular_pattern'
    name = 'Circular pattern'
    order = 70
    schema = {
        'feature': {'type': 'string'},
        'axis': JS_AXIS,
        'center': JS_CENTER,
        'quantity': JS_LEN,
        'angle': JS_LEN,
    }
    prompt = (
        'Circular Pattern:\n'
        '   {"op": "circular_pattern", "feature": feature_id (optional), "axis": "z", '
        '"center": [a, b] (optional, default [0, 0]), "quantity": count, "angle": "360 deg"}\n'
        '   The axis passes through "center" ([x, y] for "z", [y, z] for "x", [x, z] for "y"). '
        'Set it whenever the patterned part is not centered on the origin.'
    )
    rules = '- For radial arrays (e.g. 6 bolt holes on a flange), draw ONE hole and use `circular_pattern`!'

    def validate(self, step, where, ctx):
        qty = step.get('quantity') or step.get('count') or step.get('num')
        if not qty:
            for pname in ctx.params:
                if any(w in pname.lower() for w in ('qty', 'count', 'num')):
                    qty = pname
                    step['quantity'] = pname
                    break
        if not qty:
            raise ValueError(f'{where}: missing quantity')
        if step.get('axis', 'z').lower() not in AXES:
            raise ValueError(f'{where}: axis must be one of {AXES}')
        if 'center' in step:
            h.xy(step['center'], f'{where}.center')
        if 'feature' in step and step['feature'] not in ctx.features:
            raise ValueError(f'{where}: feature {step["feature"]!r} not found in previous features')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core

        target_feat = ctx.features.get(step['feature']) if 'feature' in step else ctx.last_feature
        if not target_feat:
            raise ValueError('no target feature found for circular_pattern')
        input_entities = adsk.core.ObjectCollection.create()
        input_entities.add(target_feat)
        circ_patterns = ctx.root.features.circularPatternFeatures
        axis_name = step.get('axis', 'z').lower()
        center = step.get('center')
        if center and not (abs(ctx.cm(center[0])) < h.EPS and abs(ctx.cm(center[1])) < h.EPS):
            plane_name = {'z': 'xy', 'x': 'yz', 'y': 'xz'}[axis_name]
            axis = _axis_through(
                ctx.root, ctx.base_planes[plane_name], ctx.world[plane_name], center,
                f'{step.get("id", f"pattern_{ctx.index}")}_axis', ctx.ex, ctx.cm,
            )
        else:
            axis = ctx.axes_map[axis_name]
        inp = circ_patterns.createInput(input_entities, axis)
        qty_clean = re.sub(r'\s*(mm|cm|in|deg)\b', '', str(step['quantity']).strip()).strip()
        inp.quantity = adsk.core.ValueInput.createByString(qty_clean)
        angle_str = str(step.get('angle', '360 deg'))
        inp.totalAngle = adsk.core.ValueInput.createByString(ctx.angle_ex(angle_str))
        inp.isSymmetric = False
        feat = circ_patterns.add(inp)
        ctx.add_feature(step, feat, default_id=f'_circ_pat_{ctx.index}')

    def pattern_copies(self, step, fid, ev):
        if step.get('feature') != fid:
            return 1
        return max(round(ev(step.get('quantity', 1))), 1)
