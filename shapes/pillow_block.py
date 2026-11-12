"""Pillow block bearing (KP08 and similar): a ball bearing in a housing with a two-hole base,
used to hold the free end of a lead screw.

Sizes are those of the common KP08 (8 mm bore, 15 mm center height, 42 mm hole spacing).
The base sits on the xy plane at z = 0, centered on the origin; the shaft runs along y.
"""
from .base import BaseShape
from . import _parts as p

SIZES = {
    'KP08': {'bore': 8.0, 'center_h': 15.0, 'length': 55.0, 'width': 13.0, 'hole_spacing': 42.0, 'hole': 5.0,
             'base_t': 5.0, 'housing': 28.0},
}
KEYS = ('bore', 'center_h', 'length', 'width', 'hole_spacing', 'hole', 'base_t', 'housing')


class PillowBlock(BaseShape):
    op = 'pillow_block'
    name = 'Pillow block bearing'
    order = 54
    schema = dict({'model': {'enum': list(SIZES)}}, **p.PLAIN_KEYS)
    prompt = '''{"op": "pillow_block", "id": name, "model": "KP08" (optional, default "KP08"), "note": text (optional)}
  A pillow block bearing (bought part) for the free end of a lead screw. Base on z = 0, centered on the origin, shaft
  along y at height "<id>_center_h". Parameters: "<id>_bore", "<id>_length" (base, along x), "<id>_width" (along y),
  "<id>_hole_spacing" (2 base holes on the x axis), "<id>_hole".'''

    def validate(self, step, where):
        p.check(step, where, (), {'model': list(SIZES)})

    def expand(self, step):
        gid = step['id']
        n = lambda k: f'{gid}_{k}'
        params = p.sizes(gid, SIZES[step.get('model', 'KP08')], step, KEYS)
        back = f'-{n("width")} / 2'
        half = f'{n("hole_spacing")} / 2'
        steps = [
            p.sketch(n('base_sk'), [p.rect([0, 0], n('length'), n('width'))]),
            p.extrude(n('base'), n('base_sk'), n('base_t'), 'new_body'),
            p.sketch(n('post_sk'), [p.rect([0, 0], n('housing'), n('width'))]),
            p.extrude(n('post'), n('post_sk'), n('center_h'), 'join'),
            p.sketch(n('housing_sk'), [p.circle([0, n('center_h')], n('housing'))], plane='xz', offset=back),
            p.extrude(n('housing_body'), n('housing_sk'), n('width'), 'join'),
            p.sketch(n('bore_sk'), [p.circle([0, n('center_h')], n('bore'))], plane='xz', offset=back),
            p.extrude(n('bore_cut'), n('bore_sk'), n('width'), 'cut'),
            p.sketch(n('hole_sk'), [p.circle([half, 0], n('hole')), p.circle([f'-{half}', 0], n('hole'))]),
            p.extrude(gid, n('hole_sk'), n('base_t'), 'cut'),
        ]
        return params, steps

    def bom(self, step):
        model = step.get('model', 'KP08')
        return [p.item('Motion', f'{model} pillow block bearing, {SIZES[model]["bore"]:g} mm bore', step)]
