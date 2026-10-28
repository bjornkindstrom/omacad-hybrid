"""Sketch constraints sit in one Constraints ▾ dropdown with full-size icons when grouped."""
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMenu, QToolButton

from omacad.ui.main_window import MainWindow
from omacad.ui.ribbon import Ribbon


def test_grouped_constraints_are_one_dropdown_that_emits_each_kind():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    row = QHBoxLayout()
    win.ribbon._build_constraints(row, True, 1.0)
    buttons = [row.itemAt(i).widget() for i in range(row.count())]
    assert len(buttons) == 1
    btn = buttons[0]
    assert isinstance(btn, QToolButton) and btn.text().startswith("Constraints")
    menu = btn.menu()
    assert isinstance(menu, QMenu)
    actions = [a for a in menu.actions() if not a.isSeparator()]
    assert [a.text() for a in actions] == [label for _c, label, _i, _t in Ribbon.CONSTRAINTS]
    assert all(not a.icon().isNull() for a in actions)
    received = []
    win.ribbon.constraint_clicked.connect(received.append)
    actions[0].trigger()
    actions[-1].trigger()
    assert received == [Ribbon.CONSTRAINTS[0][0], Ribbon.CONSTRAINTS[-1][0]]
    win.close()


def test_ungrouped_constraints_stay_one_button_each():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    row = QHBoxLayout()
    win.ribbon._build_constraints(row, False, 1.0)
    assert row.count() == len(Ribbon.CONSTRAINTS)
    win.close()
