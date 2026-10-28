# Omacad Hybrid: experiment boundary

Base: https://github.com/bjornkindstrom/omacad at
`fdf4331b00d014521de916ce65bb2863d06ee444` (Omacad 0.9.9.80.69).
Only committed, tracked files were imported. Local documents, secrets, the source
virtualenv and the source repository's Git history were not copied. This is a new
independent repository; the original `omacad` and `omacad-rs` remain untouched.

## Execution path

```text
PySide6 Viewport3D mouse movement / click
    → existing picker_mixin.py
    → existing faces_hit_tests.ray_hit_faces / ray_mesh_hit
    → viewport_accel.py
        Python: original NumPy implementation
        Rust: one bulk snapshot → TriangleIndex (BVH) → ray queries
    → original body / face / triangle identity
    → original selection, tool preview and OpenGL renderer
```

Rust owns vertices, face owners and the BVH; it never retains a borrowed NumPy
pointer. Constructor input is little-endian float64 triangles `(N,3,3)` plus
uint32 face owners. Native queries release the GIL (`Python::detach`). Face
results contain one distance for **each** original face; nearer faces must never
prune farther faces from this API. Mesh results return the nearest original
triangle index, breaking exact ties the same way as NumPy's `argmin`.

Both paths use Möller–Trumbore, determinant epsilon `1e-12`, forward-distance
cutoff `1e-6`, and caller-provided barycentric tolerance. The BVH's slab bounds
include tolerance expansion so edge-adjacent hits are not culled incorrectly.
The native module has an explicit API version checked by the adapter.

Geometry follows upstream's snapshot convention: replace a RenderMesh vertex
array or face list when geometry changes. The adapter retains the source array
identity; a new one creates a new index even when its dimensions are unchanged.
Arbitrary in-place mutation of a cached array/list is not supported by either
the upstream face-stack cache or this accelerator. Face-stack caching uses LRU
order and a one-million-triangle budget (one oversized current body is allowed).
Mesh indices live with their RenderMesh and disappear with it.

## Isolation and rollout

- `run.sh --backend python|rust|auto` selects the backend at process startup.
  `auto` uses Rust when available and logs a Python fallback when missing.
  Explicit `rust` fails with a build instruction instead of silently falling back.
- The permanent Qt status indicator shows the actual backend. All dialogs,
  sketches, modeling, undo/redo, files and GL drawing are still upstream Python.
- Settings, sessions, feedback, custom themes and arrow caches live under `.state/`
  in this repository, or `OMACAD_HYBRID_STATE_DIR` if explicitly overridden.
  The active Omarchy theme is read, never changed.
- Automatic application restart and background request submission are disabled.
  The upstream Windows-release workflow was moved out of `.github/workflows/`;
  pushing this experiment cannot publish an upstream-style release.
- Linux/CPython 3.14 is the verified target. Other operating systems and packaged
  apps need their own native wheels and verification before rollout.

## Verification

- Rust tests: face completeness, original IDs, equal-distance ties, slab/edge
  tolerance, empty/parallel/behind/zero-direction rays.
- Python parity tests: seeded random rays; empty, degenerate and non-contiguous
  data; real CAD box, hole and sphere; replacement after moves; malformed inputs;
  immutable snapshots and concurrent queries; missing-module fallback.
- Qt test: the original Viewport3D actually picks via the native module and rejects
  the old position after a document move. Existing hover/fillet/loop-picking
  regression tests run with both backends.
- `tools/benchmark_viewport.py` compares the **same public picking entrypoints**
  with both backends, identical seeded rays and per-result parity checks. It
  records cold first-query latency separately from warm median and p95 latency.
  Sphere meshes are real Manifold → RenderMesh output. The 1,000 face groups are
  a synthetic many-face workload, not an assertion about sphere B-rep topology.
- These are CPU picking measurements. They do not establish FPS, tessellation,
  boolean-modeling, GPU rendering or whole-application speedups.

The immutable BVH boundary is deliberately small. Later experiments can move mesh
preparation or the render loop into Rust if profiling identifies those as the
remaining bottlenecks. Upstream already caches body VAOs/VBOs, so porting that
cache alone would not prove a useful speed improvement.

PyO3 reference: https://pyo3.rs/v0.30.1/parallelism
