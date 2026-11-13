"""Linear (rectangular) pattern timeline feature."""
import re

from .base import AXES, BaseFeature, JS_AXIS, JS_LEN
from . import _helpers as h


class LinearPatternFeature(BaseFeature):
    op = 'linear_pattern'
    name = 'Linear pattern'
    order = 80
    schema = {
        'feature': {'type': 'string'},
        'direction': JS_AXIS,
        'distance': JS_LEN,
        'quantity': JS_LEN,
        'direction2': JS_AXIS,
        'distance2': JS_LEN,
        'quantity2': JS_LEN,
    }
    prompt = (
        'Linear Pattern:\n'
        '   {"op": "linear_pattern", "feature": feature_id (optional), "direction": "x"|"y"|"z", '
        '"distance": spacing, "quantity": count,\n'
        '    "direction2": another axis, "distance2": spacing, "quantity2": count (optional, all three for a grid)}'
    )

    def validate(self, step, where, ctx):
        dist = step.get('distance') or step.get('spacing')
        if not dist:
            raise ValueError(f'{where}: missing distance')
        qty = step.get('quantity') or step.get('count') or step.get('num')
        if not qty:
            for pname in ctx.params:
                if any(w in pname.lower() for w in ('qty', 'count', 'num')):
                    qty = pname
                    step['quantity'] = pname
                    break
        if not qty:
            raise ValueError(f'{where}: missing quantity')
        if step.get('direction', 'x').lower() not in AXES:
            raise ValueError(f'{where}: direction must be one of {AXES}')
        if 'direction2' in step:
            h.need(step, where, 'quantity2', 'distance2')
            if str(step['direction2']).lower() not in AXES or step['direction2'] == step.get('direction', 'x'):
                raise ValueError(f'{where}: direction2 must be another one of {AXES}')
        if 'feature' in step and step['feature'] not in ctx.features:
            raise ValueError(f'{where}: feature {step["feature"]!r} not found in previous features')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core
        import adsk.fusion

        target_feat = ctx.features.get(step['feature']) if 'feature' in step else ctx.last_feature
        if not target_feat:
            raise ValueError('no target feature found for linear_pattern')
        input_entities = adsk.core.ObjectCollection.create()
        input_entities.add(target_feat)
        rect_patterns = ctx.root.features.rectangularPatternFeatures
        axis = ctx.axes_map[step.get('direction', 'x').lower()]
        qty_clean = re.sub(r'\s*(mm|cm|in|deg)\b', '', str(step['quantity']).strip()).strip()
        qty_val = adsk.core.ValueInput.createByString(qty_clean)
        dist_val = adsk.core.ValueInput.createByString(ctx.ex(step['distance']))
        inp = rect_patterns.createInput(
            input_entities, axis, qty_val, dist_val,
            adsk.fusion.PatternDistanceType.SpacingPatternDistanceType,
        )
        if 'direction2' in step:
            qty2 = re.sub(r'\s*(mm|cm|in|deg)\b', '', str(step['quantity2']).strip()).strip()
            inp.setDirectionTwo(
                ctx.axes_map[step['direction2'].lower()],
                adsk.core.ValueInput.createByString(qty2),
                adsk.core.ValueInput.createByString(ctx.ex(step['distance2'])),
            )
        feat = rect_patterns.add(inp)
        ctx.add_feature(step, feat, default_id=f'_lin_pat_{ctx.index}')

    def pattern_copies(self, step, fid, ev):
        if step.get('feature') != fid:
            return 1
        n = round(ev(step.get('quantity', 1)))
        if 'quantity2' in step:
            n *= round(ev(step['quantity2']))
        return max(n, 1)
