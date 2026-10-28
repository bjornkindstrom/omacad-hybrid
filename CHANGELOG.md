# Changelog

## 0.9.9.80.70 - 2026-10-28

### Performance
- Fillet & Chamfer speedup: vectorized normal and flat-patch classification in OpenGL render mesh extraction (`CadKernel._flat_triangles`), reducing analysis time by ~25x and cutting full-box fillet rebuild time by over 80%. Replaced sequential cutter/filler unions with Manifold3D's native `batch_boolean` for faster CSG execution without losing any geometric quality.
- Compact Spline Offsets: aggressive sparse-fitting (`_fit_offset_spline`) aiming for 6–8 control points on open splines while preserving smooth curve geometry and curvature. Dramatically reduces point density (down from 70–120 points to 6–8 points) making offset curves clean, responsive, and easy to edit.

## 0.9.9.80.69 - 2026-10-27

### Fixed
- Construction button (#125): the ribbon button now always mirrors the real construction mode, and the mode resets when a sketch ends, so the button no longer looks off while construction is on. The checked state already has a distinct fill (`QToolButton:checked`) in the themes checked, so no extra `suggested` style was added.
- Micro-facet sliver cleanup on chamfers and boolean operations: tightened facet topology classification (`SLIVER_AREA = 0.03 mm²`, `SLIVER_MIN_WIDTH = 0.04 mm`) so hair-thin slivers and leftover chips where chamfers meet threads/cuts no longer fragment planar faces into clickable micro-slivers.

### Added
- Body color & Appearance picker: Right-click any 3D body in the browser or directly on a body face in the 3D viewport to choose "🎨 Appearance / Färg…". Opens a full color picker dialog with an "Återställ till ofärgad (Reset)" button to quickly restore the default solid appearance. Color customizations support full undo/redo, timeline recomputation, and file save/load.
- Unconnected endpoints indicator and drag-to-join: open/unconnected endpoints of sketch curves show an orange endpoint dot. Clicking and dragging the dot stretches the endpoint (with magnetic snap to nearby points/lines) and automatically creates a COINCIDENT constraint when dropped on another endpoint, making the dot disappear as the loop closes.
- Fully constrained sketches are now drawn with black lines (Fusion 360-style) instead of cyan when degrees of freedom reach 0 (`dof == 0`). A subtle light rim keeps the black lines crisp on dark canvas/models.
- Spline point editing and tangent handles (#130): selected splines show fit points and green circular tangent handles (Fusion 360-style). Dragging fit points moves them; dragging tangent handles adjusts the curvature vector. Double-clicking a spline or right-clicking "Insert Fit Point" adds new points along the curve.
- Sketch Offset now supports splines with sparse fit-points: independent sampled spline copies with preview, save/load and undo. Fit points are kept compact and clean without point-count explosion on small or large offsets. Positive distances offset open curves to the left and closed curves outward; collapsed offsets leave the sketch unchanged.
## 0.9.9.80.68 - 2026-10-26

### Added
- Hole command: place one or more holes on a planar face or origin plane; supports simple, counterbore and countersink forms, depth or through-all, drill point, and optional entrance chamfer.
- Sketch spline tool: click through-points and finish with Enter, double-click, or right-click; Esc cancels. Curves preview while drawing and are saved with the sketch.

## 0.9.9.80.67 - 2026-10-26

### Added
- Symmetric sketch constraint: select two lines (or two circles) and a third line as the mirror line; the two are mirrored across it, e.g. to centre a rectangle between two sides. Ribbon button in the Constraints dropdown, Studio icon `c_symmetric`.

## 0.9.9.80.65 - 2026-10-26

### Added
- Sketch Palette toggle to show or hide construction geometry (#124): a new "Show Construction" checkbox toggles visibility and hit testing of dashed construction lines and circles during sketch editing.

### Fixed
- Shell on chamfered rotated cylinders (#88): filtered out microscopic sliver triangles from convex facet planes to prevent unintended chord planar cuts through cylindrical inner cavities.
- ViewCube Home icon visibility in light themes (#113): Home icon pen now renders with high contrast against the light theme button background.
- Sketch plane world axis naming in Revolve (#114) and Move tool (#122): axes are labeled according to their corresponding 3D world axes (e.g. X and Z on XZ plane, Y and Z on YZ plane) instead of assuming default XY names.
- Sketch entity selection visibility in Studio theme (#115): selected sketch lines and curves now use an unmistakable high-contrast highlight color and distinct halo.
- Persistent dimension entity highlight after sketch exit and extrusion (#116, #117): cleared lingering dimension entity picks upon leaving a sketch, starting new operations, or pressing Escape so they do not show up as selected edges on 3D bodies.
- Dialog button text truncation in Studio theme (#118): adjusted button padding and set minimum widths so labels like "Send request" and "OK" fit comfortably without clipping.
- Unicode parameter name autocomplete in expression fields (#119): parameter name pattern now supports Swedish and Unicode characters (e.g. matching `Längd` when typing `Lä`).
- Studio canvas background brightness and grid visibility (#120, #121): lightened the canvas background, increased grid line contrast, and sharpened origin axes lines with positive and negative directions for better orientation.
- Sketch arc trimming at endpoint intersections (#123): improved sweep and boundary angle tolerance in trim calculations so arcs meeting at junctions cut correctly instead of dropping the entire arc.
- Report problem and Request change bundle cleanup: save only marked or single window screenshot in reports to keep RFC and bug report sizes efficient.

## 0.9.9.80.66 - 2026-10-26

### Changed
- Sketch constraints are one Constraints ▾ dropdown with full-size icons instead of the cramped 2-row grid (Settings > Sketch & View: turn off for one button per constraint).

## 0.9.9.80.64 - 2026-10-25

### Added
- Insert Canvas on a planar body face from its context menu or the Canvas placement list. Face placement is centered on the face and preserved through editing, save/load and undo/redo; images blend over the body surface.

## 0.9.9.80.63 - 2026-10-25

### Fixed
- Linear Pattern copies a selected hollow body with its holes and fillets instead of interpreting its void as a cut that disappears on OK (report 20261025-220532).

## 0.9.9.80.62 - 2026-10-25

### Fixed
- Loft preserves inner contours instead of filling hollow profiles (report 20261025-210210). Mismatched hole counts report an error.

### Added
- Loft profile list with Add, Remove and reorder controls, also available through Edit on an existing Loft step.

## 0.9.9.80.61 - 2026-10-25

### Changed
- Things follow their moved object (Björn): every Move step remembers where it put the body, so what belongs to an earlier step of the same object is shown where the body is now: a finished sketch (also when flashed from the timeline or lit by a dimension picked in the browser), what a step added or removed when it is clicked, the edges a Fillet/Chamfer rounds, and Find in Window on a sketch. Stepping the history back shows them where they were then.

## 0.9.9.80.60 - 2026-10-25

### Fixed
- A green face was left behind where a body used to be (#112): after moving a body (with the arrows or any other way) the face that was lit under the mouse stayed lit at the old place. The hover now lets go when the document changes, and a face counts as the same only when it is the same geometry, not just the same number.

## 0.9.9.80.59 - 2026-10-25

### Added
- Line up with a face while moving (Björn): while sliding a body with a move arrow, point at a flat face of another body that lies across the arrow's axis; the body jumps so its near or far side is flush with that face (the face lights up and the value says "flush"). Let go to keep it.

### Fixed
- The up/down move arrow was missing on flat bodies: it was left out when the body was thin on screen instead of only when the axis points at the viewer.

## 0.9.9.80.58 - 2026-10-25

### Added
- Move arrows on the selected body (#111): beside the rotate arrows, a straight double arrow per axis (X red, Y green off the front sides, Z blue above) slides the body along that axis in whole millimetres (Shift: 0.1 mm). The distance shows while dragging, Esc cancels, and letting go makes one Move step.

## 0.9.9.80.57 - 2026-10-25

### Added
- Favorites in the browser (#110): right-click a value in the browser (a step's size, a sketch dimension or a sketch text) and choose Add to favorites, into an existing group or a new one (named after the object by default). The starred values gather under ⭐ Favorites, grouped, and can be changed right there with the pencil or a double-click, for example the name on each of three hooks. F2 renames a group; right-click removes a value or a whole group. Saved with the document; every change is one undo step.

## 0.9.9.80.56 - 2026-10-25

### Added
- Rotate handles on the selected body (#107), like Layerling: a curved arrow per axis (X red, Y green on top edges, Z blue on the left upright edge). Drag one to turn the body about its centre in 15° steps (hold Shift for free angles); the angle shows while dragging, Esc cancels, and letting go makes one Move step (Ctrl+Z undoes).

## 0.9.9.80.55 - 2026-10-25

### Fixed
- A chamfer or fillet follows a hole that is moved (#105): moving a hole by its sketch dimension left the chamfer cutting a cone where the hole used to be. The edges of a body were remembered by its size and volume, which do not change when a hole moves inside a plate, so the chamfer got the old hole's edges. They are now remembered by the exact shape.

## 0.9.9.80.54 - 2026-10-25

### Added
- Margin for Text In Box (#109): a Margin field in the Text panel (only for Text In Box) keeps room free between the text and each side of the box, so the text gets a little smaller and stays centred. Saved with the sketch.

## 0.9.9.80.53 - 2026-10-25

### Added
- Size of the selected body (#106): a selected body shows its length, width and height as dimension arrows beside it (two floor edges nearest the viewer and one upright edge). With several bodies selected it shows the box around all of them.

## 0.9.9.80.52 - 2026-10-25

### Changed
- Move with Activate copy makes a full copy of the object (#108): the copy gets its own sketches and steps (Extrude, Fillet, Chamfer, ...) as a new object, and then the move. Every parameter of the copy can be changed without touching the original. Older files keep their plain copies.

## 0.9.9.80.51 - 2026-10-25

### Added
- Move to new object (#103): right-click a step in the browser (for example the sketch of a lid drawn on a box's rim) and choose Move to new object. It gets an object of its own, with the later steps that only build on it; the model itself does not change. One undo step; F2 renames the new object.

## 0.9.9.80.50 - 2026-10-25

### Fixed
- Project on a face made by Shell or Extrude takes the whole face (#103): on the rim of a shelled box it now brings in the inner outline and the screw holes as well, not only the outer outline. The outline is read from the face itself, and no hair-thin extra profiles are left beside the projected lines.

## 0.9.9.80.49 - 2026-10-25

### Added
- Measure works on flat faces (#102): one face gives its area; two parallel faces the distance between them, two faces at an angle the angle; a face and an edge give the distance (parallel edge) or the angle, a face and a circle the centre-to-face distance. D (set distance) also works between faces of two bodies.

## 0.9.9.80.48 - 2026-10-25

### Changed
- Fillet/Chamfer on an outline of straight pieces and arcs (#104): a click takes just the piece under the mouse, so you can bevel a couple of edges and leave the rest; Ctrl+click removes a piece; double-click still takes the whole outline. With Tangent chain on, smoothly joined pieces come along.

## 0.9.9.80.47 - 2026-10-25

### Added
- Dimensions can be deleted (#101): right-click a dimension's value in the view or its row in the browser and choose Delete dimension, or press Del with the mouse over the value (or with the dimension picked in the browser). One undo step; the geometry stays and becomes free.

## 0.9.9.80.46 - 2026-10-25

### Fixed
- A Smart Circle measured from a rounded rectangle's wall follows the wall when the size changes (#100). The distance had been tied to the rounded corner's guide line, which the solver moved instead of the circle; such distances (also in saved files) now measure from the wall itself.

## 0.9.9.80.45 - 2026-10-25

### Fixed
- A fillet at the foot of a leaning rib no longer leaves the band as a loose piece: fill tools reach a hair into the material.
- Inner shoulder circles split by a boolean come back as one whole circle instead of a loop plus a gapped arc.
- Emboss finds the cylinder wall behind a fillet again: sliver triangles are ignored and the wall axis is chosen by area.

### Changed
- The last three edge tests that checked float32 mesh artefacts are rewritten to check the real result; no known failures remain.
- Tests run in parallel (pytest-xdist): the whole suite takes about 2.5 min instead of 25.

## 0.9.9.80.44 - 2026-10-25

### Fixed
- Value boxes in the view (Smart Circle, line length/angle, measure, constraint badges) show their text in every theme; it was white on a white box in Studio (#91, #95, #96).
- Lines that end on a circle or arc close the region between them into a face (#93).
- Hidden bodies are left alone: an Extrude/Revolve cut or join no longer touches a body you have hidden (#99).

### Changed
- A finished sketch no longer draws the face edges it included in purple; they only show while editing (#92).
- Clicking a dimension in the browser lights up the sketch elements it measures in the view (#94).
- Construction has a dropdown: Construction Line or Construction Circle starts that tool straight away (#97).
- Lines snap to 45°, and to 90°/45° against the line they continue from, with a small angle label at the cursor (#98).

## 0.9.9.80.43 - 2026-10-25

### Fixed
- Text in the sketch palette is readable: every label there got its own small box (QLabel is a QFrame) and 11 px text; the Smart Circle hint and the checkboxes now read as normal text in Studio, Graphite and Atelier (Björn #89).
- The theme editor no longer drops the look of Studio/Graphite/Atelier while it previews (the whole app fell back to the old style and a monospace font); its starting points are now the three themes.
- Inspector status text (fully defined, selection) uses the theme's colours instead of light green/blue that was hard to read on white. "Theme" colour swatches pick dark or light text by their colour.

### Changed
- Finished sketches are grey (a theme grey, lighter on dark views) without the dark rim, and their helper lines are quiet grey dashes; Settings > Appearance > "Finished sketches" picks another colour (Björn #90).

## 0.9.9.80.42 - 2026-10-25

### Changed
- Settings > Appearance offers Studio, Graphite, Atelier and Follow Omarchy (plus themes made in the theme editor). The older choices (Fusion 360, Light, Tokyo, Nord) are gone; a saved older choice opens as Studio. Reset to defaults goes back to Follow Omarchy.

## 0.9.9.80.41 - 2026-10-25

### Changed
- Each rectangle kind (2-Point, Center, Rounded, Center Rounded) has its own icon in every icon set: the ribbon button shows the kind it draws by default, and the rectangle menus (button dropdown, "Button default", right-click Rectangle) show the same pictures.

## 0.9.9.80.40 - 2026-10-25

### Added
- Graphite (dark, amber accent, compact 3 px corners) and Atelier (warm grey, forest green accent, soft 14 px corners) from the appearance proposal, next to Studio in Settings > Appearance. They share Studio's layout, panels and line icons; each theme brings its own colours, corner radius and readable text on its accent colour.

## 0.9.9.80.39 - 2026-10-25

### Fixed
- Editing values in the browser is reliable: every editable value row has a pencil that opens the editor with one click, a double-click on an already selected row opens it too, and the tree no longer rebuilds (closing the editor) while a value is being typed.

## 0.9.9.80.38 - 2026-10-25

### Changed
- The browser is only as tall as its visible rows and grows when a branch is opened, leaving more of the drawing area free; it fills the height and scrolls only when the rows need it.

## 0.9.9.80.37 - 2026-10-25

### Changed
- Studio icon set covers every function: each ribbon command, dropdown, constraint, menu entry, right-click entry, browser row, step in the history, inspector heading and the view's Orbit/Pan/Fit/Grid bar now has a one-colour line icon instead of an emoji. Commands that shared an emoji get their own picture (Line, Smart Circle, Linear/Circular/Fill Pattern, Offset Face, Section View, Finish Sketch), and history steps are drawn by kind (Chamfer vs Fillet, pattern kinds, Move). The Blueprint icons from the design proposal are kept; other icon sets are unchanged.

## 0.9.9.80.36 - 2026-10-25

### Added
- Studio theme (Settings > Appearance > Theme Mode): light grey-blue window, white panels with 8 px corners, Noto Sans, blue accent only for focus, the active tool, selection and the primary action. The ribbon, browser, inspector, tool panels, menus and Settings share the look; tool panels get a heading and labels above their fields. Other themes and Follow Omarchy are unchanged, and a saved theme choice is never replaced.
- Studio icon set (Settings > Appearance > Icon Theme): the Blueprint line icons in one colour, blue while a tool is active, plus new line icons for Sweep, Loft, Pipe, Cone, Jar, Honeycomb, Import, Statistics, sketch Rotate/Pattern/Construction/Fix and each rectangle kind. Choosing the Studio theme suggests it.

## 0.9.9.80.35 - 2026-10-25

### Changed
- Redesigned Settings with category navigation, themed section cards, compact colour controls and persistent save/cancel actions. Perspective controls now follow the camera mode.

## 0.9.9.80.34 - 2026-10-25

### Fixed
- The ground grid stays behind solid bodies when viewing from below, instead of drawing over their surfaces (Björn #87).
- Selecting a whole outline together with arcs already in it no longer cuts those arcs twice during Fillet/Chamfer, keeping curved faces whole and their rim lines continuous.
- Long planar chamfer bands remain flat faces, with tangent seams at both ends. Surface classification now measures width perpendicular to each seam rather than along the shortest axis (report 20261025-130556).

## 0.9.9.80.33 - 2026-10-25

### Fixed
- Chamfering a curved outline no longer draws false crease lines across the bevel and down the rounded walls. Face analysis and the outline tool now preserve double precision instead of leaving thin boolean slivers through coordinate rounding.

## 0.9.9.80.32 - 2026-10-25

### Fixed
- Round surfaces (fillets, arcs of an extruded sketch, cylinder walls) light up under the cursor like flat faces. Each arc is its own surface, also where a sketch fillet runs tangent into a larger arc.

## 0.9.9.80.31 - 2026-10-25

### Added
- Settings > Sketch & View > *Show tangent edges*: draws a line where a flat face runs smoothly into a curved one (a straight wall meeting a tangent arc or fillet), like Fusion's setting. Off by default.

## 0.9.9.80.30 - 2026-10-25

### Fixed
- Selecting a step (browser or timeline) colours only the material it really added or removed: the zero-thickness skins left where the body's surface was merely split into other triangles (e.g. over a whole thread after a chamfer) are no longer drawn as green/red stripes.
- Clicking a step in the browser no longer crashes ("Internal C++ object already deleted"): making the active object bold looked like a rename and rebuilt the tree in the middle of the click.

## 0.9.9.80.29 - 2026-10-25

### Fixed
- Fillet/Chamfer (and the browser's value preview) no longer hide an active section view: the live result is cut by the section, with its own cut face, and the section's own cut returns when the tool ends.

## 0.9.9.80.28 - 2026-10-25

### Added
- Browser: each object row under Objects has its own eye that hides or shows the whole object (its bodies, its sketches and the tool objects a Combine used up). Also in the row's right-click menu and with V.

## 0.9.9.80.27 - 2026-10-25

### Added
- Browser: editing a value in the tree suggests parameter names as you type (Up/Down + Enter/Tab picks one, Esc closes the list) and shows what a formula evaluates to (e.g. "= 10" for width/2). The value's label ("Height: ") stays visible next to the field while you type.

## 0.9.9.80.26 - 2026-10-25

### Fixed
- Fillet/Chamfer: the whole top (or bottom) outline of a twisted extrude can be picked as one edge and rounded; the rounding follows the leaning walls point by point. Before, only a few stray straight pieces of the outline were pickable.

## 0.9.9.80.25 - 2026-10-25

### Added
- Sketch Fillet rounds corners where a line meets an arc, or two arcs meet (hover, click, Shift+click, box pick and two-element pick); the fillet stays tangent to both when its radius dimension is changed, and the arc keeps its circle.

## 0.9.9.80.24 - 2026-10-25

### Fixed
- CI: `test_plane_actions.py` still hovered 16 mm out on the XY plane, which since 0.9.9.80.16 only spans the bodies (+5 %); it now hovers between two boxes.
- Object history: a sketch with projected edges got different dependencies right after Finish Sketch than after undo or reload (they came from replay-time inputs), so undo and Cancel no longer returned the exact document; they now come from the history itself.
- Browser: an unfinished sketch lists its texts and dimensions again (double-click edits the text).

## 0.9.9.80.23 - 2026-10-25

### Changed
- Browser objects: a body that a Combine uses up (the tool, not kept) is no longer its own object on the main trunk; its history hangs as a branch under that Combine in the target object. Jar with Lid now shows two objects, Jar and Lid, with the neck, bore and chamfer cylinders under their Combines.

## 0.9.9.80.22 - 2026-10-25

### Fixed
- A cut sketched on one body's face, made while another object was active in the browser, was aimed at the active object, missed it and was saved cutting nothing (it then showed up as its own object). The active object now only narrows operations that refer to it; the cut belongs to the body it is sketched on.
- Editing a value in the browser: the in-row editor was only 17 px tall and cut the text off. It now takes the whole row, at least its own height.

## 0.9.9.80.21 - 2026-10-24

### Changed
- Sweep: every plain click on a profile adds it (a click again drops it), no Shift and no Profile button per part. The panel stays on Profile until you press Path, then you click the path.

## 0.9.9.80.20 - 2026-10-24

### Added
- Sweep takes several profiles: Shift+click adds more profiles of the same sketch and they are swept together along the path (the panel shows "N profiles"). Saved, editable, undoable.

## 0.9.9.80.19 - 2026-10-24

### Added
- Loft has a Twist field like Sweep: the last profile is turned against the first, each ring by its share of the distance along the loft, with extra rings so the skin follows a helix. Saved, editable, undoable.
- The corner lines of a twisted extrude or a loft (helical creases between curved surfaces) can now be hovered and selected like other edges: measure them, use them as a Sweep/Pipe path. Fillet/Chamfer skip them for now (counted as skipped). Only chains longer than 15 % of the body's diagonal count, so tessellation detail stays out.

## 0.9.9.80.18 - 2026-10-24

### Fixed
- Dark fans on the flat walls of a box under a twisted extrude (report 20261024-110308): the smooth vertex normals averaged the wall with the twisted surface that touches it at a shallow angle, so the wall was shaded up to 18 degrees off. It was only the on-screen shading (the exported mesh/STEP was fine, which is why Bambu Studio showed nothing). Flat patches walled in by sharp edges in two directions now keep their own normal.

## 0.9.9.80.17 - 2026-10-24

### Fixed
- Fillet and chamfer on a polygon's corner cut a notch (report 20261024-084617): the tool reached out of the body with points square to the first face, which lie inside the material when the faces meet at anything but 90 degrees (a hexagon's 120 degree corner got a triangular notch in the next face, visible at the top). The tool now reaches out along each face's own normal, so every corner angle loses exactly its corner region.

## 0.9.9.80.16 - 2026-10-24

### Fixed
- Origin and construction planes were drawn far too large (report 20261024-084018): each plane was a square around its origin reaching the farthest body corner on every side, so a 500 mm box standing on XY got 1050 mm XZ/YZ planes reaching 525 mm below the floor. A plane now spans the bodies' projected bounds plus a 5 % margin (a small square on an empty model), and picking uses the same rectangle.

## 0.9.9.80.15 - 2026-10-24

### Fixed
- Clicking a face in Fillet/Chamfer took only some of its edges (report 20261024-082418): on a honeycomb box side, the closed cell outlines were taken and every cell made of straight edges was left out. A face click now takes all its edges, closed loops and straight or round edges together.

## 0.9.9.80.14 - 2026-10-24

### Fixed
- Fillet on the rim of honeycomb cells left spikes at the sharp 60° corners where the margin clips a cell (report 20261024-081206): the two rounded bands only met where both overlapped, so a ridge of unrounded rim stood between them behind the corner. Each band now also runs on past the corner where the other wall leaves it open, and the roundings meet in a clean mitre.

## 0.9.9.80.13 - 2026-10-24

### Fixed
- Honeycomb Through on a cup with a rounded rim left a row of ragged, half-cut cells (report 20261024-065939): picking the wall next to the fillet tilted the cylinder's axis about 0.6°, so cells on one side started inside the wall and Through measured right across the cup into the opposite wall. The wall is now picked with its true axis, a saved face is fitted to the body again before cutting, and a cell that starts inside the material only goes through that wall.

## 0.9.9.80.12 - 2026-10-24

### Fixed
- A loft from a rectangle to a circle showed about 110 small faces with lines between them (report 20261024-065108): resampling cut the rectangle's corners off, and one quad per step between a straight side and the turning arc folded up to 39° along its diagonal. Rings now keep their corners and rings go in between where a side turns, so the skin is one smooth surface. Hovering also no longer lights up a flat face behind a curved surface.

## 0.9.9.80.11 - 2026-10-24

### Fixed
- Changing the length of a straight side between sketch fillets did nothing (report 20261024-064212): the fillet arcs are not in the solver, so the neighbouring side stayed put and the refit pulled the side back to its old length. Filleted corners are now solved as the sharp corner they round, so the neighbours follow and the radii are kept.

## 0.9.9.80.10 - 2026-10-23

### Added
- Sweep / Pipe path from body edges (Björn): with Path active the edges are picked exactly as in Fillet (hover, joined edges follow, X = see-through, a face = its outline); a sketch's line, arc or circle still works too. Esc closes the tool as in Fillet.

## 0.9.9.80.9 - 2026-10-23

### Fixed
- Sweep / Pipe: the path was "the newest sketch", so with the profile drawn last the profile was swept round itself. The path is now clicked in the 3D view like in Fusion (a line, arc or circle; everything joined to it comes along) and outlined; Profile / Path buttons say which the next click picks, and after the profile it moves on to Path. With only one other sketch that can be a path it is taken at once.
- Sweep from a profile in the middle of a curved path: the section is read off where the profile sits, not at the path's start. A profile lying along the path says so instead of making nothing.

## 0.9.9.80.8 - 2026-10-23

### Fixed
- Loft did not work: Shift+click only adds profiles from the same plane (as Extrude needs), so the second profile on another plane was silently dropped and a Loft never got two. With Loft open every click now adds a profile from any plane, in order; a second click drops it again.

## 0.9.9.80.7 - 2026-10-23

### Fixed
- A fillet round the outside corner of a wall whose side leans left a loose strip (a small triangle) on the floor and a ledge where the bands met: the band beside the leaning corner edge was cut along that edge and ran on past the rolling ball near the floor. Each band now stops square across itself where the ball first touches the corner edge, and the corner's ball is as finely cut as the bands.

## 0.9.9.80.6 - 2026-10-23

### Fixed
- Chamfers round the outside corner of a wall whose two sides lean differently met the corner edge at two heights, so their top lines did not line up; both bands now meet at the lower point, the higher band's top coming down to it over the last chamfer distance.

## 0.9.9.80.5 - 2026-10-23

### Fixed
- Chamfers at the foot of a wall that meet round its outside corner met in a mitred ridge that stuck out past the bevels; the bevel now swings round the corner edge (a cone), like the fillet's rolling ball.

## 0.9.9.80.4 - 2026-10-23

### Fixed
- Fillets at the foot of a wall that meet round its outside corner (the side and the end of a rib) met in a sharp mitred crease; the rounding now rolls round the corner edge and the two flow into each other, as in Fusion.

## 0.9.9.80.3 - 2026-10-23

### Fixed
- Clicking the foot of a wall for a chamfer also took the end edge of a fillet band lying in the same line, so the chamfer filled one and cut the other; joined edges now only follow edges of the same kind (inside or outside corner).

## 0.9.9.80.2 - 2026-10-23

### Fixed
- A fillet at the foot of a wall that narrows (the sloping sides of a triangular rib) filled the air beside the wall; the rounding now stops at the wall's sides, carried straight out, as in Fusion.

## 0.9.9.80.1 - 2026-10-23

Versions now have a fifth part for small steps (0.9.9.80.1, .2 ...).

### Added
- Sweep (Björn #46): a sketch profile carried along a path (a sketch's lines and arcs in one chain, or a circle), with Twist. Holes in the profile stay open.
- Loft: a skin through two or more profiles on different planes, in the order they are clicked.
- Pipe: a round rod or tube (wall thickness) along a path; sharp corners get a mitre.
- Cone: bottom and top radius (0 = a point) and height, placed like a Cylinder; Shell Wall hollows it.
- All four are in the ribbon (Sweep and Loft next to Revolve, Cone and Pipe under Primitives), the Create menu and the help, with live previews, and can New Body / Join / Cut / Intersect.

## 0.9.9.80 - 2026-10-23

### Added
- Plane at Angle (Björn #51): the Offset Plane panel has an Angle and a "Rotate about" choice (the start plane's X or Y direction, or a straight edge you click). The plane is turned about that axis and then offset; the preview follows.

## 0.9.9.79 - 2026-10-23

### Fixed
- Face outlines in a sketch (Include face edges) come in as lines and arcs that share their ends. A rounded lid gave ~190 tiny pieces whose corners stopped 0.01 mm short of the straight edges, plus mesh seams: one click picked only part of the outline, Offset lost the corner radius and no closed profile was found (Björn #56, #58).
- Emboss over a flat wall that runs into a rounded corner left the letters floating at the sketch plane. When no single plane or cylinder carries the text it is now projected onto the surface as it is; parts beyond the body are left out (Björn #57).
- Fill face pattern did nothing in a box: its walls counted as a filled block and a lid parked above it cast its outline onto the floor. Only material standing on the face is an obstacle now, with holes respected (Björn #59).
- Curved surfaces are shaded smooth (sharp edges stay crisp); the floor of wrapped text showed blotches and fan streaks (Björn #61).
- The value box for editing a sketch dimension could stay in the view for good after clicking elsewhere; a click elsewhere now takes the value (Björn #77).

### Added
- Tab in a tool panel moves between its number fields only, and Tab in the 3D view jumps into the open panel (Björn #47).
- Duplicate a sketch from the browser (right-click > Duplicate), as a new step (Björn #65).

## 0.9.9.78 - 2026-10-23

### Added
- Extrude Twist (Lennart #85): the profile turns the given number of degrees about its own centre from start to end, for twisted vases and columns. Profile edges are cut into short pieces so the twisted walls keep the exact volume (within 0.03 %). Saved, editable from the timeline and accepts formulas.

### Fixed
- Sketches with a circle always reported 3 degrees of freedom too many, so a circle placed with Smart Circle (diameter + two distances) still made the sketch look under-defined (#84). The solver's workplane normal is now a constant.

## 0.9.9.77 - 2026-10-23

### Changed
- Fillet/Chamfer works more like Fusion 360: while you pick edges the view shows the finished, rounded body in place of the original instead of loose blue tool slivers.
- Box corners where three filleted edges meet are now a rolling-ball sphere (before: a pointed bump where three cylinders crossed); with an equal chamfer the corner gets a flat triangle.
- Chamfer types: Equal distance, Two distances and Distance and angle, with Flip to swap the faces. The first distance lies on the top/bottom face of a straight edge and on the flat face of a circle or outline.
- Tangent chain checkbox in the panel: off picks single edges only.

## 0.9.9.76 - 2026-10-21

### Fixed
- Emboss bent onto a flat wall of a tapered hex prism: the wall's normals form a ring around the axis (the taper tilts them), so the surface passed as a 28 mm cylinder. The cylinder detector now requires every face normal to point radially from the fitted axis. Report 20261021-205724.

## 0.9.9.75 - 2026-10-21

### Fixed
- Emboss wrapped onto a cylinder wall whose top edge has a fillet: the wall was not recognised (the fillet joins it into one smooth patch), so the letters fell back to a flat face 36 mm away and floated. The cylinder detector now keeps the wall triangles of such a patch, also used by picking. Report 20261021-204118.

## 0.9.9.74 - 2026-10-21

### Changed
- Split Body now stores the source solid geometry in its timeline step. Earlier sketch and feature edits no longer change either split result, while the split plane can still be edited.

## 0.9.9.73 - 2026-10-21

### Changed
- Origin and construction planes now display over the projected bounds of visible bodies, so a plane used to split a body visibly covers it.

## 0.9.9.72 - 2026-10-21

### Added
- Request a change can use an image copied to the clipboard from another application (Lennart #86).

## 0.9.9.71 - 2026-10-20

### Fixed
- An Extrude cut that matches a moved body's outline no longer leaves a wall skin standing above the floor: the cut now takes the 1 um cutter clearance when the result has needle triangles and it removes them (report 20261020-220439).

## 0.9.9.70 - 2026-10-20

### Fixed
- Edge picking uses the segment midpoint for its visibility test again, so the fillet face-pick test (CI build) passes; shallow-view rim picking stays covered by its test.

## 0.9.9.69 - 2026-10-20

### Added
- Fillet accepts a negative radius that cuts a concave cove into selected convex square edges and full circular rims; unsupported edge types are reported as skipped (Lennart #79).
- Request a change accepts multiple additional image attachments, and Jar with Lid has a Reset to defaults button (Lennart #82, #83).

### Fixed
- Parameter-driven number fields now use dark text on a light background so the expression is readable across themes (Lennart #80).
- Clicking a parameter expression starts editing it immediately, with a visible white editor and the cursor at the end of its current value; F8 can open Request a change while a dialog is active (Lennart #81).
- Honeycomb reattaches a moved planar face to the nearest parallel face when an earlier feature changes its position, preserving the pattern through timeline edits (Lennart #82).
- Circular edges left by an annular cut in a cylinder are now detected and selectable for Fillet/Chamfer. Boolean seam fragments had made the edge graph branch at microscopic duplicate segments.
- Face picking now tolerates tiny barycentric errors at boolean-generated triangle boundaries, so the annular floor after a circular cut remains selectable for another Extrude.
- Edge picking on shallow-view rims (e.g. a hole's circular rim in a cylindrical extrude) now tests visibility at the exact point on the edge nearest the cursor, not the segment midpoint; this prevents false occlusion that hid selectable edges in views from certain angles.

## 0.9.9.68 - 2026-10-19

### Added
- Timeline: clicking (or resting the mouse on) a Fillet/Chamfer step outlines the edges that step rounds in dark blue, through the material, and the outline stays while you edit the step, so with several chamfers you can see which one you are changing (Lennart #67).

## 0.9.9.67 - 2026-10-19

### Fixed
- Concave fillets along a straight edge beside a cylindrical face now use the cylinder's actual circular section, following the curved wall along the full edge. The previous planar approximation left a pointed spike, and its clearance estimate collapsed the requested 6.8 mm radius to about 0.043 mm (problem report).

Versions: 0.x while the feature set is still growing, 1.0 when Omacad is a complete and dependable CAD. Since 0.9.9 every change is a tiny step (0.9.9.1, 0.9.9.2, ...); 1.0 comes only when the owner says so.
The version lives in `omacad/__init__.py`; every build is published as release `v<version>` (and as `latest`).

## 0.9.9.66 - 2026-10-19

### Added
- Jar with Lid: *Thread chamfer* (1 mm by default, 0 = none): a 45° chamfer on the neck's outer rim that runs out through the start of the jar's thread, and a 45° lead-in cone in the lid's mouth, so the lid finds the thread (Lennart #70).

## 0.9.9.65 - 2026-10-19

### Fixed
- Sketch Move with Copy: the originals disappeared until OK; they are now drawn where they stay the whole time (Björn).

## 0.9.9.64 - 2026-10-19

### Fixed
- Fillet round an outline with inward arcs (a dog bone) left a row of teeth along the arcs (Björn #78). Where an arc meets a circle the rounding folds a little, so the tool is built piece by piece; those straight pieces now overlap a hair and the gap at every inward turn is filled with the section turned about the corner, so the rounding is smooth and has no thin flaps.

## 0.9.9.63 - 2026-10-19

### Added
- Sketch tool panel (Björn #76): every sketch tool shows what to do next in the sketch palette, and its numbers (Length/Angle, Width/Height, Diameter, Side/Sides, Radius, Move X/Y) as fields with sliders. A value set there locks it for the following shapes until "Follow the mouse"; Sides and corner radius set the defaults. The Offset/Trim/Mirror/Fillet hints moved from the banner over the drawing into the panel.
- Sketch Move (Björn #75): X / Y fields with sliders move the picked elements at once from their centre (a click still picks another base point), and "Copy" keeps the originals.
- Sketch Pattern (Björn #75): new Pattern button in the sketch's Modify group. Rows and columns (count and spacing in X and Y) or around a centre (count, angle, selection/origin/face centre), live, with sliders; OK is one undo step, Cancel or Esc puts the sketch back.
- Midpoint constraint (Björn #73): an end point or a circle's centre on the middle of a line (select it and the line).
- Settings > Appearance: thickness of sketch lines and selected lines, and the colour of selected lines (Björn #74). Default lines are thinner (1.6 px, was 2.4) with a thinner dark rim.
- Hovering a dimension tells what it measures, its value and formula (Björn #72).

### Fixed
- Rectangle width and height dimensions were placed inside the rectangle; they are outside now, also on rounded rectangles (Björn #71).
- Extension lines of a line dimension on the "negative" side stopped 2 mm short of the dimension line (Björn #72).
- Tests: closing a module-scoped test window could open the "save changes?" box and hang the run (since 0.9.9.61).

## 0.9.9.62 - 2026-10-19

### Added
- 3-point Arc: tangent magnet (Björn #53). When the arc leaves or meets a line, arc or face edge that ends at its start or end point within 8° of smooth, the third point sticks so the arc is exactly tangent there; a green ring marks it. A real snap point (end point, mid point, edge) still wins.

## 0.9.9.61 - 2026-10-19

### Fixed
- Jar with Lid: the lid could not be screwed on (Lennart #70). The lid is cut from the jar, so its groove copied the coil's tapered ends and was missing where the coil starts at the lid's mouth; the full tooth jammed there. Offset Face on a thread now cuts a full, untapered channel that runs one turn out through the mouth, so the lid screws all the way off.
- Circular pattern on a round body with an inner thread (a lid with slots) left fins on every copy (Lennart #69). The round test and trim now only look at the ring the copies sweep, so the clean round-body path is used and the thread stays untouched.
- Closing Omacad (window X, Ctrl+Q, logging out) never asked to save unsaved changes (Björn #55, Lennart #68): Qt's own closeEvent hid ours. A restart for a new version still closes without asking (the session is saved).

### Changed
- Primitives: "Hexagon" is now called "Prism" (Björn #66).
- Sketching on a face centres the face and zooms so it fills the view (Björn #48).

## 0.9.9.60 - 2026-10-18

### Fixed
- The model is always built at full curve quality. If the coarse quality used while dragging was left on (for example a lost mouse release), a rebuild or a new step could otherwise come out with coarse curves.

## 0.9.9.59 - 2026-10-18

### Fixed
- Letting go of the Extrude arrow after dragging it no longer raises an error. A new window no longer restyles every other window when nothing about the theme changed (the full test run went from 25 to 8 minutes).

## 0.9.9.58 - 2026-10-18

### Added
- Text In Box (Text tool, Type: Text In Box): click two corners and the text fills the box as far as it can, centred, measured on the letters themselves. It fits again at once when you change the font, the text or the style; the height field shows the height the box gives. The box shows as a dashed outline in the sketch (not a profile), and is saved with the file.

## 0.9.9.57 - 2026-10-18

### Added
- Help & Commands has a Close button next to Run (Esc closes it too).

## 0.9.9.56 - 2026-10-18

### Changed
- Help > Help & Commands (F1) replaces the picture guides: every function grouped as in the ribbon (SOLID, SKETCH, file, view, timeline and browser, working tips) with help text, its key and where to find it. Type keywords to search (hole, round, parameter, print …); the best match is selected and Enter runs it. The Create, Modify and Inspect menus show what an entry does when you hover it.

## 0.9.9.55 - 2026-10-18

### Changed
- Report problem is now F10 (Omarchy uses F9).

## 0.9.9.54 - 2026-10-18

### Added
- Fix Sketch (SKETCH tab, MODIFY, and the sketch right-click menu) closes what you drew into a face with as few changes as possible: it removes empty and doubled lines, joins ends that nearly meet (two lines run on to their real corner), extends or shortens a line that stops just short of or just past another, and closes an open outline with one line. Tails sticking out past a corner are left alone. One undo step; the status line says what it did.

## 0.9.9.53 - 2026-10-18

### Added
- Help for formulas where you type: the parameter list under a field ends with a grey line using your own names, such as "Formulas too: radius+2 · radius/2 · 2*radius", and once a whole name is typed a line shows its value and the same examples (Enter still works as usual). The field tooltip and Change Parameters explain formulas with examples such as radius+2 and test1+5*test3.

## 0.9.9.52 - 2026-10-18

### Added
- Point to point: every full circle (a cylinder's ends, holes, pins) now has five points, its centre and four quarter points in line with the axes, like a cross. A cylinder can be put against another by its side, and the move follows when the cylinder is changed later.

## 0.9.9.51 - 2026-10-18

### Fixed
- Texts that did not fit in the tool panels are shorter now, with the explanation in the tooltip: in Move (Lay face flat…, Pivot: Body centre / Origin), Box/Cylinder/Hexagon placement, Thread/Coil, Jar with Lid, Shell, Honeycomb and the Extrude/Revolve profile lists. The Swedish texts left in these panels are now English like the rest of the app.

## 0.9.9.50 - 2026-10-18

### Changed
- Move applies each move at once: when you let go of an arrow or ring, the move becomes a real step (everything after it rebuilds) and the panel stays open with the numbers back at 0, so you can move a body in several goes without pressing OK in between. Starting Point to point, Face to face or Lay on ground first applies what you typed, so the picks are made where the body now is. Each move is its own undo step; Esc or Cancel keeps the applied moves and only drops what was not applied yet.

## 0.9.9.49 - 2026-10-18

### Fixed
- Typing a parameter name no longer sets off shortcuts: the letters of "depth" used to start Extrude at the e, whether typed in the 3D view with a tool open or in the dimension fields while drawing. Letters typed in the 3D view now go into the open panel's field, like numbers. A list of the parameters starting with what you type opens under the field (also under the dimension fields while drawing): Up/Down step through it, Enter or Tab picks the name without pressing OK, Esc closes it. Values that follow a parameter are marked: blue text in the fields, a blue "ƒx name = value" badge on sketch dimensions, and ƒx on timeline steps with formulas.

## 0.9.9.48 - 2026-10-18

### Added
- Smart buttons: the ribbon buttons that fit what you have selected get an orange border (a profile: Extrude, Revolve, Emboss; one body: Move, Shell, Split Body, Offset Face, Fillet, Chamfer; two or more bodies: Combine and Move; picked edges: Fillet and Chamfer). No button moves. The Settings button now sits level with the other buttons.

## 0.9.9.47 - 2026-10-18

### Changed
- Right-click menus use the same names and keys as the ribbon (Combine N Bodies, Construction X, the sketch tools in the ribbon's Create / Modify order). New entries: Delete Sketch on a sketch in the view, Emboss on a profile, Project in the sketch menu. Browser > Offset Plane now starts from the plane or sketch you right-clicked (it asked for a pick). Menus use … consistently.

## 0.9.9.46 - 2026-10-18

### Changed
- Buttons and menus are reorganised the Fusion 360 way, with few groups. SOLID: CREATE (Create Sketch, Extrude, Revolve, Emboss, Primitives, Pattern, Honeycomb, Offset Plane, Insert: Canvas and Import 3MF) / MODIFY (Fillet, Chamfer, Shell, Offset Face, Combine, Split Body, Move, Change Parameters, Delete) / INSPECT (Measure, Section View, Document Statistics), each group named under its buttons, Settings at the far right. SKETCH: CREATE / MODIFY / CONSTRAINTS / INSPECT. The menu bar has Create, Modify and Inspect in the same order. Every command has one name and one shortcut everywhere (Guide Line is now Construction, Perpendic. is Perpendicular). Revolve and Honeycomb are in the menus now, and Document Statistics can be reached again.

## 0.9.9.45 - 2026-10-18

### Fixed
- Deleting a step now also takes along (and warns about) an Extrude that uses a hole or profile of its sketch, and an Offset Face on its thread. A fillet or chamfer on a flat or folded edge no longer divides by zero. The Thread panel keeps the length at least one turn (the pitch) instead of the model stretching it silently.

## 0.9.9.44 - 2026-10-18

### Fixed
- A step that fails while the history rebuilds now shows a red chip on the timeline with the reason in its tooltip (it was only printed). Rotated objects in an imported 3MF file come in rotated the right way (they were mirrored or turned the wrong way). Profile and face-analysis failures are written to the log that goes with a problem report.

## 0.9.9.43 - 2026-10-18

### Changed
- Edit on the timeline rolls the history back to the step while its panel is open, as in Fusion 360: you see and pick the model as it was before the step, and OK or Cancel rolls forward again. In the edit panels, Shell's open faces, a Box/Cylinder/Hexagon's "On face" and a Thread's face or cylinder can now be picked again (those buttons did nothing). Move's pick buttons are greyed out in an edit and say why. A Box or Cylinder preview error is shown in the panel instead of failing silently.

## 0.9.9.42 - 2026-10-18

### Fixed
- Editing a step from the timeline: a box, cylinder, hexagon or sphere dragged before placing now previews where it is; a step edited right after making it has a preview (Offset Face, Honeycomb, Thread); Auto in an Extrude/Revolve edit decides against the bodies before the step (an upward join no longer turns into a cut); a preview error is shown instead of hidden; formulas for counts (prism sides) stay whole numbers and at least 3 sides.

## 0.9.9.41 - 2026-10-18

### Fixed
- With the timeline rolled back, formulas typed in Box, Cylinder, Sphere and Extrude, the jar's thread and the Shell/Pattern previews now belong to the step just added, not to the last step of the history.

## 0.9.9.40 - 2026-10-18

### Fixed
- Text tool: Cancel removes or resets only the text, never other lines drawn while the panel was open. Picking another sketch tool after placing the text keeps the text as its own undo step.

## 0.9.9.39 - 2026-10-18

### Fixed
- While a tool panel is open, Delete and the timeline buttons (rewind, step, roll back, edit, suppress, delete) wait and say why, instead of rebuilding the bodies under the tool. Delete in a sketch no longer deletes selected bodies, and says when nothing is selected. Solid tools started inside a sketch (Extrude, Revolve, primitives, Fillet, Pattern, Shell, Move ...) finish the sketch first, as in Fusion 360.

## 0.9.9.38 - 2026-10-18

### Fixed
- Esc in Shell, Offset Face, Honeycomb and Move now cancels the tool. It used to stop only the face picking, leaving a panel that could no longer pick and a status saying "Create Sketch cancelled". Esc while picking for Offset Plane or Section View now names that tool.

## 0.9.9.37 - 2026-10-18

### Fixed
- Pressing OK or Cancel right after changing a value in Shell, Offset Face, Thread or Fillet/Pattern no longer leaves the body hidden or a preview behind.

## 0.9.9.36 - 2026-10-18

### Fixed
- In a sketch, M and F now start the sketch's Move and Fillet as the ribbon says; they used to open Move Body and fit the view.

## 0.9.9.35 - 2026-10-18

### Fixed
- Opening a tool while another was open left the first one half alive (its preview, a hidden body, pick mode) and could block Undo and reopening the tool. A new tool now cancels the open one first; a short value prompt (fillet radius, offset distance) brings you back to the tool it was asked from.

## 0.9.9.34 - 2026-10-18

### Fixed
- A formula like (-8)^(1/3) or a huge power no longer crashes the app; it is shown as an invalid value.

## 0.9.9.33 - 2026-10-18

### Fixed
- Changing Curve smoothness now really rebuilds round shapes (cached steps were reused at the old smoothness), and undo always runs the steps again, so values they measure while running (a thread following its cylinder, pattern copy counts) are there.

## 0.9.9.32 - 2026-10-18

### Changed
- A new step made while the timeline is rolled back is inserted at the marker, as in Fusion 360; the later steps are kept and come back when you roll forward (they used to be deleted).

## 0.9.9.31 - 2026-10-18

### Fixed
- After deleting a step or a sketch, a new step or sketch could get the same id as an existing one and replace it (a new box overwrote another body; a new sketch replaced one and never reached the timeline). Ids are now always unique.

## 0.9.9.30 - 2026-10-18

### Fixed
- Editing a sketch after the history had been rebuilt could lose the edit: the rebuild handed out a copy of the sketch, and finishing put the old one back.

## 0.9.9.29 - 2026-10-18

### Fixed
- The zero thread clearance announced in 0.9.9.21 now really is the default (Thread/Coil panel, new steps and the kernel); it had not been committed.

## 0.9.9.28 - 2026-10-18

### Added
- Jar with Lid: Inside chamfer (4 mm by default) at the bottom and under the shoulder inside the jar. At the shoulder's width it turns the shoulder into a 45° cone that prints without support.

### Changed
- Fillet/Chamfer: a click where only a hidden edge lies (inside a jar, under a shoulder) now says so and how to reach it: X or Alt picks through the model.

## 0.9.9.27 - 2026-10-18

### Added
- Jar with Lid (Primitives menu and Create menu): a threaded jar and its screw lid in one go. Diameter, height, wall, neck diameter and height, pitch, thread profile, lid top and thread tolerance (-0.2 mm by default; minus = looser), all with sliders and a live preview. The lid is laid upside down beside the jar, ready to print (or screwed on). Everything is made of ordinary, editable timeline steps and is one undo step; the panel remembers the last sizes and refuses a lid wall that is too thin.

### Fixed
- Shell right after other steps could make a different body than after reopening the file (a cup on a stacked cylinder got a 0.5 mm thinner shoulder until the history was rebuilt). Shell now works from the current history.

## 0.9.9.26 - 2026-10-18

### Added
- Honeycomb (ribbon button): cut a lattice of hexagons, circles, squares, diamonds or triangles into picked flat and cylindrical faces of a body. Cell size, wall, margin to the edge, depth or Through (each cell goes to the air behind it, so the opposite wall of a box stays whole), rotation, and optional cut cells at the edge. The pattern is placed where the most whole cells fit and closes exactly round a cylinder (walls only get wider, never thinner). Live preview, undo, save/load, editable in the timeline.

## 0.9.9.25 - 2026-10-18

### Fixed
- Fill face pattern: a margin wider than the original's own distance to the edge left no room for its row (a 10 mm margin on a 22 mm wall gave two clipped slivers). The margin is now held to that distance, and the panel says so.

## 0.9.9.24 - 2026-10-18

### Added
- Point picking (Move / Rotate, point to point): every flat face has a centre point, and every full circle (holes, cylinder ends) has its centre.

### Fixed
- Point picking: the dots stayed at their old screen spots when the view was zoomed or turned, so they sat in the wrong places on the body. They are now projected again on every repaint.
- Point picking: points behind a body (also the body being moved, hidden behind its preview) are no longer shown, in perspective and orthographic views.

## 0.9.9.23 - 2026-10-18

### Changed
- Split the viewport, sketch, face-analysis, tool-prompt and theme code into focused modules while keeping their existing public entry points.

### Fixed
- Fillet/Chamfer: the edge where a flat face meets a wall is a whole circle again on bodies with patterns, embosses and shells. Leftover zero-area triangles from the booleans had chopped it into short arcs with gaps that could not be picked.

## 0.9.9.22 - 2026-10-18

### Fixed
- A circular pattern on a round body no longer erases a thread elsewhere on it: only the height the patterned features occupy is trimmed to what every rotation keeps.

## 0.9.9.21 - 2026-10-18

### Changed
- New threads default to zero clearance; users can still enter a clearance when they need one.

## 0.9.9.20 - 2026-10-18

### Changed
- While creating a primitive, drag the preview with the left mouse button to set its position; the offset is stored in the primitive feature and follows save/load and undo.
- Move / Rotate adds **Activate copy**: the original stays put and a parametrically transformed copy is created, saved, restored and undone with the Move step.
- Move preview in copy mode now shows both the unchanged original and the moved copy.
- Point to point can snap to the centre of a body's top and bottom, including curved extremes.
- Right-clicking a planar face now offers **Move this Body…**, which opens Move / Rotate for the whole owning body.
- Move / Rotate no longer has a separate Active handle row; click a gizmo axis directly. The gizmo hides while picking point-to-point references.
- Face-to-face Move accepts the target face first or the moving face first.
- The moving body remains visible and pickable while choosing faces for Face-to-face Move.
- Lay on ground hides the Move gizmo, shows the body while picking, and lays the clicked face flat on XY.
- Right-clicking a body while Move / Rotate is active selects it as the target body.
- Move gizmo stays hidden while Face-to-face is waiting for its two face picks.

## 0.9.9.19 - 2026-10-18

### Fixed
- Ordinary cuts no longer get nanometre steps along their edges (which broke later fillet/chamfer edge picks): the cutter is only grown when that actually removes strips left along a faceted wall.

## 0.9.9.18 - 2026-10-18

### Changed
- Offset Plane: a plane offset from an origin plane now starts at the centre of the visible model (projected onto the base plane), so its marker sits around the part instead of at world origin.

## 0.9.9.17 - 2026-10-18

### Fixed
- Extruded cuts along a cylinder wall still left vertical strips at fine curve smoothness (360 segments): the sketch profile and the wall are faceted differently and differ by up to 0.5 μm. When a cut leaves zero-thickness sheets, the cutter is now grown by an invisible 1 μm (other cuts keep exact volumes).

## 0.9.9.16 - 2026-10-18

### Fixed
- Extruded cuts through a shelled, threaded cylinder could leave narrow mesh strips where the circular cutter nearly coincided with the faceted inner wall. The cutter now grows by 1 nm before cutting to resolve the boundary cleanly.

## 0.9.9.15 - 2026-10-18

### Changed
- Thread / Coil: the short lead-in & runout (a third of a turn) is now the default; it works best for coils. Editing an existing thread keeps its own setting.

## 0.9.9.14 - 2026-10-18

### Fixed
- Combine: with no body selected, clicks in the view could only change the tool, so the target stayed the first body and a lid "cut by the can" cut the can instead. Now the first body clicked is the target and the next the tool (like Fusion), with a hint saying which one to click.
- Combine shows a live preview of the result (new Combine had none, and the preview when editing a Combine silently failed).

## 0.9.9.13 - 2026-10-18

### Fixed
- Shell of stacked bodies (a narrow cylinder joined on top of a wide one): the narrow part was put back solid and the open top face swept the wide cavity through its wall. The cavity now follows the inner shape with exact 2 mm walls, and an open face opens only the region of that face.

## 0.9.9.12 - 2026-10-18

### Fixed
- Report problem (F9), Request a change (F8) and Save failed once the design had a Shell with a picked open face: the step kept the dialog's live face object, which can't be written to JSON.

## 0.9.9.11 - 2026-10-18

### Fixed
- CI (and the Windows EXE build) hung since 0.9.9.6: a fill pattern grew to 7+ GB in `drop_slivers`. After a pattern the body carried ~10^5 mesh-relation runs, which `decompose()` multiplies per part; `drop_slivers` now drops the relation first (`as_original`).
- Mirrored chamfered holes got their zero-thickness fins back (0.9.9.7): `drop_slivers` rebuilds from the solid parts again and cuts closed inner voids back out, instead of subtracting flakes that lie on the surface.
- Edge and loop picking on patterned bodies (0.9.9.6): `clean_difference` only grows/clips when the plain difference really has zero-thickness sheets (`CadKernel.has_sheets`); otherwise every face moved a hair off its plane and edges split.
- `test_thread_dialog_click` failed in the full suite (and in CI): it took a ThreadDialog left over by an earlier test.

## 0.9.9.10 - 2026-10-18

### Changed
- Fillet and Chamfer moved on the Solid ribbon, right after Primitives (before Extrude).

## 0.9.9.9 - 2026-10-18

### Changed
- Shelled Box and Shelled Cylinder are gone from the ribbon and the Create menu, to save room: Box, Cylinder and Hexagon hollow themselves with Shell Wall in their own panel. The "Primitive shell thickness" setting went with them.

## 0.9.9.8 - 2026-10-18

### Added
- Hexagon primitive (ribbon Primitives / Create menu): a regular prism sized across flats, 6 sides by default (3 to 64), a flat facing +X. It has every Cylinder option: Shell Wall, Outer and Inner Edge fillet or chamfer, Taper angle, placement on a face or plane, drag handles, formulas and editing in the timeline. The wall, the rounds and the taper are measured square to the flats.

## 0.9.9.7 - 2026-10-18

### Fixed
- Shell no longer hangs on a cylinder with embossed ribs. When everything since the last convex state of the body only added material outside it, that convex body is shelled exactly and the additions are put back on the wall, instead of eroding every triangle (minutes on a wrapped emboss). The preview, the edit preview and the step all use this.
- Editing a Shell step opens again (the dialog's direction and open-faces fields had been renamed).
- Removing loose flakes no longer drops a closed inner void of a body.

## 0.9.9.6 - 2026-10-17

### Fixed
- Patterns no longer cover a body in hair-thin strips. A circular pattern of an emboss wrapped on a cylinder copied, with every slot, the zero-thickness sheets left where the cylinder's surface was tessellated differently before and after the emboss. Patterns now copy a cleaned difference (`CadKernel.clean_difference`) that keeps nothing thinner than a millionth of a millimetre, for every pattern kind.

## 0.9.9.5 - 2026-10-17

### Added
- Move / Rotate: "Pick points…" in the panel. Click a point on the body, the end of a straight edge or the sharp corner a rounding hides (move the mouse near the rounding: dashed guide lines show the corner), then click where it should go: a point on another body or the origin. The first point becomes the rotation pivot ("Picked point"); press Esc after it to rotate about it without moving. Dx/dy/dz and the angles still work on top, and the step follows when a radius or size before it changes.

## 0.9.9.4 - 2026-10-17

### Added
- Move steps can carry a body point to point (from a snap point on it to a point on another body or a fixed spot) and rotate about a picked point. The points are stored in the step and found again after a rebuild, so the move follows when a radius or size before it changes. Not yet in the Move panel.

## 0.9.9.3 - 2026-10-17

### Added
- Groundwork for moving and rotating a body from a point: Omacad finds the snap points of a body, the ends of its straight edges and the sharp corner each rounding hides (where the straight edges would meet). Not yet in the Move panel.

## 0.9.9.2 - 2026-10-17

### Fixed
- The 3D view no longer turns sluggish on bodies with fillets, text or many faces. Finding the edge and face under the cursor projected every edge point and tested every face one by one on each mouse move (up to 0.2-0.6 s per move); it now handles a body's edges and faces in one go and reuses the camera matrices, so a mouse move takes 1-4 ms on the same models.

## 0.9.9.1 - 2026-10-17

### Changed
- Type a number straight away in every tool, not only Extrude: with Fillet, Chamfer, Shell, Offset Face and the other tool panels open, digits typed in the 3D view go into the tool's main field (the old value is replaced) and Enter is OK. While edges are being picked, Backspace still removes the last edge.

## 0.9.9 - 2026-10-17

### Fixed
- Rounded rectangles can be rotated to any angle. Their Width and Height were horizontal/vertical distances, which blocked every rotation that is not a quarter turn; they now measure wall to opposite wall, square to the walls, so they stay right when the rectangle is turned. Changing a point-to-line distance keeps the line it is measured from in place, so a turned rectangle keeps its angle when you change its size.
- Plain rectangles keep their Horizontal/Vertical constraints (as in Fusion 360): Rotate already turns them into relative constraints, and without them a rectangle would twist when its size is changed.

## 0.9.8 - 2026-10-17

### Changed
- The drag sliders from the primitives are now under every number field: all tool panels (also fields inside group boxes, such as the Thread clearance), the sketch Rotate panel, the sketch palette (Polygon sides, Corner radius), the canvas (reference image) dialog and Settings. Angle sliders cover the field's range up to one full turn each way.

## 0.9.7 - 2026-10-17

### Added
- A rounded rectangle gets construction guide lines from its straight sides out to each sharp corner, where they meet, so you can snap a rotation pivot, a dimension or a line to the corner. They follow when the width, height or a corner radius changes, and they are not part of the profile.

### Changed
- The sketch palette shows Polygon sides only while the Polygon tool is active, and Corner radius only for the rounded rectangles.

## 0.9.6 - 2026-10-17

### Changed
- Sketch Rotate is driven by the mouse: click in the sketch to set the pivot (it snaps to points and the grid), then drag around it to turn the selection; Shift turns in 15° steps and full turns keep counting. Typing an angle and the pivot list still work; Enter / OK applies, Esc cancels. The "Pick pivot" button is gone, a click does it.

## 0.9.5 - 2026-10-17

### Changed
- Sketch Move only moves: the elements no longer turn with the mouse direction and the Angle field is gone (Rotate, Shift+R, still rotates). Pick what to move right in the tool (click a figure, Ctrl+click one element, several at once), press Enter, click the base point, then where it should go; X / Y can be typed. Anything selected beforehand goes straight to the base point.

## 0.9.4 - 2026-10-17

### Fixed
- STEP export of threaded and other detailed bodies opens in Bambu Studio, FreeCAD and other OpenCASCADE-based programs again. Points at the same spot are welded and paper-thin facets removed before writing, so readers no longer reject the solid. Body and file names with å/ä/ö or apostrophes are written as valid STEP text.

## 0.9.3 - 2026-10-17

### Fixed
- Thread / Coil works again: OK after clicking a cylinder crashed before the step was made (a missing expression helper), and the live preview never showed (a misnamed quality call). Both broke in 0.7.9.57.

## 0.9.2 - 2026-10-17

### Fixed
- Shell works on cylinders and other round convex bodies: Inside keeps the side wall (it used to leave only the top and bottom discs), and Outside stays round instead of growing into a box.

## 0.9.1 - 2026-10-17

### Fixed
- Circular pattern on a round body no longer leaves paper-thin skin strips and shards over the copied cuts (for example wrapped deboss slots with a fillet). When the body is round about the axis, the result is what every rotated copy keeps, so cuts land cleanly even when the angle is not a whole number of facets.

## 0.9.0 - 2026-10-17

### Added
- Circular Feature Pattern in Create and the Pattern dropdown. Select a rib and its fillets together in the timeline or feature list, choose the total quantity (including the original) and full/partial signed angle.
- Rotate around X, Y or Z, or pick a circular edge/cylindrical face to define an arbitrary axis. Axis settings persist and remain editable in the timeline.

### Fixed
- Circular feature groups compose only the checked feature changes; unchecked intermediate holes or other edits are not repeated. Fillet removal is combined with the added rib before copying.
- Pattern type changes preserve synchronized numeric sliders.

## 0.8.0 - 2026-10-17

### Added
- Rotate selected sketch elements (Shift+R) with live preview and a visible pivot marker. Choose the figure area centroid (including holes), selection center, supporting face center, sketch origin, or a picked/exact custom point.
- Rotation supports cancel, one-step undo/redo and project persistence; horizontal/vertical relations follow the rotated selection while preserving rectangle shape and dimensions. Fixed geometry and incompatible axis distance dimensions are protected.

## 0.7.9.68 - 2026-10-17

### Fixed
- Subdivide wrapped Emboss/Deboss tool interiors before bending them around cylinders, preventing detached material flaps in long slots.

## 0.7.9.67 - 2026-10-17

### Fixed
- Wrapped Emboss/Deboss contours on cylinders can now be selected and rounded/chamfered, including face selection in Fillet/Chamfer mode (request #63).
- Recognize nonplanar cylindrical contour loops, preserve their references through rebuild/save/undo, and limit rounding to the available rim depth. Subdivide flat rounding tools before wrapping them around the cylinder.

## 0.7.9.66 - 2026-10-17

### Added
- Taper angle for Box and Cylinder, including shelled versions, with numeric/slider input, live preview, timeline editing and project persistence. Positive angles narrow the top; negative angles widen it.
- Tapered shells preserve normal wall thickness and floor thickness. Invalid angles or closed openings are rejected before creation.

## 0.7.9.65 - 2026-10-17

### Added
- Sliders alongside numeric fields throughout docked tool panels, including integer controls. Numeric entry, formulas, live change signals and field limits remain available.
- Adaptive slider ranges keep small values usable while typed values retain the field's full range. Primitive dimension sliders follow the primitive drag precision preference.

## 0.7.9.64 - 2026-10-17

### Added
- Shelled Box and Shelled Cylinder in Primitives and Create, with open tops, live dimension handles and per-shape Shell Wall thickness.
- Settings → Sketch & View → Primitive shell thickness: saved default wall and floor thickness for shelled primitives (2 mm by default).

## 0.7.9.63 - 2026-10-17

### Changed
- Primitive handles now snap to whole millimetres by default. Settings → Sketch & View → Primitive drag decimals offers 0, 1 or 2 decimal places, saved between sessions.
- Cylinder previews have two handles (radius and height); sphere previews have one radius handle.

## 0.7.9.62 - 2026-10-17

### Added
- Drag dimension handles directly in the Box, Cylinder and Sphere previews to resize primitives, with live measurements and synchronized numeric fields. Handles follow the chosen placement plane; Escape cancels a drag or the tool.

### Fixed
- Stop pending primitive previews after OK/Cancel and return the created sphere body correctly.

## 0.7.9.61 - 2026-10-17

### Added
- Larger navigation cube with face-aligned labels, hover highlighting, 26 face/edge/corner views and drag-to-orbit navigation, inspired by Layerling.

### Fixed
- Correct mirrored cube orientation and align the Home button hit area with its drawing; resolve clicks from their actual position.

## 0.7.9.60 - 2026-10-17

### Added
- Settings → Sketch & View: adjustable guide line gap (1–50 screen pixels, default 6), saved between sessions.

### Fixed
- Prevent floating-point rounding from stalling dashed guide line rendering with fractional gap values.

## 0.7.9.59 - 2026-10-17

### Fixed
- Construction (guide) lines in a sketch are now drawn dashed instead of solid.

## 0.7.9.58 - 2026-10-17

### Fixed
- **Emboss turned into a flat extrude after editing the text** (#60): `EmbossFeature._surface_behind` only cast one ray from the text's centroid to find the cylinder behind it, so a longer string whose centroid ended up beside the cylinder missed it and the letters were extruded flat at the sketch plane. It now tries the centroid first and then points spread across the text, so the letters keep wrapping the cylinder.
- **Offset Plane and construction planes were drawn far too large**: the preview and the finished plane are now drawn at the same size as the origin plane markers, centred on the plane, and the click area matches.

### Added
- **Settings for the line under the cursor** (#52): *Settings → Appearance* has a new colour (*Line under the cursor*, default white) and thickness (*Line under cursor, thickness*, 1-12 px, default 3.5) for the edge or sketch line you hover over.

## 0.7.9.57 - 2026-10-17

### Fixed
- **Missing or swapped letter parts (`e`, `o`, `a`, `å`, `ä`, `ö`) after editing sketch text** (#44): when a `SketchText`'s height, font, spacing or string content was edited, `solve_profiles()` could reorder profiles so a letter's outer profile and its counter-hole swapped indices or changed count, causing `Emboss` / `Extrude` / `Revolve` to pick the inner hole instead of the letter. `ProfileRefs` now tracks `_follows_text` and automatically synchronizes with `sketch.text_profile_indices()` whenever text is edited.
- **UI responsiveness & anti-freeze during live 3D previews**: added 50–60 ms `QTimer` debouncing and interactive quality mode (`quality.set_interactive_mode(True)`) to live previews in `feature_edit.py` and `tool_prompts.py`, precomputed fillet edge resolution outside the spinbox callback in `feature_edit.py`, added fast Ray–AABB bounding-box rejection in `picker_mixin.py`, and cleaned up stale OpenGL VAO/VBO cache entries in `render_mixin.py`.
- **`EQUAL` constraint between circles**: `solve_sketch()` now writes back solved radii for all `SketchCircle` entities whenever the solver changes their radius (not only polygon group circles).

### Added
- **Dimensioning for Arcs and Slots (`D` tool & right-click menu)**: clicking a `SketchArc` with the Dimension tool sets its **Radius (`R`)**; clicking a `SketchSlot`'s side sets its **Center-to-Center Length**, and clicking its rounded end cap sets its **Slot Width (`Ø`)**. Both are also available in the right-click context menu.
- **Complete Timeline Editing for `Split Body`, `Shell`, `Combine` and `Thread`**:
  - Added full timeline editing + live 3D split-plane preview for `Split Body`.
  - `Shell` timeline editing now preserves and allows changing open faces (`open_faces`).
  - `Combine` timeline editing now updates `target_body_id` and `tool_body_id` with historical body names from before the step.
  - `ThreadFeature` now persists `exprs` and `suppressed` across save/load and timeline edits.
- **Browser & Ribbon polish**: enabled renaming construction planes (`cplane`) in the Browser, unchecked all 14 sketch tool buttons when leaving sketch mode, added missing timeline icons/tooltips, and translated remaining Swedish UI strings in `side_panel.py`, `tool_prompts.py`, `boolean_dlg.py` and `thread_dlg.py` to English.

## 0.7.9.56 - 2026-10-17

### Added
- **Start Offset in mm for Extrude** (#43): added a **Start Offset** field (`mm`, with formula and parameter support) in *Extrude* so extrusions (*One Side*, *Symmetric*, *Two Sides*) can begin at a signed offset distance from the sketch plane, with live 3D handle positioning and timeline editing support.

### Changed
- **Offset Face dialog**: removed the embedded thread-fit guide box from the *Offset Face* panel.

## 0.7.9.55 - 2026-10-17

### Added
- **Live 3D preview when editing from Timeline** (#31): editing any step from the timeline (*Extrude*, *Emboss*, *Revolve*, *Box*, *Cylinder*, *Sphere*, *Fillet/Chamfer*, *Offset Face*, *Shell*, *Combine*, *Pattern/Mirror*, *Move*, *Thread*) now shows a live 3D preview in the viewport while you adjust values and temporarily hides the replaced target body.
- **Edit Revolve, Shell and Combine from Timeline**: double-clicking or right-clicking a *Revolve*, *Shell* or *Combine* step in the timeline now opens its dialog to edit parameters.
- **Copy primitives with Pattern / Mirror** (#35): standalone primitives (*Box*, *Cylinder*, *Sphere*, *Thread*) can now be copied with *Linear Pattern*, *Circular Pattern* and *Mirror*, and are automatically pre-checked in the Pattern dialog when created last.
- **Easy text editing in sketches** (#38):
  - Clicking or double-clicking anywhere inside the letters or bounding box of a `SketchText` selects / edits it.
  - Added an **🔤 Edit Text…** button in the *Sketch Palette* whenever the active sketch contains text.
  - Text items are now listed as child nodes under their sketch in the *Browser* tree—double-clicking or right-clicking a text node enters the sketch and opens the text editor directly.
- **Full cylindrical wrapping (>180° / 360°) and Wrap toggle in Emboss** (#40): added a **Wrap around curved surface** checkbox (enabled by default) in *Emboss*. When enabled on a cylinder, the embossed/debossed profile wraps around the cylinder's circumference using true arc-length mapping (`theta = s / r`), supporting wide text and full 360° wraps; unchecking it uses flat projection.
- **Smart Box & Smart Cylinder** (#42): *Box* and *Cylinder* dialogs and timeline editors now include optional **Wall Thickness (Shell)** (hollow with open top), **Outer Edges** (*Fillet* or *Chamfer* + size) and **Inner Edges** (*Fillet* or *Chamfer* + size) in a single parametric step.
- **Standalone Offset Face button & clearer Guide Line button in Ribbon**: added `Offset Face` to the Solid tab when *Group Modify* is off, styled all ribbon dropdown menus consistently with the active theme, and renamed `Construct (X)` to `Guide Line (X)` (`┄`) with a clearer tooltip.

## 0.7.9.54 - 2026-10-17

### Fixed
- **Black tooltip box on timeline steps, Browser and Inspector** (#39): `TimelineBar.scroll_area`, `BrowserWidget` and `InspectorPanel` had selector-less stylesheets (`border: none; background: transparent;`) which cascaded to every descendant widget—including Qt's `QTipLabel` popup window—turning the tooltip background `RGBA(0, 0, 0, 0)` (solid black on Windows and Wayland). Scoped those stylesheets to their container classes/IDs (`QScrollArea`, `QWidget#BrowserWidget`, `QWidget#InspectorPanel`).

## 0.7.9.53 - 2026-10-17

### Fixed
- **Tooltips and button margins**: styled `QToolTip` globally, scoped `TimelineChip` frame styles, and reduced `QPushButton` horizontal padding so dialog buttons (*Yes*, *No*, *Send request*) never clip text on high-DPI / low-resolution screens.
- **Settings dialog cleanup**: removed duplicate *Toolbar button size* control, organized preferences into clear tabs (*Appearance*, *Interface*, *Sketch & View*, *General*), and integrated *Theme Editor* as a button inside *Appearance*.

## 0.7.9.52 - 2026-10-17

### Added
- **Your own image in Request a change / Report problem**: the dialog has *Use my own image…* (pick a PNG/JPEG from your computer; you can zoom and draw on it) and *Use the screenshot* to go back. With your own image, it is sent instead of the built-in screenshots (`screenshot_own.png`).

## 0.7.9.51 - 2026-10-17

### Fixed
- **Emboss / Deboss now hugs a cylinder** (via the in-app report): text sketched on a plane in front of a cylinder used to float at the plane; the letters now wrap round the cylinder behind them (standing the depth above its surface, or pressed in for Deboss) and are joined to it. A flat face behind a sketch plane in the air is reached too.

## 0.7.9.50 - 2026-10-17

### Added
- **Text in sketches** (Sketch > Text, as in Fusion): options in the side panel: Type (*Text* in a frame, or *Text On Path* along a circle, arc or line), the text (several lines), Font, Bold / Italic, Height (of a capital letter), Character spacing, Horizontal and Vertical alignment, Angle, Flip, and for a path: Placement (above / below) and *Fit to path*. A ghost follows the cursor; click to place, or click the circle / arc / line the text follows (it lights up). The letters are real sketch profiles, with the holes of O, A, B ... as holes: they can be extruded, embossed, moved (M), rotated, mirrored (Mirror makes a mirrored copy), saved, and the text moves with its path when the circle changes. Right-click a text: **Edit Text…** or **Explode Text** (turns it into lines). Placing and editing is one undo step; Cancel / Esc removes it.
- **Emboss** (Solid > Create > Emboss, as in Fusion): pick the profiles (it starts with all the letters of the newest text sketch picked; *Select all text of this sketch*), set the **Depth** (positive = Emboss adds material, negative = Deboss presses it in; the Effect follows the sign), **Flip normal**, **Horizontal / Vertical distance** and **Rotation**. Live green / red preview, one undo step, editable from the timeline, formulas and parameters work. Emboss steps can be copied round a circle with Pattern / Mirror (Circular pattern).

## 0.7.9.49 - 2026-10-17

### Changed
- The SOLID / SKETCH selector moved out of the ribbon: it is a small bar in the 3D view directly above the Browser, part of the big box, and the Browser moved down to make room. SKETCH still appears only while a sketch is open. The ribbon is one row lower (just the buttons).

## 0.7.9.48 - 2026-10-17

### Changed
- All ribbon buttons are the same size, in both tabs, with and without names (the widest plain button sets the width), instead of each button being as wide as its own text. The small margins from 0.7.9.47 are kept.

## 0.7.9.47 - 2026-10-17

### Changed
- Timeline: only the last step shows its name, the others are small icons. Hover a step and it grows to show its name, and the model shows what that step made: green = material it added (a coil, an extruded face with its preview), red = material it removed; a sketch step lights its sketch up. Moving away restores what you had (a step you clicked stays coloured). A quick pass over the steps does not compute anything.
- The SOLID / SKETCH tabs are small muted text on the window's own background instead of a band of their own, with a thin line under the active one.
- Ribbon buttons have much smaller margins, with and without text, so more fit and the ribbon is lower.

### Fixed
- Help > Changelog has a Close button and opens at the newest version (it used to open at the oldest entries at the bottom).

## 0.7.9.46 - 2026-10-17

### Changed
- The bar at the bottom of the window is gone, and with it the *Report problem* button (F9 and Help > Report problem still work). The status message now sits in the 3D view above the Azimuth / Elevation / Zoom line, and the sketch status and the units at the lower right, as plain text that takes no room of its own. A running background job shows "Working…" in the same line. The view is about 50 px taller.

## 0.7.9.45 - 2026-10-17

### Added
- A thread on a cylinder now follows the cylinder's diameter (#37): it is measured when the Thread step runs, so an Offset Face (or any earlier step) that changes the cylinder carries the thread along; the difference you typed (for example -0.01 mm) is kept. New threads on a cylinder follow by default; in *Edit Thread* the checkbox **Follow the cylinder's diameter** switches it on for an older thread (it then takes the cylinder's diameter as it is now).

## 0.7.9.44 - 2026-10-17

### Fixed
- Under a section view the preview of a cut (Extrude cut, Offset Face ...) was partly hidden behind the opaque cut face; it is now drawn after it and shows through the cross-section (#36).

## 0.7.9.43 - 2026-10-17

### Changed
- Move / Rotate gizmo: smaller wheels and arrows, pale and translucent until the mouse is on them. Rotation rings show degree ticks (every 15°, longer at 45° and 90°) outside the ring: drag close to the ring to turn freely, drag outside the ticks to snap to 15° steps.

## 0.7.9.42 - 2026-10-17

### Added
- Move / Rotate: **Face to face**. Press *Pick two faces…*, click a face on the body, then the face or plane it should go to; the movement and turning are filled in (live preview). *Direction*: **Touch** (turn so the faces meet, like assembling parts), **Flush** (both faces look the same way, in one plane) or **Slide** (no turning, along the target's normal). *Centre on target* puts the face's centre on the target's centre, off keeps the sideways position. Changing the choices recomputes from the same two clicks.

## 0.7.9.41 - 2026-10-17

### Added
- Right-click with two or more bodies selected: **Join N Bodies** (joins them into the first one, one undo step), in every right-click menu outside sketch mode.
- Thread / Coil: the lead-in is now a choice: *Smooth lead-in & runout* (0.75 turn), *Smooth lead-in & runout, short* (0.3 turn) to try, or *None*. Editing an existing thread selects the matching entry.

### Fixed
- Combine (the dialog) was not an undo step; it is now (`Document.combine_bodies`).

## 0.7.9.40 - 2026-10-17

### Added
- Planes without a tool: an origin or construction plane lights up under the cursor, and every shown plane has its name in small text in its lower-right corner as seen from the camera.
- Right-click on a plane: Split Body with this Plane, Offset Plane from this Plane, Create Sketch on this Plane, Hide Plane.
- Right-click on a flat face: Offset Plane from this Face.
- While Split Body is open, clicking a plane in the view makes it the splitting plane.

### Fixed
- A hidden origin plane could still be clicked and right-clicked where it would have been.

## 0.7.9.39 - 2026-10-17

### Fixed
- The Inspector (Design overview, Shortcuts, tool panels) is as wide as what it shows instead of a fixed 380 px, stays at the right edge, and the ViewCube moves along with it.
- The window screenshot in a problem report (F9) now includes the Browser and Inspector panels that float on the 3D view.

## 0.7.9.38 - 2026-10-17

### Fixed
- CI: the visual thread test skips itself without a real display (it crashed on the build server, so 0.7.9.37 was not released).

## 0.7.9.37 - 2026-10-16

### Fixed
- Offset Face on a thread gave no clearance: it changed the Thread step, and the jar is cut by the lid, so the lid's thread grew with the groove and the fit stayed exact. Now it is an Offset Face step that changes only the body you click: the threaded zone (coil and bore/pin) is rebuilt bigger or smaller and cut from or added to that body. -0.2 on the jar gives ~0.2 mm of air all round the lid's thread; the lid keeps its size.
- The thread offset is now the same along the whole coil, also in the lead-in taper.

## 0.7.9.36 - 2026-10-16

### Fixed
- Under a section view the live preview of a tool (Offset Face, Extrude ...) was the whole solid and covered what you were looking at, for example the thread inside a jar. It is now cut like the bodies.

### Added
- How-to video script `video/offset_thread_take.py` (Offset Face on a thread, with the Browser and the tool panel in the picture).

## 0.7.9.35 - 2026-10-16

### Fixed
- Offset Face on a thread did nothing when the click landed on the wall between the turns (a short cylinder band, "could not be moved"). A cylinder that is coaxial with a thread and inside its length now changes the Thread step too, so the whole threaded zone works.

## 0.7.9.34 - 2026-10-16

### Fixed
- A body hidden with its eye in the Browser came back after any rebuild of the history (for example Offset Face on a thread brought the lid, with its big thread, back into the jar). Hidden bodies now stay hidden.

### Changed
- The thread-fit guide is a small box inside the Offset Face panel (picture, text, Back/Next, Hide). "Bigger" opens the same guide in a large window at the same step.

## 0.7.9.33 - 2026-10-16

### Added
- In-app guides: Help > Guides opens a small window with pictures and short steps. The first guide, "Make a thread looser or tighter (Offset Face)", is also behind the "? Guide: thread fit" button in the Offset Face panel. Guide pictures are small JPEGs (max 900 px wide, 120 KB each) so the app does not grow.

## 0.7.9.32 - 2026-10-16

### Fixed
- The Offset Face explanation line was cut off at the bottom of the tool panel; it is shorter now ("Thread 1 coil: OK makes every turn 0.2 mm thicker.").

## 0.7.9.31 - 2026-10-16

### Fixed
- Offset Face on a thread: the live preview still deformed the mesh and looked hairy; it now shows the rebuilt thread, exactly what OK gives. The explanation line under the dialog text uses the theme's text colour (the yellow one was unreadable).

## 0.7.9.30 - 2026-10-16

### Added
- Offset Face explains itself: a tip on how to get a looser or tighter thread fit, and a line that says what OK will do when the picked surface is a thread coil ("makes the whole coil 0.2 mm thicker").

## 0.7.9.29 - 2026-10-16

### Changed
- Offset Face on a thread/coil surface now changes the Thread step itself (new `grow` value: the tooth profile is offset on every side) instead of deforming the finished mesh. The result is an exact, clean thread, it follows later Moves, and it is one undo step.

## 0.7.9.28 - 2026-10-16

### Added
- Hovering a sketch line, circle, arc or rectangle, or a solid edge, shows its measures (length, angle, radius, diameter) in the inspector (#30).

## 0.7.9.27 - 2026-10-16

### Fixed
- Ribbon buttons were clipped on Windows and the second row of constraint buttons was hidden in sketch mode (#33, #34): the ribbon had a fixed height. It now follows the height of its content.

## 0.7.9.26 - 2026-10-16

### Fixed
- Offset Face on a thread/coil left hundreds of wall vertices almost unmoved, giving a jagged result: micro triangles that flip by float rounding made the fold guard halve the step over and over. Only real triangles count now.

## 0.7.9.25 - 2026-10-16

### Fixed
- Offset Face on a thread or other curved surface no longer folds the flat faces next to it (end caps) into slivers: rim vertices slide within the neighbouring face, and a move that would turn a triangle inside out stops short.

## 0.7.9.24 - 2026-10-16

### Fixed
- **Request #32: Offset Face on a cylinder left slivers (fins) of the old wall behind** (the report's body fell apart into 53 pieces): the ring that is added or removed now reaches a little past the old wall, so no hair-thin remainder is left. Test with the report's document in `tests/test_offset_face_hover_and_slivers.py`.
- **Offset Face: cylinders, threads and other curved surfaces now light up under the cursor** (like flat faces), so you can see what a click will pick.

## 0.7.9.23 - 2026-10-16

### Fixed
- Offset Face under a Section View: clicks now hit the cut surface you see (for example the inner thread) instead of the half of the body that is cut away.

## 0.7.9.23 - 2026-10-16

### Changed
- **Section view: every body gets its own tint on the cut face** (yellow, light blue, green, pink, lavender, peach, in the order of the bodies), with hatching in a darker shade of the same colour, so touching bodies can be told apart. A single body looks as before. Test in `tests/test_section_hatch.py`.

## 0.7.9.22 - 2026-10-16

### Added
- **Offset Face works on curved surfaces such as threads and coils**: clicking a surface that is not flat or a plain cylinder picks the whole smooth patch around the click (a whole round thread, a flank, a fillet) and moves it along its own normal; + adds material, - removes it. Clicking the same patch twice moves it once. Tests in `tests/test_offset_face.py` (sphere, flat patch, real thread).

## 0.7.9.21 - 2026-10-16

### Added
- **Offset Face** (Modify > Offset Face, Modify menu in the ribbon, or right-click a face): click flat faces, holes or pins, type a distance (+ adds material, so a hole gets smaller; - removes it), OK. Made for tolerances on threads, pins and pockets. Flat faces move along their normal (neighbouring faces that are slanted stay bounded by their own planes); full cylinders change radius. Live preview, one undo step, editable in the timeline, formulas and parameters work in the distance. Tests in `tests/test_offset_face.py` and `tests/test_offset_face_ui.py`.
- **Help > Changelog** shows the whole `CHANGELOG.md` inside the app (searchable). The file is packaged with the app. Test in `tests/test_changelog_dialog.py`.

## 0.7.9.20 - 2026-10-16

### Fixed
- **Fillet at the foot of a leaning wall hung over the box edge when the radius was too big**: a concave straight edge was never size-limited, so the filling extended past the floor face. Like in Fusion 360 the radius is now limited so the fillet stays on the floor (and the wall). Fillets that fit were already exact. Test in `tests/test_wall_foot_fillet.py`.

## 0.7.9.19 - 2026-10-16

### Fixed
- **Mouse move raised AttributeError after 0.7.9.18** (panels in the 3D view looked displaced): `Viewport3D` never defined `hover_face` until Fillet/Chamfer was started, but the idle hover reads it on every move. It is now set in `__init__`. Test in `tests/test_idle_hover.py`.

## 0.7.9.18 - 2026-10-16

### Fixed
- **No hover highlight outside Fillet/Chamfer** (report via F9): edges and flat faces now light up under the cursor whenever nothing is being edited, and right-clicking a lit edge (or a face) offers Fillet / Chamfer, which opens the tool with those edges already picked. Test in `tests/test_idle_hover.py`.

## 0.7.9.17 - 2026-10-16

### Fixed
- **The four timeline playback buttons were empty squares** (the arrow emoji did not render): they now have drawn icons (rewind, step back, step forward, fast forward) in all three icon sets, and follow the theme. Test in `tests/test_timeline_icons.py`.

## 0.7.9.16 - 2026-10-16

### Added (request from Björn)
- **Right-click on a sketch in the 3D view offers Edit Sketch** (also Extrude and Hide Sketch): on the sketch's lines or circles, and "Edit Sketch" also leads the menu when you right-click inside one of its shaded profiles. Test in `tests/test_browser_tree.py`.

## 0.7.9.15 - 2026-10-16

### Changed (requests from Björn: browser like Fusion 360)
- **The browser tree is built like Fusion 360's** (same colours/theme as before): `(Unsaved)` / the file name at the top, then Document Settings (Units, Parametric Design), Named Views (Home, Top, Front, Right, Back, Left, Bottom; click one to go there), Origin, Analysis (the section views), Bodies, Canvases and Sketches. All sketches sit under Sketches (also those drawn on a body face). Bodies, Canvases and Sketches have an eye on the group that shows/hides everything in it, and **V** shows/hides the selected item. The group names no longer carry counts, so open/closed state is kept.
- **Right-click menus like Fusion 360:** sketch: Extrude (E), Offset Plane, Edit Sketch, Rename, Show/Hide (V), Find in Window, Find in Timeline, Delete; body: Move, Shell, Split, Rename, Show/Hide, Find in Window/Timeline, Export STL/STEP, Delete; planes and canvases got Show/Hide and Rename too. Find in Window frames the body or sketch, Find in Timeline scrolls to its step and colours what it changed.
- **Menus were black:** every pop-up menu is now dark grey with an orange selection, like the menu bar.
- Tests in `tests/test_browser_tree.py`.

## 0.7.9.14 - 2026-10-16

### Changed (request from Björn: Section View like Fusion 360)
- **The cut face of a section view is hatched like Fusion 360:** pale yellow with dark diagonal hatching and a black outline (holes stay open), instead of a flat highlight colour. The hatching keeps about the same density on screen when you zoom. Logic in `omacad/model/section_hatch.py` (shapely), drawing in `render_section_cap`. Tests in `tests/test_section_hatch.py`.

## 0.7.9.13 - 2026-10-16

### Fixed / Changed (reports from Björn)
- **Tick boxes were black** (Pattern "Copy these steps", "Second direction", every list/tree/dialog check box): no theme was applied to the indicators, so the style drew black boxes where a tick could not be told from an empty box, which made it look impossible to un-tick a step. They are now a clear empty box and an orange box with a white tick, in the theme's colours (`theme.indicator_stylesheet`, set on the application).
- **The tool panel fits its content:** the panel on the right is now only as tall as the open tool needs (no scrolling when there is room), and only scrolls when the window is too short. The sideways scrollbar is gone (the panel is 380 px wide for the 358 px tool boxes). Test in `tests/test_tool_panel_fit.py`.

## 0.7.9.12 - 2026-10-16

### Changed (requests for change from Björn)
- **Smart Circle works with lines at any angle:** step 2 now measures from the centre, at right angles, to the nearest straight line of any angle (vertical, horizontal or slanted; sketch lines and face edges); step 3 does the same to the nearest line that is not parallel to the first, and the two distances fix the centre. Both steps are still needed. With nothing typed a step still just takes the cursor, as before. The dotted measure line and the dimensions it creates (distance from the centre to the line) follow the right angle. Before, only vertical and horizontal lines were considered. Tests in `tests/test_smart_circle.py`.
- **New Dimension icon:** the Dimension button no longer uses the ruler (that is the Measure icon). It shows a Fusion 360 style dimension: a shape with extension lines, a dimension line with arrowheads and a value box (all three icon sets).

## 0.7.9.11 - 2026-10-16

### Changed (requests for change from Björn)
- **No sketch-mode banner:** the "SKETCH MODE: Sketch 1 (XY) · Under defined" box at the top of the 3D view is gone (it covered the drawing). The sketch name, plane and solve status ("Under defined (2 DOF)") now sit at the right end of the status bar.
- **Dimension value box in the 3D view:** with the Dimension tool, as soon as two points are picked a small box appears next to them showing the distance as it is. It follows the cursor (above/below = horizontal, left/right = vertical, diagonal = aligned) until you type; type a number, a formula or a parameter name, then press Enter or click to place the dimension (a click without typing keeps the measured value, Esc cancels). Other dimension values (diameter, length, angle, distance to a line, editing an existing dimension) also open as a box next to the cursor instead of in the side panel. Tests in `tests/test_inline_dimension_box.py`.

## 0.7.9.10 - 2026-10-16

### Changed / Added (requests for change from Björn)
- **Smaller plane markers:** the origin plane markers (shown while picking a plane, and when you turn a plane on under Origin) now cover only the first quadrant of each plane (positive u and v) and are smaller: 20 mm, or 75% of the model's largest coordinate. Only that quadrant can be clicked. Test in `tests/test_origin_plane_quadrant.py`.
- **Thread / Coil at the top of a cylinder:** after picking a cylinder (outside or inside) the Thread dialog has "Place at: Bottom end / Top end" and a gap in mm from that end, so a short thread no longer always starts at the bottom. A thread longer than the free space falls back to the bottom. Stored on the step (`anchor`, `anchor_gap`, `host_length`) so it can be edited and is saved. Tests in `tests/test_thread_anchor.py`.

## 0.7.9.9 - 2026-10-16

### Added (request for change from Lennart: distances between objects, movable dimensions)
- **Drag a dimension out of the way:** in a sketch, press a dimension badge and drag it; the dimension line follows the cursor (length, rectangle sides, diameter/radius, angle, horizontal/vertical/aligned distance, distance from a point to a line). A plain click still edits the value. A drag is one undo step. Logic in `omacad/model/dim_layout.py` (`offset_for_point`, the inverse of the drawing layout).
- **Distance between two parallel lines:** with the Dimension tool, clicking two lines that are parallel (within 0.5 degrees) now gives a distance (and keeps them parallel with a constraint) instead of an angle.
- **Set the distance between two bodies (3D):** in the Measure tool pick an edge on each of two bodies, then press D, type the wanted distance and the second body moves along the measured line (a Move step in the timeline, so it can be edited and undone).
- Tests in `tests/test_dimension_distance.py`.

## 0.7.9.8 - 2026-10-16

### Added (request for change from Björn: files)
- **Unsaved-changes question:** New Design, Open (also from Open Recent) and closing the window ask "Do you want to save the changes to <name>?" (Save / Don't Save / Cancel) when the design differs from what is on disk. A cancelled Save As or a failed write keeps the current design. Selecting or moving the camera is not a change.
- **File > Open Recent** (last 10 files, newest first, missing files are removed, "Clear Recent Files"). Files are added when opened or saved.
- Save As already existed (File > Save Project As..., Ctrl+Shift+S). Tests in `tests/test_file_session.py`; the logic is in `omacad/ui/controllers/file_session.py`.

## 0.7.9.7 - 2026-10-16

### Fixed
- **The Browser tree collapsed whenever something changed** (hiding a plane, axis, body ...): the tree is rebuilt from the document on every change and every node came back with its default state (the Origin group closed). Now the expanded/collapsed state of every node and the scroll position are kept across a rebuild. Test in `tests/test_origin_visibility.py`.

## 0.7.9.6 - 2026-10-16

### Added (request for change from Lennart: control what is shown of the origin)
- **Origin visibility:** the whole origin, each of the X/Y/Z axes and each of the XY/XZ/YZ planes can be shown or hidden, from the eye icons in the Browser (Origin group) or from View > Origin. The planes are hidden by default, as before; showing one draws it as a translucent quad. Turning a single part on also turns the origin back on. The axes no longer depend on the ground grid being shown. The choice is saved in the `.omacad` file (`origin_vis`). Picking a plane while sketching still shows all three. Tests in `tests/test_origin_visibility.py`.

## 0.7.9.5 - 2026-10-16

### Changed (request for change: bigger drawing area)
- **Icon-only ribbon:** the text under the toolbar buttons is gone by default, buttons and margins are tighter and the ribbon is about 30% lower, so the drawing area gets bigger. Hovering a button shows a tooltip that starts with its name. Settings > Sketch & View has "Show button names under the toolbar icons" to bring the labels back. Test in `tests/test_ribbon_compact.py`.

## 0.7.9.3 - 2026-10-16

### Added & Enhanced (Fusion 360 Parity)
- **Fuskion420-tema (Fusion 360 färgval):**
  - Nytt tema `assets/themes/fuskion420.toml` med exakta färgval från Autodesk Fusion (canvas `#F7F7F7`, grid `#D8DDE3`, accent/highlight `#0696D7`, finish green `#2E7D32` och rena gråa nyanser).
  - Valbart i Settings-dialogen under Theme Mode ("Fusion 360 (fuskion420)").
- **Genomskinligt Browser-träd:**
  - Vänstra Browser-panelen har gjorts genomskinlig och integrerad i skärmen så 3D-vyn syns igenom, med flytande hover- och markeringsstilar precis som i Fusion 360.
- **Filnamn i menyraden:**
  - Det aktiva dokumentets filnamn visas nu tydligt uppe till höger i menyraden med ren typografi och ikon (`📄 <filnamn>`).
- **Genomskinlig Inspector (högra verktygsfältet):**
  - Högra verktygsfältet är nu helt genomskinligt där det inte finns innehåll. Endast aktiva verktygsdialoger, sketch palette och infokort har kortbakgrund, medan tomma ytor smälter in i 3D-skärmen.

## 0.7.9.2 - 2026-10-16

### Fixed
- **Settings-dialogen och sparaknappar på mindre skärmar (Windows):**
  - Flikarna i Settings-dialogen (Theme samt Sketch & View) är nu inbäddade i `QScrollArea` och dialogens initiala storlek är anpassad så att Save/Cancel-knapparna längst ned alltid syns och går att klicka på oavsett skärmupplösning eller skalfaktor i Windows.
  - Regressionstest tillagt i `tests/test_settings_dialog.py`.

## 0.7.9.1 - 2026-10-16

### Fixed
- **Fill face pattern on edge-based features without sketches (e.g. chamfers/fillets on bottom face):**
  - When patterning a fillet or chamfer with "Fill face pattern" (such as chamfering holes on the bottom face of a model), the pattern failed because `_source_plane` assumed the source feature was created from a sketch (`sk.plane`).
  - Now `PatternFeature._source_plane` determines the target face plane from the feature's edges and planar face matches on the body, or from the coplanar faces of the modified region.
  - Regression test added in `tests/test_fill_face_chamfer.py`.

## 0.7.9.0 - 2026-10-15

### Added & Fixed (Fusion 360 Parity)
- **Markering av plana ytor i Fillet och Chamfer (Fusion 360-paritet):**
  - I Fillet/Chamfer-kantmarkeringsläge kan användaren nu klicka direkt på en plan yta (eller hovra över den) för att markera alla dess yttre gränskonturer och inre hål/slitsöglor på en gång, precis som i Fusion 360.
  - Hovring över en plan yta i kantläget ger en genomskinlig färgmarkering för tydlig feedback.
  - Klick på en plan yta markerar alla tillhörande loopar/kanter; om de redan är markerade avmarkeras de (eller avmarkeras selektivt med Ctrl+klick).
  - Löser problemet där användare vänt en modell upp och ner och försökt fasa/runda undersidan och dess konturer.

## 0.7.8.9 - 2026-10-15

### Fixed
- **Markering av LoopEdge vid överlappande cirkelbågar (Fillet/Chamfer):**
  - På plana ytor med sammansatta konturer (raka sidor och hörnradier, t.ex. avrundade plattor) fanns både en övergripande `LoopEdge` och enskilda `CircularEdge`-bågar för hörnen. Vid klick för kantmarkering prioriterades cirkelbågen om den låg marginellt närmare skärmklicket, vilket hindrade användaren från att markera och fasa/runda hela ytterkonturen. Nu prioriteras `LoopEdge` vid sammanfallande kanter (near-ties inom 1 px) i `_pick_edge`.

## 0.7.8.8 - 2026-10-15

### Performance & Fixed (Shell Feature)
- **Massiv optimering av Shell-verktyget:**
  - Snabbväg `_shrink`: Planära och konvexa solider eroderas nu inåt via snabba planförskjutningar (`trim_by_plane`) i stället för tung 3D Minkowski-difference, vilket ger en hastighetsökning på 20–50×.
  - Optimerad sfärupplösning för Minkowski-beräkningar på krökta solider för att drastiskt reducera CPU-belastning.
  - Debounce (75 ms) på förhandsvisningen i Shell-dialogen för att förhindra att UI:t fryser vid snabb textinmatning eller stegning av väggtjocklek.

## 0.7.8.7 - 2026-10-15

### Performance & Engine (High-Performance Engine)
- **Topologicache för plana ytor och kanter:**
  - `compute_planar_faces_and_edges` cachar nu analysen per geometriskt fingerprint, vilket ger över 800× snabbare uppslag för oförändrade solider.
- **Inkrementell tidslinjeomräkning (Incremental Timeline Recompute):**
  - Tidslinjen sparar och återanvänder checkpoints för stegen i historiken; vid ändring beräknas enbart påverkade nedströmssteg om istället för hela historiken från steg 0.
- **GPU VBO/VAO Caching för 3D-solider:**
  - Viewporten laddar nu upp body-meshar och skarpa linjekonturer direkt till dedikerade GPU VBO/VAO:er så kameranavigation (orbit/pan/zoom) flyter med full GPU-framerate utan CPU-tapp.
- **Adaptiv tessellering under interaktiv dragning:**
  - Under aktiv dragning i 3D-handtag (t.ex. extrude-pil) används en optimerad lägre segmentupplösning, med automatisk återgång till full finupplösning vid släpp.
- **Profilcache för 2D-skisser:**
  - `Sketch.solve_profiles` fingeravtryckstestar linjer och referenser för att undvika onödig Shapely-polygonisering.
- **Bakgrundstråd (`QThreadPool`) och laddningsindikator:**
  - Integrerad trådpool och progressindikator i statusraden för asynkrona geometriberäkningar.

## 0.7.8.6 - 2026-10-15

### Performance & Fixed
- **Prestandalyft för solider och omräkning av tidslinjen:**
  - `compute_planar_faces_and_edges`: delar topologisk analys mellan ytor och kanter i en enda genomgång istället för dubbla körningar.
  - Snabbväg för enkla trianglar i `_group_min_width` och tidig exit i `_curved_roots` gör igenkänning av plana ytor och kanter upp till 6× snabbare.
  - Live-preview i Thread & Coil har fått 60 ms debounce vilket förhindrar att UI:t fryser vid snabb textinmatning eller stegning i spinnboxar.
  - Tidslinjeomräkning på modeller med coils och gängor går nu över 70 % snabbare, och hela testsviten exekverar på halva tiden.

## 0.7.8.5 - 2026-10-15

### Fixed
- **Automatisk kapning av fnas och överhäng på gängändar (Thread / Coil end trimming):**
  - Gängor och coils kapas nu automatiskt exakt längs ändplanen `z=0` och `z=length` med `trim_by_plane`.
  - Detta eliminerar fnas och profiler som sticker ut förbi cylinderns ändytor vid både trapetsformade, metriska och runda profiler.

## 0.7.8.4 - 2026-10-15

### Added
- **Valbar AI-agent för felrättning (agy / Claude / Gemini / Omarchy):**
  - Stöd för att köra **Antigravity CLI (`agy`)** direkt när fel rapporteras (F9).
  - Möjlighet att välja standard-AI i Inställningar (`Ctrl+,` -> *Sketch & View* -> *AI agent for fixing errors*).
  - Val av AI direkt i felrapporteringsdialogen med sparad standard.

## 0.7.8.3 - 2026-10-15

### Fixed
- A flat face is no longer split by 1e-9 float noise in tiny triangle normals, so the rim circle of a tilted cylinder top can be selected for Fillet/Chamfer.

## 0.7.8.2 - 2026-10-15

### Fixed
- **Rund gängprofil för burkar och behållare (DIN 168 / bottle round thread):**
  - Justerade rundprofilens radie och flankbredd till korrekta behållarproportioner (radial höjd ~0.22·pitch och axiell halvvidd ~0.28·pitch).
  - Integrerade exakt FDM-tolerans/clearance mellan utvändig gänga (burkhals) och invändig gängskärare (lock) så att lock glider på mjukt utan att kärva eller kollidera.

## 0.7.8.1 - 2026-10-15

### Fixed
- Rounded thread/coil left bare cylinder between the turns (wire radius was 0.22 x pitch). The ridge is now an ellipse almost as wide as the pitch.

## 0.7.7.3 - 2026-10-15

### Fixed
- **Dölj origin-plan vid cylinderplockning (*Hide Origin Planes in Thread/Coil Pick*):**
  - Stora origin-plan (XY, XZ, YZ) ritas inte längre ut och blockerar inte klick när du väljer cylindrar eller ytor för Thread / Coil.
  - Klick i 3D-vyn träffar nu garanterat cylinderytan eller modellens ytor utan att origin-planen kommer i vägen.

## 0.7.7.2 - 2026-10-15

### Fixed
- **Mått & Passning utan glapp (*Zero-Gap Seamless Attachment*):**
  - Åtgärdat beräkningen för spiralradier vid applicering på befintliga cylindrar. Coils och gängor lägger sig nu direkt på cylinderns ytteryta ($R = D/2$) med sömlös överlappning så att boolesk sammanfogning (`Join`) blir 100% vattentät utan något synligt glapp eller nedsänkning.
  - Korrigerat skärradien för invändig gängning i hål (`Cut`) så att gängspåret skär rent och med rätt djup in i hålväggen.
- **Helautomatisk aktivering & måttsättning (*Auto-Measure on Click*):**
  - När verktyget öppnas aktiveras ytplockning direkt – du behöver inte trycka på "Välj yta / cylinder", utan kan direkt klicka på valfri cylinder eller hål i 3D-vyn.
  - Cylindern mäts automatiskt och sätter in exakt diameter, längd samt rekommenderad stigning/preset anpassad för 3D-print.
  - Ytplockningen förblir aktiv så du enkelt kan klicka på andra cylindrar eller ytor för att direkt uppdatera måtten.

## 0.7.7.1 - 2026-10-15

### Added
- **Automatisk attach till cylinder (utsida eller hål):**
  - Klicka på mantelytan på en cylinder eller insidan av ett cylindriskt hål för att automatiskt fästa gängan eller coilen.
  - Omacad analyserar automatiskt geometrin och fyller i cylinderns mittaxel, diameter och längd.
  - Normalanalys känner av om du klickat på **utsidan** (Male / yttergänga) och ställer in `Join`, eller **insidan** (Female / innergänga) och ställer in `Cut`.
- **Rundad coil-profil (*Round / Circular Coil*):**
  - Lagt till profilen "Round / Circular Coil" för fjädrar, rundgängor, rörcoils och runda spiralspår med jämn och vattentät geometri samt konsekvent triangelorientering.

## 0.7.7 - 2026-10-14

### Added
- **3D-Print-optimerat gäng- och coilverktyg (*Thread / Coil*):**
  - **45° Trapezoidal-profil:** Eliminerar branta överhäng som säckar ihop i FDM-print. Kan skrivas rent oavsett munstycksstorlek eller lagerhöjd utan supportmaterial. (ISO 60° metrisk profil finns som valbart alternativ).
  - **Automatisk 3D-print tolerans/frigång (*Fit Clearance*):** Justerbar toleranskompensation (0.10–0.40 mm, standard 0.25 mm) anpassad för 0.4 mm munstycken så att bultar och muttrar inte nyper fast.
  - **Smooth Lead-in & Runout Taper:** Mjuk övergång och infasning under gängans första och sista varv för att förhindra snedgängning (cross-threading) och göra det enkelt att starta skruven.
  - **Snabbval / Presets:** Förinställda gängstandarder anpassade för 3D-print med lite grövre stigning (M6x1.25, M8x1.5, M10x2.0, M12x2.0, M16x2.5, M20x2.5, M24x3.0, M30x3.5) samt helt valfria anpassade dimensioner.
  - **Ytter- och innergänga:** Skapa antingen fristående bultar/kärnor eller applicera direkt på befintlig cylinder/hål i modellen (Join / Cut) med live 3D-förhandsgranskning.
  - **Full integration:** Registreras i parametriska tidslinjen (`ThreadFeature`), fullt redigerbar med dubbelklick och serialiseras i `.omacad`-filer.
  - **Ikoner för alla tre teman:** Nya handgjorda SVG-vektorikoner för *Modern Solid Fill*, *Technical Blueprint* och *Semantic Color-Coded CAD*.

## 0.7.6.4 - 2026-10-14

### Fixed
- The rotation gizmo rings crashed `paintGL` (a polyline was passed where line segments are expected); they are now drawn as segment pairs.
- Technical Blueprint icons for Offset Plane, Canvas, Parameters, Polygon, Rectangle and Slot were blank: the SVGs had duplicate `stroke` attributes and would not parse. `tests/test_icon_svgs.py` checks that every icon is valid XML.

## 0.7.6.3 - 2026-10-14

### Added
- **Combine: Behåll verktygskroppar (*Keep tool bodies*):**
  - Lagt till kryssrutan "Keep tool bodies" i Combine-dialogen (Fusion 360-stil). När denna är ikryssad förbrukas inte verktygskroppen (`tool body`) utan behålls i modellen efter Cut/Join/Intersect.
- **Interaktivt 3D-klick för att välja bodies i sidopanelens dialoger:**
  - När verktyg som **Combine**, **Split Body**, **Move / Rotate**, **Shell** eller **Pattern / Mirror** är öppna kan du nu klicka direkt på önskad solid i 3D-vyn för att välja eller ändra aktiv body i listorna till höger.

## 0.7.6.2 - 2026-10-14

### Improved
- **Tydlig styling och synlighet för rullgardinsmenyer (QComboBox):**
  - Rullgardinsrutor har nu en distinkt knappram med kontrastrik bakgrund (`#2D3138`), tydliga gränslinjer och en markerad drop-down-knapp med pil (`QComboBox::down-arrow`).
  - Förbättrad hover- och focus-återkoppling med CAD-accentfärg när menyn är aktiv.
  - Optimerade och förtydligade etiketter i dialoger (t.ex. Pattern/Mirror och Move) så att texter inte klipps eller försvinner bakom pilen.
  - Utökad bredd i sidopanelen till 380px (dialoger 358px) så att alla rullgardinsmenyer och etiketter ryms luftigt utan textavklippning.

## 0.7.6.1 - 2026-10-14

### Added
- **Fusion 360-stil på 3D Body Rotation Gizmo:**
  - Utökat Move-gizmon med 3 färgkodade cirkulära rotationsringar runt X (röd), Y (grön) och Z (blå).
  - Interaktiv vinkelrotering genom att klicka och dra direkt i ringarna med ren 5°/1° snäppning och direkt koppling till `rx`, `ry`, `rz`.
  - Uppdaterat Move / Rotate Body dialogen med aktiva knappar för både translationsaxlar (X, Y, Z) och rotationsaxlar (Rx, Ry, Rz).
- **Rotation av sketchelement:**
  - Implementerat `rotate_entity` och vinkelstöd i Move-verktyget för markerade sketchelement runt elementens geometriska mittpunkt / pivot.
  - Dynamisk inmatning (Tab) stöder nu `X`, `Y` och `Angle` för precis flytt och rotation av skisser.

### Fixed
- **Riktning på Fillet och Chamfer hjälppilar:**
  - Hjälppilen för fasning och avrundning pekar nu korrekt inåt mot materialet/avfasningen längs hörnbisektrisen (`d1 + d2` inåt mot kroppen på konvexa kanter) precis som i Fusion 360, istället för rakt ut i tomma luften.

## 0.7.6 - 2026-10-14

### Added
- **Tre teman och konsoliderad Theme-flik:** Lagt till tre tydliga lägen i Inställningar under en samlad flik "Theme":
  1. *Follow Omarchy system theme*
  2. *Light Mode: Clean Studio Latte*
  3. *Dark Mode: Tokyo Slate / Nord Frost*
  - "Start from" i temaeditorn har renodlats till de tre valda bas-teman.
- **Tre kompletta vektor-ikonteman:**
  - *Modern Solid Fill* (standard med fyllda stilrena former)
  - *Technical Blueprint* (tekniska konturlinjer och CAD-grafik)
  - *Semantic Color-Coded CAD* (färgkodade efter CAD-operationer)
  - Skarp rendering i alla upplösningar med dynamisk färganpassning efter ljust/mörkt tema.
- **Tydligare och taktila knappar i alla teman:**
  - Standardiserat QPushButton och Primary/Success/OK-knappar med förhöjd kontrast, distinkta ramar och bottenkanter för tydlig knappkänsla i både ljusa och mörka teman.
  - Ribbon-knappar har fått en subtil bakgrund och tydliga kantlinjer för ökad synlighet.
- **Flexibel placering av Box och Cylinder (Primitives):**
  - Stöd för att placera undersidan direkt i origo (`bottom_center`), hörn (`corner`), eller solid mittpunkt (`center`).
  - Stöd för placering direkt på godtycklig plan yta (*On face*) med orientering (horisontell/vertikal) och interaktiv val av yta i 3D-vyn samt live preview.

### Improved
- **Dockade verktygsdialoger i högerpanelen:** Verktygsrutor som Box, Cylinder, Fillet, Chamfer m.fl. dockas stabilt i högerpanelen (Inspector) så att de aldrig flyter iväg, försvinner eller skymmer 3D-modellen.

## 0.7.5.1 - 2026-10-14

### Added
- **Parameter auto-complete & parameter sets:** Typing in numeric fields now auto-completes parameter names with matching names and current values. Added "Save Set" and "Load Set" to the Change Parameters dialog to save and reuse parameter sets across projects.

### Fixed
- Extrude cut starting on a planar face no longer leaves an uncut zero-thickness coplanar skin/cap over the opening.
- Straight-edge chamfers and fillets now extend a tiny margin into the empty side of convex edges (just like circular loops already do), eliminating zero-thickness fins ("fnas") left in hole walls and inside polygon corners.

## 0.7.5 - 2026-10-13

### Fixed
- Mirrored/patterned holes left thin zero-thickness fins in their walls (debris after a later fillet): cuts that leave the body are now extended by moving the end-face vertices instead of unioning a shifted copy.

## 0.7.4.9 - 2026-10-13

### Fixed
- Fillet/Chamfer: picking an edge now selects the whole smooth chain (straight sides and tangent arcs), and the preview covers every picked edge instead of failing with "truth value of an array is ambiguous".

## 0.7.4.8 - 2026-10-13

### Fixed
- Sketch mode did not start and the viewport crashed in paintGL: the viewport modularization left the mixins without imports (`math`, `ctypes`, `Qt`, `theme`, sketch classes ...). Added them and a test that checks every module for undefined names.

## 0.7.4 - 2026-10-13

### Fixed
- **Shell: open faces can be picked again.** Clicking a face crashed (missing numpy import), and the hidden target body could not be hit. Shell now only offers the faces of the chosen body and no longer draws the origin planes.

## 0.7.3 - 2026-10-13

### Added
- **Trädstruktur för Bodies och Skisser**: Skisser som skapas på en yta av en viss kropp (eller Face-to-Sketch) grupperas nu automatiskt under den tillhörande kroppen som en utfällbar gren i Model Browser. Fristående skisser på basplan (XY, XZ, YZ) eller konstruktionsplan visas i en egen skiss-gren.
- **3D-markering av bodies med vänsterklick**: Klick på en solid i 3D-viewporten markerar kroppen direkt och sätter den som aktiv för verktyg som Move, Split och Shell. Klick i tomt utrymme avmarkerar.

### Improved
- **Shell live preview & skissrensning**: När Shell-verktyget öppnas döljs förbrukade skisser automatiskt. Ändring av väggtjocklek eller val av öppna ytor ger direkt 3D-förhandsvisning med tydlig färgmarkering på öppna ytor.

## 0.7.2 - 2026-10-13

### Improved
- **Direct typing on Extrude**: when starting Extrude or picking a sketch profile in the 3D viewport, the distance input field is immediately focused with its value selected so you can type the desired distance right away without having to click the text box. Keystrokes in the 3D viewport also automatically forward directly to the distance input.

## 0.7.1 - 2026-10-13

### Added
- **Toolbar button size** (Settings > Toolbar button size): adjust button and icon size in the top ribbon (Compact 75%, Medium 100%, Large 125%, Extra large 150%).
- **Fillet clearance clamping**: 3D fillet/chamfer automatically limits reach on convex straight edges so exaggerated radii do not cut past opposite walls or adjacent boundary edges.

### Fixed
- Dimension badges no longer obscure sketch circles/geometry when dimensioning circle to line.
- Smart circle anchor point fix: editing circle-to-edge distance moves the circle instead of shifting the entire sketch off origin.
- Removed redundant duplicate "BROWSER" inner header label in the left dock panel.

## 0.7.0 - 2026-10-13

### Added
- **Theme editor** (Settings > Theme editor): set every colour by hand (background, dark background, text, muted text, accent, 3D highlight, 3D view background, grid, and the four tool colours), see it live, save it under a name. Saved themes (`~/.config/omacad/themes`) appear with a star in the Theme list and carry their tool colours.
- `skills/omacad-video`: a skill describing how the demo videos are made (frame-exact capture, local narration and music).

### Fixed
- The inside of scroll areas (ribbon background, lists in dialogs) ignored the theme and stayed dark; Qt's own palette now follows the theme.
- Report problem / Request a change: the screenshot was shown too small on scaled (HiDPI) screens, and the dialog could be larger than a small screen so the text box was out of reach. It now fits the screen and the message box is framed and labelled.

## 0.6.34 - 2026-10-13

### Added
- Help > Request a change (F8): send a change request with screenshot and note; it is stored in a private GitHub repo for review. Unsent requests are kept locally and retried at startup.
- Whole UI in English.
- Windows build runs `Omacad.exe --selftest` before publishing.

## 0.6.33 - 2026-10-13

### Added
- **Choose the theme: follow Omarchy or pick one** (Settings > Färger > Tema): "Följ Omarchy-temat (live)" as before, or a fixed theme that Omarchy theme switches no longer change. The Omarchy themes are now bundled with the app (`assets/themes`), so the choice also works on Windows, where "Omacad standard (mörk)" is the default look.
- **Click in empty space to deselect the body** (a click on nothing clears the selection in the browser/inspector).

## 0.6.32 - 2026-10-13

### Changed
- **Smart Circle shows its numbers as dimensions while you type**: after Enter on the diameter, a diameter dimension appears on the circle; after each distance, a dimension line from the wall to the centre with its value. Before, the numbers only appeared once the circle was finished.

## 0.6.31 - 2026-10-12

### Fixed
- **Start-up error on a Windows PC** ("Error calling Python override of QProxyStyle::pixelMetric", repeated down the screen): the big-icon style could raise an error while Qt was drawing, which then repeated forever. It now falls back to the base style and never raises.

## 0.6.30 - 2026-10-12

### Fixed
- **Omacad.exe failed to start on some Windows PCs** ("LoadLibrary: invalid access to memory location"): the exe is no longer UPX-compressed or stripped, which could damage the Qt DLLs. It is larger but starts everywhere. The build also bundles python-solvespace, which was missing.

## 0.6.29 - 2026-10-12

### Fixed
- Pattern / Mirror finds nothing to copy when the hole is part of the extrude that creates the body (the default ticks start at the sketch, so there was no "before" body). It now copies the holes enclosed in the body's outline.

## 0.6.28 - 2026-10-12

### Changed
- **Fill pattern packs polygons of 3 to 8 sides tightly** (Staggered / Triangular layout): the lattice is now searched for the polygon itself, so squares form a square grid, hexagons a honeycomb, octagons their tightest grid, and triangles, pentagons and other odd polygons pair each copy with one turned 180 degrees. The gap between neighbours stays exactly the chosen value. Non-regular convex polygons work too.

## 0.6.27 - 2026-10-12

### Fixed
- **Fill pattern kept too far away from holes and bosses** (via F9): the edge margin was also applied round every hole and boss in the face, so large areas stayed empty. The margin now applies only to the outer edge; holes and bosses get just the gap between copies.

## 0.6.26 - 2026-10-12

### Fixed
- **Changing a rounded rectangle's width did nothing visible** (via F9): the solver moved one wall but left the corner arcs and the neighbouring lines behind. Fillet arcs are now refitted to their lines after every solve.

## 0.6.25 - 2026-10-12

### Changed
- **Rounded rectangles are sized by their overall width and height** (via F9): the two size dimensions now measure the whole part (left wall to right wall, bottom to top wall) instead of the straight pieces between the corners. Change them and the corner radii keep their mm, and anything dimensioned from a wall (a Smart Circle hole, for instance) follows that wall.
- **Move / Rotate Body: "Lay on plane"** (via F9): a button in the panel; click it, then click the face that should rest on the ground, and the rotation and height are filled in (adjust or OK). Works about the body centre or the world origin.

## 0.6.24 - 2026-10-12

### Fixed
- Problem report screenshot now includes the 3D view's overlay (sketch dimensions, banner, ViewCube).

## 0.6.23 - 2026-10-12

### Changed
- About now says "Vibecoded by Kindstrom".

## 0.6.22 - 2026-10-12

### Fixed
- Smart Circle picked from the ribbon dropdown could not take typed numbers, because the keyboard focus stayed on the ribbon button. The view now takes the focus when the tool starts and when the cursor moves over it.

## 0.6.21 - 2026-10-12

### Changed
- The ribbon's Circle button has a dropdown with Center Circle and Smart Circle.

## 0.6.20 - 2026-10-12

### Changed
- **Rounded rectangle: radius after width and height** (via F9): after you type width and height and press Enter, a third field, Radius, opens and the preview shows all four corners rounding as you type. Enter confirms (an empty Radius keeps the value from the sketch panel). Works for both rounded rectangle tools.
- **Smart Circle shows its mode**: until you have a diameter, a small dashed shadow circle follows the cursor so it is clear the tool is active.

## 0.6.19 - 2026-10-12

### Fixed
- **Fill pattern left channels and strips unfilled** (via F9): hairline cracks between the triangles of the face were widened to margin-wide stripes by the inset, so whole rows of copies were missing; and on a sketch plane whose origin is not the world origin the face was shifted against the copies, so copies landed off the plate. Both fixed.

## 0.6.18 - 2026-10-12

### Added
- **Smart Circle** (Shift+C, or right-click in a sketch → Draw → Smart Circle): place a circle with numbers and Enter. Type the diameter, Enter; then the distance from the centre to the nearest *vertical* line (a sketch line or a face edge, highlighted as you move), Enter; then the same to the nearest *horizontal* line, Enter. The cursor picks which line and which side (a minus flips the side); an empty field + Enter or a click takes the cursor position. Backspace on an empty field goes back a step. The circle gets a diameter dimension and a distance dimension for every typed value, so it stays parametric. Afterwards the tool is ready for the next circle.

## 0.6.17 - 2026-10-12

### Added
- **Fillet and chamfer on arcs** (via F9): an open arc where a flat face meets part of a cylinder (a concave cut, a rounded corner) can now be picked and rounded or bevelled, not only full circles and whole outlines. The step remembers the arc by centre, radius and angle. Measure shows radius, arc length and angle for an arc.

## 0.6.16 - 2026-10-12

### Changed
- **Shapes inside the profile you extrude stay open** (via F9): when sketches lie in the same plane and one shape sits inside the profile you pick, extruding the big profile no longer fills the shape in; it is left open, as in Fusion. The selection highlight leaves it unshaded. **Shift+click** a profile of another sketch in the same plane to include it again (Shift+click it once more to remove it). The extrude step stores the open shapes and the extra profiles, so they do not depend on which sketches are visible. Steps from older files are unchanged.

## 0.6.15 - 2026-10-12

### Fixed
- **Changing Curve smoothness broke the model** (via F9): Extrude and Revolve pointed at their profile by number only, and a sketch is numbered differently when circles are cut into a different number of pieces, so steps ended up on the wrong profile (a spike, or nothing). Steps now also remember each profile's centre and area and find it again. Files from before this (made at 48 pieces) are read at 48 first to remember their profiles, so they open right at any smoothness. A file written by this version stores `curve_segments` and the signatures.

## 0.6.14 - 2026-10-12

### Added
- **Mark up the report screenshot**: in *Report problem* you can zoom the picture (mouse wheel around the pointer, middle/right button or Ctrl+drag to move, double-click to fit) and draw with a pen, rectangle or arrow. The marked picture is saved as `screenshot_marked.png` and the agent is told to look at it first.
- **Click what to copy in Pattern / Mirror**: click a surface in the 3D view and the step that made it (and its sketch) is ticked in the list; click again to untick. `Document.step_at_point`.
- **Right-click on a sketch profile** gives a menu for that profile (Extrude, Revolve, Deselect, plus Undo/Redo and View) and selects it.

### Fixed
- Right-clicking the selected profile used to light up the whole face around it and open the face menu.

## 0.6.13 - 2026-10-12

### Added
- **Arrow settings** (Settings > Sketch & Visning): *Arrow size* (0.3-4x) and *Arrow distance from the surface* (default 2 mm). The extrude arrow is now always drawn that far off the surface, in the direction it points, so it never starts inside the material; the distance you drag is unchanged.

### Fixed
- Tests no longer read or write the user's real settings file (a changed Curve smoothness could make a test fail).

## 0.6.12 - 2026-10-12

### Added
- **Curve smoothness setting** (Settings > Sketch & Visning): how many flat pieces a circle is cut into (32 to 360, default 96, was a fixed 48). Lower is lighter for the computer, higher gives smoother round shapes. Applies to circles, arcs, cylinders and spheres; the model is rebuilt when you change it. `omacad/model/quality.py`.

### Fixed
- **Foot fillets did not flow into each other at corners**: filleting the straight edges at the foot of a polygon wall left a notch at every corner, because each band ended square. Neighbouring foot edges on the same floor now run past the corner and are cut along the bisector (mitred).
- **Fill pattern drew broken triangles in the middle of the face**: copies touching a hole or something standing on the face were clipped, leaving fragments. Now only the outer edge of the face may cut a copy; a copy that would touch a hole is left out whole.

## 0.6.11 - 2026-10-12

### Added
- **Lay a face flat**: right-click a face > *Lay this face on the ground (XY)* or *on a face or plane...* turns and moves the body (one undoable Move step) so that face rests on the plane. `Document.lay_face_on`, helpers in `omacad/model/geometry.py`.
- **Right-click while a tool panel is open** (Extrude, Fillet, ...): *Finish* and *Cancel* in the menu. Right-click on the Move arrows picks the axis (X/Y/Z).
- **Esc leaves the current function** wherever the focus is: first a pending step, then the sketch tool, then the open tool panel, then the selection.

### Fixed
- The distance on the extrude arrow stays after you release the mouse (it follows the arrow until the tool closes; symmetric extrude shows the full distance).
- Spin box up/down buttons were blank boxes in some themes: they now have a visible background and arrows in the theme's text colour.
- The X/Y/Z buttons in Move were too narrow and hard to read: short labels, in the axis colours (filled when active).

## 0.6.10 - 2026-10-12

### Fixed
- **Polygon "Sides" field said mm**: the number of sides is a count, so it is shown as a whole number without a unit.

### Added
- **Value on the extrude arrow**: while you drag the arrow, the distance is shown as a label beside the middle of the shaft.
- **More right-click menus**: on empty space in 3D you get New Sketch on XY/XZ/YZ, Undo/Redo and View (Home/Top/Front/Right, fit, grid, edges); in a sketch you get Finish Sketch, Draw and Modify tool lists, Dimension, Construction mode, Undo/Redo and View (Look at sketch). The Draw/Modify lists come from the registry `omacad/ui/sketch_tools.py` (rectangle kinds in a Rectangle submenu), so a new tool appears in the menu once it is listed there; `tests/test_sketch_tools_registry.py` fails if a tool is missing. The face menu and the sketch element menu also end with Undo/Redo and View.

## 0.6.9 - 2026-10-12

### Added
- **Camera settings** (Settings > Sketch & Visning): perspective field of view (10-60°, default 30° instead of the fixed 45° that made the view look skewed) and an orthographic camera. Changing either leaves the zoom unchanged; only the perspective distortion changes. Tests in `tests/test_projection.py`.

## 0.6.8 - 2026-10-11

### Added
- **Timeline click shows what the step did**: clicking a step in the timeline colours the material it added (green) and removed (red) in the view; a second click clears it.

## 0.6.7 - 2026-10-11

### Fixed
- **Rough edge when a foot fillet is too big for the shelf**: a fillet at the foot of a wall assumed flat face under it. When a rim fillet had already narrowed the shelf, the fillet hung over the rounding like a thin lip. The radius now shrinks to the widest one that still rests on the face, so the two roundings run out smoothly into each other.

## 0.6.6 - 2026-10-11

### Fixed
- **Top view jumped when orbiting**: passing 89° elevation switched the camera's up vector to world Y regardless of azimuth, so the view rolled up to 90° at once. Z is now up at every elevation (the orbit stops at ±89.9°), so the view turns smoothly over the top. The plan's milestones after 0.6.x were renumbered (0.7 and up).

## 0.6.5 - 2026-10-11

### Changed
- A sketch on a face now has its origin in the middle of the face (the origin snap locks to the centre; edges, corners and midpoints already snap) and a grid on the face plane, centred there and sized to the face, instead of the ground grid around the world origin.

## 0.6.4 - 2026-10-11

### Added
- **Center Rounded Rect**: a rounded rectangle drawn from its centre (fourth kind in the rectangle dropdown, uses the palette's corner radius).

### Changed
- The sketch palette now sits at the top of the right-hand inspector instead of floating over the canvas.

## 0.6.3 - 2026-10-11

### Added
- **Rectangle dropdown**: 2-Point, Center and Rounded Rect are one ribbon button. Clicking it draws the default kind, the arrow lists all three and *Button default* chooses which one the button draws (remembered in settings).
- **Automatic restart on a new version**: the app watches the commit of its source tree; when a new commit appears (e.g. the agent finished a reported fix) it saves the document, the sketch being edited and the camera to `~/.local/share/omacad/session.json`, restarts and puts everything back (`app.py --resume`). It waits while a dialog is open, cancels if saving fails, and can be turned off in Settings.

## 0.6.2 - 2026-10-11

### Added
- **Rounded Rect** (sketch ribbon): a two-corner rectangle with all four corners rounded in one step. The radius is the *Corner radius* field in the sketch palette (capped just under half the shorter side); the live preview shows the rounded outline and Tab still types width and height. Reported from the app with F9.

## 0.6.1 - 2026-10-11

### Added
- **Report problem (F9, Help menu, status bar)**: describe what is wrong; the app takes a screenshot (before any dialog opens), saves it with the whole document, the camera, the undo history and the log in `~/.local/share/omacad/feedback/<time>/`, and starts Omarchy's default coding agent on it (`omarchy agent prompt`) to reproduce, fix, test and commit. The log (status messages, printed output, errors) is recorded by `omacad/applog.py`.
- `omacad.md` (+ `AGENTS.md`, `CLAUDE.md`): the memory of the AI agents: architecture, rules, how to test, and a log of solved problems.

### Fixed
- **Sketch Offset with arcs**: lines and arcs are offset as whole chains. Arcs keep their centre and change radius (r - d inward, r + d outward), every joint is remade, so a rounded rectangle gives a rounded rectangle with no broken lines; an inward offset larger than the radius drops the arcs and closes the chain with sharp corners.

## 0.6.0 - 2026-10-11 (Trygghet)

### Added
- **Global undo / redo (Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y) for everything**: every step that changes the document (primitives, extrude, revolve, fillet/chamfer, shell, hole, pattern, move, split, import, parameter changes, timeline edits, rename/suppress/delete, offset planes, section views, canvases, deleting bodies, starting and finishing sketches) is one undo step. Edits inside a sketch still undo one at a time. *Finish Sketch* can be undone and takes you back into the sketch. The Edit menu shows what will be undone ("Undo Extrude"); undo waits while a tool panel is open or something is being dragged.
- Test suite (`tests/`, pytest): exact-volume checks for fillet/chamfer (irregular outlines, circles, edited history, rounded block foot), shell, revolve, hole, mirror, trim/offset/mirror in sketches, face edges, undo/redo of every step type and file round trips. CI runs it before the Windows build; a failing test stops the release.

### Fixed
- **Delete body** is now a real step in the history (it used to come back at the next rebuild) and can be undone.

## 0.5.2 - 2026-10-11

### Fixed
- Fillet/Chamfer at the **foot of a block with rounded vertical corners** (a wall rising from a flat face): only the straight pieces were filled and the corner arc was left out, giving a gap. The whole foot outline (straight pieces + corner arcs) is now one pickable edge that is filled in one go, for both Fillet and Chamfer. (Inner outlines were only recognised for outer rims before.)

## 0.5.1 - 2026-10-11

### Added
- **Box selection in sketches**: drag a box on empty space (left to right = only what is fully inside, blue; right to left = everything it touches, green). With **Fillet** the box picks all corners inside it (then Enter = one radius), with **Offset** it picks the chains it touches. Ctrl+drag adds to the selection. **Alt+drag orbits** in sketch mode.

## 0.5.0 - 2026-10-11 (Fusion 360 parity step 1)
Not yet released as a build. Includes everything from 0.4.1 below.

### Added
- **Revolve** is a real feature now: profile, axis (a construction line / any line of the sketch, or the sketch X/Y axis), angle (360 = full, negative flips), One Side / Symmetric / Two Sides, Auto/New/Join/Cut/Intersect, live preview.
- **Include / Project face edges**: sketching on a face includes its outline (lines, full circles, arcs) as real, purple sketch elements - offset them, trim them, snap to them, draw on them. Toggle "Include Face Edges" in the sketch palette; the **Project (edges)** button includes in-plane body edges in any sketch.
- Hole feature in the model (simple / counterbore / countersink, flat or 118 deg tip, through); dialog and placement come next.

### Changed
- Arrow handles (extrude etc.): the grab area follows the drawn head with a margin and a ring marks the grab point.

## 0.4.1 - 2026-10-11

### Added
- Sketch Fillet: **Shift+click** picks several corners (click a picked corner again to drop it), then **Enter** or a plain click on one more corner asks for one radius with live preview. One undo step.

- Sketch **Offset** works like Fusion: press O (or the ribbon button), a click takes the whole connected chain, click more curves to add (click a picked chain again to drop it, Alt+click = one element), Enter or right-click asks for the distance with live preview (negative = inward).

### Fixed
- Sketch selection: Shift+click used to pan instead of selecting, and Ctrl+click toggled twice. Both now add/remove one element.
- Rounded vertical corner standing on a lower step (stairs): a hairline notch was cut into the lower surface, drawn as a square corner outline round the rounded foot. The fillet tool now only reaches past an edge end where there is open space.

## 0.4.0 - 2026-10-11
First numbered version.

### Added
- Sketch **Trim** (T): remove the piece of a line, circle or arc up to the nearest crossings (dangling stubs too).
- Sketch **Mirror** (Shift+M): pick shapes, then a line or an origin axis.
- Pattern/Mirror: mirror steps across an origin or offset plane.
- **Shell** directions: Inside, Outside, Both (separate thickness each).
- Fillet/Chamfer edge picking: X / Alt see-through, Shift+double-click loop on the other face, Ctrl+click removes, Backspace undoes, Ctrl+Backspace clears.
- Version shown in the title bar and About dialog.

### Fixed
- Shell crashed on OK; Move Body dialog crashed on open.
- Fillet/Chamfer: mild bends in an extruded outline were taken for curved surfaces (walls not pickable); edges that moved after editing earlier steps were skipped (sharp edge left behind); inside corners of a bevelled outline got a notch; circle tools use the cylinder's segment count (half the triangles).
- Canvas image stayed the same when a new canvas reused an id.
- No demo "Base Box" at startup.
