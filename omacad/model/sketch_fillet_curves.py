"""Sketch fillet where a line meets an arc, or two arcs meet. The fillet circle touches both, so its centre lies on
each curve offset by the radius toward the inside of the corner: a parallel line for a line, a concentric circle
(R + r or R - r) for an arc. Two lines keep their own bisector construction in Sketch.fillet_corner."""

import math
from typing import Optional, Tuple
import numpy as np
from omacad.model.sketch_entities import SketchArc, SketchLine

TAU = 2.0 * math.pi
REACH = 0.995      # the fillet may use this much of a side, as for two lines


def ends(ent):
    """The (name, point) of each end of a line or an arc."""
    if isinstance(ent, SketchLine):
        return (("p1", ent.p1), ("p2", ent.p2))
    if isinstance(ent, SketchArc):
        return (("p_start", ent.p_start), ("p_end", ent.p_end))
    return ()


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else None


def _side(ent, end, V):
    """How the entity leaves the corner V at `end`: tangent into it, and for an arc its circle, the turning sense s
    (+1 counter-clockwise from V toward the far end) and the angle it covers from V; for a line its length from V."""
    far = np.array(next(p for name, p in ends(ent) if name != end), dtype=float)
    if isinstance(ent, SketchLine):
        t = _unit(far - V)
        return None if t is None else {"t": t, "reach": float(np.linalg.norm(far - V))}
    params = ent.get_circle_params()
    if not params:
        return None
    C, R, _a1, _a3, ccw = params
    C = np.array(C, dtype=float)
    s = 1.0 if (end == "p_start") == ccw else -1.0
    rho = _unit(V - C)
    if rho is None:
        return None
    aV = math.atan2(rho[1], rho[0])
    aF = math.atan2(far[1] - C[1], far[0] - C[0])
    return {"t": s * np.array([-rho[1], rho[0]]), "C": C, "R": R, "s": s, "aV": aV, "sweep": (s * (aF - aV)) % TAU}


def end_tangent(ent, end, V) -> Optional[np.ndarray]:
    """Unit direction in which the entity leaves V at `end` (None if it cannot tell)."""
    side = _side(ent, end, np.array(V, dtype=float))
    return None if side is None else side["t"]


def _curve(side, V, n, r):
    """The side's curve offset by r toward n: ("line", n, c) for dot(p, n) = c, or ("circle", C, radius)."""
    if "C" not in side:
        return ("line", n, float(np.dot(V, n)) + r)
    out = float(np.dot(n, V - side["C"])) > 0
    return ("circle", side["C"], side["R"] + r if out else side["R"] - r)


def _intersect(c1, c2):
    if c1[0] == "circle" and c2[0] == "line":
        c1, c2 = c2, c1
    if c1[0] == "line" and c2[0] == "circle":
        _, n, c = c1
        _, C, rad = c2
        d = c - float(np.dot(C, n))
        if rad <= 0 or abs(d) > rad:
            return []
        foot, h, along = C + d * n, math.sqrt(max(rad * rad - d * d, 0.0)), np.array([-n[1], n[0]])
        return [foot + h * along, foot - h * along]
    if c1[0] == "circle" and c2[0] == "circle":
        (_, C1, r1), (_, C2, r2) = c1, c2
        dist = float(np.linalg.norm(C2 - C1))
        if r1 <= 0 or r2 <= 0 or dist < 1e-12 or dist > r1 + r2 or dist < abs(r1 - r2):
            return []
        a = (r1 * r1 - r2 * r2 + dist * dist) / (2 * dist)
        h = math.sqrt(max(r1 * r1 - a * a, 0.0))
        u = (C2 - C1) / dist
        foot, along = C1 + a * u, np.array([-u[1], u[0]])
        return [foot + h * along, foot - h * along]
    return []


def _touch(side, V, O):
    """Where the fillet circle centred at O touches the side, and whether that is on the side's own piece."""
    if "C" not in side:
        along = float(np.dot(O - V, side["t"]))
        return V + along * side["t"], 1e-9 < along < REACH * side["reach"]
    T = side["C"] + side["R"] * _unit(O - side["C"])
    travel = (side["s"] * (math.atan2(T[1] - side["C"][1], T[0] - side["C"][0]) - side["aV"])) % TAU
    return T, 1e-9 < travel < REACH * side["sweep"]


def corner_point(ent_a, end_a, ent_b, end_b, near) -> Optional[Tuple[float, float]]:
    """Where the two curves (carried on) meet, nearest `near`: the sharp corner a fillet between them rounds."""
    near = np.array(near, dtype=float)
    curves = []
    for ent, end in ((ent_a, end_a), (ent_b, end_b)):
        side = _side(ent, end, near)
        if side is None:
            return None
        n = np.array([-side["t"][1], side["t"][0]])
        curves.append(("line", n, float(np.dot(near, n))) if "C" not in side else ("circle", side["C"], side["R"]))
    hits = _intersect(*curves)
    if not hits:
        return None
    best = min(hits, key=lambda p: float(np.linalg.norm(p - near)))
    return float(best[0]), float(best[1])


def fillet_points(ent_a, end_a, ent_b, end_b, V, radius: float):
    """(Ta, M, Tb) of the fillet arc touching ent_a at Ta and ent_b at Tb, or (None, reason)."""
    V = np.array(V, dtype=float)
    sa, sb = _side(ent_a, end_a, V), _side(ent_b, end_b, V)
    if sa is None or sb is None:
        return None, "One of the elements is too short."
    if abs(float(np.dot(sa["t"], sb["t"]))) > 0.9999:
        return None, "The elements already meet tangentially."
    curves = []
    for me, other in ((sa, sb), (sb, sa)):
        n = np.array([-me["t"][1], me["t"][0]])
        if float(np.dot(n, other["t"])) < 0:
            n = -n
        curves.append(_curve(me, V, n, radius))
    best = None
    for O in _intersect(*curves):
        (Ta, ok_a), (Tb, ok_b) = _touch(sa, V, O), _touch(sb, V, O)
        if ok_a and ok_b and (best is None or np.linalg.norm(O - V) < np.linalg.norm(best[0] - V)):
            best = (O, Ta, Tb)
    if best is None:
        return None, "The radius is too large for this corner."
    O, Ta, Tb = best
    M = O + radius * _unit((Ta + Tb) / 2 - O)
    return tuple(tuple(float(x) for x in p) for p in (Ta, M, Tb)), "OK"


def trim_end(ent, end: str, T) -> None:
    """Moves the entity's `end` to T; an arc keeps its circle and turning sense (its middle point follows)."""
    T = (float(T[0]), float(T[1]))
    if not isinstance(ent, SketchArc):
        setattr(ent, end, T)
        return
    (cx, cy), R, _a1, _a3, ccw = ent.get_circle_params()
    setattr(ent, end, T)
    a_s = math.atan2(ent.p_start[1] - cy, ent.p_start[0] - cx)
    a_e = math.atan2(ent.p_end[1] - cy, ent.p_end[0] - cx)
    sweep = ((a_e - a_s) if ccw else (a_s - a_e)) % TAU
    m = a_s + (sweep if ccw else -sweep) / 2
    ent.p_mid = (cx + R * math.cos(m), cy + R * math.sin(m))
