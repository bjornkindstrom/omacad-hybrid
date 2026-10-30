"""Optional native picking. Qt/OpenGL and the CAD document stay in Python.

Meshes and face lists are immutable geometry snapshots, as in upstream's face-stack
cache. Replacing a vertex array or face list builds a fresh index. No Python/NumPy
memory is borrowed while Rust runs without the GIL.
"""
from __future__ import annotations

import importlib
import logging
import os

import numpy as np

_MODE = os.environ.get("OMACAD_VIEWPORT_BACKEND", "auto").lower()
if _MODE not in {"auto", "python", "rust"}:
    raise ValueError("OMACAD_VIEWPORT_BACKEND must be auto, python, or rust")
_NATIVE = None
_ERROR = None
if _MODE != "python":
    try:
        _NATIVE = importlib.import_module("_viewport_native")
        if _NATIVE.API_VERSION != 2:
            raise ImportError("native picking API version mismatch; rebuild the extension")
    except ImportError as error:
        _NATIVE = None
        _ERROR = str(error)
        if _MODE == "rust":
            raise RuntimeError("Rust picking requested but unavailable. Run ./tools/build_native.sh") from error
        logging.getLogger(__name__).warning("Rust picking unavailable; using Python: %s", error)


def backend_name() -> str:
    return "rust" if _NATIVE is not None else "python"


def build_index(triangles, owners, face_count):
    """One bulk transfer per geometry snapshot; None selects the NumPy path."""
    if _NATIVE is None:
        return None
    tri = np.ascontiguousarray(triangles, dtype="<f8").reshape(-1, 3, 3)
    owner = np.ascontiguousarray(owners, dtype="<u4")
    if owner.ndim != 1 or len(owner) != len(tri):
        raise ValueError("triangle owners must be a one-dimensional array matching triangles")
    return _NATIVE.TriangleIndex(tri.tobytes(), owner.tobytes(), int(face_count))


def face_hits(index, origin, direction, bary_tol):
    values = index.face_hits(tuple(map(float, origin)), tuple(map(float, direction)), float(bary_tol))
    return np.frombuffer(values, dtype="<f8").copy()


def mesh_hit(mesh, origin, direction):
    """Nearest triangle, preserving the original RenderMesh triangle index."""
    if _NATIVE is None:
        raise RuntimeError("mesh_hit requires the native backend")
    vertices = mesh.vertices
    cached = getattr(mesh, "_native_pick_index", None)
    if cached is None or cached[0] is not vertices:
        triangles = np.asarray(vertices, dtype=np.float64).reshape(-1, 3, 3)
        cached = (vertices, build_index(triangles, np.zeros(len(triangles), dtype=np.uint32), 1))
        mesh._native_pick_index = cached
    return cached[1].nearest(tuple(map(float, origin)), tuple(map(float, direction)))


def flat_patch_mask(count, coplanar, sharp, directions):
    """Exact-order native flat-patch pass; None retains the Python reference path."""
    if _NATIVE is None:
        return None
    data = _NATIVE.flat_patch_mask(int(count), np.ascontiguousarray(coplanar,dtype="<u8").tobytes(),
                                  np.ascontiguousarray(sharp,dtype="<u8").tobytes(),
                                  np.ascontiguousarray(directions,dtype="<f8").tobytes(), np.asarray(directions).dtype == np.float32)
    return np.frombuffer(data,dtype=np.bool_).copy()


def coplanar_roots(v, f, normals, areas, adjacency, tolerance):
    """Batch the old coplanarity/union pass; root identities and face order are preserved."""
    if _NATIVE is None:
        return None
    data = _NATIVE.coplanar_roots(np.ascontiguousarray(v[f],dtype="<f8").tobytes(),
                                 np.ascontiguousarray(normals,dtype="<f8").tobytes(),
                                 np.ascontiguousarray(areas,dtype="<f8").tobytes(),
                                 np.ascontiguousarray(adjacency,dtype="<u8").tobytes(),float(tolerance))
    return np.frombuffer(data,dtype="<u8").astype(np.int64)


def snap_and_clean_segments(v, segments, snap_tol):
    """Native snap-vertex pass: returns (cleaned_segments, original_indices)."""
    if _NATIVE is None:
        return None
    seg_arr = np.ascontiguousarray(segments, dtype="<u8")
    data = _NATIVE.snap_and_clean_segments(
        np.ascontiguousarray(v, dtype="<f8").tobytes(),
        seg_arr.tobytes(),
        float(snap_tol)
    )
    res = np.frombuffer(data, dtype="<u8").reshape(-1, 3)
    return res
