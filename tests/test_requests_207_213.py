"""Requests #207-#213 (2026-11-07): Emboss/Deboss from the Text panel, sketch profiles win the hover over their face,
Split Body fields not cut off in Studio, Delete on a top object, no shard at a groove when a cut face is rounded,
smooth shading on a shelled fillet."""
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from omacad.io.exporter import Exporter
from omacad.model.kernel import CadKernel
from omacad.model.sketch import SketchPlane
from omacad.ui.main_window import MainWindow

DATA = Path(__file__).parent / "data"


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    return MainWindow()


def _box_with_text(w):
    doc = w.doc
    doc.add_box(60.0, 40.0, 10.0, center="bottom_center")
    top = max(next(iter(doc.bodies.values())).faces, key=lambda f: f.normal[2])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(top.normal, top.origin))
    return sk


def test_207_deboss_button_in_the_text_panel_finishes_and_opens_emboss_on_that_text(win, monkeypatch):
    sk = _box_with_text(win)
    win.prompt_text()
    dlg = win._text_session.dlg
    dlg.edt_text.setPlainText("HI")
    dlg.spn_height.setValue(12.0)
    win.viewport.text_place_requested.emit((0.0, 0.0), None)
    calls = []
    monkeypatch.setattr("omacad.ui.controllers.text_prompts.QTimer.singleShot",
                        lambda _ms, _ctx, fn: calls.append(fn))
    dlg.btn_deboss.click()
    monkeypatch.undo()
    assert win._text_session is None and len(calls) == 1
    calls[0]()                                                  # what the timer runs: Emboss on that sketch, pressed in
    emb = win._emboss_dlg
    assert win.doc.active_sketch is None                         # the sketch was finished first
    assert emb.spn_depth.value() == pytest.approx(-1.0) and emb.cmb_effect.currentData() == "deboss"
    assert win.doc.selected_profile[0] == sk.sketch_id and len(win.doc.selected_extra) == 1     # H and I
    v0 = next(iter(win.doc.bodies.values())).manifold.volume()
    emb.accept()
    assert win.doc.timeline.features[-1].feature_type == "emboss"
    assert next(iter(win.doc.bodies.values())).manifold.volume() < v0


def test_208_a_profile_under_the_cursor_wins_the_hover_over_its_face(win, monkeypatch):
    vp = win.viewport
    asked = []
    monkeypatch.setattr(vp, "_update_profile_hover", lambda x, y: setattr(vp, "hover_profile", ("sketch_1", 0)))
    monkeypatch.setattr(vp, "_update_edge_hover", lambda x, y: asked.append((x, y)))
    monkeypatch.setattr(vp, "_idle_hover_ok", lambda: True)
    vp.hover_face = object()
    ev = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(50, 50), QPointF(50, 50), Qt.MouseButton.NoButton,
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    vp.mouseMoveEvent(ev)
    assert asked == [] and vp.hover_face is None                 # the face's hover light no longer covers the letter
    monkeypatch.setattr(vp, "_update_profile_hover", lambda x, y: setattr(vp, "hover_profile", None))
    vp.mouseMoveEvent(ev)
    assert len(asked) == 1                                       # off the profile, faces light up as before


def test_209_split_body_fields_are_not_cut_off_in_studio(win):
    from omacad.ui import theme
    from omacad.ui.dialogs.boolean_dlg import SplitBodyDialog
    theme.set_fixed_theme("studio")
    try:
        w = MainWindow()
        w.attach_document(Exporter.load_project(str(DATA / "split_body_panel_209.omacad")))
        w.prompt_split_body()
        QApplication.processEvents()
        dlg = next(x for x in QApplication.allWidgets() if isinstance(x, SplitBodyDialog) and x.window() is w)
        pair = dlg.cmb_target.parentWidget()
        assert pair.height() >= pair.layout().sizeHint().height()
        assert dlg.cmb_target.height() >= dlg.cmb_target.sizeHint().height()
        dlg.reject()
    finally:
        theme.set_fixed_theme(None)


def test_211_delete_on_a_top_object_removes_its_steps_in_one_undo_step(win):
    doc = win.doc
    doc.add_box(20.0, 20.0, 10.0)
    doc.add_cylinder(5.0, 10.0)
    doc.object_history.sync(doc)
    first = next(oid for oid, o in doc.object_history.objects.items() if o.parent_id is None)
    n_bodies, n_steps = len(doc.bodies), len(doc.timeline.features)
    gone = doc.object_delete_indexes(first)
    assert gone and doc.delete_object(first)
    assert len(doc.timeline.features) == n_steps - len(gone) and len(doc.bodies) == n_bodies - 1
    doc.undo()
    assert len(doc.timeline.features) == n_steps and len(doc.bodies) == n_bodies


