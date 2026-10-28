"""Regression test: Fill face pattern on an edge-based feature (fillet / chamfer),
such as chamfering holes on the bottom face of a model where no sketch exists on that face.
"""

import os
from pathlib import Path

from omacad.io.exporter import Exporter
from omacad.model.features.pattern import PatternFeature


def test_fill_pattern_on_bottom_face_chamfer():
    report_file = str(Path(__file__).parent / "data" / "fill_bottom_chamfer.omacad")
    doc = Exporter.load_project(report_file)
    body_id = list(doc.bodies.keys())[0]

    # Chamfer 2 (fillet_7) was created on the bottom face (z=0) chamfering a hole
    ch2 = doc.timeline.features[6]
    assert ch2.feature_id == "fillet_7"

    # Fill face pattern targeting fillet_7
    pat = PatternFeature(
        "pat_test_bottom",
        "Fill bottom chamfers",
        ["fillet_7"],
        kind="fill",
        count1=3.0,
        spacing1=1.0,
        spacing2=3.0,
        mirror_mode="stagger",
    )

    res = pat.compute(doc, body_id)
    assert res is not None, "PatternFeature.compute should succeed for edge/chamfer features without a sketch"
    rem, add = res
    assert rem is not None and not rem.is_empty(), "Removed manifold should be non-empty"
    assert pat.copies > 0, "Should generate pattern copies on the bottom face"
