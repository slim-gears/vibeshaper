"""Helpers shared by the bought-part shapes (motors, rails, bearings...).

A bought part is modeled around its own origin, close enough to design the parts that hold it:
outline, mounting holes, shaft. Its bill-of-materials item is the part itself ("whole"), with the
step's optional "note" (a rating, a seller's model number). Sizes come from the usual catalog
tables; sellers differ, so every size is a parameter and can be overridden.
"""
import re

_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
PLAIN_KEYS = {'note': {'type': 'string'}}


def num(v):
    try:
        return float(re.sub(r'\s*mm$', '', str(v).strip()))
    except ValueError:
        return None


def length(v):
    """A bare number gets mm; anything else is used as written."""
    try:
        float(str(v).strip())
        return f'{v} mm'
    except ValueError:
        return f'({v})'


def check(step, where, required=(), choices=None):
    """The checks every part shares: required keys, a snake_case id, allowed values, a string note."""
    for key in ('id',) + tuple(required):
        if key not in step:
            raise ValueError(f'{where}: missing {key}')
    if not isinstance(step['id'], str) or not _NAME.match(step['id']):
        raise ValueError(f'{where}: id must be a snake_case name; it prefixes the part\'s parameters')
    for key, allowed in (choices or {}).items():
        if key in step and step[key] not in allowed:
            raise ValueError(f'{where}: {key} must be one of {tuple(allowed)}')
    if 'note' in step and not isinstance(step['note'], str):
        raise ValueError(f'{where}: note must be a string')
    for key in required:
        if num(step[key]) is not None and num(step[key]) <= 0:
            raise ValueError(f'{where}: {key} must be more than 0')


def sizes(gid, preset, step, keys):
    """Parameters for the preset sizes, each overridable by the step's own key."""
    return {f'{gid}_{k}': length(step.get(k, preset[k])) for k in keys}


def sketch(sid, entities, plane='xy', offset=None):
    s = {'op': 'sketch', 'id': sid, 'plane': plane, 'entities': entities}
    if offset is not None:
        s['offset'] = offset
    return s


def circle(center, diameter):
    return {'type': 'circle', 'center': center, 'diameter': diameter}


def rect(center, width, height):
    return {'type': 'center_rectangle', 'center': center, 'width': width, 'height': height}


def extrude(eid, sk, distance, mode):
    step = {'op': 'extrude', 'sketch': sk, 'distance': distance, 'mode': mode}
    if eid:
        step['id'] = eid
    return step


def item(category, text, step, **extra):
    it = dict({'category': category, 'item': text, 'whole': True}, **extra)
    if step.get('note'):
        it['note'] = step['note']
    return it


def chamfer(cid, distance, edges):
    step = {'op': 'chamfer', 'distance': distance, 'edges': edges}
    if cid:
        step['id'] = cid
    return step


def fillet(fid, radius, edges):
    step = {'op': 'fillet', 'radius': radius, 'edges': edges}
    if fid:
        step['id'] = fid
    return step
