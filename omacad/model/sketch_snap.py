"""
Omacad - 2D Sketch Snapping Engine
Calculates intelligent snapping against Origin, Endpoints, Midpoints,
Orthogonal (H/V) axes, and Grid increments.
"""

import math
from dataclasses import dataclass
from typing import Tuple, Optional, List
import numpy as np
from omacad.model.sketch import Sketch, SketchLine, SketchRect, SketchCircle, SketchArc, SketchSpline


Segment = Tuple[Tuple[float, float], Tuple[float, float]]


def _closest_on_segment(pt, p1, p2):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return p1
    t = max(0.0, min(1.0, ((pt[0] - p1[0]) * dx + (pt[1] - p1[1]) * dy) / L2))
    return (p1[0] + t * dx, p1[1] + t * dy)


@dataclass
class SnapResult:
    """Holds information about the snapped 2D coordinate and its type."""
    uv: Tuple[float, float]
    snap_type: str  # "NONE", "ORIGIN", "ENDPOINT", "MIDPOINT", "EDGE", "ORTHO_H", "ORTHO_V", "GRID", "TANGENT"
    target_uv: Optional[Tuple[float, float]] = None
    guide_line: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None
    label: str = ""   # ANGLE snaps: the angle shown next to the cursor ("45°", "90°")


