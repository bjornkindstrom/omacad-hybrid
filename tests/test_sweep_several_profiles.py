"""Sweep takes several profiles of one sketch and sweeps them together along the path."""
import math

from omacad.io.exporter import Exporter
from omacad.model.document import Document


def _doc():
    doc = Document()
    prof = doc.start_sketch("YZ")
    prof.add_rect((-12, -1), (-8, 1))               # two separate 4 x 2 rectangles, 20 mm apart
    prof.add_rect((8, -1), (12, 1))
    doc.finish_sketch()
    path = doc.start_sketch("XY")
    line = path.add_line((0, 0), (30, 0))
    doc.finish_sketch()
    return doc, prof, path, [line.entity_id]


def test_two_profiles_make_two_rails(tmp_path):
    doc, prof, path, ids = _doc()
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
