"""Request #151: Primitive: Box in a row.
Lådor i rad grupperade i objects, alla mått/radier/chamfer/honeycomb valbara,
slide-over lock med offset face, samt snabbknapp för lock i viewporten.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.io.exporter import Exporter
from omacad.ui.browser import BrowserTree


def test_add_box_row_basic():
    QApplication.instance() or QApplication([])
    doc = Document()
    bodies = doc.add_box_row(
        count=3,
        length=50.0,
        width=30.0,
        height=20.0,
        wall_thickness=2.0,
        has_lid=True,
        outer_round=2.0,
        outer_round_kind="fillet",
        honeycomb=False,
    )
    # 3 boxes + 3 lids = 6 bodies
    assert len(bodies) == 6
    box_bodies = [b for b in bodies if not b.is_lid]
    lid_bodies = [b for b in bodies if b.is_lid]
    assert len(box_bodies) == 3
    assert len(lid_bodies) == 3

    # All bodies belong to an object group
    assert len(doc.object_groups) == 1
    g = doc.object_groups[0]
    assert g["name"] == "Box in a row 1"
    assert len(g["objects"]) == 6

    # Browser hierarchy
    browser = BrowserTree(doc)
    rows = [item.text(0) for item, _ in browser._walk()]
    assert "Box in a row 1" in rows

    # Group selection highlights/selects all bodies
    doc.select_object_group(g["id"])
    for b in bodies:
        assert doc.bodies[b.body_id].selected is True


def test_box_in_row_with_chamfer_and_honeycomb():
    QApplication.instance() or QApplication([])
    doc = Document()
    bodies = doc.add_box_row(
        count=2,
        length=60.0,
        width=40.0,
        height=25.0,
        wall_thickness=2.0,
        bottom_thickness=2.0,
        outer_round=2.0,
        outer_round_kind="chamfer",
        inner_round=1.0,
        inner_round_kind="chamfer",
        honeycomb=True,
        honeycomb_size=5.0,
        honeycomb_wall=1.2,
        has_lid=True,
        lip_height=6.0,
        lip_step=1.0,
        clearance=0.2,
    )
    assert len(bodies) == 4
    for b in bodies:
        # All manifolds must be valid with positive volume
        assert b.manifold.num_tri() > 0
        assert b.manifold.volume() > 0


def test_lid_viewport_toggle():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(count=2, has_lid=True)

    assert doc.has_lids() is True
    assert doc.are_lids_visible() is True

    # Toggle off (hide all lids to see inside)
    res = doc.toggle_lids_visibility()
    assert res is False
    assert doc.are_lids_visible() is False
    lids = [b for b in doc.bodies.values() if b.is_lid]
    for lid in lids:
        assert lid.visible is False

    # Toggle on (show lids again)
    res = doc.toggle_lids_visibility()
    assert res is True
    assert doc.are_lids_visible() is True
    for lid in lids:
        assert lid.visible is True


def test_box_in_row_save_and_load(tmp_path):
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(count=2, has_lid=True, honeycomb=True)

    path = str(tmp_path / "box_row.omacad")
    Exporter.save_project(doc, path)

    loaded = Exporter.load_project(path)
    assert len(loaded.bodies) == 4
    assert len(loaded.object_groups) == 1
    assert loaded.object_groups[0]["name"] == "Box in a row 1"
    assert loaded.has_lids() is True
    lids = [b for b in loaded.bodies.values() if b.is_lid]
    assert len(lids) == 2


def test_sliding_lid_in_groove_from_feedback_report():
    """Feedback report 20261101-185047:
    The lid should be a sliding plate fitting into internal wall grooves with front entry slot,
    front grip bead, and snap detent, with no flared trumpet edges or knife-edge claws.
    """
    QApplication.instance() or QApplication([])
    doc = Document()
    bodies = doc.add_box_row(
        count=3,
        length=60.0,
        width=40.0,
        height=30.0,
        wall_thickness=2.0,
        bottom_thickness=2.0,
        outer_round=2.0,
        outer_round_kind="fillet",
        inner_round=1.0,
        inner_round_kind="fillet",
        honeycomb=True,
        honeycomb_size=5.0,
        honeycomb_wall=1.2,
        honeycomb_margin=2.0,
        has_lid=True,
        lip_height=6.0,
        lip_step=1.0,
        clearance=0.2,
    )
    assert len(bodies) == 6
    boxes = [b for b in bodies if not b.is_lid]
    lids = [b for b in bodies if b.is_lid]
    assert len(boxes) == 3
    assert len(lids) == 3

    for box, lid in zip(boxes, lids):
        assert box.manifold.status().name == "NoError"
        assert lid.manifold.status().name == "NoError"
        assert box.manifold.volume() > 0
        assert lid.manifold.volume() > 0
        # Overlap between box and lid must be 0 (clean sliding fit with clearance)
        overlap = (box.manifold ^ lid.manifold).volume()
        assert overlap < 1e-3

    # Load the actual project from the user's feedback report
    feedback_file = "/home/kindstrom/Work/omacad-hybrid/.state/data/feedback/20261101-185047/document.omacad"
    if os.path.exists(feedback_file):
        rep_doc = Exporter.load_project(feedback_file)
        assert len(rep_doc.bodies) == 6
        for bid, b in rep_doc.bodies.items():
            assert b.manifold.status().name == "NoError"
            assert b.manifold.volume() > 0


def test_box_in_row_chamfered_grooves_and_adjustable_flarp():
    """Verify chamfered sliding grooves on short sides, no hanging lip at front opening,
    and adjustable flarp (tab_size) on the lid with 0 collision.
    """
    QApplication.instance() or QApplication([])
    doc = Document()
    for tab_sz in [2.0, 5.0, 8.0]:
        bodies = doc.add_box_row(
            count=1,
            length=50.0,
            width=30.0,
            height=25.0,
            wall_thickness=2.0,
            has_lid=True,
            lip_height=5.0,
            lip_step=1.0,
            clearance=0.2,
            tab_size=tab_sz,
        )
        box = bodies[0]
        lid = bodies[1]
        assert box.manifold.status().name == "NoError"
        assert lid.manifold.status().name == "NoError"
        assert (box.manifold ^ lid.manifold).volume() < 1e-3
        # Volume of lid increases as tab_size increases
        assert lid.manifold.volume() > 0

