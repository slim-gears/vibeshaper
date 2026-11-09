"""Vent grid: round, hexagonal or slot holes filling a rectangle, cut into the existing body.

One hole is cut and patterned in two directions. The number of holes comes from parameter
formulas (how many fit in the area), so the grid refills itself when the area, hole size or
wall width is changed in Fusion. "staggered" offsets every other column by half a row, which
gives a honeycomb with hexagons and the densest packing with round holes.
"""
import math
import re

from .base import BaseShape

_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_AXES = {'xy': ('x', 'y'), 'xz': ('x', 'z'), 'yz': ('y', 'z')}
HOLES = ('circle', 'hexagon', 'slot')
LAYOUTS = ('grid', 'staggered')


def _num(v):
    try:
        return float(re.sub(r'\s*mm$', '', str(v).strip()))
    except ValueError:
        return None


def _length(v):
    """A bare number gets mm; anything else is used as written."""
    try:
        float(str(v).strip())
        return f'{v} mm'
    except ValueError:
        return f'({v})'


class VentGrid(BaseShape):
    op = 'vent_grid'
    name = 'Vent grid'
    order = 30
    schema = {
        'width': {'type': ['string', 'number']},
        'height': {'type': ['string', 'number']},
        'hole': {'enum': list(HOLES)},
        'size': {'type': ['string', 'number']},
        'length': {'type': ['string', 'number']},
        'wall': {'type': ['string', 'number']},
        'layout': {'enum': list(LAYOUTS)},
        'depth': {'type': ['string', 'number']},
        'columns': {'type': ['string', 'number']},
        'rows': {'type': ['string', 'number']},
    }
    prompt = '''{"op": "vent_grid", "id": name, "plane": "xy"|"xz"|"yz", "offset": length, "center": [a, b] (optional, default [0, 0]),
 "width": length, "height": length, "size": length, "depth": length,
 "hole": "circle"|"hexagon"|"slot" (optional, default "circle"), "length": length (slots only: overall slot length, along b),
 "wall": length (optional, default "2 mm", material between holes), "layout": "grid"|"staggered" (optional; default "staggered", "grid" for slots),
 "columns": count, "rows": count (optional; by default as many as fit)}
  Cuts a pattern of vent holes, filling a width x height area (along a and b) centered on "center", into the existing body.
  "size" is the hole diameter, the hexagon's width across flats, or the slot width. Put the sketch plane on the face to cut
  through; "depth" is signed like an extrude distance. Hexagons with "staggered" make a honeycomb. The step's "id" names
  the last pattern.
  Example: {"op": "vent_grid", "id": "lid_vent", "plane": "xy", "offset": "lid_thick", "width": "60 mm", "height": "40 mm",
   "hole": "hexagon", "size": "5 mm", "wall": "1.6 mm", "depth": "-lid_thick"}'''

    def validate(self, step, where):
        for key in ('id', 'width', 'height', 'size', 'depth'):
            if key not in step:
                raise ValueError(f'{where}: missing {key}')
        if not isinstance(step['id'], str) or not _NAME.match(step['id']):
            raise ValueError(f'{where}: id must be a snake_case name; it prefixes the grid\'s parameters')
        hole = step.get('hole', 'circle')
        if hole not in HOLES:
            raise ValueError(f'{where}: hole must be one of {HOLES}')
        if step.get('layout', 'grid' if hole == 'slot' else 'staggered') not in LAYOUTS:
            raise ValueError(f'{where}: layout must be one of {LAYOUTS}')
        if step.get('plane', 'xy') not in _AXES:
            raise ValueError(f'{where}: plane must be one of {tuple(_AXES)}')
        c = step.get('center', [0, 0])
        if not (isinstance(c, list) and len(c) == 2):
            raise ValueError(f'{where}: center must be [a, b]')
        if hole == 'slot' and 'length' not in step:
            raise ValueError(f'{where}: slots need a length')
        for key in ('columns', 'rows'):
            v = _num(step.get(key, 1))
            if v is not None and (v != int(v) or v < 1):
                raise ValueError(f'{where}: {key} must be a whole number of at least 1')
        # When the sizes are plain numbers, check that the holes fit.
        a_cnt, b_cnt = self._counts(step)
        need = 2 if self._layout(step) == 'staggered' else 1
        if a_cnt is not None and min(a_cnt, b_cnt) < need:
            raise ValueError(f'{where}: the area fits {a_cnt} x {b_cnt} holes; '
                             f'it needs at least {need} x {need}: make it larger or the holes smaller')
        if hole == 'slot' and _num(step['length']) is not None and _num(step['size']) is not None \
                and _num(step['length']) <= _num(step['size']):
            raise ValueError(f'{where}: a slot\'s length must be more than its width (size)')

    @staticmethod
    def _layout(step):
        hole = step.get('hole', 'circle')
        return step.get('layout', 'grid' if hole == 'slot' else 'staggered')

    def _counts(self, step):
        """Hole counts of the main grid, when every size is a plain number (else None, None)."""
        hole = step.get('hole', 'circle')
        vals = [_num(step[k]) for k in ('width', 'height', 'size')] + [_num(step.get('wall', 2))]
        if hole == 'slot':
            vals.append(_num(step['length']))
        if any(v is None for v in vals):
            return None, None
        w, h, size, wall = vals[:4]
        ext_a = size * 2 / math.sqrt(3) if hole == 'hexagon' else size
        ext_b = vals[4] if hole == 'slot' else size
        pitch_b = ext_b + wall
        if self._layout(step) == 'staggered':
            col = size + wall if hole == 'slot' else pitch_b * math.sqrt(3) / 2
            step_a = 2 * col
        else:
            step_a = ext_a + wall
        a_cnt = math.floor((w - ext_a) / step_a + 1e-9) + 1
        b_cnt = math.floor((h - ext_b) / pitch_b + 1e-9) + 1
        if 'columns' in step and _num(step['columns']) is not None:
            a_cnt = int(_num(step['columns']))
        if 'rows' in step and _num(step['rows']) is not None:
            b_cnt = int(_num(step['rows']))
        return a_cnt, b_cnt

    def expand(self, step):
        gid = step['id']
        n = lambda key: f'{gid}_{key}'
        hole = step.get('hole', 'circle')
        staggered = self._layout(step) == 'staggered'
        plane = step.get('plane', 'xy')
        ax_a, ax_b = _AXES[plane]
        ca, cb = (f'({c})' for c in step.get('center', [0, 0]))

        params = {
            n('width'): _length(step['width']),
            n('height'): _length(step['height']),
            n('size'): _length(step['size']),
            n('wall'): _length(step.get('wall', 2)),
        }
        if hole == 'slot':
            params[n('length')] = _length(step['length'])
        params[n('ext_a')] = f'{n("size")} * 2 / sqrt(3)' if hole == 'hexagon' else n('size')
        params[n('ext_b')] = n('length') if hole == 'slot' else n('size')
        params[n('pitch_b')] = f'{n("ext_b")} + {n("wall")}'
        if staggered:
            params[n('col_step')] = (f'{n("size")} + {n("wall")}' if hole == 'slot'
                                     else f'{n("pitch_b")} * sqrt(3) / 2')
            params[n('pitch_a')] = f'2 * {n("col_step")}'
        else:
            params[n('pitch_a')] = f'{n("ext_a")} + {n("wall")}'
        params[n('count_a')] = (str(step['columns']) if 'columns' in step
                                else f'floor(({n("width")} - {n("ext_a")}) / {n("pitch_a")}) + 1')
        params[n('count_b')] = (str(step['rows']) if 'rows' in step
                                else f'floor(({n("height")} - {n("ext_b")}) / {n("pitch_b")}) + 1')

        def hole_at(a, b):
            if hole == 'circle':
                return {'type': 'circle', 'center': [a, b], 'diameter': n('size')}
            if hole == 'hexagon':
                return {'type': 'regular_polygon', 'center': [a, b], 'sides': 6, 'across_flats': n('size')}
            r, h = f'{n("size")} / 2', f'({n("length")} - {n("size")}) / 2'
            return {'type': 'profile', 'start': [f'{a} + {r}', f'{b} - {h}'], 'segments': [
                {'to': [f'{a} + {r}', f'{b} + {h}']},
                {'to': [f'{a} - {r}', f'{b} + {h}'], 'through': [a, f'{b} + {n("length")} / 2']},
                {'to': [f'{a} - {r}', f'{b} - {h}']},
                {'to': [f'{a} + {r}', f'{b} - {h}'], 'through': [a, f'{b} - {n("length")} / 2']},
            ]}

        def sketch(key, entity):
            s = {'op': 'sketch', 'id': n(key), 'plane': plane, 'entities': [entity]}
            if 'offset' in step:
                s['offset'] = step['offset']
            return s

        def grid(key, a, b, count_a, count_b, pattern_id):
            return [
                sketch(f'{key}_sk', hole_at(a, b)),
                {'op': 'extrude', 'id': n(key), 'sketch': n(f'{key}_sk'), 'distance': step['depth'], 'mode': 'cut'},
                {'op': 'linear_pattern', 'id': pattern_id, 'feature': n(key),
                 'direction': ax_a, 'quantity': count_a, 'distance': n('pitch_a'),
                 'direction2': ax_b, 'quantity2': count_b, 'distance2': n('pitch_b')},
            ]

        # The first hole sits in the corner of the grid, so the patterns run along +a and +b.
        a0 = f'{ca} - ({n("count_a")} - 1) * {n("pitch_a")} / 2'
        b0 = f'{cb} - ({n("count_b")} - 1) * {n("pitch_b")} / 2'
        if not staggered:
            return params, grid('hole', a0, b0, n('count_a'), n('count_b'), gid)
        steps = grid('hole', a0, b0, n('count_a'), n('count_b'), n('main'))
        # The offset columns sit between the main ones, half a row up.
        steps += grid('hole2', f'{a0} + {n("col_step")}', f'{b0} + {n("pitch_b")} / 2',
                      f'{n("count_a")} - 1', f'{n("count_b")} - 1', gid)
        return params, steps
