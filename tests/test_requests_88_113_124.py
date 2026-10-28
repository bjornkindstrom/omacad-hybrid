"""Regression tests for open requests #88 and #113..#124."""
import os
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchArc, SketchLine, SketchPlane
from omacad.model.sketch_trim import trim_plan, apply_trim
from omacad.model import expr
from omacad.ui.expr_spin import name_before, matching_parameters
from omacad.ui.sketch_palette import SketchPalette
from omacad.ui.sketch_tool_panel import SketchToolPanel
from omacad.ui.dialogs.revolve_dlg import RevolveDialog


def test_request_88_shell_on_chamfered_rotated_cylinder():
    """#88: Shell on a chamfered and rotated cylinder keeps a round, uniform inner wall without sliver-plane cuts."""
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_circle((0.0, 0.0), 87.26)
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 80.0, "new_body")
    bid = next(iter(doc.bodies))
    body = doc.bodies[bid]
    edges = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2]) < 1.0]
    assert edges
    doc.add_fillet(edges, 34.0, "chamfer")
    doc.move_body(bid, 0.0, 0.0, 0.0, 180.0, 0.0, 0.0, pivot=(0.0, 0.0, 40.0))
    doc.add_shell(bid, 2.0, open_faces=[{"normal": [0.0, 0.0, 1.0], "origin": [0.0, 0.0, 80.0]}])
    cs = doc.bodies[bid].manifold.slice(25.0)
    polys = cs.to_polygons()
    assert len(polys) == 2
    radii = np.concatenate([np.hypot(p[:, 0], p[:, 1]) for p in polys])
    inner = radii[radii < 86.2]
    assert len(inner) >= 60
    assert float(inner.min()) > 85.15 and float(inner.max()) < 85.35


def test_request_119_unicode_parameter_suggestions():
    """#119: Parameter autocomplete continues matching Swedish/Unicode letters like Längd when typing Lä."""
    expr.set_variables({"Längd": 40.0, "Höjd": 25.0})
    try:
        for partial in ("L", "Lä", "Län", "Läng"):
            tok, _ = name_before(partial)
            names, _ = matching_parameters(tok)
            assert tok == partial
            assert names == ["Längd"]
    finally:
        expr.set_variables({})


def test_requests_114_122_sketch_plane_axis_names():
    """#114 & #122: Revolve and Sketch Move label axes with true world X/Y/Z names of the sketch plane."""
    QApplication.instance() or QApplication([])
    assert SketchPlane.create_named("XY").axis_names() == ("X", "Y")
    assert SketchPlane.create_named("XZ").axis_names() == ("X", "Z")
    assert SketchPlane.create_named("YZ").axis_names() == ("Y", "Z")

    doc = Document()
    sk = doc.start_sketch("XZ")
    sk.add_rect((0.0, 0.0), (20.0, 30.0))
    doc.finish_sketch()

    dlg = RevolveDialog(doc)
    axes_text = [dlg.cmb_axis.itemText(i) for i in range(dlg.cmb_axis.count())]
    assert any("Sketch Z axis (vertical)" in t for t in axes_text)
    assert any("Sketch X axis (horizontal)" in t for t in axes_text)

    panel = SketchToolPanel()
    panel.show_tool("MOVE", axis_names=sk.plane.axis_names())
    assert "X / Z" in panel.hint.text()


def test_request_123_trim_arc_at_endpoint_junction():
    """#123: Trimming an arc where another arc ends on it cuts at the junction instead of removing the whole arc."""
    sk = Sketch("sketch_1")
    arc5 = SketchArc("arc_5", (10.4106765, 27.7912028), (11.1695534, 34.9901843), (12.6426619, 42.1041279))
    arc7 = SketchArc("arc_7", (2.6368981, 31.1190704), (6.7276037, 30.9462499), (10.7584037, 31.4057464))
    line6 = SketchLine("line_6", (2.6368981, 31.1190704), (10.4106765, 27.7912028))
    sk.entities.extend([arc5, arc7, line6])
    plan = trim_plan(sk, 10.5, 29.0, 2.0)
    assert plan is not None
    ent, _removed, pieces = plan
    assert ent.entity_id == "arc_5"
    assert len(pieces) == 1
    apply_trim(sk, plan)
    arcs = [e for e in sk.entities if isinstance(e, SketchArc)]
    assert len(arcs) == 2


def test_request_124_show_construction_checkbox():
    """#124: SketchPalette has a 'Show Construction' toggle (checked by default) and hit_test respects it."""
    QApplication.instance() or QApplication([])
    pal = SketchPalette()
    assert hasattr(pal, "chk_show_construction")
    assert pal.chk_show_construction.isChecked()

    sk = Sketch("sketch_1")
    line = sk.add_line((0.0, 0.0), (10.0, 0.0), is_construction=True)
    assert sk.hit_test(5.0, 0.0, 1.0, include_construction=True) is line
    assert sk.hit_test(5.0, 0.0, 1.0, include_construction=False) is None
