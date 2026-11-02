"""Tests for the Cool small box sliding lid design (problem report 20261101-202026).
Clean sliding lid with side V-grooves matching triangular wall rails,
lowered front entry sill, solid back stop, compliant thumb slot, raised grip rib,
and underside snap pip with 0 collision and exact inner usable height measurement.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document, box_row_outer_height, box_row_inner_height
from omacad.io.exporter import Exporter


def test_cool_small_box_geometry_and_clearance():
    QApplication.instance() or QApplication([])
    doc = Document()
    # Nominal dimensions matching 70 x 45 x 15 mm box
    inner_z = 11.0
    bot_t = 1.5
    wall_t = 2.0
    lip_h = 2.26
    c = 0.2
    outer_h = box_row_outer_height(inner_z, bot_t, wall_t, has_lid=True, lip_height=lip_h, clearance=c)

    bodies = doc.add_box_row(
        count=1,
        length=71.0,
        width=46.0,
        height=inner_z,
        wall_thickness=wall_t,
        bottom_thickness=bot_t,
        outer_round=5.0,
        outer_round_kind="fillet",
        inner_round=3.0,
        inner_round_kind="fillet",
        has_lid=True,
        lip_height=lip_h,
        lip_step=1.0,
        clearance=c,
        tab_size=3.0,
    )
    assert len(bodies) == 2
    box = bodies[0]
    lid = bodies[1]

    assert box.manifold.status().name == "NoError"
    assert lid.manifold.status().name == "NoError"
    assert box.manifold.volume() > 8000
    assert lid.manifold.volume() > 4000

    # Overlap between box and lid must be 0 (collision-free sliding fit)
    overlap = (box.manifold ^ lid.manifold).volume()
    assert overlap < 1e-3

    # Check bounds
    bb_box = box.manifold.bounding_box()
    bb_lid = lid.manifold.bounding_box()

    # Outer footprint
    assert abs((bb_box[3] - bb_box[0]) - 71.0) < 1e-3
    assert abs((bb_box[4] - bb_box[1]) - 46.0) < 1e-3
    assert abs((bb_box[5] - bb_box[2]) - outer_h) < 1e-3

    # Lid sits inside the box:
    # Underside of lid sits at z = bot_t + inner_z
    lid_underside_z = min(f.origin[2] for f in lid.faces if f.normal[2] < -0.99)
    floor_z = bb_box[2] + bot_t
    usable_h = lid_underside_z - floor_z
    assert abs(usable_h - inner_z) < 1e-3, f"Expected {inner_z}, got {usable_h}"

    # Main flat plate of lid is flush with the top of the box (within clearance)
    lid_plate_top_z = max(f.origin[2] for f in lid.faces if f.normal[2] > 0.99 and f.area > 500)
    box_top_z = bb_box[5]
    assert lid_plate_top_z <= box_top_z + 1e-3
    assert box_top_z - lid_plate_top_z < 0.5


def test_cool_small_box_from_user_feedback_report():
    """Verify loading the user feedback report project and re-building box in a row."""
    QApplication.instance() or QApplication([])
    feedback_file = "/home/kindstrom/Work/omacad-hybrid/.state/data/feedback/20261101-202026/document.omacad"
    if os.path.exists(feedback_file):
        rep_doc = Exporter.load_project(feedback_file)
        assert len(rep_doc.bodies) >= 2
        for bid, b in rep_doc.bodies.items():
            assert b.manifold.status().name == "NoError"
            assert b.manifold.volume() > 0


def test_cool_small_box_chamfer_and_honeycomb():
    """Test box with chamfered corners and honeycomb floor."""
    QApplication.instance() or QApplication([])
    doc = Document()
    bodies = doc.add_box_row(
        count=2,
        length=60.0,
        width=40.0,
        height=20.0,
        wall_thickness=2.0,
        bottom_thickness=2.0,
        outer_round=3.0,
        outer_round_kind="chamfer",
        inner_round=1.0,
        inner_round_kind="chamfer",
        has_lid=True,
        honeycomb=True,
        honeycomb_size=4.0,
        lip_height=2.2,
        clearance=0.2,
    )
    assert len(bodies) == 4
    for b in bodies:
        assert b.manifold.status().name == "NoError"
        assert b.manifold.volume() > 0
    # Overlap of each pair is 0
    assert (bodies[0].manifold ^ bodies[1].manifold).volume() < 1e-3
    assert (bodies[2].manifold ^ bodies[3].manifold).volume() < 1e-3


def test_box_lid_lead_in_chamfer_and_feedback_report():
    """Verify lead-in chamfer on the insertion end of the slide lid (problem report 20261102-183235)."""
    QApplication.instance() or QApplication([])

    # 1. Feedback report reproduction
    feedback_file = "/home/kindstrom/Work/omacad-hybrid/.state/data/feedback/20261102-183235/document.omacad"
    if os.path.exists(feedback_file):
        rep_doc = Exporter.load_project(feedback_file)
        rep_doc.timeline.recompute(rep_doc)
        box = rep_doc.bodies["body_box_1"]
        lid = rep_doc.bodies["body_box_2"]
        assert box.manifold.status().name == "NoError"
        assert lid.manifold.status().name == "NoError"
        assert (box.manifold ^ lid.manifold).volume() < 1e-3
        # Check that the lid's insertion corners are chamfered
        m = lid.manifold.to_mesh()
        min_x = min(v[0] for v in m.vert_properties)
        max_y = max(v[1] for v in m.vert_properties)
        back_y = max(v[1] for v in m.vert_properties if abs(v[0] - min_x) < 0.05)
        assert back_y < max_y - 0.5, f"Expected chamfer on back corners: back_y={back_y}, max_y={max_y}"

    # 2. Creating Box in a row with inner chamfer passes to the lid
    doc = Document()
    bodies = doc.add_box_row(
        count=1,
        length=60.0,
        width=40.0,
        height=30.0,
        wall_thickness=2.0,
        bottom_thickness=2.0,
        outer_round=2.0,
        outer_round_kind="fillet",
        inner_round=1.0,
        inner_round_kind="chamfer",
        has_lid=True,
        lip_height=2.2,
        lip_step=1.0,
        clearance=0.2,
    )
    box, lid = bodies[0], bodies[1]
    lid_feat = doc.timeline.features[1]
    assert lid_feat.inner_round == 1.0
    assert lid_feat.inner_round_kind == "chamfer"

    m = lid.manifold.to_mesh()
    min_x = min(v[0] for v in m.vert_properties)
    max_y = max(v[1] for v in m.vert_properties)
    back_y = max(v[1] for v in m.vert_properties if abs(v[0] - min_x) < 0.05)
    assert back_y < max_y - 0.5, f"Expected chamfered back corners: back_y={back_y}, max_y={max_y}"
    assert (box.manifold ^ lid.manifold).volume() < 1e-3

    # 3. Default inner_round=0 still provides a lead-in chamfer to ease insertion
    doc_sq = Document()
    sq_bodies = doc_sq.add_box_row(count=1, inner_round=0.0, outer_round=0.0, has_lid=True)
    sq_box, sq_lid = sq_bodies[0], sq_bodies[1]
    m_sq = sq_lid.manifold.to_mesh()
    min_x = min(v[0] for v in m_sq.vert_properties)
    max_y = max(v[1] for v in m_sq.vert_properties)
    back_y = max(v[1] for v in m_sq.vert_properties if abs(v[0] - min_x) < 0.05)
    assert back_y < max_y - 0.5, f"Expected default lead-in chamfer on square box lid: back_y={back_y}, max_y={max_y}"
    assert (sq_box.manifold ^ sq_lid.manifold).volume() < 1e-3

    # 4. update_box_row_group propagates inner_round and inner_round_kind to lids
    gid = doc.object_groups[0]["id"]
    doc.update_box_row_group(gid, inner_round=1.5, inner_round_kind="chamfer")
    assert doc.timeline.features[1].inner_round == 1.5
    assert doc.timeline.features[1].inner_round_kind == "chamfer"

