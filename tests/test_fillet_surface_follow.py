"""Regression for an inside fillet where one adjacent face is cylindrical."""
import math
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import edge_from_ref
from omacad.model.features.fillet import FilletFeature


def test_inside_fillet_follows_the_adjacent_cylinder_for_the_full_edge():
    path = Path(__file__).parent / "data" / "fillet_surface_follow.omacad"
    doc = Exporter.load_project(str(path))
    doc.timeline.marker_index = 2  # replay sketch and extrusion, before the reported fillet
    doc.timeline.clear_cache()
    doc.timeline.recompute(doc)

    feature = doc.timeline.features[-1]
    assert isinstance(feature, FilletFeature)
    body = next(iter(doc.bodies.values()))
    edge = edge_from_ref(feature.edges[0], body.edges)
    assert edge is not None and edge.kind == "line" and not edge.convex

    circle = next(e for e in body.edges if e.kind == "circle" and abs(float(e.axis @ [0, 0, 1])) > 0.999)
    tool = feature._circular_neighbor_tool(body, edge, feature.size)
    assert tool is not None

    # Every axial slice follows the true radius 10 mm wall. A tangent-plane approximation
    # would leave this circle and generate the thin pointed spike from the report.
    cx, cy = circle.center[:2]
    for z in (1.0, 7.5, 14.0):
        polygons = tool.slice(z).to_polygons()
        assert len(polygons) == 1
        points = np.asarray(polygons[0])
        radial_error = np.abs(np.linalg.norm(points - [cx, cy], axis=1) - circle.radius)
        assert np.count_nonzero(radial_error < 0.03) >= 90

    # The automatic fillet uses the requested radius (the former clearance heuristic
    # reduced it to about 0.043 mm) and joins the body as one valid solid.
    expected_added_volume = tool.volume()
    feature.execute(doc)
    assert body.manifold.status().name == "NoError"
    assert math.isclose(body.manifold.volume(), 11986.372361773334 + expected_added_volume,
                        rel_tol=1e-7, abs_tol=1e-5)
    assert feature.skipped == 0
