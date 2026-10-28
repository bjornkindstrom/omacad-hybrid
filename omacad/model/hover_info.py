"""What the inspector shows while the mouse rests on a sketch element or a solid edge: (name, [(label, text)...])."""
import math
from typing import List, Optional, Tuple

import numpy as np

Info = Tuple[str, List[Tuple[str, str]]]


def _mm(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") + " mm"


def _deg(rad: float) -> str:
    return f"{math.degrees(rad):.2f}".rstrip("0").rstrip(".") + "°"


def describe_entity(ent) -> Optional[Info]:
    """Measures of a sketch element (line, circle, arc, rectangle); None for kinds without a simple size."""
    kind = getattr(ent, "entity_type", "")
    if kind == "line":
        du, dv = ent.p2[0] - ent.p1[0], ent.p2[1] - ent.p1[1]
        return "Line", [("Length", _mm(math.hypot(du, dv))), ("Angle", _deg(math.atan2(dv, du) % math.pi))]
    if kind == "circle":
        return "Circle", [("Radius", _mm(ent.radius)), ("Diameter", _mm(2 * ent.radius))]
    if kind == "arc":
        params = ent.get_circle_params()
        if params is None:
            return None
        _c, r, a0, a1, ccw = params
        sweep = (a1 - a0) % (2 * math.pi) if ccw else (a0 - a1) % (2 * math.pi)
        return "Arc", [("Radius", _mm(r)), ("Angle", _deg(sweep)), ("Length", _mm(r * sweep))]
    if kind == "rect":
        w, h = abs(ent.p2[0] - ent.p1[0]), abs(ent.p2[1] - ent.p1[1])
        return "Rectangle", [("Width", _mm(w)), ("Height", _mm(h))]
    return None


def describe_edge(edge) -> Optional[Info]:
    """Measures of a solid edge (straight, circle or arc, or a whole outline)."""
    kind = getattr(edge, "kind", "")
    if kind == "line":
        return "Edge", [("Length", _mm(edge.length))]
    if kind == "circle":
        r = float(edge.radius)
        if edge.is_arc:
            return "Arc edge", [("Radius", _mm(r)), ("Angle", _deg(edge.sweep)), ("Length", _mm(r * edge.sweep))]
        return "Circular edge", [("Radius", _mm(r)), ("Diameter", _mm(2 * r)), ("Length", _mm(2 * np.pi * r))]
    if kind in ("loop", "wrapped"):
        return "Outline", [("Length", _mm(edge.perimeter))]
    if kind == "curve":
        return "Curved edge", [("Length", _mm(edge.length))]
    return None
