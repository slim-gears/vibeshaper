"""Thread timeline feature."""
import re

from .base import BaseFeature, JS_LEN
from . import _helpers as h


def _is_cylindrical_face_internal(face):
    """Return True if cylindrical face is an internal hole/bore, False if external shaft/boss."""
    geom = face.geometry
    pt = face.pointOnFace
    orig = geom.origin
    axis = geom.axis.copy()
    axis.normalize()
    v = orig.vectorTo(pt)
    proj = axis.copy()
    proj.scaleBy(v.dotProduct(axis))
    v.subtract(proj)
    try:
        _, normal = face.evaluator.getNormalAtPoint(pt)
    except Exception:
        normal = None
    if normal and v.length > 1e-6:
        return normal.dotProduct(v) < 0
    return True


def _select_cylindrical_faces(body_or_feat, target_type='all', dia_cm=None, tol=0.05):
    import adsk.core
    matched = []
    faces = getattr(body_or_feat, 'faces', None)
    if not faces:
        return []
    for k in range(faces.count):
        face = faces.item(k)
        if face.geometry.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType:
            continue
        cyl = face.geometry
        face_dia_cm = cyl.radius * 2.0
        if dia_cm is not None and abs(face_dia_cm - dia_cm) > tol:
            continue
        is_int = _is_cylindrical_face_internal(face)
        if target_type == 'internal' and not is_int:
            continue
        if target_type == 'external' and is_int:
            continue
        matched.append((face, is_int, face_dia_cm))
    return matched


class ThreadFeature(BaseFeature):
    op = 'thread'
    name = 'Thread'
    order = 90
    schema = {
        'feature': {'type': 'string'},
        'target': {'type': 'string'},
        'modeled': {'type': 'boolean'},
        'designation': {'type': 'string'},
        'thread_class': {'type': 'string'},
        'diameter': JS_LEN,
    }
    prompt = (
        'Thread:\n'
        '   {"op": "thread", "feature": feature_id (optional), "target": "internal"|"external"|"all" (optional), '
        '"modeled": true|false (optional, default true), "designation": "M6x1" (optional)}'
    )
    rules = (
        '- To thread a hole, bore, or bolt, add a `thread` step specifying the cut feature: '
        '`{"op": "thread", "feature": "bore_cut", "target": "internal", "designation": "M20x2.5"}`. '
        'Physical 3D threads are modeled by default (`modeled: true`).'
    )

    def validate(self, step, where, ctx):
        target = step.get('target', 'all')
        if target not in ('internal', 'external', 'all'):
            raise ValueError(f'{where}: target must be one of ("internal", "external", "all")')
        if 'feature' in step and step['feature'] not in ctx.features:
            raise ValueError(f'{where}: feature {step["feature"]!r} not found in previous features')
        if 'id' in step:
            ctx.features.add(step['id'])

    def execute(self, step, ctx):
        import adsk.core
        import adsk.fusion

        target_type = step.get('target', 'all')
        target_obj = (ctx.features.get(step['feature']) if 'feature' in step
                      else h.get_body(ctx.root, step.get('target_body'), ctx.features))
        target_dia_cm = ctx.cm(step['diameter']) if 'diameter' in step else None

        # Derive target diameter from designation (e.g. M20x2.5 -> 2.0 cm) if not explicitly set
        desig_req = str(step.get('designation', '')).strip()
        if target_dia_cm is None and desig_req:
            m_desig = re.search(r'M(\d+(?:\.\d+)?)', desig_req, re.IGNORECASE)
            if m_desig:
                target_dia_cm = float(m_desig.group(1)) / 10.0

        matches = _select_cylindrical_faces(
            target_obj, target_type, target_dia_cm, tol=0.3 if target_dia_cm else 0.05
        )
        if not matches:
            raise ValueError(f"no cylindrical faces matched for thread (target={target_type})")

        groups = {}
        for face, is_int, dia_cm in matches:
            key = (is_int, round(dia_cm, 3))
            groups.setdefault(key, []).append((face, dia_cm))

        thread_feats = ctx.root.features.threadFeatures
        try:
            tdq = adsk.fusion.ThreadDataQuery.create(False)
        except Exception:
            tdq = thread_feats.threadDataQuery

        def_thread_type = (tdq.defaultMetricThreadType if hasattr(tdq, 'defaultMetricThreadType')
                           else 'ISO Metric profile')
        req_thread_type = step.get('thread_type') or def_thread_type
        is_modeled = step.get('modeled', True)

        created_any = False
        for (is_int, _), face_list in groups.items():
            sample_dia = face_list[0][1]
            desig = step.get('designation')
            t_class = step.get('thread_class')

            # If designation specified, skip cylinders that do not match its nominal size
            if desig:
                m_desig = re.search(r'M(\d+(?:\.\d+)?)', str(desig), re.IGNORECASE)
                if m_desig:
                    nominal_cm = float(m_desig.group(1)) / 10.0
                    if abs(sample_dia - nominal_cm) > 0.35:
                        continue
            if not desig:
                try:
                    rec = tdq.recommendThreadData(sample_dia, is_int, req_thread_type)
                    if rec and rec[0]:
                        desig = rec[1]
                        if not t_class:
                            t_class = rec[2]
                except Exception:
                    pass

            if not desig:
                try:
                    sizes = tdq.allSizes(req_thread_type)
                    if sizes:
                        best_s = min(sizes, key=lambda sz: abs(ctx.um.evaluateExpression(sz, 'mm') - sample_dia * 10))
                        desigs = tdq.allDesignations(req_thread_type, best_s)
                        if desigs:
                            desig = desigs[0]
                except Exception:
                    pass

            if not desig:
                nominal_mm = int(round(sample_dia * 10))
                desig = f"M{nominal_mm}x1" if nominal_mm < 10 else f"M{nominal_mm}x1.5"

            if not t_class:
                try:
                    classes = tdq.allClasses(is_int, req_thread_type, desig)
                    if classes:
                        t_class = classes[0]
                except Exception:
                    pass
            if not t_class:
                t_class = "6H" if is_int else "6g"

            thread_info = thread_feats.createThreadInfo(is_int, req_thread_type, desig, t_class)
            faces_coll = adsk.core.ObjectCollection.create()
            for f, _ in face_list:
                faces_coll.add(f)

            inp = thread_feats.createInput(faces_coll, thread_info)
            inp.isFullLength = True
            inp.isModeled = bool(is_modeled)
            feat = thread_feats.add(inp)
            ctx.add_feature(step, feat)
            created_any = True

        if not created_any:
            raise ValueError(f"no matching cylindrical faces found for thread designation {step.get('designation')!r}")
