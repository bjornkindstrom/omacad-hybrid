"""Where a dimension is drawn: the inverse of the layout in `ui/viewport/overlay_mixin.draw_dimensions`.

`offset_for_point` turns a point the user dragged the dimension to into the `offset_distance` that makes the
drawing pass through it, so dragging a badge moves the dimension line out of the way of the drawing.
"""

import math
from typing import Optional, Tuple

from omacad.model.sketch import (
    SketchArc, SketchCenterRect, SketchCircle, SketchLine, SketchRect, SketchSlot,
    arm_vector, point_of, ref_segment, EDGE_PTS,
)

PT_LINE_DEFAULT_OFFSET = 12.0   # the offset a point-to-line dimension is created with (draws the 8 mm / radius+6 shift)


def pt_line_base_shift(ent) -> float:
    """How far a point-to-line dimension is drawn along the line from the point, at the default offset."""
    return (ent.radius + 6.0) if isinstance(ent, SketchCircle) else 8.0


def lines_are_parallel(a: SketchLine, b: SketchLine, tol_deg: float = 0.5) -> bool:
    """Within half a degree of parallel (either direction)."""
    ax, ay = a.p2[0] - a.p1[0], a.p2[1] - a.p1[1]
    bx, by = b.p2[0] - b.p1[0], b.p2[1] - b.p1[1]
    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
    if la < 1e-9 or lb < 1e-9:
        return False
    return abs(ax * by - ay * bx) / (la * lb) <= math.sin(math.radians(tol_deg))


def line_distance(a: SketchLine, b: SketchLine) -> float:
    """Distance from the start of `a` to the (infinite) line through `b`: the gap between two parallel lines."""
    (x1, y1), (x2, y2) = b.p1, b.p2
    L = math.hypot(x2 - x1, y2 - y1) or 1.0
    return abs((a.p1[0] - x1) * (y2 - y1) - (a.p1[1] - y1) * (x2 - x1)) / L


def _angle_vertex(sketch, dim):
    ent = sketch.get_entity(dim.target_entity_id)
    other = sketch.get_entity(dim.refs[0]) if dim.refs else None
    if not (isinstance(ent, SketchLine) and isinstance(other, SketchLine) and len(dim.pts) == 2):
        return None
    ua, ub = arm_vector(ent, dim.pts[0]), arm_vector(other, dim.pts[1])
    na, nb = math.hypot(*ua), math.hypot(*ub)
    if na <= 1e-6 or nb <= 1e-6:
        return None
    pa, pb = point_of(ent, dim.pts[0]), point_of(other, dim.pts[1])
    det = ua[0] * ub[1] - ua[1] * ub[0]
    if abs(det) > 1e-9 * na * nb:
        t = ((pb[0] - pa[0]) * ub[1] - (pb[1] - pa[1]) * ub[0]) / det
        return (pa[0] + ua[0] * t, pa[1] + ua[1] * t)
    return ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)


