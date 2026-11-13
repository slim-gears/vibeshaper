"""Fillet timeline feature."""
from .base import BaseFeature, JS_LEN
from . import _helpers as h


class FilletFeature(BaseFeature):
    op = 'fillet'
    name = 'Fillet'
    order = 40
    schema = {
        'radius': JS_LEN,
        'edges': h.JS_EDGES,
        'target': {'type': 'string'},
    }
    prompt = (
        'Fillet (ONLY uses radius and edges! NEVER put thickness or remove_faces here!):\n'
        '   {"op": "fillet", "radius": length, "edges": "vertical"|"top"|"bottom"|"circular"|"all"|edge_object}'
    )
    rules = (
        '- For rounded corners or chamfered rims, use `fillet` or `chamfer` with edge selectors '
        '(`"vertical"`, `"top"`, `"circular"`).'
    )

    def validate(self, step, where, ctx):
        # Ignore dummy defaults emitted by flat schemas
        if step.get('remove_faces') not in (None, 'none') and step.get('thickness') not in (None, 0, '0', '0 mm'):
            raise ValueError(f'{where}: cannot combine fillet and shell in one step; make shell a separate step')
        rad = step.get('radius') or step.get('distance')
        if not rad:
            for pname in ctx.params:
                if any(w in pname.lower() for w in ('radius', 'fillet', 'corner', 'round')):
                    rad = pname
                    step['radius'] = pname
                    break
        if not rad:
            raise ValueError(f'{where}: missing radius')
        h.check_edges(step.get('edges', 'all'), where, ctx.features, ctx.sketches)
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core

        body = h.get_body(ctx.root, step.get('target'), ctx.features)
        edges = h.select_edges(body, step.get('edges', 'all'), ctx.features, ctx.sketches)
        if not edges:
            raise ValueError(f"no edges matched selector {step.get('edges')!r}")
        col = adsk.core.ObjectCollection.create()
        for e in edges:
            col.add(e)
        fillets = ctx.root.features.filletFeatures
        rad = step.get('radius') or step.get('distance')
        inp = fillets.createInput()
        inp.addConstantRadiusEdgeSet(col, adsk.core.ValueInput.createByString(ctx.ex(rad)), True)
        feat = fillets.add(inp)
        ctx.add_feature(step, feat)
