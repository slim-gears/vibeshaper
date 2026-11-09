"""Bolt hole: a clearance hole for a metric bolt, with an optional counterbore, countersink
or hex nut trap, sized from standard tables.

The sizes come from ISO 273 (clearance holes), ISO 4762 (socket head cap screws), ISO 10642
and ISO 7046 (countersunk heads) and ISO 4032 (hex nuts). Pockets get a printing tolerance on
top of the part they hold. Every size becomes a named parameter, so it can be adjusted in
Fusion afterwards; changing the bolt size itself (M5 to M6) needs a new step.
"""
import re

from .base import BaseShape

_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# size: (close, normal, loose clearance hole), socket head (diameter, height),
#       countersunk head diameter, hex nut (across flats, thickness). All in mm.
SIZES = {
    'M2': ((2.2, 2.4, 2.6), (3.8, 2.0), 3.8, (4.0, 1.6)),
    'M2.5': ((2.7, 2.9, 3.1), (4.5, 2.5), 4.7, (5.0, 2.0)),
    'M3': ((3.2, 3.4, 3.6), (5.5, 3.0), 6.72, (5.5, 2.4)),
    'M4': ((4.3, 4.5, 4.8), (7.0, 4.0), 8.96, (7.0, 3.2)),
    'M5': ((5.3, 5.5, 5.8), (8.5, 5.0), 11.2, (8.0, 4.7)),
    'M6': ((6.4, 6.6, 7.0), (10.0, 6.0), 13.44, (10.0, 5.2)),
    'M8': ((8.4, 9.0, 10.0), (13.0, 8.0), 17.92, (13.0, 6.8)),
    'M10': ((10.5, 11.0, 12.0), (16.0, 10.0), 22.4, (16.0, 8.4)),
    'M12': ((13.0, 13.5, 14.5), (18.0, 12.0), 26.88, (18.0, 10.8)),
}
FITS = ('close', 'normal', 'loose')
HEADS = ('none', 'counterbore', 'countersink', 'nut_trap')


def _num(v):
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def _with_unit(v, unit='mm'):
    """A bare number gets a unit; anything else is used as written."""
    return f'{v} {unit}' if _num(v) is not None else f'({v})'


def _points(step):
    return step['points'] if 'points' in step else [step.get('center', [0, 0])]


