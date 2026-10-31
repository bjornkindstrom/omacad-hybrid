"""Small pictures of each object's bodies for the browser, drawn only when the app has nothing else to do.

`render_thumbnail` paints the solids from the front-right-top (as the Home view) with flat shading, back faces
culled, through a small numpy z-buffer (no GL context needed, all triangles at once). `BodyThumbnails` keeps one picture per object and
redraws an object only when its geometry changed, after the user has paused (IDLE_MS) and with no mouse button
held, one object per event-loop turn, so modelling never waits for a picture."""
import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication

SIZE = 40           # shown size in the tree, px
OVERSAMPLE = 2      # drawn this much larger and scaled down: smooth edges
IDLE_MS = 700       # quiet time after the last change before pictures are drawn
NEXT_MS = 30        # pause between two pictures, so input in between is handled first

_EYE = np.array([1.0, -1.3, 1.0]) / np.linalg.norm([1.0, -1.3, 1.0])      # from the model towards the viewer
_RIGHT = np.cross(-_EYE, [0.0, 0.0, 1.0])
_RIGHT /= np.linalg.norm(_RIGHT)
_UP = np.cross(_RIGHT, -_EYE)
_LIGHT = _EYE + 0.6 * _UP - 0.3 * _RIGHT
_LIGHT /= np.linalg.norm(_LIGHT)


