"""Fillet/Chamfer panel: like Fusion the view shows the finished body (not loose tool slivers) while edges are
picked, the chamfer type rows follow the choice, and OK stores the chamfer type on the step."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()


def test_live_result_and_chamfer_types(win):
    body = win.doc.add_box(30, 20, 10)
    win.prompt_round_edges("chamfer")
    dlg = win._round_dlg
    vp = win.viewport
    assert not dlg.spn_size2.isVisibleTo(dlg) and not dlg.chk_flip.isVisibleTo(dlg)
    top = body.manifold.bounding_box()[5]
    edge = next(e for e in body.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - top) < 1e-6 and abs(e.p1[2] - top) < 1e-6 and abs(e.p0[0] - e.p1[0]) > 1)
    vp.selected_edges = [edge]
    vp.edges_selection_changed.emit()
    shown = vp.display_override[body.body_id]
    assert len(shown.vertices) > len(body.render_mesh.vertices)    # the bevelled body, drawn in place of the box
    assert vp.preview_mesh is None
    dlg.cmb_chamfer.setCurrentIndex(1)       # two distances
    assert dlg.spn_size2.isVisibleTo(dlg) and dlg.chk_flip.isVisibleTo(dlg) and not dlg.spn_angle.isVisibleTo(dlg)
    dlg.spn_size.setValue(4.0)
    dlg.spn_size2.setValue(1.5)
    dlg.chk_chain.setChecked(False)
    assert vp.edge_tangent_chain is False
    dlg.accept()
    QApplication.processEvents()
    feat = win.doc.timeline.features[-1]
    assert (feat.kind, feat.chamfer_type, feat.size, feat.size2) == ("chamfer", "two", 4.0, 1.5)
    assert vp.display_override is None and vp.edge_tangent_chain is True
    vol = next(iter(win.doc.bodies.values())).manifold.volume()
    assert abs(vol - (30 * 20 * 10 - 0.5 * 4.0 * 1.5 * 30)) < 1e-6
