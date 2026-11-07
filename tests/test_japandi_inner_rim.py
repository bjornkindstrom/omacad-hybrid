"""Report 20261107-110203: no folded strips across the smooth inner lip."""
from pathlib import Path

import numpy as np
import pytest
from shapely import contains_xy
from shapely.geometry import Polygon

from omacad.io.exporter import Exporter


def test_report_inner_lip_has_no_crosswise_creases():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "japandi_inner_rim.omacad"))
    body = next(iter(doc.bodies.values()))
    solid = body.manifold
    assert solid.status().name == "NoError"
    assert len(solid.decompose()) == 1
    # The bore below the lip identifies its inside, excluding the external ribs.
    bore = min((Polygon(p) for p in solid.slice(20.).to_polygons()), key=lambda p: p.area)
    segments = body.render_mesh.sharp_lines.reshape(-1, 2, 3)
    mid = segments.mean(axis=1)
    inside_lip = ((mid[:, 2] > 22.01) & (mid[:, 2] < 24.99)
                  & contains_xy(bore.buffer(0.01), mid[:, 0], mid[:, 1]))
    assert not np.any(inside_lip & (np.abs(segments[:, 1, 2] - segments[:, 0, 2]) > 0.01))
    # The full-width round lip is still present; the wall and top opening stay put.
    def hole_at(z):
        return min((Polygon(p) for p in solid.slice(z).to_polygons()), key=lambda p: p.area)
    middle = hole_at(23.5)
    assert middle.bounds == pytest.approx((-54., -22., 54., 22.), abs=0.01)
    assert hole_at(24.999).bounds == pytest.approx(bore.bounds, abs=0.01)
    # Straight portions match a one millimetre inward offset at the lip's crest.
    assert middle.area == pytest.approx(bore.buffer(-1., join_style="mitre").area, abs=0.1)
