"""Chamfer timeline feature."""
from .base import BaseFeature, JS_LEN
from . import _helpers as h


class ChamferFeature(BaseFeature):
    op = 'chamfer'
    name = 'Chamfer'
    order = 50
    schema = {
        'distance': JS_LEN,
        'edges': h.JS_EDGES,
        'target': {'type': 'string'},
    }
    prompt = (
        'Chamfer (ONLY uses distance and edges!):\n'
        '   {"op": "chamfer", "distance": length, "edges": "vertical"|"top"|"bottom"|"circular"|"all"|edge_object}\n'
        '   edge_object picks edges made by an earlier step: {"feature": step_id, "faces": "all"|"side"|"start"|"end" (optional), '
        '"exclude": step_id or [ids] (optional, drops edges touching those steps\' faces), "on": sketch_id (optional, only edges in that sketch\'s plane), '
        '"type": "circle"|"line" (optional)}.\n'
        '   Prefer it over the broad words when only some edges should change, e.g. {"feature": "screw_cut", "type": "circle", "exclude": "pocket_cut"}.'
    )

    def validate(self, step, where, ctx):
        dist = step.get('distance') or step.get('radius')
        if not dist:
            for pname in ctx.params:
                if any(w in pname.lower() for w in ('chamfer', 'bevel')):
                    dist = pname
                    step['distance'] = pname
                    break
        if not dist:
            raise ValueError(f'{where}: missing distance')
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
        dist = step.get('distance') or step.get('radius')
        chamfers = ctx.root.features.chamferFeatures
        if hasattr(chamfers, 'createInput2'):
            inp = chamfers.createInput2()
            inp.chamferEdgeSets.addEqualDistanceChamferEdgeSet(
                col, adsk.core.ValueInput.createByString(ctx.ex(dist)), True
            )
        else:
            inp = chamfers.createInput(col, True)
            inp.setToEqualDistance(adsk.core.ValueInput.createByString(ctx.ex(dist)))
        feat = chamfers.add(inp)
        ctx.add_feature(step, feat)
