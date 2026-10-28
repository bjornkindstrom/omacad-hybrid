from omacad.ui.controllers.tool_prompts import ToolPromptsMixin
from omacad.ui.controllers.text_prompts import EmbossPromptMixin, TextPromptsMixin
from omacad.ui.controllers.file_session import FileSessionMixin
from omacad.ui.controllers.menu_setup import MenuSetupMixin
"""
Omacad - Main CAD Application Window
Connects Ribbon, Viewport, Browser, Timeline, and Menu Bar.
"""

from pathlib import Path
from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, QSize, QTimer, QThreadPool, QRunnable, Signal, QObject
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QDockWidget,
    QFileDialog, QMessageBox, QLabel, QMenu, QPushButton, QProgressBar
)
from PySide6.QtGui import QAction, QKeySequence, QIcon, QShortcut


class _WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class _BackgroundWorker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _WorkerSignals()

    def run(self):
        try:
            res = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(res)
        except Exception as e:
            self.signals.error.emit(str(e))

from omacad.model.document import Document, ORIGIN_GROUPS
from omacad.model.timeline import ExtrudeFeature, CombineFeature, SplitBodyFeature, ShellFeature, MoveFeature
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.ui.ribbon import Ribbon, RECT_TOOLS
from omacad.ui.viewport import Viewport3D
from omacad.ui.browser import BrowserTree
from omacad.ui.timeline_bar import STEP_CHANGE_MIN_THICKNESS, TimelineBar
from omacad.ui.side_panel import InspectorPanel
from omacad.ui.canvas_dialog import CanvasEditorDialog
from omacad.ui.dialogs import (
    RoundEdgesDialog, PatternDialog, OffsetPlaneDialog,
    SketchPlaneDialog, ExtrudeDialog, BoxDialog, CylinderDialog,
    SphereDialog, CombineDialog, SplitBodyDialog, ShellDialog, MoveBodyDialog
)
from omacad.io.exporter import Exporter


