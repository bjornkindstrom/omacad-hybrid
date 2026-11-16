"""Regression tests for #234 (rotate handles X/Y full turns) and #241 (split body with lip joint)."""
import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.viewport.resize(900, 700)
    return w


def _drag_circle(vp, rh, pos, tangent, centre_s, turns=1.5, steps=72):
    dx0, dy0 = pos[0] - centre_s[0], pos[1] - centre_s[1]
    radius = math.hypot(dx0, dy0)
    theta0 = math.atan2(dy0, dx0)
    ccw_dir = np.array([-dy0, dx0]) / radius
    sign = 1.0 if float(np.dot(ccw_dir, tangent)) >= 0 else -1.0
    angles = [0.0]
    for i in range(1, steps + 1):
        theta = theta0 + sign * (turns * 2.0 * math.pi) * (i / steps)
        rh.move(centre_s[0] + radius * math.cos(theta), centre_s[1] + radius * math.sin(theta))
        angles.append(rh.drag["angle"])
    return angles


@pytest.mark.parametrize("azimuth, axis_name, move_attr, expected_mode", [
    (355.9, "Y", "ry", "plane"),    # Lennart's camera: Y in plane mode
    (355.9, "X", "rx", "linear"),   # Lennart's camera: X edge-on in linear mode
    (335.0, "X", "rx", "screen"),   # Oblique X in screen mode (0.15 <= |denom| < 0.5)
])
def test_rotate_handles_xy_full_turn_from_lennarts_camera(win, azimuth, axis_name, move_attr, expected_mode):
    """#234: dragging X or Y handle grows angle monotonically past 360° without mode-switching or wrapping."""
    doc, vp = win.doc, win.viewport
    bid = doc.add_box(50, 50, 25).body_id
    doc.selected_body_ids = [bid]
    vp.azimuth = azimuth
    vp.elevation = -34.2
    vp.distance = 135.0
    vp.target = np.array([25.0, 25.0, 12.5])

    rh = vp.rotate_handles
    pos, tangent, _out = rh.handles()[axis_name]
    lo = np.asarray(doc.bodies[bid].render_mesh.bounds_min, float)
    hi = np.asarray(doc.bodies[bid].render_mesh.bounds_max, float)
    centre_s = vp.project_points(np.array([(lo + hi) / 2.0]))[0][0]

    assert rh.press(*pos)
    assert rh.drag["mode"] == expected_mode

    if expected_mode == "linear":
        angles = [0.0]
        for i in range(1, 41):
            rh.move(*(pos + tangent * (20.0 * i)))
            angles.append(rh.drag["angle"])
    else:
        angles = _drag_circle(vp, rh, pos, tangent, centre_s)

    assert all(b >= a for a, b in zip(angles, angles[1:])), f"non-monotonic angles: {angles}"
    assert angles[-1] > 360.0

    assert rh.release()
    move = doc.timeline.features[-1]
    assert move.feature_type == "move"
    assert getattr(move, move_attr) == angles[-1]
    assert move.pivot == "center"


def test_split_body_with_lip_joint(tmp_path):
    """#241: split_body with lip adds a mating lip on one half and a clearance pocket on the other."""
    from omacad.io.exporter import Exporter
    from omacad.model.document import Document

    doc = Document()
    jar = doc.add_cylinder(20.0, 19.0, center=False)
    doc.add_shell(jar.body_id, 4.0)
    plane_id = doc.add_construction_plane(doc.origin_planes["XY"], 9.0)

    # Half volumes before lip
    raw_lower = doc.bodies[jar.body_id].manifold.trim_by_plane(np.array([0.0, 0.0, -1.0]), -9.0)
    raw_upper = doc.bodies[jar.body_id].manifold.trim_by_plane(np.array([0.0, 0.0, 1.0]), 9.0)
    v_lower_raw = raw_lower.volume()
    v_upper_raw = raw_upper.volume()

    feat = doc.split_body(jar.body_id, plane_id, lip={"height": 5.0, "width": 0.0, "clearance": 0.2, "lip_on": "back"})
    assert feat is not None
    upper_id = jar.body_id
    lower_id = feat.result_body_id
    lower_m = doc.bodies[lower_id].manifold
    upper_m = doc.bodies[upper_id].manifold

    expected_lip_vol = math.pi * (18.0 ** 2 - 16.0 ** 2) * 5.0
    expected_pocket_vol = math.pi * (18.2 ** 2 - 16.0 ** 2) * 5.2
    assert lower_m.volume() - v_lower_raw == pytest.approx(expected_lip_vol, rel=0.02)
    assert v_upper_raw - upper_m.volume() == pytest.approx(expected_pocket_vol, rel=0.02)
    assert (lower_m ^ upper_m).is_empty()
    assert float(lower_m.bounding_box()[5]) == pytest.approx(14.0, abs=1e-4)

    # Save and reload via Exporter preserves volumes
    save_path = tmp_path / "lip_jar.omacad"
    Exporter.save_project(doc, str(save_path))
    reloaded = Exporter.load_project(str(save_path))
    assert reloaded.bodies[lower_id].manifold.volume() == pytest.approx(lower_m.volume(), rel=1e-5)
    assert reloaded.bodies[upper_id].manifold.volume() == pytest.approx(upper_m.volume(), rel=1e-5)

    # Undo removes all 4 split+lip steps
    assert doc.undo()
    assert [f.feature_type for f in doc.timeline.features] == ["cylinder", "shell"]
    assert list(doc.bodies) == [jar.body_id]