def offset_for_point(sketch, dim, uv: Tuple[float, float]) -> Optional[float]:
    """The offset_distance that puts the dimension line through `uv`, or None for a dimension that has none."""
    u, v = uv
    ent = sketch.get_entity(dim.target_entity_id)
    if ent is None:
        return None
    t = dim.dim_type
    if t == "RECT_WIDTH":
        if isinstance(ent, SketchRect):
            y_base = min(ent.p1[1], ent.p2[1])
        elif isinstance(ent, SketchCenterRect):
            y_base = ent.get_corners()[0][1]
        else:
            return None
        return y_base - v
    if t == "RECT_HEIGHT":
        if isinstance(ent, SketchRect):
            x_base = max(ent.p1[0], ent.p2[0])
        elif isinstance(ent, SketchCenterRect):
            x_base = ent.get_corners()[1][0]
        else:
            return None
        return u - x_base
    if t == "LENGTH":
        if isinstance(ent, SketchLine):
            a, b, extra = ent.p1, ent.p2, 0.0
        elif isinstance(ent, SketchSlot):
            a, b, extra = ent.center1, ent.center2, ent.radius
        else:
            return None
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L <= 1e-4:
            return None
        return ((u - a[0]) * -(b[1] - a[1]) + (v - a[1]) * (b[0] - a[0])) / L - extra
    if t in ("DIAMETER", "RADIUS"):
        if isinstance(ent, (SketchCircle, SketchSlot)):
            (cx, cy), r = (ent.center if isinstance(ent, SketchCircle) else ent.center2), ent.radius
        elif isinstance(ent, SketchArc) and ent.get_circle_params():
            (cx, cy), r = ent.get_circle_params()[0], ent.get_circle_params()[1]
        else:
            return None
        return math.hypot(u - cx, v - cy) - r
    if t == "ANGLE":
        vtx = _angle_vertex(sketch, dim)
        if vtx is None:
            return None
        return (max(8.0, math.hypot(u - vtx[0], v - vtx[1]) - 6.0) - 8.0) / 0.6   # badge sits 6 mm outside the arc
    if t in ("DISTANCE", "HORIZ_DIST", "VERT_DIST", "PT_LINE_DIST"):
        other = sketch.get_entity(dim.refs[0]) if dim.refs else None
        edge = ref_segment(dim.refs[0]) if dim.refs else None
        if t == "PT_LINE_DIST":
            if edge is not None:
                (x1, y1), (x2, y2) = edge[0], edge[1]
            elif isinstance(other, SketchLine):
                (x1, y1), (x2, y2) = other.p1, other.p2
            else:
                return None
            if not dim.pts or dim.pts[0] in EDGE_PTS:
                return None                    # edge of a circle to a line: drawn straight between them, nothing to move
            P = point_of(ent, dim.pts[0])
            L = math.hypot(x2 - x1, y2 - y1)
            if P is None or L <= 1e-6:
                return None
            shift = ((u - P[0]) * (x2 - x1) + (v - P[1]) * (y2 - y1)) / L
            return shift - pt_line_base_shift(ent) + PT_LINE_DEFAULT_OFFSET
        if other is None or len(dim.pts) != 2:
            return None
        A, B = point_of(ent, dim.pts[0]), point_of(other, dim.pts[1])
        if not (A and B):
            return None
        if t == "HORIZ_DIST":
            return v - max(A[1], B[1])
        if t == "VERT_DIST":
            return u - max(A[0], B[0])
        L = math.hypot(B[0] - A[0], B[1] - A[1])
        if L <= 1e-6:
            return None
        return ((u - A[0]) * -(B[1] - A[1]) + (v - A[1]) * (B[0] - A[0])) / L
    return None


DIM_KINDS = {
    "LENGTH": "Length of a line", "DIAMETER": "Diameter", "RADIUS": "Radius", "ANGLE": "Angle between two lines",
    "DISTANCE": "Distance between two points", "HORIZ_DIST": "Horizontal distance", "VERT_DIST": "Vertical distance",
    "PT_LINE_DIST": "Distance from a point to a line", "RECT_WIDTH": "Rectangle width", "RECT_HEIGHT": "Rectangle height",
}


def describe_dimension(dim) -> str:
    """Hover text for a dimension badge: what it measures, its value (and formula) and what you can do with it."""
    unit = "°" if dim.dim_type == "ANGLE" else " mm"
    kind = DIM_KINDS.get(dim.dim_type, dim.dim_type.replace("_", " ").capitalize())
    title = f"{dim.dim_id}: {dim.name}" if dim.name and dim.name != dim.dim_id else dim.dim_id
    lines = [title, f"{kind}: {dim.value:g}{unit}"]
    if dim.expr:
        lines.append(f"Formula: {dim.expr}")
    lines.append("Double-click to change it, drag to move it.")
    return "\n".join(lines)
