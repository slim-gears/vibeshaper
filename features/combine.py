"""Combine (boolean) timeline feature."""
from .base import BaseFeature, JS_MODE, MODES
from . import _helpers as h


class CombineFeature(BaseFeature):
    op = 'combine'
    name = 'Combine'
    order = 110
    target_key = 'target'
    schema = {
        'target': {'type': 'string'},
        'tools': {'type': 'array', 'items': {'type': 'string'}},
        'mode': JS_MODE,
        'keep_tools': {'type': 'boolean'},
    }
    prompt = (
        'Combine (Boolean):\n'
        '   {"op": "combine", "target": body_or_feature_id (optional), "tools": [tool_id, ...], '
        '"mode": "cut"|"join"|"intersect", "keep_tools": false}'
    )
    rules = '- To carve or combine separate bodies, use `combine` with `mode: "cut"` / `"join"` and list tool body IDs in `tools`.'

    def validate(self, step, where, ctx):
        tools = step.get('tools') or step.get('tool_bodies')
        if not tools:
            raise ValueError(f'{where}: missing tools')
        if isinstance(tools, str):
            tools = [tools]
        if not isinstance(tools, list):
            raise ValueError(f'{where}: tools must be a list or string')
        mode = step.get('mode', 'join').lower()
        if mode not in MODES:
            raise ValueError(f'{where}: mode must be one of {MODES}')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core
        import adsk.fusion

        combines = ctx.root.features.combineFeatures
        target_body = h.get_body(ctx.root, step.get('target') or step.get('target_body'), ctx.features)
        raw_tools = step.get('tools') or step.get('tool_bodies')
        if isinstance(raw_tools, str):
            raw_tools = [raw_tools]
        tool_bodies = adsk.core.ObjectCollection.create()
        for t_name in raw_tools:
            tool_b = h.get_body(ctx.root, t_name, ctx.features)
            if tool_b != target_body:
                tool_bodies.add(tool_b)
        if tool_bodies.count == 0:
            raise ValueError("no tool bodies found for combine")

        mode = step.get('mode', 'join').lower()
        op_mode = ctx.ops.get(mode, adsk.fusion.FeatureOperations.JoinFeatureOperation)
        inp = combines.createInput(target_body, tool_bodies)
        inp.operation = op_mode
        inp.isKeepToolBodies = bool(step.get('keep_tools', False))
        feat = combines.add(inp)
        ctx.add_feature(step, feat)
