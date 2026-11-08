"""The panel rule (Björn 2026-11-08): docked tool panels group short values two per row to save room, but never cut a
label, a choice or a check box's text."""
import pytest
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QLabel, QWidget

from omacad.ui.dialogs.base import auto_pair_rows
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    yield w
    w.close()                     # no window left open for the tests after these (they draw and compare pixels)
    w.deleteLater()
    QApplication.processEvents()


def _cut(dlg):
    QApplication.processEvents()
    bad = []
    for kind in (QLabel, QComboBox, QAbstractSpinBox, QCheckBox):
        for w in dlg.findChildren(kind):
            if not w.isVisible() or (isinstance(w, QLabel) and w.wordWrap()):
                continue
            if w.width() + 1 < w.minimumSizeHint().width():
                bad.append((type(w).__name__, w.text() if hasattr(w, "text") and not isinstance(w, QAbstractSpinBox)
                            else "", w.width(), w.minimumSizeHint().width()))
    return bad


@pytest.mark.parametrize("prompt", ["prompt_jar", "prompt_box_row", "prompt_star_brackets", "prompt_cylinder",
                                    "prompt_box", "prompt_thread", "prompt_cone", "prompt_prism"])
def test_no_text_is_cut_in_tool_panels(win, prompt):
    getattr(win, prompt)()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None
    assert _cut(dlg) == []
    dlg.reject()


def test_script_panel_pairs_numbers_and_keeps_text_whole(win, monkeypatch):
    from omacad.scripting import folder as sf
    from omacad.scripting.loader import read_info, resolve_values
    from omacad.ui.scripts_ui import ScriptParamsDialog
    info = read_info(sf.EXAMPLES / "jar_with_lid.py")
    dlg = ScriptParamsDialog(info, resolve_values(info.params, {}), win)
    win.dock(dlg)
    pairs = [c for c in dlg.findChildren(QWidget) if getattr(c, "omacad_pair", False)]
    assert len(pairs) >= 4                                   # the jar's 12 numbers take about half the rows
    assert _cut(dlg) == []
    auto_pair_rows(dlg)                                      # a second dock changes nothing
    assert len([c for c in dlg.findChildren(QWidget) if getattr(c, "omacad_pair", False)]) == len(pairs)
    dlg.reject()


def test_a_pair_that_got_too_wide_is_split_when_docked(win):
    """A dialog pairs its fields in __init__, before the panel's style (other fonts on another machine can make a
    choice wider than half the panel): docking gives such fields their own rows instead of cutting them."""
    from PySide6.QtWidgets import QFormLayout
    from omacad.ui.dialogs.base import BaseFeatureDialog
    dlg = BaseFeatureDialog("Pairs")
    form = QFormLayout()
    a, b = QComboBox(), QComboBox()
    a.addItem("Fillet")
    b.addItem("Chamfer")
    form.addRow("Outer:", a)
    form.addRow("Inner:", b)
    dlg.main_layout.addLayout(form)
    dlg.pair_form_rows(form, [(a, b)])
    assert any(getattr(c, "omacad_pair", False) for c in dlg.findChildren(QWidget))
    b.addItem("Chamfer, two distances")      # now wider than half the panel
    win.dock(dlg)
    assert not any(getattr(c, "omacad_pair", False) for c in dlg.findChildren(QWidget))
    assert _cut(dlg) == []
    dlg.reject()
