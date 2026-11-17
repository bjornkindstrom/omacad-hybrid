"""Tests for bento_tray.py (Omacad script & CLI generator for Bento3D Tray)."""

from pathlib import Path
import manifold3d as m3d
import pytest

bento_tray = pytest.importorskip("bento_tray")
from omacad.scripting.loader import read_info
from omacad.scripting.runner import check_report, run_script
from omacad.model.document import Document


def test_omacad_script_metadata_and_check_report():
    script_path = Path(bento_tray.__file__).resolve()
    info = read_info(script_path)
    assert info.error == ""
    assert info.name == "Bento3D Förvaringsbricka"
    assert info.output_name == "BentoBricka"
    assert info.easy_params is not None and "preset" in info.easy_params

    ok, report = check_report(script_path)
    assert ok, f"check_report failed:\n{report}"
    assert "RESULT: OK" in report


def test_bento_classic_layout_cells():
    cells = bento_tray.compute_cells(
        {"preset": "Bento (Klassisk 4 fack)", "width": 100.0, "depth": 100.0, "thickness": 2.0}
    )
    assert len(cells) == 4
    # Left full-depth cell: x = -24.5, y = 0, w = 47, d = 96
    c_left = min(cells, key=lambda c: c["x"])
    assert c_left["x"] == pytest.approx(-24.5)
    assert c_left["y"] == pytest.approx(0.0)
    assert c_left["w"] == pytest.approx(47.0)
    assert c_left["d"] == pytest.approx(96.0)


def test_stackable_vs_unstackable_geometry():
    m_stack = bento_tray.build_tray(
        {"preset": "4 fack (2x2)", "width": 100.0, "depth": 80.0, "height": 20.0, "stackable": True}
    )
    m_flat = bento_tray.build_tray(
        {"preset": "4 fack (2x2)", "width": 100.0, "depth": 80.0, "height": 20.0, "stackable": False}
    )
    assert m_stack.status() == m3d.Error.NoError
    assert m_flat.status() == m3d.Error.NoError

    # Both sit on Z=0..20 without negative Z overhangs
    bb_stack = m_stack.bounding_box()
    bb_flat = m_flat.bounding_box()
    assert bb_stack[2] == pytest.approx(0.0, abs=1e-3)
    assert bb_stack[5] == pytest.approx(20.0, abs=1e-3)
    assert bb_flat[2] == pytest.approx(0.0, abs=1e-3)
    assert bb_flat[5] == pytest.approx(20.0, abs=1e-3)

    # Stackable has 45° bottom outer bevel and 45° top inner bevel so its volume is slightly smaller
    assert m_stack.volume() < m_flat.volume()


def test_bottom_scoop_preserves_front_and_back_symmetry():
    """Verifies that bottom_scoop curves the floor along Y without filling the Y < 0 half."""
    params_no_scoop = {
        "preset": "4 fack (2x2)",
        "width": 100.0,
        "depth": 100.0,
        "height": 20.0,
        "stackable": False,
        "bottom_scoop": False,
    }
    params_scoop = dict(params_no_scoop, bottom_scoop=True, scoop_radius=6.0)
    m_no = bento_tray.build_tray(params_no_scoop)
    m_sc = bento_tray.build_tray(params_scoop)
    assert m_sc.status() == m3d.Error.NoError
    # Scoop adds curved fillets at the floor transitions so tray volume increases modestly (< 25%),
    # never filling half the tray!
    vol_no = m_no.volume()
    vol_sc = m_sc.volume()
    assert vol_no < vol_sc < vol_no * 1.25

    # Check Y-symmetry by intersecting with Y < 0 and Y > 0 half-spaces
    half_front = m3d.Manifold.cube([200.0, 100.0, 50.0]).translate([-100.0, -100.0, -5.0])
    half_back = m3d.Manifold.cube([200.0, 100.0, 50.0]).translate([-100.0, 0.0, -5.0])
    v_front = (m_sc ^ half_front).volume()
    v_back = (m_sc ^ half_back).volume()
    assert v_front == pytest.approx(v_back, rel=1e-3)


def test_full_features_watertight_and_label_plate():
    params = {
        "preset": "Bento (Klassisk 4 fack)",
        "width": 120.0,
        "depth": 100.0,
        "height": 28.0,
        "thickness": 2.0,
        "fillet": 2.5,
        "stackable": True,
        "bottom_scoop": True,
        "scoop_radius": 5.0,
        "wall_pattern": "Hexagon",
        "wall_hole_size": 5.5,
        "wall_margin": "Normal (3 mm)",
        "finger_pull": True,
        "finger_pull_width": 22.0,
        "finger_pull_height": 8.0,
        "label_holder": True,
        "label_position": "Vänster",
        "label_width": 35.0,
        "label_height": "15mm",
        "label_text": "M3x10",
    }
    doc = Document()
    script_path = Path(bento_tray.__file__).resolve()
    res = run_script(doc, script_path, values=params)
    assert res.ok
    # Should produce 2 watertight bodies: the tray and the slide-in label plate
    assert len(doc.bodies) == 2
    for b in doc.bodies.values():
        assert b.manifold.status() == m3d.Error.NoError
        assert b.manifold.volume() > 0


def test_cli_stl_export(tmp_path):
    out_stl = tmp_path / "bento_out.stl"
    rc = bento_tray.main([
        "-o", str(out_stl),
        "--preset", "Bento (Klassisk 4 fack)",
        "-W", "90",
        "-D", "70",
        "-H", "22",
        "--wall-pattern", "Cirkel",
        "--finger-pull",
        "--label-holder",
    ])
    assert rc == 0
    assert out_stl.exists()
    assert out_stl.stat().st_size > 1000
