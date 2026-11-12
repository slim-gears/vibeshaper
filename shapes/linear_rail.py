"""Miniature linear guides (MGN7, MGN9, MGN12, MGN15): the rail, cut to length, and its carriage.

Sizes follow the HIWIN MGN catalog, which the common clones copy. Check the hole pitch and the
carriage's hole spacing against what you receive; every size is a parameter.

Both are modeled on the rail's own axes: the rail runs along +x from x = 0, centered on y = 0,
with its bottom on z = 0. A carriage is centered on x = y = 0 in those same axes, so placing it
at [x, 0, 0] relative to its rail puts it on the rail.
"""
from .base import BaseShape
from . import _parts as p

# rail: width, height, hole pitch, through hole, counterbore diameter and depth
RAILS = {
    'MGN7': {'rail_w': 7.0, 'rail_h': 4.8, 'pitch': 15.0, 'hole': 2.4, 'cbore': 4.2, 'cbore_depth': 2.3},
    'MGN9': {'rail_w': 9.0, 'rail_h': 6.5, 'pitch': 20.0, 'hole': 3.5, 'cbore': 6.0, 'cbore_depth': 3.5},
    'MGN12': {'rail_w': 12.0, 'rail_h': 8.0, 'pitch': 25.0, 'hole': 3.5, 'cbore': 6.0, 'cbore_depth': 4.5},
    'MGN15': {'rail_w': 15.0, 'rail_h': 10.0, 'pitch': 40.0, 'hole': 3.5, 'cbore': 6.0, 'cbore_depth': 4.5},
}
RAIL_KEYS = ('rail_w', 'rail_h', 'pitch', 'hole', 'cbore', 'cbore_depth')

# carriage: height over the rail's bottom, gap under it, width, hole spacing across (b) and
# along (c, per block type), length (per block type), mounting thread (drawn at its size)
CARRIAGES = {
    'MGN7': {'height': 8.0, 'gap': 1.5, 'width': 17.0, 'hole_b': 12.0, 'c': {'C': 8.0, 'H': 13.0},
             'l': {'C': 22.5, 'H': 30.8}, 'thread': 2.0},
    'MGN9': {'height': 10.0, 'gap': 2.0, 'width': 20.0, 'hole_b': 15.0, 'c': {'C': 10.0, 'H': 16.0},
             'l': {'C': 28.9, 'H': 39.9}, 'thread': 3.0},
    'MGN12': {'height': 13.0, 'gap': 3.0, 'width': 27.0, 'hole_b': 20.0, 'c': {'C': 15.0, 'H': 20.0},
              'l': {'C': 34.7, 'H': 45.4}, 'thread': 3.0},
    'MGN15': {'height': 16.0, 'gap': 4.0, 'width': 32.0, 'hole_b': 25.0, 'c': {'C': 20.0, 'H': 25.0},
              'l': {'C': 42.1, 'H': 58.8}, 'thread': 3.0},
}
BLOCKS = ('H', 'C')


