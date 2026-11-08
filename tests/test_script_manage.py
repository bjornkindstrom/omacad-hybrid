"""Scripts: pictures for the AI (files, pasted, from the 3D view) reach the instructions; rename (right-click in the
tool menus or in Scripts) changes only the NAME and keeps trust; only the user's own scripts can be deleted."""
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QEvent
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from omacad.scripting import folder as sfolder
from omacad.scripting import prompt as sprompt
from omacad.scripting.loader import read_info
from omacad.ui.settings import get_settings


def _img(color="red"):
    img = QImage(40, 30, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


@pytest.fixture(scope="module")
def win():
    QApplication.instance() or QApplication([])
    from omacad.ui.main_window import MainWindow
    return MainWindow()


@pytest.fixture
def folder(tmp_path, win):
    get_settings().set("scripts_folder", str(tmp_path / "scripts"))
    return win.scripts_folder()


def test_rename_changes_only_the_name(tmp_path):
    p = tmp_path / "a.py"
    p.write_text('"""Doc."""\nNAME = "Old"\nPARAMS = []\n\ndef run(ctx, params):\n    pass\n', encoding="utf-8")
    sfolder.rename_script(p, "  New   name ")
    assert read_info(p).name == "New name" and p.read_text(encoding="utf-8").count("NAME") == 1
    q = tmp_path / "b.py"
    q.write_text('"""Doc\nmore."""\nimport math\n\ndef run(ctx, params):\n    pass\n', encoding="utf-8")
    sfolder.rename_script(q, "Given")
    assert read_info(q).name == "Given" and q.read_text(encoding="utf-8").splitlines()[2] == "NAME = 'Given'"
    with pytest.raises(ValueError):
        sfolder.rename_script(q, "  ")


def test_only_own_scripts_can_be_deleted(folder):
    with pytest.raises(ValueError):
        sfolder.delete_script(folder / "jar_with_lid.py")
    own = folder / "mine.py"
    own.write_text("def run(ctx, params):\n    pass\n", encoding="utf-8")
    (folder / "mine.check.txt").write_text("RESULT: OK\n", encoding="utf-8")
    assert sfolder.delete_script(own)
    assert not own.exists() and not (folder / "mine.check.txt").exists()
    assert (folder / "jar_with_lid.py").exists()


def test_pictures_are_saved_and_named_in_the_instructions(tmp_path):
    src = tmp_path / "sketch.JPG"
    _img("blue").save(str(src), "JPG")
    saved = sfolder.save_images([str(src), _img()], tmp_path, "jar_ribbed.py")
    assert [p.name for p in saved] == ["1.jpg", "2.png"] and all(p.exists() for p in saved)
    assert saved[0].parent.parent == tmp_path / ".omacad-ai" / "images"
    agent = sprompt.build_modify_prompt("Ribbed lid", tmp_path, sfolder.EXAMPLES / "jar_with_lid.py",
                                        tmp_path / "jar_ribbed.py", True, images=saved)
    assert "## Pictures from the user" in agent and all(str(p) in agent for p in saved)
    chat = sprompt.build_prompt("A box", tmp_path, "box.py", False, images=saved)
    assert "attaches 2 pictures" in chat
    assert "Pictures from the user" not in sprompt.build_prompt("A box", tmp_path, "box.py", True)


def test_ai_dialog_takes_pictures_from_files_paste_and_the_3d_view(win, folder, tmp_path):
    from omacad.ui.scripts_ui import AiScriptDialog
    f = tmp_path / "photo.png"
    _img("green").save(str(f))
    dlg = AiScriptDialog(win, folder, None, grab_view=lambda: _img("white"))
    assert not dlg.lst_images.isVisibleTo(dlg) and dlg.btn_grab_view.isVisibleTo(dlg)
    dlg.add_image(str(f))
    mime = QMimeData()
    mime.setImageData(_img("yellow"))
    assert dlg.edt_wish.canInsertFromMimeData(mime)
    dlg.edt_wish.insertFromMimeData(mime)                  # Ctrl+V of a picture: not into the text
    dlg.btn_grab_view.click()
    assert dlg.edt_wish.toPlainText() == "" and dlg.lst_images.count() == 3
    imgs = dlg.images()
    assert imgs[0] == str(f) and isinstance(imgs[1], QImage) and imgs[2].pixelColor(0, 0) == QColor("white")
    dlg.lst_images.setCurrentRow(0)
    dlg._remove_images()
    assert dlg.lst_images.count() == 2 and isinstance(dlg.images()[0], QImage)
    text = QMimeData()
    text.setText("plain words")
    dlg.edt_wish.insertFromMimeData(text)
    assert dlg.edt_wish.toPlainText() == "plain words"
    dlg.reject()


def test_rename_keeps_trust_and_delete_forgets_the_script(win, folder):
    own = folder / "mine.py"
    own.write_text('NAME = "Mine"\n\ndef run(ctx, params):\n    ctx.box(1, 1, 1)\n', encoding="utf-8")
    s = get_settings()
    s.set("trusted_scripts", sfolder.trust(dict(s.get("trusted_scripts") or {}), own))
    s.set("script_values", {str(own.resolve()): {"__name__": "x"}})
    assert win.rename_user_script(own, "Better")
    assert read_info(own).name == "Better"
    assert sfolder.is_trusted(s.get("trusted_scripts"), own)          # Omacad's own edit: still trusted
    told = []
    from PySide6.QtWidgets import QMessageBox
    orig = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: told.append(a[1]))
    try:
        assert not win.delete_user_script(folder / "gear_generator.py", confirm=False)
    finally:
        QMessageBox.information = orig
    assert told == ["Delete Script"]
    assert (folder / "gear_generator.py").exists()
    assert win.delete_user_script(own, confirm=False) and not own.exists()
    assert str(own.resolve()) not in (s.get("trusted_scripts") or {})
    assert str(own.resolve()) not in (s.get("script_values") or {})


def test_right_click_in_a_tool_menu_manages_the_script(win, folder, monkeypatch):
    from omacad.ui import script_menus
    copy = sprompt.make_copy(folder / "jar_with_lid.py", folder, "jar_tall.py", "taller")
    menu = win.ribbon._family_menu(win, "jar")
    menu.aboutToShow.emit()
    acts = [a for a in menu.actions() if a.data()]
    assert [Path(a.data()).name for a in acts] == ["jar_with_lid.py", "jar_tall.py"]
    ran, shown = [], []
    win.ribbon.script_run_requested.connect(lambda p: ran.append(p))
    monkeypatch.setattr(script_menus.ScriptRightClick, "show_for", lambda self, p, at: shown.append(Path(p).name))
    menu.popup(win.mapToGlobal(win.rect().center()))
    QApplication.processEvents()
    acts = [a for a in menu.actions() if a.data()]                    # filled again as it opened
    pos = QPointF(menu.actionGeometry(acts[1]).center())
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(menu, QMouseEvent(kind, pos, menu.mapToGlobal(pos), Qt.MouseButton.RightButton,
                                                 Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier))
    menu.close()
    assert shown == ["jar_tall.py"] and ran == []                       # right-click never runs it
    got = []
    monkeypatch.setattr(win, "prompt_modify_script", lambda family="", base=None: got.append((family, Path(base).name)))
    win.manage_user_script("modify", str(copy))
    monkeypatch.setattr(win, "rename_user_script", lambda p: got.append(("rename", Path(p).name)))
    win.manage_user_script("rename", str(copy))
    assert got == [("jar", "jar_tall.py"), ("rename", "jar_tall.py")]
