# Omacad – progress and roadmap

- Sketch Offset supports open and closed splines with independent sampled copies, preview and undo (0.9.9.80.69).

- Canvas placement on planar body faces through the face context menu and placement list (0.9.9.80.64).

- Linear Pattern preserves hollow bodies and fillets in preview and committed copies (0.9.9.80.63).

- Hollow Loft profiles and an editable profile list with add/remove/reorder (0.9.9.80.62).

- Leaning-rib fillet whole, shoulder circles whole, emboss wall behind a fillet, parallel tests (0.9.9.80.45).
- Readable value boxes, faces closed by lines on a circle, browser dimension highlight, Construction menu, 45°/90° snaps, hidden bodies untouched (0.9.9.80.44, #91–#99).
- Readable sketch palette, grey finished sketches (0.9.9.80.43, #89 #90).
- Theme choice trimmed to Studio, Graphite, Atelier and Follow Omarchy (0.9.9.80.42).
- Own icon per rectangle kind, shown on the ribbon button for the default (0.9.9.80.41).
- Graphite and Atelier themes (0.9.9.80.40); pencil to edit browser values (0.9.9.80.39).
- Browser fits its rows instead of filling the window height (0.9.9.80.38).
- Studio line icons for every command, menu, tree row and history step (0.9.9.80.37).
- Studio theme and Studio line icons from the appearance proposal, selectable in Settings (0.9.9.80.36).
- Redesigned settings navigation and section cards with theme-aware styling (0.9.9.80.35).

- Ground grid remains behind bodies from below; chamfer outlines keep continuous rims and whole planar/curved faces even with overlapping edge selections (0.9.9.80.34).

- Fixed false crease lines after chamfering curved outlines by retaining double precision in topology and outline tools (0.9.9.80.33).

- Circular Feature Pattern: selected rib + fillet groups, picked/world axes, partial/full circles and timeline selection/editing (0.9.0).

Current version: **0.8.0** (see `CHANGELOG.md`). Goal: behave like Fusion 360 wherever it makes sense; 1.0 = a complete, dependable CAD.

Native parametric 3D CAD for Omarchy (Hyprland/Wayland). Python 3.14, PySide6 + OpenGL, manifold3d, shapely, SolveSpace.
This file lists what has been built, step by step, and what is left. (Swedish feature overview: `README.md`.)

## Done

- Sketch rotation with selectable area/face/origin/custom pivots, live preview, point snapping, and undo/redo (0.8.0).

### 1. Foundation
- Fusion-style UI: ribbon (SOLID / SKETCH), browser tree, timeline bar, ViewCube, OpenGL canvas with edge lines, themed from the active Omarchy theme and font.
- Parametric taper angle for Box/Cylinder, including constant-thickness shells and timeline editing.
- Numeric sliders throughout docked tool panels, retaining exact numeric and formula entry.
- Hollow primitives through Shell Wall in the Box / Cylinder / Hexagon panels (the separate Shelled Box / Shelled Cylinder presets were removed in 0.9.9.9).
- Direct dimension handles with live previews for box, cylinder and sphere creation.
- Primitives (box, cylinder, sphere), Combine (join / cut / intersect), STL/OBJ export, `.omacad` project files (JSON, atomic save).

### 2. Sketching
- Sketch on origin planes, on any flat body face (right-click → *Create Sketch on this Face*) and on offset planes.
- Tools: line, 2-point rect, centre rect, circle, 3-point arc, slot, **regular polygon** (`P`, side count + side length, stays regular).
- Snapping to points, midpoints, grid and all body face edges. Tab-entry of dimensions while drawing; Enter/Esc behaviour like Fusion.
- Select / move / delete, undo / redo for sketch changes, sketch visibility (eye), rename (F2).
- Constraints via SolveSpace: horizontal, vertical, parallel, perpendicular, equal, tangent, concentric, coincident, fixed, point-on-circle.
- Dimensions as real constraints: length, distance (H/V/aligned), point-to-line, angle, diameter; guided right-click menus; measuring from circle/polygon centres; formulas and named parameters in every field.
- **Offset (`O`)** like Fusion: a click takes the whole connected chain, click more to add, Enter = distance with live preview. **Trim (`T`)**, sketch **Mirror (`Shift+M`)**, Shift/Ctrl multi-select. **Measure (`I`)** for lines, circles and body edges.
- **Face edges as sketch elements**: sketching on a face includes its outline (lines, circles, arcs) as real, purple elements; *Project (edges)* does it in any sketch.
- **Fillet (`F`)** of sketch corners with tangent arcs and parametric radius dimensions; Shift+click picks several corners for one radius.

### 3. Solids
- **Extrude**: draggable arrow *and* typed value, one side / symmetric / two sides, *To face…*, Auto / New / Join / Cut / Intersect, live preview, manual profile selection (Shift+click to add/remove; nothing auto-picked), extrude a whole face. Profiles with holes now extrude correctly.
- **Fillet / Chamfer**: straight edges, full circles (screw holes, countersinks), whole outlines with rounded corners (also radii larger than the corners), inside and outside corners, double-click selects a loop, live preview.
- **Pattern / Mirror**: linear, mirror (auto: corners / round bodies along the diameter with N evenly spaced copies), circular, and **Fill the face** (fixed gap, edge margin / frame, grid or honeycomb, partial copies cut at the frame, avoids bosses and other features on the face), all with live preview.
- **Jar with Lid**: threaded jar + screw lid generator (sizes, pitch, profile, thread tolerance -0.2 by default, sliders, live preview); builds ordinary editable steps, one undo step; lid laid out upside down for printing.
- **Honeycomb**: hexagon / circle / square / diamond / triangle cells cut into picked flat and cylindrical faces (inside or out), cell size, wall, edge margin, depth or Through (to the air behind each cell), rotation, optional cut cells at the edge; placed for the most whole cells and closed seamlessly round a cylinder.
- **Revolve** (axis = construction/any sketch line or sketch X/Y axis, angle, one side / symmetric / two sides, Auto/New/Join/Cut/Intersect, live preview).
- **Shell**: Inside / Outside / Both, open faces (outer skin trimmed flush).
- **Hole** exists as a model feature (simple / counterbore / countersink, flat or 118° tip, through); dialog and placement are next.
- **Offset Plane** (pick XY/XZ/YZ, then any surface incl. cylinders), **Section View** (draggable offset, saved in the tree, toggled with the eye).

### 4. Parametric history
- Timeline editing (click a step to colour what it changed, double-click to edit it, roll back, suppress), parameters with formulas, automatic hiding of used sketches, delete/suppress with downstream rebuild.
- Robustness: sliver clean-up after booleans, zero-area triangle handling in the renderer.

- Fillet/Chamfer robustness: see-through edge picking, loop on the other face, moved edges are re-matched after upstream edits, inside corners are mitred, no notch at the foot of rounded corners.

### 5. UX
- All tool dialogs dock in a right-hand panel so the model is never covered.
- Context menus on faces, sketch elements, tree items; icons enlarged; themed with Omarchy.
- **Settings (`Ctrl+,`)**: Persistent inställningar i `~/.config/omacad/settings.json`. Konfigurerbara färger för 3D-extrude pilar, mätverktyg (I), aktiva sketchlinjer, konstruktionslinjer, highlight, inverterat mushjul, standard-radie för fillets samt placering och autogömning av sketch-paletten.

### 6. Project and web
- Private repo `bjornkindstrom/omacad`; screenshots in `screenshots/`.
- Project page on kindstrom.duckdns.org (admin in `~/Work/kindstrom-site`).

## Remaining

**The forward plan (milestones 0.6 to 1.0, the smart-features track, safety net and AI feedback loop) lives in [`PLAN.md`](PLAN.md).** The list below is the older gap list, kept for reference.

Priorities follow what Fusion 360 users reach for first.

### Next up
- **Hole** dialog (`H`): click to place on a face with snapping to circle centres, type/extents, live preview.
- **Extrude**: Taper angle, Start (profile plane / offset / object), extent *All* / *To object*.
- **Press/Pull** (`Q`): context sensitive (profile → extrude, edge → fillet, face → offset face).
- **Global undo/redo** (today only sketch edits), Delete key for bodies, Move/Copy, copy-paste.
- **Viewport**: orthographic camera, display styles (wireframe, shaded + edges), Home view.

### Sketching
- Extend, Break, Project of *selected* geometry, Scale, Stretch, rectangular/circular pattern in a sketch, ellipse, spline, more arc and circle modes (centre arc, tangent arc, 2/3-point circle, 2-tangent circle), text.
- Arcs and slots inside the constraint solver (radius/angle dimensions, tangent arcs); symmetric, midpoint, collinear and smooth constraints.

### Solids
- Sweep, Loft, Rib/Web, Draft, Scale, Thread, Torus/Coil/Pipe primitives, variable fillet, fillet of cones and partial arcs.
- Choose target bodies for Join/Cut; Align, Offset Face, Split Face.
- Face sketches and offset planes associative with the body (today they are absolute).

### History and files
- STEP / IGES import and export (OpenCASCADE), assemblies and joints, CAM / G-code, appearance/material.

### Quality
- Automated tests (today verified with scripted GUI runs on the real display and exact-volume checks).
