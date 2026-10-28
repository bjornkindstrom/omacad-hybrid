"""Björn #57: text over a flat wall that runs into a rounded corner. No single plane or cylinder carries it, so
Emboss used to leave the letters floating at the sketch plane, 10 mm in front of the lid. They are now projected
onto the surface as it is, and the part beyond the lid's outline is left out."""
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.features.emboss import EmbossFeature

DOC = str(Path(__file__).parent / "data" / "emboss_flat_and_round.omacad")


def test_text_lands_on_the_wall_and_round_corner():
    doc = Exporter.load_project(DOC)
    lid = doc.bodies["body_extrude_9"].manifold
    tool = EmbossFeature("t", "t", "sketch_4", 0, 1.0, extra_profiles=[1, 2, 3, 4]).build_solid(doc)
    bb = np.array(tool.bounding_box())
    assert bb[1] > -31.5                       # at the wall (y = -30) plus the 1 mm height, not at the sketch (y = -40)
    assert bb[3] <= 45.0 + 1e-6                # nothing past the lid's side
    assert (tool ^ lid).volume() > 0.5         # it sits in the lid's surface, so a join holds together
    # where the letters run into the rounded corner they stand on the curve: the wall there lies further back
    pts = np.asarray(tool.to_mesh().vert_properties)[:, :3]
    near_corner = pts[pts[:, 0] > 43.0]
    assert near_corner[:, 1].max() > -29.0


def test_emboss_joins_the_lid():
    doc = Exporter.load_project(DOC)
    before = doc.bodies["body_extrude_9"].manifold.volume()
    doc.add_emboss("sketch_4", 0, 1.0, extra_profiles=[1, 2, 3, 4])
    lid = doc.bodies["body_extrude_9"].manifold
    assert lid.volume() - before > 5.0
    assert len(doc.bodies) == 2                # no loose letters as a new body
