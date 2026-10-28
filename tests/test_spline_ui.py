import pytest
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
from omacad.ui.viewport.viewport import Viewport3D
from omacad.model.document import Document
from omacad.model.sketch_entities import SketchSpline

@pytest.fixture
def viewport():
    if QApplication.instance() is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        QSurfaceFormat.setDefaultFormat(fmt)
        QApplication([])
    doc = Document()
    vp = Viewport3D(doc)
    vp.resize(800, 600)
    return vp

def test_spline_handle_picking_and_insert(viewport):
    doc = viewport.doc
    sk = doc.start_sketch("XY")
    sp = sk.add_spline([(0, 0), (10, 20), (30, 0)])
    viewport.selected_entities = {sp.entity_id}

    plane = sk.plane
    fit_scr = viewport.world_to_screen(plane.uv_to_world(10, 20))
    assert fit_scr is not None
    handle = viewport._pick_spline_handle(fit_scr[0], fit_scr[1])
    assert handle is not None
    assert handle["entity"].entity_id == sp.entity_id

    uv = (5.0, 10.0)
    idx = sk.insert_spline_point(sp.entity_id, uv)
    assert len(sp.points) == 4
