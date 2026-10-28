"""Report 20261025-220532: linear copies must be rings, not cuts of their voids."""
from pathlib import Path

import pytest

from omacad.io.exporter import Exporter
from omacad.model.features.pattern import PatternFeature


def test_linear_pattern_copies_the_finished_hollow_body():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "linear_pattern_hollow_body.json"))
    ids = [f.feature_id for f in doc.timeline.features]
    bid, body = next(iter(doc.bodies.items()))
    original = body.manifold
    expected_copies = original.translate((0, 0, 20)) + original.translate((0, 0, 40))
    params = dict(axis1="z", count1=3, spacing1=20)
    preview = PatternFeature("preview", "Preview", ids, "linear", **params)
    removed, added = preview.compute(doc, bid)
    assert removed is None
    assert added is not None
    assert (added - expected_copies).volume() == pytest.approx(0, abs=1e-6)
    assert (expected_copies - added).volume() == pytest.approx(0, abs=1e-6)

    feature = doc.add_pattern(ids, "linear", **params)
    assert feature.copies == 2
    result = doc.bodies[bid].manifold
    assert result.volume() == pytest.approx(3 * original.volume(), rel=1e-8)
    assert len(result.decompose()) == 3
    assert (result - original - expected_copies).volume() == pytest.approx(0, abs=1e-6)
    doc.timeline.recompute(doc)
    assert doc.bodies[bid].manifold.volume() == pytest.approx(3 * original.volume(), rel=1e-8)
    doc.undo()
    assert doc.bodies[bid].manifold.volume() == pytest.approx(original.volume())
    doc.redo()
    assert doc.bodies[bid].manifold.volume() == pytest.approx(3 * original.volume(), rel=1e-8)
