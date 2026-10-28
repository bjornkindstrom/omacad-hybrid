"""
Omacad - Thread Feature
Parametric 3D-printable helical thread feature.
"""

from typing import Dict, Any, Optional
import math
import numpy as np
import manifold3d as m3d
from omacad.model import quality
from omacad.model.kernel import CadKernel
from omacad.model.features.base import Feature, Body, combine_with_bodies


class ThreadFeature(Feature):
    """Parametric helical thread feature optimized for 3D printing or standard CAD."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        diameter: float,
        pitch: float,
        length: float,
        is_female: bool = False,
        clearance: float = 0.0,
        profile: str = "trapezoidal_45",
        taper_lead_in: bool = True,
        taper_turns: float = 0.75,
        target_body_id: Optional[str] = None,
        operation: str = "new_body",  # "new_body", "join", "cut"
        plane_origin: Any = None,
        plane_normal: Any = None,
        plane_u: Any = None,
        plane_v: Any = None,
        anchor: str = "bottom",
        anchor_gap: float = 0.0,
        host_length: Optional[float] = None,
        grow: float = 0.0,
        follow_host: bool = False,
        host_offset: float = 0.0,
    ):
        super().__init__(feature_id, "thread", name)
        # Where along a cylinder the thread sits: `anchor` "bottom"/"top" is the end it starts from, `anchor_gap` the
        # distance kept free at that end and `host_length` the cylinder's length (None: attached to a plain face).
        self.anchor = "top" if anchor == "top" else "bottom"
        self.anchor_gap = float(anchor_gap)
        self.host_length = float(host_length) if host_length is not None else None
        self.grow = float(grow)       # profile offset in mm (set by Offset Face on a thread surface)
        # follow_host: the thread's diameter is the diameter of the cylinder it sits on (as it is when this step runs,
        # so an earlier Offset Face on the cylinder carries the thread along) plus host_offset (e.g. -0.01 clearance)
        self.follow_host = bool(follow_host)
        self.host_offset = float(host_offset)
        self._effective = None        # the diameter used the last time this step ran
        self.diameter = float(diameter)
        self.pitch = float(pitch)
        self.length = float(length)
        self.is_female = bool(is_female)
        self.clearance = float(clearance)
        self.profile = str(profile)
        self.taper_lead_in = bool(taper_lead_in)
        self.taper_turns = float(taper_turns)
        self.target_body_id = str(target_body_id) if target_body_id else None
        self.operation = str(operation)
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.plane_u = [float(x) for x in plane_u] if plane_u is not None else None
        self.plane_v = [float(x) for x in plane_v] if plane_v is not None else None

    @property
    def used_diameter(self) -> float:
        """The diameter the thread was built with the last time it ran (the typed one when it does not follow)."""
        return self._effective if (self.follow_host and self._effective is not None) else self.diameter

    def measure_host(self, manifold) -> Optional[float]:
        """Diameter of the cylinder this thread sits on or in, measured on `manifold` (the target body as it is when
        this step runs) halfway along the threaded length. Male: the outer wall around the axis; female: the hole."""
        mat = self.placement()
        if mat is None:
            return None
        full = np.vstack([mat, [0.0, 0.0, 0.0, 1.0]])
        local = manifold.transform(np.linalg.inv(full)[:3])
        try:
            loops = local.slice(self.start_z() + 0.5 * self.length).to_polygons()
        except Exception:
            return None
        best = None
        for loop in loops:
            pts = np.asarray(loop, dtype=float)
            if len(pts) < 8:
                continue
            lo, hi = pts.min(axis=0), pts.max(axis=0)
            if not (lo[0] <= 0.0 <= hi[0] and lo[1] <= 0.0 <= hi[1]):          # must surround the axis
                continue
            area = 0.5 * abs(float(np.dot(pts[:, 0], np.roll(pts[:, 1], 1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], 1))))
            if best is None or (area < best[0] if self.is_female else area > best[0]):
                best = (area, float(np.linalg.norm(pts, axis=1).mean()))
        return None if best is None else 2.0 * best[1]

    def start_z(self) -> float:
        """The thread's start along its own axis: placement() already includes start_offset, so 0."""
        return 0.0

    def start_offset(self) -> float:
        """Distance from the stored plane origin (the cylinder's bottom) to where the thread starts, along its axis."""
        if self.host_length is None:
            return 0.0
        if self.anchor == "top":
            return max(0.0, self.host_length - self.length - self.anchor_gap)
        return self.anchor_gap

    def surface_sign(self, point, normal, shifts, tol: float = 0.01):
        """(+1 / -1, shift) when the picked surface point lies on this thread's coil, moved by `shift`, and the surface
        faces the same way as / against the coil's own outward normal (the picked body is the coil's own material /
        the body the coil was cut from); (0, None) when it is not on the coil. `shifts` are the places the body may
        have been moved to since (translations only)."""
        mesh = self.build_solid().to_mesh()
        v = np.asarray(mesh.vert_properties, dtype=float)[:, :3]
        t = np.asarray(mesh.tri_verts)
        a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
        cross = np.cross(b - a, c - a)
        area2 = np.linalg.norm(cross, axis=1)
        n_tri = cross / np.where(area2 > 1e-12, area2, 1.0)[:, None]
        reach = float(np.max(np.linalg.norm(b - a, axis=1))) * 1.5 + tol
        centroid = (a + b + c) / 3.0
        n = np.asarray(normal, dtype=float)
        for shift in shifts:
            p = np.asarray(point, dtype=float) - np.asarray(shift, dtype=float)
            for i in np.where(np.linalg.norm(centroid - p, axis=1) < reach)[0]:
                # the point lies in this triangle (to within tol) when its distance to the plane is small and the
                # barycentric coordinates are inside
                d = float(n_tri[i] @ (p - a[i]))
                if abs(d) > tol or abs(float(n_tri[i] @ n)) < 0.8 or area2[i] < 1e-12:
                    continue
                q = p - d * n_tri[i]
                w = [float(np.cross(e1 - e0, q - e0) @ n_tri[i]) / area2[i]
                     for e0, e1 in ((a[i], b[i]), (b[i], c[i]), (c[i], a[i]))]
                if min(w) >= -tol:
                    return (1 if n_tri[i] @ n > 0 else -1), shift
        return 0, None

    def cylinder_sign(self, ref, shifts):
        """For a picked cylinder face (the wall between the turns, a bore or pin carrying this thread): (+1 / -1, shift)
        when it is coaxial with the thread, about the thread's diameter and inside its length (+1: a pin, the coil
        belongs to its material; -1: a hole the coil was cut from); (0, None) otherwise."""
        if self.plane_origin is None or self.plane_normal is None:
            return 0, None
        n = np.asarray(self.plane_normal, dtype=float)
        n = n / max(float(np.linalg.norm(n)), 1e-12)
        a = np.asarray(ref["axis"], dtype=float)
        a = a / max(float(np.linalg.norm(a)), 1e-12)
        if np.linalg.norm(np.cross(a, n)) > 0.01 or abs(float(ref["radius"]) - 0.5 * self.used_diameter) > 0.6 * self.pitch:
            return 0, None
        start = np.asarray(self.plane_origin, dtype=float) + n * self.start_offset()
        for shift in shifts:
            d = np.asarray(ref["origin"], dtype=float) - np.asarray(shift, dtype=float) - start
            along = float(d @ n)
            if np.linalg.norm(d - along * n) < 0.05 and -0.5 * self.pitch <= along <= self.length + 0.5 * self.pitch:
                return (-1 if ref.get("internal") else 1), shift
        return 0, None

    def placement(self) -> Optional[np.ndarray]:
        """3x4 matrix from the thread's own frame (axis = +Z from where it starts) to the world; None: at the origin."""
        if self.plane_origin is None or self.plane_normal is None:
            return None
        n = np.array(self.plane_normal, dtype=float)
        n_len = float(np.linalg.norm(n))
        if n_len <= 1e-12:
            return None
        n = n / n_len
        if self.plane_u is not None and self.plane_v is not None:
            u = np.array(self.plane_u, dtype=float)
            u = u / max(float(np.linalg.norm(u)), 1e-12)
            v = np.array(self.plane_v, dtype=float)
            v = v / max(float(np.linalg.norm(v)), 1e-12)
        else:
            hint = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            u = hint - np.dot(hint, n) * n
            u /= np.linalg.norm(u)
            v = np.cross(n, u)
        origin = np.array(self.plane_origin, dtype=float) + n * self.start_offset()
        return np.column_stack([u, v, n, origin]).astype(float)

    def build_solid(self, grow: Optional[float] = None, diameter: Optional[float] = None,
                    lead: float = 0.0) -> m3d.Manifold:
        """The thread solid; `lead` > 0 starts it that much earlier (whole turns keep the coil where it was), untapered,
        so a mating part cut with it gets a channel the coil can screw out through."""
        include_core = (self.operation == "new_body" or not self.target_body_id) and not self.is_female
        attached = bool(self.target_body_id and self.operation == "join" and not self.is_female)
        solid = CadKernel.create_thread(
            diameter=self.used_diameter if diameter is None else diameter,
            pitch=self.pitch,
            length=self.length + lead,
            is_female=self.is_female,
            clearance=self.clearance,
            profile=self.profile,
            taper_lead_in=self.taper_lead_in and lead <= 0.0,
            taper_turns=self.taper_turns,
            include_core=include_core,
            attached_to_cylinder=attached,
            grow=self.grow if grow is None else grow,
        )
        if lead > 0.0:
            solid = solid.translate([0.0, 0.0, -lead])
        mat = self.placement()
        return solid if mat is None else solid.transform(mat)

    def zone(self, extra: float, channel: bool = False) -> m3d.Manifold:
        """The threaded region (coil + the cylinder it sits on or in) grown by `extra` on every side, radially; used
        by Offset Face to give one body clearance against the other without touching the Thread step. `channel`: the
        coil runs one turn further back and is not tapered, so a part cut with it (a lid cut from a jar) has a full
        groove out through its mouth; a groove copied from the tapered or ending coil is too shallow there and the
        coil's full tooth jams in it while screwing."""
        r = 0.5 * self.used_diameter + extra
        core = m3d.Manifold.cylinder(self.length, r, r, circular_segments=quality.circle_segments())
        mat = self.placement()
        core = core if mat is None else core.transform(mat)
        return self.build_solid(grow=self.grow + extra, lead=self.pitch if channel else 0.0) + core

    def execute(self, doc: Any) -> None:
        self._effective = None
        if self.follow_host and self.target_body_id in doc.bodies and self.operation in ("join", "cut"):
            host = self.measure_host(doc.bodies[self.target_body_id].manifold)
            if host is not None:
                self._effective = host + self.host_offset
        tool = self.build_solid()

        if self.target_body_id and self.target_body_id in doc.bodies:
            target = doc.bodies[self.target_body_id]
            if self.operation == "cut" or self.is_female:
                target.manifold = target.manifold - tool
            elif self.operation == "join":
                target.manifold = target.manifold + tool
            else:
                body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=tool)
                body.update_render_mesh()
                doc.bodies[body.body_id] = body
                return
            target.update_render_mesh()
        else:
            body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=tool)
            body.update_render_mesh()
            doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": "thread",
            "name": self.name,
            "suppressed": self.suppressed,
            "exprs": dict(self.exprs),
            "diameter": self.diameter,
            "pitch": self.pitch,
            "length": self.length,
            "is_female": self.is_female,
            "clearance": self.clearance,
            "profile": self.profile,
            "taper_lead_in": self.taper_lead_in,
            "taper_turns": self.taper_turns,
            "target_body_id": self.target_body_id,
            "operation": self.operation,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "plane_u": self.plane_u,
            "plane_v": self.plane_v,
            "anchor": self.anchor,
            "anchor_gap": self.anchor_gap,
            "host_length": self.host_length,
            "grow": self.grow,
            "follow_host": self.follow_host,
            "host_offset": self.host_offset,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThreadFeature":
        feat = cls(
            feature_id=data["feature_id"],
            name=data.get("name", "Thread"),
            diameter=data["diameter"],
            pitch=data["pitch"],
            length=data["length"],
            is_female=data.get("is_female", False),
            clearance=data.get("clearance", 0.25),
            profile=data.get("profile", "trapezoidal_45"),
            taper_lead_in=data.get("taper_lead_in", True),
            taper_turns=data.get("taper_turns", 0.75),
            target_body_id=data.get("target_body_id"),
            operation=data.get("operation", "new_body"),
            plane_origin=data.get("plane_origin"),
            plane_normal=data.get("plane_normal"),
            plane_u=data.get("plane_u"),
            plane_v=data.get("plane_v"),
            anchor=data.get("anchor", "bottom"),
            anchor_gap=data.get("anchor_gap", 0.0),
            host_length=data.get("host_length"),
            grow=data.get("grow", 0.0),
            follow_host=data.get("follow_host", False),
            host_offset=data.get("host_offset", 0.0),
        )
        feat.suppressed = bool(data.get("suppressed", False))
        feat.exprs = dict(data.get("exprs") or {})
        return feat

