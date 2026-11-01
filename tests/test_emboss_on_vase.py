"""Emboss wrapped onto a revolved spline (a vase): every letter must sit on the wall.

The vase wall passes the cylinder fit (it allows 15 % of the radius), so the letters were wrapped at one radius
(21.8 mm) while the wall under them runs from about 20 to 22 mm: three of the four letters floated up to 1.7 mm off
the surface ("Glapp mellan emboss och yta"). Document from problem report 20261101-105801."""
from pathlib import Path

from omacad.io.exporter import Exporter

DATA = Path(__file__).parent / "data" / "emboss_on_vase.omacad"


def _before_emboss():
    doc = Exporter.load_project(str(DATA))
    emboss = next(f for f in doc.timeline.features if f.feature_type == "emboss")
    doc.timeline.marker_index = doc.timeline.features.index(emboss)
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values())).manifold
    sketch = doc.sketches[emboss.sketch_id]
    region = emboss.region(doc, sketch, [emboss.profile_idx] + list(emboss.extra_profiles))
    return doc, emboss, body, region


def test_every_letter_touches_the_vase_wall():
    doc, emboss, body, region = _before_emboss()
    tool = emboss.build_solid(doc)
    letters = tool.decompose()
    assert len(letters) == len(region.geoms) == 4
    for letter in letters:
        assert (letter ^ body).volume() > 1.0          # starts inside the wall, not above it
    assert len((tool + body).decompose()) == 1


def test_letters_stand_the_depth_above_the_wall():
    doc, emboss, body, region = _before_emboss()
    raised = (emboss.build_solid(doc) - body).volume()
    # wrapped on a convex wall the outer face is a little larger than the flat letters, never smaller
    assert region.area * emboss.depth <= raised <= 1.05 * region.area * emboss.depth


def test_report_document_rebuilds_into_one_body():
    doc = Exporter.load_project(str(DATA))
    body = next(iter(doc.bodies.values())).manifold
    assert len(body.decompose()) == 1
