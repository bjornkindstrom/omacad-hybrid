"""Loft twist: the last profile is turned against the first, the skin follows a helix (every slice is
the same square, only turned)."""
import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.document import Document


def _square_loft(twist):
    doc = Document()
    a = doc.start_sketch("XY")
    a.add_rect((-10, -10), (10, 10))
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 30.0, origin=(0, 0, 0)))
    b = doc.start_sketch_on_plane(plane)
    b.add_rect((-10, -10), (10, 10))
    doc.finish_sketch()
    doc.add_loft([(a.sketch_id, 0), (b.sketch_id, 0)], twist=twist)
    return doc


def test_twisted_loft_keeps_every_slice_and_turns_the_top():
    doc = _square_loft(45.0)
    m = next(iter(doc.bodies.values())).manifold
    assert 0.995 * 12000 < m.volume() <= 12000 + 1e-6      # flat quads between rings cut the helix by ~0.1 %
    v = np.asarray(m.to_mesh().vert_properties[:, :3])
    top = v[np.abs(v[:, 2] - 30) < 1e-6][:, :2]
    assert np.linalg.norm(top - [0, 10 * 2 ** 0.5], axis=1).min() < 1e-3      # corner (10, 10) went 45 degrees
    mid = v[np.abs(v[:, 2] - 15) < 0.5][:, :2]
    assert np.linalg.norm(mid, axis=1).max() > 10 * 2 ** 0.5 - 1e-3          # a true helix, not a chord through it


def test_untwisted_loft_unchanged_and_twist_survives_save_and_edit(tmp_path):
    doc = _square_loft(0.0)
    top = np.asarray(next(iter(doc.bodies.values())).manifold.to_mesh().vert_properties)[:, :2]
    assert np.linalg.norm(top - [10, 10], axis=1).min() < 1e-6
    feat = next(f for f in doc.timeline.features if f.feature_type == "loft")
    doc.edit_feature(doc.timeline.features.index(feat), twist=90.0)
    f = tmp_path / "t.omacad"
    Exporter.save_project(doc, str(f))
    again = Exporter.load_project(str(f))
    assert next(x for x in again.timeline.features if x.feature_type == "loft").twist == 90.0
