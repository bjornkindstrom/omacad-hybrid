"""Shell feature: hollows out solid bodies."""

from typing import List, Dict, Any, Optional
import numpy as np
import manifold3d as m3d

from omacad.model.features.base import Feature
from omacad.model.kernel import CadKernel


class ShellFeature(Feature):
    """Hollows out a 3D solid body, optionally opening selected faces. direction: "inside" (wall grows inward by
    `thickness`), "outside" (wall grows outward by `thickness`) or "both" (`thickness` inward and `thickness2` outward)."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        thickness: float = 2.0,
        open_faces: Optional[List[Dict[str, Any]]] = None,
        direction: str = "inside",
        thickness2: float = 2.0,
    ):
        super().__init__(feature_id, "shell", name)
        self.target_body_id = target_body_id
        self.thickness = float(thickness)
        self.open_faces = open_faces
        self.direction = direction if direction in ("inside", "outside", "both") else "inside"
        self.thickness2 = float(thickness2)

    @property
    def open_faces(self) -> List[Dict[str, Any]]:
        return self._open_faces

    @open_faces.setter
    def open_faces(self, faces) -> None:
        # only the plain data: the dialog's picks carry the live "_face" object, which can't be saved
        self._open_faces = [{k: v for k, v in f.items() if not k.startswith("_")} for f in faces or []]

    def wall_sizes(self):
        """(inward, outward) wall thickness in mm."""
        if self.direction == "outside":
            return 0.0, self.thickness
        if self.direction == "both":
            return self.thickness, self.thickness2
        return self.thickness, 0.0

    @staticmethod
    def _facet_planes(m):
        """(unit normals, offsets) of a convex body's distinct facet planes, or None if it is not convex.
        Every facet counts, not merged faces: a cylinder's side facets are one curved face but many planes."""
        try:
            hull = m.hull()
        except Exception:
            return None
        if hull.is_empty() or abs(hull.volume() - m.volume()) >= 1e-6 * max(1.0, m.volume()):
            return None
        mesh = m.to_mesh()
        v = np.asarray(mesh.vert_properties, dtype=float)[:, :3][np.asarray(mesh.tri_verts)]
        n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        ln = np.linalg.norm(n, axis=1)
        ok = ln > (1e-3 * float(np.max(ln)) if len(ln) else 1e-12)
        n = n[ok] / ln[ok, None]
        d = np.einsum("ij,ij->i", n, v[ok, 0])
        _, keep = np.unique(np.round(np.column_stack((n, d)), 4), axis=0, return_index=True)
        return n[keep], d[keep]

    @classmethod
    def _grow(cls, m, t):
        """The body with every surface moved outward by t. Convex bodies keep sharp corners (facet planes moved
        out and intersected); anything else is grown with a ball, which rounds its outer edges."""
        planes = cls._facet_planes(m)
        if planes is not None:
            bb = np.array(m.bounding_box())
            size = float(np.max(bb[3:] - bb[:3])) + 4 * t + 10
            out = m3d.Manifold.cube((size, size, size), True).translate(tuple((bb[:3] + bb[3:]) / 2.0))
            for n, d in zip(*planes):
                out = out.trim_by_plane(tuple(-n), -(d + t))   # keeps the side where n.x <= d + t
            if not out.is_empty():
                return out
        return m.minkowski_sum(m3d.Manifold.sphere(t, 12))

    @classmethod
    def _shrink(cls, m, t):
        """Erodes the body inward by t. For convex bodies (cubes, prisms, cylinders) facet-plane trims are
        exact and 20-50x faster than a 3D Minkowski difference."""
        planes = cls._facet_planes(m)
        if planes is not None:
            cav = cls._trimmed(m, *planes, t)
            if not cav.is_empty() and cav.volume() > 1e-6:
                return cav
        return m.minkowski_difference(m3d.Manifold.sphere(t, 12))

    @staticmethod
    def _trimmed(m, normals, offsets, t):
        """`m` cut by every plane (normal n, offset d) moved inward by t."""
        for n, d in zip(normals, offsets):
            m = m.trim_by_plane(tuple(-n), -(d - t))
        return m

    @classmethod
    def _stacked_cavity(cls, base, added, t):
        """The exact cavity of a convex `base` with convex parts joined onto it (a cylinder stacked on a
        cylinder), or None if a part is not convex. Each piece is eroded by its own facet planes, and each joint
        by the planes of both pieces except the glued faces, so the cavity runs through the joint with sharp
        corners and the walls stay exactly t thick."""
        bn, bd = cls._facet_planes(base)
        pieces = [cls._trimmed(base, bn, bd, t)]
        for part in added.decompose():
            planes = cls._facet_planes(part)
            if planes is None:
                return None
            pn, pd = planes
            # glued: a base facet and a part facet on the same plane, facing each other
            glued = (np.abs(bn @ pn.T + 1.0) < 1e-6) & (np.abs(bd[:, None] + pd[None, :]) < 1e-4)
            keep_b, keep_p = ~glued.any(axis=1), ~glued.any(axis=0)
            pieces.append(cls._trimmed(part, pn, pd, t))
            pieces.append(cls._trimmed(base + part, np.vstack((bn[keep_b], pn[keep_p])),
                                       np.concatenate((bd[keep_b], pd[keep_p])), t))
        return m3d.Manifold.batch_boolean([p for p in pieces if not p.is_empty()], m3d.OpType.Add)

    EPS = 1e-3     # mm: how far off a face plane its region is sliced

    @staticmethod
    def _frame(n):
        """Rotation (rows u, v, n) that takes the unit normal n to +Z."""
        a = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = np.cross(a, n)
        u /= np.linalg.norm(u)
        return np.array([u, np.cross(n, u), n])

    @classmethod
    def _face_region(cls, body, face):
        """(rotation to the face frame, face plane height in it, the face's region there) for an open face, or None.
        The region is where the body ends at the plane (inside just under it, not just over it), only the
        connected part under the picked point: a ledge is an annulus, not the whole cross-section."""
        n = np.array(face.get("normal", [0, 0, 1]), dtype=float)
        ln = float(np.linalg.norm(n))
        if ln < 1e-6:
            return None
        R = cls._frame(n / ln)
        o = R @ np.array(face.get("origin", [0, 0, 0]), dtype=float)
        local = body.transform(np.column_stack((R, np.zeros(3))))
        region = local.slice(o[2] - cls.EPS) - local.slice(o[2] + cls.EPS)
        if region.is_empty():
            return None
        dot = m3d.CrossSection.square((2 * cls.EPS, 2 * cls.EPS), True).translate((o[0], o[1]))
        parts = [p for p in region.decompose() if not (p ^ dot).is_empty()]
        if parts:
            region = m3d.CrossSection.batch_boolean(parts, m3d.OpType.Add)
        return R, float(o[2]), region

    @staticmethod
    def _prism(R, region, z0, z1):
        """`region` (in the face frame R) extruded from height z0 to z1, back in world space."""
        prism = m3d.Manifold.extrude(region, z1 - z0).translate((0.0, 0.0, z0))
        return prism.transform(np.column_stack((R.T, np.zeros(3))))

    @classmethod
    def compute_shell(cls, body, thickness: float, direction: str = "inside", thickness2: float = 2.0,
                      open_faces: Optional[list] = None, cavity=None):
        """Hollows out a manifold body with wall thickness and optional open faces. Returns new Manifold or None.
        `cavity`: the body already eroded by the inside wall, when the caller knows it exactly."""
        if direction == "outside":
            t_in, t_out = 0.0, float(thickness)
        elif direction == "both":
            t_in, t_out = float(thickness), float(thickness2)
        else:
            t_in, t_out = float(thickness), 0.0

        if t_in <= 0.001 and t_out <= 0.001:
            return body

        # 1. The empty space: eroded by inside wall (or body itself for outside-only)
        if cavity is None and t_in > 0.001:
            try:
                cavity = cls._shrink(body, t_in)
            except Exception as e:
                print(f"ShellFeature shrink error: {e}")
                return None
            if cavity.is_empty() or cavity.volume() < 1e-6:
                return None
        cavity = body if cavity is None else cavity

        # 2. Outer skin: grown by outside wall
        outer = body
        if t_out > 0.001:
            try:
                outer = cls._grow(body, t_out)
            except Exception as e:
                print(f"ShellFeature grow error: {e}")
                return None

        # 3. Open faces: a prism through each picked face, as wide as the cavity just under it
        openings = []
        for f in open_faces or []:
            picked = cls._face_region(body, f)
            if picked is None:
                continue
            R, d, region = picked
            if t_out > 0.001:
                outer = outer - cls._prism(R, region.offset(t_out, m3d.JoinType.Miter), d, d + t_out + 1.0)
            under = cavity.transform(np.column_stack((R, np.zeros(3)))).slice(d - t_in - cls.EPS) ^ region
            if not under.is_empty():
                openings.append(cls._prism(R, under, d - t_in - 2 * cls.EPS, d + t_out + 1.0))
        sweep = m3d.Manifold.batch_boolean([cavity] + openings, m3d.OpType.Add) if openings else cavity

        # 4. Wall = outer skin minus empty space
        try:
            shelled = outer - sweep
            if not shelled.is_empty() and shelled.volume() > 1e-6:
                return shelled
        except Exception as e:
            print(f"ShellFeature boolean subtraction error: {e}")
        return None

    @classmethod
    def _convex_base(cls, doc, body_id: str, upto: int, body):
        """(last earlier convex state of the body, what was only added onto it since), or (None, None).
        A cylinder with embossed ribs is shelled as the cylinder (exact facet planes, fast) with the ribs put
        back outside, instead of eroding every rib triangle with a sphere (minutes on a wrapped emboss)."""
        if cls._facet_planes(body) is not None:
            return None, None              # convex already: the plain path is exact
        for j in range(upto - 1, -1, -1):
            state = getattr(doc, "step_states", {}).get(j, {}).get(body_id)
            if state is None or state.is_empty():
                return None, None
            if cls._facet_planes(state) is None:
                continue
            removed = CadKernel.drop_slivers(CadKernel.clean_difference(state, body))
            if removed.volume() > 1e-6 * state.volume():
                return None, None          # something was cut or moved since: erode the real body
            return state, CadKernel.drop_slivers(CadKernel.clean_difference(body, state))
        return None, None

    @classmethod
    def _thicker_than(cls, m, t):
        """Whether some part of `m` still has material left after eroding it by t (a wall would be hollowed).
        Convex parts are eroded exactly; for others (ribs, text) volume/area is half their thickness."""
        for part in m.decompose():
            if cls._facet_planes(part) is not None:
                if cls._trimmed(part, *cls._facet_planes(part), t).volume() > 1e-6:
                    return True
            elif part.volume() > t * part.surface_area():
                return True
        return False

    @classmethod
    def shell_body(cls, doc, body_id: str, upto: int, body, thickness: float, direction: str = "inside",
                   thickness2: float = 2.0, open_faces: Optional[list] = None):
        """`body` shelled where step `upto` stands, its history before that step in `doc.step_states`
        (the preview, the edit preview and the step use this)."""
        if direction == "inside":
            base, added = cls._convex_base(doc, body_id, upto, body)
            if base is not None and not cls._thicker_than(added, thickness):
                shelled = cls.compute_shell(base, thickness, direction, thickness2, open_faces)
                if shelled is not None:
                    return CadKernel.drop_slivers(shelled + added) if not added.is_empty() else shelled
            elif base is not None:         # a stacked cylinder is hollowed too, not put back solid
                cavity = cls._stacked_cavity(base, added, thickness)
                if cavity is not None:
                    return cls.compute_shell(body, thickness, direction, thickness2, open_faces, cavity=cavity)
        return cls.compute_shell(body, thickness, direction, thickness2, open_faces)

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        feats = doc.timeline.features
        upto = feats.index(self) if self in feats else doc.timeline.marker_index
        shelled = self.shell_body(doc, self.target_body_id, upto, target.manifold, self.thickness, self.direction, self.thickness2,
                                  self.open_faces)
        if shelled is not None:
            target.manifold = shelled
            target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "thickness": self.thickness,
            "direction": self.direction,
            "thickness2": self.thickness2,
            "open_faces": self.open_faces,
        }
