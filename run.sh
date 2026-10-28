#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "${1:-}" == --backend ]]; then
    export OMACAD_VIEWPORT_BACKEND="${2:?Choose python, rust, or auto}"
    shift 2
fi
case "${OMACAD_VIEWPORT_BACKEND:-auto}" in
    auto|python|rust) ;;
    *) echo 'Backend must be auto, python, or rust' >&2; exit 2 ;;
esac
exec .venv/bin/python app.py "$@"
