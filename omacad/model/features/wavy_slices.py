"""Wavy Slices feature: rebuilds a solid as stacked horizontal layers whose outlines follow a wave."""

import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import manifold3d as m3d

from omacad.model.features.base import Feature

MAX_LAYERS = 1000
MAX_RING_POINTS = 1500
RING_STEP = 1.0                 # mm between outline points, unless the waves need them closer
POINTS_PER_WAVE = 16
CORNER_TURN = math.radians(20)  # outline vertices that turn this much stay exact points
MIN_LAST_LAYER = 0.1            # a top layer thinner than this share of the slice height joins the one below


def _signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def layer_bounds(z_min: float, z_max: float, slice_height: float) -> List[Tuple[float, float]]:
    """(bottom, top) of every layer. The stack keeps the body's exact height."""
    if slice_height <= 0:
        raise ValueError("Slice height must be above zero.")
    total = z_max - z_min
    count = max(1, math.ceil(total / slice_height - 1e-9))
    if count > 1 and total - (count - 1) * slice_height < MIN_LAST_LAYER * slice_height:
        count -= 1
    if count > MAX_LAYERS:
        raise ValueError(f"{count} layers is too many (the limit is {MAX_LAYERS}). Use a taller slice height.")
    edges = [z_min + i * slice_height for i in range(count)] + [z_max]
    return list(zip(edges[:-1], edges[1:]))


def wave_ring(ring, waves: int, amplitude: float, phase: float) -> np.ndarray:
    """A closed outline moved along its outward normal by a sine wave of `waves` whole cycles (`amplitude` peak to
    peak). Each ring is measured from where it crosses a ray from its centre towards +X, not from its first vertex,
    which differs from one slice to the next: that keeps the waves lined up up the stack and keeps holes in step
    with the outer wall, so a hollow body's wall thickness stays even."""
    pts = np.asarray(ring, dtype=float)
    if _signed_area(pts) < 0:
        pts = pts[::-1]
    lengths = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
    keep = lengths > 1e-9
    pts, lengths = pts[keep], lengths[keep]
    if len(pts) < 3:
        return pts
    along = np.concatenate(([0.0], np.cumsum(lengths)))
    perimeter = float(along[-1])

    next_pts = np.roll(pts, -1, axis=0)
    cross = pts[:, 0] * next_pts[:, 1] - next_pts[:, 0] * pts[:, 1]
    center = np.sum((pts + next_pts) * cross[:, None], axis=0) / (3.0 * np.sum(cross))
    a, b = pts - center, next_pts - center
    crossing = np.nonzero((a[:, 1] <= 0) & (b[:, 1] > 0))[0]
    start = 0.0
    if len(crossing):
        share = -a[crossing, 1] / (b[crossing, 1] - a[crossing, 1])
        reach = a[crossing, 0] + share * (b[crossing, 0] - a[crossing, 0])
        best = int(np.argmax(reach))
        start = float(along[crossing[best]] + share[best] * lengths[crossing[best]])

    count = int(np.clip(max(POINTS_PER_WAVE * waves, perimeter / RING_STEP), 3 * POINTS_PER_WAVE, MAX_RING_POINTS))
    edges = (next_pts - pts) / lengths[:, None]
    before = np.roll(edges, 1, axis=0)
    turn = np.abs(np.arctan2(before[:, 0] * edges[:, 1] - before[:, 1] * edges[:, 0], np.sum(before * edges, axis=1)))
    # t is measured from the seam; the corners join the even samples, so an amplitude of 0 returns the sharp outline
    corners = (along[:-1][turn >= CORNER_TURN] - start) % perimeter
    t = np.unique(np.concatenate((np.arange(count) * perimeter / count, corners)))
    closed = np.vstack((pts, pts[:1]))
    on_ring = (t + start) % perimeter
    samples = np.column_stack((np.interp(on_ring, along, closed[:, 0]), np.interp(on_ring, along, closed[:, 1])))

    steps = np.roll(samples, -1, axis=0) - samples
    steps /= np.maximum(np.linalg.norm(steps, axis=1, keepdims=True), 1e-12)
    tangent = steps + np.roll(steps, 1, axis=0)
    normals = np.column_stack((tangent[:, 1], -tangent[:, 0]))
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)

    shift = amplitude / 2.0 * np.sin(2.0 * math.pi * waves * t / perimeter + phase)
    return samples + normals * shift[:, None]


def wavy_section(section: m3d.CrossSection, waves: int, amplitude: float, phase: float) -> m3d.CrossSection:
    """`section` with every outline waved. Loops that fold over themselves are cleaned up by the fill rule."""
    solid, holes = [], []
    for ring in section.to_polygons():
        ring = np.asarray(ring, dtype=float)
        if len(ring) >= 3:
            (solid if _signed_area(ring) > 0 else holes).append(wave_ring(ring, waves, amplitude, phase))
    result = m3d.CrossSection(solid, m3d.FillRule.Positive)
    if holes:
        result = result - m3d.CrossSection(holes, m3d.FillRule.Positive)
    return result


def slice_body(m: m3d.Manifold, waves: int, slice_height: float, amplitude: float, phase_shift: float = 0.0,
               offset: float = 0.0) -> m3d.Manifold:
    """The stack of waved layers for body `m`. phase_shift: degrees each layer's wave moves from the one below
    (360 = one whole wave). offset: mm the outline first moves outward (+) or inward (-). Each layer takes its
    outline from its own mid-height. Raises ValueError when the values give no usable body."""
    if m.is_empty():
        raise ValueError("The body is empty.")
    waves = max(1, int(round(waves)))
    bbox = m.bounding_box()
    layers = []
    for i, (bottom, top) in enumerate(layer_bounds(bbox[2], bbox[5], slice_height)):
        section = m.slice((bottom + top) / 2.0)
        if offset:
            section = section.offset(offset, m3d.JoinType.Miter, 4.0)
        if section.is_empty():
            continue
        waved = wavy_section(section, waves, amplitude, i * math.radians(phase_shift))
        if not waved.is_empty():
            layers.append(waved.extrude(top - bottom).translate((0.0, 0.0, bottom)))
    if not layers:
        raise ValueError("Nothing is left of the body. Use a smaller inward offset.")
    return m3d.Manifold.batch_boolean(layers, m3d.OpType.Add)


class WavySlicesFeature(Feature):
    """Rebuilds a body as a stack of horizontal layers with wavy edges."""

    PARAMS = ("waves", "slice_height", "amplitude", "phase_shift", "offset")

    def __init__(self, feature_id: str, name: str, target_body_id: str, waves: int = 12, slice_height: float = 2.0,
                 amplitude: float = 2.0, phase_shift: float = 15.0, offset: float = 0.0):
        super().__init__(feature_id, "wavy_slices", name)
        self.target_body_id = target_body_id
        self.waves = int(round(waves))
        self.slice_height = float(slice_height)
        self.amplitude = float(amplitude)
        self.phase_shift = float(phase_shift)
        self.offset = float(offset)

    def build(self, m: m3d.Manifold) -> m3d.Manifold:
        return slice_body(m, self.waves, self.slice_height, self.amplitude, self.phase_shift, self.offset)

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        target.manifold = self.build(target.manifold)
        target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            **{key: getattr(self, key) for key in self.PARAMS},
        }
