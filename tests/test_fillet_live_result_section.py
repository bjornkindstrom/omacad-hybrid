"""Rapport 20261025-120548: Fillet/Chamfer drew its live result in place of the body without the section view's cut,
so the section seemed to switch off while edges were picked. The result is now cut like the bodies, with its own
cut face, and the section's own cut comes back when the tool ends."""
import pytest
from PySide6.QtWidgets import QApplication
from shapely.geometry import Polygon

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()


def _cut_area(vp, bid):
    cap = next(c for c in vp.section["caps"] if c["body_id"] == bid)
    rings = [Polygon(p) for p in cap["polys"]]
    return sum(r.area if r.exterior.is_ccw else -r.area for r in rings)


def test_chamfer_result_is_cut_by_the_section_view(win):
    body = win.doc.add_box(30, 20, 10)
    x0, y0, z0, x1, y1, z1 = body.manifold.bounding_box()
    vp = win.viewport
    win.doc.add_section(((x0 + x1) / 2, 0, 0), (1, 0, 0), 0.0)        # a saved section, turned on
    whole = vp.section["meshes"][body.body_id]
    assert abs(_cut_area(vp, body.body_id) - 20 * 10) < 1e-6

    win.prompt_round_edges("chamfer")
    dlg = win._round_dlg
    dlg.spn_size.setValue(2.0)
    edge = next(e for e in body.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - z1) < 1e-6 and abs(e.p1[2] - z1) < 1e-6 and abs(e.p0[0] - e.p1[0]) > 1)
    vp.selected_edges = [edge]
    vp.edges_selection_changed.emit()
    assert vp.section is not None and body.body_id in vp.display_override
    cut = vp.section["meshes"][body.body_id]
    assert len(cut.vertices) > len(whole.vertices) and max(cut.vertices[:, 0]) <= (x0 + x1) / 2 + 1e-6
    assert abs(_cut_area(vp, body.body_id) - (20 * 10 - 2 * 2 / 2)) < 1e-6     # the bevel shows in the cut face

    dlg.reject()
    QApplication.processEvents()
    assert vp.section is not None and len(vp.section["meshes"][body.body_id].vertices) == len(whole.vertices)
    assert abs(_cut_area(vp, body.body_id) - 20 * 10) < 1e-6
