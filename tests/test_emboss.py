"""Emboss (Fusion's): text on a face raised by a depth (Emboss) or pressed in (Deboss), with exact volumes."""
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane

BOX = (60.0, 40.0, 10.0)


def _scene(text="HI", height=12.0, anchor=(0.0, 0.0), **kw):
    doc = Document()
    doc.add_box(*BOX, center="bottom_center")
    body = next(iter(doc.bodies))
    top = max(doc.bodies[body].faces, key=lambda f: f.normal[2])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(top.normal, top.origin))
    t = sk.add_text(text, anchor, height=height, h_align="center", v_align="middle", **kw)
    doc.finish_sketch()
    return doc, body, sk, t


def _text_profiles(sk):
    return sk.text_profile_indices()


def _volume(doc, body):
    return doc.bodies[body].manifold.volume()


def test_text_profile_indices_are_the_letters_not_the_counters():
    doc, body, sk, t = _scene("O")
    idx = _text_profiles(sk)
    assert len(idx) == 1 and sk.profiles[idx[0]].interior_holes          # the ring, with its counter as a hole
    assert len(sk.profiles) == 3                          # the face's own outline, the ring and the counter inside it


def test_emboss_adds_the_exact_volume_and_deboss_removes_it():
    doc, body, sk, t = _scene("HI")
    idx = _text_profiles(sk)
    area = t.geometry().area
    base = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 1.5, extra_profiles=idx[1:])
    assert _volume(doc, body) == pytest.approx(base + area * 1.5, rel=2e-3)
    assert len(doc.bodies) == 1                                          # joined to the box
    top = doc.bodies[body].manifold.bounding_box()[5]
    assert top == pytest.approx(BOX[2] + 1.5, abs=1e-3)                  # raised outwards
    doc.undo()
    assert _volume(doc, body) == pytest.approx(base, rel=1e-9)
    doc.add_emboss(sk.sketch_id, idx[0], -2.0, extra_profiles=idx[1:])    # a negative depth is Deboss
    assert _volume(doc, body) == pytest.approx(base - area * 2.0, rel=2e-3)
    assert doc.bodies[body].manifold.bounding_box()[5] == pytest.approx(BOX[2], abs=1e-6)


def test_the_counter_of_an_o_stays_open_when_embossed():
    doc, body, sk, t = _scene("O", height=20.0)
    idx = _text_profiles(sk)
    base = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 1.0)
    assert _volume(doc, body) == pytest.approx(base + t.geometry().area * 1.0, rel=2e-3)   # the ring, not the disc


def test_flip_goes_the_other_way_and_shift_and_turn_move_the_text():
    doc, body, sk, t = _scene("HI")
    idx = _text_profiles(sk)
    doc.add_emboss(sk.sketch_id, idx[0], 1.0, flip=True, extra_profiles=idx[1:])
    # flipped: the letters stand on the face's other side (they hang into the box = nothing to join to, so a new body)
    assert doc.bodies[body].manifold.bounding_box()[5] == pytest.approx(BOX[2], abs=1e-6)
    doc2, body2, sk2, t2 = _scene("HI")
    idx2 = _text_profiles(sk2)
    doc2.add_emboss(sk2.sketch_id, idx2[0], 1.0, dx=10.0, dy=5.0, extra_profiles=idx2[1:])
    top = doc2.bodies[body2].manifold
    letters = top.trim_by_plane((0, 0, 1), BOX[2] + 0.5)             # only what stands above the face
    x0, y0, _, x1, y1, _ = letters.bounding_box()
    bx0, by0, bx1, by1 = t2.bbox()
    assert (x0, y0, x1, y1) == pytest.approx((bx0 + 10.0, by0 + 5.0, bx1 + 10.0, by1 + 5.0), abs=0.05)
    doc3, body3, sk3, t3 = _scene("HI")
    idx3 = _text_profiles(sk3)
    doc3.add_emboss(sk3.sketch_id, idx3[0], 1.0, rotation=90.0, extra_profiles=idx3[1:])
    r = doc3.bodies[body3].manifold.trim_by_plane((0, 0, 1), BOX[2] + 0.5).bounding_box()
    assert (r[3] - r[0], r[4] - r[1]) == pytest.approx((t3.bbox()[3] - t3.bbox()[1], t3.bbox()[2] - t3.bbox()[0]), abs=0.1)


def test_save_load_and_edit_keep_working():
    doc, body, sk, t = _scene("HI")
    idx = _text_profiles(sk)
    v0 = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 1.0, extra_profiles=idx[1:])
    feat = doc.timeline.features[-1]
    assert feat.feature_type == "emboss" and feat.effect == "emboss"
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    assert loaded.timeline.features[-1].feature_type == "emboss"
    assert next(iter(loaded.bodies.values())).manifold.volume() == pytest.approx(_volume(doc, body), rel=1e-9)
    doc.edit_feature(len(doc.timeline.features) - 1, depth=-1.0)          # edit it from the timeline: now a deboss
    assert doc.timeline.features[-1].effect == "deboss"
    assert _volume(doc, body) == pytest.approx(v0 - t.geometry().area * 1.0, rel=2e-3)


def test_emboss_on_text_along_a_circle():
    doc = Document()
    doc.add_cylinder(20.0, 6.0, name="Coin")
    body = next(iter(doc.bodies))
    top = max(doc.bodies[body].faces, key=lambda f: f.normal[2])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(top.normal, top.origin).centered_on(top.tris))
    ring = sk.add_circle((0.0, 0.0), 14.0, is_construction=True)
    t = sk.add_text("COIN * TEXT *", height=4.0, path_id=ring.entity_id, h_align="center")
    doc.finish_sketch()
    idx = sk.text_profile_indices()
    assert idx
    base = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 0.8, extra_profiles=idx[1:])
    assert _volume(doc, body) == pytest.approx(base + t.geometry().area * 0.8, rel=3e-3)


def test_embossed_letter_can_be_copied_round_a_circle_with_the_pattern_tool():
    """'Circular pattern' of an Emboss step: six copies of the letter round the coin."""
    doc = Document()
    doc.add_cylinder(20.0, 6.0, name="Coin")
    body = next(iter(doc.bodies))
    top = max(doc.bodies[body].faces, key=lambda f: f.normal[2])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(top.normal, top.origin))
    t = sk.add_text("A", (14.0, 0.0), height=4.0, h_align="center", v_align="middle")
    doc.finish_sketch()
    idx = sk.text_profile_indices()
    base = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 0.8, extra_profiles=idx[1:])
    one = _volume(doc, body) - base
    assert one == pytest.approx(t.geometry().area * 0.8, rel=3e-3)
    emboss_id = doc.timeline.features[-1].feature_id
    doc.add_pattern([emboss_id], "circular", count1=6, angle=360.0, about="body")
    assert _volume(doc, body) == pytest.approx(base + 6 * one, rel=5e-3)