class MainWindow(QMainWindow, ToolPromptsMixin, TextPromptsMixin, EmbossPromptMixin, FileSessionMixin, MenuSetupMixin):
    """Main Fusion 360 style window for Omacad."""

    # QMainWindow comes first in the bases, so Qt's own closeEvent would hide the mixin's (no "save changes?" on close)
    closeEvent = FileSessionMixin.closeEvent

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Omacad {__import__('omacad').__version__} - Native CAD for Omarchy")
        self.resize(1340, 860)

        import os
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Apply Fusion 360 Dark Theme
        style(self, theme._BASE_CSS, theme._STUDIO_CSS)
        self.apply_theme_font()
        self.theme_watcher = theme.ThemeWatcher(self)
        self.theme_watcher.changed.connect(self.on_theme_changed)

        # Active Document
        self.doc = Document("Omacad - Untitled")
        self.current_path: Optional[str] = None

        # Central Layout Container
        central_container = QWidget()
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 1. Top Ribbon
        self.ribbon = Ribbon(self.doc, self)
        central_layout.addWidget(self.ribbon)

        # 2. 3D Viewport (spans full central width, overlays float on top like Fusion 360)
        self.viewport = Viewport3D(self.doc, self)
        central_layout.addWidget(self.viewport, stretch=1)

        from omacad.ui import dialogs as _dialogs
        # Left Browser overlay floating on viewport
        self.browser = BrowserTree(self.doc, self.viewport)
        self.browser.setMinimumWidth(160)

        # Right Inspector overlay floating on viewport
        self.inspector = InspectorPanel(self.doc, self.viewport)
        self.inspector.width_fitted.connect(self._keep_viewcube_clear)
        self.inspector.set_palette(self.viewport.sketch_palette)
        _dialogs.SIDE_HOST = self
        self.doc.add_change_listener(self.inspector.refresh_info)
        self.viewport.hover_info_changed.connect(self.inspector.show_hover)
        self._init_undo_listener = True   # registered once the Edit menu exists (see _build_menus)

        # SOLID / SKETCH: a small bar in the view, directly above the Browser (it belongs to the big box, not the ribbon)
        self.workspace_bar = self.ribbon.workspace_bar
        self.workspace_bar.setParent(self.viewport)
        self.workspace_bar.show()

        def _update_overlays(size=None):
            if size is None:
                size = self.viewport.size()
            top_pad = 10
            bottom_pad = 10
            self.workspace_bar.adjustSize()
            self.workspace_bar.move(10, 4)
            browser_top = max(top_pad, 4 + self.workspace_bar.sizeHint().height() + 2)
            h = max(100, size.height() - browser_top - bottom_pad)
            self.browser.setGeometry(10, browser_top, self.browser.preferred_width(size.width()),
                                     self.browser.preferred_height(h))      # only as tall as its rows: more drawing area
            self.inspector.move(self.inspector.x(), top_pad)
            self.inspector.set_max_height(h)          # the panel fits its content and anchors to the right edge

        self.browser.content_width_changed.connect(_update_overlays)
        self.viewport._on_viewport_resized = _update_overlays
        _update_overlays()

        # 3. Bottom Timeline
        self.timeline_bar = TimelineBar(self.doc, self)
        self.timeline_bar.hide()  # Browser owns object history navigation; retain the shared editing/highlight controller.

        self.setCentralWidget(central_container)

        # 4. Status line: no status bar; the message, the sketch status and "busy" are painted into the 3D view
        self.status_label = self.viewport.hud_status
        self.lbl_sketch_status = self.viewport.hud_sketch
        self.progress_bar = self.viewport.hud_busy
        self.doc.add_change_listener(self.sync_sketch_status)
        self.thread_pool = QThreadPool.globalInstance()

        # Setup Menus & Actions
        self.setup_menu_bar()

        # Connect Ribbon Signals
        self.ribbon.create_sketch_clicked.connect(self.prompt_create_sketch)
        self.viewport.plane_picked.connect(self.on_plane_picked)
        self.viewport.face_extrude_requested.connect(self.on_extrude_face)
        self.viewport.canvas_face_requested.connect(self.prompt_canvas_on_face)
        self.viewport.move_body_requested.connect(self.prompt_move_body)
        self.viewport.body_color_requested.connect(self.prompt_body_color)
        self.ribbon.constraint_clicked.connect(self.viewport.handle_constraint_clicked)
        self.viewport.status_message.connect(self.status_label.setText)
        self.viewport.plane_pick_cancelled.connect(self.on_plane_pick_cancelled)
        self.ribbon.extrude_clicked.connect(self.prompt_extrude)
        self.ribbon.hole_clicked.connect(self.prompt_hole)
        self.ribbon.pattern_clicked.connect(self.prompt_pattern)
        self.ribbon.pattern_kind_clicked.connect(self.prompt_pattern)
        self.ribbon.offset_plane_clicked.connect(self.prompt_offset_plane)
        self.ribbon.section_clicked.connect(self.prompt_section)
        self.ribbon.measure_clicked.connect(self.viewport.begin_measure)
        self.ribbon.fillet_clicked.connect(lambda: self.prompt_round_edges("fillet"))
        self.ribbon.chamfer_clicked.connect(lambda: self.prompt_round_edges("chamfer"))
        self.ribbon.parameters_clicked.connect(self.on_change_parameters)
        self.ribbon.revolve_clicked.connect(self.prompt_revolve)
        self.ribbon.emboss_clicked.connect(self.prompt_emboss)
        self.ribbon.box_clicked.connect(self.prompt_box)
        self.ribbon.cylinder_clicked.connect(self.prompt_cylinder)
        self.ribbon.hexagon_clicked.connect(self.prompt_prism)
        self.ribbon.cone_clicked.connect(self.prompt_cone)
        self.ribbon.sweep_clicked.connect(lambda: self.prompt_sweep_tool("sweep"))
        self.ribbon.loft_clicked.connect(lambda: self.prompt_sweep_tool("loft"))
        self.ribbon.pipe_clicked.connect(lambda: self.prompt_sweep_tool("pipe"))
        self.ribbon.jar_clicked.connect(self.prompt_jar)
        self.ribbon.thread_clicked.connect(self.prompt_thread)
        self.ribbon.combine_clicked.connect(self.prompt_combine)
        self.ribbon.split_body_clicked.connect(self.prompt_split_body)
        self.viewport.join_bodies_requested.connect(self.on_join_bodies)
        self.viewport.text_place_requested.connect(self.on_text_place)
        self.viewport.text_edit_requested.connect(self.prompt_text_edit)
        self.viewport.split_plane_requested.connect(lambda pid: self.prompt_split_body(plane_id=pid))
        self.ribbon.shell_clicked.connect(self.prompt_shell)
        self.ribbon.offset_face_clicked.connect(lambda: self.prompt_offset_face())
        self.ribbon.honeycomb_clicked.connect(self.prompt_honeycomb)
        self.ribbon.project_clicked.connect(lambda: self.viewport.project_edges())
        self.ribbon.move_clicked.connect(self.prompt_move_body)
        self.ribbon.canvas_clicked.connect(self.prompt_insert_canvas)
        self.ribbon.import_3mf_clicked.connect(self.on_import_3mf)
        self.ribbon.selected_edge_count = lambda: len(self.viewport.selected_edges) if self.viewport.edge_pick_mode else 0
        self.viewport.edges_selection_changed.connect(self.ribbon.sync_context)
        self.viewport.profile_picked.connect(self.ribbon.sync_context)
        self.ribbon.delete_clicked.connect(self.on_delete_selected)
        self.ribbon.inspect_clicked.connect(self.on_inspect)
        self.ribbon.settings_clicked.connect(self.on_open_settings)
        self.ribbon.sketch_tool_selected.connect(self.on_sketch_tool_selected)
        self.viewport.sketch_tool_changed.connect(self.sync_sketch_tool_from_viewport)
        self.ribbon.toggle_construction_clicked.connect(self.viewport.toggle_construction_mode)
        self.ribbon.construction_tool_requested.connect(self.start_construction_tool)
        self.viewport.construction_mode_changed.connect(self._sync_construction_button)
        self.doc.add_change_listener(self._reset_construction_outside_sketch)
        self.ribbon.finish_sketch_clicked.connect(self.on_finish_sketch)
        self.ribbon.fix_sketch_clicked.connect(self.on_fix_sketch)
        self.viewport.finish_sketch_requested.connect(self.on_finish_sketch)
        self.viewport.menu_command.connect(self.on_menu_command)
        self.viewport.active_tool_title = self._active_tool_title
        self.viewport.offset_face_requested.connect(lambda face: self.prompt_offset_face(face))
        self.viewport.round_requested.connect(lambda kind, edges: self.prompt_round_edges(kind, edges))
        self.viewport.lay_face_requested.connect(self.on_lay_face_requested)
        self.viewport.lay_target_picked.connect(self.on_lay_target_picked)
        self._lay_face = None
        # Esc leaves the current function wherever the keyboard focus is (a tool panel field, the tree ...);
        # the viewport decides what that means, in the same order as when it has the focus itself
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._escape_pressed)

        # Connect Browser Signals
        self.browser.start_sketch_on_plane.connect(self.start_sketch_on_plane)
        self.browser.edit_sketch_requested.connect(self.on_edit_sketch)
        self.browser.edit_sketch_text_requested.connect(self.on_edit_sketch_text)
        self.viewport.sketch_palette.edit_text_clicked.connect(self.on_palette_edit_text)
        self.browser.start_sketch_on_cplane.connect(self.start_sketch_on_cplane)
        self.viewport.offset_base_picked.connect(self.on_offset_base_picked)
        self.viewport.section_base_picked.connect(self.on_section_base_picked)
        self.browser.edit_section_requested.connect(self.edit_section)
        self.timeline_bar.edit_sketch_requested.connect(self.on_edit_sketch)
        self.timeline_bar.busy_reason = self._busy_reason
        self.browser.busy_reason = self._busy_reason
        self.timeline_bar.status_message.connect(self.status_label.setText)
        self.timeline_bar.highlight_changed.connect(
            lambda added, removed: self.viewport.set_preview(added, "join", extra=removed, extra_op="cut",
                                                             min_thickness=STEP_CHANGE_MIN_THICKNESS))
        self.timeline_bar.flash_sketch_requested.connect(self.viewport.set_flash_sketch)
        self.timeline_bar.step_edges_changed.connect(self.viewport.set_step_edges)
        self.browser.export_body_stl.connect(self.export_single_body_stl)
        self.browser.export_body_step.connect(self.export_single_body_step)
        self.browser.move_body_requested.connect(self.prompt_move_body)
        self.browser.body_color_requested.connect(self.prompt_body_color)
        self.browser.split_body_requested.connect(self.prompt_split_body)
        self.browser.shell_body_requested.connect(self.prompt_shell)
        self.browser.insert_canvas_requested.connect(self.prompt_insert_canvas)
        self.browser.edit_canvas_requested.connect(self.prompt_edit_canvas)
        self.viewport.edit_sketch_requested.connect(self.on_edit_sketch)
        self.viewport.extrude_sketch_requested.connect(self.on_extrude_sketch)
        self.browser.named_view_requested.connect(self.viewport.set_view)
        self.browser.extrude_sketch_requested.connect(self.on_extrude_sketch)
        self.browser.offset_plane_requested.connect(self.on_browser_offset_plane)
        self.browser.find_in_window_requested.connect(self.find_in_window)
        self.browser.find_in_timeline_requested.connect(self.find_in_timeline)
        self.browser.preview_changed.connect(self.viewport.set_display_override)
        self.browser.status_message.connect(self.status_label.setText)
        self.browser.feature_selected.connect(self.on_browser_feature_selected)
        self.browser.feature_edit_requested.connect(self.on_browser_feature_edit)
        self.browser.pick_feature = self.pick_browser_feature
        self.browser.dimension_selected.connect(self.viewport.show_dimension_entities)
        self.browser.feature_delete_requested.connect(self.on_browser_feature_delete)
        self.browser.delete_sketch_requested.connect(self.on_delete_sketch)


    def on_open_settings(self):
        from omacad.ui.settings_dialog import SettingsDialog
        from omacad.ui.settings import get_settings
        before_curves = get_settings().get("curve_segments")
        before_scale = get_settings().get("button_scale")
        before_labels = get_settings().get("show_button_labels")
        before_group_prim = get_settings().get("group_primitives")
        before_group_mod = get_settings().get("group_modify")
        before_group_insp = get_settings().get("group_inspect")
        before_group_cons = get_settings().get("group_constraints")

        dlg = SettingsDialog(self)
        dlg.exec()
        self.on_theme_changed()   # the theme choice may have changed (colours were re-applied by theme.set_fixed_theme)

        grouping_changed = (
            get_settings().get("group_primitives") != before_group_prim or
            get_settings().get("group_modify") != before_group_mod or
            get_settings().get("group_inspect") != before_group_insp or
            get_settings().get("group_constraints") != before_group_cons
        )
        scale_changed = (get_settings().get("button_scale") != before_scale
                         or get_settings().get("show_button_labels") != before_labels)

        if grouping_changed or scale_changed:
            self.ribbon.rebuild_ribbon()
        if get_settings().get("curve_segments") != before_curves:
            self.rebuild_for_curve_quality()

    def rebuild_for_curve_quality(self):
        """Round shapes are cut into pieces when sketches and steps are built, so a new smoothness needs a rebuild."""
        from PySide6.QtWidgets import QApplication
        self.status_label.setText("Rebuilding with the new curve smoothness…")
        QApplication.processEvents()
        for sk in self.doc.sketches.values():
            sk.solve_profiles()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.viewport.update()
        self.status_label.setText("Rebuilt with the new curve smoothness.")

    # ------------------ Action Handlers ------------------

    def apply_theme_font(self):
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        theme.ensure_big_icon_style(app)
        if app is not None:
            f = QFont(theme.font_family())
            f.setPixelSize(13)
            # only when they change: setting the app's font or stylesheet restyles every widget of every window,
            # and a second window (or a test making many) would pay for all of them each time
            if app.font() != f:
                app.setFont(f)
            theme.apply_qt_palette()
            css = theme.indicator_stylesheet()                # visible tick boxes everywhere (lists, trees, dialogs)
            if app.styleSheet() != css:
                app.setStyleSheet(css)

    def on_theme_changed(self):
        """The Omarchy theme was switched: stylesheets were already re-applied by theme.refresh()."""
        theme.clear_icon_cache()
        self.apply_theme_font()
        if hasattr(self, "ribbon") and self.ribbon:
            self.ribbon.update_button_scale()
        if hasattr(self, "timeline_bar") and self.timeline_bar:
            self.timeline_bar.update_icons()
        self.viewport.update()
        self.status_label.setText("Theme updated.")

    def dock(self, dlg):
        """Put a tool dialog into the right-hand inspector panel."""
        self.inspector.dock_tool(dlg)

    def run_async(self, fn, on_success=None, on_error=None, status_msg: str = ""):
        """Runs a heavy function in the thread pool without freezing the GUI."""
        if status_msg:
            self.status_label.setText(status_msg)
        self.progress_bar.setVisible(True)

        worker = _BackgroundWorker(fn)

        def _handle_done(result):
            self.progress_bar.setVisible(False)
            if on_success:
                on_success(result)

        def _handle_err(err):
            self.progress_bar.setVisible(False)
            if on_error:
                on_error(err)
            else:
                self.status_label.setText(f"Error: {err}")

        worker.signals.finished.connect(_handle_done)
        worker.signals.error.connect(_handle_err)
        self.thread_pool.start(worker)

    def on_change_parameters(self):
        from omacad.ui.parameters_dialog import ParametersDialog
        ParametersDialog(self.doc, self).exec()
        self.viewport.update()

    def _busy_reason(self):
        """Why undo/redo must wait: a tool panel is open or something is being dragged."""
        if self.inspector.current_tool_dlg is not None or any(getattr(self, a, None) is not None for a in ("_extrude_dlg", "_revolve_dlg", "_round_dlg")):
            return "Finish or cancel the open tool first (Esc)."
        if self.viewport.is_busy():
            return "Finish what you are doing first (Esc)."
        return None

    def _after_history_change(self):
        self.viewport.set_preview(None)
        self.viewport.clear_extrude_handle()
        self.viewport.update()
        self._update_undo_actions()

    def _update_undo_actions(self):
        u, r = self.doc.undo_label(), self.doc.redo_label()
        self.act_undo.setText(f"Undo {u}" if u else "Undo")
        self.act_undo.setEnabled(u is not None)
        self.act_redo.setText(f"Redo {r}" if r else "Redo")
        self.act_redo.setEnabled(r is not None)

    def on_undo(self):
        busy = self._busy_reason()
        if busy:
            self.status_label.setText(busy)
            return
        name = self.doc.undo()
        self._after_history_change()
        self.status_label.setText(f"Undo: {name}." if name else "Nothing to undo.")

    def _escape_pressed(self):
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        self.viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))

    def _active_tool_title(self):
        dlg = self.inspector.current_tool_dlg
        return dlg.windowTitle() if dlg is not None else None

    def on_lay_face_requested(self, face, mode: str):
        if mode == "ground":
            self.doc.lay_face_on(face.body_id, face.normal, face.origin, (0, 0, 0), (0, 0, 1))
            self.viewport.update()
            self.status_label.setText("Laid the face on the ground. Undo (Ctrl+Z) turns it back.")
        else:
            self._lay_face = face
            self.viewport.begin_plane_pick("lay_target")
            self.status_label.setText("Lay flat: click the face or plane this face should rest on (Esc cancels).")

    def on_lay_target_picked(self, plane):
        face, self._lay_face = self._lay_face, None
        if face is None or face.body_id not in self.doc.bodies:
            return
        self.doc.lay_face_on(face.body_id, face.normal, face.origin, plane.origin, plane.normal)
        self.viewport.update()
        self.status_label.setText("Laid the face on the chosen plane.")

    def on_menu_command(self, cmd: str):
        """Entries of the viewport's right-click menus that need the main window."""
        if cmd in ("tool_ok", "tool_cancel"):
            dlg = self.inspector.current_tool_dlg
            if dlg is not None:
                dlg.accept() if cmd == "tool_ok" else dlg.reject()
        elif cmd == "extrude":
            self.prompt_extrude()
        elif cmd == "fix_sketch":
            self.on_fix_sketch()
        elif cmd == "emboss":
            self.prompt_emboss()
        elif cmd.startswith("delete_sketch:"):
            self.on_delete_sketch(cmd.split(":", 1)[1])
        elif cmd == "revolve":
            self.prompt_revolve()
        elif cmd == "undo":
            self.on_undo()
        elif cmd == "redo":
            self.on_redo()
        elif cmd.startswith("sketch:"):
            self.start_sketch_on_plane(cmd.split(":", 1)[1])

    def on_redo(self):
        busy = self._busy_reason()
        if busy:
            self.status_label.setText(busy)
            return
        name = self.doc.redo()
        self._after_history_change()
        self.status_label.setText(f"Redo: {name}." if name else "Nothing to redo.")

    def start_sketch_on_cplane(self, pid: str):
        if pid in self.doc.construction_planes:
            self.on_plane_picked(self.doc.construction_plane(pid))

    def on_plane_pick_cancelled(self):
        what = {"sketch": "Create Sketch", "offset_base": "Offset Plane", "section_base": "Section View"}
        name = what.get(self.viewport.plane_pick_purpose)
        self.status_label.setText(f"{name} cancelled." if name else "Face selection cancelled.")

    def start_sketch_on_plane(self, plane_name: str):
        sketch = self.doc.start_sketch(plane_name)
        # Smoothly orient camera facing normal to sketch plane
        if plane_name.upper() == "XY":
            self.viewport.azimuth = 0.0
            self.viewport.elevation = 89.9
        elif plane_name.upper() == "XZ":
            self.viewport.azimuth = 0.0
            self.viewport.elevation = 0.0
        elif plane_name.upper() == "YZ":
            self.viewport.azimuth = 90.0
            self.viewport.elevation = 0.0
        self.viewport.update()
        self.status_label.setText(f"Active Sketch: {sketch.name} on {plane_name} plane. Select a tool (Line, Rect, Circle) to draw.")

    def on_extrude_sketch(self, sketch_id: str):
        """Right-click a sketch > Extrude: open the Extrude panel with that sketch's first closed profile chosen."""
        sk = self.doc.sketches.get(sketch_id)
        if sk is None:
            return
        if self.doc.active_sketch is not None:
            self.on_finish_sketch()
        sk.visible = True
        profiles = sk.solve_profiles()
        if not profiles:
            self.status_label.setText(f"{sk.name} has no closed profile to extrude.")
            return
        self.doc.selected_profile = (sketch_id, 0)
        self.prompt_extrude()
        dlg = getattr(self, "_extrude_dlg", None)
        if dlg is not None:
            dlg.reload_profiles()
            dlg.select_profile((sketch_id, 0))

    def find_in_window(self, kind: str, item_id: str):
        if kind == "body":
            self.doc.select_body(item_id)
            self.viewport.zoom_to_body(item_id)
        elif kind == "sketch":
            self.viewport.zoom_to_sketch(item_id)

    def on_browser_feature_delete(self, feature_id):
        if self.timeline_bar._blocked():
            return
        from omacad.ui import feature_edit
        index = self.doc.object_history.index(self.doc, feature_id)
        if index is not None and feature_edit.confirm_delete(self, self.doc, index):
            self.doc.delete_feature(index)

    def start_construction_tool(self, tool: str):
        """Construction ▾ Line/Circle: helper geometry on, and that tool picked, in one step."""
        if not self.viewport.construction_mode:
            self.viewport.toggle_construction_mode()
        self.ribbon.select_sketch_tool(tool)

    def pick_browser_feature(self, feature_id):
        handler = self.timeline_bar.feature_pick_handler
        if handler is None:
            return False
        handler(feature_id)
        return True

    def on_browser_feature_selected(self, feature_id):
        index = self.doc.object_history.index(self.doc, feature_id)
        if index is not None:
            self.timeline_bar.on_node_clicked(index + 1)

    def on_browser_feature_edit(self, feature_id):
        index = self.doc.object_history.index(self.doc, feature_id)
        if index is not None:
            self.timeline_bar.on_node_edit(index + 1)

    def find_in_timeline(self, kind: str, item_id: str):
        idx = self.doc.feature_index_for(kind, item_id)
        if idx is None:
            self.status_label.setText("That item has no step in the timeline.")
            return
        from omacad.ui.object_browser import find_feature
        find_feature(self.browser, self.doc.timeline.features[idx].feature_id)

    def on_fix_sketch(self):
        """Fix Sketch: close the open sketch's drawing into faces (see model/sketch_fix.py), as one undo step."""
        from omacad.model.sketch_fix import fix_sketch
        sk = self.doc.active_sketch
        if sk is None:
            self.status_label.setText("Fix Sketch works on the open sketch: edit a sketch first.")
            return
        before = sk.to_dict()
        done = fix_sketch(sk)
        self.doc.record_sketch_change(sk, before)
        n = len(sk.profiles)
        if done:
            self.status_label.setText(f"Fix Sketch: {', '.join(done)}. {n} closed face(s) now. Ctrl+Z undoes it.")
        elif n:
            self.status_label.setText(f"Fix Sketch: the sketch is already closed ({n} face(s)); nothing changed.")
        else:
            self.status_label.setText("Fix Sketch: nothing to close here (a face needs at least two connected curves).")
        self.doc.notify_changed()
        self.viewport.update()

    def on_browser_offset_plane(self, kind: str, item_id: str):
        """Browser > Offset Plane: start from the plane or sketch that was right-clicked (it used to ask for a pick)."""
        if kind == "plane":
            base = self.doc.origin_planes.get(item_id)
        elif kind == "cplane":
            base = self.doc.construction_plane(item_id) if item_id in self.doc.construction_planes else None
        else:
            sk = self.doc.sketches.get(item_id)
            base = sk.plane if sk is not None else None
        if base is None:
            self.prompt_offset_plane()
            return
        if self.doc.active_sketch:
            self.on_finish_sketch()
        self.on_offset_base_picked(base)

    def on_delete_sketch(self, sketch_id: str):
        from omacad.ui import feature_edit
        idx = self.doc.feature_index_for("sketch", sketch_id)
        if idx is not None and feature_edit.confirm_delete(self, self.doc, idx):
            self.doc.delete_feature(idx)

    def on_edit_sketch(self, sketch_id: str):
        sketch = self.doc.edit_sketch(sketch_id)
        if sketch:
            self.viewport.align_to_plane(sketch.plane)
            self.viewport.update()
            self.status_label.setText(f"Editing {sketch.name}. Double-click dimension badges or text to edit.")

    def on_edit_sketch_text(self, sketch_id: str, entity_id: str):
        if self.doc.active_sketch is None or self.doc.active_sketch.sketch_id != sketch_id:
            self.on_edit_sketch(sketch_id)
        if self.doc.active_sketch is not None:
            self.viewport.selected_entities = {entity_id}
            self.viewport.selection_changed.emit()
            self.viewport.update()
            self.prompt_text_edit(entity_id)

    def on_palette_edit_text(self):
        sk = self.doc.active_sketch
        if sk is None:
            return
        from omacad.model.sketch import SketchText
        texts = [e for e in sk.entities if isinstance(e, SketchText)]
        if not texts:
            return
        chosen = next((e for e in texts if e.entity_id in self.viewport.selected_entities), texts[0])
        self.viewport.selected_entities = {chosen.entity_id}
        self.viewport.selection_changed.emit()
        self.viewport.update()
        self.prompt_text_edit(chosen.entity_id)

    def on_sketch_tool_selected(self, tool_name: str):
        self.viewport.set_sketch_tool(tool_name)
        if tool_name == "TEXT":
            self.prompt_text()
            return
        if tool_name != "ROTATE":
            self.status_label.setText(f"Sketch Tool: {tool_name}. Click on grid plane to place points.")

    def _sync_construction_button(self, val=None):
        """The viewport's construction mode is the truth; the ribbon button only mirrors it."""
        btn = getattr(self.ribbon, "btn_construct", None)
        if btn is not None:
            btn.setChecked(self.viewport.construction_mode if val is None else bool(val))

    def _reset_construction_outside_sketch(self):
        if self.doc.active_sketch is None and self.viewport.construction_mode:
            self.viewport.toggle_construction_mode()
        else:
            self._sync_construction_button()

    def sync_sketch_tool_from_viewport(self, tool_name: str):
        self.ribbon.btn_line.setChecked(tool_name == "LINE")
        self.ribbon.btn_rect.setChecked(tool_name in RECT_TOOLS)
        self.ribbon.btn_circle.setChecked(tool_name in ("CIRCLE", "SMART_CIRCLE"))
        self.ribbon.btn_polygon.setChecked(tool_name == "POLYGON")
        self.ribbon.btn_arc.setChecked(tool_name == "ARC")
        self.ribbon.btn_slot.setChecked(tool_name == "SLOT")
        self.ribbon.btn_text.setChecked(tool_name == "TEXT")
        self.ribbon.btn_trim_sk.setChecked(tool_name == "TRIM")
        self.ribbon.btn_mirror_sk.setChecked(tool_name == "MIRROR")
        self.ribbon.btn_offset_sk.setChecked(tool_name == "OFFSET")
        self.ribbon.btn_fillet_sk.setChecked(tool_name == "FILLET")
        self.ribbon.btn_dim.setChecked(tool_name == "DIMENSION")
        self.ribbon.btn_move.setChecked(tool_name == "MOVE")
        self.ribbon.btn_rotate_sk.setChecked(tool_name == "ROTATE")
        if tool_name != "NONE":
            self.status_label.setText(f"Sketch Tool: {tool_name}. Click on grid plane to place points.")
        else:
            self.status_label.setText("Ready.")

    def on_finish_sketch(self):
        self.viewport.set_sketch_tool("NONE")
        self.viewport.constraint_help.dismiss()
        sketch = self.doc.finish_sketch()
        if sketch:
            self.status_label.setText(f"Finished {sketch.name} ({len(sketch.profiles)} closed profiles found).")
        self.viewport.update()

    def on_extrude_face(self, face):
        """Right-click > Extrude this Face: the face outline becomes the profile; default is 5 mm into the body."""
        sk, idx = self.doc.face_to_sketch(face)
        if idx is None:
            self.status_label.setText("That face has no closed outline to extrude.")
            return
        self.doc.selected_profile = (sk.sketch_id, idx)
        dlg = getattr(self, "_extrude_dlg", None)
        if dlg is not None:
            dlg.reload_profiles()
            dlg.select_profile((sk.sketch_id, idx))
            dlg.set_distance(-5.0)
            dlg.raise_()
            return
        self.prompt_extrude(default_distance=-5.0)

    def on_delete_selected(self):
        # In sketch mode Delete removes the selected sketch elements
        dim = self.viewport.dimension_to_delete() if self.doc.active_sketch else None
        if dim and not self.viewport.selected_entities and self.viewport.delete_dimension(*dim):
            self.browser.refresh_tree()
            return
        if self.doc.active_sketch and self.viewport.selected_entities:
            n = self.viewport.delete_selected_entities()
            self.status_label.setText(f"Deleted {n} sketch element{'s' if n != 1 else ''}.")
            return
        if self.doc.active_sketch:
            self.status_label.setText("Select sketch elements to delete them (Del over a dimension deletes it).")
            return
        busy = self._busy_reason()      # the open tool works on the selected bodies
        if busy:
            self.status_label.setText(busy)
            return
        chosen = [b for b in self.doc.selected_body_ids if b in self.doc.bodies]
        if not chosen:
            self.status_label.setText("Nothing selected to delete.")
            return
        for b_id in chosen:
            self.doc.delete_body(b_id)
        self.status_label.setText(f"Deleted {len(chosen)} bod{'ies' if len(chosen) != 1 else 'y'}.")

    def on_inspect(self):
        num_bodies = len(self.doc.bodies)
        num_sketches = len(self.doc.sketches)
        num_features = len(self.doc.timeline.features)
        QMessageBox.information(
            self, "Document Statistics",
            f"Bodies: {num_bodies}\nSketches: {num_sketches}\nParametric Features: {num_features}\nUnits: mm"
        )

    def sync_sketch_status(self):
        """Sketch name, plane and solve status ("Under defined (2 DOF)") at the right of the status bar."""
        sk = self.doc.active_sketch
        text = ""
        has_text = False
        if sk is not None:
            from omacad.model.sketch import SketchText
            has_text = any(isinstance(e, SketchText) for e in sk.entities)
            status = self.doc.sketch_status(sk)
            text = f"✏️ {sk.name} ({sk.plane.name})" + (f"  ·  {status}" if status else "")
        self.viewport.sketch_palette.set_has_text(has_text)
        if text != self.lbl_sketch_status.text():
            self.lbl_sketch_status.setText(text)

    def sync_origin_actions(self):
        """Tick the View > Origin entries to match the document (they show each part's own switch)."""
        for (kind, name), act in getattr(self, "_origin_actions", {}).items():
            on = self.doc.origin_vis["all"] if kind == "all" else self.doc.origin_vis[ORIGIN_GROUPS[kind]][name]
            act.blockSignals(True)
            act.setChecked(bool(on))
            act.blockSignals(False)

    def toggle_grid(self):
        self.viewport.show_grid = not self.viewport.show_grid
        self.viewport.update()

    def toggle_edges(self):
        self.viewport.show_edges = not self.viewport.show_edges
        self.viewport.update()














    # ------------------ Restart with a new version ------------------






    def _keep_viewcube_clear(self, inspector_width: int):
        """The ViewCube sits just to the left of the Inspector, whatever width the panel fitted to."""
        self.viewport.viewcube.right_margin = inspector_width + 25
        self.viewport.update()

    def grab_with_overlay(self, view_shot):
        """Window screenshot where the 3D view includes its painter overlay (dimensions, banner, ViewCube):
        `QWidget.grab` renders only the GL scene of a QOpenGLWidget, so the framebuffer grab is painted on top,
        and then the panels floating on the view (Browser, Inspector, ...) on top of that."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter
        shot = self.grab()
        painter = QPainter(shot)
        try:
            top_left = self.viewport.mapTo(self, self.viewport.rect().topLeft())
            painter.drawImage(QRectF(top_left.x(), top_left.y(), self.viewport.width(), self.viewport.height()), view_shot)
            for child in self.viewport.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if child.isVisible():
                    painter.drawPixmap(child.mapTo(self, child.rect().topLeft()), child.grab())
        finally:
            painter.end()
        return shot

    def on_report_problem(self):
        """Screenshot first (before any dialog covers the problem), then the note, then the report goes to the AI agent."""
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QPixmap
        from omacad import feedback
        from omacad.ui.feedback_dialog import FeedbackDialog

        def png(image):
            data, buf = QByteArray(), QBuffer()
            buf.setBuffer(data)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buf, "PNG")
            return bytes(data)

        view_shot = self.viewport.grabFramebuffer()
        window_shot = self.grab_with_overlay(view_shot)
        dlg = FeedbackDialog(self, window_shot)
        if not dlg.exec():
            return
        v = self.viewport
        extra = {"camera": {"azimuth": v.azimuth, "elevation": v.elevation, "distance": v.distance,
                            "target": [float(x) for x in v.target]},
                 "sketch_tool": v.sketch_tool, "selected_sketch_entities": sorted(v.selected_entities),
                 "window_size": [self.width(), self.height()]}
        own = dlg.own_image()
        if own is not None:         # the user's own picture replaces the built-in screenshots
            images = {"screenshot_own.png": png(own)}
        else:
            marked = dlg.marked_image()
            if marked is not None:
                images = {"screenshot_marked.png": png(marked)}
            else:
                images = {"screenshot_window.png": png(window_shot.toImage())}
        folder = feedback.build_bundle(self.doc, dlg.text(), images, extra)
        if dlg.fix_now() and feedback.launch_agent(folder, dlg.selected_agent()):
            self.status_label.setText(f"Report sent to {dlg.selected_agent()} (a terminal opened). Saved in {folder}")
        else:
            self.status_label.setText(f"Report saved in {folder}")

    def on_request_change(self):
        """Like Report problem, but the result is a request for change that goes to GitHub for the owner to review."""
        from PySide6.QtWidgets import QApplication
        from omacad import rfc
        from omacad.ui.feedback_dialog import FeedbackDialog
        from omacad.ui.settings import get_settings
        view_shot = self.viewport.grabFramebuffer()
        window_shot = self.grab_with_overlay(view_shot)
        dlg = FeedbackDialog(self, window_shot, mode="request")
        if not dlg.exec():
            return
        if not dlg.text():
            self.status_label.setText("Request not sent: write what you would like first.")
            return
        get_settings().set("rfc_name", dlg.name())
        own = dlg.own_image()
        if own is not None:         # the user's own picture replaces the built-in screenshots
            images = {"screenshot_own.png": self._png(own)}
        else:
            marked = dlg.marked_image()
            if marked is not None:
                images = {"screenshot_marked.png": self._png(marked)}
            else:
                images = {"screenshot_window.png": self._png(window_shot.toImage())}
        for i, (name, image) in enumerate(dlg.additional_images(), 1):
            safe_name = Path(name).name.replace("/", "_").replace("\\", "_")
            images[f"attachment_{i:02d}_{safe_name}"] = self._png(image)
        v = self.viewport
        extra = {"kind": "request for change", "camera": {"azimuth": v.azimuth, "elevation": v.elevation, "distance": v.distance},
                 "window_size": [self.width(), self.height()]}
        folder = rfc.build_request(self.doc, dlg.text(), dlg.name(), images, extra)
        self.status_label.setText("Sending your request…")
        QApplication.processEvents()
        ok, message = rfc.send(folder)
        self.status_label.setText(message)
        QMessageBox.information(self, "Request a change", message)

    @staticmethod
    def _png(image) -> bytes:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        data, buf = QByteArray(), QBuffer()
        buf.setBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        return bytes(data)

    def on_join_bodies(self, body_ids) -> None:
        body = self.doc.join_bodies(list(body_ids))
        if body is not None:
            self.status_label.setText(f"Joined {len(body_ids)} bodies into {body.name}.")

    def show_help(self):
        """Help & Commands (F1): every function with help text and a keyword search (see ui/help_dialog.py)."""
        from omacad.ui.help_dialog import HelpWindow
        win = getattr(self, "_help_window", None)
        if win is None:
            win = self._help_window = HelpWindow(self)
        win.show()
        win.raise_()
        win.activateWindow()
        win.edt_search.setFocus()
        win.edt_search.selectAll()

    def on_changelog(self):
        from omacad.ui.changelog_dialog import ChangelogDialog
        ChangelogDialog(self).exec()

    def on_about(self):
        QMessageBox.about(
            self, "About Omacad",
            f"<h3>Omacad {__import__('omacad').__version__}</h3>"
            "<p>A native CAD application for <b>Omarchy Linux</b>.</p>"
            "<p>Inspired by Autodesk Fusion 360, built with Python, PySide6 (Qt6), and Manifold3D.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Watertight Solid CSG Modeling (Manifold3D)</li>"
            "<li>2D Sketching & Closed Profile Extrusion</li>"
            "<li>Parametric Feature Timeline & History Replay</li>"
            "<li>Interactive 3D ViewCube & Dynamic Grid</li>"
            "<li>Native Wayland Integration on Omarchy</li>"
            "<li>Direct STL & OBJ Export for 3D Printing</li>"
            "</ul>"
            "<p><i>Vibecoded by Kindstrom</i></p>"
        )
