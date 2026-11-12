"""T-slot aluminum profile (2020, 2040, 3030, 4040 and similar).

The section is built the way these extrusions are: each outer corner is a block with a rounded
corner and a lip along both faces; each cell has a core (square or round) with a center bore;
four diagonal spars join the core to the corners. A slot is the space between two lips, two
spars and the core, so it is wide under the lips and narrows toward the core, which is where
T-nuts sit. Between the cells of a 2040 or longer, short stubs from the side walls meet the
spars and leave a hollow in the middle. Optional: a hole in each corner block, and a shallow
recess along each slot opening.

The preset sizes come from NopSCADlib's extrusion library (20 mm: its E2020t, 30 mm: E3030,
40 mm: E4040t). Makers differ, so check them against your supplier's drawing and override any
of them. Every size is a parameter.
"""
import math
import re

from .base import BaseShape

_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_PLANES = ('xy', 'xz', 'yz')
_SERIES = re.compile(r'^(\d{2})(\d{2,3})$')
_R2 = math.sqrt(0.5)
SHAPES = ('square', 'round')

# Sizes in mm. slot: opening; chamber: width under the lips; lip: lip thickness; spar: diagonal
# spar thickness; core: core width (or diameter when round); bore: center hole; corner_hole: hole
# in each corner block (0: none); fillet: outer corner radius; recess: shallow cut along the
# opening (width 0: none).
PRESETS = {
    20: {'slot': 6.2, 'chamber': 11.0, 'lip': 1.8, 'spar': 1.5, 'core': 7.8, 'core_shape': 'square',
         'bore': 5.0, 'corner_hole': 0, 'corner_hole_shape': 'round', 'fillet': 1.5,
         'recess_width': 7.2, 'recess_depth': 0.5},
    30: {'slot': 8.0, 'chamber': 16.5, 'lip': 2.0, 'spar': 2.0, 'core': 12.0, 'core_shape': 'square',
         'bore': 6.8, 'corner_hole': 4.2, 'corner_hole_shape': 'round', 'fillet': 1.0,
         'recess_width': 0, 'recess_depth': 0},
    40: {'slot': 10.0, 'chamber': 20.0, 'lip': 4.0, 'spar': 2.4, 'core': 16.0, 'core_shape': 'round',
         'bore': 10.0, 'corner_hole': 6.8, 'corner_hole_shape': 'square', 'fillet': 1.5,
         'recess_width': 12.0, 'recess_depth': 1.0},
}
SIZE_KEYS = ('slot', 'chamber', 'lip', 'spar', 'core', 'bore', 'corner_hole', 'fillet',
             'recess_width', 'recess_depth')


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


def _parse(series):
    """'2040' -> (20, 2): cell size and the number of cells along b."""
    m = _SERIES.match(str(series).strip())
    if not m:
        return None
    size, long = int(m.group(1)), int(m.group(2))
    if size not in PRESETS or long % size or not 1 <= long // size <= 8:
        return None
    return size, long // size


def _is_zero(v):
    return v in (None, False) or _num(v) == 0 or str(v).strip().lower() == 'none'


class _L(dict):
    """A length as sum(coefficient * parameter)."""

    def __add__(self, other):
        out = _L(self)
        for k, c in other.items():
            out[k] = out.get(k, 0) + c
        return out

    def __neg__(self):
        return _L({k: -c for k, c in self.items()})

    def __sub__(self, other):
        return self + -other

    def __mul__(self, f):
        return _L({k: c * f for k, c in self.items()})

    __rmul__ = __mul__


def _p(key, coef=1.0):
    return _L({key: coef})


_ZERO = _L()