def render_thumbnail(solids, size: int = SIZE, scale: float = 2.0) -> QImage:
    """`solids` = [(manifold, rgb 0..1)]. Transparent image of size*scale pixels (devicePixelRatio = scale)."""
    pts, tris, colors = [], [], []
    offset = 0
    for manifold, rgb in solids:
        mesh = manifold.to_mesh()
        v = np.asarray(mesh.vert_properties, dtype=float)[:, :3]
        t = np.asarray(mesh.tri_verts, dtype=np.int64)
        if not len(t):
            continue
        pts.append(v)
        tris.append(t + offset)
        colors.append(np.repeat([rgb[:3]], len(t), axis=0))
        offset += len(v)
    px = int(round(size * scale))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    image.setDevicePixelRatio(scale)
    if not tris:
        return image
    v, t, rgb = np.vstack(pts), np.vstack(tris), np.vstack(colors)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    n = np.cross(b - a, c - a)
    length = np.linalg.norm(n, axis=1)
    keep = (n @ _EYE > 0) & (length > 0)
    if not keep.any():
        return image
    big = px * OVERSAMPLE
    screen = np.stack([v @ _RIGHT, -(v @ _UP)], axis=1)
    lo, hi = screen.min(axis=0), screen.max(axis=0)
    fit = 0.9 * big / max(float((hi - lo).max()), 1e-9)
    screen = (screen - (lo + hi) / 2) * fit + big / 2
    shade = 0.45 + 0.55 * np.clip((n[keep] / length[keep, None]) @ _LIGHT, 0.0, 1.0)
    fill = np.clip(rgb[keep] * shade[:, None] * 255, 0, 255).astype(np.uint8)
    rgba = np.zeros((big, big, 4), np.uint8)
    pixel, tri = _rasterize(screen[t[keep]], (v @ _EYE)[t[keep]], big)
    rgba.reshape(-1, 4)[pixel, :3] = fill[tri]
    rgba.reshape(-1, 4)[pixel, 3] = 255
    canvas = QImage(rgba.tobytes(), big, big, 4 * big, QImage.Format.Format_RGBA8888).copy()
    small = canvas.scaled(px, px, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    small.setDevicePixelRatio(scale)
    return small


def _rasterize(corners, depth, size):
    """Z-buffer: (pixel index, triangle index) of the triangle nearest the viewer at every covered pixel centre.
    `corners` (n, 3, 2) in pixels, `depth` (n, 3) larger = nearer. All triangles at once, no Python loop."""
    x0 = np.clip(np.floor(corners[..., 0].min(axis=1) - 0.5), 0, size - 1).astype(np.int64)
    x1 = np.clip(np.ceil(corners[..., 0].max(axis=1) - 0.5), 0, size - 1).astype(np.int64)
    y0 = np.clip(np.floor(corners[..., 1].min(axis=1) - 0.5), 0, size - 1).astype(np.int64)
    y1 = np.clip(np.ceil(corners[..., 1].max(axis=1) - 0.5), 0, size - 1).astype(np.int64)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    count = w * h
    tri = np.repeat(np.arange(len(corners)), count)
    local = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    px, py = x0[tri] + local % w[tri], y0[tri] + local // w[tri]
    (ax, ay), (bx, by), (cx, cy) = (corners[tri, k].T for k in range(3))
    qx, qy = px + 0.5, py + 0.5
    area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    with np.errstate(divide='ignore', invalid='ignore'):
        l1 = ((cx - bx) * (qy - by) - (cy - by) * (qx - bx)) / area
        l2 = ((ax - cx) * (qy - cy) - (ay - cy) * (qx - cx)) / area
    l3 = 1.0 - l1 - l2
    inside = (area != 0) & (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
    tri, pixel = tri[inside], (py * size + px)[inside]
    d = depth[tri, 0] * l1[inside] + depth[tri, 1] * l2[inside] + depth[tri, 2] * l3[inside]
    order = np.lexsort((-d, pixel))                       # per pixel, nearest first
    pixel, tri = pixel[order], tri[order]
    first = np.ones(len(pixel), bool)
    first[1:] = pixel[1:] != pixel[:-1]
    return pixel[first], tri[first]


def _signature(manifold):
    """Changes whenever the shape or its place changes; cheap compared with drawing."""
    return (manifold.num_tri(), round(manifold.volume(), 6), round(manifold.surface_area(), 6),
            tuple(round(x, 6) for x in manifold.bounding_box()))


class BodyThumbnails(QObject):
    """Pictures for the browser's object rows, kept up to date in idle time."""
    ready = Signal(str)        # object id whose picture was (re)drawn

    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.icons, self.keys, self.pending = {}, {}, []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.work)

    def icon(self, object_id):
        return self.icons.get(object_id)

    def _wanted(self, object_id):
        """(key, [(manifold, rgb)]) of an object's bodies now, or (None, []) when it has none."""
        doc = self.browser.doc
        obj = doc.object_history.objects.get(object_id)
        bodies = [doc.bodies[b] for b in (obj.body_ids if obj else ()) if b in doc.bodies]
        solids = [(b.manifold, tuple(b.color[:3])) for b in bodies if not b.manifold.is_empty()]
        if not solids:
            return None, []
        return tuple((_signature(m), rgb) for m, rgb in solids), solids

    def schedule(self):
        """After a document change: note the objects whose picture is out of date and wait for a quiet moment."""
        objects = self.browser.doc.object_history.objects
        for gone in [oid for oid in self.icons if oid not in objects]:
            self.icons.pop(gone)
            self.keys.pop(gone, None)
        self.pending = list(objects)
        self.timer.start(IDLE_MS)

    def work(self):
        """Draw the next out-of-date picture; put off while a mouse button is down (dragging, orbiting)."""
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            self.timer.start(IDLE_MS)
            return
        self._draw_next()
        if self.pending:
            self.timer.start(NEXT_MS)

    def _draw_next(self):
        while self.pending:
            oid = self.pending.pop(0)
            key, solids = self._wanted(oid)
            if key is None:
                self.icons.pop(oid, None)
                self.keys.pop(oid, None)
                continue
            if self.keys.get(oid) == key:
                continue
            self.icons[oid] = QIcon(QPixmap.fromImage(render_thumbnail(solids)))
            self.keys[oid] = key
            self.ready.emit(oid)
            return

    def finish(self):
        """Draw everything that is pending now instead of in idle time (tests)."""
        self.timer.stop()
        while self.pending:
            self._draw_next()
