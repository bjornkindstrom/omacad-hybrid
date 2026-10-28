"""Fill pattern: the room it fills is exactly the face (no hairline channels, no shift when the sketch plane's
origin is not the world origin)."""
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from omacad.io.exporter import Exporter

DATA = Path(__file__).parent / "data"


def _fill(name, mode="grid"):
    doc = Exporter.load_project(str(DATA / name))
    doc.timeline.recompute(doc)
    ext = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
    doc.add_pattern([ext.feature_id], kind="fill", spacing1=3.0, spacing2=3.0, count1=25.0, mirror_mode=mode)
    feat = doc.timeline.features[-1]
    body = next(iter(doc.bodies.values()))
    rem, _ = feat.compute(doc, body.body_id)
    return feat, body, rem


def test_no_channel_along_the_triangle_edges_of_the_face():
    feat, _, rem = _fill("fill_pattern_hairline_cracks.omacad")
    room = feat._fill_clip[0]
    assert room.area == pytest.approx(53.0 * 53.0, rel=1e-3)   # 59 mm face inset by the 3 mm margin
    assert feat.copies == 15                                  # 4 x 4 lattice, minus the original


@pytest.mark.parametrize("mode", ["grid", "stagger"])
def test_copies_stay_over_the_body_when_the_plane_origin_is_off_centre(mode):
    _, body, rem = _fill("fill_pattern_offset_plane_origin.omacad", mode)
    shell = Polygon(max(body.manifold.project().to_polygons(), key=len))
    for p in rem.decompose():
        bb = p.bounding_box()
        box = Polygon([(bb[0], bb[1]), (bb[3], bb[1]), (bb[3], bb[4]), (bb[0], bb[4])])
        assert box.intersection(shell).area / box.area > 0.5
