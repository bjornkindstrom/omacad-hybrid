"""Tests for Thread Pin + Cut Thread (thread, cut, 3D-print clearance, and lead-in chamfer)."""
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui.dialogs import CutThreadDialog, ThreadPinDialog


def test_cut_thread_keep_screw_clearance_and_chamfer(tmp_path):
    doc = Document()
    box = doc.add_box(40, 40, 20, center="bottom_center")
    pin = doc.add_cylinder(5.0, 25.0, name="Thread Pin 1")
    doc.move_body(pin.body_id, dz=8.0)

    # First run without chamfer to measure pure clearance, then undo and run with chamfer
    feat_no_ch = doc.cut_thread(box.body_id, pin.body_id, pitch=2.0, clearance=0.2, chamfer=0.0, keep_screw=True)
    assert feat_no_ch is not None
    box_m0 = doc.bodies[box.body_id].manifold
    bolt_m0 = doc.bodies[pin.body_id].manifold
    assert box_m0.status().name == "NoError" and bolt_m0.status().name == "NoError"
    assert len(bolt_m0.decompose()) == 1
    band = lambda m: m.trim_by_plane((0, 0, 1), 11.0).trim_by_plane((0, 0, -1), -17.0)
    assert 0.18 < band(box_m0).min_gap(band(bolt_m0), 1.0) < 0.21

    v_box_no_ch = box_m0.volume()
    v_bolt_no_ch = bolt_m0.volume()
    doc.undo()

    feat = doc.cut_thread(box.body_id, pin.body_id, pitch=2.0, clearance=0.2, chamfer=1.0, keep_screw=True)
    assert feat is not None
    box_m = doc.bodies[box.body_id].manifold
    bolt_m = doc.bodies[pin.body_id].manifold
    assert box_m.status().name == "NoError" and bolt_m.status().name == "NoError"
    assert len(bolt_m.decompose()) == 1
    # Chamfers removed material at the hole mouth (z=20) and screw tips (z=8, z=33)
    assert box_m.volume() < v_box_no_ch - 5.0
    assert bolt_m.volume() < v_bolt_no_ch - 1.0

    # Roundtrip save/load and undo
    path = str(tmp_path / "cut_thread.omacad")
    Exporter.save_project(doc, path)
    again = Exporter.load_project(path)
    assert again.bodies[box.body_id].manifold.volume() == pytest.approx(box_m.volume(), rel=1e-5)
    assert again.bodies[pin.body_id].manifold.volume() == pytest.approx(bolt_m.volume(), rel=1e-5)

    doc.undo()
    assert doc.bodies[box.body_id].manifold.volume() == pytest.approx(40 * 40 * 20, rel=1e-5)


def test_cut_thread_without_keeping_screw_removes_pin_and_widens_hole():
    doc = Document()
    box = doc.add_box(40, 40, 20, center="bottom_center")
    pin = doc.add_cylinder(5.0, 25.0, name="Thread Pin 1")
    doc.move_body(pin.body_id, dz=8.0)

    v_before = box.manifold.volume()
    feat = doc.cut_thread(box.body_id, pin.body_id, pitch=2.0, clearance=0.2, chamfer=1.0, keep_screw=False)
    assert feat is not None
    assert pin.body_id not in doc.bodies
    assert doc.bodies[box.body_id].manifold.volume() < v_before - 1000.0
    assert doc.bodies[box.body_id].manifold.status().name == "NoError"


def test_cut_thread_rotated_pin_works():
    doc = Document()
    box = doc.add_box(40, 40, 40, center="bottom_center")
    pin = doc.add_cylinder(5.0, 25.0, name="Thread Pin 1")
    doc.move_body(pin.body_id, rx=90.0, dy=20.0, dz=20.0)
    feat = doc.cut_thread(box.body_id, pin.body_id, pitch=2.0, clearance=0.2, chamfer=1.0, keep_screw=True)
    assert feat is not None
    assert doc.bodies[box.body_id].manifold.status().name == "NoError"
    assert doc.bodies[pin.body_id].manifold.status().name == "NoError"


def test_thread_pin_and_cut_thread_dialogs():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(40, 40, 20)
    doc.add_cylinder(5.0, 25.0, name="Thread Pin 1")

    pin_dlg = ThreadPinDialog()
    assert pin_dlg.get_values() == {"diameter": 10.0, "length": 25.0}

    cut_dlg = CutThreadDialog(doc)
    vals = cut_dlg.get_values()
    assert vals["clearance"] == pytest.approx(0.2)
    assert vals["chamfer"] == pytest.approx(1.0)
    assert vals["keep_screw"] is True
    assert vals["target_body_id"] != vals["pin_body_id"]



def test_cut_thread_off_origin_pin_stays_in_place():
    doc = Document()
    box = doc.add_box(50, 50, 25, center="bottom_center")
    pin = doc.add_cylinder(5.0, 25.0, name="Thread Pin 1")
    doc.move_body(pin.body_id, dx=10.0, dy=5.0, dz=13.0)
    bb0 = pin.manifold.bounding_box()
    doc.cut_thread(box.body_id, pin.body_id, pitch=2.0, clearance=0.2, chamfer=1.0, keep_screw=True)
    bb1 = doc.bodies[pin.body_id].manifold.bounding_box()
    assert bb1[0] == pytest.approx(bb0[0] + 0.2, abs=1e-3)
    assert bb1[3] == pytest.approx(bb0[3] - 0.2, abs=1e-3)
    assert bb1[1] == pytest.approx(bb0[1] + 0.2, abs=1e-3)
    assert bb1[4] == pytest.approx(bb0[4] - 0.2, abs=1e-3)
    assert bb1[2] == pytest.approx(bb0[2], abs=1e-3)
    assert bb1[5] == pytest.approx(bb0[5], abs=1e-3)
