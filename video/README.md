# Intro video: status and handover

Everything here was written in a cloud session **without a screen or PySide6**, so nothing has been run yet. Fix it up on the real machine (Wayland).

## Files
- `plate_take.py`: rounded rectangle, Smart Circle hole, extrude, chamfer, Mirror to four corners (about 25 s). Writes `video/plate/marks.json` (frame of every caption).
- `take.py`: shared frame-exact capture helper (`Take`: `say`, `glide`, `press`, `type_number`, `enter`, `fly`, `encode`).
- `tts.py`: **local text to speech** through ComfyUI (Qwen3-TTS VoiceDesign, 1.7B). Needs the Comfy desktop app running; keeps one voice by fixing voice text + seed. Tested 2026-10-12, a Whisper round trip returned the exact sentences. Uses `attention: sdpa` and `max_new_tokens: 512`: with the default the 8 GB GPU ran out of memory. If it still does, `curl -XPOST localhost:8188/free -H 'content-type: application/json' -d '{"unload_models":true,"free_memory":true}'`.
- `narrate.py` + `lines_plate.json`: one sentence per caption (null = silent), spoken with `tts.py`, placed at the caption's frame and muxed onto the video. Cached per text+voice+seed in `video/audio/`.
  `.venv/bin/python video/plate_take.py --out ~/Videos/omacad-plate-holes.mp4` then `.venv/bin/python video/narrate.py video/plate/marks.json ~/Videos/omacad-plate-holes.mp4 ~/Videos/omacad-plate-holes-narrated.mp4 --lines video/lines_plate.json`
- `smart_circle_take.py`: **Smart Circle demo, run and working (2026-10-12)**. Drives the real viewport with mouse and key events (type diameter, Enter, distance to a vertical line, Enter, distance to a horizontal line, Enter), draws cursor and captions on each frame and encodes with ffmpeg. Frame-exact, no screen recorder. `.venv/bin/python video/smart_circle_take.py --out ~/Videos/omacad-smart-circle.mp4` (about 21 s, 1280x720). Copy it for other tool demos (the `Take` class has `glide`, `type_number`, `enter`, `say`).
- `pan_take.py`: **frame-exact camera pan** over the finished part, one take per Omarchy theme (`--themes a,b,c,d,e`). The camera is a pure function of the frame number and frames are rendered with `grab()` to PNG, so every take has identical motion and lines up frame for frame; cross-dissolve between takes in the editor (or ffmpeg `xfade`) for the theme transition. Edit `START`/`END` at the top for the move. Output in `video/pan/` (git-ignored).
- `SCRIPT.md`: scene table (time, on screen, narration), recording prep, YouTube title/description/thumbnail ideas.
- `record_demo.py`: drives the real `MainWindow` through the scenes with captions. `--record` starts `wf-recorder` (-> `omacad_demo.mp4`), `--speed 1.5` for rehearsal.
- `comfyui_prompts.md`: image prompts for the title card, end card, thumbnail and b-roll.

## Demo flow (scene functions in `record_demo.py`)
1. `s1_title` caption + home view
2. `s2_sketch` centre rounded rect (60 x 40 mm, r 6) on XY
3. `s3_extrude` finish sketch, extrude 10 mm, orbit
4. `s4_hole` one hole (r 2.5) near a corner, `s4b_mirror` Mirror (`mirror_mode="xy"`) to all four corners, `s4c_fill` hexagon cut + Fill pattern (gap 1.5, margin 4, `stagger`)
5. `s4d_edit` edit the first sketch (80 x 40, r 10), Finish Sketch, everything rebuilds
6. `s7_theme` switches 3 Omarchy themes live (`omarchy-theme-list`/`omarchy-theme-set`), `s7b_theme_back` restores yours
7. `s5_section` Section View, `s6_undo`/`s6b_redo`, `s8_end`

## Known issues / to check on the machine
- Never run. Expect API mistakes in `record_demo.py`; run with `--speed 3` first.
- Fill pattern parameters (`spacing1/2`, `mirror_mode="stagger"`) are guessed from `timeline.py`; compare with the Pattern dialog.
- `s4d_edit`: the hole sketches do not move, so after widening the plate the holes are no longer at the corners. Either edit the hole sketch too or choose a smaller change.
- Holes and hexagon are sketched on the XY plane, not on a face; `SCRIPT.md` scene 4 mentions sketching on a face. Consider a real face sketch (`start_sketch_on_plane(SketchPlane.centered_on(...))`).
- Fillet scene (5 in the table) is not automated; `add_fillet` needs edge refs.
- F9 scene is manual (starts the real agent).
- Turn off `auto_restart` before recording, or a commit restarts the app mid-take.
- Window must be 1920x1080 (`hyprctl dispatch resizeactive exact 1920 1080`).
- Caption bar is a plain QLabel; restyle to the theme if wanted.

- Theme scene: not run; it changes your real desktop theme for ~11 s and restores it afterwards (if it crashes mid-way, run `omarchy-theme-set <yours>`). Check that the viewport background, ribbon and tree all update (`ThemeWatcher` in `omacad/ui/theme.py`); anything that does not is a bug worth fixing before filming.

## Next steps
1. Run, fix, tune the hold times in `SCENES`.
2. Record with `--record`, record the voice-over after the finished picture.
3. Generate images with `comfyui_prompts.md`, cut together, upload.

## Scenes still missing (added 2026-10-12, features newer than the script)
Smart Circle (done, see above), rounded rectangle with radius after width/height, polygon Fill pattern for 3-8 sides (honeycomb, paired triangles), Measure (I), Move/Rotate body with Lay on plane, global undo across features, F9 report with marked-up screenshot, Offset with arc chains. Reuse `smart_circle_take.py`'s `Take` class for each.
