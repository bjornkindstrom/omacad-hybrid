"""A thread shorter than its cylinder can sit at the top end (or a gap from either end), not only at the bottom."""
import pytest

from omacad.model.document import Document


def _cylinder_thread(anchor, gap=0.0, length=10.0):
    doc = Document()
    doc.add_cylinder(10.0, 40.0)                       # radius 10, height 40, standing on z = 0
    cyl = next(iter(doc.bodies.values()))
    doc.add_thread(diameter=20.0, pitch=2.5, length=length, target_body_id=cyl.body_id, operation="join",
                   plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0],
                   anchor=anchor, anchor_gap=gap, host_length=40.0)
    return doc, doc.timeline.features[-1]


def _thread_z_range(doc, feat):
    solid = feat.build_solid()
    box = solid.bounding_box()
    return box[2], box[5]


@pytest.mark.parametrize("anchor,gap,length,lo", [("bottom", 0.0, 10.0, 0.0), ("bottom", 5.0, 10.0, 5.0),
                                                  ("top", 0.0, 10.0, 30.0), ("top", 4.0, 10.0, 26.0)])
def test_start_offset(anchor, gap, length, lo):
    doc, feat = _cylinder_thread(anchor, gap, length)
    assert feat.start_offset() == pytest.approx(lo)
    z0, z1 = _thread_z_range(doc, feat)
    assert z0 >= lo - 1e-3 and z1 <= lo + length + 0.5     # (the lead-in/out never leaves the length by more than a bit)
    assert z0 == pytest.approx(lo, abs=1.5) and z1 > lo + length - 1.5


def test_top_thread_longer_than_cylinder_falls_back_to_bottom():
    doc, feat = _cylinder_thread("top", 0.0, 60.0)
    assert feat.start_offset() == 0.0


def test_without_a_cylinder_nothing_moves():
    doc = Document()
    doc.add_thread(diameter=10.0, pitch=2.0, length=10.0)
    feat = doc.timeline.features[-1]
    assert feat.host_length is None and feat.start_offset() == 0.0


def test_saved_and_reloaded_keeps_the_anchor():
    from omacad.io.exporter import Exporter
    doc, feat = _cylinder_thread("top", 3.0)
    d2 = Document()
    Exporter.apply_dict(d2, Exporter.document_to_dict(doc))
    f2 = d2.timeline.features[-1]
    assert (f2.anchor, f2.anchor_gap, f2.host_length) == ("top", 3.0, 40.0)
    assert f2.start_offset() == pytest.approx(feat.start_offset())


def test_edit_moves_the_thread():
    doc, feat = _cylinder_thread("bottom")
    idx = len(doc.timeline.features) - 1
    assert doc.edit_feature(idx, anchor="top")
    assert doc.timeline.features[idx].start_offset() == pytest.approx(30.0)


def test_dialog_values_carry_the_anchor():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.dialogs import ThreadDialog
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_cylinder(10.0, 40.0)
    dlg = ThreadDialog(doc)
    assert not dlg.cmb_anchor.isEnabled()
    dlg.apply_cylinder_info({"diameter": 20.0, "length": 40.0, "is_internal": False, "origin": [0, 0, 0], "axis": [0, 0, 1]})
    assert dlg.cmb_anchor.isEnabled()
    dlg.cmb_anchor.setCurrentIndex(dlg.cmb_anchor.findData("top"))
    dlg.spn_length.setValue(10.0)
    v = dlg.get_values()
    assert (v["anchor"], v["host_length"]) == ("top", 40.0)
