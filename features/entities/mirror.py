"""Mirror sketch entity."""
import math

from ..base import JS_POINT
from .. import _helpers as h
from .base import BaseEntity


def _arc_mid(arc):
    """The point halfway along a sketch arc, in sketch space."""
    ev = arc.geometry.evaluator
    _, t0, t1 = ev.getParameterExtents()
    _, p = ev.getPointAtParameter((t0 + t1) / 2)
    return p


def _mirror_curves(sk, src, axis):
    """Copy lines, arcs and circles across the construction line `axis`; returns the copies.

    Points on the axis are shared with the copy, so a chain that ends on the axis joins its
    mirror image. A point shared by two curves gets one mirrored point. Each new point is tied
    to its original by a symmetry constraint (a circle's or arc's size by an equal constraint).
    Curves that are their own mirror image are left alone.
    """
    import adsk.core
    P = adsk.core.Point3D.create
    curves, gc = sk.sketchCurves, sk.geometricConstraints
    a, b = axis.startSketchPoint.geometry, axis.endSketchPoint.geometry
    dx, dy = b.x - a.x, b.y - a.y
    n2 = dx * dx + dy * dy

    def refl(p):
        t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / n2
        return P(2 * (a.x + t * dx) - p.x, 2 * (a.y + t * dy) - p.y, 0)

    def on_axis(p):
        return abs((p.x - a.x) * dy - (p.y - a.y) * dx) / math.sqrt(n2) < h.EPS

    def key(p):
        return round(p.x / h.EPS), round(p.y / h.EPS)

    def near(p, q):
        return abs(p.x - q.x) < h.EPS and abs(p.y - q.y) < h.EPS

    copies = {}  # an original point's position -> its mirrored sketch point

    def image(sp):
        """The sketch point that mirrors sp, if there is one already."""
        return sp if on_axis(sp.geometry) else copies.get(key(sp.geometry))

    def tie(orig, new):
        copies[key(orig.geometry)] = new
        h.try_call(gc.addSymmetry, orig, new, axis)

    def settle(c, new):
        """If the copy came out looser than its original, tie the curves themselves too (and an
        arc's center), as Fusion's own Mirror does. Fusion refuses a constraint that adds nothing."""
        if not getattr(c, 'isFullyConstrained', False) or getattr(new, 'isFullyConstrained', True):
            return
        h.try_call(gc.addSymmetry, c, new, axis)
        if not new.isFullyConstrained and hasattr(c, 'centerSketchPoint'):
            h.try_call(gc.addSymmetry, c.centerSketchPoint, new.centerSketchPoint, axis)

    made = []
    for c in src:
        if c is axis or getattr(c, 'isConstruction', False):
            continue
        kind = getattr(c, 'objectType', type(c).__name__)
        if 'Circle' in kind:
            cp = c.centerSketchPoint
            if on_axis(cp.geometry):
                continue
            new = curves.sketchCircles.addByCenterRadius(refl(cp.geometry), c.radius)
            tie(cp, new.centerSketchPoint)
            h.try_call(gc.addEqual, c, new)
        elif 'Arc' in kind:
            s0, s1 = c.startSketchPoint, c.endSketchPoint
            mid = _arc_mid(c)
            if on_axis(mid) and near(refl(s0.geometry), s1.geometry):
                continue
            ims = [image(s0), image(s1)]
            new = curves.sketchArcs.addByThreePoints(refl(s0.geometry), refl(mid), refl(s1.geometry))
            n0, n1 = new.startSketchPoint, new.endSketchPoint
            if not near(n0.geometry, refl(s0.geometry)):  # Fusion may start the arc at either end
                n0, n1 = n1, n0
            for orig, im, np_ in ((s0, ims[0], n0), (s1, ims[1], n1)):
                if im is None:
                    tie(orig, np_)
                else:
                    h.try_call(gc.addCoincident, np_, im)
            h.try_call(gc.addEqual, c, new)
        elif 'Line' in kind:
            s0, s1 = c.startSketchPoint, c.endSketchPoint
            if on_axis(s0.geometry) and on_axis(s1.geometry):
                continue
            ims = [image(s0), image(s1)]
            new = curves.sketchLines.addByTwoPoints(*[im if im is not None else refl(sp.geometry)
                                                      for sp, im in zip((s0, s1), ims)])
            for orig, im, np_ in ((s0, ims[0], new.startSketchPoint), (s1, ims[1], new.endSketchPoint)):
                if im is None:
                    tie(orig, np_)
        else:
            continue
        settle(c, new)
        made.append(new)
    return made


class MirrorEntity(BaseEntity):
    type = 'mirror'
    name = 'Mirror'
    order = 80
    required = ('entities', 'line')
    schema = {
        'entities': {'type': 'array', 'items': {'type': 'string'}},
        'line': {'type': 'array', 'items': JS_POINT, 'minItems': 2, 'maxItems': 2},
    }
    prompt = ('{"type": "mirror", "id": name, "entities": [ids of earlier entities in this sketch], '
              '"line": [[a, b], [c, d]]}   copies them across the line through the two points, tied by symmetry. '
              'For symmetric outlines, draw one side as an open chain ("closed": false) that starts and ends on the line, '
              'then mirror it; mirror the mirror\'s id to mirror again')

    def validate(self, entity, where, ent_ids):
        refs = entity['entities']
        if not isinstance(refs, list) or not refs:
            raise ValueError(f'{where}: entities must be a non-empty list of entity ids')
        for ref in refs:
            if ref not in ent_ids:
                raise ValueError(f'{where}: entities refers to {ref!r}, which is not an entity id '
                                 f'defined earlier in this sketch')
        line = entity['line']
        if not isinstance(line, list) or len(line) != 2:
            raise ValueError(f'{where}: line must be two points [[a, b], [a, b]]')
        for p in line:
            h.xy(p, f'{where}.line')

    def draw(self, sk, e, ctx):
        # The mirror line is a construction line placed like any other; the copies are tied to
        # their originals by symmetry constraints, so they follow every parameter change.
        a_xy, b_xy = e['line']
        axis = sk.sketchCurves.sketchLines.addByTwoPoints(
            ctx.pt(ctx.cm(a_xy[0]), ctx.cm(a_xy[1])),
            ctx.pt(ctx.cm(b_xy[0]), ctx.cm(b_xy[1])),
        )
        axis.isConstruction = True
        ctx.place([axis.startSketchPoint, axis.endSketchPoint], [a_xy, b_xy], [(0, 1, axis)])
        src = [c for ref in e['entities'] for c in h.as_list(ctx.ent_map[ref])]
        made = _mirror_curves(sk, src, axis)
        ctx.register(e, src + made)
