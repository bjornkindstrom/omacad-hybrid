"""Request #30: hovering a sketch line or solid edge shows its measures in the inspector."""
import math
from types import SimpleNamespace

import numpy as np
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.faces import CircularEdge, PlanarEdge
from omacad.model.hover_info import describe_edge, describe_entity
from omacad.model.sketch import SketchArc, SketchCircle, SketchLine
from omacad.ui.side_panel import InspectorPanel
from omacad.ui.viewport.viewport import Viewport3D


def _rows(info):
    return dict(info[1])


def test_sketch_measures():
    line = SketchLine("l", (0, 0), (30, 40))
    t, rows = describe_entity(line)
    assert t == "Line" and _rows((t, rows))["Length"] == "50 mm"
    assert _rows(describe_entity(SketchCircle("c", (0, 0), 5)))["Diameter"] == "10 mm"
    arc = SketchArc("a", (10, 0), (0, 10), (-10, 0))
    r = _rows(describe_entity(arc))
    assert r["Radius"] == "10 mm" and r["Angle"] == "180°" and r["Length"] == f"{10 * math.pi:.3f}".rstrip("0") + " mm"


def test_edge_measures():
    z = np.zeros(3)
    e = PlanarEdge(p0=z, p1=np.array([0.0, 7.5, 0.0]), n1=z, n2=z, d1=z, d2=z, convex=True)
    assert _rows(describe_edge(e)) == {"Length": "7.5 mm"}
    c = CircularEdge(center=z, axis=np.array([0.0, 0.0, 1.0]), radius=4.0, s1=1, s2=1, convex=True)
    assert _rows(describe_edge(c))["Diameter"] == "8 mm"


def test_viewport_emits_on_hover_change_and_inspector_shows_card():
    QApplication.instance() or QApplication([])
    sk = SimpleNamespace(hit_test=lambda u, v, tol: SketchLine("l", (0, 0), (3, 4)))
    sent = []
    vp = SimpleNamespace(hover_entity_id=None, hover_info_changed=SimpleNamespace(emit=sent.append), update=lambda: None,
                         _can_select_sketch_entities=lambda: True, doc=SimpleNamespace(active_sketch=sk),
                         sketch_tool="NONE", measure=None, _pick_entity=lambda x, y: sk.hit_test(0, 0, 1))
    Viewport3D._update_entity_hover(vp, 1, 1)
    assert sent[-1][0] == "Line" and vp.hover_entity_id == "l"
    panel = InspectorPanel(Document())
    panel.show_hover(sent[-1])
    assert panel.hover_layout.count() == 1
    panel.show_hover(None)
    QApplication.processEvents()
    assert panel.hover_layout.count() == 0
