"""Viewport capture tools for vision-capable models.

Allows the model to render and inspect 2D screenshots of the open Fusion 360 viewport from standard
camera orientations (isometric, front, back, top, bottom, left, right, or the user's current view),
restoring the user's original camera state afterward.
"""
import base64
import math
import pathlib
import tempfile

from .base import BaseToolkit, ToolError

DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
MIN_SIZE = 200
MAX_SIZE = 1920

# World-coordinate (Z-up, mm) eye direction vectors (from target toward camera eye) and up vectors.
# Matches VibeShaper's coordinate frame: XY ground (+Z up), XZ front (-Y front, +Y back), YZ right (+X right).
VIEW_DIRS = {
    'iso':            ((1.0, -1.0, 0.8),  (0.0, 0.0, 1.0)),
    'iso_top_right':  ((1.0, -1.0, 0.8),  (0.0, 0.0, 1.0)),
    'iso_top_left':   ((-1.0, -1.0, 0.8), (0.0, 0.0, 1.0)),
    'iso_bottom_right': ((1.0, 1.0, -0.8), (0.0, 0.0, 1.0)),
    'iso_bottom_left':  ((-1.0, 1.0, -0.8), (0.0, 0.0, 1.0)),
    'front':          ((0.0, -1.0, 0.0),  (0.0, 0.0, 1.0)),
    'back':           ((0.0, 1.0, 0.0),   (0.0, 0.0, 1.0)),
    'top':            ((0.0, 0.0, 1.0),   (0.0, 1.0, 0.0)),
    'bottom':         ((0.0, 0.0, -1.0),  (0.0, 1.0, 0.0)),
    'right':          ((1.0, 0.0, 0.0),   (0.0, 0.0, 1.0)),
    'left':           ((-1.0, 0.0, 0.0),  (0.0, 0.0, 1.0)),
}
VIEWS = ('current', *VIEW_DIRS.keys())

TOOL_SPECS = [
    {
        'name': 'capture_viewport',
        'description': (
            'Capture one or more rendered screenshots of the 3D viewport from specified camera orientations '
            'so you can visually inspect the model geometry, proportions, alignment, and orientation. '
            'The user\'s camera is automatically restored after capturing.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'views': {
                    'type': 'array',
                    'items': {'type': 'string', 'enum': list(VIEWS)},
                    'description': (
                        'Camera views to capture (1 to 4 views per call). '
                        'Default: ["iso"]. Use ["iso", "front", "right", "top"] for a multi-angle inspection.'
                    ),
                },
                'width': {
                    'type': 'integer',
                    'description': f'Image width in pixels (default {DEFAULT_WIDTH}, max {MAX_SIZE}).',
                },
                'height': {
                    'type': 'integer',
                    'description': f'Image height in pixels (default {DEFAULT_HEIGHT}, max {MAX_SIZE}).',
                },
            },
        },
    },
]
TOOL_NAMES = [t['name'] for t in TOOL_SPECS]


def _clamp_dim(val, default):
    try:
        n = int(val or default)
    except (TypeError, ValueError):
        n = default
    return max(MIN_SIZE, min(MAX_SIZE, n))


def _assign_vec(obj, attr, coords, cls):
    if cls is not None and hasattr(cls, 'create'):
        setattr(obj, attr, cls.create(*coords))
    else:
        cur = getattr(obj, attr, None)
        if cur is not None:
            cur.x, cur.y, cur.z = coords
            setattr(obj, attr, cur)


def _set_camera_view(viewport, view_name):
    """Orient `viewport` to `view_name` and fit the model."""
    if view_name == 'current':
        return
    dirs = VIEW_DIRS.get(view_name)
    if not dirs:
        raise ToolError(f'Unknown view "{view_name}". Valid views: {", ".join(VIEWS)}.')
    (dx, dy, dz), (ux, uy, uz) = dirs
    cam = viewport.camera
    tgt = getattr(cam, 'target', None)
    eye = getattr(cam, 'eye', None)
    dist = 10.0
    if tgt is not None and eye is not None:
        dist = math.sqrt((eye.x - tgt.x) ** 2 + (eye.y - tgt.y) ** 2 + (eye.z - tgt.z) ** 2) or 10.0
    norm = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    scale = dist / norm
    try:
        import adsk.core
        pt_cls = getattr(adsk.core, 'Point3D', None)
        vec_cls = getattr(adsk.core, 'Vector3D', None)
    except ImportError:
        pt_cls, vec_cls = None, None

    tx, ty, tz = getattr(tgt, 'x', 0.0), getattr(tgt, 'y', 0.0), getattr(tgt, 'z', 0.0)
    _assign_vec(cam, 'eye', (tx + dx * scale, ty + dy * scale, tz + dz * scale), pt_cls)
    _assign_vec(cam, 'upVector', (ux, uy, uz), vec_cls)
    if hasattr(cam, 'isSmoothTransition'):
        cam.isSmoothTransition = False
    if hasattr(cam, 'isFitView'):
        cam.isFitView = True
    viewport.camera = cam
    if hasattr(viewport, 'fit'):
        viewport.fit()
    if hasattr(viewport, 'refresh'):
        viewport.refresh()