class LinearRail(BaseShape):
    op = 'linear_rail'
    name = 'Linear rail'
    order = 50
    schema = dict({'series': {'type': ['string', 'number']}, 'length': {'type': ['string', 'number']}},
                  **p.PLAIN_KEYS)
    prompt = '''{"op": "linear_rail", "id": name, "series": "MGN7"|"MGN9"|"MGN12"|"MGN15", "length": length, "note": text (optional)}
  A miniature linear guide rail cut to length (bought part), with counterbored holes centered along it. It runs along +x
  from x = 0, centered on y = 0, bottom on z = 0. Parameters: "<id>_rail_w", "<id>_rail_h", "<id>_pitch" (hole spacing),
  "<id>_count" (holes), "<id>_start" (x of the first hole). Pair it with rail_carriage steps of the same series.'''

    def validate(self, step, where):
        p.check(step, where, ('series', 'length'), {'series': list(RAILS)})
        length, pitch = p.num(step['length']), RAILS[step['series']]['pitch']
        if length is not None and length < 2 * pitch:
            raise ValueError(f'{where}: length must be at least {2 * pitch:g} mm (two hole pitches)')

    def expand(self, step):
        gid = step['id']
        n = lambda k: f'{gid}_{k}'
        params = p.sizes(gid, RAILS[step['series']], step, RAIL_KEYS)
        params[n('length')] = p.length(step['length'])
        params[n('count')] = f'floor({n("length")} / {n("pitch")})'
        params[n('start')] = f'({n("length")} - ({n("count")} - 1) * {n("pitch")}) / 2'

        def pattern(feature, pid):
            return {'op': 'linear_pattern', 'id': pid, 'feature': feature, 'direction': 'x',
                    'distance': n('pitch'), 'quantity': n('count')}
        steps = [
            p.sketch(n('sk'), [p.rect([0, f'{n("rail_h")} / 2'], n('rail_w'), n('rail_h'))], plane='yz'),
            p.extrude(n('bar'), n('sk'), n('length'), 'new_body'),
            p.sketch(n('hole_sk'), [p.circle([n('start'), 0], n('hole'))], offset=n('rail_h')),
            p.extrude(n('hole'), n('hole_sk'), f'-{n("rail_h")}', 'cut'),
            p.sketch(n('cbore_sk'), [p.circle([n('start'), 0], n('cbore'))], offset=n('rail_h')),
            p.extrude(n('cbore'), n('cbore_sk'), f'-{n("cbore_depth")}', 'cut'),
            pattern(n('hole'), n('holes')),
            pattern(n('cbore'), gid),
        ]
        return params, steps

    def bom(self, step):
        return [p.item('Motion', f'{step["series"]} linear rail, cut to {{length}}', step, length=step['length'])]


class RailCarriage(BaseShape):
    op = 'rail_carriage'
    name = 'Rail carriage'
    order = 51
    schema = dict({'series': {'type': ['string', 'number']}, 'block': {'enum': list(BLOCKS)}}, **p.PLAIN_KEYS)
    prompt = '''{"op": "rail_carriage", "id": name, "series": "MGN7"|"MGN9"|"MGN12"|"MGN15", "block": "H"|"C" (optional, default "H": long; "C": short), "note": text (optional)}
  The carriage (block) of a linear_rail (bought part), centered on x = y = 0 in the rail's axes (rail bottom on z = 0),
  with 4 tapped holes on top. Parameters: "<id>_height" (top above the rail's bottom), "<id>_width", "<id>_length",
  "<id>_hole_b" (hole spacing across), "<id>_hole_c" (along). Make it its own component and place each carriage with
  an instance at its spot along the rail.'''

    def validate(self, step, where):
        p.check(step, where, ('series',), {'series': list(CARRIAGES), 'block': BLOCKS})

    def expand(self, step):
        gid = step['id']
        n = lambda k: f'{gid}_{k}'
        series, block = step['series'], step.get('block', 'H')
        c = CARRIAGES[series]
        preset = {'height': c['height'], 'gap': c['gap'], 'width': c['width'], 'hole_b': c['hole_b'],
                  'hole_c': c['c'][block], 'length': c['l'][block], 'thread': c['thread'],
                  'rail_w': RAILS[series]['rail_w'], 'rail_h': RAILS[series]['rail_h'],
                  'hole_depth': round(min(c['thread'] + 1, c['height'] - RAILS[series]['rail_h'] - 0.4), 2)}
        params = p.sizes(gid, preset, step, tuple(preset))
        hb, hc = f'{n("hole_b")} / 2', f'{n("hole_c")} / 2'
        holes = [p.circle([f'{sx}{hc}', f'{sy}{hb}'], n('thread')) for sx in ('', '-') for sy in ('', '-')]
        steps = [
            p.sketch(n('sk'), [p.rect([0, 0], n('length'), n('width'))], offset=n('gap')),
            p.extrude(n('block'), n('sk'), f'{n("height")} - {n("gap")}', 'new_body'),
            p.sketch(n('channel_sk'), [p.rect([0, 0], f'{n("length")} + 2 mm', f'{n("rail_w")} + 0.4 mm')],
                     offset=n('gap')),
            p.extrude(n('channel'), n('channel_sk'), f'{n("rail_h")} + 0.2 mm - {n("gap")}', 'cut'),
            p.sketch(n('hole_sk'), holes, offset=n('height')),
            p.extrude(gid, n('hole_sk'), f'-{n("hole_depth")}', 'cut'),
        ]
        return params, steps

    def bom(self, step):
        return [p.item('Motion', f'{step["series"]}{step.get("block", "H")} carriage', step)]
