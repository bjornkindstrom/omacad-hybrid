"""Help & Commands: every function of the app, grouped as in the ribbon, with help text and search words.

The commands come from omacad.ui.commands (so a new command is in the help as soon as it is in the ribbon); MORE adds
a longer text where the tooltip is not enough, and EXTRA lists what is not a ribbon command (files, view, timeline,
constraints, ways of working). Text is English, like the rest of the app.
"""
from dataclasses import dataclass
from typing import List, Optional

from omacad.ui import commands


@dataclass
class Topic:
    title: str
    group: str
    text: str
    shortcut: str = ""
    where: str = ""
    keywords: str = ""
    cid: Optional[str] = None           # a command the help window can run

    def words(self) -> List[str]:
        import re
        return re.findall(r"[\w+]+", " ".join((self.title, self.group, self.text, self.shortcut, self.where,
                                               self.keywords)).lower())


# Longer help where the ribbon tooltip is short. Keywords help the search find a command by other names.
MORE = {
    "create_sketch": ("Click a plane (XY, XZ, YZ, a construction plane) or a flat face of a body, then draw. Finish "
                      "Sketch returns to 3D.", "draw 2d plane face start"),
    "extrude": ("Pick closed profiles in the view (Shift+click adds more), type the distance or drag the arrow. "
                "Auto joins, cuts or makes a new body depending on where it starts. Two sides, symmetric and a start "
                "offset are in the panel. Twist turns the profile about its centre on the way (a twisted vase). Also: right-click "
                "a face > Extrude this Face.", "pull push pad pocket cut boss twist spiral"),
    "revolve": ("Pick a profile and an axis (a construction line in the sketch, or the sketch's X/Y axis), set the "
                "angle.", "lathe turn rotate around axis"),
    "sweep": ("Click the profile in the view, then the path: body edges as in Fillet, or a sketch's line, arc or circle "
              "(everything joined to it comes along). The profile may sit anywhere on the path and must cross it; Twist turns it over the length.",
              "path rail follow spring"),
    "loft": ("Click profiles in order (each on its own plane), or add them from the profile list. The skin "
             "passes through them and preserves holes (all profiles need the same number). Use Edit on the Loft step to add, remove or reorder profiles.", "blend transition skin"),
    "pipe": ("Click the path in the view - body edges as in Fillet, or a sketch's line, arc or circle - and set the "
             "diameter; a wall thickness makes it a tube. Bends and corners follow the path.", "tube hose wire rod path edge"),
    "cone": ("Bottom radius, top radius (0 = a point) and height, placed like a cylinder; Shell Wall hollows it.",
             "frustum taper point funnel"),
    "emboss": ("Text or any profile in a sketch on a face: positive depth raises it, negative presses it in. Wraps "
               "round cylinders.", "deboss engrave text letters"),
    "pattern": ("Pick the steps to copy in the timeline or the list (a rib and its fillets together), then the kind: "
                "linear, circular round an axis, mirror across a plane, or filling a face.", "array copy repeat"),
    "honeycomb": ("Pick flat or round faces; set cell shape, size, wall, margin and depth or Through.", "hexagon cells lattice vent"),
    "offset_plane": ("Click a plane or flat face and type the distance, or touch any surface (a cylinder's side). "
                     "Angle turns the plane about its X or Y direction or about an edge you click (Plane at Angle).",
                     "construction plane workplane angle rotate tilt"),
    "fillet": ("Pick edges (X or Alt picks hidden ones through the model), type the radius. A whole tangent chain "
               "is picked with one click (untick Tangent chain for single edges), a face picks all its edges. The view shows the "
               "finished body; box corners where three fillets meet become a rolling ball.", "round radius edge"),
    "chamfer": ("Pick edges, type the size. Chamfer type: Equal distance, Two distances or Distance and angle "
                "(Flip swaps the faces). Inside corners get material added.", "bevel edge two distances angle"),
    "shell": ("Pick the body, the wall thickness, and click faces to leave them open.", "hollow wall thickness"),
    "offset_face": ("Click flat faces, holes or pins and type how far they move: + adds material, − removes it. On a "
                    "thread it changes only the thread, for a looser or tighter fit.", "tolerance fit clearance hole pin"),
    "combine": ("Join, cut or intersect a target body with a tool body; keep the tool if you want it again.",
                "boolean union subtract intersect join cut merge"),
    "split_body": ("Cut a body in two with a plane.", "cut divide plane"),
    "move": ("Drag the arrows or rings, type numbers, or use Point to point, Face to face or Lay face flat. Each "
             "drag is applied at once, so you can move in several goes; OK closes. Activate copy keeps the original. "
             "Circles give five points (centre and four quarter points) for point to point.",
             "translate rotate position align point face copy"),
    "parameters": ("Name values (width = 40) and use them in every number field, also in formulas: width/2, "
                   "radius+2, test1+5*test3. Change a value and every step follows.", "variables formula expression fx"),
    "delete": ("Deletes the selected bodies (as a timeline step, so undo brings them back).", "remove"),
    "measure": ("Click edges, lines, circles or faces: size, distance and angle. In 3D, D after two bodies sets the "
                "distance between them.", "distance angle size inspect"),
    "section": ("Cut through the model at a plane or face and slide the cut; it stays in the browser as a Section View "
                "you can switch on and off.", "cross section cut view"),
    "line": ("Click points; the line continues from the last point. Tab types length and angle (also parameter "
             "names). Esc ends the chain.", "polyline draw"),
    "circle": ("Click the centre, then the size (Tab types the diameter). The arrow on the button: Smart Circle.",
               "round hole"),
    "text": ("Type the text, pick font and height, click where it goes, or on a circle, arc or line for Text On "
             "Path. The letters are profiles: extrude or emboss them.", "letters font engrave label"),
    "offset_sketch": ("Click curves, including splines (Shift/Ctrl+click toggles one), then type the distance. "
                      "Closed shapes: + outward, − inward. Open curves: + left of the drawing direction, − right. "
                      "Spline offsets are independent sampled splines; tight curves may split or disappear.",
                      "parallel copy inset outset spline"),
    "dimension": ("Click a line, circle, two lines or two points and type the value; a parameter name or formula "
                  "makes it follow the parameters (shown as ƒx).", "size constraint driving"),
    "fix_sketch": ("When what you drew does not make a face: removes doubled lines, joins ends that nearly meet, "
                   "extends lines that stop short, and closes an open outline with one line. One undo step.",
                   "repair close gap open profile face"),
    "construction": ("Toggle drawing helper lines, or turn the selected curves into construction lines.",
                     "guide helper axis dashed reference"),
}

