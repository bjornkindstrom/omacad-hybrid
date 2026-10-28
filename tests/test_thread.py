"""
Tests for 3D-printable thread and coil generation.
"""

import numpy as np
import pytest
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.document import Document
from omacad.model.features.thread import ThreadFeature
from omacad.io.exporter import Exporter


def test_cad_kernel_create_thread_male_trapezoidal():
    """Verify male thread generation produces a valid, watertight solid manifold."""
    bolt = CadKernel.create_thread(
        diameter=10.0,
        pitch=2.0,
        length=20.0,
        is_female=False,
        clearance=0.25,
        profile="trapezoidal_45",
        taper_lead_in=True,
        taper_turns=0.75,
        include_core=True,
    )
    assert not bolt.is_empty()
    assert str(bolt.status()) == "Error.NoError"
    assert bolt.volume() > 0.0


def test_cad_kernel_create_thread_female_cutter():
    """Verify female thread cutter produces a valid manifold and can cut a hole."""
    cutter = CadKernel.create_thread(
        diameter=12.0,
        pitch=2.0,
        length=15.0,
        is_female=True,
        clearance=0.25,
        profile="trapezoidal_45",
        taper_lead_in=True,
        include_core=False,
    )
    assert not cutter.is_empty()
    assert str(cutter.status()) == "Error.NoError"

    # Blank nut block
    nut_blank = CadKernel.create_box(20.0, 20.0, 15.0, center=False)
    hole = CadKernel.create_cylinder(radius=5.0, height=20.0, center=False)
    # Cut hole and female thread
    nut = (nut_blank - hole) - cutter
    assert not nut.is_empty()
    assert str(nut.status()) == "Error.NoError"
    assert nut.volume() < nut_blank.volume()


def test_document_add_thread_feature_and_timeline():
    """Verify adding a thread to a Document updates bodies, timeline and serialization."""
    doc = Document()
    body = doc.add_thread(
        diameter=8.0,
        pitch=1.5,
        length=16.0,
        clearance=0.2,
        profile="trapezoidal_45",
        taper_lead_in=True,
    )
    assert body is not None
    assert body.body_id in doc.bodies
    assert len(doc.timeline.features) == 1
    assert doc.timeline.features[0].feature_type == "thread"

    # Serialize to dict and reload
    doc_json = doc.snapshot()
    doc2 = Document()
    doc2.restore(doc_json)
    assert len(doc2.timeline.features) == 1
    feat = doc2.timeline.features[0]
    assert feat.feature_type == "thread"
    assert feat.diameter == 8.0
    assert feat.pitch == 1.5
    assert feat.clearance == 0.2
    assert len(doc2.bodies) == 1


def test_cad_kernel_create_thread_round_coil():
    """Verify round/circular profile coil generation is watertight with positive volume."""
    coil = CadKernel.create_thread(
        diameter=14.0,
        pitch=3.0,
        length=24.0,
        is_female=False,
        clearance=0.25,
        profile="round",
        taper_lead_in=True,
        taper_turns=0.75,
        include_core=False,
    )
    assert not coil.is_empty()
    assert str(coil.status()) == "Error.NoError"
    assert coil.volume() > 0.0


def test_detect_cylinder_surface_external_and_internal():
    """Verify automatic detection of external cylinder (male) vs internal hole (female)."""
    from omacad.model.faces import detect_cylinder_surface, ray_mesh_hit

    # 1. External cylinder
    cyl = CadKernel.create_cylinder(radius=10.0, height=35.0, center=False)
    mesh_cyl = CadKernel.extract_render_mesh(cyl)
    hit1 = ray_mesh_hit(mesh_cyl, [0.0, -40.0, 15.0], [0.0, 1.0, 0.0])
    assert hit1 is not None
    info1 = detect_cylinder_surface(mesh_cyl, hit1[1])
    assert info1 is not None
    assert abs(info1["radius"] - 10.0) < 0.1
    assert abs(info1["length"] - 35.0) < 0.1
    assert info1["is_internal"] is False

    # 2. Internal hole in a box
    box = CadKernel.create_box(40.0, 40.0, 30.0, center=False)
    hole = CadKernel.create_cylinder(radius=6.0, height=50.0, center=False).translate([20.0, 20.0, -10.0])
    nut = box - hole
    mesh_nut = CadKernel.extract_render_mesh(nut)
    hit2 = ray_mesh_hit(mesh_nut, [20.0, 20.0, 15.0], [1.0, 0.0, 0.0])
    assert hit2 is not None
    info2 = detect_cylinder_surface(mesh_nut, hit2[1])
    assert info2 is not None
    assert abs(info2["radius"] - 6.0) < 0.1
    assert abs(info2["length"] - 30.0) < 0.1
    assert info2["is_internal"] is True


