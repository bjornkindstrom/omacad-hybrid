"""Fusion-like Fillet/Chamfer: rolling-ball box corners, chamfer corner triangles, two distances, distance and angle."""
import math

import manifold3d as m3d

from omacad.io.exporter import Exporter
from omacad.model.document import Document

A, B, C, R = 30.0, 20.0, 10.0, 3.0


def _box_round(kind, **kw):
    doc = Document()
    body = doc.add_box(A, B, C)
    edges = [e.ref() for e in body.edges if getattr(e, "kind", "line") == "line"]
    assert len(edges) == 12
    feat = doc.add_fillet(edges, R, kind, **kw)
    assert feat.skipped == 0
    return doc, next(iter(doc.bodies.values())).manifold


def _planes_box(planes):
    """The box cut by planes (normal, offset) keeping n.x >= offset: an independent build of a convex chamfer."""
    m = m3d.Manifold.cube((A, B, C))
    for n, off in planes:
        k = math.sqrt(sum(c * c for c in n))
        m = m.trim_by_plane(tuple(c / k for c in n), off / k)
    return m


def _box_frame(doc):
    bb = next(iter(doc.bodies.values())).manifold.bounding_box()
    return bb[:3]


def test_all_box_edges_fillet_meet_in_a_ball():
    """Three cylinders crossing leave a pointed bump of (2 - sqrt2) r^3 per corner; the ball corner matches the
    exact rounded box (only the tessellation of the arcs is missing)."""
    _doc, m = _box_round("fillet")
    a, b, c = A - 2 * R, B - 2 * R, C - 2 * R
    exact = a * b * c + 2 * R * (a * b + b * c + a * c) + math.pi * R * R * (a + b + c) + 4 / 3 * math.pi * R ** 3
    bumps = 8 * ((2 - math.sqrt(2)) - math.pi / 6) * R ** 3
    assert m.genus() == 0
    assert abs(m.volume() - exact) < 0.1 * bumps


def test_equal_chamfer_corners_get_a_triangle():
    doc, m = _box_round("chamfer")
    x0, y0, z0 = _box_frame(doc)
    planes = []
    for sx in (0, 1):
        for sy in (0, 1):
            for sz in (0, 1):
                corner = (sx * A, sy * B, sz * C)
                n = (1 - 2 * sx, 1 - 2 * sy, 1 - 2 * sz)      # into the box from this corner
                dot = sum(a * b for a, b in zip(n, corner))
                planes.append((n, 2 * R + dot))              # the corner triangle: u + v + w >= 2r
                for k in range(3):                           # the three edges from this corner: u + v >= r
                    ne = tuple(0 if i == k else n[i] for i in range(3))
                    planes.append((ne, R + sum(a * b for a, b in zip(ne, corner))))
    ref = _planes_box(planes).translate((x0, y0, z0))
    assert abs(m.volume() - ref.volume()) < 1e-6
    assert (m - ref).volume() < 1e-6 and (ref - m).volume() < 1e-6


def test_two_distance_chamfer_puts_the_first_distance_on_the_top_face():
    doc = Document()
    body = doc.add_box(A, B, C)
    zmax = body.manifold.bounding_box()[5]
    edge = next(e for e in body.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - zmax) < 1e-6 and abs(e.p1[2] - zmax) < 1e-6 and abs(e.p0[0] - e.p1[0]) > 1)
    doc.add_fillet([edge.ref()], 4.0, "chamfer", chamfer_type="two", size2=1.5)
    m = next(iter(doc.bodies.values())).manifold
    assert abs(m.volume() - (A * B * C - 0.5 * 4.0 * 1.5 * A)) < 1e-6
    top = m.slice(zmax - 1e-4)        # just below the top: 4 mm narrower on that side
    width = top.bounds()[3] - top.bounds()[1]
    assert abs(width - (B - 4.0)) < 1e-2
    # Flip swaps the faces
    feat = doc.timeline.features[-1]
    doc.edit_feature(len(doc.timeline.features) - 1, flip=True)
    m = next(iter(doc.bodies.values())).manifold
    top = m.slice(zmax - 1e-4)
    assert abs(top.bounds()[3] - top.bounds()[1] - (B - 1.5)) < 1e-2
    assert feat.flip


def test_distance_and_angle_chamfer_and_save_roundtrip(tmp_path):
    doc = Document()
    body = doc.add_box(A, B, C)
    zmax = body.manifold.bounding_box()[5]
    edge = next(e for e in body.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - zmax) < 1e-6 and abs(e.p1[2] - zmax) < 1e-6 and abs(e.p0[0] - e.p1[0]) > 1)
    doc.add_fillet([edge.ref()], 2.0, "chamfer", chamfer_type="angle", angle=60.0)
    vol = A * B * C - 0.5 * 2.0 * 2.0 * math.tan(math.radians(60.0)) * A
    assert abs(next(iter(doc.bodies.values())).manifold.volume() - vol) < 1e-6
    path = tmp_path / "c.omacad"
    Exporter.save_project(doc, str(path))
    again = Exporter.load_project(str(path))
    feat = again.timeline.features[-1]
    assert (feat.chamfer_type, feat.angle) == ("angle", 60.0)
    assert abs(next(iter(again.bodies.values())).manifold.volume() - vol) < 1e-6
