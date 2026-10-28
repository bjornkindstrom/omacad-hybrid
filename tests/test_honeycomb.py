"""Honeycomb: lattices of cells cut into flat and cylindrical faces, with exact volumes."""
import math

import manifold3d as m3d
import pytest
from shapely.ops import unary_union

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.honeycomb import SHAPES, HoneycombFeature, lattice

HEX = math.sqrt(3) / 2 * 6.0 ** 2          # hexagon 6 mm across flats
P = dict(shape="hexagon", size=6.0, wall=1.5, margin=3.0, depth=1.0, through=True, angle=0.0, partial=False)
PLATE = m3d.Manifold.cube((40, 30, 2))
TOP = {"kind": "plane", "normal": [0, 0, 1], "origin": [20, 15, 2]}


@pytest.mark.parametrize("shape, cells, area", [
    ("hexagon", 11, HEX), ("circle", 11, None), ("square", 12, 36.0), ("diamond", 8, 36.0),
    ("triangle", 8, math.sqrt(3) / 4 * (6.0 * math.sqrt(3)) ** 2)])
def test_plate_through_every_shape(shape, cells, area):
    m, n, skipped = HoneycombFeature.compute(PLATE, [TOP], dict(P, shape=shape))
    assert (n, skipped) == (cells, 0)
    assert m.genus() == cells                                 # every cell is a hole through the plate
    if area is not None:
        assert PLATE.volume() - m.volume() == pytest.approx(cells * area * 2.0, rel=1e-6)


def _doc_box():
    doc = Document()
    body = doc.add_box(40, 30, 20, wall_thickness=2)         # open top, 2 mm walls
    return doc, body


def test_through_a_box_wall_leaves_the_opposite_wall():
    _, body = _doc_box()
    front = {"kind": "plane", "normal": [0, -1, 0], "origin": [20, 0, 10]}
    m, n, _ = HoneycombFeature.compute(body.manifold, [front], P)
    assert n > 0
    assert body.manifold.volume() - m.volume() == pytest.approx(n * HEX * 2.0, rel=1e-6)
    back = m3d.Manifold.cube((40, 2, 20)).translate((0, 28, 0))
    assert (m ^ back).volume() == pytest.approx((body.manifold ^ back).volume(), rel=1e-9)


def test_fixed_depth_does_not_pierce():
    _, body = _doc_box()
    front = {"kind": "plane", "normal": [0, -1, 0], "origin": [20, 0, 10]}
    m, n, _ = HoneycombFeature.compute(body.manifold, [front], dict(P, through=False, depth=1.0))
    assert body.manifold.volume() - m.volume() == pytest.approx(n * HEX * 1.0, rel=1e-6)
    assert m.genus() == body.manifold.genus()


def test_round_wall_of_a_cup_all_the_way_round():
    doc = Document()
    cup = doc.add_cylinder(15, 40, wall_thickness=2).manifold
    ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 15.0, "length": 40.0, "internal": False}
    m, n, skipped = HoneycombFeature.compute(cup, [ref], P)
    assert skipped == 0 and n % 12 == 0                       # 2*pi*15 / 7.5 = 12.6 -> 12 columns, walls only widen
    assert m.genus() == cup.genus() + n                         # each cell goes through the wall, none merge
    # an annular prism: cell area on the surface times (R^2 - r^2) / 2R, faceting aside
    assert cup.volume() - m.volume() == pytest.approx(n * HEX * (15 ** 2 - 13 ** 2) / 30.0, rel=0.02)
    bottom = m3d.Manifold.cube((40, 40, 2)).translate((-20, -20, 0))
    assert (m ^ bottom).volume() == pytest.approx((cup ^ bottom).volume(), rel=1e-9)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("angle", [0.0, 90.0])
def test_lattice_closes_round_a_cylinder_without_overlap(shape, angle):
    circ = 2 * math.pi * 15.0
    cells = lattice(shape, 6.0, 1.5, angle, (0, 0, circ, 30), (circ / 2, 15), period=circ)
    copies = cells + [c for c in (__import__("shapely").affinity.translate(c, circ) for c in cells)]
    gaps = [a.distance(b) for i, a in enumerate(copies) for b in copies[i + 1:] if a.distance(b) < 1.4]
    assert not gaps                                            # the wall (1.5 mm) holds across the seam too
    assert unary_union(cells).area == pytest.approx(sum(c.area for c in cells), rel=1e-9)


def test_document_save_load_and_undo(tmp_path):
    doc, body = _doc_box()
    v0 = body.manifold.volume()
    front = {"kind": "plane", "normal": [0, -1, 0], "origin": [20, 0, 10]}
    feat = doc.add_honeycomb(body.body_id, [front], **dict(P, shape="square"))
    v1 = doc.bodies[body.body_id].manifold.volume()
    assert v0 - v1 == pytest.approx(feat.cells * 36.0 * 2.0, rel=1e-6)
    path = tmp_path / "honeycomb.omacad"
    Exporter.save_project(doc, str(path))
    again = Exporter.load_project(str(path))
    assert next(iter(again.bodies.values())).manifold.volume() == pytest.approx(v1, rel=1e-9)
    idx = doc.timeline.features.index(feat)
    assert doc.edit_feature(idx, shape="hexagon")
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(v0 - feat.cells * HEX * 2.0, rel=1e-6)
    doc.undo()
    doc.undo()
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(v0, rel=1e-9)
