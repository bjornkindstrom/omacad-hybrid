# Local verification — 2026-10-28

Environment: Linux 7.2.8 / Omarchy x86_64, CPython 3.14.8, PySide6 6.12.0,
NumPy 2.5.4, PyO3 0.30.1. Native module built in release mode.

- Rust unit tests: **3 passed**.
- Strict `cargo clippy --all-targets -- -D warnings`: **passed**.
- Native parity + existing affected Qt picking regressions: **12 passed**.
- Existing affected Qt picking regressions in Python mode: **4 passed**.
- Real Wayland Qt/OpenGL smoke: **passed in both modes**, including a valid
  QOpenGLWidget context and a real body pick. Native mode also verifies that
  mesh and face indices were actually built by the extension.
- Captured viewport framebuffer comparison: same `(1256, 1280, 4)` size,
  **zero differing pixels** between Python and Rust mode. The full window
  captures differ in the backend label as intended.
- Shell launcher/build/setup syntax checks: passed.

The existing `manifold3d`/nanobind dependency emits reference-leak diagnostics
at interpreter shutdown in both Python and Rust test/smoke runs. They are not
new Rust BVH objects, and tests and both smoke processes exit successfully.
This experiment does not claim to fix upstream dependency shutdown diagnostics.

## CPU picking benchmark

See `benchmark-linux.json` for every cold/median/p95 result and fixed-seed
NumPy parity checks. Benchmarked with 120 rays per scene and no concurrent test
process. These are not FPS measurements.

| Mesh | Triangles | Python warm median | Rust warm median | Rust first query |
|---|---:|---:|---:|---:|
| Medium sphere, nearest triangle | 8,192 | 0.569 ms | 0.0052 ms | 1.90 ms |
| Dense sphere, nearest triangle | 131,072 | 12.440 ms | 0.0058 ms | 40.06 ms |

Construction is paid once for a geometry snapshot; changing the geometry needs
a new index. Ray-query improvements do not establish the speedup of the entire
hover path or application. The original GPU drawing code is unchanged.

Reproduce real-window checks (requires a working desktop OpenGL session):

```bash
OMACAD_VIEWPORT_BACKEND=rust .venv/bin/python tools/smoke_hybrid.py \
  --output docs/viewport-rust.png
OMACAD_VIEWPORT_BACKEND=python .venv/bin/python tools/smoke_hybrid.py \
  --output docs/viewport-python.png
```

Add `--keep-open` to inspect and interact with the demo scene after the check.
