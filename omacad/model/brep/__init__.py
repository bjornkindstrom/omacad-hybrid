"""B-rep bodies (experimental, setting "brep_bodies"): exact OpenCascade shapes next to the manifold3d meshes.

A body may carry a `brep` (an OCP TopoDS_Shape). When it does, its `manifold` is always the tessellation of that
shape, so everything that only knows meshes (view, picking, face analysis, mesh features) keeps working. Any
feature that writes a new mesh into a body drops the B-rep (`Body.__setattr__`), so a body silently becomes a plain
mesh body again instead of carrying a stale shape. Nothing about B-rep is saved: the history rebuilds it.

The model has no Qt, so the settings manager pushes the switch in here (like `quality`)."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from omacad import applog

_enabled = False
_available: Optional[bool] = None
_why_unavailable = ""


def available() -> bool:
    """True when the OpenCascade bindings (cadquery-ocp) import. Checked once."""
    global _available, _why_unavailable
    if _available is None:
        try:
            import OCP  # noqa: F401
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: F401
            _available = True
        except Exception as exc:      # missing wheel or a broken library: B-rep stays off, the log says why
            _available = False
            _why_unavailable = f"{type(exc).__name__}: {exc}"
            applog.log("WARNING", f"B-rep bodies unavailable: {_why_unavailable}")
    return _available


def why_unavailable() -> str:
    available()
    return _why_unavailable


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)


def active() -> bool:
    """New bodies are built as B-rep only when the setting is on and OpenCascade is installed."""
    return _enabled and available()


# ---- shapes ---------------------------------------------------------------------------------------------------------
def box(length: float, width: float, height: float):
    """Box with its min corner at the origin (same as CadKernel.create_box before placement)."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    return BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(length, width, height)).Shape()


def cylinder(radius: float, height: float):
    """Upright cylinder, bottom centre at the origin."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), radius, height).Shape()


def transform(shape, matrix):
    """Applies a 3x4 (or 4x4) affine matrix, the same convention as Manifold.transform."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform, BRepBuilderAPI_Transform
    from OCP.gp import gp_GTrsf, gp_Trsf
    m = np.asarray(matrix, dtype=float)[:3, :4]
    lin = m[:, :3]
    trsf = gp_Trsf()
    if np.allclose(lin @ lin.T, np.eye(3), atol=1e-9):     # rotation, translation and mirroring stay exact
        trsf.SetValues(*m[0], *m[1], *m[2])
        return BRepBuilderAPI_Transform(shape, trsf, True).Shape()
    gt = gp_GTrsf()                                   # scaling/shear: general transform (turns faces into B-splines)
    for r in range(3):
        for c in range(4):
            gt.SetValue(r + 1, c + 1, float(m[r, c]))
    return BRepBuilderAPI_GTransform(shape, gt, True).Shape()


def translate(shape, offset):
    m = np.eye(4)[:3]
    m[:, 3] = np.asarray(offset, dtype=float)
    return transform(shape, m)


def volume(shape) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def is_valid(shape) -> bool:
    from OCP.BRepCheck import BRepCheck_Analyzer
    return bool(BRepCheck_Analyzer(shape).IsValid())


# ---- tessellation -----------------------------------------------------------------------------------------------------
def _faces(shape):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        yield TopoDS.Face(exp.Current())
        exp.Next()


def tessellate(shape, segments: Optional[int] = None):
    """(verts float64 (n,3), tris int64 (m,3)) welded across faces. A full circle gets about `segments` pieces
    (Omacad's curve smoothness), independent of its size, like the manifold primitives."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location
    if segments is None:
        from omacad.model import quality
        segments = quality.circle_segments()
    BRepTools.Clean_s(shape)                           # a cached coarser mesh would be reused otherwise
    # Relative deflection = the sagitta of an n-gon over the edge's size, plus the same angle: about n pieces per
    # circle whatever its radius (an absolute deflection would give big circles more pieces than small ones).
    n = max(8, int(segments))
    BRepMesh_IncrementalMesh(shape, (1 - math.cos(math.pi / n)) / 2, True, 2 * math.pi / n * 1.0001, True)
    vs, ts, off = [], [], 0
    for face in _faces(shape):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        pts = np.array([tri.Node(i).Transformed(trsf).Coord() for i in range(1, tri.NbNodes() + 1)], dtype=float)
        idx = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64) - 1
        if face.Orientation() == TopAbs_REVERSED:
            idx = idx[:, ::-1]
        vs.append(pts)
        ts.append(idx + off)
        off += len(pts)
    if not vs:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    v, t = np.vstack(vs), np.vstack(ts)
    # Faces share their edge discretisation, so seam points coincide; weld them (1 nm grid).
    key = np.round(v * 1e6).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    t = inverse.reshape(-1)[t]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    return v[first], t


def to_manifold(shape, segments: Optional[int] = None):
    """The shape as a manifold3d solid. Raises ValueError when the tessellation is not a closed manifold."""
    import manifold3d as m3d
    v, t = tessellate(shape, segments)
    man = m3d.Manifold(m3d.Mesh64(vert_properties=np.ascontiguousarray(v, dtype=np.float64),
                                  tri_verts=np.ascontiguousarray(t, dtype=np.uint64)))
    status = str(man.status())
    if not status.endswith("NoError") or man.is_empty():
        raise ValueError(f"B-rep tessellation is not a closed solid ({status})")
    return man


def attach(body, shape) -> bool:
    """Gives `body` the shape and its tessellation. False (body untouched) when the shape can't be meshed."""
    try:
        man = to_manifold(shape)
    except Exception as exc:
        applog.log("WARNING", f"{getattr(body, 'name', '?')}: B-rep not used ({exc}); keeping the mesh")
        return False
    body.set_brep(shape, man)
    return True


