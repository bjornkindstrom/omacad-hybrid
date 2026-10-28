#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export VIRTUAL_ENV="$PWD/.venv"
exec .venv/bin/maturin develop --locked --release --manifest-path native/Cargo.toml
