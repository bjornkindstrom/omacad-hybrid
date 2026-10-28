#!/usr/bin/env bash
# Run a take on a virtual Hyprland monitor, so it never touches the real screen:
#     video/headless.sh .venv/bin/python video/features_take.py --out ~/Videos/x.mp4
# A headless output (2560x1440, scale 1.25 like the laptop panel) is created, windows with the class
# "omacad-video" (set by the takes) are sent there fullscreen without taking focus, and everything is
# removed again afterwards.
set -u
OUT=videorender
hyprctl output create headless "$OUT" >/dev/null
hyprctl eval "hl.monitor({ output = \"$OUT\", mode = \"2560x1440@60\", position = \"auto\", scale = 1.25 })" >/dev/null
hyprctl eval "hl.workspace_rule({ workspace = \"name:video\", monitor = \"$OUT\", default = true })" >/dev/null
hyprctl eval 'hl.window_rule({ name = "omacad-video", match = { class = "^omacad-video$" }, workspace = "name:video silent", fullscreen = true })' >/dev/null
cleanup() {
    hyprctl eval 'hl.window_rule({ name = "omacad-video", enabled = false })' >/dev/null
    hyprctl output remove "$OUT" >/dev/null
}
trap cleanup EXIT INT TERM
"$@"
