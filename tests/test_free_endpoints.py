import pytest
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
from omacad.ui.viewport.viewport import Viewport3D
from omacad.model.document import Document

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

def test_free_endpoints_dot_and_join(viewport):
    doc = viewport.doc
    sk = doc.start_sketch("XY")
    l1 = sk.add_line((0, 0), (20, 0))
    l2 = sk.add_line((30, 0), (50, 0))

    # Both lines have 2 free ends
    free = viewport._free_endpoints()
    assert len(free) == 4

    # Connect l1.p2 with l2.p1
    l1.p2 = l2.p1
    free_after = viewport._free_endpoints()
    assert len(free_after) == 2
    pts = {f[2] for f in free_after}
    assert (0.0, 0.0) in pts
    assert (50.0, 0.0) in pts

    # Picking free endpoint
    plane = sk.plane
    scr = viewport.world_to_screen(plane.uv_to_world(0.0, 0.0))
    assert scr is not None
    picked = viewport._pick_free_endpoint(scr[0], scr[1])
    assert picked is not None
    assert picked["entity"].entity_id == l1.entity_id
    assert picked["point_name"] == "p1"
