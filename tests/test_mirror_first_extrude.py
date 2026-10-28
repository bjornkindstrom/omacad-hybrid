"""Mirror also works when the hole is part of the extrude that makes the body (steps tick from the sketch on)."""
from pathlib import Path

import pytest

from omacad.io.exporter import Exporter


def test_mirror_copies_hole_made_by_the_body_creating_extrude():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "mirror_hole_in_first_extrude.omacad"))
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    before = body.manifold.volume()
    ids = [f.feature_id for f in doc.timeline.features]
    doc.add_pattern(ids, kind="mirror", mirror_mode="xy")
    after = next(iter(doc.bodies.values())).manifold.volume()
    # three more copies of the hole and its chamfer (about 856 mm3 each)
    assert before - after == pytest.approx(3 * 856, rel=0.02)
