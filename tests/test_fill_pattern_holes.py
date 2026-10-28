"""Fill pattern: copies are cut off only at the outer edge of the face, never next to a hole in its middle."""
from pathlib import Path

import numpy as np
import pytest

from omacad.io.exporter import Exporter


def filled(doc):
    ext = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
    doc.add_pattern([ext.feature_id], kind="fill", spacing1=3.0, spacing2=1.0, count1=5.0, mirror_mode="triangular")
    return doc.timeline.features[-1]


def test_no_partial_triangles_beside_the_holes():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "fill_pattern_around_holes.omacad"))
    doc.timeline.recompute(doc)
    feat = filled(doc)
    body = next(iter(doc.bodies.values()))
    res = feat.compute(doc, body.body_id)
    rem, _ = res
    pieces = rem.decompose()
    full = max(p.volume() for p in pieces)
    # every cut piece is either a whole triangle or touches the outer outline of the body
    outer = body.manifold.project()
    outline = outer.to_polygons()
    from shapely.geometry import Polygon
    shell = Polygon(max(outline, key=len)).exterior
    partial_inside = 0
    for p in pieces:
        if p.volume() > 0.98 * full:
            continue
        bb = p.bounding_box()
        pg = Polygon([(bb[0], bb[1]), (bb[3], bb[1]), (bb[3], bb[4]), (bb[0], bb[4])])
        if pg.distance(shell) > 1.5:
            partial_inside += 1
    assert partial_inside == 0
