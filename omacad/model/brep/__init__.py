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
    if np.allclose(lin @ lin.T, np.eye(3), atol=1e-9) and np.linalg.det(lin) > 0:
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
