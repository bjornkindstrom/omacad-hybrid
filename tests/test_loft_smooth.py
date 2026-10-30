import pytest
import numpy as np
from omacad.model.document import Document
from omacad.io.exporter import Exporter

def test_loft_smooth_transition():
    doc = Document()
    s1 = doc.start_sketch("XY")
    s1.add_circle((0.0, 0.0), 20.0)
    doc.finish_sketch()

    pl2 = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 30.0, origin=(0, 0, 0)))
    s2 = doc.start_sketch_on_plane(pl2)
    s2.add_circle((0.0, 0.0), 30.0)
    doc.finish_sketch()

    pl3 = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 60.0, origin=(0, 0, 0)))
    s3 = doc.start_sketch_on_plane(pl3)
    s3.add_circle((0.0, 0.0), 15.0)
    doc.finish_sketch()

    # Linear loft
    f_linear = doc.add_loft([(s1.sketch_id, 0), (s2.sketch_id, 0), (s3.sketch_id, 0)], smooth=False)
    body_linear = list(doc.bodies.values())[-1]
    vol_linear = body_linear.manifold.volume()

    # Smooth loft
    doc2 = Document()
    s1_2 = doc2.start_sketch("XY")
    s1_2.add_circle((0.0, 0.0), 20.0)
    doc2.finish_sketch()

    pl2_2 = doc2.construction_plane(doc2.add_construction_plane(doc2.origin_planes["XY"], 30.0, origin=(0, 0, 0)))
    s2_2 = doc2.start_sketch_on_plane(pl2_2)
    s2_2.add_circle((0.0, 0.0), 30.0)
    doc2.finish_sketch()

    pl3_2 = doc2.construction_plane(doc2.add_construction_plane(doc2.origin_planes["XY"], 60.0, origin=(0, 0, 0)))
    s3_2 = doc2.start_sketch_on_plane(pl3_2)
    s3_2.add_circle((0.0, 0.0), 15.0)
    doc2.finish_sketch()

    f_smooth = doc2.add_loft([(s1_2.sketch_id, 0), (s2_2.sketch_id, 0), (s3_2.sketch_id, 0)], smooth=True)
    body_smooth = list(doc2.bodies.values())[-1]
    vol_smooth = body_smooth.manifold.volume()

    assert f_smooth.smooth is True
    assert f_linear.smooth is False
    assert vol_smooth > 0
    assert vol_linear > 0
    # Smooth transition curves out through the mid-section yielding a different volume
    assert abs(vol_smooth - vol_linear) > 10.0

    # Test serialization / deserialization round-trip
    d = Exporter.document_to_dict(doc2)
    doc_reloaded = Document()
    Exporter.apply_dict(doc_reloaded, d)
    reloaded_feat = doc_reloaded.timeline.features[-1]
    assert reloaded_feat.smooth is True