class SketchSnapper:
    """Finds the best magnetic snap point for a given 2D cursor coordinate."""

    @staticmethod
    def snap(
        raw_uv: Tuple[float, float],
        sketch: Optional[Sketch],
        start_uv: Optional[Tuple[float, float]] = None,
        snap_distance: float = 4.0,  # mm tolerance
        grid_step: float = 5.0,      # mm grid step
        enable_grid_snap: bool = True,
        enable_geom_snap: bool = True,
        reference_segments=None,  # np.ndarray (N, 2, 2) of projected body edges
    ) -> SnapResult:
        ru, rv = raw_uv

        if not enable_geom_snap and not enable_grid_snap:
            return SnapResult(uv=(ru, rv), snap_type="NONE")

        # 1. Highest Priority: Origin (0, 0)
        if enable_geom_snap:
            dist_origin = math.hypot(ru, rv)
            if dist_origin <= snap_distance:
                return SnapResult(uv=(0.0, 0.0), snap_type="ORIGIN", target_uv=(0.0, 0.0))

        # 2. Geometry Endpoints & Centers
        if enable_geom_snap and sketch:
            endpoints: List[Tuple[float, float]] = []
            midpoints: List[Tuple[float, float]] = []

            for ent in sketch.entities:
                if isinstance(ent, SketchLine):
                    endpoints.append(ent.p1)
                    endpoints.append(ent.p2)
                    midpoints.append(((ent.p1[0] + ent.p2[0]) * 0.5, (ent.p1[1] + ent.p2[1]) * 0.5))
                elif isinstance(ent, SketchRect):
                    x1, y1 = ent.p1
                    x2, y2 = ent.p2
                    endpoints.extend([
                        (min(x1, x2), min(y1, y2)),
                        (max(x1, x2), min(y1, y2)),
                        (max(x1, x2), max(y1, y2)),
                        (min(x1, x2), max(y1, y2))
                    ])
                    # midpoints of rectangle edges
                    midpoints.extend([
                        ((x1 + x2) * 0.5, min(y1, y2)),
                        ((x1 + x2) * 0.5, max(y1, y2)),
                        (min(x1, x2), (y1 + y2) * 0.5),
                        (max(x1, x2), (y1 + y2) * 0.5),
                    ])
                elif isinstance(ent, SketchCircle):
                    endpoints.append(ent.center)
                elif isinstance(ent, SketchArc):
                    endpoints.append(ent.p_start)
                    endpoints.append(ent.p_end)
                    midpoints.append(ent.p_mid)
                elif isinstance(ent, SketchSpline) and ent.points:
                    endpoints.extend((ent.points[0], ent.points[-1]))

            # Edges of the surrounding geometry (face boundary, other bodies' edges in this plane)
            ref = reference_segments
            if ref is not None and len(ref):
                q = np.array([ru, rv])
                A, B = ref[:, 0], ref[:, 1]
                for pts, dest in ((np.concatenate([A, B]), endpoints), ((A + B) * 0.5, midpoints)):
                    dd = np.hypot(*(pts - q).T)
                    i = int(dd.argmin())
                    if dd[i] <= snap_distance:
                        dest.append((float(pts[i, 0]), float(pts[i, 1])))

            # Check Endpoints
            best_ep = None
            min_ep_dist = snap_distance
            for ep in endpoints:
                d = math.hypot(ru - ep[0], rv - ep[1])
                if d <= min_ep_dist:
                    min_ep_dist = d
                    best_ep = ep

            if best_ep is not None:
                return SnapResult(uv=best_ep, snap_type="ENDPOINT", target_uv=best_ep)

            # Check Midpoints
            best_mp = None
            min_mp_dist = snap_distance
            for mp in midpoints:
                d = math.hypot(ru - mp[0], rv - mp[1])
                if d <= min_mp_dist:
                    min_mp_dist = d
                    best_mp = mp

            if best_mp is not None:
                return SnapResult(uv=best_mp, snap_type="MIDPOINT", target_uv=best_mp)

        # 2b. Anywhere along an edge (reference edges and the sketch's own lines)
        if enable_geom_snap:
            edge_segs: List[Segment] = []
            if sketch:
                for ent in sketch.entities:
                    edge_segs.extend(ent.to_lines())
            best_edge, best_d = None, snap_distance
            ref = reference_segments
            if ref is not None and len(ref):
                A, B = ref[:, 0], ref[:, 1]
                D = B - A
                L2 = (D * D).sum(axis=1)
                q = np.array([ru, rv])
                t = np.where(L2 > 1e-12, ((q - A) * D).sum(axis=1) / np.where(L2 > 1e-12, L2, 1.0), 0.0)
                P = A + np.clip(t, 0.0, 1.0)[:, None] * D
                dd = np.hypot(*(P - q).T)
                i = int(dd.argmin())
                if dd[i] <= best_d:
                    best_edge, best_d = (float(P[i, 0]), float(P[i, 1])), float(dd[i])
            for a, b in edge_segs:
                q = _closest_on_segment((ru, rv), a, b)
                d = math.hypot(ru - q[0], rv - q[1])
                if d <= best_d:
                    best_edge, best_d = q, d
            if best_edge is not None:
                return SnapResult(uv=best_edge, snap_type="EDGE", target_uv=best_edge)

        # 3. Orthogonal Alignment (Horizontal / Vertical against start point)
        if start_uv is not None:
            su, sv = start_uv
            # Check horizontal alignment (v == sv)
            if abs(rv - sv) <= snap_distance:
                guide = ((su - 500.0, sv), (su + 500.0, sv))
                u_coord = round(ru / grid_step) * grid_step if enable_grid_snap else ru
                return SnapResult(uv=(u_coord, sv), snap_type="ORTHO_H", target_uv=(su, sv), guide_line=guide)

            # Check vertical alignment (u == su)
            if abs(ru - su) <= snap_distance:
                guide = ((su, sv - 500.0), (su, sv + 500.0))
                v_coord = round(rv / grid_step) * grid_step if enable_grid_snap else rv
                return SnapResult(uv=(su, v_coord), snap_type="ORTHO_V", target_uv=(su, sv), guide_line=guide)

            # 45° diagonals, and 90°/45° to the line that ends where this one starts (Björn #98)
            dirs = [((1.0, 1.0), "45°"), ((1.0, -1.0), "45°")]
            prev = next((e for e in reversed(sketch.entities) if getattr(e, "entity_type", "") == "line"
                         and math.hypot(e.p2[0] - su, e.p2[1] - sv) < 1e-6), None) if sketch else None
            if prev is not None:
                pu, pv = prev.p2[0] - prev.p1[0], prev.p2[1] - prev.p1[1]
                dirs += [((-pv, pu), "90°"), ((pu - pv, pv + pu), "45°"), ((pu + pv, pv - pu), "45°")]
            best = None
            for (du, dv), label in dirs:
                n = math.hypot(du, dv)
                if n < 1e-9:
                    continue
                du, dv = du / n, dv / n
                t = (ru - su) * du + (rv - sv) * dv
                d = abs((ru - su) * dv - (rv - sv) * du)
                if d <= snap_distance and abs(t) > snap_distance and (best is None or d < best[0]):
                    best = (d, du, dv, t, label)
            if best is not None:
                _, du, dv, t, label = best
                guide = ((su - 500.0 * du, sv - 500.0 * dv), (su + 500.0 * du, sv + 500.0 * dv))
                return SnapResult(uv=(su + t * du, sv + t * dv), snap_type="ANGLE", target_uv=(su, sv),
                                  guide_line=guide, label=label)

        # 4. Grid Snapping
        if enable_grid_snap and grid_step > 0:
            gu = round(ru / grid_step) * grid_step
            gv = round(rv / grid_step) * grid_step
            return SnapResult(uv=(gu, gv), snap_type="GRID")

        # 5. Free movement
        return SnapResult(uv=(ru, rv), snap_type="NONE")
