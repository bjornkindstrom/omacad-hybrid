"""
Tests for Star Brackets group settings in the tree, parametric updates, and project save/load.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from omacad.model.document import Document
from omacad.ui.history_delegate import apply_dimension, value_ref
from omacad.ui.browser import BrowserTree
from omacad.io.exporter import Exporter


def test_star_brackets_creation_and_bounds():
    QApplication.instance() or QApplication([])
    doc = Document()
    bodies = doc.add_star_brackets(
        tube_size=10.0,
        tube_length=250.0,
        clearance=0.25,
        wall_thickness=2.5,
        socket_depth=25.0,
        hole_diameter=3.5,
        hole_offset=12.0,
        outer_angle=36.0,
        inner_angle=108.0,
        foot_width=40.0,
        foot_length=70.0,
        foot_thickness=4.0,
        foot_tube_angle=36.0,
    )
    assert len(bodies) == 4
    outer_b, inner_b, foot_b, tube_b = bodies

    # Check that volumes are positive and meshes are valid
    assert outer_b.manifold.volume() > 10000.0
    assert inner_b.manifold.volume() > 5000.0
    assert foot_b.manifold.volume() > 10000.0
    assert tube_b.manifold.volume() > 5000.0

    # Check that object group was created
    assert len(doc.object_groups) == 1
    gid = doc.object_groups[0]["id"]
    assert doc.is_star_bracket_group(gid)

    params = doc.star_bracket_group_params(gid)
    assert params["tube_size"] == 10.0
    assert params["tube_length"] == 250.0
    assert params["outer_angle"] == 36.0
    assert params["inner_angle"] == 108.0


def test_star_brackets_group_settings_in_browser_tree():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_star_brackets()
    browser = BrowserTree(doc)

    gid = doc.object_groups[0]["id"]
    tree_items = list(browser._walk())
    labels = [it[0].text(0) for it in tree_items]

    # Group exists
    assert any("Star brackets 1" in l for l in labels)
    # Settings branch exists
    assert any("Settings" in l for l in labels)

    # Parameter rows exist under Settings
    param_labels = [it[0].text(0) for it in tree_items if it[0].data(0, Qt.ItemDataRole.UserRole) and it[0].data(0, Qt.ItemDataRole.UserRole)[0] == "group_param"]
    assert any("Assembled view (1 = star, 0 = parts): 0" in l for l in param_labels)
    assert any("Tube length: 250 mm" in l for l in param_labels)
    assert any("Tube size: 10 mm" in l for l in param_labels)
    assert any("Wall thickness: 2.5 mm" in l for l in param_labels)
    assert any("Socket depth: 25 mm" in l for l in param_labels)
    assert any("Outer angle (tip): 36 °" in l for l in param_labels)
    assert any("Inner angle (valley): 108 °" in l for l in param_labels)
    assert any("Foot width: 40 mm" in l for l in param_labels)

    # Check value_ref
    item = next(it[0] for it in tree_items if it[0].data(0, Qt.ItemDataRole.UserRole) == ("group_param", (gid, "tube_size")))
    ref = value_ref(item.data(0, Qt.ItemDataRole.UserRole))
    assert ref == ("group_param", (gid, "tube_size"))


def test_star_brackets_edit_param_and_recompute():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_star_brackets(tube_size=10.0, socket_depth=25.0)
    gid = doc.object_groups[0]["id"]

    v_before = doc.bodies["body_star_bracket_1"].manifold.volume()

    # Edit tube_size from 10 to 12 mm
    assert doc.edit_star_bracket_group_param(gid, "tube_size", "12.0")
    v_after = doc.bodies["body_star_bracket_1"].manifold.volume()
    assert v_after > v_before  # larger tube = larger socket

    # Edit via apply_dimension
    assert apply_dimension(doc, "group_param", (gid, "socket_depth"), "30.0")
    v_deep = doc.bodies["body_star_bracket_1"].manifold.volume()
    assert v_deep > v_after

    # Toggle assembled to 1
    assert doc.edit_star_bracket_group_param(gid, "assembled", "1")
    v_assembled_out = doc.bodies["body_star_bracket_1"].manifold.volume()
    # 5 brackets in assembled view vs 1 in print view
    assert v_assembled_out > 4.5 * v_deep

    # Check that tubes volume in assembled view is 10 * 12 * 12 * 250 = 360,000
    v_tubes = doc.bodies["body_star_bracket_4"].manifold.volume()
    assert abs(v_tubes - 360000.0) < 1.0

    # Test angle coupling: changing outer_angle to 40 updates inner to 112 and foot to 34
    assert doc.edit_star_bracket_group_param(gid, "outer_angle", "40.0")
    p = doc.star_bracket_group_params(gid)
    assert p["outer_angle"] == 40.0
    assert p["inner_angle"] == 112.0
    assert p["foot_tube_angle"] == 34.0

    # Test angle coupling: changing inner_angle to 100 updates outer to 28 and foot to 40
    assert doc.edit_star_bracket_group_param(gid, "inner_angle", "100.0")
    p = doc.star_bracket_group_params(gid)
    assert p["outer_angle"] == 28.0
    assert p["inner_angle"] == 100.0
    assert p["foot_tube_angle"] == 40.0


def test_star_brackets_dialog_angle_coupling():
    from omacad.ui.dialogs.primitives_dlg import StarBracketsDialog
    from omacad.ui.numeric_slider import add_numeric_sliders, NumericSlider
    QApplication.instance() or QApplication([])
    dlg = StarBracketsDialog()
    add_numeric_sliders(dlg)
    assert dlg.spn_outer_angle.value() == 36.0
    assert dlg.spn_inner_angle.value() == 108.0
    assert dlg.spn_foot_angle.value() == 36.0

    # Changing outer to 40
    dlg.spn_outer_angle.setValue(40.0)
    assert dlg.spn_inner_angle.value() == 112.0
    assert dlg.spn_foot_angle.value() == 34.0

    # Changing inner to 100
    dlg.spn_inner_angle.setValue(100.0)
    assert dlg.spn_outer_angle.value() == 28.0
    assert dlg.spn_foot_angle.value() == 40.0

    # Verify that sliders sync without breaking
    outer_slider = next(s for s in dlg.findChildren(NumericSlider) if s.field is dlg.spn_outer_angle)
    inner_slider = next(s for s in dlg.findChildren(NumericSlider) if s.field is dlg.spn_inner_angle)
    assert outer_slider.slider.value() > 0
    assert inner_slider.slider.value() > 0


def test_star_brackets_assembled_tube_socket_alignment():
    """Regression test for report 20261102-205851 ('Rören går inte in i fästena').
    Verifies that for arbitrary angles (e.g. pointy 15° star or wide 45° star),
    the aluminum tubes enter the outer and inner bracket sockets with exact collinearity."""
    import math
    import numpy as np
    from omacad.model.features.star_bracket import StarBracketFeature, star_radii

    for outer_a in [15.0, 36.0, 45.0]:
        inner_a = outer_a + 72.0
        tube_len = 500.0
        tube_s = 10.0
        clr = 0.25
        wall_t = 2.5
        sock_d = 40.0

        R_out, R_in, xs_out, xs_in = star_radii(tube_len, tube_s, clr, wall_t, outer_a, inner_a)

        # Tip 0 is at [0, R_out]
        t0 = np.array([0.0, R_out])
        # Valley 0 is at angle 90 - 36 = 54 deg
        v0 = np.array([R_in * math.cos(math.radians(54.0)), R_in * math.sin(math.radians(54.0))])

        vec = v0 - t0
        dist = np.linalg.norm(vec)
        # Distance must match tube_len + stops exactly
        assert abs(dist - (tube_len + xs_out + xs_in)) < 1e-9

        # Outer bracket arm 1 direction (rotated by 270 deg, arm 1 at -90 + outer_a/2)
        arm1_dir = np.array([math.cos(math.radians(-90.0 + outer_a / 2.0)), math.sin(math.radians(-90.0 + outer_a / 2.0))])
        tube_dir = vec / dist
        assert np.linalg.norm(arm1_dir - tube_dir) < 1e-12

        # Inner bracket arm 1 direction at valley 0 (rotated by 54 deg, arm 1 at 54 + inner_a/2)
        inner_arm1_dir = np.array([math.cos(math.radians(54.0 + inner_a / 2.0)), math.sin(math.radians(54.0 + inner_a / 2.0))])
        assert np.linalg.norm(inner_arm1_dir - (-tube_dir)) < 1e-12

        # Verify that solids build without error and intersect cleanly
        f_out = StarBracketFeature("test_out", "Outer", part_type="outer", tube_length=tube_len,
                                   tube_size=tube_s, clearance=clr, wall_thickness=wall_t,
                                   socket_depth=sock_d, outer_angle=outer_a, inner_angle=inner_a, assembled=True)
        f_tubes = StarBracketFeature("test_tubes", "Tubes", part_type="tubes", tube_length=tube_len,
                                     tube_size=tube_s, clearance=clr, wall_thickness=wall_t,
                                     socket_depth=sock_d, outer_angle=outer_a, inner_angle=inner_a, assembled=True)
        b_out = f_out.build_solid()
        b_tubes = f_tubes.build_solid()
        assert not b_out.is_empty()
        assert not b_tubes.is_empty()

        # In assembled view, the tube sits inside the cavity with clearance (0 collision with plastic walls)
        overlap = b_out ^ b_tubes
        assert overlap.volume() < 1e-6  # zero solid collision: fits cleanly inside cavity

        # But tube extends well inside the outer bracket extent
        bb_tubes = b_tubes.bounding_box()
        bb_out = b_out.bounding_box()
        assert bb_tubes[0] > bb_out[0]
        assert bb_tubes[1] > bb_out[1]
        assert bb_tubes[3] < bb_out[3]
        assert bb_tubes[4] < bb_out[4]


def test_star_brackets_save_and_load(tmp_path):
    QApplication.instance() or QApplication([])
    doc = Document("Julstjarna")
    doc.add_star_brackets(outer_angle=36.0, inner_angle=108.0, tube_length=300.0, assembled=True)

    project_file = str(tmp_path / "test_star.omacad")
    Exporter.save_project(doc, project_file)
    assert os.path.exists(project_file)

    loaded = Exporter.load_project(project_file)
    assert len(loaded.bodies) == 4
    assert len(loaded.object_groups) == 1
    gid = loaded.object_groups[0]["id"]
    assert loaded.is_star_bracket_group(gid)
    params = loaded.star_bracket_group_params(gid)
    assert params["outer_angle"] == 36.0
    assert params["inner_angle"] == 108.0
    assert params["tube_length"] == 300.0
    assert params["assembled"] is True
