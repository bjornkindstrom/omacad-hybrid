"""A cache for slow kernel operations whose result depends only on their input solid and a few numbers (Shell's
Minkowski erosion of a non-convex body takes over a minute). Kept in memory for the session (undo, redo and file
reload rebuild the timeline from scratch) and on disk, so the same project opens quickly the next time.

The key is a hash of the input mesh (float64 vertices and triangles), the operation, its numbers, the manifold3d
version and CACHE_VERSION. A cached result is the very mesh the operation returned, rebuilt as a Manifold."""
from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import manifold3d as m3d

from omacad import applog

CACHE_VERSION = 3
MEMORY_ENTRIES = 8
DISK_LIMIT_BYTES = 400 * 1024 * 1024
MIN_SECONDS = 0.5           # quicker operations are not worth a disk file

# every Mesh64 field: with only vertices and triangles the next boolean on a cached result triangulates differently
# (face ids and runs steer it); with all of them the result is bit for bit the one the operation gave
FIELDS = {"vert_properties": np.float64, "tri_verts": np.uint64, "merge_from_vert": np.uint64,
          "merge_to_vert": np.uint64, "run_index": np.uint64, "run_original_id": np.uint32,
          "run_transform": np.float64, "run_flags": np.uint8, "face_id": np.uint64, "halfedge_tangent": np.float64}

_memory: "OrderedDict[str, dict]" = OrderedDict()      # key -> entry (arrays with relative ids, ids used)
_lock = threading.Lock()
_disk_dir: Optional[Path] = None


def disk_dir() -> Optional[Path]:
    """Where results are kept on disk (None = memory only)."""
    global _disk_dir
    if _disk_dir is None:
        try:
            from omacad.hybrid_paths import DATA_DIR
            _disk_dir = Path(DATA_DIR) / "solid_cache"
        except Exception:
            return None
    return _disk_dir


def set_disk_dir(path: Optional[Path]) -> None:
    global _disk_dir
    _disk_dir = path


def clear_memory() -> None:
    with _lock:
        _memory.clear()


def key_of(op: str, solid: m3d.Manifold, *numbers) -> str:
    """Hash of the input's whole mesh (every field, as they steer the result too), the op and its numbers."""
    h = hashlib.blake2b(digest_size=20)
    h.update(f"{CACHE_VERSION}|{getattr(m3d, '__version__', '?')}|{op}|{numbers!r}".encode())
    for name, a in to_arrays(solid).items():
        if name == "run_original_id":   # a per-process counter: the same solid gets another one each run
            continue
        h.update(name.encode() + str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def cached(op: str, solid: m3d.Manifold, numbers: tuple, compute: Callable[[], m3d.Manifold]) -> m3d.Manifold:
    """compute(), or its earlier result for the same input solid, op and numbers.

    Manifold numbers every solid it makes from one process-wide counter, and the numbers steer how later booleans
    triangulate. So a run records how many numbers the operation used and which of them its result carries
    (relative to where it started); a cached result uses up exactly as many and gets the same relative ones, and
    everything built after it is bit for bit what a fresh computation gives."""
    import time
    key = key_of(op, solid, *numbers)
    with _lock:
        entry = _memory.get(key)
        if entry is not None:
            _memory.move_to_end(key)
    if entry is None:
        entry = _load(key)
    if entry is not None:
        _remember(key, entry)
        return _materialize(entry)
    first = int(m3d.Manifold.reserve_ids(1))
    started = time.perf_counter()
    result = compute()
    seconds = time.perf_counter() - started
    end = int(m3d.Manifold.reserve_ids(1))
    arrays = to_arrays(result)
    rel = arrays["run_original_id"].astype(np.int64) - first
    if len(rel) and (rel.min() <= 0 or rel.max() >= end - first):
        return result                   # carries numbers from before the operation: cannot be replayed exactly
    arrays["run_original_id"] = rel.astype(np.uint32)
    entry = {"arrays": arrays, "used": end - first - 1, "tolerance": float(result.get_tolerance())}
    if seconds >= MIN_SECONDS:
        _save(key, entry)
    _remember(key, entry)
    return result


def _remember(key: str, entry: dict) -> None:
    with _lock:
        _memory[key] = entry
        _memory.move_to_end(key)
        while len(_memory) > MEMORY_ENTRIES:
            _memory.popitem(last=False)


def _materialize(entry: dict) -> m3d.Manifold:
    """The cached solid, using up the same ids the operation would have (see `cached`)."""
    first = int(m3d.Manifold.reserve_ids(1))
    if entry["used"] > 0:
        m3d.Manifold.reserve_ids(int(entry["used"]))
    m3d.Manifold.reserve_ids(1)
    arrays = {k: np.array(v) for k, v in entry["arrays"].items()}
    arrays["run_original_id"] = (arrays["run_original_id"].astype(np.int64) + first).astype(np.uint32)
    return from_arrays(arrays, entry.get("tolerance", 0.0))


def _path(key: str) -> Optional[Path]:
    d = disk_dir()
    return None if d is None else d / f"{key}.npz"


def _load(key: str) -> Optional[dict]:
    path = _path(key)
    if path is None or not path.exists():
        return None
    try:
        with np.load(path) as data:
            entry = {"arrays": {k: np.array(data[k], dtype=dt) for k, dt in FIELDS.items()},   # writable copies
                     "used": int(data["used"]), "tolerance": float(data["tolerance"])}
        if _materialize_check(entry):
            os.utime(path)                  # recently used: pruned last
            return entry
        raise ValueError("cached solid is invalid")
    except Exception as e:              # a damaged file is rebuilt, never trusted
        applog.log("WARN", f"solid cache: dropping {path.name}: {e!r}")
        try:
            path.unlink()
        except OSError:
            pass
        return None


def _materialize_check(entry: dict) -> bool:
    arrays = entry["arrays"]
    tris, verts = arrays["tri_verts"], arrays["vert_properties"]
    return (verts.ndim == 2 and verts.shape[1] >= 3 and tris.ndim == 2 and tris.shape[1] == 3
            and (len(tris) == 0 or int(tris.max()) < len(verts)) and entry["used"] >= 0)


def _save(key: str, entry: dict) -> None:
    path = _path(key)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npz")
        np.savez(tmp, used=np.array(entry["used"]), tolerance=np.array(entry["tolerance"]), **entry["arrays"])
        os.replace(tmp, path)
        _prune(path.parent)
    except Exception as e:              # the cache is an extra: the result is still returned
        applog.log("WARN", f"solid cache: could not save: {e!r}")


def to_arrays(solid: m3d.Manifold) -> dict:
    mesh = solid.to_mesh64()
    return {k: np.array(getattr(mesh, k), dtype=dt) for k, dt in FIELDS.items()}


def from_arrays(arrays: dict, tolerance: float = 0.0) -> m3d.Manifold:
    """The solid back from its mesh fields, with the tolerance the operation left it with (it steers how later
    booleans simplify, and a mesh does not carry it)."""
    if len(arrays["tri_verts"]) == 0:
        return m3d.Manifold()
    kw = {k: a for k, a in arrays.items() if a.size or k in ("vert_properties", "tri_verts")}
    return m3d.Manifold(m3d.Mesh64(**kw, tolerance=float(tolerance)))


def _prune(folder: Path) -> None:
    files = sorted(folder.glob("*.npz"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    for p in files:
        if total <= DISK_LIMIT_BYTES:
            break
        total -= p.stat().st_size
        try:
            p.unlink()
        except OSError:
            pass