def test_cylinder_coil_seamless_attachment_no_gap():
    """Verify that attaching a coil or thread to a cylinder leaves no gap and performs a watertight union."""
    cyl = CadKernel.create_cylinder(radius=10.0, height=30.0, center=False)
    v_cyl = cyl.volume()

    # 1. Round profile wrapped on cylinder:
    coil_round = CadKernel.create_thread(
        diameter=20.0,
        pitch=2.5,
        length=30.0,
        is_female=False,
        clearance=0.25,
        profile="round",
        include_core=False,
        attached_to_cylinder=True,
    )
    union_round = cyl + coil_round
    assert str(union_round.status()) == "Error.NoError"
    # Material must be added directly onto the cylinder with seamless overlap, no gap!
    assert union_round.volume() > v_cyl + 10.0

    # 2. Trapezoidal profile attached to cylinder:
    thread_trap = CadKernel.create_thread(
        diameter=20.0,
        pitch=2.0,
        length=30.0,
        is_female=False,
        clearance=0.25,
        profile="trapezoidal_45",
        include_core=False,
        attached_to_cylinder=True,
    )
    union_trap = cyl + thread_trap
    assert str(union_trap.status()) == "Error.NoError"
    assert union_trap.volume() > v_cyl + 50.0



def test_round_thread_leaves_no_bare_gap_between_turns():
    """Rounded thread on a cylinder: seamless attachment without gaps."""
    R, p = 20.0, 3.5
    cyl = CadKernel.create_cylinder(radius=R, height=40.0, center=False)
    coil = CadKernel.create_thread(2 * R, p, 40.0, profile="round", include_core=False,
                                   attached_to_cylinder=True)
    body = cyl + coil
    assert str(body.status()) == "Error.NoError"
    assert body.volume() > cyl.volume() + 10.0


def test_bottle_jar_round_thread_engagement():
    """Bottle neck and screw cap with round thread fit together with exact clearance and no collision."""
    dia, p, clr = 40.0, 3.5, 0.25
    # Male jar neck: cylinder + thread
    neck_cyl = CadKernel.create_cylinder(radius=dia * 0.5, height=20.0, center=False)
    neck_thread = CadKernel.create_thread(
        diameter=dia, pitch=p, length=20.0, is_female=False, clearance=clr,
        profile="round", attached_to_cylinder=True
    )
    neck = neck_cyl + neck_thread
    assert str(neck.status()) == "Error.NoError"

    # Female cap: cylinder block with clearance hole (D + clr) cut with female thread cutter
    cap_block = CadKernel.create_cylinder(radius=25.0, height=20.0, center=False)
    cap_hole = CadKernel.create_cylinder(radius=(dia + clr) * 0.5, height=20.0, center=False)
    cap_cutter = CadKernel.create_thread(
        diameter=dia + clr, pitch=p, length=20.0, is_female=True, clearance=clr,
        profile="round", attached_to_cylinder=True
    )
    cap = (cap_block - cap_hole) - cap_cutter
    assert str(cap.status()) == "Error.NoError"

    # When mated, there must be no physical collision between bottle neck and cap
    clash = neck ^ cap
    assert clash.volume() < 1e-4, f"Clash volume {clash.volume()} between bottle neck and cap must be 0!"


def test_thread_does_not_protrude_past_length():
    """Verify thread coils do not leave burrs/fnas protruding beyond [0, length] along Z."""
    length = 40.0
    for prof in ["trapezoidal_45", "iso_60", "round"]:
        coil = CadKernel.create_thread(
            diameter=40.0,
            pitch=3.5,
            length=length,
            is_female=False,
            profile=prof,
            include_core=False,
            attached_to_cylinder=True,
        )
        z = coil.to_mesh().vert_properties[:, 2]
        assert np.max(z) <= length + 1e-5, f"Profile {prof} protrudes above top face: max z={np.max(z)}"
        assert np.min(z) >= -1e-5, f"Profile {prof} protrudes below bottom face: min z={np.min(z)}"



def test_new_threads_default_to_zero_clearance():
    """New Thread steps, the kernel and the dialog all start at 0 mm clearance."""
    import inspect
    for fn in (Document.add_thread, ThreadFeature.__init__, CadKernel.create_thread):
        assert inspect.signature(fn).parameters["clearance"].default == 0.0


def test_thread_panel_length_is_at_least_one_turn():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from omacad.ui.dialogs.thread_dlg import ThreadDialog
    QApplication.instance() or QApplication([])
    dlg = ThreadDialog(Document())
    dlg.spn_pitch.setValue(3.0)
    dlg.spn_length.setValue(1.0)
    assert dlg.spn_length.value() == pytest.approx(3.0)       # shown, not stretched silently by the kernel