def capture_viewport(ctx, args):
    app = ctx.app
    viewport = getattr(app, 'activeViewport', None) if app is not None else None
    if viewport is None:
        raise ToolError('No active 3D viewport is available.')

    raw_views = args.get('views')
    if raw_views is None:
        views = ['iso']
    elif isinstance(raw_views, str):
        views = [raw_views]
    elif isinstance(raw_views, list) and raw_views:
        views = [str(v).strip().lower() for v in raw_views if str(v).strip()]
    else:
        raise ToolError('views must be a non-empty list of view names.')
    if not views or len(views) > 4:
        raise ToolError('views must contain between 1 and 4 view names.')
    for v in views:
        if v not in VIEWS:
            raise ToolError(f'Unknown view "{v}". Choose from: {", ".join(VIEWS)}.')

    width = _clamp_dim(args.get('width'), DEFAULT_WIDTH)
    height = _clamp_dim(args.get('height'), DEFAULT_HEIGHT)

    orig_cam = getattr(viewport, 'camera', None)
    saved_eye = getattr(orig_cam, 'eye', None)
    saved_tgt = getattr(orig_cam, 'target', None)
    saved_up = getattr(orig_cam, 'upVector', None)
    snap = (
        (getattr(saved_eye, 'x', 0.0), getattr(saved_eye, 'y', 0.0), getattr(saved_eye, 'z', 0.0)) if saved_eye else None,
        (getattr(saved_tgt, 'x', 0.0), getattr(saved_tgt, 'y', 0.0), getattr(saved_tgt, 'z', 0.0)) if saved_tgt else None,
        (getattr(saved_up, 'x', 0.0), getattr(saved_up, 'y', 0.0), getattr(saved_up, 'z', 1.0)) if saved_up else None,
    )

    images = []
    captured = []
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            for i, v in enumerate(views):
                _set_camera_view(viewport, v)
                out_path = pathlib.Path(tmp_dir) / f'view_{i}_{v}.png'
                ok = viewport.saveAsImageFile(str(out_path), width, height)
                if not ok or not out_path.exists():
                    raise ToolError(f'Fusion could not render the "{v}" viewport image.')
                b64 = base64.b64encode(out_path.read_bytes()).decode('ascii')
                images.append({'mime_type': 'image/png', 'data': b64})
                captured.append(v)
    finally:
        if orig_cam is not None and any(v != 'current' for v in views):
            try:
                try:
                    import adsk.core
                    pt_cls = getattr(adsk.core, 'Point3D', None)
                    vec_cls = getattr(adsk.core, 'Vector3D', None)
                except ImportError:
                    pt_cls, vec_cls = None, None
                if snap[0]:
                    _assign_vec(orig_cam, 'eye', snap[0], pt_cls)
                if snap[1]:
                    _assign_vec(orig_cam, 'target', snap[1], pt_cls)
                if snap[2]:
                    _assign_vec(orig_cam, 'upVector', snap[2], vec_cls)
                if hasattr(orig_cam, 'isSmoothTransition'):
                    orig_cam.isSmoothTransition = False
                viewport.camera = orig_cam
                if hasattr(viewport, 'refresh'):
                    viewport.refresh()
            except Exception:
                pass

    return {
        'views': captured,
        'width': width,
        'height': height,
        'count': len(images),
        'images': images,
    }


_TOOLS = {'capture_viewport': capture_viewport}


def label(name, args, result):
    a = args or {}
    err = isinstance(result, dict) and result.get('error')
    if name == 'capture_viewport':
        views = (isinstance(result, dict) and result.get('views')) or a.get('views') or ['iso']
        if isinstance(views, str):
            views = [views]
        v_str = ', '.join(str(v) for v in views)
        what = f'Captured viewport ({v_str})'
    else:
        what = f'Called {name}'
    return f'{what} (failed: {err})' if err else what


PROMPT = """VIEWING THE 3D VIEWPORT
- You have `capture_viewport` to take rendered screenshots of the active 3D viewport from standard camera angles
  (`"iso"`, `"front"`, `"back"`, `"top"`, `"bottom"`, `"left"`, `"right"`, or `"current"`).
- Use it when a visual look at the existing model helps clarify orientation, shape, or how a new part should fit."""


class ViewToolkit(BaseToolkit):
    """Viewport screenshot capture for vision-capable models."""
    id = 'view'
    name = 'Viewport capture'
    order = 15
    needs = ('images',)
    prompt = PROMPT

    def tools(self):
        return [dict(t) for t in TOOL_SPECS]

    def run(self, name, args, ctx):
        fn = _TOOLS.get(name)
        if not fn:
            raise ToolError(f'Unknown tool "{name}".')
        return fn(ctx, args or {})

    def label(self, name, args, result):
        return label(name, args, result)
