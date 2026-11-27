"""Lithophane: a picture as a wall of varying thickness (dark = thick), flat, round or as a globe, lit from behind.

The closed skin is built directly as one mesh, without booleans. The picture is kept inside the step (grayscale PNG,
base64) so a project never depends on the original file."""

import base64
import io
import math
from functools import lru_cache
from typing import Any, Dict, Tuple

import numpy as np
import manifold3d as m3d

from omacad.model import quality
from omacad.model.features.base import Body, Feature
from omacad.model.features.primitives import CylinderFeature

SHAPES = ("flat", "cylinder", "sphere")
FITS = ("proportional", "crop", "stretch")
MAX_PICTURE = 1000        # px, longest side of the stored picture
MAX_CELLS = 90_000        # picture cells of a finished body; finer detail is coarsened to this
PREVIEW_CELLS = 10_000    # while a panel is open


def encode_picture(source: Any) -> str:
    """A picture (path, or bytes of an image file) as the base64 grayscale PNG a step stores. Transparent = white."""
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGBA")
    img.thumbnail((MAX_PICTURE, MAX_PICTURE), Image.Resampling.LANCZOS)
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    gray = Image.alpha_composite(white, img).convert("L")
    out = io.BytesIO()
    gray.save(out, "PNG", optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii")


@lru_cache(maxsize=4)
def _picture(data: str):
    from PIL import Image
    img = Image.open(io.BytesIO(base64.b64decode(data)))
    img.load()
    return img.convert("L")


def skin(outer: np.ndarray, inner: np.ndarray, periodic: bool, pole_bottom=False, pole_top=False) -> m3d.Manifold:
    """A closed solid between two point grids (rows, cols, 3). `periodic`: the last column joins the first. A pole
    row has all its points in one place and becomes a single vertex."""
    rows, cols = outer.shape[:2]
    n = rows * cols
    idx = np.arange(n).reshape(rows, cols)
    if pole_bottom:
        idx[0] = idx[0, 0]
    if pole_top:
        idx[-1] = idx[-1, 0]
    g = np.column_stack([idx, idx[:, :1]]) if periodic else idx
    a, b, c, d = (q.ravel() for q in (g[:-1, :-1], g[:-1, 1:], g[1:, 1:], g[1:, :-1]))
    top = np.concatenate([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    tris = [top, top[:, ::-1] + n]

    def rim(chain):            # the wall between the two skins along a border, walked as the outer skin does
        p, q = chain[:-1], chain[1:]
        tris.append(np.column_stack([q, p, p + n]))
        tris.append(np.column_stack([q, p + n, q + n]))

    if not pole_bottom:
        rim(g[0])
    if not pole_top:
        rim(g[-1][::-1])
    if not periodic:
        rim(g[:, -1])
        rim(g[::-1, 0])
    faces = np.concatenate(tris)
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 2] != faces[:, 0])]
    used, faces = np.unique(faces, return_inverse=True)
    pts = np.concatenate([outer.reshape(-1, 3), inner.reshape(-1, 3)])[used]
    solid = m3d.Manifold(m3d.Mesh(pts.astype(np.float32), faces.reshape(-1, 3).astype(np.uint32)))
    if solid.status() != m3d.Error.NoError or solid.volume() <= 0:
        raise ValueError("The lithophane could not be built with these values.")
    return solid


