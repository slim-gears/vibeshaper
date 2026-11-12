"""Flexible shaft coupler (the clamp-style aluminium ones that join a motor shaft to a lead
screw). Drawn as a cylinder along +z from z = 0 with a bore from each end.
"""
from .base import BaseShape
from . import _parts as p

DEFAULTS = {'bore1': 5.0, 'bore2': 8.0, 'diameter': 19.0, 'length': 25.0}


class ShaftCoupler(BaseShape):
    op = 'shaft_coupler'
    name = 'Shaft coupler'
    order = 55
    schema = dict({'bore1': {'type': 'number'}, 'bore2': {'type': 'number'}}, **p.PLAIN_KEYS)
    prompt = '''{"op": "shaft_coupler", "id": name, "bore1": mm (optional, default 5), "bore2": mm (optional, default 8), "diameter": mm (optional, default 19), "length": mm (optional, default 25), "note": text (optional)}
  A flexible shaft coupler (bought part) along +z from z = 0: "bore1" from the bottom (the motor shaft), "bore2" from the
  top (the screw). Parameters: "<id>_diameter", "<id>_length".'''

    def validate(self, step, where):
        p.check(step, where)
        for key in DEFAULTS:
            if key in step and (p.num(step[key]) is None or p.num(step[key]) <= 0):
                raise ValueError(f'{where}: {key} must be a number of mm, more than 0')
        v = self._sizes(step)
        if max(v['bore1'], v['bore2']) >= v['diameter']:
            raise ValueError(f'{where}: the bores must be smaller than the diameter')

    @staticmethod
    def _sizes(step):
        return {k: p.num(step.get(k, d)) for k, d in DEFAULTS.items()}

    def expand(self, step):
        gid = step['id']
        n = lambda k: f'{gid}_{k}'
        params = {n(k): f'{v:g} mm' for k, v in self._sizes(step).items()}
        half = f'{n("length")} / 2'
        steps = [
            p.sketch(n('sk'), [p.circle([0, 0], n('diameter'))]),
            p.extrude(n('body'), n('sk'), n('length'), 'new_body'),
            p.sketch(n('bore1_sk'), [p.circle([0, 0], n('bore1'))]),
            p.extrude(n('bore1_cut'), n('bore1_sk'), half, 'cut'),
            p.sketch(n('bore2_sk'), [p.circle([0, 0], n('bore2'))], offset=n('length')),
            p.extrude(gid, n('bore2_sk'), f'-{half}', 'cut'),
        ]
        return params, steps

    def bom(self, step):
        v = self._sizes(step)
        return [p.item('Motion', f'Flexible shaft coupler {v["bore1"]:g} x {v["bore2"]:g} mm, '
                                 f'D{v["diameter"]:g} L{v["length"]:g}', step)]
