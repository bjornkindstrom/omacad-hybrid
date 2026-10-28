"""Emboss hugs the cylinder behind the text (Fusion's wrap), even when the sketch plane floats in the air."""
import numpy as np
import pytest

from omacad.model.document import Document
from omacad.model.sketch import SketchPlane

R, H, GAP = 20.0, 40.0, 3.5


def _scene(depth):
    doc = Document()
    doc.add_cylinder(R, H)
    body = next(iter(doc.bodies))
    n = np.array([1.0, 0.0, 0.0])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(n, n * (R + GAP)))
    t = sk.add_text("HI", (0.0, 20.0), height=10.0, h_align="center", v_align="middle")
    doc.finish_sketch()
    idx = sk.text_profile_indices()
    doc.add_emboss(sk.sketch_id, idx[0], depth, extra_profiles=idx[1:])
    return doc, body


def test_emboss_reaches_the_cylinder_and_stands_depth_above_it():
    doc, body = _scene(1.0)
    assert len(doc.bodies) == 1                               # joined to the cylinder, not floating
    mesh = doc.bodies[body].manifold
    x_max = mesh.bounding_box()[3]
    assert x_max == pytest.approx(R + 1.0, abs=0.05)          # not at the sketch plane (R + 3.5)
    assert mesh.volume() > np.pi * R * R * H + 1.0


def test_deboss_wraps_too():
    doc, body = _scene(-1.0)
    mesh = doc.bodies[body].manifold
    assert mesh.volume() < np.pi * R * R * H - 1.0
    assert mesh.bounding_box()[3] == pytest.approx(R, abs=0.05)


def test_long_text_with_centroid_beside_the_cylinder_still_wraps():
    """Request #60: after editing the text to a longer string its centroid left the cylinder and the emboss
    turned into a flat extrude floating at the sketch plane."""
    doc = Document()
    doc.add_cylinder(R, H)
    body = next(iter(doc.bodies))
    n = np.array([1.0, 0.0, 0.0])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(n, n * (R + GAP)))
    sk.add_text("Testar att andra", (-15.0, 20.0), height=10.0)
    doc.finish_sketch()
    idx = sk.text_profile_indices()
    doc.add_emboss(sk.sketch_id, idx[0], 1.0, extra_profiles=idx[1:])
    mesh = doc.bodies[body].manifold
    assert len(doc.bodies) == 1
    assert mesh.bounding_box()[3] == pytest.approx(R + 1.0, abs=0.05)


def test_reported_deboss_slot_leaves_no_detached_skin():
    """Long cap diagonals must not sag through the outer surface when wrapped."""
    from pathlib import Path
    from omacad.io.exporter import Exporter

    doc = Exporter.load_project(str(Path(__file__).parent / 'data' / 'deboss_slot_flap.omacad'))
    solid = next(iter(doc.bodies.values())).manifold
    section = solid.slice(30.0)
    # One outer loop and the original bore, with no third loop for a loose flap.
    assert len(section.to_polygons()) == 2
    radius = doc.sketches['sketch_1'].entities[0].radius
    expected_area = np.pi * (5.0**2 - 3.0**2) - (2 * radius / 5.0) * (5.0**2 - 4.0**2) / 2
    assert section.area() == pytest.approx(expected_area, abs=0.04)
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    assert next(iter(loaded.bodies.values())).manifold.volume() == pytest.approx(solid.volume())
