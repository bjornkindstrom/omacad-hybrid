"""Box in a row primitive modeling, lids, outer rounds, and group settings tests."""
import math
import os
from pathlib import Path

import numpy as np
import pytest
import manifold3d as m3d
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document, box_row_outer_height, box_row_inner_height
from omacad.model.features.primitives import BoxFeature
from omacad.ui.history_delegate import apply_dimension

DATA_DIR = Path(__file__).parent / "data"

BOX_CFG = dict(center="bottom_center", length=60.0, width=40.0, height=34.1, wall_thickness=2.0,
               bottom_thickness=2.0, outer_round=2.0, inner_round=1.0, lip_height=2.2, lip_step=1.0, clearance=0.2)


# ==============================================================================
# Outer Round Steiner Volume & Hull (Report 20261031-091740)
# ==============================================================================

def _rounded_box_volume(L, W, H, r):
    a, b, c = L - 2 * r, W - 2 * r, H - 2 * r
    return a * b * c + 2 * r * (a * b + b * c + c * a) + math.pi * r * r * (a + b + c) + 4 / 3 * math.pi * r ** 3


@pytest.mark.parametrize("r", [2.0, 5.0, 10.0])
def test_outer_round_volume_matches_the_rolling_ball_shape(r):
    solid = BoxFeature("b", "b", 50.0, 50.0, 25.0, center="bottom_center", outer_round=r).build_solid()
    assert solid.volume() == pytest.approx(_rounded_box_volume(50, 50, 25, r), rel=1e-3)
    assert solid.genus() == 0
    assert solid.bounding_box() == pytest.approx((-25, -25, 0, 25, 25, 25))


def test_outer_round_is_light_and_smooth_not_a_stack_of_slabs():
    solid = BoxFeature("b", "b", 50.0, 50.0, 25.0, center="bottom_center", outer_round=2.0).build_solid()
    assert solid.num_tri() < 6000


def test_report_document_rebuilds_the_box_light():
    doc_path = DATA_DIR / "box_outer_round_browser.omacad"
    if not doc_path.exists():
        pytest.skip("box_outer_round_browser.omacad not present")
    doc = Exporter.load_project(str(doc_path))
    body = doc.bodies["body_box_1"]
    assert body.manifold.volume() == pytest.approx(61159, rel=2e-3)
    assert body.manifold.num_tri() < 8000


# ==============================================================================
# Rails, Detents & Slots (Reports 20261101-205314, 20261101-221011, #161, #162)
# ==============================================================================

def test_front_rail_stub_is_gone():
    s = BoxFeature("b", "Box", snap_size=0.8, **BOX_CFG).build_solid()
    z = 34.1 - 2.2 + 1.0
    for poly in s.slice(z).to_polygons():
        pts = poly[(poly[:, 0] > 27.1) & (np.abs(poly[:, 1]) < 18.9)]
        assert len(pts) == 0, pts


def test_slot_size_is_adjustable():
    def lid(**kw):
        f = BoxFeature("l", "Lid", is_lid=True, **BOX_CFG, **kw)
        return f.build_solid()
    auto, big, wide = lid(), lid(slot_length=20.0, slot_width=5.0), lid(slot_length=20.0, slot_width=8.0)
    assert big.volume() < auto.volume()
    assert wide.volume() < big.volume()
    dv = big.volume() - wide.volume()
    assert dv > 0 and abs(dv) < 20.0 * 3.0 * 4.0
    assert BoxFeature("l", "Lid", is_lid=True, slot_length=20, slot_width=5, **BOX_CFG).to_dict()["slot_width"] == 5.0


def test_snap_detent_is_gone_from_box_and_lid():
    for is_lid in (False, True):
        a = BoxFeature("a", "A", snap_size=0.6, is_lid=is_lid, **BOX_CFG).build_solid()
        b = BoxFeature("b", "B", snap_size=1.5, is_lid=is_lid, **BOX_CFG).build_solid()
        assert abs(a.volume() - b.volume()) < 1e-6


def test_groove_back_corners_are_chamfered_only_at_lid_level():
    box = BoxFeature("b", "B", **BOX_CFG).build_solid()
    x_back, y_edge = -(60.0 - 4.0) / 2.0, 40.0 / 2.0 - 2.0 + 1.0
    z_lid = 34.1 - 2.2 + 0.1

    def probe(z, x0, y0, size=0.3):
        sq = m3d.CrossSection.square((size, size)).translate((x0, y0))
        return (box.slice(z) ^ sq).area()

    assert probe(z_lid, x_back, y_edge - 0.3) > 0.08
    assert probe(z_lid, x_back, -y_edge) > 0.08
    assert probe(z_lid, x_back + 2.5, y_edge - 0.3) < 1e-6
    assert probe(10.0, x_back, 17.7) < 0.09