class LithophaneFeature(Feature):
    DEFAULTS: Dict[str, Any] = {
        "image_data": "", "shape": "flat", "fit": "proportional", "width": 100.0, "height": 75.0, "radius": 40.0,
        "arc": 180.0, "lat_span": 120.0, "opening": 40.0, "upright": True, "min_thickness": 0.8,
        "max_thickness": 3.0, "detail": 0.4, "frame": 3.0, "brightness": 0.0, "contrast": 0.0, "gamma": 1.0,
        "invert": False, "mirror": False,
    }
    PARAMS = tuple(DEFAULTS)

    def __init__(self, feature_id: str, name: str, translation: Any = None, **params):
        super().__init__(feature_id, "lithophane", name)
        for key, default in self.DEFAULTS.items():
            setattr(self, key, type(default)(params.get(key, default)))
        self.plane_origin = self.plane_normal = self.plane_u = self.plane_v = None
        self.translation = [float(x) for x in ((0.0, 0.0, 0.0) if translation is None else translation)]

    def _check(self) -> None:
        if not self.image_data:
            raise ValueError("Choose a picture first.")
        if self.shape not in SHAPES or self.fit not in FITS:
            raise ValueError("Unknown lithophane shape or fit.")
        if not 0.0 < self.min_thickness < self.max_thickness:
            raise ValueError("Min thickness must be above 0 and below Max thickness.")
        if self.detail <= 0 or self.gamma <= 0 or self.frame < 0:
            raise ValueError("Detail and Gamma must be above 0, and Frame can't be negative.")
        if self.shape == "flat":
            if self.width <= 2 * self.frame or self.size()[1] <= 2 * self.frame:
                raise ValueError("The frame leaves no room for the picture.")
            return
        if self.radius <= self.max_thickness + 0.5:
            raise ValueError("Radius must be larger than Max thickness.")
        if not 5.0 <= self.arc <= 360.0:
            raise ValueError("Arc must be between 5° and 360°.")
        if self.shape == "cylinder":
            if self.size()[1] <= 2 * self.frame or (self.arc < 360.0 and self.size()[0] <= 2 * self.frame):
                raise ValueError("The frame leaves no room for the picture.")
        else:
            if not 5.0 <= self.lat_span <= 180.0:
                raise ValueError("Picture height must be between 5° and 180°.")
            if not 0.0 <= self.opening < 2 * (self.radius - self.max_thickness) * 0.95:
                raise ValueError("The opening must be smaller than the globe.")

    def size(self) -> Tuple[float, float]:
        """Width and height of the picture along the surface, mm, frame included."""
        if self.shape == "sphere":
            return self.radius * math.radians(self.arc), self.radius * math.radians(self.lat_span)
        w = self.width if self.shape == "flat" else self.radius * math.radians(self.arc)
        if self.fit != "proportional":
            return w, self.height
        fx = 0.0 if self._wraps() else self.frame
        iw, ih = _picture(self.image_data).size
        return w, (w - 2 * fx) * ih / iw + 2 * self.frame

    def _wraps(self) -> bool:
        return self.shape == "cylinder" and self.arc >= 360.0 - 1e-6

    def _thickness(self, cols: int, rows: int, aspect: float) -> np.ndarray:
        """Wall thickness at cols x rows picture points, row 0 at the bottom."""
        from PIL import Image, ImageOps
        img = _picture(self.image_data)
        if self.mirror:
            img = ImageOps.mirror(img)
        if self.fit == "crop" or (self.shape == "sphere" and self.fit == "proportional"):
            iw, ih = img.size
            cw, ch = (ih * aspect, ih) if iw / ih > aspect else (iw, iw / aspect)
            img = img.crop((round((iw - cw) / 2), round((ih - ch) / 2),
                            max(round((iw + cw) / 2), round((iw - cw) / 2) + 1),
                            max(round((ih + ch) / 2), round((ih - ch) / 2) + 1)))
        lum = np.asarray(img.resize((cols, rows), Image.Resampling.LANCZOS), dtype=float)[::-1] / 255.0
        lum = (lum - 0.5) * (1.0 + self.contrast / 100.0) + 0.5 + self.brightness / 100.0
        lum = np.clip(lum, 0.0, 1.0) ** (1.0 / self.gamma)
        if self.invert:
            lum = 1.0 - lum
        return self.max_thickness - (self.max_thickness - self.min_thickness) * lum

    def _framed(self, u: np.ndarray, v: np.ndarray, w: float, h: float) -> np.ndarray:
        """Thickness on the grid of distances u, v (mm from the lower left corner); the frame is full thickness."""
        fx = 0.0 if self._wraps() else self.frame
        fy = self.frame
        t = np.full((len(v), len(u)), self.max_thickness)
        iu = np.flatnonzero((u >= fx - 1e-9) & (u <= w - fx + 1e-9))
        iv = np.flatnonzero((v >= fy - 1e-9) & (v <= h - fy + 1e-9))
        if len(iu) and len(iv):
            t[np.ix_(iv, iu)] = self._thickness(len(iu), len(iv), (w - 2 * fx) / (h - 2 * fy))
        return t

    def _counts(self, w: float, h: float) -> Tuple[int, int]:
        limit = PREVIEW_CELLS if quality.is_interactive_mode() else MAX_CELLS
        step = max(self.detail, math.sqrt(w * h / limit))
        return max(8, int(w / step)), max(8, int(h / step))

    def effective_detail(self) -> float:
        """The point distance a finished body really gets: coarser than `detail` when that needs too many points."""
        w, h = self._surface()
        return max(self.detail, math.sqrt(w * h / MAX_CELLS))

    def _surface(self) -> Tuple[float, float]:
        return (2 * math.pi * self.radius, math.pi * self.radius) if self.shape == "sphere" else self.size()

    def build_solid(self) -> m3d.Manifold:
        self._check()
        nu, nv = self._counts(*self._surface())
        solid = {"flat": self._flat, "cylinder": self._cylinder, "sphere": self._sphere}[self.shape](nu, nv)
        return CylinderFeature._place(self, solid)

    def _flat(self, nu: int, nv: int) -> m3d.Manifold:
        w, h = self.size()
        u, v = np.linspace(0, w, nu + 1), np.linspace(0, h, nv + 1)
        t = self._framed(u, v, w, h)
        x, y = np.meshgrid(u - w / 2, v)
        zero = np.zeros_like(t)
        if self.upright:       # standing on Z 0, seen from the front (-Y)
            outer, inner = np.stack([x, -t, y], -1), np.stack([x, zero, y], -1)
        else:                  # lying on Z 0, seen from above
            outer, inner = np.stack([x, y - h / 2, t], -1), np.stack([x, y - h / 2, zero], -1)
        return skin(outer, inner, False)

    def _cylinder(self, nu: int, nv: int) -> m3d.Manifold:
        w, h = self.size()
        wraps = self._wraps()
        if wraps:
            nu = max(nu, 24)
            u = np.arange(nu) * (w / nu)
        else:
            u = np.linspace(0, w, nu + 1)
        v = np.linspace(0, h, nv + 1)
        t = self._framed(u, v, w, h)
        ang = -math.pi / 2 + (u / w - 0.5) * math.radians(self.arc)      # the middle of the picture faces -Y
        r0 = self.radius - self.max_thickness

        def shell(r):
            return np.stack([r * np.cos(ang), r * np.sin(ang), np.broadcast_to(v[:, None], r.shape)], -1)

        return skin(shell(r0 + t), shell(np.full_like(t, r0)), wraps)

    def _sphere(self, nu: int, nv: int) -> m3d.Manifold:
        r0 = self.radius - self.max_thickness
        open_bottom = self.opening > 1e-6
        low = -math.acos(min(1.0, self.opening / 2 / r0)) if open_bottom else -math.pi / 2
        nu, nv = max(nu, 32), max(nv, 16)
        lon = (np.arange(nu) / nu - 0.5) * 2 * math.pi
        lat = np.linspace(low, math.pi / 2, nv + 1)
        t = np.full((nv + 1, nu), self.max_thickness)
        half_lon, half_lat = math.radians(self.arc) / 2, math.radians(self.lat_span) / 2
        iu = np.flatnonzero((lon >= -half_lon - 1e-9) & (lon <= half_lon + 1e-9))
        # The picture's rows cover lat_span round the equator; the opening cuts off the ones below it
        step = lat[1] - lat[0]
        rows = np.arange(math.ceil((-half_lat - low) / step - 1e-9), math.floor((half_lat - low) / step + 1e-9) + 1)
        if len(iu) and len(rows):
            pic = self._thickness(len(iu), len(rows), self.arc / self.lat_span)
            keep = (rows >= 0) & (rows <= nv)
            t[np.ix_(rows[keep], iu)] = pic[keep]
        t[-1] = t[-1].mean()
        if not open_bottom:
            t[0] = t[0].mean()
        ang = lon - math.pi / 2

        def shell(r):
            c = np.cos(lat)[:, None]
            return np.stack([r * c * np.cos(ang), r * c * np.sin(ang), r * np.sin(lat)[:, None]], -1)

        solid = skin(shell(r0 + t), shell(np.full_like(t, r0)), True, not open_bottom, True)
        return solid.translate((0.0, 0.0, -solid.bounding_box()[2]))

    def execute(self, doc: Any) -> None:
        body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=self.build_solid(), relief=True)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        d = {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
             "suppressed": self.suppressed}
        d.update({key: getattr(self, key) for key in self.PARAMS})
        d["translation"] = self.translation
        return d
