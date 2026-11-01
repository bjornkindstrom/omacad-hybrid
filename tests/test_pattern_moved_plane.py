"""Fill pattern uses the sketch plane in the body's current orientation."""
from types import SimpleNamespace

import numpy as np

from omacad.model.features.pattern import PatternFeature
from omacad.model.sketch import SketchPlane


def test_source_plane_follows_body_half_turn():
    plane = SketchPlane.create_named("XY")
    source = SimpleNamespace(feature_id="sketch", sketch=SimpleNamespace(plane=plane))
    turn = np.diag([1.0, -1.0, -1.0, 1.0])
    turn[:3, 3] = (0, 0, 12)
    pattern = PatternFeature("pattern", "Fill", ["sketch"], kind="fill")
    move_before = SimpleNamespace(feature_id="move_before", feature_type="move", copy_body=False,
                                  suppressed=False, error=None, applied=turn)
    move_after = SimpleNamespace(feature_id="move_after", feature_type="move", copy_body=False,
                                 suppressed=False, error=None, applied=turn)
    doc = SimpleNamespace(timeline=SimpleNamespace(features=[source, move_before, pattern, move_after]),
                          sketches={}, object_history=SimpleNamespace(owners={
                              "sketch": "body", "move_before": "body", "move_after": "body"}))

    moved = pattern._source_plane(doc)

    np.testing.assert_allclose(moved.origin, (0, 0, 12))
    np.testing.assert_allclose(moved.normal, (0, 0, -1))
    np.testing.assert_allclose(moved.v_axis, (0, -1, 0))
    np.testing.assert_allclose(plane.normal, (0, 0, 1))
