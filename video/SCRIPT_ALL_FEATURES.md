# Omacad: every feature (about 8.5 min, English)

Target: YouTube, 1920x1080, 30 fps, whole window (ribbon, tree, timeline). Voice by `tts.py`, music by `music.py`, mux with `narrate.py --music`. One sentence per caption; the scene lasts as long as its sentence. Chapters become YouTube timestamps. Narration is respelled for TTS ("Oh-mah-cad", "C A D", "Oh-mar-key").

Take column: an existing script that can be reused, or **NEW** (to be built on the `Take` class in `take.py`).

Times are estimates at about 140 words per minute and get replaced by `marks.json` after the first render.

## 1. Meet Omacad (0:00-0:50)

| # | Time | On screen | Narration | Take |
|---|------|-----------|-----------|------|
| 1.1 | 0:00-0:10 | Title card, slow orbit round a finished part | "This is Oh-mah-cad: a native, parametric 3D C A D for Oh-mar-key Linux. In this video we go through everything it can do." | tour_take (intro) |
| 1.2 | 0:10-0:25 | Whole window: ribbon with SOLID and SKETCH tabs, browser tree, timeline, viewport. Hover the groups CREATE, MODIFY, INSPECT | "The ribbon follows Fusion 360: Create, Modify and Inspect for solids, plus Constraints when you sketch. The tree on the left, the timeline at the bottom." | NEW |
| 1.3 | 0:25-0:40 | Tool dialog (Extrude) docks in the right-hand Inspector, the model stays visible | "Every tool opens in the inspector on the right, so a dialog never covers your model." | NEW |
| 1.4 | 0:40-0:50 | Three themes swapped live; then the Theme editor with a colour changed | "Omacad follows your Oh-mar-key theme and font. Or make your own in the theme editor and see every colour change live." | theme_take |

## 2. Sketching (0:50-2:35)

| # | Time | On screen | Narration | Take |
|---|------|-----------|-----------|------|
| 2.1 | 0:50-1:05 | Pick XY, then right-click a flat face > Create Sketch on this Face, then an Offset Plane | "Sketch on an origin plane, on any flat face, or on a plane you offset by an exact distance." | NEW |
| 2.2 | 1:05-1:20 | Line, rectangle, centre rectangle, circle, three-point arc, slot drawn quickly; snap markers show | "Lines, rectangles, circles, arcs and slots. Every tool snaps to corners, edges, midpoints and the grid." | NEW |
| 2.3 | 1:20-1:32 | Rounded Rect from the rectangle drop-down: two corners, radius in the palette | "The rectangle has a rounded variant: two corners, and the radius is already there." | plate_take |
| 2.4 | 1:32-1:45 | Polygon (P): click centre, Tab, type 6 sides, then 3 and 8 | "A regular polygon with three to sixty-four sides. Press Tab to type the side length and the number of sides." | tour_take (polygons) |
| 2.5 | 1:45-2:00 | Tool panel with sliders; Tab entry while drawing a line (length, angle) | "While you draw, type the exact length and angle. The tool panel shows what to do next and keeps your values." | NEW |
| 2.6 | 2:00-2:15 | Smart Circle: diameter, distance to one wall, distance to the other | "Smart Circle: type a diameter, then how far it sits from a wall on each axis. It is fully dimensioned as you go." | smart_circle_take |
| 2.7 | 2:15-2:30 | Right-click menu on a line: horizontal, tangent, distance. Sketch turns fully constrained | "Dimensions and constraints are solved by SolveSpace: horizontal, vertical, tangent, equal, midpoint, distance, angle and more." | NEW |
| 2.8 | 2:30-2:45 | Offset (O) on a chain, Trim (T), Mirror (Shift+M), Sketch Fillet (F) with a box-select of corners | "Offset a whole chain of curves, trim to the nearest crossing, mirror, and round many corners at once by dragging a box round them." | offset_thread_take + NEW |
| 2.9 | 2:45-3:00 | Sketch on a face: its edges appear as purple lines; offset them | "Sketch on a face and its edges come along as real lines you can offset, trim and snap to." | NEW |
| 2.10 | 3:00-3:15 | Text tool, a word in a frame, then Text On Path along a circle | "Add text like in Fusion, in a frame or along a circle, arc or line. The letters are real profiles, so the hole in an O stays a hole." | NEW |
| 2.11 | 3:15-3:30 | Canvas: drop a reference image on a plane, calibrate with two clicks and a known distance | "Insert a drawing as a canvas, adjust it, and calibrate it with a virtual tape measure." | NEW |

## 3. Making solids (3:30-4:50)

| # | Time | On screen | Narration | Take |
|---|------|-----------|-----------|------|
| 3.1 | 3:30-3:45 | Extrude with the drag arrow, then typed value; symmetric, To face | "Extrude by dragging the arrow or typing a value. One side, symmetric, two sides, or all the way to a face." | tour_take (extrude) |
| 3.2 | 3:45-3:55 | Extrude with Twist: a twisted vase | "Add a twist and the profile turns as it rises." | NEW |
| 3.3 | 3:55-4:10 | Revolve a profile round a construction line | "Revolve a profile around any line for vases, knobs and bottles." | tour_take (revolve) |
| 3.4 | 4:10-4:25 | Sweep along a path picked in the 3D view; Pipe | "Sweep a profile along a path you click in the 3D view, or make a pipe." | NEW |
| 3.5 | 4:25-4:35 | Loft from a rectangle to a circle, a smooth skin | "Loft between profiles, even from a rectangle to a circle." | NEW |
| 3.6 | 4:35-4:45 | Box, Cylinder, Hexagon, Sphere dragged out with blue handles; Taper angle | "Primitives for quick shapes, dragged out in the view, with an optional taper." | NEW |
| 3.7 | 4:45-4:55 | Split Body with a plane; Combine join, cut, intersect | "Split a body with a plane, or combine bodies by join, cut or intersect." | NEW |

