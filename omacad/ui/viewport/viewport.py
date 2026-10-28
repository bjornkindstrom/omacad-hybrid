from omacad.ui.viewport.shaders import (
    VERTEX_SHADER_SOLID, FRAGMENT_SHADER_SOLID, VERTEX_SHADER_FLAT,
    FRAGMENT_SHADER_FLAT, VERTEX_SHADER_TEXTURE, FRAGMENT_SHADER_TEXTURE,
    VERTEX_SHADER_THICK, SKETCH_GROUP_ICONS
)
from omacad.ui.viewport.render_mixin import RenderGLMixin
from omacad.ui.viewport.gizmo_mixin import GizmoMixin
from omacad.ui.viewport.picker_mixin import PickerMixin
from omacad.ui.viewport.overlay_mixin import OverlayMixin
from omacad.ui.viewport.text_mixin import TextToolMixin
from omacad.ui.viewport.sketch_rotate_mixin import SketchRotateMixin
from omacad.ui.viewport.sketch_pattern_mixin import SketchPatternMixin
from omacad.ui.viewport.point_pick_mixin import PointPickMixin
from omacad.ui.viewport.events_mixin import ViewportEventsMixin
from omacad.ui.viewport.measure_mixin import MeasureMixin
from omacad.ui.viewport.context_menu_mixin import ContextMenuMixin
from omacad.ui.viewport.sketch_tools_mixin import SketchToolsMixin
from omacad.ui.viewport.pointer_mixin import PointerMixin
from omacad.ui.viewport.profile_mixin import ProfileMixin
from omacad.ui.viewport.sketch_move_mixin import SketchMoveMixin
from omacad.ui.viewport.sketch_dimensions_mixin import SketchDimensionsMixin
from omacad.ui.viewport.sketch_operation_mixin import SketchOperationMixin
from omacad.ui.viewport.dimension_overlay_mixin import DimensionOverlayMixin
"""
Omacad - 3D CAD OpenGL Viewport
Interactive 3D canvas with CAD shading, sharp edge outlines, dynamic ground grid,
interactive ViewCube, sketch overlay, and navigation controls.
"""

import copy
import ctypes
import math
from typing import Optional, List, Tuple, Dict
import numpy as np
from PySide6.QtCore import Qt, QPoint, QRectF, QPointF, Signal, QEvent, QTimer
from PySide6.QtWidgets import (QWidget, QMenu, QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton)
import omacad.ui.viewport as _vp_module
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.model import quality
from omacad.model.hover_info import describe_entity
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QGuiApplication, QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QFontMetrics
from OpenGL import GL
from OpenGL.GL import shaders

from omacad.model.document import Document
from omacad.model.kernel import CadKernel
from omacad.model.timeline import profile_cross_section
from omacad.model.faces import ray_hit_face, tangent_chain
import manifold3d as m3d
from omacad.model.sketch_solver import solve_sketch
from omacad.model.sketch import (
    Sketch, SketchPlane, SketchLine, SketchRect, SketchCircle,
    SketchCenterRect, SketchArc, SketchSlot, SketchText, move_entity, rotate_entity, rotate_point, entity_key_points,
    point_of, arm_vector, arm_angle_deg, nearest_ends_to_vertex, ref_id, ref_segment, EDGE_PTS
)
from omacad.model.sketch_snap import SketchSnapper, SnapResult
from omacad.ui.sketch_tools import SKETCH_TOOLS
from omacad.ui.math3d import REF_FOVY, camera_matrices, ray_from_screen, ray_plane_intersect
from omacad.ui.viewcube import ViewCube
from omacad.ui import dyn_input
from omacad.model import expr as expr_lib
from omacad.ui.dyn_input import DynInput
from omacad.ui import smart_circle
from omacad.ui.smart_circle import SmartCircle
from omacad.ui.sketch_palette import SketchPalette
from omacad.ui.constraint_help import ConstraintHelp
from omacad.ui.constraint_help import GUIDE_STEPS
from omacad.ui import theme
from omacad.ui.theme import qcolor

