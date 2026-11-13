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
        params.update({n('bridge'): '2.5 mm', n('slot_w'): '0.8 mm', n('slot_pitch'): '2.5 mm',
                       n('screw_z'): f'({n("length")} / 2 - {n("slot_pitch")}) / 2'})
        half = f'{n("length")} / 2'
        r_out = f'{n("diameter")} / 2 + 1 mm'
        steps = [
            p.sketch(n('sk'), [p.circle([0, 0], n('diameter'))]),
            p.extrude(n('body'), n('sk'), n('length'), 'new_body'),
            p.chamfer(n('end_edges'), '0.5 mm', {'feature': n('body'), 'type': 'circle'}),
        ]
        # three slots from alternating sides, each leaving a bridge: the part that flexes
        for k, (z, side) in enumerate(((f'{half} - {n("slot_pitch")}', ''), (half, '-'),
                                       (f'{half} + {n("slot_pitch")}', ''))):
            slot = p.rect([f'{side}({n("bridge")} + 1 mm) / 2', z], f'{n("diameter")} + 1 mm - {n("bridge")}',
                          n('slot_w'))
            steps += [p.sketch(n(f'slot{k}_sk'), [slot], plane='xz', offset=f'-({r_out})'),
                      p.extrude(n(f'slot{k}'), n(f'slot{k}_sk'), f'2 * ({r_out})', 'cut')]
        steps += [
            p.sketch(n('bore1_sk'), [p.circle([0, 0], n('bore1'))]),
            p.extrude(n('bore1_cut'), n('bore1_sk'), half, 'cut'),
            p.sketch(n('bore2_sk'), [p.circle([0, 0], n('bore2'))], offset=n('length')),
            p.extrude(n('bore2_cut'), n('bore2_sk'), f'-{half}', 'cut'),
            p.sketch(n('screw_sk'), [p.circle([0, n('screw_z')], '3.3 mm'),
                                     p.circle([0, f'{n("length")} - {n("screw_z")}'], '3.3 mm')],
                     plane='xz', offset=r_out),
            p.extrude(gid, n('screw_sk'), f'-({r_out})', 'cut'),   # a set screw into each hub
        ]
        return params, steps

    def bom(self, step):
        v = self._sizes(step)
        return [p.item('Motion', f'Flexible shaft coupler {v["bore1"]:g} x {v["bore2"]:g} mm, '
                                 f'D{v["diameter"]:g} L{v["length"]:g}', step)]