EXTRA = [
    # files
    Topic("New, Open, Save", "FILE", "Projects are .omacad files with the full history. Open Recent lists the last ones.",
          "Ctrl+N / Ctrl+O / Ctrl+S", "File menu", "project document"),
    Topic("Export STL / STEP", "FILE", "All bodies (File menu) or one body (right-click it in the browser).",
          "", "File menu, browser", "print 3d printer slicer bambu cad exchange"),
    Topic("Import 3MF", "FILE", "Brings the bodies of a 3MF file in as steps.", "", "File menu, SOLID › CREATE › Insert",
          "mesh import"),
    # edit and view
    Topic("Undo / Redo", "EDIT & VIEW", "Every change is one step; nothing is lost. Finish or cancel the open tool "
          "first.", "Ctrl+Z / Ctrl+Shift+Z", "Edit menu, right-click", "back revert history"),
    Topic("Fit view, grid, edges, origin", "EDIT & VIEW", "Fit puts the whole model in view. The View menu turns the "
          "grid, feature edges and origin planes and axes on and off.", "F / Home", "View menu", "zoom camera"),
    Topic("Settings", "EDIT & VIEW", "Colours, ribbon layout (labels, grouped dropdowns, button size), curve "
          "smoothness, zoom direction and the AI agent for problem reports.", "Ctrl+,", "Edit menu, ribbon",
          "preferences theme"),
    Topic("Report problem", "HELP", "Describe what is wrong: a screenshot, the model and the log go to the AI agent, "
          "which fixes it.", "F10", "Help menu", "bug feedback error"),
    Topic("Request a change", "HELP", "Ask for a new feature or a change; it is sent to the owner.", "F8", "Help menu",
          "feature wish rfc"),
    # timeline and browser
    Topic("Timeline", "TIMELINE & BROWSER", "Every step in order. Double-click a step to edit it (the model rolls back "
          "to it while you edit). Right-click: rename, suppress, roll back to here, delete. A red step failed: its "
          "tooltip says why. ƒx marks steps driven by parameters.", "", "bottom of the window",
          "history steps edit rollback suppress"),
    Topic("Browser", "TIMELINE & BROWSER", "Bodies, sketches, planes, sections and canvases. The eye or V shows/hides, "
          "F2 renames, right-click for more (export one body, find in timeline ...).", "V / F2", "left side",
          "tree hide show rename"),
    # sketch
    Topic("Constraints", "SKETCH · CONSTRAINTS", "Select elements, then Horizontal, Vertical, Coincident, Parallel, "
          "Perpendicular, Equal, Tangent, Concentric, Midpoint, Symmetric, Center or Fix. Center: choose two "
          "square-cornered rectangles to align their horizontal centres; dimension an edge gap for vertical offset. "
          "Symmetric: two lines or circles mirrored across a "
          "third selected line. Also in an element's right-click menu.", "",
          "SKETCH › CONSTRAINTS", "horizontal vertical parallel perpendicular equal tangent concentric midpoint symmetric center fix lock"),
    Topic("Rectangle", "SKETCH · CREATE", "2-point, centre, rounded and centre-rounded: the arrow on the button picks "
          "the kind and which one the button draws.", "R", "SKETCH › CREATE", "box square rounded"),
    Topic("Typing values while drawing", "SKETCH · CREATE", "While drawing, Tab opens the size fields; type numbers, "
          "parameter names or formulas. Typing a letter lists the parameters starting with it: Up/Down, Enter.",
          "Tab", "while drawing", "dimension input parameter formula"),
    # ways of working
    Topic("Type in the 3D view", "WORKING TIPS", "With a tool open, type a number or a parameter name anywhere over "
          "the model: it goes into the tool's main field. Enter is OK, Esc cancels.", "", "",
          "keyboard value field enter"),
    Topic("Hidden edges", "WORKING TIPS", "While picking edges, X (or holding Alt) picks through the model, for edges "
          "inside a jar or under a shoulder.", "X / Alt", "Fillet, Chamfer", "xray see through inside"),
    Topic("Highlighted buttons", "WORKING TIPS", "Buttons that fit what you selected get an orange border (a profile: "
          "Extrude; a body: Move, Shell; two bodies: Combine).", "", "ribbon", "context suggestion"),
]

