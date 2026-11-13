"""Shell timeline feature."""
from .base import BaseFeature, JS_LEN
from . import _helpers as h


class ShellFeature(BaseFeature):
    op = 'shell'
    name = 'Shell'
    order = 60
    schema = {
        'thickness': JS_LEN,
        'remove_faces': {'enum': ['top', 'bottom', 'none']},
        'target': {'type': 'string'},
    }
    prompt = (
        'Shell (ONLY uses thickness and remove_faces! NEVER put radius or edges here!):\n'
        '   {"op": "shell", "thickness": length, "remove_faces": "top"|"bottom"|"none"}'
    )
    rules = (
        '- For hollow boxes or open containers, prefer `shell` with `remove_faces: "top"` over manual pocket cuts!\n'
        '- When making an open box with rounded corners: FIRST `extrude`, NEXT `fillet` the vertical corners, '
        'THEN `shell` the top face (or shell first, then fillet). They are two distinct steps!'
    )

    def validate(self, step, where, ctx):
        h.need(step, where, 'thickness')
        faces = step.get('remove_faces', 'top')
        if isinstance(faces, str) and faces not in h.FACE_SELECTORS:
            raise ValueError(f'{where}: remove_faces selector must be one of {h.FACE_SELECTORS} or an object')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core

        body = h.get_body(ctx.root, step.get('target'), ctx.features)
        faces = h.select_faces(body, step.get('remove_faces', 'top'))
        col = adsk.core.ObjectCollection.create()
        for f in faces:
            col.add(f)
        if col.count == 0:
            col.add(body)
        shells = ctx.root.features.shellFeatures
        inp = shells.createInput(col, False)
        inp.insideThickness = adsk.core.ValueInput.createByString(ctx.ex(step['thickness']))
        feat = shells.add(inp)
        ctx.add_feature(step, feat)
