from types import SimpleNamespace
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.ui.browser import BrowserTree
from omacad.ui.dialogs.pattern_dlg import PatternDialog
from omacad.ui.feature_edit import _exec_with_preview, can_edit
from omacad.ui.ribbon import Ribbon, RibbonButton
from omacad.ui.sketch_palette import SketchPalette


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ribbon_offset_face_and_guide_line(qapp):
    doc = Document()
    ribbon = Ribbon(doc)
    solid_btn_texts = [b.text() for b in ribbon.solid_tab.findChildren(RibbonButton)]
    assert any("Offset" in t and "Face" in t for t in solid_btn_texts)

    assert "Construction" in ribbon.btn_construct.text()      # one name everywhere (was "Guide Line")
    assert "construction" in ribbon.btn_construct.toolTip().lower()


def test_request_38_sketch_text_hit_test_and_ui(qapp):
    doc = Document()
    sk = doc.start_sketch("XY")
    txt = sk.add_text("OMACAD", (0.0, 0.0), height=12.0)

    # Hit test inside text bounding box / glyph area
    bx0, by0, bx1, by1 = txt.bbox()
    cx = (bx0 + bx1) * 0.5
    cy = (by0 + by1) * 0.5
    hit = sk.hit_test(cx, cy, tol=1.0)
    assert hit is txt

    # SketchPalette shows Edit Text button when set_has_text(True) is called
    palette = SketchPalette()
    palette.set_has_text(True)
    assert not palette.btn_edit_text.isHidden()
    palette.set_has_text(False)
    assert palette.btn_edit_text.isHidden()

    # BrowserTree lists SketchText under the sketch node and emits edit_sketch_text_requested
    browser = BrowserTree(doc)
    browser.refresh_tree()
    emitted = []
    browser.edit_sketch_text_requested.connect(lambda sid, eid: emitted.append((sid, eid)))

    found_text_node = None
    for item, _ in browser._walk():
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "sketch_text":
            found_text_node = item
            break
    assert found_text_node is not None
    browser.on_item_double_clicked(found_text_node, 0)
    assert emitted == [(sk.sketch_id, txt.entity_id)]


def test_request_40_emboss_cylindrical_wrapping_and_save_load(tmp_path):
    doc = Document()
    cyl_body = doc.add_cylinder(10.0, 30.0)
    assert cyl_body is not None

    # Create sketch tangent to cylinder at Y=-10 facing -Y
    plane = SketchPlane(
        name="Tangent",
        origin=np.array([0.0, -10.0, 15.0], dtype=np.float32),
        u_axis=np.array([1.0, 0.0, 0.0], dtype=np.float32),
        v_axis=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        normal=np.array([0.0, -1.0, 0.0], dtype=np.float32),
    )
    sk = doc.start_sketch_on_plane(plane)
    # Wide rectangle spanning 40 mm (> pi * 10 = 31.4 mm -> wraps > 180 degrees around R=10 cylinder)
    sk.add_rect((-20.0, -3.0), (20.0, 3.0))
    doc.finish_sketch()

    emb_wrap = doc.add_emboss(sk.sketch_id, 0, depth=1.5, wrap=True)
    body_wrap = doc.bodies[cyl_body.body_id]
    verts_wrap = np.asarray(body_wrap.manifold.to_mesh().vert_properties)[:, :3]
    # Because it wraps > 180 deg from -Y around the cylinder, some vertices must reach +Y > 1.0 on radius > 10.5
    radii_xy = np.hypot(verts_wrap[:, 0], verts_wrap[:, 1])
    embossed_verts = verts_wrap[radii_xy > 10.5]
    assert len(embossed_verts) > 0
    assert np.max(embossed_verts[:, 1]) > 1.0

    # Compare with wrap=False (flat projection)
    idx = doc.timeline.features.index(emb_wrap)
    doc.edit_feature(idx, wrap=False)
    body_flat = doc.bodies[cyl_body.body_id]
    verts_flat = np.asarray(body_flat.manifold.to_mesh().vert_properties)[:, :3]
    radii_flat = np.hypot(verts_flat[:, 0], verts_flat[:, 1])
    embossed_flat = verts_flat[radii_flat > 10.5]
    assert len(embossed_flat) > 0
    # Flat projection from -Y only projects on the -Y half (<= 0), never wrapping into +Y
    assert np.max(embossed_flat[:, 1]) <= 1e-4

    # Save & load roundtrip preserves wrap flag
    save_file = tmp_path / "emboss_wrap.omacad"
    Exporter.save_project(doc, str(save_file))
    doc2 = Exporter.load_project(str(save_file))
    emb2 = [f for f in doc2.timeline.features if f.feature_type == "emboss"][0]
    assert emb2.wrap is False


