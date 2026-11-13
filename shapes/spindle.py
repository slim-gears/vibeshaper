"""DC spindle motor with a collet nose (the 52 mm ER11 spindles of hobby CNC machines).

Drawn as the round body and the nose with its collet nut, which is what a spindle clamp and the
Z travel have to fit. The bottom face of the body is the xy plane at z = 0: the body goes up,
the nose down. Lengths vary between sellers; set them from the listing's drawing.
"""
from .base import BaseShape
from . import _parts as p

DEFAULTS = {'diameter': 52.0, 'length': 160.0, 'nose': 19.0, 'nose_len': 25.0}
KEYS = tuple(DEFAULTS)
# boss: front bearing cap; shaft: the spindle shaft between it and the collet nut; cap: rear cap;
# terminal: the two power posts on it; collet_bore: the opening in the nut
DETAIL = {'boss': 26.0, 'boss_len': 6.0, 'shaft': 12.0, 'shaft_len': 5.0, 'cap_h': 4.0, 'terminal': 4.0,
          'terminal_h': 5.0, 'terminal_gap': 16.0, 'collet_bore': 7.0}
COLLETS = ('ER8', 'ER11', 'ER16', 'ER20')


class Spindle(BaseShape):
    op = 'spindle'
    name = 'Spindle'
    order = 56
    schema = dict({'collet': {'enum': list(COLLETS)}, 'nose': {'type': ['string', 'number']},
                   'nose_len': {'type': ['string', 'number']}}, **p.PLAIN_KEYS)
    prompt = '''{"op": "spindle", "id": name, "collet": "ER8"|"ER11"|"ER16"|"ER20" (optional, default "ER11"), "diameter": body (optional, default 52 mm),
 "length": body (optional, default 160 mm), "nose": collet nut diameter (optional, default 19 mm), "nose_len": (optional, default 25 mm), "note": text (optional, e.g. "300 W, 48 V")}
  A DC milling spindle (bought part). The bottom face of the body is the xy plane at z = 0; the body goes up, the
  collet nose down to z = -"<id>_nose_len". Clamp it around "<id>_diameter".'''

    def validate(self, step, where):
        p.check(step, where, (), {'collet': COLLETS})
        for key in KEYS:
            if key in step and p.num(step[key]) is not None and p.num(step[key]) <= 0:
                raise ValueError(f'{where}: {key} must be more than 0')

    def expand(self, step):
        gid = step['id']
        n = lambda k: f'{gid}_{k}'
        params = p.sizes(gid, dict(DEFAULTS, **DETAIL), step, KEYS + tuple(DETAIL))
        nut_top = f'-({n("boss_len")} + {n("shaft_len")})'
        t = f'{n("terminal_gap")} / 2'
        steps = [
            p.sketch(n('sk'), [p.circle([0, 0], n('diameter'))]),
            p.extrude(n('body'), n('sk'), n('length'), 'new_body'),
            p.chamfer(n('body_edges'), '1 mm', {'feature': n('body'), 'type': 'circle'}),
            p.sketch(n('cap_sk'), [p.circle([0, 0], f'{n("diameter")} - 6 mm')], offset=n('length')),
            p.extrude(n('cap'), n('cap_sk'), n('cap_h'), 'join'),
            p.chamfer(n('cap_edge'), '0.8 mm', {'feature': n('cap'), 'faces': 'end', 'type': 'circle'}),
            p.sketch(n('terminal_sk'), [p.circle([t, 0], n('terminal')), p.circle([f'-{t}', 0], n('terminal'))],
                     offset=f'{n("length")} + {n("cap_h")}'),
            p.extrude(n('terminals'), n('terminal_sk'), n('terminal_h'), 'join'),
            p.sketch(n('boss_sk'), [p.circle([0, 0], n('boss'))]),
            p.extrude(n('boss_body'), n('boss_sk'), f'-{n("boss_len")}', 'join'),
            p.chamfer(n('boss_edge'), '0.5 mm', {'feature': n('boss_body'), 'faces': 'end', 'type': 'circle'}),
            p.sketch(n('shaft_sk'), [p.circle([0, 0], n('shaft'))], offset=f'-{n("boss_len")}'),
            p.extrude(n('shaft_body'), n('shaft_sk'), f'-{n("shaft_len")}', 'join'),
            p.sketch(n('nut_sk'), [p.circle([0, 0], n('nose'))], offset=nut_top),
            p.extrude(n('nut'), n('nut_sk'), f'{n("boss_len")} + {n("shaft_len")} - {n("nose_len")}', 'join'),
            p.chamfer(n('nut_edge'), '1 mm', {'feature': n('nut'), 'faces': 'end', 'type': 'circle'}),
            p.sketch(n('collet_sk'), [p.circle([0, 0], n('collet_bore'))], offset=f'-{n("nose_len")}'),
            p.extrude(gid, n('collet_sk'), '3 mm', 'cut'),
        ]
        return params, steps

    def bom(self, step):
        d = p.num(step.get('diameter', DEFAULTS['diameter']))
        size = f', {d:g} mm body' if d is not None else ''
        return [p.item('Motion', f'{step.get("collet", "ER11")} DC spindle{size}', step)]
