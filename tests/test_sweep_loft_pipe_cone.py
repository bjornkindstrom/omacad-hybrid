"""Björn #46: Sweep, Loft, Pipe and Cone, checked against exact volumes, saved and reloaded."""
import math

from omacad.io.exporter import Exporter
from omacad.model.document import Document


def _path_doc():
    """A rectangle 4 x 2 on XZ (the profile) and on XY a path: 30 mm along X then a quarter arc R 20."""
    doc = Document()
    prof = doc.start_sketch("YZ")
    prof.add_rect((-2, -1), (2, 1))
    doc.finish_sketch()
    path = doc.start_sketch("XY")
    a = path.add_line((0, 0), (30, 0))
    arc = path.add_arc((30, 0), (30 + 20 * math.sin(math.pi / 4), 20 - 20 * math.cos(math.pi / 4)), (50, 20))
    doc.finish_sketch()
    return doc, prof, path, [a.entity_id, arc.entity_id]


def test_sweep_along_line_and_arc():
    doc, prof, path, ids = _path_doc()
    doc.add_sweep(prof.sketch_id, 0, (path.sketch_id, ids))
    m = next(iter(doc.bodies.values())).manifold
    length = 30 + math.pi / 2 * 20                       # Pappus: area x length of the centre line
    assert abs(m.volume() - 8 * length) < 0.01 * 8 * length
    assert m.genus() == 0


def test_pipe_solid_and_hollow_and_cone(tmp_path):
    doc, _prof, path, ids = _path_doc()
    length = 30 + math.pi / 2 * 20
    doc.add_pipe((path.sketch_id, ids), 6.0, 1.0)
    tube = next(b for b in doc.bodies.values()).manifold
    assert abs(tube.volume() - math.pi * (9 - 4) * length) < 0.01 * math.pi * 5 * length
    doc.add_cone(10.0, 0.0, 30.0)
    cone = list(doc.bodies.values())[-1].manifold
    assert abs(cone.volume() - math.pi * 100 * 30 / 3) < 0.005 * math.pi * 1000
    doc.add_cone(10.0, 4.0, 30.0, wall_thickness=1.0)
    frustum = list(doc.bodies.values())[-1].manifold
    assert frustum.volume() < math.pi * 30 / 3 * (100 + 40 + 16) and frustum.genus() == 0
    path_file = tmp_path / "p.omacad"
    Exporter.save_project(doc, str(path_file))
    again = Exporter.load_project(str(path_file))
    assert sorted(f.feature_type for f in again.timeline.features if f.feature_type in ("pipe", "cone")) == ["cone", "cone", "pipe"]
    assert abs(sum(b.manifold.volume() for b in again.bodies.values()) - sum(b.manifold.volume() for b in doc.bodies.values())) < 1e-6


def test_loft_circle_to_smaller_circle_is_a_frustum():
    doc = Document()
    a = doc.start_sketch("XY")
    a.add_circle((0, 0), 10)
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 20.0, origin=(0, 0, 0)))
    b = doc.start_sketch_on_plane(plane)
    b.add_circle((0, 0), 5)
    doc.finish_sketch()
    doc.add_loft([(a.sketch_id, 0), (b.sketch_id, 0)])
    m = next(iter(doc.bodies.values())).manifold
    want = math.pi * 20 / 3 * (100 + 50 + 25)
    assert abs(m.volume() - want) < 0.01 * want
    assert not a.visible and not b.visible           # used sketches are tucked away like after an Extrude
