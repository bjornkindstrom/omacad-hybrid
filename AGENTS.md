# Agents — Omacad Rules & Token Efficiency

1. **Architecture & Rules**: Read `omacad.md` (~70 lines) first for architecture, patterns, and recent fixes.
2. **Historical Solutions Log (`SOLUTIONS_LOG.md`)**: Do **NOT** read `SOLUTIONS_LOG.md` in full (~60 KB). Search it on demand with `grep_search` for relevant keywords (e.g., `thread`, `emboss`, `fillet`, `offset_face`). Append new solutions to the top of `omacad.md`'s recent log and archive older ones to `SOLUTIONS_LOG.md`.
3. **Token-frugal testing**:
   - While developing/debugging: run only the relevant test file: `.venv/bin/python -m pytest tests/test_<feature>.py -q --tb=short`.
   - Before committing: verify affected test modules pass.
4. **Git & Release**: Stage only modified source/test files (`git add omacad/... tests/... CHANGELOG.md`), never untracked `.omacad`/`.pdf`/`video/` files. Never push, build, or publish unless the user asks.
