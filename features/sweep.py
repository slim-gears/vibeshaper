"""Sweep timeline feature."""
from .base import BaseFeature, JS_MODE, MODES
from . import _helpers as h


class SweepFeature(BaseFeature):
    op = 'sweep'
    name = 'Sweep'
    order = 120
    target_key = 'sketch'
    schema = {
        'sketch': {'type': 'string'},
        'path': {'type': 'string'},
        'mode': JS_MODE,
    }
    prompt = (
        'Sweep:\n'
        '   {"op": "sweep", "sketch": profile_sketch_id, "path": path_sketch_id, "mode": "new_body"|"join"|"cut"}'
    )
    rules = (
        '- For bent pipes, tubing, wire routing, or rails, draw a cross-section `sketch` and a spine/route `path` sketch, then use `sweep`.\n'
        '- For hollow pipes or conduit: to ensure fluid can pass through, FIRST sweep the outer pipe body (`mode: "new_body"`), '
        'THEN sweep an inner bore circle with a smaller diameter along the path (`mode: "cut"`) so the pipe is hollow and has a through-bore from end to end.\n'
        '- When modeling a gusset rib against a round pipe or cylinder: rib sketch points MUST extend into the body centerline '
        '(e.g. at [0, 0] or into the wall), NOT stop on the outer radius. Because round cylinders curve away from the offset sketch plane, '
        'stopping at the outer radius causes floating gaps!'
    )

    def validate(self, step, where, ctx):
        h.need(step, where, 'sketch', 'path')
        if step['sketch'] not in ctx.sketches:
            raise ValueError(f'{where}: unknown profile sketch {step["sketch"]!r}')
        if step['path'] not in ctx.sketches:
            raise ValueError(f'{where}: unknown path sketch {step["path"]!r}')
        mode = step.get('mode', 'new_body').lower()
        if mode not in MODES:
            raise ValueError(f'{where}: mode must be one of {MODES}')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core
        import adsk.fusion

        prof_sk = ctx.sketches[step['sketch']]
        path_sk = ctx.sketches[step['path']]
        if prof_sk.profiles.count == 0:
            raise ValueError(f"profile sketch {step['sketch']!r} has no closed profiles")
        profs = adsk.core.ObjectCollection.create()
        for k in range(prof_sk.profiles.count):
            profs.add(prof_sk.profiles.item(k))
        prof_arg = prof_sk.profiles.item(0) if prof_sk.profiles.count == 1 else profs

        curves = path_sk.sketchCurves
        if curves.count == 0:
            raise ValueError(f"path sketch {step['path']!r} has no curves")
        try:
            path = ctx.root.features.createPath(curves.item(0), True)
        except Exception:
            path_coll = adsk.core.ObjectCollection.create()
            for k in range(curves.count):
                path_coll.add(curves.item(k))
            path = ctx.root.features.createPath(path_coll, False)

        sweeps = ctx.root.features.sweepFeatures
        mode = step.get('mode', 'new_body').lower()
        op_mode = ctx.ops.get(mode, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        inp = h.own_bodies(sweeps.createInput(prof_arg, path, op_mode), ctx.root, mode)
        feat = sweeps.add(inp)
        ctx.add_feature(step, feat)
