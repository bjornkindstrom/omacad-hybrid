"""Sketch Fillet: plain clicks collect corners while the radius box is open, with a live preview (no Shift)."""
import pytest

from omacad.model.document import Document


def _square(sk):
    pts = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]
    return [sk.add_line(pts[i], pts[(i + 1) % 4]) for i in range(4)]


@pytest.fixture
def view():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    vp = Viewport3D(doc)
    vp.resize(600, 400)
    yield doc, vp
    vp.deleteLater()


def test_clicks_in_the_open_radius_box_add_corners_and_the_preview_follows(view, monkeypatch):
    doc, vp = view
    sk = doc.start_sketch()
    lines = _square(sk)
    vp.set_sketch_tool("FILLET")
    corners = {tuple(pt): (pt, la, lb) for pt, la, lb, _a, _b in sk.find_corners()}
    seen = []

    def box(self, title, label, value, lo=0.1, hi=2000.0, on_change=None, **kw):
        on_change(3.0)
        seen.append(None if self.fillet_preview is None else len(self.fillet_preview))
        for c in ((0.0, 20.0), (20.0, 20.0)):              # two more plain clicks while the box is open
            pt, la, lb = corners[c]
            self._fillet_toggle_corner(pt, la.entity_id, lb.entity_id)
            seen.append(len(self.fillet_preview))
        pt, la, lb = corners[(20.0, 20.0)]                 # clicking a picked corner again drops it
        self._fillet_toggle_corner(pt, la.entity_id, lb.entity_id)
        seen.append(len(self.fillet_preview))
        return 3.0, None

    monkeypatch.setattr(type(vp), "prompt_dimension_value", box)
    pt, la, lb = corners[(0.0, 0.0)]
    vp._fillet_toggle_corner(pt, la.entity_id, lb.entity_id)   # the first click opens the box
    assert seen[0] > 0 and seen[1] > seen[0] and seen[2] > seen[1] and seen[3] == seen[1]
    arcs = [e for e in doc.active_sketch.entities if e.entity_type == "arc"]
    assert len(arcs) == 2 and vp.fillet_picked == [] and vp.fillet_preview is None
    doc.undo()
    assert not [e for e in doc.active_sketch.entities if e.entity_type == "arc"]   # one undo step for both


def test_cancel_drops_every_picked_corner(view, monkeypatch):
    doc, vp = view
    sk = doc.start_sketch()
    _square(sk)
    vp.set_sketch_tool("FILLET")
    monkeypatch.setattr(type(vp), "prompt_dimension_value", lambda self, *a, **k: None)
    pt, la, lb, _a, _b = sk.find_corners()[0]
    vp._fillet_toggle_corner(pt, la.entity_id, lb.entity_id)
    assert vp.fillet_picked == [] and not [e for e in doc.active_sketch.entities if e.entity_type == "arc"]


def test_inner_corner_where_two_rectangles_cross_is_rounded_in_the_quadrant_under_the_mouse(view, monkeypatch):
    from omacad.model.sketch_extend import line_crossings, crossing_signs
    doc, vp = view
    sk = doc.start_sketch()
    for x0, y0, x1, y1 in ((0, 0, 30, 10), (0, 0, 10, 30)):
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for i in range(4):
            sk.add_line(pts[i], pts[(i + 1) % 4])
    vp.set_sketch_tool("FILLET")
    pt, la, lb = next(c for c in line_crossings(sk) if c[0] == pytest.approx((10.0, 10.0)))
    monkeypatch.setattr(type(vp), "prompt_dimension_value", lambda self, *a, on_change=None, **k: (on_change(3.0), (3.0, None))[1])
    vp._fillet_toggle_corner(pt, la.entity_id, lb.entity_id, crossing_signs(la, lb, pt, (12.0, 12.0)))
    sk = doc.active_sketch
    arc = next(e for e in sk.entities if e.entity_type == "arc")
    assert arc.p_mid[0] > 10.0 and arc.p_mid[1] > 10.0                  # the outside quadrant of the L
    areas = sorted(p.area for p in sk.profiles)
    assert areas == [pytest.approx(100.0), pytest.approx(400.0 + 9.0 - 9.0 * 3.14159265 / 4, abs=0.01)]
    doc.undo()
    assert not [e for e in doc.active_sketch.entities if e.entity_type == "arc"]


def test_crossings_are_x_and_t_junctions_not_plain_corners():
    from omacad.model.sketch_extend import line_crossings
    doc = Document()
    sk = doc.start_sketch()
    _square(sk)
    assert line_crossings(sk) == []
    sk.add_line((10.0, -5.0), (10.0, 25.0))                          # cuts through top and bottom
    assert sorted(c[0] for c in line_crossings(sk)) == [pytest.approx((10.0, 0.0)), pytest.approx((10.0, 20.0))]
