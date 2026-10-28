"""Shell on a cylinder: its side facets are one curved face but many planes; every one must be offset."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.features.shell import ShellFeature
from omacad.model import quality


def _cylinder():
    return Document().add_cylinder(20, 40).manifold


def _area(r):
    n = quality.circle_segments()
    return n/2*math.sin(2*math.pi/n)*r**2


def _offset(t):
    """Radius whose polygon lies t (normal to the facets) from the cylinder's polygon."""
    return 20 + t/math.cos(math.pi/quality.circle_segments())


@pytest.mark.parametrize("open_top", [False, True])
def test_inside_shell_of_cylinder_keeps_its_side_wall(open_top):
    faces = [{"normal": [0, 0, 1], "origin": [0, 0, 40]}] if open_top else None
    shelled = ShellFeature.compute_shell(_cylinder(), 2.0, "inside", open_faces=faces)
    cavity = _area(_offset(-2)) * (38 if open_top else 36)
    assert shelled.volume() == pytest.approx(_area(20)*40 - cavity, rel=1e-6)


def test_outside_shell_of_cylinder_stays_round():
    shelled = ShellFeature.compute_shell(_cylinder(), 2.0, "outside")
    assert shelled.bounding_box()[3] == pytest.approx(_offset(2), rel=1e-6)
    assert shelled.volume() == pytest.approx(_area(_offset(2))*44 - _area(20)*40, rel=1e-6)


def test_shell_of_cylinder_with_embossed_ribs_uses_the_plain_cylinder():
    """Report: Shell hung (two minutes) on a cylinder with twelve wrapped emboss ribs: the body is not convex,
    so every one of its 112k triangles was eroded with a sphere. Everything since the plain cylinder only added
    material outside it, so the cylinder is shelled exactly and the ribs are put back on the wall."""
    from omacad.io.exporter import Exporter
    doc = Exporter.load_project("tests/data/circular_pattern_wrapped_emboss.omacad")
    bid = "body_cylinder_1"
    body = doc.bodies[bid].manifold
    cylinder = doc.step_states[1][bid]
    ribs = body.volume() - cylinder.volume()
    upto = len(doc.timeline.features)
    for faces, cavity_h in ((None, 58), ([{"normal": [0, 0, 1], "origin": [0, 0, 62]}], 60)):
        shelled = ShellFeature.shell_body(doc, bid, upto, body, 2.0, "inside", open_faces=faces)
        wall = _area(20)*62 - _area(_offset(-2))*cavity_h
        assert shelled.volume() == pytest.approx(wall + ribs, rel=1e-6)


def test_drop_slivers_keeps_a_closed_inner_void():
    import manifold3d as m3d
    from omacad.model.kernel import CadKernel
    hollow = m3d.Manifold.cube((10, 10, 10), True) - m3d.Manifold.cube((6, 6, 6), True)
    flake = m3d.Manifold.cube((1, 1, 1)).scale((1, 1, 1e-9)).translate((20, 0, 0))
    assert CadKernel.drop_slivers(hollow + flake).volume() == pytest.approx(1000 - 216)


def test_edit_shell_dialog_shows_the_step_values():
    """Editing a Shell step used dialog attributes that do not exist (cmb_direction, _update_faces_label)."""
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    from omacad.ui import feature_edit
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_cylinder(20, 40)
    bid = next(iter(w.doc.bodies))
    w.doc.add_shell(bid, 3.0, open_faces=[{"normal": [0, 0, 1], "origin": [0, 0, 40]}], direction="both", thickness2=1.5)
    w.doc.timeline.recompute(w.doc)      # as after a load: the state before each step is known
    seen = {}

    def fake_exec(win, doc, dlg, preview, ids, **_):
        preview()
        seen.update(dir=dlg.direction(), t=dlg.spn_thickness.value(), t2=dlg.spn_thickness2.value(),
                    faces=len(dlg.open_faces), preview=w.viewport.preview_mesh is not None)
        return False
    orig = feature_edit._exec_with_preview
    feature_edit._exec_with_preview = fake_exec
    try:
        feature_edit.edit_feature(w, w.doc, len(w.doc.timeline.features) - 1)
    finally:
        feature_edit._exec_with_preview = orig
    assert seen == {"dir": "both", "t": 3.0, "t2": 1.5, "faces": 1, "preview": True}
    w.close()


def test_shell_of_stacked_cylinders_follows_the_step():
    """Report: a cylinder R20 H40 joined with a R16 H6 one on top, shelled 2 mm inside with the small top open.
    The convex shortcut shelled only the big cylinder and put the small one back solid (a plug), and the open
    face swept the whole wide cavity up through the narrow wall. Now both are hollowed, open only over the top."""
    from omacad.io.exporter import Exporter
    doc = Exporter.load_project("tests/data/shell_stacked_cylinders.omacad")
    body = doc.bodies["body_cylinder_1"].manifold
    n = quality.circle_segments()
    inner = lambda r: _area(r - 2/math.cos(math.pi/n))
    assert len(body.decompose()) == 1
    assert body.slice(1).area() == pytest.approx(_area(20), rel=1e-6)                  # closed bottom
    assert body.slice(20).area() == pytest.approx(_area(20) - inner(20), rel=1e-6)     # big wall
    assert body.slice(39).area() == pytest.approx(_area(20) - inner(16), rel=1e-6)     # sharp ledge inside
    for z in (41, 43, 45.5):                                                           # narrow wall, open top
        assert body.slice(z).area() == pytest.approx(_area(16) - inner(16), rel=1e-6)
