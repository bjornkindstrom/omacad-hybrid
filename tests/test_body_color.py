"""Tests for body color persistence, undo/redo, and reset."""

from omacad.model.document import Document
from omacad.io.exporter import Exporter
from omacad.model.timeline import BoxFeature


def test_set_body_color_and_reset():
    doc = Document()
    doc.add_box(10.0, 10.0, 10.0)
    body_id = "body_1" if "body_1" in doc.bodies else next(iter(doc.bodies))
    body = doc.bodies[body_id]

    # Default color
    assert body.color == Document.DEFAULT_BODY_COLOR

    # Set custom color
    custom_col = [1.0, 0.0, 0.0, 1.0]
    doc.set_body_color(body_id, custom_col)
    assert doc.bodies[body_id].color == custom_col
    assert doc.body_colors[body_id] == custom_col

    # Export & Import roundtrip
    data = Exporter.document_to_dict(doc)
    assert "body_colors" in data
    assert data["body_colors"][body_id] == custom_col

    doc2 = Document()
    doc2.add_box(10.0, 10.0, 10.0)
    Exporter.apply_dict(doc2, data)
    assert doc2.body_colors[body_id] == custom_col

    # Timeline recompute keeps color
    doc.timeline.recompute(doc)
    assert doc.bodies[body_id].color == custom_col

    # Reset to uncolored (None)
    doc.set_body_color(body_id, None)
    assert doc.bodies[body_id].color == Document.DEFAULT_BODY_COLOR
    assert body_id not in doc.body_colors

    # Undo reset restores custom color
    doc.undo()
    assert doc.bodies[body_id].color == custom_col

    # Undo color change restores default color
    doc.undo()
    assert doc.bodies[body_id].color == Document.DEFAULT_BODY_COLOR
