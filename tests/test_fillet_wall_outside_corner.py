"""Fillets at the foot of a wall that meet round its outside corner (report 20261023-211810): the ball rolls round the
corner edge like in Fusion, so the two roundings flow into each other instead of meeting in a mitred crease."""
import pytest
import math
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.document import Document

DOC = Path(__file__).parent / "data" / "fillet_rib_outside_corner.omacad"
LEANING = Path(__file__).parent / "data" / "fillet_leaning_rib_corner.omacad"


def _feet_at(body, v):
    return [(tuple(e.p0), tuple(e.p1)) for e in body.edges if e.kind == "line" and not e.convex
            and min(np.linalg.norm(e.p0 - v), np.linalg.norm(e.p1 - v)) < 1e-2]


def test_square_block_corner_is_a_revolved_fillet():
    doc = Document()
    base = doc.add_box(50, 50, 10, center="bottom_center")
    block = doc.add_box(20, 20, 20, center="bottom_center", translation=(-15, -15, 10))
    doc.combine_bodies(base.body_id, block.body_id)
    body = next(iter(doc.bodies.values()))
    v = np.array([-5.0, -5.0, 10.0])
    feet = _feet_at(body, v)
    assert len(feet) == 2
    before = body.manifold.volume()
    r = 6.0
    doc.add_fillet(feet, r)
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    area = r * r * (1 - math.pi / 4)
    # two 20 mm bands plus the profile revolved a quarter turn round the corner edge (Pappus)
    exact = 2 * 20 * area + math.pi / 2 * r ** 3 * (5 / 6 - math.pi / 4)
    added = result.volume() - before
    assert abs(added - exact) / exact < 0.005


def test_rib_end_and_side_fillets_flow_round_the_corner():
    doc = Exporter.load_project(str(DOC))
    body = next(iter(doc.bodies.values()))
    v = np.array([-8.347, -4.5, 25.0])
    feet = _feet_at(body, v)
    assert len(feet) == 2
    r = 14.5
    doc.add_fillet(feet, r)
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    # 0.5 mm above the floor the end band (square wall) reaches 10.73 mm out; a mitre would put a point on the
    # diagonal about 15 mm from the corner, the rolling ball keeps every point beyond the corner within that reach
    h = 0.5
    reach = r - math.sqrt(r * r - (r - h) ** 2)
    pts = np.vstack(result.slice(25.0 + h).to_polygons())
    beyond = pts[(pts[:, 0] > v[0] + 1e-3) & (pts[:, 1] > v[1] + 1e-3)]
    assert len(beyond) > 10
    assert np.linalg.norm(beyond - v[:2], axis=1).max() < reach + 0.1


def test_band_beside_a_leaning_corner_edge_stops_at_the_ball():
    """Report 20261023-214720: the rib's side leans, so its corner edge with the square end leans too. The end band
    was cut along that edge, ran on past the ball near the floor, and the swept ball cut it off as a loose strip
    (a triangle on the floor)."""
    doc = Exporter.load_project(str(LEANING))
    feat = doc.timeline.features[-1]
    result = next(iter(doc.bodies.values())).manifold
    assert feat.skipped == 0 and result.genus() == 0
    for z in (25.001, 25.01):
        assert len(result.slice(z).decompose()) == 1
    # where the two bands meet there is no step: the corner is as fine as the bands
    mesh = result.to_mesh()
    tri = np.asarray(mesh.vert_properties)[:, :3][np.asarray(mesh.tri_verts)]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    c = tri.mean(axis=1)
    step = (np.abs(c[:, 0] - 10.0) < 0.02) & (c[:, 1] > -8) & (c[:, 1] < 1) & (n[:, 0] > 0.99 * np.linalg.norm(n, axis=1))
    assert np.linalg.norm(n[step], axis=1).sum() / 2 < 0.05
