"""Coil (spring / helix) timeline feature."""
import math

from .base import AXES, BaseFeature, JS_AXIS, JS_CENTER, JS_LEN, JS_MODE, MODES
from . import _helpers as h


class CoilFeature(BaseFeature):
    op = 'coil'
    name = 'Coil'
    order = 130
    schema = {
        'diameter': JS_LEN,
        'pitch': JS_LEN,
        'revolutions': JS_LEN,
        'section_size': JS_LEN,
        'section': {'enum': ['circle', 'square', 'rectangle']},
        'axis': JS_AXIS,
        'center': JS_CENTER,
        'mode': JS_MODE,
        'clockwise': {'type': 'boolean'},
    }
    prompt = (
        'Coil (Spring / Helix):\n'
        '   {"op": "coil", "diameter": coil_dia, "pitch": pitch, "revolutions": count, "section_size": wire_dia, '
        '"axis": "z"|"x"|"y" (optional, default "z"), "mode": "new_body"|"join"|"cut" (optional, default "new_body")}'
    )
    rules = '- For springs, coils, or screw helices, use `coil` with `diameter` (major coil diameter), `section_size` (wire diameter), and `pitch` / `revolutions` (or `height`).'

    def validate(self, step, where, ctx):
        dia = step.get('diameter') or step.get('radius') or step.get('coil_dia')
        if not dia:
            for pname in ctx.params:
                if any(w in pname.lower() for w in ('coil_dia', 'spring_dia', 'helix_dia', 'diameter', 'outer_dia', 'od')):
                    dia = pname
                    step['diameter'] = pname
                    break
        if not dia:
            raise ValueError(f'{where}: missing diameter (coil diameter)')

        sec = (step.get('section_size') or step.get('wire_dia') or step.get('wire_diameter')
               or step.get('thickness') or step.get('wire_radius'))
        if not sec:
            for pname in ctx.params:
                if any(w in pname.lower() for w in ('wire', 'section', 'thickness', 'filament')):
                    sec = pname
                    step['section_size'] = pname
                    break
        if not sec:
            raise ValueError(f'{where}: missing section_size (wire diameter)')

        if step.get('axis', 'z').lower() not in AXES:
            raise ValueError(f'{where}: axis must be one of {AXES}')
        if step.get('mode', 'new_body') not in MODES:
            raise ValueError(f'{where}: mode must be one of {MODES}')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core
        import adsk.fusion

        P = adsk.core.Point3D.create
        axis_name = str(step.get('axis', 'z')).lower()
        mode = step.get('mode', 'new_body').lower()
        op_mode = ctx.ops.get(mode, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

        dia_val = step.get('diameter') or step.get('coil_dia')
        if dia_val is None and 'radius' in step:
            R_start_cm = ctx.cm(step['radius'])
        else:
            R_start_cm = ctx.cm(dia_val) / 2.0

        dia2_val = step.get('diameter2') or step.get('end_diameter')
        if dia2_val is not None:
            R_end_cm = ctx.cm(dia2_val) / 2.0
        elif 'radius2' in step:
            R_end_cm = ctx.cm(step['radius2'])
        else:
            R_end_cm = R_start_cm

        sec_val = (step.get('section_size') or step.get('wire_dia')
                   or step.get('wire_diameter') or step.get('thickness'))
        if sec_val is None and 'wire_radius' in step:
            wire_r_cm = ctx.cm(step['wire_radius'])
        else:
            wire_r_cm = ctx.cm(sec_val) / 2.0

        has_rev = ('revolutions' in step) or ('turns' in step)
        has_pitch = 'pitch' in step
        has_h = ('height' in step) or ('length' in step)

        num_rev = ctx.eval_count(step.get('revolutions') or step.get('turns')) if has_rev else None
        pitch_cm = ctx.cm(step['pitch']) if has_pitch else None
        height_cm = ctx.cm(step.get('height') or step.get('length')) if has_h else None

        if num_rev is not None and pitch_cm is not None:
            height_cm = num_rev * pitch_cm
        elif num_rev is not None and height_cm is not None:
            pitch_cm = height_cm / num_rev if num_rev > 0 else height_cm
        elif pitch_cm is not None and height_cm is not None:
            num_rev = height_cm / pitch_cm if pitch_cm > 0 else 5.0
        elif num_rev is not None:
            pitch_cm = max(wire_r_cm * 2.5, 0.2)
            height_cm = num_rev * pitch_cm
        elif height_cm is not None:
            num_rev = 5.0
            pitch_cm = height_cm / num_rev
        else:
            num_rev = 5.0
            pitch_cm = max(wire_r_cm * 3.0, 0.5)
            height_cm = num_rev * pitch_cm

        num_rev = max(0.1, num_rev)
        center = step.get('center', [0, 0, 0])
        cx = ctx.cm(center[0]) if len(center) > 0 else 0.0
        cy = ctx.cm(center[1]) if len(center) > 1 else 0.0
        cz = ctx.cm(center[2]) if len(center) > 2 else 0.0

        points_per_rev = 24
        total_points = max(16, int(round(num_rev * points_per_rev)))
        pt_coll = adsk.core.ObjectCollection.create()
        clockwise = bool(step.get('clockwise', True))
        sign = 1.0 if clockwise else -1.0

        for j in range(total_points + 1):
            t = j / total_points
            angle = sign * t * (2.0 * math.pi * num_rev)
            R = R_start_cm + t * (R_end_cm - R_start_cm)
            axial = t * height_cm

            if axis_name == 'x':
                px = cx + axial
                py = cy + R * math.cos(angle)
                pz = cz + R * math.sin(angle)
            elif axis_name == 'y':
                px = cx + R * math.cos(angle)
                py = cy + axial
                pz = cz + R * math.sin(angle)
            else:  # 'z'
                px = cx + R * math.cos(angle)
                py = cy + R * math.sin(angle)
                pz = cz + axial

            pt_coll.add(P(px, py, pz))

        sk_path = ctx.root.sketches.add(ctx.root.xYConstructionPlane)
        sk_path.name = f"{step.get('id', f'_coil_{ctx.index}')}_path"
        spline = sk_path.sketchCurves.sketchFittedSplines.add(pt_coll)
        try:
            spline.isFixed = True
        except Exception:
            pass

        sweeps = ctx.root.features.sweepFeatures
        try:
            path = ctx.root.features.createPath(spline, True)
        except Exception:
            path = ctx.root.features.createPath(spline)

        pi = ctx.root.constructionPlanes.createInput()
        try:
            pi.setByDistanceOnPath(path, adsk.core.ValueInput.createByReal(0.0))
        except Exception:
            pi.setByDistanceOnPath(spline, adsk.core.ValueInput.createByReal(0.0))
        cplane = ctx.root.constructionPlanes.add(pi)

        sk_prof = ctx.root.sketches.add(cplane)
        sk_prof.name = f"{step.get('id', f'_coil_{ctx.index}')}_prof"
        sec_shape = str(step.get('section', 'circle')).lower()
        if sec_shape in ('square', 'rectangle'):
            w = wire_r_cm
            rect_lines = sk_prof.sketchCurves.sketchLines.addTwoPointRectangle(P(-w, -w, 0), P(w, w, 0))
            try:
                for k in range(rect_lines.count):
                    rect_lines.item(k).isFixed = True
            except Exception:
                pass
        else:
            prof_circle = sk_prof.sketchCurves.sketchCircles.addByCenterRadius(P(0, 0, 0), wire_r_cm)
            try:
                sk_prof.geometricConstraints.addCoincident(prof_circle.centerSketchPoint, sk_prof.originPoint)
                sk_prof.sketchDimensions.addDiameterDimension(
                    prof_circle, P(wire_r_cm, wire_r_cm, 0)
                ).parameter.expression = ctx.ex(step.get('wire_dia', str(wire_r_cm * 20) + ' mm'))
            except Exception:
                try:
                    prof_circle.isFixed = True
                except Exception:
                    pass
        try:
            if not sk_prof.isFullyConstrained:
                for c in [sk_prof.sketchCurves.item(k) for k in range(sk_prof.sketchCurves.count)]:
                    if not c.isFullyConstrained:
                        c.isFixed = True
        except Exception:
            pass

        prof = sk_prof.profiles.item(0)
        inp = h.own_bodies(sweeps.createInput(prof, path, op_mode), ctx.root, mode)
        feat = sweeps.add(inp)
        ctx.add_feature(step, feat)
