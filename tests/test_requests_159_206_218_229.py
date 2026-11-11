"""#159 linked/unlinked copy in Move, #206 title after Save, #218 Offset drag arrow in the view,
#229 a new name typed into a dimension becomes a parameter listed in Change Parameters."""
import os

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document

DATA = os.path.join(os.path.dirname(__file__), "data")


@pytest.fixture(autouse=True)
def no_leftover_names():
    from omacad.model import expr
    expr.set_variables({})          # parameter names are a module-level table shared by all documents
    yield
    expr.set_variables({})


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app):
    from omacad.ui.main_window import MainWindow
    w = MainWindow()
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


# ---- #229 ---------------------------------------------------------------------------------------

def test_report_dimension_name_shows_up_in_change_parameters(app):
    import json
    from omacad.model.sketch import Sketch
    with open(os.path.join(DATA, "dimension_named_parameter_229.omacad"), encoding="utf-8") as fh:
        data = json.load(fh)
    doc = Document()
    for sd in data["sketches"]:                       # the report's unfinished sketch (not in the timeline)
        sk = Sketch.from_dict(sd)
        doc.sketches[sk.sketch_id] = sk
    assert doc.parameters == []
    missing = doc.missing_parameters()
    assert [(q.name, float(q.expr)) for q in missing] == [("växel", pytest.approx(78.4693, abs=1e-4))]
    assert doc.parameters == []                       # listing changes nothing
    from omacad.ui.parameters_dialog import ParametersDialog
    dlg = ParametersDialog(doc)
    names = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
    assert names == ["växel"]
    dlg.apply_and_close()
    assert [q.name for q in doc.parameters] == ["växel"]
    assert doc.unresolved_formulas() == []


def test_typed_new_name_in_line_length_field_becomes_a_parameter(app):
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    sk = doc.start_sketch("XY")
    vp = Viewport3D(doc)
    try:
        vp.set_sketch_tool("LINE")
        vp.sketch_start_uv = (0.0, 0.0)
        vp._raw_mouse_uv = (30.0, 0.0)
        vp.dyn.start("LINE")
        vp.dyn.texts[0] = "växel"
        vp._refresh_dyn()
        assert vp.dyn.invalid(0)
        assert vp._dyn_new_parameter(0)               # what Enter does with a name nobody defined
        assert [(q.name, float(q.expr)) for q in doc.parameters] == [("växel", pytest.approx(30.0))]
        assert not vp.dyn.invalid(0) and vp.dyn.locked(0) == pytest.approx(30.0)
        vp._commit_sketch_point(vp.sketch_current_uv)
        dims = [d for d in sk.dimensions if d.expr]
        assert dims and dims[0].expr == "växel"
        assert doc.unresolved_formulas() == []
    finally:
        vp.close()
        vp.deleteLater()
        app.processEvents()


def test_name_typed_and_committed_by_click_also_becomes_a_parameter(app):
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    sk = doc.start_sketch("XY")
    vp = Viewport3D(doc)
    try:
        vp.set_sketch_tool("LINE")
        vp.sketch_start_uv = (0.0, 0.0)
        vp._raw_mouse_uv = (0.0, 25.0)
        vp.dyn.start("LINE")
        vp.dyn.texts[0] = "gear_len"
        vp._refresh_dyn()
        vp._commit_sketch_point(vp.sketch_current_uv)        # mouse click without Enter (the report's case)
        assert [q.name for q in doc.parameters] == ["gear_len"]
        assert float(doc.parameters[0].expr) == pytest.approx(25.0)
        assert doc.missing_parameters() == []
    finally:
        vp.close()
        vp.deleteLater()
        app.processEvents()


def test_existing_or_invalid_names_are_not_redefined():
    doc = Document()
    assert doc.define_parameter("width", 10)
    assert not doc.define_parameter("width", 20)
    assert not doc.define_parameter("2x", 5) and not doc.define_parameter("pi", 5)
    assert [(q.name, q.expr) for q in doc.parameters] == [("width", "10")]


# ---- #206 ---------------------------------------------------------------------------------------

def test_title_shows_file_name_after_save_even_if_recent_menu_was_deleted(win, tmp_path):
    import shiboken6
    win.doc.add_box(10, 10, 10)
    shiboken6.delete(win.menu_recent)                 # Lennart's log: QMenu already deleted during Save
    path = str(tmp_path / "Japandi 1.omacad")
    win._save_to(path)
    assert "Japandi 1.omacad" in win.windowTitle() and "Untitled" not in win.windowTitle()
    assert "Japandi 1.omacad" in win.lbl_doc_title.text()
    assert shiboken6.isValid(win.menu_recent)
    texts = [a.text() for a in win.menu_recent.actions()]
    assert any("Japandi 1.omacad" in t for t in texts)
    assert win.menu_recent.menuAction() in win.menu_file.actions()


# ---- #159 ---------------------------------------------------------------------------------------

def _box_index(doc):
    return next(i for i, f in enumerate(doc.timeline.features) if f.feature_type == "box")


