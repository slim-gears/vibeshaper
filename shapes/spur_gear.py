"""Spur gear: a root disc plus one tooth, patterned around the gear's own center.

Each tooth flank is one circular arc through three points of the true involute: where the
flank starts, on the pitch circle, and on the tip circle. That is within a few hundredths of
a millimetre of the involute for ordinary gears, well below 3D-printing tolerance. Every point
comes from parameter formulas, so the gear follows module, tooth count and pressure angle when
they are changed in Fusion. No undercut and no root fillet are modelled.
"""
import re

from .base import BaseShape

_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_AXIS = {'xy': 'z', 'xz': 'y', 'yz': 'x'}
_MIN_TEETH = 8  # fewer gives pointed teeth with a 20 degree pressure angle


def _num(v):
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def _with_unit(v, unit):
    """A bare number gets a unit; anything else is used as written."""
    return f'{v} {unit}' if _num(v) is not None else f'({v})'


def _is_zero(v):
    return _num(re.sub(r'\s*(mm|deg)$', '', str(v).strip())) == 0


class SpurGear(BaseShape):
    op = 'spur_gear'
    name = 'Spur gear'
    order = 10
    schema = {
        'module': {'type': ['string', 'number']},
        'teeth': {'type': ['string', 'number']},
        'thickness': {'type': ['string', 'number']},
        'pressure_angle': {'type': ['string', 'number']},
        'rotate': {'type': ['string', 'number']},
        'bore': {'type': ['string', 'number']},
    }
    prompt = '''{"op": "spur_gear", "id": name, "module": length, "teeth": count, "thickness": length,
 "center": [a, b] (optional, default [0, 0]), "plane": "xy"|"xz"|"yz" (optional, default "xy"), "offset": length (optional),
 "pressure_angle": angle (optional, default "20 deg"), "rotate": angle (optional), "bore": diameter (optional),
 "mode": "new_body"|"join" (optional)}
  An involute spur gear in one step; its pitch diameter is module * teeth. The step's "id" names the finished gear.
  Gears that mesh share module and pressure angle; their centers are module * (teeth1 + teeth2) / 2 apart.
  A gear at the origin has a tooth pointing along +a. For a second gear placed along +a, set "rotate": "180 deg / teeth2"
  when teeth2 is even (so a gap faces the first gear's tooth); leave rotate out when teeth2 is odd.
  Example: {"op": "spur_gear", "id": "gear2", "module": "gear_module", "teeth": "gear2_teeth", "thickness": "gear_thick",
   "center": ["gear_module * (gear1_teeth + gear2_teeth) / 2", 0], "bore": "8 mm"}'''

    def validate(self, step, where):
        for key in ('id', 'module', 'teeth', 'thickness'):
            if key not in step:
                raise ValueError(f'{where}: missing {key}')
        if not isinstance(step['id'], str) or not _NAME.match(step['id']):
            raise ValueError(f'{where}: id must be a snake_case name; it prefixes the gear\'s parameters')
        if step.get('plane', 'xy') not in _AXIS:
            raise ValueError(f'{where}: plane must be one of {tuple(_AXIS)}')
        if step.get('mode', 'new_body') not in ('new_body', 'join'):
            raise ValueError(f'{where}: mode must be "new_body" or "join"')
        c = step.get('center', [0, 0])
        if not (isinstance(c, list) and len(c) == 2):
            raise ValueError(f'{where}: center must be [a, b]')
        teeth = _num(step['teeth'])
        if teeth is not None and (teeth != int(teeth) or teeth < _MIN_TEETH):
            raise ValueError(f'{where}: teeth must be a whole number of at least {_MIN_TEETH}')

    def expand(self, step):
        gid = step['id']
        n = lambda key: f'{gid}_{key}'
        m = _with_unit(step['module'], 'mm')
        z = f'({step["teeth"]})'
        pa = _with_unit(step.get('pressure_angle', 20), 'deg')
        plane = step.get('plane', 'xy')
        center = step.get('center', [0, 0])
        cx, cy = center

        def inv_angle(r):  # polar angle of the flank at radius r, from the tooth's center line
            a = f'acos({n("base_r")} / {r})'
            return f'90 deg / {z} + (tan({pa}) - {pa} / 1 rad - tan({a}) + {a} / 1 rad) * 1 rad'

        params = {
            n('pitch_r'): f'{m} * {z} / 2',
            n('base_r'): f'{n("pitch_r")} * cos({pa})',
            n('tip_r'): f'{n("pitch_r")} + {m}',
            n('root_r'): f'{n("pitch_r")} - 1.25 * {m}',
            # The flank starts on the base circle, or on the root circle when that is larger;
            # the 0.001 mm keeps acos() inside its domain after rounding.
            n('flank_r'): f'({n("base_r")} + {n("root_r")} + abs({n("base_r")} - {n("root_r")})) / 2 + 0.001 mm',
            n('rotate_angle'): _with_unit(step.get('rotate', 0), 'deg'),
            n('pitch_angle'): f'90 deg / {z}',
            n('flank_angle'): inv_angle(n('flank_r')),
            n('tip_angle'): inv_angle(n('tip_r')),
        }

        def at(r, angle, sign):
            turn = n('rotate_angle') + (f' {sign} {angle}' if angle else '')
            x = f'{r} * cos({turn})'
            y = f'{r} * sin({turn})'
            return [x if _is_zero(cx) else f'{cx} + {x}', y if _is_zero(cy) else f'{cy} + {y}']

        flank, tip, pitch = n('flank_angle'), n('tip_angle'), n('pitch_angle')
        tooth = {
            'type': 'profile',
            'start': center,
            'segments': [
                {'to': at(n('flank_r'), flank, '-')},
                {'to': at(n('tip_r'), tip, '-'), 'through': at(n('pitch_r'), pitch, '-')},
                {'to': at(n('tip_r'), tip, '+'), 'through': at(n('tip_r'), None, '+')},
                {'to': at(n('flank_r'), flank, '+'), 'through': at(n('pitch_r'), pitch, '+')},
                {'to': center},
            ],
        }

        def sketch(key, entity):
            s = {'op': 'sketch', 'id': n(key), 'plane': plane, 'entities': [entity]}
            if 'offset' in step:
                s['offset'] = step['offset']
            return s

        thick = step['thickness']
        steps = [
            sketch('root_sk', {'type': 'circle', 'center': center, 'diameter': f'2 * {n("root_r")}'}),
            {'op': 'extrude', 'id': n('root'), 'sketch': n('root_sk'), 'distance': thick,
             'mode': step.get('mode', 'new_body')},
            sketch('tooth_sk', tooth),
            {'op': 'extrude', 'id': n('tooth'), 'sketch': n('tooth_sk'), 'distance': thick, 'mode': 'join'},
            {'op': 'circular_pattern', 'id': gid, 'feature': n('tooth'), 'axis': _AXIS[plane],
             'center': center, 'quantity': step['teeth']},
        ]
        if 'bore' in step:
            steps += [
                sketch('bore_sk', {'type': 'circle', 'center': center, 'diameter': step['bore']}),
                {'op': 'extrude', 'id': n('bore'), 'sketch': n('bore_sk'), 'distance': thick, 'mode': 'cut'},
            ]
        return params, steps