class Viewport3D(DimensionOverlayMixin, ViewportEventsMixin, MeasureMixin, ContextMenuMixin, SketchToolsMixin, PointerMixin, ProfileMixin, SketchMoveMixin, SketchDimensionsMixin, SketchOperationMixin, QOpenGLWidget, RenderGLMixin, GizmoMixin, PickerMixin, OverlayMixin, TextToolMixin, SketchRotateMixin,
                 PointPickMixin, SketchPatternMixin):
    """Modern OpenGL 3D CAD canvas with Fusion 360 look and feel."""

    selection_changed = Signal()
    hover_info_changed = Signal(object)    # (title, [(label, text)]) of what the mouse rests on, or None
    sketch_finished = Signal()
    finish_sketch_requested = Signal()
    construction_mode_changed = Signal(bool)
    sketch_tool_changed = Signal(str)
    profile_picked = Signal()
    sketch_curve_picked = Signal(str, str)   # (sketch id, entity id) clicked while a path is being picked
    plane_picked = Signal(object)       # SketchPlane chosen for a new sketch
    canvas_face_requested = Signal(object)
    plane_pick_cancelled = Signal()
    section_base_picked = Signal(object)   # plane a section view is cut along
    offset_base_picked = Signal(object)   # plane an offset plane is measured from
    surface_hover = Signal(object)        # same, while the mouse moves (None = no surface)
    surface_picked = Signal(object)       # dict(point, patch) of any body surface (planar or curved)
    target_plane_picked = Signal(object)  # plane chosen as an extrude target (distance to face)
    primitive_face_picked = Signal(object)  # plane chosen as origin/face for box or cylinder
    cylinder_picked = Signal(object)        # dict with cylinder parameters (radius, length, axis, origin, is_internal)
    shell_face_picked = Signal(object)   # plane/face chosen for hollow shell open face
    move_body_picked = Signal(object)    # plane/face chosen for move body selection
    point_picked = Signal(object)        # {"body", "kind", "xyz"}: a point picked on a body (or the origin)
    hole_point_picked = Signal(object)   # world-space point placed on the selected Hole plane
    status_message = Signal(str)
    edit_sketch_requested = Signal(str)     # right-click on a sketch > Edit Sketch
    extrude_sketch_requested = Signal(str)  # right-click on a sketch > Extrude
    edges_selection_changed = Signal()
    extrude_handle_dragged = Signal(float)  # signed distance along the extrude arrow while it is dragged
    extrude_handle_drag_finished = Signal()  # emitted when dragging the handle finishes
    move_gizmo_dragged = Signal(str, float)  # (axis: "X"|"Y"|"Z", delta_mm)
    move_gizmo_finished = Signal()
    move_gizmo_axis_selected = Signal(str)
    body_clicked = Signal(str)  # body_id of clicked 3D body
    move_body_requested = Signal(str)  # right-click on a face moves its owning whole body
    body_color_requested = Signal(str)  # right-click on a face sets its owning whole body color
    plane_clicked = Signal(str)  # an origin plane ("XY") or construction plane id clicked without a tool
    text_place_requested = Signal(object, object)   # Text tool click: (anchor uv or None, path entity id or None)
    text_edit_requested = Signal(str)               # a text element chosen for editing (Text tool click, right-click menu)
    join_bodies_requested = Signal(object)    # right-click with two or more bodies selected > Join
    split_plane_requested = Signal(str)   # right-click on a plane > Split Body with this plane
    face_extrude_requested = Signal(object)  # a flat face to extrude (pull in = cut, out = build up)
    edge_pick_cancelled = Signal()
    offset_face_picked = Signal(object, str)   # (face reference dict, body id) while Offset Face is open
    offset_face_requested = Signal(object)     # a flat face chosen from the right-click menu
    round_requested = Signal(str, object)      # ("fillet" | "chamfer", edges): start the tool with these edges picked
    lay_face_requested = Signal(object, str)   # (face, "ground" | "pick"): turn the body so this face rests on a plane
    lay_target_picked = Signal(object)         # the plane a face is to be laid on
    step_point_clicked = Signal(object)        # a point on a body surface clicked while choosing steps (Pattern/Mirror)
    menu_command = Signal(str)  # right-click menu entries the main window carries out: "undo", "redo", "sketch:XY"...

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.doc.add_change_listener(self.on_document_changed)

        # Camera parameters
        self.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.azimuth: float = 45.0      # Orbit around Z (deg)
        self.elevation: float = 30.0    # Elevation above ground (deg)
        self.distance: float = 140.0    # Distance to target (mm)
        self.fovy: float = REF_FOVY   # zoom calibration only; the drawn field of view is the view_fov setting

        # Navigation state
        self.last_mouse_pos = QPoint()
        self.is_orbiting = False
        self.is_panning = False
        self.nav_mode = "ORBIT"  # "ORBIT", "PAN", "ZOOM"

        # Display flags
        self.show_grid = True
        self.show_edges = True
        self.wireframe_only = False

        # Sketch drawing interaction state
        self.sketch_tool = "NONE"  # "NONE", "LINE", "RECT", "CENTER_RECT", "CIRCLE", "ARC", "SLOT", "DIMENSION"
        self.sketch_start_uv: Optional[Tuple[float, float]] = None
        self.sketch_second_uv: Optional[Tuple[float, float]] = None
        self.sketch_current_uv: Optional[Tuple[float, float]] = None
        self.construction_mode: bool = False
        self.active_snap: Optional[SnapResult] = None
        self.dim_badges: Dict[str, Tuple[QRectF, str, str, float]] = {}
        self.hovered_dim_id: Optional[str] = None

        # Profile picking / extrude preview state
        self.hover_profile: Optional[Tuple[str, int]] = None
        self._press_pos: Optional[QPointF] = None
        self._profile_fill_cache: Dict[tuple, np.ndarray] = {}
        self.preview_mesh = None
        self.preview_op: str = "new_body"

        # The status line, the sketch status and the busy mark are painted into the view (no status bar)
        from omacad.ui.hud_text import HudText
        self.hud_status = HudText(self, logged=True, text="Ready")
        self.hud_sketch = HudText(self)
        self.hud_busy = HudText(self)
        self.hud_busy.setVisible(False)
        self.picked_dim = None                     # (sketch_id, dim_id) picked in the browser: Del deletes it
        self.picked_dim_entities = (None, set())   # (sketch_id, entity ids) of the dimension picked in the browser
        self.flash_sketch_id = None      # a sketch lit up for a moment (hovering its step in the timeline)
        self.text_draft = None           # the SketchText being placed by the Text tool
        self.text_wants_path = False     # ... and it is Text On Path: the click picks a curve
        self.text_wants_box = False      # ... or Text In Box: two clicks draw the box it fills
        self._text_box_start = None      # Text In Box: the first corner, once clicked

        # Sketch element selection (click / Ctrl+click, Delete)
        self.selected_entities: set = set()
        self._constraint_guide = None
        self.hover_entity_id: Optional[str] = None
        self._ref_segments_cache = None  # (sketch_id, segments) of body edges lying in the sketch plane

        # Dimension tool: elements picked so far, and a point-to-point pair waiting for its placement click
        self._dim_pending: list = []
        self._dim_box = None          # floating value box while a point pair waits for its placement click
        self._dim_hover_uv = None
        self._dim_place = None
        self._dim_side = None  # "near"/"far": which circle edge a guided edge-distance measures to

        # Constraint glyphs drawn on the sketch (rect -> constraint id), rebuilt each paint
        self.constraint_badges: List[Tuple[QRectF, str]] = []

        # Moving sketch elements (mouse drag or Move tool)
        self._dim_drag = None   # pressed dimension badge: click = edit value, drag = move the dimension line
        self._spline_drag = None  # dragging a spline point or tangent handle: dict(sketch_id, entity_id, kind, index, before)
        self._endpoint_drag = None  # dragging an unconnected endpoint: dict(sketch_id, entity_id, point_name, before)
        self._drag = None   # pending/active mouse drag: dict(press_uv, press_pos, moved)
        self._move = None   # active move: dict(ids, orig, before, delta)

        # Tab dimension entry while drawing
        self.dyn = DynInput()
        self.smart = SmartCircle()   # the Smart Circle tool: numbers + Enter
        self.dyn_live: Dict[str, float] = {}
        self._raw_mouse_uv: Optional[Tuple[float, float]] = None

        # Extrude arrow (drag to set the distance)
        self.active_tool_title = lambda: None   # set by the main window: title of the open tool panel, if any
        self.pick_step_mode = False   # clicks on a body surface choose the step that made it
        self.extrude_handle = None   # dict(origin, axis, dist)
        self._handle_drag = False
        self._handle_hover = False
        self.move_gizmo = None  # dict(origin, length, active_axis, hover_axis, dragging, start_proj)

        # Edge selection for fillet / chamfer
        self.edge_pick_mode: bool = False
        self.edge_xray: bool = False   # pick edges through the model too (stairs, inside corners)
        self.hover_edge = None            # PlanarEdge under the cursor
        self.hover_face = None            # flat face under the cursor
        self.hover_surface = None         # (body_id, triangles) of a curved surface under the cursor, only lit up
        self.selected_edges: list = []    # PlanarEdge objects chosen so far

        # Right-click menu on a face
        self._rpress: Optional[QPointF] = None
        self.ctx_face = None

        # Sketch plane picking (origin planes + planar body faces)
        self.plane_pick_mode: bool = False
        self.measure = None         # active Measure tool: dict(mode, picks, text, segs)
        self.offset_preview = None  # flat segments of the sketch Offset being set up
        self.section = None         # active section view: dict(origin, normal, offset, flip, meshes, cap)
        self.preview_plane = None   # SketchPlane drawn while an Offset Plane is being set up
        self.plane_pick_purpose: str = "sketch"  # "sketch" or "extrude_target"
        self.shell_target_body_id: str = ""      # body whose faces "shell_face" picking may hit
        self.hover_plane = None  # ("origin", name) or ("face", PlanarFace)
        self.hover_patch = None  # triangle corners (n, 3) of the curved surface under the cursor (Offset Face)
        self._hover_patch_time = 0.0
        self.highlighted_faces: list = []  # list of faces or dicts to highlight (e.g. Shell open faces)
        self.step_edges: list = []         # edges of the Fillet/Chamfer step picked in the timeline or being edited

        self.primitive_handles = None
        from omacad.ui.viewport.rotate_handles import RotateHandles
        self.rotate_handles = RotateHandles(self)   # curved arrows on the selected body that turn it (#107)

        # ViewCube overlay
        self.viewcube = ViewCube(size=110, on_face_clicked=self.set_view,
                                 on_orbit=self._orbit_viewcube)

        # Floating Sketch Palette
        self.sketch_palette = SketchPalette(self)
        self._init_sketch_rotation()
        self._init_tool_panel()
        self._init_sketch_pattern()
        self.sketch_palette.finish_clicked.connect(self.finish_sketch_requested)
        self.sketch_palette.look_at_clicked.connect(self.look_at_active_plane)
        self.sketch_palette.settings_changed.connect(self.update)
        self.sketch_palette.hide()

        # Fillet tool state
        self._mirror_phase = "pick"
        self._move_phase = "pick"
        self.point_pick = False       # picking a point on a body (Move / Rotate), see PointPickMixin
        self.hole_place_mode = False
        self.hole_place_plane = None
        self.hole_place_hover = None
        self.hole_place_points = []
        self.hover_point = None
        self._near_points = []
        self.fillet_first_line = None
        self.fillet_hover_corner = None
        self.fillet_preview = None
        self.fillet_picked = []   # corners picked with Shift: (point, line_a id, line_b id)
        self._rubber = None       # box selection in the sketch: dict(p0, p1, additive)

        from omacad.ui.settings import get_settings
        get_settings().changed.connect(self.update)

        # OpenGL shader handles
        self.prog_solid = None
        self.prog_flat = None
        self.prog_thick = None
        self.prog_tex = None
        self._canvas_textures = {}
        self.vbo_thick = None
        self.vao = None
        self.vbo_pos = None
        self.vbo_norm = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.constraint_help = ConstraintHelp(self)
        self.constraint_help.dismissed.connect(self._constraint_help_dismissed)
        self._place_constraint_help()

    def _constraint_help_dismissed(self):
        self._constraint_guide = None

    def handle_constraint_clicked(self, ctype: str):
        """Start the click-by-click selection guide for a ribbon constraint."""
        sketch = self.doc.active_sketch
        if sketch is None:
            return
        if ctype not in GUIDE_STEPS:
            return
        self._constraint_guide = {"ctype": ctype, "picked": []}
        if self.selected_entities:
            self.selected_entities.clear()
            self.selection_changed.emit()
            self.update()
        self._place_constraint_help()
        self.constraint_help.begin_guide(ctype)

    def _constraint_guide_pick(self, x: float, y: float):
        guide = self._constraint_guide
        sketch = self.doc.active_sketch
        if not guide or sketch is None:
            return
        ent = self._pick_entity(x, y)
        if ent is None:
            self.constraint_help.set_progress(len(guide["picked"]), error="Click on the sketch geometry shown in the step.")
            return

        ctype, picked = guide["ctype"], guide["picked"]
        if ctype == "CENTER":
            group = self._constraint_rectangle_group(sketch, ent)
            if group is None:
                self.constraint_help.set_progress(len(guide.get("groups", [])), error="Click a side of a square-cornered rectangle.")
                return
            groups = guide.setdefault("groups", [])
            if groups and set(groups[0]) & set(group):
                self.constraint_help.set_progress(len(groups), error="Choose a different rectangle for the second step.")
                return
            groups.append(group)
            guide["picked"] = groups[0] + group
            self.selected_entities = set(guide["picked"])
            self.selection_changed.emit()
            self.update()
            if len(groups) < 2:
                self.constraint_help.set_progress(len(groups))
                return
            self._apply_constraint_guide(ctype, guide["picked"])
            return

        chosen = [next((item for item in sketch.entities if item.entity_id == eid), None) for eid in picked]
        chosen = [item for item in chosen if item is not None]
        if ent.entity_id in picked:
            self.constraint_help.set_progress(len(picked), error="That item is already selected. Choose another one.")
            return
        if not self._constraint_guide_accepts(ctype, chosen, ent):
            self.constraint_help.set_progress(len(picked), error=self._constraint_guide_error(ctype))
            return

        picked.append(ent.entity_id)
        self.selected_entities = set(picked)
        self.selection_changed.emit()
        self.update()
        if len(picked) < len(GUIDE_STEPS[ctype]):
            self.constraint_help.set_progress(len(picked))
            return

        self._apply_constraint_guide(ctype, picked)

    def _apply_constraint_guide(self, ctype, picked):
        self.constraint_help.set_progress(len(GUIDE_STEPS[ctype]))
        applied = self.apply_constraint(ctype, selected_order=picked)
        if applied:
            self._constraint_guide = None
            self.constraint_help.set_progress(len(GUIDE_STEPS[ctype]), done=True)
        else:
            self._constraint_guide = None
            self.selected_entities.clear()
            self.selection_changed.emit()
            self.update()
            message = (
                "That line does not mirror the first two. Restart Symmetric and choose the centreline last."
                if ctype == "SYMMETRIC" else
                "These rectangle centres could not be aligned. Check for conflicting constraints and try again."
                if ctype == "CENTER" else
                "It could not be added. Choose another geometry and start again."
            )
            self.constraint_help.set_progress(0, error=message)

    @staticmethod
    def _constraint_rectangle_group(sketch, ent):
        """Find the four connected, square-cornered sketch lines for the rectangle under the click."""
        if not isinstance(ent, SketchLine):
            return None
        ids = sketch.connected_entities(ent.entity_id)
        lines = [item for item in sketch.entities if item.entity_id in ids and isinstance(item, SketchLine)]
        if len(lines) != 4:
            return None
        corners = {}
        for line in lines:
            for point, other in ((line.p1, line.p2), (line.p2, line.p1)):
                key = (round(point[0], 6), round(point[1], 6))
                corners.setdefault(key, []).append((other[0] - point[0], other[1] - point[1]))
        if len(corners) != 4 or any(len(edges) != 2 for edges in corners.values()):
            return None
        for edges in corners.values():
            a, b = edges
            denom = math.hypot(*a) * math.hypot(*b)
            if denom < 1e-9 or abs((a[0] * b[0] + a[1] * b[1]) / denom) > 0.02:
                return None
        return [line.entity_id for line in lines]

    @staticmethod
    def _constraint_guide_accepts(ctype, chosen, ent):
        line, circle = isinstance(ent, SketchLine), isinstance(ent, SketchCircle)
        if ctype in ("HORIZONTAL", "VERTICAL", "PARALLEL", "PERPENDICULAR", "COINCIDENT"):
            return line
        if ctype == "FIX":
            return line or circle
        if ctype == "EQUAL":
            return (line or circle) and (not chosen or isinstance(chosen[0], type(ent)))
        if ctype == "TANGENT":
            if not chosen:
                return line or circle
            first = chosen[0]
            return (isinstance(first, SketchLine) and circle) or (isinstance(first, SketchCircle) and (line or circle))
        if ctype == "CONCENTRIC":
            return circle
        if ctype == "MIDPOINT":
            return (line or circle) if not chosen else line
        if ctype == "SYMMETRIC":
            if len(chosen) < 2:
                return (line or circle) if not chosen else isinstance(chosen[0], type(ent))
            return line
        return False

    @staticmethod
    def _constraint_guide_error(ctype):
        hints = {
            "HORIZONTAL": "Choose a straight line.", "VERTICAL": "Choose a straight line.",
            "PARALLEL": "Choose a straight line.", "PERPENDICULAR": "Choose a straight line.",
            "COINCIDENT": "Choose a straight line.", "FIX": "Choose a line or circle.",
            "EQUAL": "Choose a line or circle matching the first item.",
            "TANGENT": "Choose a line and circle, or two circles.",
            "CONCENTRIC": "Choose a circle.", "MIDPOINT": "Choose a line as the target.",
            "SYMMETRIC": "Choose the same kind of element, then a straight mirror line.",
        }
        return hints.get(ctype, "Choose supported sketch geometry.")

    def _place_constraint_help(self):
        if not hasattr(self, "constraint_help"):
            return
        width = min(360, max(220, self.width() - 24))
        height = 352
        self.constraint_help.setGeometry(
            max(8, self.width() - width - 16),
            max(8, self.height() - height - 16),
            width,
            height,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_constraint_help()
        if hasattr(self, 'sketch_palette'):
            self.sketch_palette.place_default(self.size())
        if hasattr(self, '_on_viewport_resized') and callable(self._on_viewport_resized):
            self._on_viewport_resized(self.size())

    def set_document(self, document: Document) -> None:
        """Switch to another document (File > New/Open) and drop all state tied to the old one."""
        self.constraint_help.dismiss()
        self.doc = document
        self.doc.add_change_listener(self.on_document_changed)
        self.selected_entities = set()
        self.hover_entity_id = None
        self.hover_profile = None
        self.hover_plane = None
        self.plane_pick_mode = False
        self.plane_pick_purpose = "sketch"
        self.sketch_tool = "NONE"
        self.sketch_palette.set_tool("NONE")
        self.rotation_panel.hide()
        self._rotate_drag = None
        self.point_pick = False
        self.hover_point = None
        self._near_points = []
        self.sketch_start_uv = self.sketch_second_uv = self.sketch_current_uv = None
        self.active_snap = None
        self._drag = self._move = self._dim_drag = self._spline_drag = self._endpoint_drag = None
        self._dim_pending, self._dim_place = [], None
        self.picked_dim = None
        self.picked_dim_entities = (None, set())
        self.dyn.reset()
        self.dyn_live = {}
        self.preview_mesh = None
        self.dim_badges.clear()
        self.constraint_badges = []
        self._profile_fill_cache.clear()
        self._ref_segments_cache = None
        self.on_document_changed()

    def on_document_changed(self):
        """Reacts to document updates and shows/hides Sketch Palette."""
        self._profile_fill_cache.clear()
        self._ref_segments_cache = None
        self.sync_section()
        if self.measure is not None and (self.measure["mode"] == "sketch") != bool(self.doc.active_sketch):
            self.measure = None   # sketch mode was entered or left: the picks no longer apply
        sk = self.doc.active_sketch
        if sk is None:
            self.selected_entities.clear()
            self.picked_dim = None
            self.picked_dim_entities = (None, set())
        else:
            alive = {e.entity_id for e in sk.entities}
            self.selected_entities &= alive
            if self.picked_dim_entities[0] and self.picked_dim_entities[0] != sk.sketch_id:
                self.picked_dim = None
                self.picked_dim_entities = (None, set())
        self.hover_entity_id = None
        # a hovered edge or face holds the coordinates of the body it was picked on: after a move or a rebuild it
        # would stay lit where the body used to be (Björn #112); the next mouse move picks it again
        if getattr(self, "hover_edge", None) is not None:
            self.hover_info_changed.emit(None)
        self.hover_edge = self.hover_face = self.hover_surface = None
        sel = self.doc.selected_profile
        if sel and (sel[0] not in self.doc.sketches or sel[1] >= len(self.doc.sketches[sel[0]].profiles)):
            self.doc.selected_profile = None
        self.hover_profile = None
        if self.doc.active_sketch:
            self.sketch_palette.show()
            self.sketch_palette.raise_()
            self.sketch_palette.place_default(self.size())
        else:
            self.sketch_palette.hide()
            self.sketch_palette.set_tool("NONE")
            self.rotation_panel.hide()
            self._rotate_drag = None
            self.active_snap = None
            self.sketch_tool = "NONE"
            self.sketch_start_uv = None
            self.sketch_second_uv = None
            self.sketch_current_uv = None
        self.update()


    # ---- Constraints -----------------------------------------------------------
    CONSTRAINT_GLYPHS = {
        "HORIZONTAL": "H", "VERTICAL": "V", "PARALLEL": "∥", "PERPENDICULAR": "⟂",
        "EQUAL": "=", "TANGENT": "T", "CONCENTRIC": "◎", "COINCIDENT": "•", "FIX": "F", "POINT_ON_CIRCLE": "○",
        "MIDPOINT": "M", "SYMMETRIC": "S", "CENTER": "⊙",
    }
    CONSTRAINT_HINTS = {
        "HORIZONTAL": "Horizontal: select one or more lines.",
        "VERTICAL": "Vertical: select one or more lines.",
        "PARALLEL": "Parallel: select two or more lines.",
        "PERPENDICULAR": "Perpendicular: select two or more lines.",
        "EQUAL": "Equal: select two or more lines, or two or more circles.",
        "TANGENT": "Tangent: select a line and a circle, or two circles.",
        "CONCENTRIC": "Concentric: select two circles.",
        "COINCIDENT": "Coincident: select two lines (their nearest end points are joined).",
        "MIDPOINT": "Midpoint: select a circle or line (its nearest end point) and the line whose middle it goes to.",
        "SYMMETRIC": "Symmetric: select two lines (or two circles) and the line they mirror across.",
        "CENTER": "Center: select two square-cornered rectangles to align their horizontal centres; use an edge distance for vertical offset.",
        "FIX": "Fix: select lines or circles to lock in place.",
    }




    # ---- Moving and Rotating sketch elements ---------------------------------

    # ---- Measure ----------------------------------------------------------------------------

    # ---- Sketch commit & Tab dimension entry ---------------------------------

    # ---- Smart Circle ------------------------------------------------------------

    # ---- Profile picking & feature preview ------------------------------

    def initializeGL(self):
        GL.glClearColor(*theme.palette().canvas_rgb01(), 1.0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glEnable(GL.GL_BLEND)
        # Blend colour only; keep destination alpha at 1 so the compositor never shows the desktop through
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ZERO, GL.GL_ONE)
        GL.glEnable(GL.GL_LINE_SMOOTH)

        # Create VAO and VBOs for modern OpenGL
        self.vao = GL.glGenVertexArrays(1)
        self.vbo_pos = GL.glGenBuffers(1)
        self.vbo_norm = GL.glGenBuffers(1)
        self._body_gpu_cache = {}  # (body_id, mesh_id) -> {"vao_solid", "vbo_pos", "vbo_norm", "vert_count", "vao_lines", "vbo_lines", "line_count"}

        # Compile solid shader
        try:
            vs_solid = shaders.compileShader(VERTEX_SHADER_SOLID, GL.GL_VERTEX_SHADER)
            fs_solid = shaders.compileShader(FRAGMENT_SHADER_SOLID, GL.GL_FRAGMENT_SHADER)
            self.prog_solid = shaders.compileProgram(vs_solid, fs_solid)

            vs_flat = shaders.compileShader(VERTEX_SHADER_FLAT, GL.GL_VERTEX_SHADER)
            fs_flat = shaders.compileShader(FRAGMENT_SHADER_FLAT, GL.GL_FRAGMENT_SHADER)
            self.prog_flat = shaders.compileProgram(vs_flat, fs_flat)

            vs_thick = shaders.compileShader(VERTEX_SHADER_THICK, GL.GL_VERTEX_SHADER)
            self.prog_thick = shaders.compileProgram(vs_thick, fs_flat)
            self.vbo_thick = GL.glGenBuffers(1)

            vs_tex = shaders.compileShader(VERTEX_SHADER_TEXTURE, GL.GL_VERTEX_SHADER)
            fs_tex = shaders.compileShader(FRAGMENT_SHADER_TEXTURE, GL.GL_FRAGMENT_SHADER)
            self.prog_tex = shaders.compileProgram(vs_tex, fs_tex)
        except Exception as e:
            print(f"Error compiling CAD shaders: {e}")

    def draw_buffer_arrays(self, mode, pos_loc, pos_data: np.ndarray, norm_loc=None, norm_data=None):
        """Safely draws arrays using bound VAO and VBO buffers for modern OpenGL."""
        if len(pos_data) == 0 or pos_loc < 0:
            return
        GL.glBindVertexArray(self.vao)

        pos_float = np.ascontiguousarray(pos_data, dtype=np.float32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_pos)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, pos_float.nbytes, pos_float, GL.GL_DYNAMIC_DRAW)
        GL.glEnableVertexAttribArray(pos_loc)
        GL.glVertexAttribPointer(pos_loc, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        if norm_loc is not None and norm_loc >= 0 and norm_data is not None and len(norm_data) > 0:
            norm_float = np.ascontiguousarray(norm_data, dtype=np.float32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_norm)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, norm_float.nbytes, norm_float, GL.GL_DYNAMIC_DRAW)
            GL.glEnableVertexAttribArray(norm_loc)
            GL.glVertexAttribPointer(norm_loc, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        count = pos_float.size // 3
        GL.glDrawArrays(mode, 0, count)

        GL.glDisableVertexAttribArray(pos_loc)
        if norm_loc is not None and norm_loc >= 0:
            GL.glDisableVertexAttribArray(norm_loc)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)

    def set_line_width(self, width: float):
        """Safely sets line width avoiding GL_INVALID_VALUE in OpenGL Core Profile."""
        try:
            GL.glLineWidth(min(1.0, float(width)))
        except Exception:
            pass

    def resizeGL(self, w: int, h: int):
        GL.glViewport(0, 0, w, h)

    def get_matrices(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculates Model, View, and Projection matrices (cached until the camera, size or view settings change:
        picking projects hundreds of points per mouse move)."""
        w = max(1, self.width())
        h = max(1, self.height())
        from omacad.ui.settings import get_settings
        settings = get_settings()
        fov = float(settings.get("view_fov", 30.0))
        ortho = settings.get("view_projection", "perspective") == "orthographic"
        key = (tuple(float(c) for c in self.target), float(self.distance), float(self.azimuth), float(self.elevation), w, h, fov, ortho)
        if key != getattr(self, "_matrices_key", None):
            proj, view = camera_matrices(self.target, self.distance, self.azimuth, self.elevation, float(w) / float(h), fov, ortho)
            self._matrices = (proj, view, proj @ view)
            self._matrices_key = key
        return self._matrices

    def paintGL(self):
        # QPainter (used for the overlay) resets GL state at the end of every frame,
        # so depth testing/blending must be re-enabled before each render.
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glEnable(GL.GL_BLEND)
        # Blend colour only; keep destination alpha at 1 so the compositor never shows the desktop through
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ZERO, GL.GL_ONE)
        GL.glEnable(GL.GL_LINE_SMOOTH)
        GL.glClearColor(*theme.palette().canvas_rgb01(), 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        proj, view, mvp = self.get_matrices()

        # 1. Draw 3D Ground Grid
        if self.show_grid:
            self.render_ground_grid(mvp)
            sk = self.doc.active_sketch
            if sk is not None and sk.plane.name == "FACE":
                self.render_plane_grid(mvp, sk.plane)

        self.render_origin_axes(mvp)

        # 3. Draw 3D Solid Bodies
        self.render_bodies(mvp)
        # Transparent references blend over face shading, with depth testing against bodies.
        self.render_canvases(mvp)

        # 3. Draw Active or Visible Sketches
        self.render_sketches(mvp)
        self.render_text_preview(mvp)
        self.render_profile_fills(mvp)
        if self.section is None:
            self.render_preview(mvp)
        self.render_plane_pick(mvp)
        self.render_edge_pick(mvp)
        self.render_section_cap(mvp)
        if self.section is not None:
            self.render_preview(mvp)      # after the opaque cut face, so a cut preview shows through it
        self.render_step_edges(mvp)       # on top of the preview: which edges the step being edited rounds
        self.render_extrude_handle(mvp)
        self.render_move_gizmo(mvp)
        if (self.offset_preview is not None or self.fillet_preview is not None) and self.prog_thick is not None:
            prev_lines = self.fillet_preview if self.fillet_preview is not None else self.offset_preview
            GL.glDisable(GL.GL_DEPTH_TEST)
            self.draw_thick_lines(mvp, prev_lines, (1.0, 0.65, 0.2, 1.0), 3.0, halo=True)
            GL.glEnable(GL.GL_DEPTH_TEST)

        # 4. Draw QPainter Overlay (ViewCube, HUD, sketch measurements)
        painter = QPainter(self)
        try:
            self.draw_painter_overlays(painter)
        finally:
            painter.end()

    def _get_canvas_texture(self, cid: str, b64_data: str) -> Optional[int]:
        key = hash(b64_data)
        cached = self._canvas_textures.get(cid)
        if cached is not None:
            if cached[0] == key:
                return cached[1]
            GL.glDeleteTextures([cached[1]])  # same id, new image (deleted + re-added, or other document)
            del self._canvas_textures[cid]
        try:
            import base64
            from PySide6.QtGui import QImage
            raw = base64.b64decode(b64_data)
            img = QImage()
            img.loadFromData(raw)
            if img.isNull():
                return None
            img = img.convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = img.width(), img.height()
            tex_id = int(GL.glGenTextures(1))
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            bits = img.constBits()
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, w, h, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, bytes(bits))
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            self._canvas_textures[cid] = (key, tex_id)
            return tex_id
        except Exception as e:
            print(f"Error creating canvas texture for {cid}: {e}")
            return None






    # ---- Right-click menu on a sketch element ---------------------------------------


    def get_sketch_plane_uv(self, screen_x: float, screen_y: float) -> Optional[Tuple[float, float]]:
        """Projects screen coordinate to 2D local (u, v) on the active sketch plane."""
        if not self.doc.active_sketch:
            return None

        plane = self.doc.active_sketch.plane
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(screen_x, screen_y, self.width(), self.height(), view, proj)

        pt_world = ray_plane_intersect(origin, ray_dir, plane.origin, plane.normal)
        if pt_world is None:
            return None

        return plane.world_to_uv(pt_world)

    def model_screen_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """Returns (min_x, min_y, max_x, max_y) in screen pixels of visible bodies, or None."""
        corners = []
        for b in self.doc.bodies.values():
            if b.visible and b.render_mesh and len(b.render_mesh.vertices) > 0:
                bmin = b.render_mesh.bounds_min
                bmax = b.render_mesh.bounds_max
                # 8 corners of the 3D bounding box
                for x in (bmin[0], bmax[0]):
                    for y in (bmin[1], bmax[1]):
                        for z in (bmin[2], bmax[2]):
                            corners.append(np.array([x, y, z], dtype=np.float32))

        # Also include preview_mesh if present
        if hasattr(self, "preview_mesh") and self.preview_mesh is not None and len(self.preview_mesh.vertices) > 0:
            bmin = self.preview_mesh.bounds_min
            bmax = self.preview_mesh.bounds_max
            for x in (bmin[0], bmax[0]):
                for y in (bmin[1], bmax[1]):
                    for z in (bmin[2], bmax[2]):
                        corners.append(np.array([x, y, z], dtype=np.float32))

        if not corners:
            return None

        screen_pts = []
        for c in corners:
            s = self.world_to_screen(c)
            if s is not None:
                screen_pts.append(s)

        if not screen_pts:
            return None

        xs = [p[0] for p in screen_pts]
        ys = [p[1] for p in screen_pts]
        return (min(xs), min(ys), max(xs), max(ys))
