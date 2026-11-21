"""Tests for script group Easy Mode settings in the Object Browser (#242)."""
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.scripting.runner import run_script
from omacad.ui.history_delegate import ExprLineEdit, HistoryDelegate, apply_dimension
from omacad.ui.main_window import MainWindow


SCRIPT_WITH_GROUP = '''NAME = "Box Script"
PARAMS = [
    {"name": "w", "type": "float", "default": 20.0, "min": 5.0, "max": 200.0, "unit": "mm", "label": "Width"},
    {"name": "h", "type": "float", "default": 10.0, "min": 2.0, "label": "Height"},
    {"name": "count", "type": "int", "default": 1, "min": 1, "max": 5, "label": "Count"},
    {"name": "tall", "type": "bool", "default": False, "label": "Tall"},
    {"name": "mode", "type": "choice", "default": "single", "choices": ["single", "double"], "label": "Mode"},
    {"name": "tag", "type": "str", "default": "abc", "label": "Tag"},
]
EASY_PARAMS = ["tag", "w", "count", "tall", "mode"]

def run(ctx, params):
    if params["w"] > 150:
        raise ValueError("Too wide for test")
    bodies = []
    for i in range(params["count"]):
        hz = params["h"] * (2 if params["tall"] else 1)
        if params["mode"] == "double":
            hz *= 1.5
        b = ctx.box(params["w"], 12.0, hz, at=(i * (params["w"] + 2), 0, 0), name=f"{params['tag']}_{i}")
        bodies.append(b)
    ctx.group("My Script Group", bodies)
'''

SCRIPT_NO_GROUP = '''NAME = "Auto Group"
PARAMS = [
    {"name": "size", "type": "float", "default": 15.0, "unit": "mm"},
]

def run(ctx, params):
    ctx.box(params["size"], params["size"], params["size"])
'''

SCRIPT_EMPTY_EASY = '''NAME = "Hidden Easy"
PARAMS = [{"name": "size", "type": "float", "default": 12.0}]
EASY_PARAMS = []

def run(ctx, params):
    ctx.box(params["size"], params["size"], params["size"])
'''


def _find_items(tree, role_type):
    out = []
    stack = [tree.topLevelItem(0)]
    while stack:
        it = stack.pop(0)
        if it is None:
            continue
        data = it.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and data[0] == role_type:
            out.append(it)
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return out


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_script_group_easy_params_order_and_no_group_auto_group(tmp_path, app):
    s1 = tmp_path / "with_group.py"
    s1.write_text(SCRIPT_WITH_GROUP, encoding="utf-8")
    s2 = tmp_path / "no_group.py"
    s2.write_text(SCRIPT_NO_GROUP, encoding="utf-8")
    s3 = tmp_path / "empty_easy.py"
    s3.write_text(SCRIPT_EMPTY_EASY, encoding="utf-8")

    win = MainWindow()
    run_script(win.doc, s1)
    run_script(win.doc, s2)
    run_script(win.doc, s3)
    win.browser.refresh_tree()

    settings_nodes = _find_items(win.browser.tree, "group_settings")
    # s1 and s2 have ⚙️ Settings; s3 has EASY_PARAMS = [] so it is hidden
    assert len(settings_nodes) == 2

    s1_settings = settings_nodes[0]
    labels = [s1_settings.child(i).text(0) for i in range(s1_settings.childCount())]
    assert [lbl.split(":")[0] for lbl in labels] == ["Tag", "Width", "Count", "Tall", "Mode"]
    assert "Height" not in "\n".join(labels)

    # s2 had EASY_PARAMS = None -> all PARAMS shown
    s2_settings = settings_nodes[1]
    assert s2_settings.childCount() == 1
    assert s2_settings.child(0).text(0).startswith("Size: 15 mm")


