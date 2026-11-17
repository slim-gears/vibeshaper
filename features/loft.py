"""Loft timeline feature."""
from .base import BaseFeature, JS_MODE, MODES
from . import _helpers as h


def _guide_path(root, sk, name):
    import adsk.core

    curves = sk.sketchCurves
    if curves.count == 0:
        raise ValueError(f"guide sketch {name!r} has no curves")
    try:
        return root.features.createPath(curves.item(0), True)
    except Exception:
        coll = adsk.core.ObjectCollection.create()
        for k in range(curves.count):
            coll.add(curves.item(k))
        return root.features.createPath(coll, False)


class LoftFeature(BaseFeature):
    op = 'loft'
    name = 'Loft'
    order = 125
    target_key = None
    schema = {
        'sketches': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 2},
        'rails': {'type': 'array', 'items': {'type': 'string'}},
        'centerline': {'type': 'string'},
        'closed': {'type': 'boolean'},
        'mode': JS_MODE,
    }
    prompt = (
        'Loft:\n'
        '   {"op": "loft", "sketches": [sketch_id_1, sketch_id_2, ...], "rails": [rail_sketch_id, ...] (optional), '
        '"centerline": centerline_sketch_id (optional), "closed": false (optional), '
        '"mode": "new_body"|"join"|"cut"|"intersect"}'
    )
    rules = (
        '- For smooth transitions between different cross-sections (e.g. a round-to-rectangular nozzle, tapered '
        'wing, horn, or ergonomic handle), draw each cross-section in its own offset `sketch` and blend them with `loft`.\n'
        '- Every guide rail in `loft` `"rails"` MUST touch the perimeter of EVERY cross-section in `"sketches"` at the exact '
        'same coordinates (`ASM_GUIDE_NOT_INTERSECT` occurs if a rail misses any intermediate profile); if you want a rail to '
        'curve between start and end profiles without matching an intermediate profile, omit the intermediate profile or use `"centerline"` instead.'
    )

    def label(self, step):
        what = step.get('id') or ' -> '.join(str(x) for x in (step.get('sketches') or ())[:2])
        return f'loft {what}'.strip()

    def validate(self, step, where, ctx):
        h.need(step, where, 'sketches')
        sks = step['sketches']
        if not isinstance(sks, list) or len(sks) < 2:
            raise ValueError(f'{where}: sketches must be a list of at least 2 sketch ids')
        if len(set(sks)) != len(sks):
            raise ValueError(f'{where}: sketches must be distinct sketch ids')
        for sid in sks:
            if not isinstance(sid, str) or sid not in ctx.sketches:
                raise ValueError(f'{where}: unknown section sketch {sid!r}')
        if 'rails' in step and 'centerline' in step:
            raise ValueError(f'{where}: loft cannot have both rails and centerline')
        if 'rails' in step:
            rails = step['rails']
            if not isinstance(rails, list) or not rails:
                raise ValueError(f'{where}: rails must be a non-empty list of sketch ids')
            for rid in rails:
                if not isinstance(rid, str) or rid not in ctx.sketches:
                    raise ValueError(f'{where}: unknown rail sketch {rid!r}')
        if 'centerline' in step:
            cid = step['centerline']
            if not isinstance(cid, str) or cid not in ctx.sketches:
                raise ValueError(f'{where}: unknown centerline sketch {cid!r}')
        if 'closed' in step and not isinstance(step['closed'], bool):
            raise ValueError(f'{where}: closed must be true or false')
        mode = step.get('mode', 'new_body').lower()
        if mode not in MODES:
            raise ValueError(f'{where}: mode must be one of {MODES}')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core
        import adsk.fusion

        lofts = ctx.root.features.loftFeatures
        mode = step.get('mode', 'new_body').lower()
        op_mode = ctx.ops.get(mode, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        inp = h.own_bodies(lofts.createInput(op_mode), ctx.root, mode)
        inp.isSolid = True
        if step.get('closed'):
            inp.isClosed = True

        sections = inp.loftSections
        for sid in step['sketches']:
            sk = ctx.sketches[sid]
            if sk.profiles.count == 0:
                raise ValueError(f"section sketch {sid!r} has no closed profiles")
            if sk.profiles.count == 1:
                sections.add(sk.profiles.item(0))
            else:
                profs = adsk.core.ObjectCollection.create()
                for k in range(sk.profiles.count):
                    profs.add(sk.profiles.item(k))
                sections.add(profs)

        if 'centerline' in step:
            cid = step['centerline']
            inp.centerLineOrRails.addCenterLine(_guide_path(ctx.root, ctx.sketches[cid], cid))
        elif 'rails' in step:
            for rid in step['rails']:
                inp.centerLineOrRails.addRail(_guide_path(ctx.root, ctx.sketches[rid], rid))

        feat = lofts.add(inp)
        ctx.add_feature(step, feat)
