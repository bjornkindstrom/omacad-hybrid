"""Every command a button, a menu entry or a right-click entry can start: one name, icon, shortcut and signal each.

The ribbon (`ribbon.py`) and the menu bar (`controllers/menu_setup.py`) are built from this list, so a command has
the same name and shortcut everywhere. A command's `signal` is the Ribbon signal it emits (with `arg` if given); the
main window connects each signal to its handler once. `modes` says where the shortcut is live: "model" outside a
sketch, "sketch" inside one (the sketch's own keys are handled by the viewport, see events_mixin.SKETCH_KEYS).

Layout follows Fusion 360 with few groups (the owner's choice): the SOLID tab has CREATE / MODIFY / INSPECT, the
SKETCH tab CREATE / MODIFY / CONSTRAINTS / INSPECT, and the menu bar Create / Modify / Inspect in the same order.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Command:
    cid: str
    label: str
    icon: str
    tip: str
    shortcut: str = ""                 # the main key, shown in tooltips and menus ("E", "Ctrl+P", "Shift+M")
    signal: str = ""                   # Ribbon signal name
    arg: Optional[str] = None          # argument for the signal (a pattern kind, a sketch tool, a constraint)
    modes: Tuple[str, ...] = ("model",)
    extra_shortcuts: Tuple[str, ...] = field(default_factory=tuple)


def _c(cid, label, icon, tip, shortcut="", signal="", arg=None, modes=("model",), extra=()):
    return Command(cid, label, icon, tip, shortcut, signal, arg, modes, tuple(extra))


_ALL = [
    # --- SOLID: CREATE -------------------------------------------------------------------------------------------
    _c("create_sketch", "Create Sketch", "✏️", "Start a sketch on a plane or a flat face", signal="create_sketch_clicked"),
    _c("extrude", "Extrude", "⬆️", "Pull closed sketch profiles or faces into bodies, or cut with them", "E",
       "extrude_clicked", extra=("Ctrl+E",)),
    _c("hole", "Hole", "🕳️", "Create simple, counterbore or countersink holes with optional entrance chamfer",
       signal="hole_clicked"),
    _c("revolve", "Revolve", "🔄", "Turn a sketch profile around an axis or edge into a solid", signal="revolve_clicked"),
    _c("emboss", "Emboss", "🔖", "Raise or press text (any sketch profile) into a face: positive depth raises it, "
       "negative presses it in", signal="emboss_clicked"),
    _c("sweep", "Sweep", "〰️", "Carry a sketch profile along a path (lines and arcs in a sketch)", signal="sweep_clicked"),
    _c("loft", "Loft", "🏺", "A skin through two or more profiles on different planes, in order", signal="loft_clicked"),
    _c("pipe", "Pipe", "🧪", "A round rod or tube along a path (lines and arcs in a sketch)", signal="pipe_clicked"),
    _c("box", "Box", "📦", "A rectangular box; the panel can also hollow, round and taper it", signal="box_clicked"),
    _c("cylinder", "Cylinder", "🥫", "A cylinder; the panel can also hollow, round and taper it", signal="cylinder_clicked"),
    _c("cone", "Cone", "🔺", "A cone or frustum: bottom and top radius (0 = a point) and height", signal="cone_clicked"),
    _c("hexagon", "Prism", "⬢", "A regular prism (6 sides = hexagon), sized across flats", signal="hexagon_clicked"),
    _c("thread", "Thread / Coil", "🔩", "3D-printable threads and coils, on a cylinder or on their own",
       signal="thread_clicked"),
    _c("jar", "Jar with Lid", "🫙", "A threaded jar and its screw lid, with thread tolerance, ready to print",
       signal="jar_clicked"),
    _c("pattern", "Pattern", "🔁", "Copy features (a rib and its fillets together): linear, circular, mirrored or "
       "filling a face", signal="pattern_clicked"),
    _c("pattern_linear", "Linear Pattern", "🔁", "Copies in a row or a grid", signal="pattern_kind_clicked", arg="linear"),
    _c("pattern_circular", "Circular Pattern", "🔁", "Copies around an axis", signal="pattern_kind_clicked",
       arg="circular"),
    _c("mirror", "Mirror", "🪞", "A mirrored copy across a plane", signal="pattern_kind_clicked", arg="mirror"),
    _c("pattern_fill", "Fill Face Pattern", "🔁", "Copies filling a face", signal="pattern_kind_clicked", arg="fill"),
    _c("honeycomb", "Honeycomb", "🐝", "Cut a lattice of hexagons, circles, squares, diamonds or triangles into flat "
       "and round faces", signal="honeycomb_clicked"),
    _c("offset_plane", "Offset Plane", "📐", "A new plane at a distance from a plane or face, or touching any surface",
       signal="offset_plane_clicked"),
    _c("canvas", "Canvas (Image)", "🖼️", "A reference image on a plane or flat body face: calibrate it and trace over it",
       signal="canvas_clicked"),
    _c("import_3mf", "Import 3MF", "📥", "Bring in the bodies of a 3MF file", signal="import_3mf_clicked"),
    # --- SOLID: MODIFY -------------------------------------------------------------------------------------------
    _c("fillet", "Fillet", "🔘", "Round edges (outside and inside corners): pick edges, type a radius",
       signal="fillet_clicked"),
    _c("chamfer", "Chamfer", "◢", "Bevel edges (outside and inside corners): pick edges, type a size",
       signal="chamfer_clicked"),
    _c("shell", "Shell", "🐚", "Hollow a body to a wall thickness, leaving picked faces open", signal="shell_clicked"),
    _c("offset_face", "Offset Face", "↔️", "Move flat faces, or change holes, pins and threads for a fit",
       signal="offset_face_clicked"),
    _c("combine", "Combine", "🔗", "Join, cut or intersect bodies", signal="combine_clicked"),
    _c("split_body", "Split Body", "🪚", "Split a body in two with a plane", signal="split_body_clicked"),
    _c("move", "Move", "✥", "Move or rotate a body: arrows, numbers, point to point, face to face", "M",
       "move_clicked"),
    _c("parameters", "Change Parameters", "🧮", "Named values usable in every number field", "Ctrl+P",
       "parameters_clicked"),
    _c("delete", "Delete", "🗑️", "Delete the selected bodies", "Del", "delete_clicked"),
    # --- SOLID: INSPECT ------------------------------------------------------------------------------------------
    _c("measure", "Measure", "📏", "Click an edge, line or circle for its size; a second one for distance and angle",
       "I", "measure_clicked", modes=("model", "sketch")),
    _c("section", "Section View", "✂️", "Cut through the model at a plane or face and slide the cut",
       signal="section_clicked"),
    _c("statistics", "Document Statistics", "📊", "How many bodies, sketches and steps the design has",
       signal="inspect_clicked"),
    _c("settings", "Settings", "⚙️", "Colors, ribbon layout and app preferences", "Ctrl+,", "settings_clicked",
       modes=("model", "sketch")),
    # --- SKETCH: CREATE ------------------------------------------------------------------------------------------
    _c("line", "Line", "✏️", "Connected straight lines", "L", "sketch_tool_selected", "LINE", ("sketch",)),
    _c("circle", "Circle", "⭕", "A circle from its centre", "C", "sketch_tool_selected", "CIRCLE", ("sketch",)),
    _c("smart_circle", "Smart Circle", "⭕", "A circle that snaps to what is around it", "Shift+C",
       "sketch_tool_selected", "SMART_CIRCLE", ("sketch",)),
    _c("arc", "3-Point Arc", "⌒", "An arc through three points", "A", "sketch_tool_selected", "ARC", ("sketch",)),
    _c("spline", "Spline", "〰️", "A smooth curve through a sequence of points; Enter or right-click finishes",
       signal="sketch_tool_selected", arg="SPLINE", modes=("sketch",)),
    _c("polygon", "Polygon", "⬡", "A regular polygon: centre, then out; Tab types side length and sides", "P",
       "sketch_tool_selected", "POLYGON", ("sketch",)),
    _c("slot", "Slot", "💊", "A slot from centre to centre and its width", "", "sketch_tool_selected", "SLOT",
       ("sketch",)),
    _c("text", "Text", "🔤", "Letters in a frame or along a circle, arc or line; they can be extruded or embossed",
       "", "sketch_tool_selected", "TEXT", ("sketch",)),
    _c("offset_sketch", "Offset", "⧉", "Click curves, including splines, to offset (Shift/Ctrl+click toggles one), type the distance",
       "O", "sketch_tool_selected", "OFFSET", ("sketch",)),
    _c("mirror_sketch", "Mirror", "🪞", "Pick curves to mirror, then the mirror line", "Shift+M",
       "sketch_tool_selected", "MIRROR", ("sketch",)),
    _c("project", "Project", "🟣", "Body edges in the sketch plane become sketch lines", signal="project_clicked",
       modes=("sketch",)),
    _c("dimension", "Dimension", "dimension", "Click a line, circle or two elements and type the size", "D",
       "sketch_tool_selected", "DIMENSION", ("sketch",)),
    # --- SKETCH: MODIFY ------------------------------------------------------------------------------------------
    _c("fillet_sketch", "Fillet", "╭", "Round the corner between two lines or a line and an arc", "F", "sketch_tool_selected", "FILLET",
       ("sketch",)),
    _c("trim", "Trim", "✂️", "Remove a curve up to the nearest crossings, or a dangling end", "T",
       "sketch_tool_selected", "TRIM", ("sketch",)),
    _c("move_sketch", "Move", "✥", "Move the selected sketch elements (or drag them)", "M", "sketch_tool_selected",
       "MOVE", ("sketch",)),
    _c("rotate_sketch", "Rotate", "↻", "Rotate the selected elements about a centre or a picked point", "Shift+R",
       "sketch_tool_selected", "ROTATE", ("sketch",)),
    _c("pattern_sketch", "Pattern", "⁘", "Copies of the selected elements in rows and columns or around a centre",
       "", "sketch_tool_selected", "PATTERN", ("sketch",)),
    _c("construction", "Construction", "┄", "Dashed helper lines (axes for Revolve and Mirror; Extrude ignores them); "
       "with curves selected, turns them into construction lines", "X", "toggle_construction_clicked",
       modes=("sketch",)),
    _c("fix_sketch", "Fix Sketch", "🩹", "Close what you drew into a face with the fewest changes: joins ends that nearly "
       "meet, extends lines that stop short, closes an open outline with one line", signal="fix_sketch_clicked",
       modes=("sketch",)),
    _c("finish_sketch", "Finish Sketch", "✅", "Back to 3D modelling", signal="finish_sketch_clicked",
       modes=("sketch",)),
]

COMMANDS: Dict[str, Command] = {c.cid: c for c in _ALL}

# A dropdown in the ribbon: (dropdown id, label, icon, tip, [command ids]). With the matching setting off its
# commands stand as separate buttons instead (Settings > ribbon layout).
PRIMITIVES = ("primitives", "Primitives", "📦", "Box, Cylinder, Cone, Prism, Pipe, Thread / Coil, Jar with Lid (each "
              "panel can hollow, round and taper)", ["box", "cylinder", "cone", "hexagon", "pipe", "thread", "jar"])
INSERT = ("insert", "Insert", "🖼️", "Canvas (Image) and Import 3MF", ["canvas", "import_3mf"])
MODIFY_BODY = ("modify_body", "Body", "🔗", "Combine, Split Body, Shell, Offset Face, Move",
               ["combine", "split_body", "shell", "offset_face", "move"])
INSPECT = ("inspect", "Inspect", "📏", "Measure, Section View, Document Statistics", ["measure", "section", "statistics"])
PATTERNS = ["pattern_linear", "pattern_circular", "mirror", "pattern_fill"]   # the Pattern button's arrow

SOLID_GROUPS: List[Tuple[str, list]] = [
    ("CREATE", ["create_sketch", "extrude", "hole", "revolve", "sweep", "loft", "emboss", PRIMITIVES, "pattern", "honeycomb", "offset_plane",
                INSERT]),
    ("MODIFY", ["fillet", "chamfer", MODIFY_BODY, "parameters", "delete"]),
    ("INSPECT", [INSPECT]),
]
SKETCH_GROUPS: List[Tuple[str, list]] = [
    ("CREATE", ["line", "rect", "circle", "arc", "spline", "polygon", "slot", "text", "offset_sketch", "mirror_sketch", "project",
                "dimension"]),
    ("MODIFY", ["fillet_sketch", "trim", "move_sketch", "rotate_sketch", "pattern_sketch", "construction", "fix_sketch"]),
    ("CONSTRAINTS", ["constraints"]),
    ("INSPECT", ["measure"]),
]

# Menu bar, in the ribbon's order (None = separator). File, Edit, View and Help are built in menu_setup.
MENUS: List[Tuple[str, list]] = [
    ("Create", ["create_sketch", "extrude", "hole", "revolve", "sweep", "loft", "emboss", None, "box", "cylinder", "cone",
                "hexagon", "pipe", "thread", "jar",
                None, "pattern_linear", "pattern_circular", "mirror", "pattern_fill", "honeycomb", None,
                "offset_plane", "canvas"]),
    ("Modify", ["fillet", "chamfer", "shell", "offset_face", None, "combine", "split_body", "move", None,
                "parameters", "delete"]),
    ("Inspect", ["measure", "section", "statistics"]),
]


# What the current selection suggests (Ribbon.sync_context): those buttons get an accent border. Nothing moves, so
# the hands keep finding the buttons where they always are; the border just says "this fits what you picked".
CONTEXT: Dict[str, List[str]] = {
    "profile": ["extrude", "revolve", "sweep", "loft", "emboss"],
    "edges": ["fillet", "chamfer"],
    "body": ["move", "shell", "split_body", "offset_face", "hole", "fillet", "chamfer"],
    "bodies": ["combine", "move"],
}


def get(cid: str) -> Command:
    return COMMANDS[cid]


def label(cid: str) -> str:
    return COMMANDS[cid].label


def menu_text(cid: str) -> str:
    """'Name' with the shortcut after a tab (Qt shows it right-aligned in menus)."""
    c = COMMANDS[cid]
    return f"{c.label}\t{c.shortcut}" if c.shortcut else c.label


def tooltip(cid: str) -> str:
    c = COMMANDS[cid]
    return f"{c.tip} ({c.shortcut})" if c.shortcut else c.tip


def button_text(cid: str) -> str:
    """Two short lines for a ribbon button: the name broken in the middle, or the name and its key."""
    c = COMMANDS[cid]
    words = c.label.split()
    if len(words) >= 2:
        half = (len(words) + 1) // 2
        return " ".join(words[:half]) + "\n" + " ".join(words[half:])
    return f"{c.label}\n({c.shortcut})" if c.shortcut else c.label