def test_212_rounding_a_cut_face_leaves_no_sharp_corner_where_a_groove_crosses_it():
    doc = Exporter.load_project(str(DATA / "cut_face_groove_fillet_212.omacad"))
    m = doc.bodies["body_split_6"].manifold
    window = box(-16, -25.5, -12.4, -22)
    for z in (11.6, 12.0, 16.0, 16.8):                            # the groove's flanks, where no edge could be picked
        polys = [Polygon(p).buffer(0) for p in m.slice(z).to_polygons() if len(p) >= 3]
        g = unary_union(polys).intersection(window)
        parts = [g] if g.geom_type == "Polygon" else list(g.geoms)
        pts = np.vstack([np.asarray(p.exterior.coords) for p in parts])
        corner = pts[pts[:, 1] < -23.2]
        assert corner[:, 0].max() < -12.6, z                       # rounded, not the 90° corner at x = -12.5


def test_213_shelled_fillet_is_shaded_smooth_inside_and_out():
    doc = Exporter.load_project(str(DATA / "shelled_fillet_bands_213.omacad"))
    mesh = next(iter(doc.bodies.values())).render_mesh
    V, N = mesh.vertices.reshape(-1, 3), mesh.normals.reshape(-1, 3)
    for radius, sign in ((13.0, 1.0), (9.0, -1.0)):              # the outer fillet and the wall inside after Shell
        d = np.linalg.norm(V[:, :2] - 12.0, axis=1)
        on = (np.abs(d - radius) < 0.05) & (V[:, 0] > 12.3) & (V[:, 1] > 12.3) & (np.abs(N[:, 2]) < 0.5)
        radial = np.zeros_like(V[on])
        radial[:, :2] = sign * (V[on, :2] - 12.0) / d[on, None]
        err = np.degrees(np.arccos(np.clip((N[on] * radial).sum(1), -1.0, 1.0)))
        assert on.sum() > 100 and np.mean(err > 0.5) < 0.01 and err.mean() < 0.1, radius


def test_213_a_corner_without_a_normal_no_longer_makes_the_whole_body_flat():
    """Manifold gave 17 corners of needle triangles a zero normal; the whole body then fell back to flat shading."""
    import types
    import manifold3d as m3d
    body = m3d.Manifold.cube((10, 10, 10)) + m3d.Manifold.cylinder(10, 5, 5, 64).translate((10, 5, 0))
    mesh = body.to_mesh()
    v, f = mesh.vert_properties[:, :3], mesh.tri_verts
    real = CadKernel._shaded_triangles(body, v, f)[1]
    out = body.calculate_normals(0, 30.0).to_mesh()
    props = np.array(out.vert_properties)
    props[int(out.tri_verts[0, 0]), 3:6] = 0.0                      # one corner without a normal
    holed = types.SimpleNamespace(to_mesh=lambda: types.SimpleNamespace(vert_properties=props,
                                                                        tri_verts=np.asarray(out.tri_verts)))
    fake = types.SimpleNamespace(calculate_normals=lambda *_a: holed)
    broken = CadKernel._shaded_triangles(fake, v, f)[1]
    same = (np.abs(broken - real).max(1) < 1e-4).mean()
    assert same > 0.95                                             # only the corners at that vertex differ


def test_flat_rim_beside_a_fillet_keeps_flat_normals():
    """A narrow flat face between a fillet and a sharp edge is not a strip of a curved surface (#204 still holds)."""
    doc = Exporter.load_project(str(DATA / "hover_box_row_204.omacad"))
    body = next(iter(doc.bodies.values()))
    mesh = body.manifold.to_mesh()
    v, f = mesh.vert_properties[:, :3], mesh.tri_verts
    _, normals = CadKernel._shaded_triangles(body.manifold, v, f)
    fn = CadKernel._face_normals(v, f)
    cn = normals.reshape(-1, 3, 3)
    for face in body.faces:
        if np.sort(np.ptp(face.tris.reshape(-1, 3), axis=0))[1] < 1.0:
            continue
        cen = v[f].mean(1)
        on = (np.abs((cen - face.origin) @ face.normal) < 1e-3) & (fn @ face.normal > 0.999)
        dots = (cn[on] * face.normal).sum(2)
        assert np.all(dots > 0.9999), face.index
