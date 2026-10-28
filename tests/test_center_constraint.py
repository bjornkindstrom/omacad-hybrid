import pytest

from omacad.model.document import Document


def _center(lines):
    points = []
    for line in lines:
        for point in (line.p1, line.p2):
            if not any((point[0] - old[0]) ** 2 + (point[1] - old[1]) ** 2 < 1e-10 for old in points):
                points.append(point)
    assert len(points) == 4
    return sum(point[0] for point in points) / 4, sum(point[1] for point in points) / 4


def test_center_constraint_aligns_horizontal_centres_and_keeps_sizes():
    doc = Document()
    sketch = doc.start_sketch()
    reference = sketch.add_center_rect((10.0, 5.0), (60.0, 40.0))
    target = sketch.add_center_rect((-25.0, -15.0), (-5.0, -5.0))
    before_reference, before_target = _center(reference), _center(target)
    refs = [line.entity_id for line in reference + target]

    assert before_reference != before_target
    assert doc.add_constraints(sketch.sketch_id, [("CENTER", refs, [])])

    assert _center(reference) == pytest.approx(before_reference, abs=1e-6)
    assert _center(target)[0] == pytest.approx(before_reference[0], abs=1e-6)
    assert _center(target)[1] != pytest.approx(before_reference[1], abs=1e-3)
    assert sketch.dimensions[0].value == pytest.approx(100.0)
    assert sketch.dimensions[1].value == pytest.approx(70.0)
    assert sketch.dimensions[2].value == pytest.approx(40.0)
    assert sketch.dimensions[3].value == pytest.approx(20.0)


def test_center_guide_recognizes_a_rectangle_from_any_side():
    from omacad.ui.viewport.viewport import Viewport3D

    sketch = Document().start_sketch()
    rectangle = sketch.add_center_rect((0.0, 0.0), (20.0, 10.0))
    expected = [line.entity_id for line in rectangle]

    for side in rectangle:
        assert Viewport3D._constraint_rectangle_group(sketch, side) == expected


def test_center_constraint_can_lock_rectangles_that_are_already_aligned():
    doc = Document()
    sketch = doc.start_sketch()
    reference = sketch.add_center_rect((0.0, 0.0), (50.0, 35.0))
    target = sketch.add_center_rect((0.0, 0.0), (20.0, 10.0))
    refs = [line.entity_id for line in reference + target]

    assert doc.add_constraints(sketch.sketch_id, [("CENTER", refs, [])])
    assert _center(reference) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert _center(target)[0] == pytest.approx(0.0, abs=1e-6)


def test_edge_distance_sets_vertical_offset_and_width_changes_keep_centres_aligned():
    doc = Document()
    sketch = doc.start_sketch()
    reference = sketch.add_center_rect((10.0, 5.0), (60.0, 40.0))
    target = sketch.add_center_rect((-25.0, -15.0), (-5.0, -5.0))
    refs = [line.entity_id for line in reference + target]
    assert doc.add_constraints(sketch.sketch_id, [("CENTER", refs, [])])

    assert doc.add_dimension_constraint(
        sketch.sketch_id, "PT_LINE_DIST", target[2].entity_id, 30.0,
        refs=[reference[2].entity_id], pts=["p1"],
    )
    assert abs(reference[2].p1[1] - target[2].p1[1]) == pytest.approx(30.0, abs=1e-6)
    assert _center(target)[0] == pytest.approx(_center(reference)[0], abs=1e-6)

    width = next(dim for dim in sketch.dimensions if dim.target_entity_id == target[0].entity_id)
    assert doc.update_dimension(sketch.sketch_id, width.dim_id, 60.0)
    assert width.value == pytest.approx(60.0)
    assert _center(target)[0] == pytest.approx(_center(reference)[0], abs=1e-6)
    assert abs(reference[2].p1[1] - target[2].p1[1]) == pytest.approx(30.0, abs=1e-6)

    reference_width = next(dim for dim in sketch.dimensions if dim.target_entity_id == reference[0].entity_id)
    assert doc.update_dimension(sketch.sketch_id, reference_width.dim_id, 120.0)
    assert reference_width.value == pytest.approx(120.0)
    assert _center(target)[0] == pytest.approx(_center(reference)[0], abs=1e-6)
    assert abs(reference[2].p1[1] - target[2].p1[1]) == pytest.approx(30.0, abs=1e-6)
