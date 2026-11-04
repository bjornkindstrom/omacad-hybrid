"""Knurl: cuts a grip pattern of V grooves into whole outer cylindrical faces, straight, slanted or diamond."""

import math
from typing import Any, Dict, List, Tuple

import numpy as np
import manifold3d as m3d

from omacad.model.features.base import Feature
from omacad.model.features.honeycomb import FULL_GAP, _cylinder_extent, _refitted
from omacad.model.features.offset_face import _frame
from omacad.model.features.revolved_surface import revolved_surface
from omacad.model.kernel import CadKernel

PATTERNS = ("diamond", "straight", "right", "left")
STEPS_PER_TOOTH = 2     # twist steps while a groove passes one tooth: 4 looks the same but took ten times as long to analyse
MAX_FACETS = 2_000_000  # triangles in a cutting tool: more would take minutes and be finer than a printer can show
END_OVERSHOOT = 1e-3    # mm a tool passes a free end, so it never shares a plane with the body's end face


def tooth_count(radius: float, pitch: float) -> int:
    """Whole teeth round the circumference, as close to `pitch` as they fit."""
    return max(3, int(round(2.0 * math.pi * radius / pitch)))


def star_outline(radius: float, depth: float, teeth: int) -> np.ndarray:
    """The knurled cross-section: crests on `radius`, roots `depth` below it, the first crest on +X."""
    angles = np.arange(2 * teeth) * math.pi / teeth
    radii = np.where(np.arange(2 * teeth) % 2 == 0, radius, radius - depth)
    return np.column_stack((radii * np.cos(angles), radii * np.sin(angles)))


def twist_degrees(radius: float, height: float, angle: float) -> float:
    """How far a groove at `angle` from the axis turns over `height`."""
    return math.degrees(height * math.tan(math.radians(angle)) / radius)


def kept_solid(radius: float, height: float, pattern: str, pitch: float, depth: float, angle: float) -> m3d.Manifold:
    """What the grooves leave standing, from z = 0 to `height`, right-hand grooves turning counter-clockwise going up."""
    teeth = tooth_count(radius, pitch)
    star = m3d.CrossSection([star_outline(radius, depth, teeth)])
    if pattern == "straight":
        return m3d.Manifold.extrude(star, height)
    twist = twist_degrees(radius, height, angle)
    divisions = max(1, math.ceil(twist * teeth / 360.0 * STEPS_PER_TOOTH))
    facets = 4 * teeth * divisions * (2 if pattern == "diamond" else 1)
    if facets > MAX_FACETS:
        raise ValueError(f"A pitch of {pitch:g} mm is too fine for a face this large. Use a coarser pitch or a steeper angle.")
    right = m3d.Manifold.extrude(star, height, divisions, twist) if pattern != "left" else None
    left = m3d.Manifold.extrude(star, height, divisions, -twist) if pattern != "right" else None
    if pattern == "diamond":
        return right ^ left
    return right if pattern == "right" else left


def knurl_tool(manifold: m3d.Manifold, ref: Dict[str, Any], params: Dict[str, Any]) -> Tuple[m3d.Manifold, int]:
    """(the solid to cut away, teeth per turn) for one face. Raises ValueError saying why a face can't be knurled."""
    if ref.get("kind") != "cylinder" or ref.get("internal"):
        raise ValueError("A knurl needs an outer round face.")
    ref = _refitted(manifold, ref)
    radius = float(ref["radius"])
    pitch, depth, margin = params["pitch"], params["depth"], params["margin"]
    if pitch <= 0 or depth <= 0 or not 0 <= params["angle"] < 90:
        raise ValueError("Pitch and depth must be above zero, and the angle under 90°.")
    if depth >= radius:
        raise ValueError(f"A depth of {depth:g} mm doesn't fit in a radius of {radius:g} mm.")
    M = _frame(ref["origin"], ref["axis"])
    if revolved_surface(manifold, M, ref) is not None:
        raise ValueError("A knurl needs a straight round face, and this one's radius changes along its length.")
    extent = _cylinder_extent(manifold, np.linalg.inv(M), radius, float(ref["length"]), False)
    if extent is None:
        raise ValueError("The round face was not found on the body.")
    theta, (z0, z1) = extent
    if np.diff(np.append(theta, theta[0] + 2.0 * math.pi)).max() >= FULL_GAP:
        raise ValueError("A knurl needs a face that goes all the way round.")
    bottom = z0 + margin if margin > 0 else z0 - END_OVERSHOOT
    top = z1 - margin if margin > 0 else z1 + END_OVERSHOOT
    if top - bottom <= 1e-3:
        raise ValueError("The margin leaves no room for a knurl.")
    height = top - bottom
    kept = kept_solid(radius, height, params["pattern"], pitch, depth, params["angle"])
    # only the band of the wall: whatever lies inside the roots, such as a bore, is not touched
    outer = radius + max(depth, 1.0)
    band = m3d.Manifold.cylinder(height, outer, outer, 96)
    return (band - kept).translate((0.0, 0.0, bottom)).transform(M[:3, :]), tooth_count(radius, pitch)


def apply_knurl(manifold: m3d.Manifold, faces: List[Dict[str, Any]], params: Dict[str, Any]):
    """(new manifold, teeth cut per turn in all faces, why any face was left out)."""
    tools, teeth, notes = [], 0, []
    for ref in faces:
        try:
            tool, count = knurl_tool(manifold, ref, params)
        except ValueError as e:         # one odd face must not break the history; the panel shows the reason
            notes.append(str(e))
            continue
        tools.append(tool)
        teeth += count
    if not tools:
        return manifold, 0, notes
    return CadKernel.drop_slivers(manifold - m3d.Manifold.batch_boolean(tools, m3d.OpType.Add)), teeth, notes


class KnurlFeature(Feature):
    """Cuts a knurl into the chosen round faces of one body."""

    PARAMS = ("pattern", "pitch", "depth", "angle", "margin")

    def __init__(self, feature_id: str, name: str, target_body_id: str, faces=None, pattern: str = "diamond",
                 pitch: float = 1.5, depth: float = 0.6, angle: float = 30.0, margin: float = 0.0):
        super().__init__(feature_id, "knurl", name)
        self.target_body_id = target_body_id
        self.faces = list(faces or [])
        self.pattern = pattern if pattern in PATTERNS else "diamond"
        self.pitch, self.depth, self.angle, self.margin = float(pitch), float(depth), float(angle), float(margin)
        self.teeth = 0
        self.notes: List[str] = []

    def params(self) -> Dict[str, Any]:
        return {key: getattr(self, key) for key in self.PARAMS}

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        target.manifold, self.teeth, self.notes = apply_knurl(target.manifold, self.faces, self.params())
        target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "target_body_id": self.target_body_id, "faces": self.faces,
                **self.params()}