## 4. Modifying (4:55-6:50)

| # | Time | On screen | Narration | Take |
|---|------|-----------|-----------|------|
| 4.1 | 4:55-5:10 | Fillet and Chamfer on edges, whole face click, corners where three meet are round | "Fillet and chamfer: click edges or a whole face, and corners where three fillets meet turn into a smooth ball." | tour_take (chamfer) |
| 4.2 | 5:10-5:20 | Press X for see-through, pick an edge inside a jar | "Press X to see through the part and reach edges on the inside." | NEW |
| 4.3 | 5:20-5:32 | Shell with open top, Inside / Outside / Both | "Shell makes a part hollow. Click the faces to leave open." | tour_take (section) |
| 4.4 | 5:32-5:47 | Move / Rotate Body (M), Face to face with Touch and Flush | "Move and rotate a body by numbers, or snap one face onto another." | NEW |
| 4.5 | 5:47-6:02 | Pattern / Mirror: rows and columns, around an axis, across a plane, circular feature pattern of a rib | "Pattern in rows, around an axis, or mirror across any plane. Even a rib with its fillet can be repeated in a circle." | tour_take (mirror) |
| 4.6 | 6:02-6:17 | Fill the face with hexagons, exact 1.5 mm gaps and a margin | "Fill the face packs a surface with exact gaps, edge to edge." | fill_take |
| 4.7 | 6:17-6:30 | Honeycomb cut into a cylinder wall, then Through | "Honeycomb cuts a pattern of cells into flat or round walls." | fill_take (cylinder) |
| 4.8 | 6:30-6:40 | Emboss then Deboss text on a mug | "Emboss raises text on a face, or deboss engraves it." | NEW |
| 4.9 | 6:40-6:50 | Thread and Coil on a cylinder | "Thread and coil wrap printable threads onto any cylinder." | tour_take (thread) |
| 4.10 | 6:50-7:05 | Jar with Lid: a threaded jar and a screw lid made at once | "Jar with Lid makes a threaded jar and a matching lid in one go." | jar_lid_preview_take |

## 5. Inspecting (7:05-7:30)

| # | Time | On screen | Narration | Take |
|---|------|-----------|-----------|------|
| 5.1 | 7:05-7:17 | Measure (I): two edges, distance and angle | "Measure lengths, diameters, distances and angles, in the sketch and on the solid." | NEW |
| 5.2 | 7:17-7:30 | Section View slides through the part | "Slide a section plane through the model to see inside." | tour_take (section) |

## 6. Parametric history (7:30-8:20)

| # | Time | On screen | Narration | Take |
|---|------|-----------|-----------|------|
| 6.1 | 7:30-7:42 | Parameters dialog; a field with `width/2` | "Name your parameters and use formulas in any field." | NEW |
| 6.2 | 7:42-8:00 | Timeline: click a step to see its change in green and red, roll back, suppress a step, edit the first sketch and everything rebuilds | "The timeline shows what each step changed. Roll back, suppress a step, or edit the first sketch and the rest follows." | NEW |
| 6.3 | 8:00-8:12 | Ctrl+Z several times, Ctrl+Shift+Z | "Undo covers everything, not only sketches. Your work is never lost." | tour_take (undo) |

## 7. Files and the end (8:12-8:50)

| # | Time | On screen | Narration | Take |
|---|------|-----------|-----------|------|
| 7.1 | 8:12-8:25 | Import 3MF, export STEP, STL, OBJ; save as .omacad | "Import 3 M F, export STEP, STL or OBJ for your slicer and other C A D, and save with the full history." | NEW |
| 7.2 | 8:25-8:40 | F10: type the problem, screenshot goes to the agent, a fix appears | "Press F10 to report a problem. Omacad sends a screenshot, the model and the log to your Oh-mar-key AI agent, which fixes the code." | tour_take (report) |
| 7.3 | 8:40-8:50 | End card, orbit | "Oh-mah-cad is open source and free. Try it, and tell us what you want next." | tour_take (end) |

## Takes to build (priority)

1. Sketch tools, Tab entry and constraints (2.2, 2.5, 2.7, 2.8, 2.9): the core of the video.
2. Sweep/Pipe, Loft, Twist, primitives, Split/Combine (3.2 to 3.7).
3. Move/Rotate, Emboss, X see-through, Measure (4.2, 4.4, 4.8, 5.1).
4. Text, Canvas, parameters, timeline, file formats, UI tour (1.2, 1.3, 2.1, 2.10, 2.11, 6.1, 6.2, 7.1).

Check against `CHANGELOG.md` before filming: sweep, loft and fillet change often (latest 0.9.9.80.17), so verify each scene in the running app first.
