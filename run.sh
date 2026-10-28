#!/usr/bin/env bash
# Quick launcher for Omacad on Omarchy Linux

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/python" ]; then
    exec .venv/bin/python app.py "$@"
else
    exec python3 app.py "$@"
fi