def test_honeycomb_cuts_walls_and_lid():
    box30 = dict(center="bottom_center", length=60.0, width=40.0, height=30.0, wall_thickness=2.0,
                 bottom_thickness=2.0, outer_round=2.0, inner_round=1.0, lip_height=2.2, lip_step=1.0, clearance=0.2)
    plain_box = BoxFeature("b", "B", **box30).build_solid()
    hc_box = BoxFeature("b", "B", honeycomb=True, honeycomb_size=5.0, honeycomb_wall=1.2, **box30).build_solid()
    assert hc_box.volume() < plain_box.volume()
    assert hc_box.slice(10.0).area() < plain_box.slice(10.0).area() - 5.0

    plain_lid = BoxFeature("l", "L", is_lid=True, **box30).build_solid()
    hc_lid = BoxFeature("l", "L", is_lid=True, honeycomb=True, honeycomb_size=5.0, honeycomb_wall=1.2, **box30).build_solid()
    assert hc_lid.volume() < plain_lid.volume() * 0.9


def test_honeycomb_is_editable_in_box_row_settings():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(count=2, length=60.0, width=40.0, height=30.0, has_lid=True)
    gid = doc.object_groups[0]["id"]
    assert doc.box_row_group_params(gid)["honeycomb"] is False
    boxes, lids = doc.box_row_features(gid)
    assert apply_dimension(doc, "group_param", (gid, "honeycomb"), "1") is True
    assert doc.box_row_group_params(gid)["honeycomb"] is True
    assert apply_dimension(doc, "group_param", (gid, "honeycomb_size"), "6") is True
    boxes, lids = doc.box_row_features(gid)
    assert all(f.honeycomb and f.honeycomb_size == 6.0 for f in boxes + lids)
    assert apply_dimension(doc, "group_param", (gid, "honeycomb"), "0") is True
    assert not any(f.honeycomb for f in doc.box_row_features(gid)[0])


# ==============================================================================
# Box Row Generation & Document Integration
# ==============================================================================

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
    assert len(bodies) == 6
    box_bodies = [b for b in bodies if not b.is_lid]
    lid_bodies = [b for b in bodies if b.is_lid]
    assert len(box_bodies) == 3
    assert len(lid_bodies) == 3
    assert len(doc.object_groups) == 1
    g = doc.object_groups[0]
    assert g["name"] == "Box in a row 1"
    assert len(g["objects"]) == 6

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
        assert b.manifold.num_tri() > 0
        assert b.manifold.volume() > 0


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
        overlap = (box.manifold ^ lid.manifold).volume()
        assert overlap < 1e-3


def test_box_in_row_chamfered_grooves_and_adjustable_flarp():
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
        box, lid = bodies[0], bodies[1]
        assert box.manifold.status().name == "NoError"
        assert lid.manifold.status().name == "NoError"
        assert (box.manifold ^ lid.manifold).volume() < 1e-3
        assert lid.manifold.volume() > 0


# ==============================================================================
# Height Z Calculation & Flat Lid
# ==============================================================================

def test_height_z_clear_distance_calculation():
    QApplication.instance() or QApplication([])
    doc = Document()
    inner_z = 35.0
    wall_t = 2.0
    bot_t = 2.5
    lip_h = 6.0
    clearance = 0.2
    outer_h = box_row_outer_height(
        inner_z,
        bottom_thickness=bot_t,
        wall_thickness=wall_t,
        has_lid=True,
        lip_height=lip_h,
        clearance=clearance,
    )
    z_floor = bot_t
    z_g = outer_h - lip_h
    z_lid_bottom = z_g + clearance / 2.0
    assert abs((z_lid_bottom - z_floor) - inner_z) < 1e-6
    assert abs(box_row_inner_height(outer_h, bot_t, wall_t, True, lip_h, clearance) - inner_z) < 1e-6

    bodies = doc.add_box_row(
        count=1,
        length=50.0,
        width=40.0,
        height=inner_z,
        wall_thickness=wall_t,
        bottom_thickness=bot_t,
        has_lid=True,
        lip_height=lip_h,
        clearance=clearance,
    )
    box, lid = bodies[0], bodies[1]
    box_bounds = box.manifold.bounding_box()
    lid_bounds = lid.manifold.bounding_box()
    assert abs((box_bounds[5] - box_bounds[2]) - outer_h) < 1e-3
    assert lid_bounds[2] >= box_bounds[2]
    assert lid_bounds[5] <= box_bounds[5] + 1e-2

    outer_h_no_lid = box_row_outer_height(inner_z, bot_t, wall_t, has_lid=False)
    assert abs((outer_h_no_lid - bot_t) - inner_z) < 1e-6


def test_lid_is_flat_without_raised_rib():
    QApplication.instance() or QApplication([])
    doc = Document()
    bodies = doc.add_box_row(
        count=1,
        length=60.0,
        width=40.0,
        height=30.0,
        wall_thickness=2.0,
        bottom_thickness=2.0,
        has_lid=True,
        lip_height=2.2,
        clearance=0.2,
        snap_size=0.6,
    )
    box, lid = bodies[0], bodies[1]
    bb_box = box.manifold.bounding_box()
    bb_lid = lid.manifold.bounding_box()
    assert bb_lid[5] <= bb_box[5] + 1e-3
    gid = doc.object_groups[0]["id"]
    box_feats, lid_feats = doc.box_row_features(gid)
    box_after = doc.bodies[f"body_{box_feats[0].feature_id}"]
    lid_after = doc.bodies[f"body_{lid_feats[0].feature_id}"]
    assert (box_after.manifold ^ lid_after.manifold).volume() < 1e-3
