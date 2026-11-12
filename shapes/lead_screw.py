"""Trapezoidal lead screw (T8 and similar) and its flanged nut, as sold for 3D printers and
small CNC machines.

The nut's sizes are those of the common T8 brass and POM anti-backlash nuts (22 mm flange,
four 3.5 mm holes on a 16 mm circle). Makers differ, so check them; every size is a parameter.
The screw runs along +z from z = 0. The nut's flange face (the face it is mounted by) is the xy
plane at z = 0, with the flange above it and the body below.
"""
from .base import BaseShape
from . import _parts as p

STOCK = [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 700, 800, 1000]
NUT = {'flange': 22.0, 'flange_t': 3.5, 'body': 10.2, 'pcd': 16.0, 'hole': 3.5, 'bore': 8.0}
NUT_LENGTH = {False: 15.0, True: 25.0}  # plain brass nut; nut with a spring-loaded second half
NUT_KEYS = ('flange', 'flange_t', 'body', 'pcd', 'hole', 'bore', 'length')


class LeadScrew(BaseShape):
    op = 'lead_screw'
    name = 'Lead screw'
    order = 52
    schema = dict({'diameter': {'type': ['string', 'number']}, 'lead': {'type': ['string', 'number']},
                   'length': {'type': ['string', 'number']}}, **p.PLAIN_KEYS)
    prompt = '''{"op": "lead_screw", "id": name, "length": length, "diameter": mm (optional, default 8), "lead": mm per turn (optional, default 2), "note": text (optional)}
  A trapezoidal lead screw (bought part), drawn as a plain rod along +z from z = 0. Order lengths are rounded up to the
  next stock length (100, 150, 200 ... mm), so pick one of those. Pair it with a lead_nut.'''

    def validate(self, step, where):
        p.check(step, where, ('length',))
        for key in ('diameter', 'lead'):
            if key in step and (p.num(step[key]) is None or p.num(step[key]) <= 0):
                raise ValueError(f'{where}: {key} must be a number of mm, more than 0')

    def expand(self, step):
        gid = step['id']
        n = lambda k: f'{gid}_{k}'
        params = {n('diameter'): p.length(step.get('diameter', 8)), n('lead'): p.length(step.get('lead', 2)),
                  n('length'): p.length(step['length'])}
        steps = [p.sketch(n('sk'), [p.circle([0, 0], n('diameter'))]),
                 p.extrude(gid, n('sk'), n('length'), 'new_body')]
        return params, steps

    def bom(self, step):
        d, lead = p.num(step.get('diameter', 8)), p.num(step.get('lead', 2))
        return [p.item('Motion', f'T{d:g} lead screw, lead {lead:g} mm, {{length}}', step,
                       length=step['length'], stock=STOCK)]


class LeadNut(BaseShape):
    op = 'lead_nut'
    name = 'Lead screw nut'
    order = 53
    schema = dict({'anti_backlash': {'type': 'boolean'}, 'lead': {'type': ['string', 'number']}}, **p.PLAIN_KEYS)
    prompt = '''{"op": "lead_nut", "id": name, "lead": mm (optional, default 2), "anti_backlash": true|false (optional, default true), "note": text (optional)}
  The flanged nut of a T8 lead_screw (bought part). Its flange face is the xy plane at z = 0: the flange is above it,
  the body below, the screw passes along z. Parameters: "<id>_flange" (diameter), "<id>_flange_t", "<id>_body"
  (diameter), "<id>_pcd" (circle of the 4 mounting holes, on the x and y axes), "<id>_hole", "<id>_length".'''

    def validate(self, step, where):
        p.check(step, where)
        if not isinstance(step.get('anti_backlash', True), bool):
            raise ValueError(f'{where}: anti_backlash must be true or false')
        if 'lead' in step and (p.num(step['lead']) is None or p.num(step['lead']) <= 0):
            raise ValueError(f'{where}: lead must be a number of mm, more than 0')

    def expand(self, step):
        gid = step['id']
        n = lambda k: f'{gid}_{k}'
        preset = dict(NUT, length=NUT_LENGTH[step.get('anti_backlash', True)])
        params = p.sizes(gid, preset, step, NUT_KEYS)
        r = f'{n("pcd")} / 2'
        holes = [p.circle(c, n('hole')) for c in ([r, 0], [f'-{r}', 0], [0, r], [0, f'-{r}'])]
        steps = [
            p.sketch(n('flange_sk'), [p.circle([0, 0], n('flange'))]),
            p.extrude(n('flange_body'), n('flange_sk'), n('flange_t'), 'new_body'),
            p.sketch(n('body_sk'), [p.circle([0, 0], n('body'))]),
            p.extrude(n('body_ext'), n('body_sk'), f'{n("flange_t")} - {n("length")}', 'join'),
            p.sketch(n('bore_sk'), [p.circle([0, 0], n('bore'))], offset=n('flange_t')),
            p.extrude(n('bore_cut'), n('bore_sk'), f'-{n("length")}', 'cut'),
            p.sketch(n('hole_sk'), holes),
            p.extrude(gid, n('hole_sk'), n('flange_t'), 'cut'),
        ]
        return params, steps

    def bom(self, step):
        kind = 'anti-backlash nut (POM)' if step.get('anti_backlash', True) else 'flanged nut (brass)'
        return [p.item('Motion', f'T8 lead screw {kind}, lead {p.num(step.get("lead", 2)):g} mm', step)]
