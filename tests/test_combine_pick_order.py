"""Combine: with nothing selected, the first body clicked is the target and the next the tool (like Fusion).

Report: a lid cut by the can (Keep tool bodies) cut the can instead, because clicks in the view could only
ever change the tool, so the target stayed the first body in the list.
"""
import numpy as np
from PySide6.QtWidgets import QApplication


def _can_and_lid(doc):
    can = doc.add_cylinder(20, 40, name="Burk")
    lid = doc.add_cylinder(20, 10, name="Locket", plane_origin=[0, 0, 35], plane_normal=[0, 0, 1],
                           plane_u=[1, 0, 0], plane_v=[0, 1, 0])
    doc.selected_body_ids = []
    return can.body_id, lid.body_id


def test_first_click_is_the_target_then_the_tool():
    from omacad.model.document import Document
    from omacad.ui.dialogs import CombineDialog

    QApplication.instance() or QApplication([])
    doc = Document()
    can_id, lid_id = _can_and_lid(doc)
    can_volume, lid_volume = doc.bodies[can_id].manifold.volume(), doc.bodies[lid_id].manifold.volume()
    dlg = CombineDialog(doc)
    assert dlg.picking_target()
    dlg.select_body(lid_id)
    dlg.select_body(can_id)
    dlg.cmb_op.setCurrentIndex(1)
    dlg.chk_keep_tool.setChecked(True)
    target_id, tool_id, op, keep = dlg.get_values()
    assert (target_id, tool_id, op, keep) == (lid_id, can_id, "cut", True)

    doc.combine_bodies(target_id, tool_id, op, keep)
    assert np.isclose(doc.bodies[can_id].manifold.volume(), can_volume)            # the can is untouched
    assert np.isclose(doc.bodies[lid_id].manifold.volume(), lid_volume / 2)        # 5 of the lid's 10 mm overlap


def test_a_preselected_target_takes_clicks_as_the_tool():
    from omacad.model.document import Document
    from omacad.ui.dialogs import CombineDialog

    QApplication.instance() or QApplication([])
    doc = Document()
    can_id, lid_id = _can_and_lid(doc)
    dlg = CombineDialog(doc, preselected_target_id=lid_id)
    assert not dlg.picking_target()
    dlg.select_body(lid_id)          # clicking the target again changes nothing
    dlg.select_body(can_id)
    assert dlg.get_values()[:2] == (lid_id, can_id)


def test_new_combine_previews_the_result_once_the_target_is_picked():
    from omacad.ui.main_window import MainWindow
    from omacad.ui.dialogs import CombineDialog

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    doc = win.doc
    can_id, lid_id = _can_and_lid(doc)
    previews = []
    win.viewport.set_preview = lambda solid, *a, **k: previews.append(solid)
    win.prompt_combine()
    dlg = next(w for w in app.allWidgets() if isinstance(w, CombineDialog) and w.window() is win)
    assert previews[-1] is None                  # nothing to show while the target is not picked
    dlg.select_body(lid_id)
    dlg.cmb_op.setCurrentIndex(1)
    assert np.isclose(previews[-1].volume(), doc.bodies[lid_id].manifold.volume() / 2)
    assert not doc.bodies[lid_id].visible and doc.bodies[can_id].visible
    dlg.reject()
    assert doc.bodies[lid_id].visible and previews[-1] is None
    win.close()