class TSlotProfile(BaseShape):
    op = 'tslot_profile'
    name = 'T-slot profile'
    order = 40
    schema = {
        'series': {'type': 'string'},
        'length': {'type': ['string', 'number']},
        'slot': {'type': ['string', 'number']},
        'chamber': {'type': ['string', 'number']},
        'lip': {'type': ['string', 'number']},
        'spar': {'type': ['string', 'number']},
        'core': {'type': ['string', 'number']},
        'core_shape': {'enum': list(SHAPES)},
        'bore': {'type': ['string', 'number']},
        'corner_hole': {'type': ['string', 'number']},
        'corner_hole_shape': {'enum': list(SHAPES)},
        'fillet': {'type': ['string', 'number']},
        'recess_width': {'type': ['string', 'number']},
        'recess_depth': {'type': ['string', 'number']},
    }
    prompt = '''{"op": "tslot_profile", "id": name, "series": "2020"|"2040"|"2060"|"2080"|"3030"|"3060"|"4040"|"4080", "length": length,
 "plane": "xy"|"xz"|"yz" (optional, default "xy"; the profile runs along the plane's normal), "offset": length (optional),
 "center": [a, b] (optional, default [0, 0]), "mode": "new_body"|"join" (optional),
 overrides (optional lengths): "slot" (opening), "chamber" (width under the lips), "lip", "spar" (diagonal web), "core",
 "core_shape": "square"|"round", "bore" (center hole, 0: none), "corner_hole" (0: none), "corner_hole_shape": "square"|"round",
 "fillet" (outer corners), "recess_width", "recess_depth" (shallow cut along each opening, 0: none)}
  An aluminum T-slot extrusion with the real section: rounded corner blocks with lips, a core with a bore in each cell,
  diagonal spars, slots that widen under the lips, and hollows between cells. For mockups and for designing parts
  that fit it. "2040" is 20 mm along a and 40 mm along b. "length" is signed like an extrude distance. The preset
  sizes are typical; override them from the supplier's drawing. The step's "id" names the extrusion.
  Example: {"op": "tslot_profile", "id": "rail", "series": "2040", "length": "rail_len"}'''

    def validate(self, step, where):
        for key in ('id', 'series', 'length'):
            if key not in step:
                raise ValueError(f'{where}: missing {key}')
        if not isinstance(step['id'], str) or not _NAME.match(step['id']):
            raise ValueError(f'{where}: id must be a snake_case name; it prefixes the profile\'s parameters')
        if not _parse(step['series']):
            raise ValueError(f'{where}: series must be like "2020", "2040" or "3030" '
                             f'(cell sizes {tuple(PRESETS)}, up to 8 cells)')
        if step.get('plane', 'xy') not in _PLANES:
            raise ValueError(f'{where}: plane must be one of {_PLANES}')
        if step.get('mode', 'new_body') not in ('new_body', 'join'):
            raise ValueError(f'{where}: mode must be "new_body" or "join"')
        for key in ('core_shape', 'corner_hole_shape'):
            if step.get(key, 'square') not in SHAPES:
                raise ValueError(f'{where}: {key} must be one of {SHAPES}')
        c = step.get('center', [0, 0])
        if not (isinstance(c, list) and len(c) == 2):
            raise ValueError(f'{where}: center must be [a, b]')
        size = _parse(step['series'])[0]
        v = {k: _num(step.get(k, PRESETS[size][k])) for k in SIZE_KEYS}
        for k in ('bore', 'corner_hole', 'fillet', 'recess_width', 'recess_depth'):
            if _is_zero(step.get(k, PRESETS[size][k])):
                v[k] = 0.0
        if None in v.values():
            return  # formulas: Fusion checks them when it builds
        block = (size - v['chamber']) / 2  # how far each corner block reaches in from both faces
        rules = [
            (0 < v['slot'] < v['chamber'] < size, f'0 < slot < chamber < {size} mm'),
            (0 < v['spar'] < block, 'the spar thinner than a corner block: spar < (cell - chamber) / 2'),
            (0 < v['lip'] and v['lip'] + v['spar'] * _R2 < block,
             'room for the spars under the lips: lip + 0.71 * spar < (cell - chamber) / 2'),
            (v['spar'] / _R2 < v['core'] < v['chamber'], '1.41 * spar < core < chamber'),
            (0 <= v['bore'] < v['core'], 'bore < core'),
            (0 <= v['fillet'] < block, 'fillet < (cell - chamber) / 2'),
            (0 <= v['corner_hole'] < block, 'corner_hole < (cell - chamber) / 2'),
        ]
        if v['recess_width'] and v['recess_depth']:  # either one 0: no recess
            rules.append((0 < v['recess_depth'] < v['lip'] and v['slot'] < v['recess_width'] < size - 2 * v['fillet'],
                          'recess_depth < lip and slot < recess_width < cell - 2 * fillet'))
        for ok, rule in rules:
            if not ok:
                raise ValueError(f'{where}: the sizes must keep {rule}')

    def expand(self, step):
        gid = step['id']
        n = lambda key: f'{gid}_{key}'
        size, cells = _parse(step['series'])
        preset = PRESETS[size]
        get = lambda key: step.get(key, preset[key])
        round_core = get('core_shape') == 'round'
        has = {k: not _is_zero(get(k)) for k in ('bore', 'corner_hole', 'fillet', 'recess_width')}
        has['recess_width'] = has['recess_width'] and not _is_zero(get('recess_depth'))
        ca, cb = step.get('center', [0, 0])

        params = {n('cell'): f'{size} mm', n('length'): _length(step['length'])}
        for key in ('slot', 'chamber', 'lip', 'spar', 'core'):
            params[n(key)] = _length(get(key))
        for key in ('bore', 'corner_hole', 'fillet'):
            if has[key]:
                params[n(key)] = _length(get(key))
        if has['recess_width']:
            params[n('recess_width')] = _length(get('recess_width'))
            params[n('recess_depth')] = _length(get('recess_depth'))
        params[n('block')] = f'({n("cell")} - {n("chamber")}) / 2'
        if round_core:
            # Where a spar's side meets the round core (relative to the core's center), and the
            # point halfway along the core's arc from there to the slot's center line.
            params[n('core_s')] = f'sqrt(({n("core")} * {n("core")} - {n("spar")} * {n("spar")}) / 2)'
            params[n('core_hu')] = f'({n("spar")} / sqrt(2) - {n("core_s")}) / 2'
            params[n('core_hv')] = f'({n("spar")} / sqrt(2) + {n("core_s")}) / 2'
            reach = f'({n("core_hv")} + {n("core")} / 2)'
            scale = f'{n("core")} / 2 / sqrt({n("core_hu")} * {n("core_hu")} + {reach} * {reach})'
            params[n('core_mu')] = f'{n("core_hu")} * {scale}'
            params[n('core_mv')] = f'{reach} * {scale}'

        def expr(base, terms):
            """base + sum(coef * parameter): a coordinate as a formula."""
            out = '' if _num(base) == 0 else f'({base})'
            for key, coef in terms.items():
                if abs(coef) < 1e-12:
                    continue
                mag = '' if abs(abs(coef) - 1) < 1e-12 else f'{abs(coef):.10g} * '
                if not out:
                    out = f'{"-" if coef < 0 else ""}{mag}{n(key)}'
                else:
                    out += f' {"-" if coef < 0 else "+"} {mag}{n(key)}'
            return out or '0'

        def point(xy):
            return [expr(ca, xy[0]), expr(cb, xy[1])]

        def chain(eid, start, segs):
            return {'type': 'profile', 'id': eid, 'start': point(start), 'closed': False,
                    'segments': [{'to': point(q), **({'through': point(th)} if th else {})} for q, th in segs]}

        def mirror(eid, refs, a, b):
            return {'type': 'mirror', 'id': eid, 'entities': refs, 'line': [point(a), point(b)]}

        half_cell = _p('cell', 0.5)
        k = _p('spar', _R2)              # half a spar's width, measured along a face
        half_core = _p('core', 0.5)
        if round_core:  # (across, depth) from the core's center
            core_hit, core_mid = (_p('core_hu'), _p('core_hv')), (_p('core_mu'), _p('core_mv'))
        else:
            core_hit, core_mid = (k - half_core, half_core), None

        # One slot in (u along the face, v into the profile), cut in two at its center line, as
        # (point, arc point or None) steps. A round core's floor is two arcs.
        if has['recess_width']:
            rw, rd = _p('recess_width', 0.5), _p('recess_depth')
            mouth = [(-rw, _ZERO), (-rw, rd), (_p('slot', -0.5), rd)]
        else:
            mouth = [(_p('slot', -0.5), _ZERO)]
        left = mouth + [(_p('slot', -0.5), _p('lip')), (_p('chamber', -0.5), _p('lip')),
                        (_p('chamber', -0.5), _p('block') - k), (core_hit[0], half_cell - core_hit[1])]
        right = [(-u, v) for u, v in reversed(left)]
        floor = (_ZERO, half_cell - half_core)
        arc_l = (core_mid[0], half_cell - core_mid[1]) if round_core else None
        arc_r = (-core_mid[0], half_cell - core_mid[1]) if round_core else None
        first_half = [(q, None) for q in left] + [(floor, arc_l)]
        second_half = [(right[0], arc_r)] + [(q, None) for q in right[1:]]

        hw, hh = half_cell, _p('cell', cells / 2)
        f = _p('fillet') if has['fillet'] else _ZERO
        cell_y = [_p('cell', i - (cells - 1) / 2) for i in range(cells)]
        segs = []

        def at(c, t, uv):
            nv = (-t[1], t[0])
            return (c[0] + uv[0] * t[0] + uv[1] * nv[0], c[1] + uv[0] * t[1] + uv[1] * nv[1])

        def put(c, t, path):
            for uv, th in path:
                segs.append((at(c, t, uv), None if th is None else at(c, t, th)))

        def corner(to_diagonal):
            """The bottom-right corner, rounded; to_diagonal stops halfway, on its diagonal."""
            if not has['fillet']:
                segs.append(((hw, -hh), None))
                return
            cx, cy = hw - f, f - hh
            segs.append(((cx, -hh), None))
            if to_diagonal:
                segs.append(((cx + f * _R2, cy - f * _R2),
                             (cx + f * math.sin(math.pi / 8), cy - f * math.cos(math.pi / 8))))
            else:
                segs.append(((hw, cy), (cx + f * _R2, cy - f * _R2)))

        # The outline: draw a part from the bottom slot's center line around the bottom-right
        # corner, then mirror it. A square profile is symmetric about its diagonals too, so 1/8
        # is enough; a 2040 or longer needs 1/4, up to the horizontal center line.
        bottom = (_ZERO, -hh)
        start = at(bottom, (1, 0), floor)
        put(bottom, (1, 0), second_half)
        vertical, horizontal = ((_ZERO, -hh), (_ZERO, hh)), ((-hw, _ZERO), (hw, _ZERO))
        if cells == 1:
            corner(True)
            outline = [chain('part', start, segs),
                       mirror('quarter', ['part'], (_ZERO, _ZERO), (hw, -hh)),
                       mirror('half', ['quarter'], *vertical),
                       mirror('whole', ['half'], *horizontal)]
        else:
            corner(False)
            for i, y in enumerate(cell_y):
                if 2 * i + 1 < cells:
                    put((hw, y), (0, 1), first_half + second_half)
                elif 2 * i + 1 == cells:  # the middle cell's slot is cut by the center line
                    put((hw, y), (0, 1), first_half)
            if cells % 2 == 0:
                segs.append(((hw, _ZERO), None))
            outline = [chain('part', start, segs),
                       mirror('half', ['part'], *vertical),
                       mirror('whole', ['half'], *horizontal)]

        def sketch(key, entities):
            sk = {'op': 'sketch', 'id': n(key), 'plane': step.get('plane', 'xy'), 'entities': entities}
            if 'offset' in step:
                sk['offset'] = step['offset']
            return sk

        steps = [
            sketch('sk', outline),
            {'op': 'extrude', 'id': gid, 'sketch': n('sk'), 'distance': n('length'),
             'mode': step.get('mode', 'new_body')},
        ]

        # Holes: drawn below the horizontal center line (and right of the vertical one), then
        # mirrored. A bore on the center line is drawn whole.
        holes, lower, right_side = [], [], []
        if has['bore']:
            for i, y in enumerate(cell_y):
                if 2 * i + 1 <= cells:
                    holes.append({'type': 'circle', 'id': f'bore{i}', 'center': point((_ZERO, y)),
                                  'diameter': n('bore')})
                    if 2 * i + 1 < cells:
                        lower.append(f'bore{i}')
        if has['corner_hole']:
            off = _p('block', 0.5)
            c = point((hw - off, off - hh))
            if get('corner_hole_shape') == 'square':
                holes.append({'type': 'center_rectangle', 'id': 'corner', 'center': c,
                              'width': n('corner_hole'), 'height': n('corner_hole')})
            else:
                holes.append({'type': 'circle', 'id': 'corner', 'center': c, 'diameter': n('corner_hole')})
            right_side.append('corner')
        # The hollow between two cells is bounded by both cores, the four spars, the stubs from
        # the side walls and the walls. Its right half runs from the lower core to the upper one.
        stub_x = hw - _p('block') + _p('spar', 1 - _R2)
        stub_y = _p('spar') - _p('block')
        wall_x = hw - _p('lip')
        for j in range(1, cells):
            if 2 * j > cells:
                break
            ys = _p('cell', j - cells / 2)
            top = (_ZERO, half_core - hw)                            # top of the lower core
            p1 = (-core_hit[0], core_hit[1] - hw)
            arc1 = (-core_mid[0], core_mid[1] - hw) if round_core else None
            path = [(p1, arc1), ((stub_x, stub_y), None), ((wall_x, stub_y), None)]
            if 2 * j == cells:   # on the horizontal center line: a quarter is enough
                path.append(((wall_x, _ZERO), None))
            else:
                flip = lambda q: (q[0], -q[1])
                path += [((wall_x, -stub_y), None), ((stub_x, -stub_y), None), (flip(p1), None),
                         (flip(top), flip(arc1) if round_core else None)]
            sh = lambda q: (q[0], q[1] + ys)
            holes.append(chain(f'hollow{j}', sh(top), [(sh(q), sh(th) if th else None) for q, th in path]))
            right_side.append(f'hollow{j}')
        if right_side:
            holes.append(mirror('left', right_side, *vertical))
            lower = ['left'] + lower
        if lower:
            holes.append(mirror('upper', lower, *horizontal))
        if holes:
            steps += [
                sketch('hole_sk', holes),
                {'op': 'extrude', 'id': n('hole_cut'), 'sketch': n('hole_sk'), 'distance': n('length'), 'mode': 'cut'},
            ]
        return params, steps

    def bom(self, step):
        return [{'category': 'Frame', 'item': f'{step["series"]} aluminium T-slot extrusion, cut to {{length}}',
                 'length': step['length'], 'whole': True}]
