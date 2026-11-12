"""DC spindle motor with a collet nose (the 52 mm ER11 spindles of hobby CNC machines).

Drawn as the round body and the nose with its collet nut, which is what a spindle clamp and the
Z travel have to fit. The bottom face of the body is the xy plane at z = 0: the body goes up,
the nose down. Lengths vary between sellers; set them from the listing's drawing.
"""
from .base import BaseShape
from . import _parts as p

DEFAULTS = {'diameter': 52.0, 'length': 160.0, 'nose': 19.0, 'nose_len': 30.0}
KEYS = tuple(DEFAULTS)
COLLETS = ('ER8', 'ER11', 'ER16', 'ER20')


class Spindle(BaseShape):
    op = 'spindle'
    name = 'Spindle'
    order = 56
    schema = dict({'collet': {'enum': list(COLLETS)}, 'nose': {'type': ['string', 'number']},
                   'nose_len': {'type': ['string', 'number']}}, **p.PLAIN_KEYS)
    prompt = '''{"op": "spindle", "id": name, "collet": "ER8"|"ER11"|"ER16"|"ER20" (optional, default "ER11"), "diameter": body (optional, default 52 mm),
 "length": body (optional, default 160 mm), "nose": collet nut diameter (optional, default 19 mm), "nose_len": (optional, default 30 mm), "note": text (optional, e.g. "300 W, 48 V")}
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
        params = p.sizes(gid, DEFAULTS, step, KEYS)
        steps = [
            p.sketch(n('sk'), [p.circle([0, 0], n('diameter'))]),
            p.extrude(n('body'), n('sk'), n('length'), 'new_body'),
            p.sketch(n('nose_sk'), [p.circle([0, 0], n('nose'))]),
            p.extrude(gid, n('nose_sk'), f'-{n("nose_len")}', 'join'),
        ]
        return params, steps

    def bom(self, step):
        d = p.num(step.get('diameter', DEFAULTS['diameter']))
        size = f', {d:g} mm body' if d is not None else ''
        return [p.item('Motion', f'{step.get("collet", "ER11")} DC spindle{size}', step)]
