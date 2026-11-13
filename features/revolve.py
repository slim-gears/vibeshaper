"""Revolve timeline feature."""
from .base import AXES, BaseFeature, JS_AXIS, JS_LEN, JS_MODE, MODES
from . import _helpers as h


class RevolveFeature(BaseFeature):
    op = 'revolve'
    name = 'Revolve'
    order = 30
    target_key = 'sketch'
    schema = {
        'sketch': {'type': 'string'},
        'axis': JS_AXIS,
        'angle': JS_LEN,
        'mode': JS_MODE,
    }
    prompt = (
        'Revolve:\n'
        '   {"op": "revolve", "id": optional_name, "sketch": sketch_id, "axis": "x"|"y"|"z", '
        '"angle": "360 deg" (optional), "mode": "new_body"|"join"|"cut"}'
    )

    def validate(self, step, where, ctx):
        h.need(step, where, 'sketch')
        if step['sketch'] not in ctx.sketches:
            raise ValueError(f'{where}: unknown sketch {step["sketch"]!r} (must be defined earlier)')
        if step.get('axis', 'z').lower() not in AXES:
            raise ValueError(f'{where}: axis must be one of {AXES}')
        if step.get('mode', 'new_body') not in MODES:
            raise ValueError(f'{where}: mode must be one of {MODES}')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core

        sk = ctx.sketches[step['sketch']]
        if sk.profiles.count == 0:
            raise ValueError(f'sketch {step["sketch"]!r} has no closed profiles')
        profs = adsk.core.ObjectCollection.create()
        for k in range(sk.profiles.count):
            profs.add(sk.profiles.item(k))
        revolves = ctx.root.features.revolveFeatures
        axis = ctx.axes_map[step.get('axis', 'z').lower()]
        mode = step.get('mode', 'new_body')
        inp = h.own_bodies(revolves.createInput(profs, axis, ctx.ops[mode]), ctx.root, mode)
        angle_str = str(step.get('angle', '360 deg'))
        inp.setAngleExtent(False, adsk.core.ValueInput.createByString(ctx.angle_ex(angle_str)))
        feat = revolves.add(inp)
        ctx.add_feature(step, feat, default_id=step['sketch'])
