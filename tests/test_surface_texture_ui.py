"""Surface Texture: one command in every menu in place of Honeycomb, Knurl and Wavy Slices, and one panel for all three."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from omacad.model.features.offset_face import plane_face_ref
from omacad.ui import commands, help_topics
from omacad.ui.dialogs import SurfaceTextureDialog
from omacad.ui.feature_edit import can_edit
from omacad.ui.main_window import MainWindow

OLD = {"honeycomb", "knurl", "wavy_slices"}
R, H = 15.0, 40.0
ROUND = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": R, "length": H, "internal": False}


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    if w.inspector.current_tool_dlg is not None:
        w.inspector.current_tool_dlg.reject()
    w.close()


def flat(items):
    for item in items:
        if isinstance(item, tuple):
            yield from flat(item[4])
        elif item:
            yield item


def fan_ids(items):
    for item in items:
        yield item.id
        yield from fan_ids(item.children or [])


def test_the_old_commands_are_gone_from_the_ribbon_and_the_menus_and_the_new_one_is_there():
    assert not OLD & set(commands.COMMANDS)
    solid = [cid for _title, items in commands.SOLID_GROUPS for cid in flat(items)]
    menus = {title: list(flat(items)) for title, items in commands.MENUS}
    assert not OLD & set(solid) and not any(OLD & set(m) for m in menus.values())
    assert solid.count("surface_texture") == 1
    assert "surface_texture" in dict(commands.SOLID_GROUPS)["MODIFY"]
    assert menus["Modify"].count("surface_texture") == 1 and "surface_texture" not in menus["Create"]


def test_the_fan_menu_has_it_under_modify_only(win):
    categories = {c.id: c for c in win.viewport._build_workspace_fan_categories(False)}
    assert not OLD & set(fan_ids(categories.values()))
    assert "surface_texture" in [c.id for c in categories["cat_modify"].children]
    assert "surface_texture" not in fan_ids(categories["cat_create"].children)


def test_the_fan_entry_opens_the_tool(win):
    win.doc.add_box(20, 20, 20)
    win.on_menu_command("surface_texture")
    assert isinstance(win.inspector.current_tool_dlg, SurfaceTextureDialog)


def test_a_right_clicked_face_starts_on_cells_with_that_face(win):
    body = win.doc.add_box(40, 30, 20)
    face = min(body.faces, key=lambda f: f.normal[1])
    win.viewport.surface_texture_requested.emit(face)
    dlg = win.inspector.current_tool_dlg
    assert dlg.kind() == "honeycomb" and dlg.faces == [plane_face_ref(face)] and dlg.body_id == body.body_id
    assert "cells will be cut" in dlg.lbl_info.text()


def test_a_body_from_the_tree_starts_on_wavy_slices_with_that_body(win):
    win.doc.add_box(20, 20, 20)
    body = win.doc.add_box(40, 30, 20)
    win.browser.surface_texture_requested.emit(body.body_id)
    dlg = win.inspector.current_tool_dlg
    assert dlg.kind() == "wavy_slices" and dlg.target_body_id() == body.body_id
    assert win.viewport.preview_mesh is not None and not win.doc.bodies[body.body_id].visible
    assert not win.viewport.plane_pick_mode


def test_help_finds_the_tool_under_all_the_old_names():
    words = help_topics.MORE["surface_texture"][1].split()
    for word in ("honeycomb", "knurl", "wavy", "voronoi", "slice"):
        assert word in words
    assert not OLD & set(help_topics.MORE)


def test_the_panel_shows_only_the_chosen_type_also_when_docked(win):
    win.doc.add_box(20, 20, 20)
    win.resize(1400, 900)
    win.show()
    win.prompt_surface_texture()
    dlg = win.inspector.current_tool_dlg
    QTest.qWait(50)
    cells, knurl, wavy = dlg.pages["honeycomb"], dlg.pages["knurl"], dlg.pages["wavy_slices"]
    assert cells.isVisible() and not knurl.isVisible() and not wavy.isVisible()
    assert not cells.spins["seed"].isVisible()
    cells.cmb_shape.setCurrentText("Voronoi")
    assert cells.spins["seed"].isVisible() and cells.spins["randomness"].isVisible()
    cells.cmb_shape.setCurrentText("Hexagon")
    assert not cells.spins["seed"].isVisible()

    dlg.cmb_kind.setCurrentText("Knurl")
    assert knurl.isVisible() and not cells.isVisible() and win.viewport.plane_pick_mode
    assert not dlg.target_row.isVisible()
    dlg.cmb_kind.setCurrentText("Wavy Slices")
    assert wavy.isVisible() and dlg.target_row.isVisible() and not dlg.btn_clear.isVisible()
    assert not win.viewport.plane_pick_mode
    dlg.cmb_kind.setCurrentText("Cells")
    assert win.viewport.plane_pick_mode


def test_switching_to_knurl_keeps_only_outer_round_faces(win):
    body = win.doc.add_cylinder(R, H)
    win.prompt_surface_texture()
    dlg = win.inspector.current_tool_dlg
    plane = {"kind": "plane", "normal": [0, 0, 1], "origin": [0, 0, H]}
    win.viewport.offset_face_picked.emit(plane, body.body_id)
    win.viewport.offset_face_picked.emit(dict(ROUND), body.body_id)
    assert len(dlg.faces) == 2
    dlg.cmb_kind.setCurrentText("Knurl")
    assert [f["kind"] for f in dlg.faces] == ["cylinder"]
    win.viewport.offset_face_picked.emit(plane, body.body_id)
    assert len(dlg.faces) == 1 and "outer round" in win.status_label.text()


def test_each_type_makes_its_own_step_and_the_panel_remembers_the_last_type(win):
    pin = win.doc.add_cylinder(R, H).body_id
    box = win.doc.add_box(40, 30, 20).body_id
    win.prompt_surface_texture()
    dlg = win.inspector.current_tool_dlg
    dlg.cmb_kind.setCurrentText("Knurl")
    dlg.page.cmb_pattern.setCurrentText("Straight")
    win.viewport.offset_face_picked.emit(dict(ROUND), pin)
    dlg.accept()
    QApplication.processEvents()
    assert win.doc.timeline.features[-1].feature_type == "knurl"
    assert win.doc.bodies[pin].visible

    win.prompt_surface_texture()
    dlg = win.inspector.current_tool_dlg
    assert dlg.kind() == "knurl"
    dlg.cmb_kind.setCurrentText("Cells")
    face = min(win.doc.bodies[box].faces, key=lambda f: f.normal[1])
    win.viewport.offset_face_picked.emit(plane_face_ref(face), box)
    dlg.accept()
    QApplication.processEvents()
    feat = win.doc.timeline.features[-1]
    assert feat.feature_type == "honeycomb" and feat.name == "Cells 1" and feat.cells > 0

    volume = win.doc.bodies[box].manifold.volume()
    win.doc.undo()
    assert win.doc.bodies[box].manifold.volume() > volume


def test_a_step_is_edited_in_the_same_panel_with_its_type_locked():
    QApplication.instance() or QApplication([])
    from omacad.model.document import Document
    doc = Document()
    body = doc.add_cylinder(R, H)
    feat = doc.add_knurl(body.body_id, [dict(ROUND)], pattern="straight", pitch=2.0, depth=0.5)
    assert can_edit(feat)
    dlg = SurfaceTextureDialog(doc, feature=feat)
    assert dlg.kind() == "knurl" and not dlg.cmb_kind.isEnabled()
    assert dlg.faces == feat.faces and dlg.params()["pitch"] == 2.0 and dlg.params()["pattern"] == "straight"
    assert not dlg.btn_clear.isVisibleTo(dlg) and not dlg.target_row.isVisibleTo(dlg)
    dlg.deleteLater()

    wavy = doc.add_wavy_slices(body.body_id, waves=5, amplitude=1.0)
    dlg = SurfaceTextureDialog(doc, feature=wavy)
    assert dlg.kind() == "wavy_slices" and dlg.params()["waves"] == 5 and dlg.target_body_id() == body.body_id
    dlg.deleteLater()


def test_the_neighbouring_commands_keep_their_longer_help():
    assert {"pattern", "offset_plane", "fillet", "chamfer", "shell", "offset_face"} <= set(help_topics.MORE)
