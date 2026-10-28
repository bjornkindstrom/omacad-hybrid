"""Chamfers at the foot of a wall that meet round its outside corner (report 20261023-213524): the bevel swings round
the corner edge like the fillet's rolling ball, instead of meeting the other band in a mitred ridge."""
import math
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.document import Document

DOC = Path(__file__).parent / "data" / "chamfer_rib_outside_corner.omacad"


def _feet_at(body, v):
    return [(tuple(e.p0), tuple(e.p1)) for e in body.edges if e.kind == "line" and not e.convex
            and min(np.linalg.norm(e.p0 - v), np.linalg.norm(e.p1 - v)) < 1e-2]


def test_square_block_corner_is_a_quarter_cone():
    doc = Document()
    base = doc.add_box(50, 50, 10, center="bottom_center")
    block = doc.add_box(20, 20, 20, center="bottom_center", translation=(-15, -15, 10))
    doc.combine_bodies(base.body_id, block.body_id)
    body = next(iter(doc.bodies.values()))
    feet = _feet_at(body, np.array([-5.0, -5.0, 10.0]))
    assert len(feet) == 2
    before = body.manifold.volume()
    d = 6.0
    doc.add_fillet(feet, d, kind="chamfer")
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    # two 20 mm bands plus the bevel triangle swung a quarter turn round the corner edge (a quarter cone)
    exact = 2 * 20 * d * d / 2 + math.pi * d ** 3 / 12
    added = result.volume() - before
    assert abs(added - exact) / exact < 0.005


def test_rib_end_and_side_chamfers_swing_round_the_corner():
    doc = Exporter.load_project(str(DOC))
    body = next(iter(doc.bodies.values()))
    v = np.array([10.0, -7.269, 25.0])
    feet = _feet_at(body, v)
    assert len(feet) == 2
    d = 7.0
    doc.add_fillet(feet, d, kind="chamfer")
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    # 0.5 mm above the floor the end band (square wall) reaches 6.5 mm out; a mitre puts a point 6.5 * sqrt(2)
    # out on the diagonal, the swung bevel keeps every point beyond the corner within that reach
    pts = np.vstack(result.slice(25.5).to_polygons())
    beyond = pts[(pts[:, 0] < v[0] - 1e-3) & (pts[:, 1] > v[1] + 1e-3)]
    assert len(beyond) > 10
    assert np.linalg.norm(beyond - v[:2], axis=1).max() < d - 0.5 + 0.05


def test_bands_on_differently_leaning_walls_meet_at_one_point():
    """Report 20261023-213915: 7 mm up the rib's upright end meets the leaning corner edge 8.23 mm up, 7 mm up the
    slanted side only 7 mm up; the bands now meet at the lower point, the end band's top coming down to it over the
    last 7 mm."""
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "chamfer_leaning_rib_corner.omacad"))
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    v = np.array([10.0, -7.269, 25.0])
    cd = np.array([0.0, -7.731, 12.5]) / np.linalg.norm([0.0, -7.731, 12.5])
    pts = np.asarray(result.to_mesh().vert_properties)[:, :3]
    d = pts - v
    t = d @ cd
    on_edge = t[(np.linalg.norm(d - t[:, None] * cd, axis=1) < 1e-3) & (t > 0.5) & (t < 14.0)]
    assert len(on_edge) and np.allclose(on_edge, 7.0, atol=1e-3)
    # the end face keeps the full 7 mm chamfer height until 7 mm from the corner
    end_top = pts[(abs(pts[:, 0] - 10.0) < 1e-3) & (abs(pts[:, 2] - 32.0) < 1e-3)]
    corner_y = v[1] - 7.0 * 7.731 / 12.5          # where z = 32 crosses the corner edge
    assert abs(end_top[:, 1].max() - (corner_y - 7.0)) < 1e-2