def test_request_35_pattern_primitives(qapp):
    doc = Document()
    box_body = doc.add_box(10.0, 10.0, 10.0)
    box_feat = doc.timeline.features[-1]

    # PatternDialog defaults to checking the primitive when it's the latest step
    dlg = PatternDialog(doc=doc)
    assert dlg.source_ids() == [box_feat.feature_id]

    # Linear pattern of standalone Box primitive
    doc.add_pattern(
        source_ids=[box_feat.feature_id],
        kind="linear",
        axis1="x",
        count1=3,
        spacing1=20.0,
    )
    pat_body = doc.bodies[box_body.body_id]
    assert pat_body.manifold.volume() == pytest.approx(3000.0, rel=1e-2)

    # Mirror pattern of standalone Cylinder primitive across YZ plane
    doc2 = Document()
    cyl_body = doc2.add_cylinder(
        5.0,
        10.0,
        plane_origin=(15.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
    )
    cyl_feat = doc2.timeline.features[-1]
    vol1 = cyl_body.manifold.volume()
    doc2.add_pattern(
        source_ids=[cyl_feat.feature_id],
        kind="mirror",
        mirror_mode="plane:YZ",
    )
    mir_body = doc2.bodies[cyl_body.body_id]
    assert mir_body.manifold.volume() == pytest.approx(vol1 * 2.0, rel=1e-2)


def test_request_42_smart_box_and_smart_cylinder(tmp_path):
    doc = Document()
    # Hollow box with outer fillet and inner chamfer
    box_body = doc.add_box(
        length=40.0,
        width=40.0,
        height=20.0,
        wall_thickness=3.0,
        outer_round=2.0,
        outer_round_kind="fillet",
        inner_round=1.0,
        inner_round_kind="chamfer",
    )
    assert box_body is not None
    solid_vol = 40.0 * 40.0 * 20.0
    assert 0.0 < box_body.manifold.volume() < solid_vol * 0.6

    # Hollow cylinder with outer chamfer and inner fillet
    cyl_body = doc.add_cylinder(
        radius=20.0,
        height=30.0,
        wall_thickness=3.0,
        outer_round=1.5,
        outer_round_kind="chamfer",
        inner_round=1.5,
        inner_round_kind="fillet",
    )
    assert cyl_body is not None
    solid_cyl_vol = np.pi * 20.0**2 * 30.0
    assert 0.0 < cyl_body.manifold.volume() < solid_cyl_vol * 0.6

    # Save & load roundtrip preserves smart primitive properties
    save_file = tmp_path / "smart_prims.omacad"
    Exporter.save_project(doc, str(save_file))
    doc2 = Exporter.load_project(str(save_file))
    b2 = [f for f in doc2.timeline.features if f.feature_type == "box"][0]
    c2 = [f for f in doc2.timeline.features if f.feature_type == "cylinder"][0]
    assert b2.wall_thickness == pytest.approx(3.0)
    assert b2.outer_round == pytest.approx(2.0)
    assert b2.outer_round_kind == "fillet"
    assert b2.inner_round == pytest.approx(1.0)
    assert b2.inner_round_kind == "chamfer"
    assert c2.wall_thickness == pytest.approx(3.0)
    assert c2.outer_round == pytest.approx(1.5)
    assert c2.outer_round_kind == "chamfer"
    assert c2.inner_round == pytest.approx(1.5)
    assert c2.inner_round_kind == "fillet"


def test_request_31_feature_edit_support_and_live_preview(qapp):
    for ftype in ("revolve", "shell", "combine", "extrude", "emboss", "box", "cylinder"):
        assert can_edit(SimpleNamespace(feature_type=ftype))

    # Verify _exec_with_preview wires changed signal, updates preview, and cleans up after exec()
    from PySide6.QtCore import QObject, Signal
    import manifold3d as m3d

    class DummyDlg(QObject):
        changed = Signal()

        def exec(self):
            self.changed.emit()
            return True

    class DummyViewport:
        def __init__(self):
            self.previews = []
            self.updated = 0

        def set_preview(self, m, color=None):
            self.previews.append((m, color))

        def update(self):
            self.updated += 1

    doc = Document()
    body = doc.add_box(10.0, 10.0, 10.0)

    class DummyWin:
        def __init__(self):
            self.doc = doc
            self.viewport = DummyViewport()

    win = DummyWin()
    dlg = DummyDlg()
    cube = m3d.Manifold.cube([5.0, 5.0, 5.0])
    ok = _exec_with_preview(
        win,
        doc,
        dlg,
        preview_fn=lambda: win.viewport.set_preview(cube, (0.3, 0.7, 1.0, 0.5)),
        hide_body_ids=[body.body_id],
    )
    assert ok is True
    # Initial preview + changed signal preview + cleanup None preview
    assert len(win.viewport.previews) >= 3
    assert win.viewport.previews[0][0] is cube
    assert win.viewport.previews[-1] == (None, None)
    assert body.visible is True


def test_request_43_extrude_start_offset(tmp_path):
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((-5.0, -5.0), (5.0, 5.0))
    doc.finish_sketch()

    # Extrude 20 mm starting 15 mm above the XY sketch plane -> Z spans [15, 35]
    doc.extrude_profile(sk.sketch_id, 0, distance=20.0, operation="new_body", start_offset=15.0)
    body = list(doc.bodies.values())[0]
    bb = body.manifold.bounding_box()
    assert bb[2] == pytest.approx(15.0, abs=1e-4)
    assert bb[5] == pytest.approx(35.0, abs=1e-4)

    # Edit start_offset to -10 mm via edit_feature -> Z spans [-10, 10]
    idx = len(doc.timeline.features) - 1
    doc.edit_feature(idx, start_offset=-10.0)
    body = list(doc.bodies.values())[0]
    bb = body.manifold.bounding_box()
    assert bb[2] == pytest.approx(-10.0, abs=1e-4)
    assert bb[5] == pytest.approx(10.0, abs=1e-4)

    # Save & load roundtrip preserves start_offset
    save_file = tmp_path / "extrude_offset.omacad"
    Exporter.save_project(doc, str(save_file))
    doc2 = Exporter.load_project(str(save_file))
    ext2 = [f for f in doc2.timeline.features if f.feature_type == "extrude"][0]
    assert ext2.start_offset == pytest.approx(-10.0)
    body2 = list(doc2.bodies.values())[0]
    bb2 = body2.manifold.bounding_box()
    assert bb2[2] == pytest.approx(-10.0, abs=1e-4)
    assert bb2[5] == pytest.approx(10.0, abs=1e-4)


def test_request_44_sketch_text_profile_sync_on_edit(qapp, tmp_path):
    """Regression test for Request #44: editing SketchText height or content must not drop parts of letters like 'e'."""
    from omacad.model.sketch import SketchText
    import numpy as np

    doc = Document()
    cyl = doc.add_cylinder(radius=25.0, height=30.0)

    sk = doc.start_sketch("XZ")
    sk.plane.origin = np.array([0.0, -30.0, 15.0], dtype=np.float32)
    txt = sk.add_text("Text som är lång", anchor=(-20.0, -5.0), height=10.0)
    doc.finish_sketch()

    initial_text_indices = sk.text_profile_indices()
    assert len(initial_text_indices) >= 14
    doc.add_emboss(
        sketch_id=sk.sketch_id,
        profile_idx=initial_text_indices[0],
        extra_profiles=initial_text_indices[1:],
        depth=1.5,
    )

    emboss_feat = [f for f in doc.timeline.features if f.feature_type == "emboss"][0]
    assert [emboss_feat.profile_idx] + list(emboss_feat.extra_profiles) == initial_text_indices

    # Now edit text height from 10.0 -> 8.0 (triggers profile re-ordering in solve_profiles where 'e' and its hole swap indices)
    txt.height = 8.0
    sk.solve_profiles()
    doc.timeline.recompute(doc)

    new_text_indices = sk.text_profile_indices()
    resolved = [emboss_feat.profile_idx] + list(emboss_feat.extra_profiles)
    assert sorted(resolved) == sorted(new_text_indices), (
        f"Expected emboss profiles {new_text_indices}, got {resolved}"
    )

    # Also edit the text string so the number of glyphs changes completely
    txt.text = "Text med flera eee"
    sk.solve_profiles()
    doc.timeline.recompute(doc)

    changed_indices = sk.text_profile_indices()
    resolved_after_str_change = [emboss_feat.profile_idx] + list(emboss_feat.extra_profiles)
    assert sorted(resolved_after_str_change) == sorted(changed_indices)


def test_wave2_circle_equal_constraint_and_edit_features(tmp_path):
    """Verify EQUAL constraint between two regular SketchCircles, plus SplitBody/Shell/Combine/Thread/cplane improvements."""
    from omacad.model.sketch import SketchCircle, SketchPlane

    doc = Document()
    sk = doc.start_sketch("XY")
    c1 = sk.add_circle((0.0, 0.0), 12.0)
    c2 = sk.add_circle((30.0, 0.0), 5.0)
    assert doc.add_constraints(sk.sketch_id, [("EQUAL", [c1.entity_id, c2.entity_id], [])])
    c1_ent = sk.get_entity(c1.entity_id)
    c2_ent = sk.get_entity(c2.entity_id)
    assert isinstance(c1_ent, SketchCircle) and isinstance(c2_ent, SketchCircle)
    assert c1_ent.radius == pytest.approx(c2_ent.radius, abs=1e-4)
    doc.finish_sketch()

    # Verify split_body is editable and cplane can be renamed
    assert can_edit(SimpleNamespace(feature_type="split_body"))
    assert "split_body" in Document.EDITABLE
    assert "combine" in Document.EDITABLE
    assert "shell" in Document.EDITABLE

    pid = doc.add_construction_plane(SketchPlane.create_named("XY"), 15.0, name="OldPlane")
    assert doc.rename_item("cplane", pid, "NewPlane")
    assert doc.construction_planes[pid]["name"] == "NewPlane"

    # Verify ThreadFeature preserves exprs and suppressed in to_dict/from_dict
    cyl = doc.add_cylinder(radius=5.0, height=20.0)
    doc.add_thread(
        diameter=10.0,
        pitch=1.5,
        length=15.0,
        target_body_id=cyl.body_id,
        operation="join",
        exprs={"length": "15"},
    )
    th_feat = [f for f in doc.timeline.features if f.feature_type == "thread"][0]
    th_feat.suppressed = True
    save_file = tmp_path / "thread_exprs.omacad"
    Exporter.save_project(doc, str(save_file))
    doc2 = Exporter.load_project(str(save_file))
    th2 = [f for f in doc2.timeline.features if f.feature_type == "thread"][0]
    assert th2.suppressed is True
    assert th2.exprs == {"length": "15"}


