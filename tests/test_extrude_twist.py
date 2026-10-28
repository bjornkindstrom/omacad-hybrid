"""Lennart #85: Extrude with Twist turns the profile about its own centre from bottom to top."""
import math

from shapely.geometry import Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document


def _hexagon_doc(twist, centre=(20.0, 10.0), r=10.0, height=40.0):
    doc = Document()
    sk = doc.start_sketch("XY")
    pts = [(centre[0] + r * math.cos(math.radians(60 * k)), centre[1] + r * math.sin(math.radians(60 * k))) for k in range(6)]
    for k in range(6):
        sk.add_line(pts[k], pts[(k + 1) % 6])
    sk.solve_profiles()
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, height, "new_body", twist=twist)
    return doc, pts


def test_twisted_hexagon_keeps_its_area_and_turns_about_its_centre():
    doc, pts = _hexagon_doc(90.0)
    m = next(iter(doc.bodies.values())).manifold
    area = Polygon(pts).area
    assert abs(m.volume() - area * 40.0) < 3e-4 * area * 40.0   # a twist moves material, it never adds any
    top = Polygon(m.slice(40.0 - 1e-6).to_polygons()[0])
    mid = Polygon(m.slice(20.0).to_polygons()[0])
    assert abs(top.centroid.x - 20.0) < 1e-3 and abs(top.centroid.y - 10.0) < 1e-3
    # a hexagon turned 90 degrees (= 30 modulo 60) differs from the original; at the middle it has turned 45
    want_top = Polygon([(20 + 10 * math.cos(math.radians(60 * k + 90)), 10 + 10 * math.sin(math.radians(60 * k + 90))) for k in range(6)])
    want_mid = Polygon([(20 + 10 * math.cos(math.radians(60 * k + 45)), 10 + 10 * math.sin(math.radians(60 * k + 45))) for k in range(6)])
    assert top.symmetric_difference(want_top).area < 1e-3 * area
    assert mid.symmetric_difference(want_mid).area < 1e-3 * area
    assert top.symmetric_difference(Polygon(pts)).area > 10.0


def test_twist_is_saved_and_editable(tmp_path):
    doc, _ = _hexagon_doc(60.0)
    path = tmp_path / "t.omacad"
    Exporter.save_project(doc, str(path))
    again = Exporter.load_project(str(path))
    idx = next(i for i, f in enumerate(again.timeline.features) if f.feature_type == "extrude")
    assert again.timeline.features[idx].twist == 60.0
    assert again.edit_feature(idx, twist=-120.0)
    top = Polygon(next(iter(again.bodies.values())).manifold.slice(40.0 - 1e-6).to_polygons()[0])
    want = Polygon([(20 + 10 * math.cos(math.radians(60 * k - 120)), 10 + 10 * math.sin(math.radians(60 * k - 120))) for k in range(6)])
    assert top.symmetric_difference(want).area < 0.3     # ~0.1 % of the 260 mm² hexagon
