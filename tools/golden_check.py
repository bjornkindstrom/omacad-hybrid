#!/usr/bin/env python3
"""Quality gate for speed work: rebuild every project document and compare each body's geometry, faces, edges and
render mesh with a recorded baseline. A speed change must give zero differences.

    .venv/bin/python tools/golden_check.py --record            # baseline from the current code
    .venv/bin/python tools/golden_check.py --check             # compare; exit 1 on any difference
    .venv/bin/python tools/golden_check.py --check -k jar      # only documents whose name contains "jar"

Each document is rebuilt in its own process (a crash or hang in one cannot hide the others) with fast view off and
isolated settings, like the test suite. The baseline lives in .state/golden/ (not committed)."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".state" / "golden" / "baseline.json"
DECIMALS = 9


def documents(pattern: str = "") -> list[Path]:
    found = sorted((ROOT / "tests" / "data").rglob("*.omacad")) + sorted(ROOT.glob("*.omacad"))
    return [p for p in found if pattern.lower() in p.name.lower()]


# ---------------------------------------------------------------- worker side (one document per process)

def _digest(*arrays) -> str:
    import numpy as np
    h = hashlib.blake2b(digest_size=12)
    for a in arrays:
        a = np.asarray(a, dtype=np.float64)
        h.update(str(a.shape).encode())
        h.update(np.round(a, DECIMALS).tobytes())
    return h.hexdigest()


def _plain(v):
    """A JSON-safe, rounded copy of an edge ref (tuples of floats, strings, nested)."""
    import numpy as np
    if isinstance(v, (float, np.floating)):
        return round(float(v), DECIMALS - 2)
    if isinstance(v, (int, np.integer, bool, str)) or v is None:
        return v if not isinstance(v, np.integer) else int(v)
    if isinstance(v, np.ndarray):
        return _plain(v.tolist())
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in sorted(v.items())}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return repr(v)


def _edge_sig(e) -> str:
    try:
        ref = _plain(e.ref())
    except Exception as err:            # an edge type without a ref still counts, by its type and error
        ref = f"no ref: {type(err).__name__}"
    convex = getattr(e, "convex", None)
    return json.dumps([type(e).__name__, ref, convex], sort_keys=True)


def body_signature(body) -> dict:
    import numpy as np
    mesh = body.manifold.to_mesh64()
    verts = np.asarray(mesh.vert_properties)[:, :3]
    tris = np.asarray(mesh.tri_verts)
    faces = sorted(json.dumps([f.index, _plain(np.round(f.normal, 7)), round(float(f.area), 7),
                               _digest(f.tris)]) for f in body.faces)
    edges = sorted(_edge_sig(e) for e in body.edges)
    rm = body.render_mesh
    sig = {
        "name": body.name,
        "volume": round(float(body.manifold.volume()), 6),
        "area": round(float(body.manifold.surface_area()), 6),
        "genus": int(body.manifold.genus()),
        "mesh": _digest(verts, tris),
        "faces": hashlib.blake2b("\n".join(faces).encode(), digest_size=12).hexdigest(),
        "n_faces": len(faces),
        "edges": hashlib.blake2b("\n".join(edges).encode(), digest_size=12).hexdigest(),
        "n_edges": len(edges),
        "edge_kinds": sorted({json.loads(s)[0] for s in edges}),
    }
    if rm is not None:
        sig["render"] = _digest(rm.vertices, rm.normals)
        sig["sharp"] = _digest(rm.sharp_lines)
        sig["tangent"] = _digest(rm.tangent_lines())
    return sig


def run_one(path: str) -> dict:
    """Runs in a fresh interpreter: load + rebuild one document, return {body id: signature}."""
    state = Path(tempfile.mkdtemp(prefix="omacad-golden-"))
    os.environ.setdefault("OMACAD_HYBRID_STATE_DIR", str(state))
    sys.path.insert(0, str(ROOT))
    from omacad.ui import settings
    settings._instance = settings.SettingsManager(state / "settings.json")
    from omacad.model import quality
    quality.set_fast_view(False)
    quality.set_interactive_mode(False)
    from omacad.io.exporter import Exporter
    started = time.perf_counter()
    doc = Exporter.load_project(path)
    bodies = {bid: body_signature(b) for bid, b in sorted(doc.bodies.items())}
    return {"bodies": bodies, "seconds": round(time.perf_counter() - started, 2)}


# ---------------------------------------------------------------- driver side

def _spawn(path: Path, timeout: int) -> tuple[str, dict]:
    key = path.relative_to(ROOT).as_posix()
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", str(path)]
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    try:
        out = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return key, {"error": f"timeout after {timeout}s"}
    line = next((ln for ln in reversed(out.stdout.splitlines()) if ln.startswith("GOLDEN ")), None)
    if out.returncode != 0 or line is None:
        tail = (out.stderr or out.stdout).strip().splitlines()[-3:]
        return key, {"error": " | ".join(tail) or f"exit {out.returncode}"}
    return key, json.loads(line[len("GOLDEN "):])


def collect(paths: list[Path], jobs: int, timeout: int) -> dict:
    result = {}
    with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
        for key, data in pool.map(lambda p: _spawn(p, timeout), paths):
            result[key] = data
            state = data.get("error") or f"{len(data['bodies'])} bodies, {data['seconds']} s"
            print(f"  {key}: {state}", flush=True)
    return result


def compare(base: dict, now: dict) -> list[str]:
    diffs = []
    for key, cur in now.items():
        old = base.get(key)
        if old is None:
            diffs.append(f"{key}: not in the baseline (record again)")
            continue
        if "error" in old or "error" in cur:
            if old.get("error") != cur.get("error"):
                diffs.append(f"{key}: error changed: {old.get('error')!r} -> {cur.get('error')!r}")
            continue
        ob, cb = old["bodies"], cur["bodies"]
        for bid in sorted(set(ob) | set(cb)):
            if bid not in ob or bid not in cb:
                diffs.append(f"{key}: body {bid} {'added' if bid in cb else 'missing'}")
                continue
            for field in sorted(set(ob[bid]) | set(cb[bid])):
                if ob[bid].get(field) != cb[bid].get(field):
                    diffs.append(f"{key}: {bid}.{field}: {ob[bid].get(field)!r} -> {cb[bid].get(field)!r}")
    return diffs


def timing_table(base: dict, now: dict) -> str:
    rows, tb, tn = [], 0.0, 0.0
    for key, cur in sorted(now.items()):
        old = base.get(key, {})
        if "seconds" in cur and "seconds" in old:
            tb, tn = tb + old["seconds"], tn + cur["seconds"]
            if old["seconds"] >= 1.0:
                rows.append(f"  {old['seconds']:7.2f} -> {cur['seconds']:7.2f} s  {key}")
    rows.append(f"  {tb:7.2f} -> {tn:7.2f} s  TOTAL")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("-k", default="", help="only documents whose file name contains this")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.worker:
        print("GOLDEN " + json.dumps(run_one(a.worker)), flush=True)
        return 0
    if a.record == a.check:
        ap.error("give --record or --check")
    paths = documents(a.k)
    print(f"{len(paths)} documents, {a.jobs} at a time", flush=True)
    now = collect(paths, a.jobs, a.timeout)
    if a.record:
        a.baseline.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(a.baseline.read_text()) if a.baseline.exists() and a.k else {}
        old.update(now)
        a.baseline.write_text(json.dumps(old, indent=1, sort_keys=True))
        print(f"baseline written: {a.baseline}")
        return 0
    base = json.loads(a.baseline.read_text())
    diffs = compare(base, now)
    print(timing_table(base, now))
    if diffs:
        print(f"\n{len(diffs)} DIFFERENCES:")
        print("\n".join("  " + d for d in diffs[:200]))
        return 1
    print("\nno differences")
    return 0


if __name__ == "__main__":
    sys.exit(main())
