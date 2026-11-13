"""NEMA stepper motor (sizes 14, 17, 23): square body with chamfered corners, pilot boss, shaft with
a flat, the four mounting holes on the face, and the cable connector on one side (-y), near the back.

Face sizes, hole spacing and pilot diameters follow NEMA ICS 16; shaft lengths are typical of
hobby motors. The face is the xy plane at z = 0, the body goes down (-z), the shaft points up.
"""
from .base import BaseShape
from . import _parts as p

# face: body width; pitch: mounting hole spacing (square); hole: tapped hole (drawn at the
# screw's size); hole_depth; pilot: boss diameter; pilot_h: its height; shaft: diameter;
# shaft_len: from the face.
SIZES = {
    '14': {'corner': 3.5, 'face': 35.2, 'pitch': 26.0, 'hole': 3.0, 'hole_depth': 3.5, 'pilot': 22.0, 'pilot_h': 2.0,
           'shaft': 5.0, 'shaft_len': 20.0, 'screw': 'M3'},
    '17': {'corner': 4.0, 'face': 42.3, 'pitch': 31.0, 'hole': 3.0, 'hole_depth': 4.5, 'pilot': 22.0, 'pilot_h': 2.0,
           'shaft': 5.0, 'shaft_len': 24.0, 'screw': 'M3'},
    '23': {'corner': 5.0, 'face': 56.4, 'pitch': 47.14, 'hole': 5.0, 'hole_depth': 5.0, 'pilot': 38.1, 'pilot_h': 1.6,
           'shaft': 6.35, 'shaft_len': 21.0, 'screw': 'M5'},
}
KEYS = ('corner', 'face', 'pitch', 'hole', 'hole_depth', 'pilot', 'pilot_h', 'shaft', 'shaft_len', 'flat_len',
        'plug_w', 'plug_h', 'plug_out')
PLUG = {'flat_len': 15.0, 'plug_w': 16.0, 'plug_h': 8.0, 'plug_out': 4.0}  # shaft flat; connector housing


class NemaMotor(BaseShape):
    op = 'nema_motor'
    name = 'NEMA stepper motor'
    order = 50
    schema = dict({'size': {'type': ['string', 'number']}, 'length': {'type': ['string', 'number']}},
                  **p.PLAIN_KEYS)
    prompt = '''{"op": "nema_motor", "id": name, "size": "14"|"17"|"23", "length": body length (e.g. 40 mm), "note": text (optional, e.g. "1.5 A, 0.42 N·m")}
  A stepper motor (bought part): square body, pilot boss, shaft, the 4 tapped holes on the face and the cable connector
  on the -y side near the back. The face is the xy plane at z = 0, the body goes down, the shaft points up (+z) from [0, 0]. Model it in its own component and place it
  with instances; design mounts around "<id>_pitch" (hole spacing), "<id>_pilot" (boss) and "<id>_face" (body width).'''

    def validate(self, step, where):
        p.check(step, where, ('size', 'length'), {'size': list(SIZES) + [int(s) for s in SIZES]})

    def expand(self, step):
        gid = step['id']
        n = lambda k: f'{gid}_{k}'
        params = p.sizes(gid, dict(SIZES[str(step['size'])], **PLUG), step, KEYS)
        params[n('length')] = p.length(step['length'])
        half = f'{n("pitch")} / 2'
        holes = [p.circle([f'{sx}{half}', f'{sy}{half}'], n('hole')) for sx in ('', '-') for sy in ('', '-')]
        side = f'-({n("face")} / 2 + {n("plug_out")})'           # the connector's outer face (y)
        back = f'1 mm - {n("length")}'                             # the connector's bottom (z)
        steps = [
            p.sketch(n('body_sk'), [p.rect([0, 0], n('face'), n('face'))]),
            p.extrude(n('body'), n('body_sk'), f'-{n("length")}', 'new_body'),
            p.chamfer(n('corners'), n('corner'), 'vertical'),
            p.chamfer(n('front_edge'), '0.5 mm', {'feature': n('body'), 'faces': 'start'}),
            p.chamfer(n('back_edge'), '0.5 mm', {'feature': n('body'), 'faces': 'end'}),
            p.sketch(n('pilot_sk'), [p.circle([0, 0], n('pilot'))]),
            p.extrude(n('pilot_boss'), n('pilot_sk'), n('pilot_h'), 'join'),
            p.chamfer(n('pilot_edge'), '0.4 mm', {'feature': n('pilot_boss'), 'faces': 'end', 'type': 'circle'}),
            p.sketch(n('shaft_sk'), [p.circle([0, 0], n('shaft'))], offset=n('pilot_h')),
            p.extrude(n('shaft_body'), n('shaft_sk'), f'{n("shaft_len")} - {n("pilot_h")}', 'join'),
            p.chamfer(n('shaft_tip'), '0.4 mm', {'feature': n('shaft_body'), 'faces': 'end'}),
            p.sketch(n('flat_sk'), [p.rect([f'{n("shaft")} / 2 + 0.25 mm', 0], '1.5 mm', f'{n("shaft")} + 1 mm')],
                     offset=n('shaft_len')),
            p.extrude(n('flat'), n('flat_sk'), f'-{n("flat_len")}', 'cut'),
            p.sketch(n('plug_sk'), [p.rect([0, f'-({n("face")} / 2 + {n("plug_out")} / 2 - 0.5 mm)'], n('plug_w'),
                                           f'{n("plug_out")} + 1 mm')], offset=back),
            p.extrude(n('plug'), n('plug_sk'), n('plug_h'), 'join'),
            p.sketch(n('socket_sk'), [p.rect([0, f'{back} + {n("plug_h")} / 2'], f'{n("plug_w")} - 4 mm',
                                             f'{n("plug_h")} - 3 mm')], plane='xz', offset=side),
            p.extrude(n('socket'), n('socket_sk'), f'{n("plug_out")} - 0.5 mm', 'cut'),
            p.sketch(n('hole_sk'), holes),
            p.extrude(gid, n('hole_sk'), f'-{n("hole_depth")}', 'cut'),
        ]
        return params, steps

    def bom(self, step):
        size = str(step['size'])
        face = SIZES[size]['face']
        return [p.item('Motion', f'NEMA{size} stepper motor, {face:g} mm square, body {{length}}', step,
                       length=step['length'])]