class BoltHole(BaseShape):
    op = 'bolt_hole'
    name = 'Bolt hole'
    order = 20
    schema = {
        'size': {'type': ['string', 'number']},  # keys are shared by every step type; validate() checks the size
        'points': {'type': 'array', 'items': {'type': 'array', 'items': {'type': ['string', 'number']},
                                               'minItems': 2, 'maxItems': 2}},
        'depth': {'type': ['string', 'number']},
        'head': {'enum': list(HEADS)},
        'fit': {'enum': list(FITS)},
        'tolerance': {'type': ['string', 'number']},
    }
    prompt = '''{"op": "bolt_hole", "id": name, "size": "M2"|"M2.5"|"M3"|"M4"|"M5"|"M6"|"M8"|"M10"|"M12", "plane": "xy"|"xz"|"yz", "offset": length,
 "points": [[a, b], ...] (or "center": [a, b]), "depth": length,
 "head": "none"|"counterbore"|"countersink"|"nut_trap" (optional, default "none"), "fit": "close"|"normal"|"loose" (optional, default "normal"),
 "tolerance": length (optional, default "0.3 mm", added to head and nut pockets)}
  Cuts standard clearance holes for metric bolts into the existing body, with the head or nut pocket sized from ISO tables;
  use it instead of drawing bolt holes, counterbores or nut traps by hand. Put the sketch plane (plane + offset) on the face
  the bolt enters; "depth" is signed like an extrude distance (negative cuts against the plane's normal, e.g. down from a top face).
  The pocket is cut at that face. The step's "id" names the hole cut.
  Example: {"op": "bolt_hole", "id": "mount_bolts", "size": "M5", "plane": "xy", "offset": "base_thick", "depth": "-base_thick",
   "head": "nut_trap", "points": [["-hole_off", "-hole_off"], ["hole_off", "-hole_off"], ["hole_off", "hole_off"], ["-hole_off", "hole_off"]]}'''

    def validate(self, step, where):
        for key in ('id', 'size', 'depth'):
            if key not in step:
                raise ValueError(f'{where}: missing {key}')
        if not isinstance(step['id'], str) or not _NAME.match(step['id']):
            raise ValueError(f'{where}: id must be a snake_case name; it prefixes the hole\'s parameters')
        if step['size'] not in SIZES:
            raise ValueError(f'{where}: size must be one of {tuple(SIZES)}')
        if step.get('head', 'none') not in HEADS:
            raise ValueError(f'{where}: head must be one of {HEADS}')
        if step.get('fit', 'normal') not in FITS:
            raise ValueError(f'{where}: fit must be one of {FITS}')
        if step.get('plane', 'xy') not in ('xy', 'xz', 'yz'):
            raise ValueError(f'{where}: plane must be one of ("xy", "xz", "yz")')
        pts = _points(step)
        if not isinstance(pts, list) or not pts or not all(isinstance(p, list) and len(p) == 2 for p in pts):
            raise ValueError(f'{where}: points must be a non-empty list of [a, b]')
        if _num(step['depth']) == 0:
            raise ValueError(f'{where}: depth must not be 0')

    def expand(self, step):
        gid = step['id']
        n = lambda key: f'{gid}_{key}'
        clear, (cap_d, cap_h), csk_d, (nut_af, nut_m) = SIZES[step['size']]
        head = step.get('head', 'none')
        pts = _points(step)

        params = {
            n('hole_d'): f'{clear[FITS.index(step.get("fit", "normal"))]} mm',
            n('depth'): _with_unit(step['depth']),
        }
        if head != 'none':
            params[n('tolerance')] = _with_unit(step.get('tolerance', 0.3))
        if head == 'counterbore':
            params[n('head_d')] = f'{cap_d} mm + 2 * {n("tolerance")}'
            params[n('head_depth')] = f'{cap_h} mm + {n("tolerance")}'
        elif head == 'countersink':
            params[n('head_d')] = f'{csk_d} mm + 2 * {n("tolerance")}'
        elif head == 'nut_trap':
            params[n('nut_af')] = f'{nut_af} mm + 2 * {n("tolerance")}'
            params[n('nut_depth')] = f'{nut_m} mm + {n("tolerance")}'

        def sketch(key, entities):
            s = {'op': 'sketch', 'id': n(key), 'plane': step.get('plane', 'xy'), 'entities': entities}
            if 'offset' in step:
                s['offset'] = step['offset']
            return s

        def pocket(depth_key):  # cut from the entry face, the same way as the hole
            return f'{n(depth_key)} * {n("depth")} / abs({n("depth")})'

        steps = [
            sketch('sk', [{'type': 'circle', 'center': p, 'diameter': n('hole_d')} for p in pts]),
            {'op': 'extrude', 'id': gid, 'sketch': n('sk'), 'distance': n('depth'), 'mode': 'cut'},
        ]
        if head == 'counterbore':
            steps += [
                sketch('head_sk', [{'type': 'circle', 'center': p, 'diameter': n('head_d')} for p in pts]),
                {'op': 'extrude', 'id': n('head'), 'sketch': n('head_sk'), 'distance': pocket('head_depth'),
                 'mode': 'cut'},
            ]
        elif head == 'countersink':  # a 90 degree cone: an equal chamfer on the rim at the entry face
            steps.append({'op': 'chamfer', 'id': n('head'), 'distance': f'({n("head_d")} - {n("hole_d")}) / 2',
                          'edges': {'feature': gid, 'type': 'circle', 'on': n('sk')}})
        elif head == 'nut_trap':
            steps += [
                sketch('nut_sk', [{'type': 'regular_polygon', 'center': p, 'sides': 6, 'across_flats': n('nut_af')}
                                  for p in pts]),
                {'op': 'extrude', 'id': n('nut'), 'sketch': n('nut_sk'), 'distance': pocket('nut_depth'),
                 'mode': 'cut'},
            ]
        return params, steps