def test_edit_all_param_types_undo_redo_and_preserves_group(tmp_path, app):
    s1 = tmp_path / "with_group.py"
    s1.write_text(SCRIPT_WITH_GROUP, encoding="utf-8")

    doc = Document()
    run_script(doc, s1)
    assert len(doc.object_groups) == 1
    gid = doc.object_groups[0]["id"]
    doc.object_groups[0]["name"] = "Custom Renamed"
    doc.object_groups[0]["visible"] = False
    assert doc.is_script_group(gid)

    # float
    assert apply_dimension(doc, "group_param", (gid, "w"), "40")
    assert doc.script_group_params(gid)["w"] == 40.0
    assert doc.object_groups[0]["id"] == gid
    assert doc.object_groups[0]["name"] == "Custom Renamed"
    assert doc.object_groups[0]["visible"] is False

    # int
    assert apply_dimension(doc, "group_param", (gid, "count"), "3")
    assert doc.script_group_params(gid)["count"] == 3
    assert len(doc.bodies) == 3

    # bool
    assert apply_dimension(doc, "group_param", (gid, "tall"), "1")
    assert doc.script_group_params(gid)["tall"] is True

    # choice
    assert apply_dimension(doc, "group_param", (gid, "mode"), "double")
    assert doc.script_group_params(gid)["mode"] == "double"

    # str
    assert apply_dimension(doc, "group_param", (gid, "tag"), "boxxy")
    assert doc.script_group_params(gid)["tag"] == "boxxy"
    assert any(b.name == "boxxy_0" for b in doc.bodies.values())

    # Undo & redo
    assert doc.undo()
    assert doc.script_group_params(gid)["tag"] == "abc"
    assert doc.redo()
    assert doc.script_group_params(gid)["tag"] == "boxxy"


def test_delegate_editor_types_for_script_params(tmp_path, app):
    s1 = tmp_path / "with_group.py"
    s1.write_text(SCRIPT_WITH_GROUP, encoding="utf-8")

    win = MainWindow()
    run_script(win.doc, s1)
    win.browser.refresh_tree()

    param_rows = _find_items(win.browser.tree, "group_param")
    delegate = HistoryDelegate(win.browser)

    for row in param_rows:
        idx = win.browser.tree.indexFromItem(row, 0)
        editor = delegate.createEditor(win.browser.tree, None, idx)
        _, (_, key) = row.data(0, Qt.ItemDataRole.UserRole)
        if key == "tag":
            assert type(editor) is QLineEdit
        elif key == "mode":
            assert isinstance(editor, QComboBox)
            assert [editor.itemText(i) for i in range(editor.count())] == ["single", "double"]
        else:
            assert isinstance(editor, ExprLineEdit)


def test_save_load_round_trip_and_error_rollback(tmp_path):
    s1 = tmp_path / "with_group.py"
    s1.write_text(SCRIPT_WITH_GROUP, encoding="utf-8")

    doc = Document()
    run_script(doc, s1)
    gid = doc.object_groups[0]["id"]
    bodies_before = set(doc.bodies.keys())

    # Out-of-range min/max -> ValueError + rollback
    with pytest.raises(ValueError):
        doc.edit_script_group_param(gid, "w", "2")
    assert doc.script_group_params(gid)["w"] == 20.0
    assert set(doc.bodies.keys()) == bodies_before

    # ScriptRunError inside run() -> ValueError + rollback
    with pytest.raises(ValueError, match="Too wide for test"):
        doc.edit_script_group_param(gid, "w", "180")
    assert doc.script_group_params(gid)["w"] == 20.0
    assert set(doc.bodies.keys()) == bodies_before

    # Invalid choice -> ValueError + rollback
    with pytest.raises(ValueError):
        doc.edit_script_group_param(gid, "mode", "triple")
    assert doc.script_group_params(gid)["mode"] == "single"

    # Save & load round-trip
    save_file = tmp_path / "project.omacad"
    Exporter.save_project(doc, str(save_file))
    loaded = Exporter.load_project(str(save_file))
    assert loaded.is_script_group(gid)
    assert loaded.edit_script_group_param(gid, "w", "35")
    assert loaded.script_group_params(gid)["w"] == 35.0

    # Missing script file -> ValueError + rollback
    s1.unlink()
    with pytest.raises(ValueError, match="Script file not found"):
        loaded.edit_script_group_param(gid, "w", "50")
    assert loaded.script_group_params(gid)["w"] == 35.0


def test_edit_script_with_combine_leaves_no_orphaned_tools(tmp_path):
    script = tmp_path / "combine_script.py"
    script.write_text('''NAME = "Combine Test"
PARAMS = [{"name": "w", "type": "float", "default": 20.0}]

def run(ctx, params):
    a = ctx.box(params["w"], 20.0, 10.0)
    b = ctx.box(10.0, 10.0, 20.0, at=(2.0, 2.0, 0.0))
    res = ctx.combine(a, b, "cut")
    ctx.group("Combined", [res])
''', encoding="utf-8")
    doc = Document()
    run_script(doc, script)
    feat_count_before = len(doc.timeline.features)
    gid = doc.object_groups[0]["id"]
    assert doc.edit_script_group_param(gid, "w", "30")
    assert len(doc.timeline.features) == feat_count_before
    assert len(doc.bodies) == 1