def boolean(a, b, operation: str):
    """join / cut / intersect of two shapes. Raises when OpenCascade fails or the result is invalid or empty."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    op = {"join": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut, "intersect": BRepAlgoAPI_Common}[operation](a, b)
    op.Build()
    if not op.IsDone():
        raise RuntimeError(f"OpenCascade {operation} failed")
    out = op.Shape()
    if operation == "join":
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        unify = ShapeUpgrade_UnifySameDomain(out, True, True, True)   # merge the faces the fuse split in two
        unify.Build()
        out = unify.Shape()
    if not is_valid(out):
        raise RuntimeError(f"OpenCascade {operation} made an invalid shape")
    if volume(out) <= 1e-12:
        raise ValueError(f"{operation} left nothing")
    return out


def planar_face_at(shape, normal, origin, tol: float = 1e-3):
    """The flat face of `shape` facing `normal` that contains (is nearest to) the point `origin`, or None."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.gp import gp_Pnt
    n = np.asarray(normal, dtype=float)
    n = n / max(float(np.linalg.norm(n)), 1e-300)
    point = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, origin))).Vertex()
    best = None
    for face in _faces(shape):
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() != GeomAbs_Plane:
            continue
        fn = np.array(surf.Plane().Axis().Direction().Coord())
        if face.Orientation() == TopAbs_REVERSED:
            fn = -fn
        if float(fn @ n) < 0.999:
            continue
        dist = BRepExtrema_DistShapeShape(point, face)
        if not dist.IsDone():
            continue
        d = dist.Value()
        if d <= tol and (best is None or d < best[0]):
            best = (d, face)
    return best[1] if best else None


def shell(shape, open_faces, inward: float, outward: float):
    """Hollow `shape` with walls `inward` (into the material) or `outward`; `open_faces` = [(normal, point)] flat
    faces left open. One side only: a wall both ways is left to the mesh tools."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
    from OCP.collections import List_TopoDS_Shape
    if inward > 1e-9 and outward > 1e-9:
        raise ValueError("a wall both ways is not supported as B-rep")
    removed = List_TopoDS_Shape()
    for normal, origin in open_faces:
        face = planar_face_at(shape, normal, origin)
        if face is None:
            raise ValueError("open face not found on the B-rep shape")
        removed.Append(face)
    offset = -inward if inward > 1e-9 else outward
    if removed.Size() == 0:
        # closed hollow body: MakeThickSolid without an opening returns only the offset skin, so cut it instead
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
        off = BRepOffsetAPI_MakeOffsetShape()
        off.PerformByJoin(shape, float(offset), 1e-4)
        off.Build()
        if not off.IsDone():
            raise RuntimeError("OpenCascade could not offset the body")
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
        from OCP.TopoDS import TopoDS
        from OCP.TopAbs import TopAbs_SHELL
        from OCP.TopExp import TopExp_Explorer
        skin = off.Shape()
        exp = TopExp_Explorer(skin, TopAbs_SHELL)
        if not exp.More():
            raise RuntimeError("offset gave no shell")
        other = BRepBuilderAPI_MakeSolid(TopoDS.Shell(exp.Current())).Solid()
        if volume(other) < 0:
            other.Reverse()
        out = boolean(shape, other, "cut") if inward > 1e-9 else boolean(other, shape, "cut")
        return out
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidByJoin(shape, removed, float(offset), 1e-4)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("OpenCascade could not build the shell")
    out = mk.Shape()
    if not is_valid(out):
        raise RuntimeError("OpenCascade made an invalid shell")
    v0, v1 = volume(shape), volume(out)
    if not (0 < v1 < v0) and inward > 0 or outward > 0 and not v1 > 0:
        raise RuntimeError("the B-rep shell has an unexpected volume")
    return out


class MatrixProbe:
    """Stands in for a Manifold in a function that moves one (m.translate(...).mirror(...) ...), and records the
    4x4 matrix it applies, so the same move can be given to a B-rep shape."""

    def __init__(self, matrix=None):
        self.matrix = np.eye(4) if matrix is None else matrix

    def _then(self, m):
        return MatrixProbe(m @ self.matrix)

    def translate(self, offset):
        m = np.eye(4)
        m[:3, 3] = np.asarray(offset, dtype=float)
        return self._then(m)

    def transform(self, matrix):
        m = np.eye(4)
        m[:3, :4] = np.asarray(matrix, dtype=float)[:3, :4]
        return self._then(m)

    def mirror(self, normal):
        n = np.asarray(normal, dtype=float)
        n = n / max(float(np.linalg.norm(n)), 1e-300)
        m = np.eye(4)
        m[:3, :3] = np.eye(3) - 2.0 * np.outer(n, n)
        return self._then(m)

    def rotate(self, degrees):
        """Manifold.rotate: about X, then Y, then Z (degrees)."""
        rx, ry, rz = (np.radians(float(a)) for a in degrees)
        cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
        mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
        m = np.eye(4)
        m[:3, :3] = mz @ my @ mx
        return self._then(m)


def matrix_of(move) -> np.ndarray:
    """The 3x4 matrix of a function that moves a Manifold (see MatrixProbe)."""
    out = move(MatrixProbe())
    if not isinstance(out, MatrixProbe):
        raise TypeError("the move is not a plain transform")
    return out.matrix[:3, :4]