@pytest.mark.parametrize("style, r_in, r_out", [
    ("outer", 18.0, 20.0),
    ("groove", 16.0 + 4.0 / 3.0, 20.0 - 4.0 / 3.0),
])
def test_split_body_lip_styles_outer_and_groove(style, r_in, r_out):
    """#241: 'outer' and 'groove' (tongue & groove) styles produce non-overlapping mating halves."""
    from omacad.model.document import Document

    doc = Document()
    jar = doc.add_cylinder(20.0, 19.0, center=False)
    doc.add_shell(jar.body_id, 4.0)
    plane_id = doc.add_construction_plane(doc.origin_planes["XY"], 9.0)

    raw_lower = doc.bodies[jar.body_id].manifold.trim_by_plane(np.array([0.0, 0.0, -1.0]), -9.0)
    v_lower_raw = raw_lower.volume()

    feat = doc.split_body(jar.body_id, plane_id,
                          lip={"style": style, "height": 5.0, "width": 0.0, "clearance": 0.2, "lip_on": "back"})
    assert feat is not None
    lower_m = doc.bodies[feat.result_body_id].manifold
    upper_m = doc.bodies[jar.body_id].manifold

    expected_lip_vol = math.pi * (r_out ** 2 - r_in ** 2) * 5.0
    assert lower_m.volume() - v_lower_raw == pytest.approx(expected_lip_vol, rel=0.03)
    assert (lower_m ^ upper_m).is_empty()
    assert float(lower_m.bounding_box()[5]) == pytest.approx(14.0, abs=1e-4)


def test_split_body_dialog_reads_lip_settings(win):
    from omacad.ui.dialogs.boolean_dlg import SplitBodyDialog
    from omacad.ui.settings import get_settings

    cfg = get_settings()
    orig = {k: cfg.get(k) for k in ("split_lip_enabled", "split_lip_style", "split_lip_height", "split_lip_width", "split_lip_clearance")}
    try:
        cfg.update({"split_lip_enabled": True, "split_lip_style": "groove", "split_lip_height": 6.0, "split_lip_width": 1.5, "split_lip_clearance": 0.25})
        win.doc.add_box(20, 20, 20)
        plane = win.doc.add_construction_plane(win.doc.origin_planes["XY"], 10.0)
        dlg = SplitBodyDialog(win.doc, win, preselected_plane_id=plane)
        _bid, _pid, lip = dlg.get_values()
        assert lip is not None
        assert lip["style"] == "groove"
        assert lip["height"] == pytest.approx(6.0)
        assert lip["width"] == pytest.approx(1.5)
        assert lip["clearance"] == pytest.approx(0.25)
    finally:
        cfg.update(orig)


def test_split_body_lip_snap_fit_box():
    """#241: snap_fit adds beveled detent bumps on the lip and matching recesses in the pocket."""
    from omacad.model.document import Document

    def make_box(snap_fit):
        doc = Document()
        box = doc.add_box(60.0, 40.0, 20.0)
        doc.add_shell(box.body_id, 3.0)
        plane_id = doc.add_construction_plane(doc.origin_planes["XY"], 10.0)
        feat = doc.split_body(
            box.body_id, plane_id,
            lip={"style": "inner", "height": 5.0, "width": 0.0, "clearance": 0.2, "lip_on": "back", "snap_fit": snap_fit},
        )
        return doc.bodies[feat.result_body_id].manifold, doc.bodies[box.body_id].manifold

    low_plain, up_plain = make_box(False)
    low_snap, up_snap = make_box(True)

    assert low_snap.volume() > low_plain.volume() + 5.0
    assert up_snap.volume() < up_plain.volume() - 5.0
    assert (low_snap ^ up_snap).is_empty()



