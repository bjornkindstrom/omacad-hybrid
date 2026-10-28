"""The incremental recompute cache must never hand out stale copies of the user's work."""
from omacad.model.document import Document


def _sketch_with_extrude():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5.0)
    return doc, sk.sketch_id


def test_sketch_edit_after_cached_recompute_is_kept():
    doc, sid = _sketch_with_extrude()
    doc.timeline.recompute(doc)
    doc.timeline.recompute(doc)          # second run restores the sketch step from the cache
    sk = doc.edit_sketch(sid)
    sk.add_rect((20, 0), (30, 10))
    doc.finish_sketch()
    assert len(doc.sketches[sid].entities) == 8
    assert len(doc.sketches[sid].profiles) == 2
    feat = next(f for f in doc.timeline.features if f.feature_type == "sketch")
    assert doc.sketches[sid] is feat.sketch


def test_new_step_at_a_rolled_back_marker_is_inserted_and_later_steps_stay():
    doc = Document()
    doc.add_box(10, 10, 10)
    doc.add_cylinder(5, 10)
    doc.add_box(20, 20, 20)
    later = [f.feature_id for f in doc.timeline.features[1:]]
    doc.timeline.step_to(1, doc)
    doc.add_cylinder(2, 3)
    ids = [f.feature_id for f in doc.timeline.features]
    assert ids[2:] == later and len(ids) == 4
    assert doc.timeline.marker_index == 2
    doc.timeline.fast_forward(doc)
    assert len(doc.bodies) == 4


def test_new_curve_smoothness_rebuilds_cached_steps():
    from omacad.model import quality
    old = quality.circle_segments()
    try:
        quality.set_circle_segments(48)
        doc = Document()
        doc.add_cylinder(5, 10)
        doc.timeline.recompute(doc)
        quality.set_circle_segments(192)
        doc.timeline.recompute(doc)
        verts = len(next(iter(doc.bodies.values())).manifold.to_mesh().vert_properties)
        assert verts == 2 * 192
    finally:
        quality.set_circle_segments(old)


def test_undo_runs_the_steps_again_so_their_results_are_there():
    """A thread following its host measures it while it runs; after undo the new step object must have it too."""
    doc = Document()
    doc.add_cylinder(20.0, 10.0)
    cyl = next(iter(doc.bodies))
    doc.add_thread(diameter=39.99, pitch=3.0, length=8.0, target_body_id=cyl, operation="join", profile="round",
                   plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0],
                   host_length=10.0, follow_host=True, host_offset=-0.01)
    doc.timeline.recompute(doc)
    before = doc.timeline.features[-1]._effective
    assert before is not None
    doc.add_box(5, 5, 5)
    doc.undo()
    assert doc.timeline.features[-1]._effective == before


def test_the_model_is_built_at_full_quality_even_if_interactive_mode_was_left_on():
    from omacad.model import quality
    doc = Document()
    doc.add_cylinder(5, 10)
    quality.set_interactive_mode(True)          # e.g. a drag whose release was lost
    try:
        doc.timeline.clear_cache()
        doc.timeline.recompute(doc)
        verts = len(next(iter(doc.bodies.values())).manifold.to_mesh().vert_properties)
        assert verts == 2 * quality.DEFAULT_SEGMENTS      # full quality (interactive would give 2 * 32)
        assert quality.is_interactive_mode()    # the flag itself is left as it was
    finally:
        quality.set_interactive_mode(False)


def test_a_new_step_is_built_at_full_quality_even_if_interactive_mode_was_left_on():
    from omacad.model import quality
    doc = Document()
    quality.set_interactive_mode(True)
    try:
        doc.add_cylinder(5, 10)
        verts = len(next(iter(doc.bodies.values())).manifold.to_mesh().vert_properties)
        assert verts == 2 * quality.DEFAULT_SEGMENTS and quality.is_interactive_mode()
    finally:
        quality.set_interactive_mode(False)
