"""Smart Circle: place a circle with numbers and Enter.

Step 1 type the diameter, step 2 the distance from the centre to the nearest straight line (any angle: vertical,
horizontal or slanted), step 3 the distance to the nearest line that is not parallel to the first one. Distances are
measured at right angles from the centre. The mouse picks the line and the side; with nothing typed a step
just takes the mouse position. Pure logic, no Qt (the viewport draws it and creates the circle)."""
import math
from typing import List, Optional, Tuple

from omacad.model import expr

UV = Tuple[float, float]
# a guide line: (p1, p2, ref) where ref is a sketch line id or ("edge", p1, p2) for a face edge, so it can be dimensioned
Segment = Tuple[UV, UV, object]

SIZE, ACROSS, DOWN = 0, 1, 2
LABELS = {SIZE: "Diameter", ACROSS: "Distance to line 1", DOWN: "Distance to line 2"}
PARALLEL_TOL = 0.02   # |sin| of the angle below which two lines count as parallel


def _seg_distance(p: UV, a: UV, b: UV) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def line_normal(seg: Segment) -> UV:
    """Unit normal of the line through the segment (pointing to its left)."""
    (ax, ay), (bx, by), _ = seg
    length = math.hypot(bx - ax, by - ay) or 1.0
    return (-(by - ay) / length, (bx - ax) / length)


def signed_distance(seg: Segment, p: UV) -> float:
    """Right-angle distance from p to the (infinite) line through seg; positive on the normal's side."""
    n, a = line_normal(seg), seg[0]
    return n[0] * (p[0] - a[0]) + n[1] * (p[1] - a[1])


def foot_on_line(seg: Segment, p: UV) -> UV:
    """The point of the line through seg nearest to p (where a right-angle measure from p lands)."""
    n, d = line_normal(seg), signed_distance(seg, p)
    return (p[0] - n[0] * d, p[1] - n[1] * d)


def nearest_line(segments: List[Segment], p: UV, not_parallel_to: Optional[UV] = None) -> Optional[Segment]:
    """The straight line (any angle) closest to p, optionally skipping lines parallel to the normal `not_parallel_to`."""
    best, best_d = None, 1e18
    for seg in segments:
        a, b, _ = seg
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-6:
            continue
        if not_parallel_to is not None:
            n = line_normal(seg)
            if abs(n[0] * not_parallel_to[1] - n[1] * not_parallel_to[0]) < PARALLEL_TOL:
                continue
        d = _seg_distance(p, a, b)
        if d < best_d:
            best, best_d = seg, d
    return best


def nearest_axis_line(segments: List[Segment], p: UV, vertical: bool) -> Optional[Segment]:
    """The vertical (or horizontal) straight line closest to p, or None."""
    best, best_d = None, 1e18
    for seg in segments:
        a, b, _ = seg
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1e-6:
            continue
        along, across = (abs(b[1] - a[1]), abs(b[0] - a[0])) if vertical else (abs(b[0] - a[0]), abs(b[1] - a[1]))
        if across > 1e-3 * length + 1e-9 or along < 0.99 * length:
            continue
        d = _seg_distance(p, a, b)
        if d < best_d:
            best, best_d = seg, d
    return best


class SmartCircle:
    def __init__(self):
        self.segments: List[Segment] = []
        self.reset()

    def reset(self):
        self.stage = SIZE
        self.text = ""
        self.mouse: Optional[UV] = None
        self.diameter: Optional[float] = None
        self.dimension = {}          # stage -> (segment, typed distance), kept for the dimensions of the circle
        self.fixed = {}              # stage -> (unit normal, k): the centre lies on n . c = k, locked by Enter / click

    # ---- typing -------------------------------------------------------------------
    def typed(self) -> Optional[float]:
        try:
            return expr.evaluate(self.text)
        except ValueError:
            return None

    def invalid(self) -> bool:
        return bool(self.text.strip()) and self.typed() is None

    # ---- geometry -----------------------------------------------------------------
    def guide(self) -> Optional[Segment]:
        if self.stage == SIZE or self.mouse is None:
            return None
        if self.stage == ACROSS:
            return nearest_line(self.segments, self.mouse)
        first = self.fixed.get(ACROSS)
        return nearest_line(self.segments, self.mouse, not_parallel_to=first[0] if first else None)

    def _fallback_normal(self, stage: int) -> UV:
        """No line to measure from: the old behaviour, plain x (step 2) or y (step 3) of the cursor."""
        first = self.fixed.get(ACROSS)
        if stage == ACROSS or first is None or abs(first[0][1]) > PARALLEL_TOL:
            return (1.0, 0.0) if stage == ACROSS else (0.0, 1.0)
        return (1.0, 0.0)

    def _resolve(self, stage: int):
        """The line the centre must lie on for this step as it looks now: (unit normal, k with n . c = k)."""
        if self.mouse is None:
            return None
        d, g = self.typed(), self.guide() if stage == self.stage else None
        if d is None:        # nothing typed: the cursor decides
            if stage == DOWN and self.fixed.get(ACROSS) is not None:
                return None  # (second step) slide along the line the first step fixed
            n = self._fallback_normal(stage)
            return (n, n[0] * self.mouse[0] + n[1] * self.mouse[1])
        if g is None:
            n = self._fallback_normal(stage)
            return (n, n[0] * self.mouse[0] + n[1] * self.mouse[1])
        n = line_normal(g)
        side = 1.0 if signed_distance(g, self.mouse) >= 0 else -1.0
        return (n, n[0] * g[0][0] + n[1] * g[0][1] + side * d)

    def centre(self) -> Optional[UV]:
        if self.mouse is None:
            return None
        c1 = self.fixed.get(ACROSS) or (self._resolve(ACROSS) if self.stage == ACROSS else None)
        c2 = self.fixed.get(DOWN) or (self._resolve(DOWN) if self.stage == DOWN else None)
        mx, my = self.mouse
        if c1 is None:
            return (mx, my)
        (n1, k1) = c1
        if c2 is not None:
            (n2, k2) = c2
            det = n1[0] * n2[1] - n1[1] * n2[0]
            if abs(det) > 1e-9:
                return ((k1 * n2[1] - k2 * n1[1]) / det, (n1[0] * k2 - n2[0] * k1) / det)
        t = k1 - (n1[0] * mx + n1[1] * my)         # slide the cursor at right angles onto the first line
        return (mx + n1[0] * t, my + n1[1] * t)

    # ---- Enter / click ------------------------------------------------------------
    def accept(self) -> str:
        """Takes the current step. Returns "invalid", "need_size", "next" or "done"."""
        if self.invalid():
            return "invalid"
        if self.stage == SIZE:
            d = self.typed()
            if d is None or abs(d) < 1e-6:
                return "need_size"
            self.diameter = abs(d)
            self.stage, self.text = ACROSS, ""
            return "next"
        d, g = self.typed(), self.guide()
        if d is not None and g is None:
            return "no_line"
        locked = self._resolve(self.stage)
        if locked is None and self.stage == ACROSS:
            return "invalid"
        if locked is not None:
            self.fixed[self.stage] = locked
        if d is not None:
            self.dimension[self.stage] = (g, abs(d))
        if self.stage == ACROSS:
            self.stage, self.text = DOWN, ""
            return "next"
        return "done"

    def back(self) -> bool:
        """Backspace on an empty field: return to the previous step."""
        if self.text or self.stage == SIZE:
            return False
        self.stage -= 1
        self.fixed.pop(self.stage, None)
        self.dimension.pop(self.stage, None)
        if self.stage == SIZE:
            self.diameter = None
        return True
