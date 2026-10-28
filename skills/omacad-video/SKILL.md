---
name: omacad-video
description: Make narrated demo/tutorial videos of the Omacad CAD app (or any PySide6/Qt app with a QOpenGLWidget) without a screen recorder. Renders the real window frame by frame from a script that drives the app, draws cursor and captions, adds a local text-to-speech voice-over and background music through ComfyUI, and encodes with ffmpeg. Use when asked to record, script, narrate or re-make an Omacad feature video, tour, or tutorial clip.
---

# Omacad video creation

Frame-exact videos: a Python "take" script opens the real `MainWindow`, drives it through its own mouse/key event handlers, saves one PNG per frame (cursor and caption painted on), and ffmpeg encodes the frames. Voice-over and music are generated locally (nothing leaves the machine) and muxed on afterwards. Because the camera/actions are functions of the frame number, every run is identical and re-takes are cheap.

## Requirements
- Omacad checkout with its `.venv` (PySide6, numpy). Run on the **real display** (Wayland/X11/Windows), never offscreen: the viewport needs a GL context.
- `ffmpeg` and `ffprobe` on PATH.
- For voice and music only: the ComfyUI desktop app running on `127.0.0.1:8188` (override with env `COMFY`), with the nodes `FB_Qwen3TTSVoiceDesign` / `FB_Qwen3TTSVoiceClone` (Qwen3-TTS 1.7B) and ACE-Step 1.5 XL (`acestep_v1.5_xl_sft_bf16.safetensors`, `ace_1.5_vae`, `qwen_0.6b_ace15`, `qwen_4b_ace15`). `COMFY_INPUT` (default `~/ComfyUI-Shared/input`) must be ComfyUI's input folder.
- Silent videos need neither ComfyUI nor audio models.

## Setup
Copy `scripts/*.py` into the project's `video/` folder (they import each other and expect the repo root one level up). Put new takes next to them, in `video/<name>_take.py`. Add the frame folder (`video/<name>/`) and `video/audio/` to `video/.gitignore`: frames are thousands of PNGs.

## The pipeline
1. **Write the take** (`examples/plate_take.py` is the smallest complete one; `examples/tour_take.py` is the narrated two-minute tour with many scenes).
2. **Render silent**: `.venv/bin/python video/<name>_take.py --out ~/Videos/<name>.mp4` → frames in `video/<name>/`, plus `marks.json` (frame number, caption, spoken line per scene).
3. **Narrate**: `.venv/bin/python video/narrate.py video/<name>/marks.json ~/Videos/<name>.mp4 ~/Videos/<name>-narrated.mp4 --lines video/lines_<name>.json [--music video/audio/music.flac]`
4. **Music (optional)**: `.venv/bin/python video/music.py video/audio/music.flac --seconds 130 --seed 3`

## Writing a take
```python
from take import Take, W, H            # 1280x720, 30 fps
win = MainWindow(); win.resize(1600, 900); win.show(); win.viewport.setFixedSize(W, H)
QTimer.singleShot(1500, run)           # start after the GL context exists; wrap run() in try/except -> app.quit()
t = Take(app, win, OUTDIR)             # window=True films the whole window instead of just the 3D view
```
`Take` API: `shoot(n)` render n frames · `hold(n)` repeat the last frame · `say(text)` set caption and add a mark · `scene(caption, line, action, seconds=None)` one narrated scene (action runs, then the picture is held until the sentence is spoken; set `Take.durations = {line: seconds}` first so scenes last as long as their sentence) · `glide(uv, frames)` move the cursor in sketch coordinates · `press(uv)` click · `type_number("60")`, `enter(hold)` type into the dynamic input · `move_event(px)`, `uv_to_px(uv)` · `fly(target, distance, az, el, frames)` camera move · `circle(...)` Smart Circle sequence · `encode(out)` (1280x720) / `encode_scaled(out)` (full-window frames to 1080p), both write `marks.json`.

Rules that matter:
- Drive the app through the same handlers a user triggers (`vp.set_sketch_tool("ROUNDED_RECT")`, key events via `t.type_number`, `doc.*` calls for steps that are not the point of the scene). Always `vp.setFocus()` after changing tool.
- Call `t.shoot(n)` after every input so the result is visible; a UI that changes without a rendered frame never shows up.
- Orbit or pan with a pure function of the frame counter (`vp.azimuth += 1.2; vp.update(); t.shoot()`), never wall-clock time.
- Never change the user's real Omarchy theme. The app's own theme scene should swap `theme.set_preview(...)` / `theme.set_fixed_theme(...)` colours and restore them.
- Do not touch the user's real settings file in scripts; tests use an isolated one (see `omacad.md`).

## Narration
- One sentence per scene, spoken by ONE cloned narrator voice. Voice text + seed are the voice: keep both fixed for a whole video (`tts.NARRATOR`, `--seed`). VoiceDesign alone invents a new person every sentence, so `tts.py` designs the voice once from `REF_TEXT` and clones it for every line.
- `lines_<name>.json`: JSON list, one entry per mark in order; `null` = silent. Counts must match `marks.json` (`narrate.py` asserts it).
- Audio is cached under `video/audio/` per text+voice+seed; edit a sentence and only that one is re-generated.
- A sentence longer than its scene is never cut: the next one starts after it. If the last one runs past the end, `narrate.py` warns: lengthen the last scene.
- 8 GB GPU: TTS sometimes runs out of memory; `tts.synthesize` retries after `POST /free`. If it keeps failing: `curl -XPOST localhost:8188/free -H 'content-type: application/json' -d '{"unload_models":true,"free_memory":true}'`. Generate music before narration, not at the same time.
- Music is mixed at 0.22 linear gain, ducked under the voice (sidechain), faded in/out, then loudness-normalised to -16 LUFS.

## Checklist before delivering
1. Watch the silent render first; fix timing in the take, not in ffmpeg.
2. Sentences are short, plain and describe what is on screen right now.
3. Narrated file duration equals the silent one (`ffprobe`).
4. Nothing personal in frame (file paths, other windows, tokens); the window is Omacad only.
5. Frames and `video/audio/` stay out of git.

## Known limits
- Takes need a real display and 10-20 minutes for the long tour (window mode renders each frame).
- The TTS/music graphs target specific ComfyUI custom nodes; if node names change, edit `_synthesize`/`reference` in `tts.py` and `generate` in `music.py` (they are plain API-format graphs).
- Imports in the examples assume the repo layout `omacad/` + `video/`.
