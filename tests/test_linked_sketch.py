"""Tests for LinkedSketchFeature and sketch scaling."""

import pytest
import numpy as np
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane, SketchLine, SketchCircle, SketchRect
from omacad.model.sketch_entities import scale_entity, scale_point
from omacad.model.sketch_scale import scale_sketch_entities
from omacad.io.exporter import Exporter


def test_scale_point_and_entities():
    pt = scale_point((10.0, 20.0), 2.0, (0.0, 0.0))
    assert pt == (20.0, 40.0)

    pt_pivot = scale_point((10.0, 20.0), 2.0, (5.0, 10.0))
    assert pt_pivot == (15.0, 30.0)

    line = SketchLine("l1", (0.0, 0.0), (10.0, 0.0))
    scale_entity(line, 2.5, (0.0, 0.0))
    assert line.p1 == (0.0, 0.0)
    assert line.p2 == (25.0, 0.0)

    circ = SketchCircle("c1", (10.0, 10.0), 5.0)
    scale_entity(circ, 2.0, (0.0, 0.0))
    assert circ.center == (20.0, 20.0)
    assert circ.radius == 10.0


def test_scale_sketch_tool():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 20))
    doc.finish_sketch()

    orig_area = sk.profiles[0].area
    assert orig_area == pytest.approx(200.0)

    # Scale 2x
    ok = doc.scale_sketch(sk.sketch_id, 2.0, pivot=(0.0, 0.0))
    assert ok
    assert sk.profiles[0].area == pytest.approx(800.0)


def test_linked_sketch_parametric_update_and_scale():
    doc = Document()
    sk1 = doc.start_sketch("XY")
    sk1.add_rect((0, 0), (10, 10))
    doc.finish_sketch()
    assert sk1.profiles[0].area == pytest.approx(100.0)

    # Copy to XZ plane with scale 1.5
    xz_plane = doc.origin_planes["XZ"]
    sk2 = doc.add_linked_sketch(sk1.sketch_id, xz_plane, scale=1.5)
    assert sk2 is not None
    assert sk2.plane.name == "XZ"
    assert len(sk2.entities) == len(sk1.entities)
    # Area should be scaled by 1.5 * 1.5 = 2.25 => 225.0
    assert sk2.profiles[0].area == pytest.approx(225.0)

    # Modify source sketch: add another entity or scale source
    doc.scale_sketch(sk1.sketch_id, 2.0, pivot=(0.0, 0.0))
    # After source changed, recompute updates linked sketch automatically!
    sk1 = doc.sketches[sk1.sketch_id]
    sk2 = doc.sketches[sk2.sketch_id]
    assert sk1.profiles[0].area == pytest.approx(400.0)
    assert sk2.profiles[0].area == pytest.approx(400.0 * 2.25)


def test_linked_sketch_exporter_round_trip():
    doc = Document()
    sk1 = doc.start_sketch("XY")
    sk1.add_rect((0, 0), (20, 30))
    doc.finish_sketch()

    doc.add_linked_sketch(sk1.sketch_id, "YZ", scale=0.5)

    data = Exporter.document_to_dict(doc)
    loaded = Document()
    Exporter.apply_dict(loaded, data)

    assert len(loaded.sketches) == 2
    sk2 = [s for s in loaded.sketches.values() if s.sketch_id != sk1.sketch_id][0]
    assert sk2.plane.name == "YZ"
    assert sk2.profiles[0].area == pytest.approx(600.0 * 0.25)
