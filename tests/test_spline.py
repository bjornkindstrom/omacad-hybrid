from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.sketch_entities import SketchSpline, move_entity, rotate_entity


def test_spline_interpolates_picked_points_and_roundtrips():
    points = [(0, 0), (5, 8), (10, 0)]
    spline = SketchSpline("spline_1", points)

    sampled = spline.get_points()
    assert sampled[0] == points[0]
    assert sampled[-1] == points[-1]
    assert all(point in sampled for point in points)
    assert len(spline.to_lines()) == 32
    assert SketchSpline.from_dict(spline.to_dict()).points == points


def test_spline_sketch_serialization_and_transformations():
    sketch = Sketch("sketch_1", plane=SketchPlane.create_named("XY"))
    spline = sketch.add_spline([(0, 0), (5, 8), (10, 0)])
    restored = Sketch.from_dict(sketch.to_dict())
    assert restored.entities[0].to_dict() == spline.to_dict()

    move_entity(spline, 2, -1)
    assert spline.points[0] == (2, -1)
    rotate_entity(spline, 90, (0, 0))
    assert abs(spline.points[0][0] - 1) < 1e-9
    assert abs(spline.points[0][1] - 2) < 1e-9


def _old_catmull(points, n=16):
    out = []
    for i in range(len(points) - 1):
        p0 = points[max(0, i - 1)]; p1, p2 = points[i], points[i + 1]; p3 = points[min(len(points) - 1, i + 2)]
        for j in range(n):
            t = j / n; t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2*p0[k] - 5*p1[k] + 4*p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3*p1[k] - 3*p2[k] + p3[k]) * t3) for k in (0, 1)))
    return out + [points[-1]]


def test_default_tangents_match_old_curve_and_dict_is_unchanged():
    pts = [(0, 0), (5, 8), (10, 0), (14, 3)]
    sp = SketchSpline("s", pts)
    for a, b in zip(sp.get_points(), _old_catmull([tuple(map(float, p)) for p in pts])):
        assert abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9
    assert "tangents" not in sp.to_dict()
    sp.tangents[1] = (3.0, 0.0)
    assert SketchSpline.from_dict(sp.to_dict()).tangents == {1: (3.0, 0.0)}
    assert (5.0, 8.0) in sp.get_points()


def test_edit_methods_and_undo_on_sketch_level():
    sketch = Sketch("sketch_1", plane=SketchPlane.create_named("XY"))
    sp = sketch.add_spline([(0, 0), (5, 8), (10, 0)])
    sketch.move_spline_point(sp.entity_id, 1, (5, 10))
    assert sp.points[1] == (5.0, 10.0)
    sketch.set_spline_tangent(sp.entity_id, 1, (4, 0))
    assert (5.0, 10.0) in sp.get_points()
    before = sp.get_points()
    i = sketch.insert_spline_point(sp.entity_id, (2.5, 6))
    assert i == 1 and len(sp.points) == 4
    assert (0.0, 0.0) in sp.get_points() and (10.0, 0.0) in sp.get_points()
    assert (5.0, 10.0) in sp.points
    p = sp.points[1]
    assert min(((p[0]-q[0])**2 + (p[1]-q[1])**2) ** .5 for q in before) < 0.8
    sp.projected = True
    import pytest
    with pytest.raises(ValueError):
        sketch.move_spline_point(sp.entity_id, 0, (1, 1))


def test_document_spline_edits_are_single_undo_steps():
    from omacad.model.document import Document
    doc = Document()
    sk = doc.start_sketch("XY")
    sp = sk.add_spline([(0, 0), (5, 8), (10, 0)])
    sk.add_line((10, 0), (0, 0))
    doc.finish_sketch()
    orig = sk.to_dict()
    doc.move_spline_point(sk.sketch_id, sp.entity_id, 1, (5, 12))
    doc.set_spline_tangent(sk.sketch_id, sp.entity_id, 1, (6, 0))
    doc.insert_spline_point(sk.sketch_id, sp.entity_id, (2.5, 8))
    assert len(sp.points) == 4
    doc.undo(); doc.undo()
    assert doc.sketches[sk.sketch_id].entities[0].points[1] == (5.0, 12.0)
    doc.undo()
    assert doc.sketches[sk.sketch_id].to_dict() == orig
    doc.redo()
    assert doc.sketches[sk.sketch_id].entities[0].points[1] == (5.0, 12.0)
    assert doc.sketches[sk.sketch_id].profiles
