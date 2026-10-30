import pytest
import numpy as np
from omacad.model.document import Document
from omacad.ui.history_delegate import apply_dimension

def test_polygon_sides_update():
    doc = Document()
    sketch = doc.start_sketch("XY")
    res = sketch.add_polygon((0.0, 0.0), (20.0, 0.0), sides=5)
    gid = res[0].group
    doc.finish_sketch()
    
    sketch = doc.sketches[sketch.sketch_id]
    poly_info = sketch.polygon_groups()[gid]
    assert poly_info["sides"] == 5
    assert len(poly_info["lines"]) == 5

    # Change to 8 sides via Document API
    doc.set_polygon_sides(sketch.sketch_id, gid, 8)
    sketch = doc.sketches[sketch.sketch_id]
    poly_info = sketch.polygon_groups()[gid]
    assert poly_info["sides"] == 8
    assert len(poly_info["lines"]) == 8

    # Undo
    doc.undo()
    sketch = doc.sketches[sketch.sketch_id]
    poly_info = sketch.polygon_groups()[gid]
    assert poly_info["sides"] == 5
    assert len(poly_info["lines"]) == 5

    # Redo
    doc.redo()
    sketch = doc.sketches[sketch.sketch_id]
    poly_info = sketch.polygon_groups()[gid]
    assert poly_info["sides"] == 8
    assert len(poly_info["lines"]) == 8

def test_polygon_sides_history_delegate_apply():
    doc = Document()
    sketch = doc.start_sketch("XY")
    res = sketch.add_polygon((10.0, 10.0), (25.0, 10.0), sides=6)
    gid = res[0].group
    doc.finish_sketch()
    feat = doc.extrude_profile(sketch.sketch_id, 0, 25.0)

    # Test apply_dimension for polygon_sides
    apply_dimension(doc, "polygon_sides", (sketch.sketch_id, gid), "4")

    sketch = doc.sketches[sketch.sketch_id]
    poly_info = sketch.polygon_groups()[gid]
    assert poly_info["sides"] == 4
    assert len(poly_info["lines"]) == 4
