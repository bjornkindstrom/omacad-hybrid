"""Tests for requests #193, #194, and #195:
- #193: Quick button for Shell on ribbon, thickness slider, and automatic opening face default.
- #194: Removal of dark/black halo rim during face and edge hover/selection.
- #195: Face boundary outline fallback via patch_boundary_segments when filleted cylinder caps have 0 body.edges.
"""

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui import commands
from omacad.ui.dialogs.shell_dlg import ShellDialog
from omacad.ui.numeric_slider import NumericSlider
from omacad.ui.viewport.picker_mixin import patch_boundary_segments, PickerMixin


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_request_193_shell_quick_button():
    """Verify Shell is a direct quick button in MODIFY, not buried in MODIFY_BODY."""
    modify_group = next(items for title, items in commands.SOLID_GROUPS if title == "MODIFY")
    assert "shell" in modify_group, "Shell should be a standalone button in MODIFY"

    # Verify Shell was removed from the MODIFY_BODY dropdown to prevent duplicate appearance
    modify_body = next(item for item in modify_group if isinstance(item, tuple) and item[0] == "modify_body")
    assert "shell" not in modify_body[4], "Shell should not be duplicated inside MODIFY_BODY"


def test_request_193_shell_dialog_thickness_slider(qapp):
    """Verify ShellDialog has a slider paired with spn_thickness."""
    doc = Document()
    doc.add_cylinder(radius=10.0, height=20.0)

    dlg = ShellDialog(doc)
    sliders = [w for w in dlg.findChildren(NumericSlider) if w.field is dlg.spn_thickness]
    assert len(sliders) == 1, "spn_thickness should have a NumericSlider"

    ns = sliders[0]
    changed_emitted = []
    dlg.changed.connect(lambda: changed_emitted.append(True))

    # Test slider movement updates thickness
    ns.slider.setValue(ns.slider.maximum() // 2)
    assert dlg.spn_thickness.value() > 0
    assert len(changed_emitted) > 0


def test_request_193_auto_open_face_in_shell(qapp):
    """Verify prompt_shell auto-detects top planar face when no face was preselected."""
    from unittest.mock import MagicMock
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QWidget
    from omacad.ui.controllers.body_prompts import BodyPromptsMixin

    doc = Document()
    cylinder = doc.add_cylinder(radius=10.0, height=30.0)
    bid = list(doc.bodies.keys())[0]

    class MockVP(QWidget):
        shell_face_picked = Signal(object)
        body_clicked = Signal(str)

        def __init__(self):
            super().__init__()
            self.selected_faces = []
            self.shell_target_body_id = None
            self.highlighted_faces = []

        def begin_plane_pick(self, *args):
            pass

        def end_plane_pick(self):
            pass

        def set_preview(self, *args):
            pass

        def world_to_screen(self, pt):
            return 0.0, 0.0

    class MockWindow(QWidget, BodyPromptsMixin):
        def __init__(self):
            super().__init__()
            self.doc = doc
            self.viewport = MockVP()
            self.docked_dlg = None
            self.inspector = MagicMock()
            self.status_label = MagicMock()

        def dock(self, dlg):
            self.docked_dlg = dlg

    win = MockWindow()
    win.prompt_shell(bid)

    assert win.docked_dlg is not None
    dlg = win.docked_dlg
    assert isinstance(dlg, ShellDialog)

    # Check that open_faces has 1 face and it is the top face (normal.z > 0.5, origin.z == 30.0)
    assert len(dlg.open_faces) == 1
    top_f = dlg.open_faces[0]
    assert top_f["normal"][2] > 0.5
    assert np.isclose(top_f["origin"][2], 30.0, atol=1e-3)

    # Check that highlighted_faces on viewport was set
    assert len(win.viewport.highlighted_faces) == 1

    # Check clear open faces button
    dlg.clear_faces()
    assert len(dlg.open_faces) == 0
    assert len(win.viewport.highlighted_faces) == 0


def test_request_194_no_dark_halo(qapp):
    """Verify render_edge_pick passes halo=False to draw_thick_lines for selected faces and edges."""
    from unittest.mock import MagicMock

    doc = Document()
    doc.add_cylinder(radius=10.0, height=20.0)
    bid = list(doc.bodies.keys())[0]
    body = doc.bodies[bid]

    class MockViewport(PickerMixin):
        def __init__(self):
            self.doc = doc
            self.selected_faces = [(bid, body.faces[0])]
            self.edge_pick_mode = False
            self.hover_face = None
            self.hover_surface = None
            self.hover_edge = None
            self.selected_edges = []
            self.prog_flat = 1
            self.prog_solid = 1
            self.prog_thick = 1
            self.edge_xray = False
            self.draw_thick_lines_calls = []

        def _idle_hover_ok(self):
            return True

        def draw_buffer_arrays(self, *args, **kwargs):
            pass

        def _trim_tris_by_section(self, tris):
            return tris

        def draw_thick_lines(self, mvp, flat_segments, rgba, width_px, halo=True, **kwargs):
            self.draw_thick_lines_calls.append({"halo": halo, "rgba": rgba, "width": width_px})

    vp = MockViewport()
    mvp = np.eye(4, dtype=np.float32)

    # Intercept OpenGL calls
    import OpenGL.GL as GL
    orig_glUseProgram = GL.glUseProgram
    orig_glGetUniformLocation = GL.glGetUniformLocation
    orig_glGetAttribLocation = GL.glGetAttribLocation
    orig_glUniformMatrix4fv = GL.glUniformMatrix4fv
    orig_glDepthMask = GL.glDepthMask
    orig_glEnable = GL.glEnable
    orig_glDisable = GL.glDisable
    orig_glPolygonOffset = GL.glPolygonOffset

    try:
        GL.glUseProgram = MagicMock()
        GL.glGetUniformLocation = MagicMock(return_value=0)
        GL.glGetAttribLocation = MagicMock(return_value=0)
        GL.glUniformMatrix4fv = MagicMock()
        GL.glDepthMask = MagicMock()
        GL.glEnable = MagicMock()
        GL.glDisable = MagicMock()
        GL.glPolygonOffset = MagicMock()

        vp.render_edge_pick(mvp)
    finally:
        GL.glUseProgram = orig_glUseProgram
        GL.glGetUniformLocation = orig_glGetUniformLocation
        GL.glGetAttribLocation = orig_glGetAttribLocation
        GL.glUniformMatrix4fv = orig_glUniformMatrix4fv
        GL.glDepthMask = orig_glDepthMask
        GL.glEnable = orig_glEnable
        GL.glDisable = orig_glDisable
        GL.glPolygonOffset = orig_glPolygonOffset

    assert len(vp.draw_thick_lines_calls) >= 2
    # Verify no call used halo=True (Request #194 fix)
    for call in vp.draw_thick_lines_calls:
        assert call["halo"] is False, f"draw_thick_lines called with halo=True: {call}"


def test_request_195_filleted_cylinder_boundary_fallback(qapp):
    """Verify filleted cylinder caps (which have 0 body.edges) outline via patch_boundary_segments."""
    doc = Document()
    body = doc.add_cylinder(radius=10.0, height=20.0)
    circ_edges = [e.ref() for e in body.edges if hasattr(e, "ref")]
    doc.add_fillet(circ_edges, size=2.0)
    filleted_body = doc.bodies[list(doc.bodies.keys())[0]]

    # Ensure filleted body has 0 sharp edges in body.edges
    assert len(filleted_body.edges) == 0

    class MockViewport(PickerMixin):
        def __init__(self):
            self.doc = doc

    vp = MockViewport()
    for face in filleted_body.faces:
        edges = vp._edges_of_face(face, filleted_body)
        assert len(edges) == 0, "No sharp edges in body.edges"
        # Fallback boundary segments
        b_segs = patch_boundary_segments(face.tris)
        assert len(b_segs) > 0, "patch_boundary_segments should produce outline segments"
        assert b_segs.shape[1:] == (2, 3), "Segments should have shape (K, 2, 3)"
