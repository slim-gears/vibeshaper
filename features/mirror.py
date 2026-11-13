"""Mirror timeline feature."""
from .base import BaseFeature, JS_PLANE, PLANES
from . import _helpers as h


class MirrorFeature(BaseFeature):
    op = 'mirror'
    name = 'Mirror'
    order = 100
    schema = {
        'feature': {'type': 'string'},
        'plane': JS_PLANE,
        'combine': {'type': 'boolean'},
        'target': {'type': 'string'},
    }
    prompt = (
        'Mirror:\n'
        '   {"op": "mirror", "feature": feature_id (optional), "plane": "xy"|"xz"|"yz"|"top"|"bottom", '
        '"combine": true|false (optional, default true)}'
    )
    rules = (
        '- For symmetric designs, model ONE half and use `mirror` across "xz" or "yz" '
        'with `combine: true` to complete the full symmetric body!'
    )

    def validate(self, step, where, ctx):
        if 'feature' in step and step['feature'] not in ctx.features:
            raise ValueError(f'{where}: feature {step["feature"]!r} not found in previous features')
        plane = step.get('plane', 'xz')
        if isinstance(plane, str) and plane not in PLANES and plane not in h.FACE_SELECTORS:
            raise ValueError(f'{where}: plane must be one of {PLANES} or a face selector')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core

        mirrors = ctx.root.features.mirrorFeatures
        input_entities = adsk.core.ObjectCollection.create()
        is_body = False
        if 'feature' in step:
            f = ctx.features.get(step['feature'])
            if not f:
                raise ValueError(f"feature {step['feature']!r} not found for mirror")
            input_entities.add(f)
        else:
            body = h.get_body(ctx.root, step.get('target') or step.get('target_body'), ctx.features)
            input_entities.add(body)
            is_body = True

        plane_spec = step.get('plane', 'xz')
        if isinstance(plane_spec, str) and plane_spec.lower() in ctx.base_planes:
            mirror_plane = ctx.base_planes[plane_spec.lower()]
        else:
            ref_body = h.get_body(ctx.root, None, ctx.features)
            matched_faces = h.select_faces(ref_body, plane_spec)
            if not matched_faces:
                raise ValueError(f"no plane or face matched for mirror plane {plane_spec!r}")
            mirror_plane = matched_faces[0]

        inp = mirrors.createInput(input_entities, mirror_plane)
        if is_body:
            inp.isCombine = bool(step.get('combine', True))
        feat = mirrors.add(inp)
        ctx.add_feature(step, feat)
