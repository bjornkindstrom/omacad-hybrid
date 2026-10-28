#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv/bin/python ]]; then
    uv venv --python "${OMACAD_PYTHON:-python3.14}" .venv
fi
# Upstream python-solvespace's mimalloc needs pre-C23 atomics on recent GCC.
CFLAGS="${CFLAGS:-} -std=gnu17" CXXFLAGS="${CXXFLAGS:-} -std=gnu++17" \
    uv pip install --python .venv/bin/python -r requirements.txt
exec ./tools/build_native.sh
