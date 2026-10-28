"""Serializable sketch profiles, constraints, and dimensions."""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from shapely.geometry import Polygon, Point

EDGE_PTS = ("edge_near", "edge_far")
SOLVER_DIM_TYPES = ("ANGLE", "DISTANCE", "HORIZ_DIST", "VERT_DIST", "PT_LINE_DIST")
REF_PREFIX = "ref:"


@dataclass
class SketchProfile:
    """A closed 2D profile bounded by sketch curves, ready for Extrude/Revolve."""
    profile_id: str
    exterior_pts: List[Tuple[float, float]]
    interior_holes: List[List[Tuple[float, float]]] = field(default_factory=list)
    area: float = 0.0

    def contains_point(self, u: float, v: float) -> bool:
        """Tests if a 2D point lies inside this profile."""
        try:
            poly = Polygon(self.exterior_pts, self.interior_holes)
            return poly.contains(Point(u, v))
        except Exception:
            return False

@dataclass
class SketchConstraint:
    """A geometric relation between sketch entities, enforced by the constraint solver.

    ctype: HORIZONTAL, VERTICAL, PARALLEL, PERPENDICULAR, EQUAL, TANGENT, CONCENTRIC,
           COINCIDENT (pts names the touching points), POINT_ON_CIRCLE (refs: circle, line; pts: the line's point), FIX
    """
    cid: str
    ctype: str
    refs: List[str]
    pts: List[str] = field(default_factory=list)  # point names for COINCIDENT ("p1", "p2", "center")

    def to_dict(self) -> Dict[str, Any]:
        return {"cid": self.cid, "ctype": self.ctype, "refs": list(self.refs), "pts": list(self.pts)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchConstraint":
        return cls(data["cid"], data["ctype"], list(data["refs"]), list(data.get("pts", [])))

@dataclass
class SketchDimension:
    """Represents a parametric dimensional constraint in 2D space."""
    dim_id: str
    name: str
    dim_type: str  # LENGTH, DIAMETER, RADIUS, ANGLE, DISTANCE, HORIZ_DIST, VERT_DIST, PT_LINE_DIST (+legacy RECT_*)
    target_entity_id: str
    value: float
    offset_distance: float = 12.0
    # Multi-entity dimensions: the other entity/entities and the point names involved.
    #   ANGLE:        target = line A, refs = [line B], pts = [end of A at the vertex, end of B at the vertex]
    #   *DIST:        target = entity A, refs = [entity B], pts = [point of A, point of B]
    #   PT_LINE_DIST: target = entity with the point, refs = [line], pts = [point name]
    refs: List[str] = field(default_factory=list)
    pts: List[str] = field(default_factory=list)
    # Formula the value comes from (e.g. "width/2"); None = a plain number. Re-evaluated whenever a
    # parameter changes.
    expr: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dim_id": self.dim_id,
            "name": self.name,
            "dim_type": self.dim_type,
            "target_entity_id": self.target_entity_id,
            "value": float(self.value),
            "offset_distance": float(self.offset_distance),
            "refs": list(self.refs),
            "pts": list(self.pts),
            "expr": self.expr,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchDimension":
        return cls(
            dim_id=data["dim_id"],
            name=data.get("name", data["dim_id"]),
            dim_type=data["dim_type"],
            target_entity_id=data["target_entity_id"],
            value=float(data["value"]),
            offset_distance=float(data.get("offset_distance", 12.0)),
            refs=list(data.get("refs", [])),
            pts=list(data.get("pts", [])),
            expr=data.get("expr"),
        )
