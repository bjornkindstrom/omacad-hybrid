"""Björn #56/#58: on a sketch on the lid (top or bottom face) the outline came in as ~190 tiny lines whose rounded
corners stopped 0.01 mm short of the straight edges, plus mesh seams. One click picked only part of the outline,
the offset lost the corner radius and the sketch found no closed profile. Now the outline is 4 lines + 4 arcs that
share their ends, and an inward offset keeps the radius (R5 - 2 = R3)."""
from pathlib import Path

from omacad.io.exporter import Exporter

DOC = str(Path(__file__).parent / "data" / "lid_face_outline.omacad")


def _face_sketch(sketch_id):
    doc = Exporter.load_project(DOC)
    sk = doc.start_sketch_on_plane(doc.sketches[sketch_id].plane)
    return sk, [e for e in sk.entities if getattr(e, "projected", False)]


def test_lid_outline_is_lines_and_arcs_in_one_chain():
    for sketch_id in ("sketch_5", "sketch_3"):     # top and underside of the lid
        sk, proj = _face_sketch(sketch_id)
        assert sorted(e.entity_type for e in proj) == ["arc"] * 4 + ["line"] * 4
        assert sk.connected_entities(proj[0].entity_id) == {e.entity_id for e in proj}


def test_inward_offset_keeps_the_radius():
    sk, proj = _face_sketch("sketch_5")
    new = sk.offset_entities([e.entity_id for e in proj], -2.0)
    assert sorted(e.entity_type for e in new) == ["arc"] * 4 + ["line"] * 4
    want = 86 * 56 - (4 - 3.141592653589793) * 3 ** 2      # the offset outline as a filled profile
    assert any(abs(p.area - want) < 0.5 for p in sk.profiles), sorted(round(p.area, 1) for p in sk.profiles if p.area > 1)
