"""
Omacad - Dynamic dimension input while sketching (Fusion-style Tab entry).

Pure logic, no Qt: holds the typed fields for the active tool and resolves the
final end point from the (snapped) mouse position plus any locked values.
"""

import math

from omacad.model import expr
from typing import Dict, List, Optional, Tuple

UV = Tuple[float, float]

FIELDS: Dict[str, List[str]] = {
    "LINE": ["Length", "Angle"],
    "RECT": ["Width", "Height"],
    "ROUNDED_RECT": ["Width", "Height", "Radius"],
    "CENTER_RECT": ["Width", "Height"],
    "CENTER_ROUNDED_RECT": ["Width", "Height", "Radius"],
    "CIRCLE": ["Diameter"],
    "POLYGON": ["Side", "Sides"],
    "MOVE": ["X", "Y"],
}

def supports(tool: str) -> bool:
    return tool in FIELDS


class DynInput:
    def __init__(self):
        self.reset()

    def reset(self):
        self.editing = False  # True once Tab was pressed or a character typed: letters then belong to the field
        self.tool: Optional[str] = None
        self.names: List[str] = []
        self.texts: List[str] = []
        self.focus: int = -1
        self.default_sides: int = getattr(self, "default_sides", 6)   # set by the view from its Sides spinner
        self.default_radius: float = getattr(self, "default_radius", 3.0)   # corner radius of the rounded rectangles

    @property
    def active(self) -> bool:
        return self.tool is not None

    def start(self, tool: str) -> bool:
        if not supports(tool):
            return False
        if self.tool != tool:
            self.tool = tool
            self.names = list(FIELDS[tool])
            self.texts = [""] * len(self.names)
            self.focus = -1
        return True

    def tab(self, backwards: bool = False):
        if not self.active:
            return
        n = len(self.names)
        if self.focus < 0:
            self.focus = n - 1 if backwards else 0
        else:
            self.focus = (self.focus + (-1 if backwards else 1)) % n

    def type_char(self, ch: str):
        if not self.active:
            return
        if self.focus < 0:
            self.focus = 0
        self.texts[self.focus] += ch

    def backspace(self):
        if self.active and self.focus >= 0:
            self.texts[self.focus] = self.texts[self.focus][:-1]

    def locked(self, i: int) -> Optional[float]:
        """Typed value of field i, or None if empty/unparseable (follows the mouse)."""
        try:
            return expr.evaluate(self.texts[i])  # plain numbers and formulas such as 10-1 or 2x(3+5)
        except (ValueError, IndexError):
            return None

    def invalid(self, i: int) -> bool:
        """Text typed into field i that is not (yet) a valid number or formula."""
        return i >= 0 and bool(self.texts[i].strip()) and self.locked(i) is None

    def locked_values(self) -> Dict[str, float]:
        out = {}
        for i, name in enumerate(self.names):
            v = self.locked(i)
            if v is not None:
                out[name] = v
        return out

    def resolve(self, start: UV, mouse: UV) -> Tuple[UV, Dict[str, float]]:
        """Returns (end_uv, live_values) combining the mouse with locked fields."""
        lk = self.locked_values()
        u1, v1 = start
        dx, dy = mouse[0] - u1, mouse[1] - v1
        sx = -1.0 if dx < 0 else 1.0
        sy = -1.0 if dy < 0 else 1.0

        if self.tool == "LINE":
            length = lk.get("Length", math.hypot(dx, dy))
            ang = lk.get("Angle", math.degrees(math.atan2(dy, dx)))
            if "Length" in lk and "Angle" not in lk and math.hypot(dx, dy) > 1e-9:
                ang = math.degrees(math.atan2(dy, dx))
            a = math.radians(ang)
            end = (u1 + length * math.cos(a), v1 + length * math.sin(a))
            return end, {"Length": length, "Angle": ang}

        radius = {"Radius": abs(lk["Radius"]) if "Radius" in lk else self.default_radius} if "Radius" in self.names else {}

        if self.tool in ("RECT", "ROUNDED_RECT"):
            w = abs(lk["Width"]) if "Width" in lk else abs(dx)
            h = abs(lk["Height"]) if "Height" in lk else abs(dy)
            return (u1 + sx * w, v1 + sy * h), {"Width": w, "Height": h, **radius}

        if self.tool in ("CENTER_RECT", "CENTER_ROUNDED_RECT"):
            w = abs(lk["Width"]) if "Width" in lk else 2.0 * abs(dx)
            h = abs(lk["Height"]) if "Height" in lk else 2.0 * abs(dy)
            return (u1 + sx * w / 2.0, v1 + sy * h / 2.0), {"Width": w, "Height": h, **radius}

        if self.tool == "MOVE":
            mx = lk.get("X", dx)
            my = lk.get("Y", dy)
            return (u1 + mx, v1 + my), {"X": mx, "Y": my}

        if self.tool == "POLYGON":
            n = max(3, min(200, int(round(lk["Sides"])))) if "Sides" in lk else int(self.default_sides)
            dist = math.hypot(dx, dy)
            r = abs(lk["Side"]) / (2.0 * math.sin(math.pi / n)) if "Side" in lk else dist
            ux, uy = (dx / dist, dy / dist) if dist > 1e-9 else (1.0, 0.0)
            return (u1 + ux * r, v1 + uy * r), {"Side": 2.0 * r * math.sin(math.pi / n), "Sides": float(n)}

        if self.tool == "CIRCLE":
            dist = math.hypot(dx, dy)
            d = abs(lk["Diameter"]) if "Diameter" in lk else 2.0 * dist
            ux, uy = (dx / dist, dy / dist) if dist > 1e-9 else (1.0, 0.0)
            return (u1 + ux * d / 2.0, v1 + uy * d / 2.0), {"Diameter": d}

        return mouse, {}
