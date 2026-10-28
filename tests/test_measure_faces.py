"""Measure between flat faces, and between a face and an edge (#102)."""
import numpy as np
import pytest

from omacad.model.document import Document
from omacad.model.measure import face_centroid, face_outline, measure_3d


def _box():
    doc = Document()
    doc.add_box(30.0, 20.0, 10.0)
    body = next(iter(doc.bodies.values()))
    return body


def _face(body, n):
    return next(f for f in body.faces if float(np.asarray(f.normal) @ np.asarray(n, dtype=float)) > 0.999)


def test_one_face_gives_its_area_and_outline():
    body = _box()
    top = _face(body, (0, 0, 1))
    text, segs = measure_3d([top])
    assert text == ["Area 600.000 mm²"] and segs == []
    assert len(face_outline(top)) >= 4
    assert face_centroid(top)[2] == pytest.approx(10.0)


def test_parallel_faces_give_the_gap():
    body = _box()
    top, bottom = _face(body, (0, 0, 1)), _face(body, (0, 0, -1))
    text, segs = measure_3d([top, bottom])
    assert text == ["Distance between the faces 10.000 mm"]
    a, b = segs[0]
    assert float(np.linalg.norm(np.asarray(b) - np.asarray(a))) == pytest.approx(10.0)
    left, right = _face(body, (-1, 0, 0)), _face(body, (1, 0, 0))
    assert measure_3d([left, right])[0] == ["Distance between the faces 30.000 mm"]


def test_face_at_an_angle_and_face_to_edge():
    body = _box()
    top, side = _face(body, (0, 0, 1)), _face(body, (1, 0, 0))
    assert measure_3d([top, side])[0][0] == "Angle between the faces 90.00°"
    bottom = _face(body, (0, 0, -1))
    # a top edge, parallel to the bottom face: 10 mm away
    edge = next(e for e in body.edges if e.kind == "line" and abs(e.p0[2] - 10.0) < 1e-6 and abs(e.p1[2] - 10.0) < 1e-6)
    assert measure_3d([bottom, edge])[0] == ["Edge to face 10.000 mm"]
    assert measure_3d([edge, bottom])[0] == ["Edge to face 10.000 mm"]
    upright = next(e for e in body.edges if e.kind == "line" and abs(e.p0[2] - e.p1[2]) > 1.0)
    text = measure_3d([bottom, upright])[0]
    assert text[0] == "Angle edge to face 90.00°" and text[1] == "Nearest end to face 0.000 mm"


def test_measure_tool_falls_back_to_the_face_under_the_cursor(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from omacad.ui import settings as settings_mod
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    doc = Document()
    doc.add_box(30.0, 20.0, 10.0)
    v = Viewport3D(doc)
    body = next(iter(doc.bodies.values()))
    top, bottom = _face(body, (0, 0, 1)), _face(body, (0, 0, -1))
    v.begin_measure()
    picks = iter([top, bottom, bottom])
    monkeypatch.setattr(v, "_pick_edge", lambda x, y: None)
    monkeypatch.setattr(v, "_pick_face", lambda x, y: (body, next(picks)))
    v._measure_click(10, 10)
    assert v.measure["text"] == ["Area 600.000 mm²"]
    v._measure_click(20, 20)
    assert v.measure["text"] == ["Distance between the faces 10.000 mm"]
    v._measure_click(20, 20)          # the same face again: picked off
    assert len(v.measure["picks"]) == 1
