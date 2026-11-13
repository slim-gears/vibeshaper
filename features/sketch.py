"""Sketch timeline feature."""
import sys

from .base import BaseFeature, JS_LEN, JS_PLANE, PLANES
from . import _helpers as h
from . import entities

CONSTRAINT_TYPES = (
    'perpendicular', 'parallel', 'concentric', 'tangent', 'equal', 'coincident', 'midpoint', 'symmetry'
)


class SketchFeature(BaseFeature):
    op = 'sketch'
    name = 'Sketch'
    order = 10
    target_key = None
    prompt = (
        'Sketch:\n'
        '   {"op": "sketch", "id": unique_name, "plane": "xy"|"xz"|"yz", "offset": length (optional), '
        '"entities": [entity, ...], "constraints": [{"type": "perpendicular"|"parallel"|"concentric"|"tangent"|"equal", '
        '"entities": [id1, id2]}, ...] (optional)}'
    )

    def __init__(self):
        entities.on_change(self._on_entity_change)

    @staticmethod
    def _on_entity_change():
        pkg = sys.modules.get(__package__)
        if pkg is not None:
            pkg.notify_change()

    def get_schema(self):
        return {
            'plane': JS_PLANE,
            'offset': JS_LEN,
            'entities': entities.schema(),
            'constraints': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'type': {'enum': list(CONSTRAINT_TYPES)},
                        'entities': {'type': 'array', 'items': {'type': 'string'}},
                        'point': {'type': 'string'},
                        'entity': {'type': 'string'},
                        'symmetry_line': {'type': 'string'},
                    },
                    'required': ['type'],
                },
            },
        }

    def extra_prompt(self):
        ent_prompt = entities.prompt()
        if not ent_prompt:
            return ''
        return (
            'SKETCH ENTITIES (entities can have optional "id": "name" to be referenced by constraints)\n'
            + ent_prompt
        )

    def validate(self, step, where, ctx):
        h.need(step, where, 'id', 'plane', 'entities')
        if step['plane'] not in PLANES:
            raise ValueError(f'{where}: plane must be one of {PLANES}')
        if step['id'] in ctx.sketches:
            raise ValueError(f'{where}: duplicate sketch id {step["id"]!r}')
        if not isinstance(step['entities'], list) or not step['entities']:
            raise ValueError(f'{where}: entities must be a non-empty list')
        ent_ids = set()
        for j, e in enumerate(step['entities']):
            entities.validate_entity(e, f'{where}.entities[{j}]', ent_ids)

        if 'constraints' in step:
            if not isinstance(step['constraints'], list):
                raise ValueError(f'{where}: constraints must be a list')
            for c_idx, c in enumerate(step['constraints']):
                cw = f'{where}.constraints[{c_idx}]'
                h.need(c, cw, 'type')
                ctype = c['type']
                if ctype not in CONSTRAINT_TYPES:
                    raise ValueError(f'{cw}: unknown constraint type {ctype!r}')
                targets = c.get('entities') or []
                if not isinstance(targets, list):
                    raise ValueError(f'{cw}: entities must be a list')
                for t_name in targets:
                    base_id = t_name.split('.')[0]
                    if base_id not in ent_ids:
                        raise ValueError(f'{cw}: target entity {t_name!r} not found in sketch entities')
        ctx.sketches.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core

        P = adsk.core.Point3D.create
        plane = ctx.base_planes[step['plane']]
        off = step.get('offset')
        if off not in (None, 0, '0', '0 mm'):
            pi = ctx.root.constructionPlanes.createInput()
            pi.setByOffset(plane, adsk.core.ValueInput.createByString(ctx.ex(off)))
            plane = ctx.root.constructionPlanes.add(pi)
        sk = ctx.root.sketches.add(plane)
        sk.name = str(step['id'])
        to_world = ctx.world[step['plane']]

        def pt(a, b, sk=sk, to_world=to_world):
            p = sk.modelToSketchSpace(P(*to_world(a, b)))
            p.z = 0
            return p

        ent_map = {}
        for e in step['entities']:
            entities.draw(sk, e, ctx.ex, ctx.cm, pt, ent_map)

        # Process explicit sketch constraints
        for c in step.get('constraints', []):
            ctype = c.get('type')
            ents = c.get('entities', [])
            try:
                if ctype == 'perpendicular' and len(ents) >= 2:
                    sk.geometricConstraints.addPerpendicular(ent_map[ents[0]], ent_map[ents[1]])
                elif ctype == 'parallel' and len(ents) >= 2:
                    sk.geometricConstraints.addParallel(ent_map[ents[0]], ent_map[ents[1]])
                elif ctype == 'concentric' and len(ents) >= 2:
                    sk.geometricConstraints.addConcentric(ent_map[ents[0]], ent_map[ents[1]])
                elif ctype == 'tangent' and len(ents) >= 2:
                    sk.geometricConstraints.addTangent(ent_map[ents[0]], ent_map[ents[1]])
                elif ctype == 'equal' and len(ents) >= 2:
                    sk.geometricConstraints.addEqual(ent_map[ents[0]], ent_map[ents[1]])
                elif ctype == 'coincident':
                    e1 = ent_map.get(c.get('entity1') or (ents[0] if ents else None))
                    e2 = ent_map.get(c.get('entity2') or (ents[1] if len(ents) > 1 else None))
                    if e1 and e2:
                        sk.geometricConstraints.addCoincident(e1, e2)
                elif ctype == 'midpoint':
                    pt_ent = ent_map.get(c.get('point') or (ents[0] if ents else None))
                    crv_ent = ent_map.get(c.get('entity') or (ents[1] if len(ents) > 1 else None))
                    if pt_ent and crv_ent:
                        sk.geometricConstraints.addMidPoint(pt_ent, crv_ent)
                elif ctype == 'symmetry' and len(ents) >= 2:
                    sym_line = ent_map.get(c.get('symmetry_line'))
                    if sym_line:
                        sk.geometricConstraints.addSymmetry(ent_map[ents[0]], ent_map[ents[1]], sym_line)
            except Exception:
                pass

        # Never fix geometry: fixed curves ignore later parameter changes.
        ctx.sketches[step['id']] = sk
