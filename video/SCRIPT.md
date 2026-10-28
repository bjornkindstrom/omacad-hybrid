# Omacad intro video: script (about 2 min, English)

Target: YouTube, 1920x1080, 30 fps. Record with `video/record_demo.py` (drives the real app, shows captions, optionally starts `wf-recorder`), then add the voice-over in any editor. Narration is timed to the on-screen steps in the script; each scene has a number that matches `SCENES` in `record_demo.py`.

| # | Time | On screen | Narration |
|---|------|-----------|-----------|
| 1 | 0:00-0:10 | Empty Omacad window, then the title card "Omacad: native parametric CAD for Omarchy" | "This is Omacad, a native parametric 3D CAD for Omarchy Linux. Fast, keyboard-friendly, and it follows your theme." |
| 2 | 0:10-0:30 | New sketch on the XY plane. A centre rounded rectangle is drawn (60 x 40 mm, 6 mm corners) | "Start the way you would in Fusion 360: pick a plane and sketch. Rectangles come with rounded corners built in, and every tool snaps to what is already there." |
| 3 | 0:30-0:45 | Finish Sketch, Extrude 10 mm. The orbit camera turns around the block | "Finish the sketch and extrude it. Everything is a step in the timeline, so you can always go back." |
| 3b | - | Smart Circle (`smart_circle_take.py`): type the diameter and the distances to two walls, circle appears fully dimensioned | "Type a diameter, then how far it sits from a wall on each axis. The circle is dimensioned as you go." |
| 4 | 0:45-1:05 | One 5 mm hole cut near a corner, then Pattern/Mirror copies it to all four corners in one step | "Cut one hole, then mirror it: the same hole lands in all four corners with a single step." |
| 4b | 1:05-1:20 | Hexagon cut, then Fill the face (honeycomb layout, 1.5 mm gaps, 4 mm margin) | "Fill the face: draw one hexagon and Omacad packs the whole surface with exact gaps, edge to edge." |
| 4c | 1:20-1:30 | Edit the first sketch (plate 60 -> 80 mm wide, rounder corners), Finish Sketch: the holes and the hexagon fill rebuild to match | "Everything is parametric. Go back to the first sketch, change it, and the holes and the pattern follow." |
| 5 | 1:05-1:25 | Fillet on the block edges, then a Section View slides through the part | "Round the edges with fillet or chamfer, and slide a section plane through the model to check the inside." |
| 6 | 1:25-1:40 | Ctrl+Z three times, then Ctrl+Shift+Z: the model steps back and forward | "Undo covers everything, not only sketches. Your work can never be lost." |
| 6b | 1:40-1:50 | Three Omarchy themes switched live with `omarchy-theme-set`; the ribbon, tree and viewport change colour without a restart, then the original theme returns | "Switch your Omarchy theme and Omacad follows instantly: colours, fonts, everything." |
| 7 | 1:40-1:55 | F9 dialog "Report problem", typed text, the agent window | "Found a bug or want a feature? Press F9. Omacad sends a screenshot, your model and the log to your AI agent, which fixes the code, and the app restarts on the new version with your work intact." |
| 8 | 1:55-2:05 | Home view, end card with the GitHub URL | "Omacad is open source and free. Link in the description. Thanks for watching." |

## Before recording

- Use a clean Omarchy theme and a 1920x1080 window (`hyprctl dispatch resizeactive exact 1920 1080`).
- Set `auto_restart` off in Settings so a commit does not restart the app mid-take.
- Run the script (see below); record the voice-over after, to the finished picture.

## Recording

```bash
.venv/bin/python video/record_demo.py              # just play the demo
.venv/bin/python video/record_demo.py --record     # also run wf-recorder -> video/omacad_demo.mp4
.venv/bin/python video/record_demo.py --speed 1.5  # faster pace while rehearsing
```

Scene 7 (F9) is not automated, since it starts your real agent. Record it by hand and cut it in.

## YouTube

- Title: "Omacad: a native parametric CAD for Omarchy Linux (intro)"
- Description: what it is, link to the repo, the shortcuts shown (P polygon, O offset, T trim, F fillet, F9 report), chapters from the table above.
- Thumbnail: the finished block with the hole on the dark theme, large text "Native CAD".

## Theme transition shot (pan_take.py)

Render 5-7 takes with the same camera move, one per theme:

```bash
.venv/bin/python video/pan_take.py --themes tokyo-night,catppuccin,gruvbox,nord,rose-pine --seconds 6
```

Because the takes are frame-aligned, put them on one track each in the editor and cross-dissolve (or wipe) at the same timecode, or chain them with ffmpeg:
`ffmpeg -i a.mp4 -i b.mp4 -filter_complex "xfade=transition=fade:duration=0.6:offset=2.7" out.mp4`.
Best look: dissolve mid-pan while the camera is moving fastest (about 50 %), so the colours change while the part keeps turning.