_GROUP_ORDER = ["SOLID · CREATE", "SOLID · MODIFY", "SOLID · INSPECT", "SKETCH · CREATE", "SKETCH · MODIFY",
                "SKETCH · CONSTRAINTS", "SKETCH · INSPECT", "FILE", "EDIT & VIEW", "TIMELINE & BROWSER", "HELP",
                "WORKING TIPS"]


def _where(cid: str, tab: str, group: str, dropdown: str = "") -> str:
    parts = [f"{tab} › {group}" + (f" › {dropdown}" if dropdown else "")]
    menu = next((title for title, cids in commands.MENUS if cid in cids), None)
    if menu:
        parts.append(f"{menu} menu")
    return ", ".join(parts)


def topics() -> List[Topic]:
    out: List[Topic] = []
    seen = set()
    for tab, groups in (("SOLID", commands.SOLID_GROUPS), ("SKETCH", commands.SKETCH_GROUPS)):
        for group, items in groups:
            for item in items:
                members = [(c, item[1]) for c in item[4]] if isinstance(item, tuple) else [(item, "")]
                if item == "pattern":
                    members += [(c, "Pattern") for c in commands.PATTERNS]
                for cid, dropdown in members:
                    if cid not in commands.COMMANDS or cid in seen:
                        continue
                    seen.add(cid)
                    c = commands.get(cid)
                    more, words = MORE.get(cid, ("", ""))
                    text = c.tip + (". " + more if more else "")
                    out.append(Topic(c.label, f"{tab} · {group}", text, c.shortcut, _where(cid, tab, group, dropdown),
                                     words, cid))
    extra_cids = {"settings"}
    out = [t for t in out if t.cid not in extra_cids] + EXTRA
    return sorted(out, key=lambda t: _GROUP_ORDER.index(t.group) if t.group in _GROUP_ORDER else len(_GROUP_ORDER))


def search(query: str, items: Optional[List[Topic]] = None) -> List[Topic]:
    """Topics where every word of `query` starts a word of the topic ("hole" finds holes, not "whole"); case does not
    matter, and topics whose name matches come first."""
    items = topics() if items is None else items
    query_words = query.lower().split()
    if not query_words:
        return items
    def found_in(text):
        return all(any(w.startswith(q) for w in text.lower().split()) for q in query_words)

    hits = [t for t in items if all(any(w.startswith(q) for w in t.words()) for q in query_words)]
    # best first: the name matches, then the search words (other names for it), then only the text
    return sorted(hits, key=lambda t: 0 if found_in(t.title) else (1 if found_in(t.keywords) else 2))
