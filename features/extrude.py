"""Extrude timeline feature."""
from .base import BaseFeature, JS_LEN, JS_MODE, MODES
from . import _helpers as h


class ExtrudeFeature(BaseFeature):
    op = 'extrude'
    name = 'Extrude'
    order = 20
    target_key = 'sketch'
    schema = {
        'sketch': {'type': 'string'},
        'distance': JS_LEN,
        'mode': JS_MODE,
    }
    prompt = (
        'Extrude:\n'
        '   {"op": "extrude", "id": optional_name, "sketch": sketch_id, "distance": length, '
        '"mode": "new_body"|"join"|"cut"|"intersect"}'
    )
    rules = (
        '- An extrude or revolve uses EVERY closed region of its sketch. '
        'Never draw a shape inside another shape in the same sketch.'
    )

    def validate(self, step, where, ctx):
        h.need(step, where, 'sketch', 'distance')
        if step['sketch'] not in ctx.sketches:
            raise ValueError(f'{where}: unknown sketch {step["sketch"]!r} (must be defined earlier)')
        if step.get('mode', 'new_body') not in MODES:
            raise ValueError(f'{where}: mode must be one of {MODES}')
        ctx.features.add(step.get('id', step['sketch']))  # execute() names an id-less extrude after its sketch

    def execute(self, step, ctx):
        import adsk.core

        sk = ctx.sketches[step['sketch']]
        if sk.profiles.count == 0:
            raise ValueError(f'sketch {step["sketch"]!r} has no closed profiles')
        profs = adsk.core.ObjectCollection.create()
        for k in range(sk.profiles.count):
            profs.add(sk.profiles.item(k))
        feats = ctx.root.features.extrudeFeatures
        mode = step.get('mode', 'new_body')
        inp = h.own_bodies(feats.createInput(profs, ctx.ops[mode]), ctx.root, mode)
        inp.setDistanceExtent(False, adsk.core.ValueInput.createByString(ctx.ex(step['distance'])))
        feat = feats.add(inp)
        ctx.add_feature(step, feat, default_id=step['sketch'])