def test_linked_copy_follows_the_original_unlinked_does_not():
    doc = Document()
    doc.add_box(10, 10, 10)
    src = next(iter(doc.bodies))
    doc.move_body(src, dx=30, copy_body=True, linked=True)
    doc.move_body(src, dx=-30, copy_body=True, linked=False)
    assert any(f.feature_type == "branch" for f in doc.timeline.features)
    by_x = sorted(doc.bodies.values(), key=lambda b: b.manifold.bounding_box()[0])
    unlinked, original, linked = by_x
    assert original.body_id == src
    assert linked.manifold.bounding_box()[0] == pytest.approx(30.0)
    assert unlinked.manifold.bounding_box()[0] == pytest.approx(-30.0)
    assert doc.edit_feature(_box_index(doc), height=25.0)
    vols = {bid: b.manifold.volume() for bid, b in doc.bodies.items()}
    assert vols[src] == pytest.approx(2500.0)
    assert vols[linked.body_id] == pytest.approx(2500.0)                 # follows
    assert vols[unlinked.body_id] == pytest.approx(1000.0)               # its own steps
    assert doc.bodies[linked.body_id].manifold.bounding_box()[0] == pytest.approx(30.0)   # keeps its place


def test_move_panel_offers_linked_copy(win):
    win.doc.add_box(10, 10, 10)
    src = next(iter(win.doc.bodies))
    win.prompt_move_body(src)
    dlg = win.inspector.current_tool_dlg
    assert not dlg.cmb_copy_kind.isEnabled()
    dlg.chk_copy_body.setChecked(True)
    assert dlg.cmb_copy_kind.isEnabled()
    dlg.cmb_copy_kind.setCurrentIndex(dlg.cmb_copy_kind.findData("linked"))
    dlg.spn_dx.setValue(40.0)
    dlg.accept()
    QApplication.processEvents()
    assert any(f.feature_type == "branch" for f in win.doc.timeline.features)
    assert len(win.doc.bodies) == 2
    xs = sorted(b.manifold.bounding_box()[0] for b in win.doc.bodies.values())
    assert xs == [pytest.approx(0.0), pytest.approx(40.0)]
    win.doc.undo()
    assert len(win.doc.bodies) == 1


# ---- #218 ---------------------------------------------------------------------------------------

def test_offset_shows_a_drag_arrow_pointing_outward_and_dragging_sets_the_distance(app, monkeypatch):
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    sk = doc.start_sketch("XY")
    lines = sk.add_rect((0.0, 0.0), (20.0, 10.0))
    vp = Viewport3D(doc)
    seen = {}
    try:
        vp.selected_entities = {e.entity_id for e in lines}

        def prompt(*args, **kwargs):
            assert kwargs.get("handle_drag") is True
            kwargs["on_change"](4.0)
            h = vp.extrude_handle
            seen["origin"], seen["axis"], seen["dist"] = h["origin"].copy(), h["axis"].copy(), h["dist"]
            return (3.0, None)

        vp.prompt_dimension_value = prompt
        vp.offset_selected()
        assert vp.extrude_handle is None                  # cleared afterwards
        assert seen["dist"] == pytest.approx(4.0)
        centre = np.array([10.0, 5.0, 0.0])
        assert float(seen["axis"] @ (seen["origin"] - centre)) > 0      # positive = outward
        assert np.linalg.norm(seen["axis"]) == pytest.approx(1.0)
        assert len(sk.entities) == 8
    finally:
        vp.close()
        vp.deleteLater()
        app.processEvents()


def test_dragging_the_arrow_drives_the_value_box(app, monkeypatch):
    from omacad.ui import dialogs
    from omacad.ui.viewport.viewport import Viewport3D
    from PySide6.QtWidgets import QDialog
    vp = Viewport3D(Document())

    def fake_run(dlg):
        vp.extrude_handle_dragged.emit(7.3)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(dialogs, "run_docked", fake_run)
    try:
        res = vp.prompt_dimension_value("Offset", "Distance", 5.0, lo=-50, hi=50, on_change=lambda v: None,
                                        handle_drag=True)
        assert res[0] == pytest.approx(7.3)
        vp.extrude_handle_dragged.emit(1.0)              # disconnected after the prompt: nothing breaks
    finally:
        vp.close()
        vp.deleteLater()
        app.processEvents()


def test_mouse_drag_on_the_offset_arrow_in_sketch_mode_emits_distances(app):
    """The arrow catches the press before the Offset tool's own clicks (real mouse events on the widget)."""
    from PySide6.QtCore import QPointF, Qt, QEvent
    from PySide6.QtGui import QMouseEvent
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    sk = doc.start_sketch("XY")
    lines = sk.add_rect((0.0, 0.0), (20.0, 10.0))
    vp = Viewport3D(doc)
    vp.resize(800, 600)
    try:
        if hasattr(vp, "align_to_plane"):
            vp.align_to_plane(sk.plane)
        vp.set_sketch_tool("OFFSET")
        vp.selected_entities = {e.entity_id for e in lines}
        origin, axis = vp._offset_handle_frame(sk, set(vp.selected_entities))
        vp.set_extrude_handle(origin, axis, 5.0)
        got = []
        vp.extrude_handle_dragged.connect(got.append)
        g = vp._handle_geometry()
        assert g is not None
        start = QPointF(*g[2])
        far = vp.world_to_screen(origin + axis * 30.0)
        assert far is not None

        def ev(kind, pos, buttons):
            return QMouseEvent(kind, pos, pos, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)

        vp.mousePressEvent(ev(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton))
        assert vp._handle_drag
        vp.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(*far), Qt.MouseButton.LeftButton))
        vp.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(*far), Qt.MouseButton.NoButton))
        assert not vp._handle_drag
        assert got and got[-1] > 10.0                 # dragged outward, further than it started
        assert len(sk.entities) == 4                  # the press did not run the Offset tool's pick
    finally:
        vp.close()
        vp.deleteLater()
        app.processEvents()
