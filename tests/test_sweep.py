"""Sweep and Pipe model tests: single/multi profile sweeps along lines and arcs, hollow pipes, and cones."""
import math
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui.dialogs.sweep_dlg import path_entities


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


def _two_profiles_doc():
    doc = Document()
    prof = doc.start_sketch("YZ")
    prof.add_rect((-12, -1), (-8, 1))               # two separate 4 x 2 rectangles, 20 mm apart
    prof.add_rect((8, -1), (12, 1))
    doc.finish_sketch()
    path = doc.start_sketch("XY")
    line = path.add_line((0, 0), (30, 0))
    doc.finish_sketch()
    return doc, prof, path, [line.entity_id]


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


def test_two_profiles_make_two_rails(tmp_path):
    doc, prof, path, ids = _two_profiles_doc()
    assert len(prof.profiles) == 2
    doc.add_sweep(prof.sketch_id, 0, (path.sketch_id, ids), extra_profiles=[1])
    m = next(iter(doc.bodies.values())).manifold
    assert abs(m.volume() - 2 * 8 * 30) < 1.0
    assert len(m.decompose()) == 2
    f = tmp_path / "s.omacad"
    Exporter.save_project(doc, str(f))
    again = next(iter(Exporter.load_project(str(f)).bodies.values())).manifold
    assert abs(again.volume() - 480) < 1.0 and len(again.decompose()) == 2
    doc.undo()
    assert not doc.bodies


def test_sweep_from_a_profile_in_the_middle_of_a_curved_path():
    doc = Document()
    path = doc.start_sketch("XY")
    path.add_line((0, 0), (30, 0))
    path.add_arc((30, 0), (30 + 20 * math.sin(math.pi / 4), 20 - 20 * math.cos(math.pi / 4)), (50, 20))
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["YZ"], 15.0, origin=(0, 0, 0)))
    prof = doc.start_sketch_on_plane(plane)
    prof.add_circle(tuple(prof.plane.world_to_uv((15.0, 0.0, 0.0))), 2)
    doc.finish_sketch()
    doc.add_sweep(prof.sketch_id, 0, (path.sketch_id, path_entities(path)))
    m = next(iter(doc.bodies.values())).manifold
    length = 30 + math.pi / 2 * 20
    assert abs(m.volume() - math.pi * 4 * length) < 0.01 * math.pi * 4 * length
    bb = m.bounding_box()
    assert abs(bb[4] - 20.0) < 0.1 and abs(bb[3] - 52.0) < 0.1      # it follows the arc up to its end at (50, 20)
