"""Fillet and Chamfer UI, viewport interaction, picking, and arrow handle tests."""
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from shapely.geometry import Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import LoopEdge
from omacad.model.faces_types import CircularEdge, PlanarEdge
from omacad.ui.main_window import MainWindow
from omacad.ui.math3d import orbit_view, perspective
from omacad.ui.viewport.picker_mixin import PickerMixin
from omacad.ui.viewport.viewport import Viewport3D

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    yield w
    w.close()


# ==============================================================================
# Face pick selecting boundary loops (Fusion 360 parity)
# ==============================================================================

def test_fillet_face_click_selects_all_boundary_loops():
    doc_path = str(DATA_DIR / "fillet_face_pick.omacad")
    doc = Exporter.load_project(doc_path)
    b = doc.bodies["body_extrude_2"]

    face44 = next(f for f in b.faces if np.allclose(f.normal, [0, 0, 1], atol=1e-3) and abs(f.origin[2] - 10.0) < 1e-4)

    class MockDoc:
        bodies = doc.bodies

    class MockViewport(Viewport3D):
        def __init__(self):
            self.doc = MockDoc()
            self.edge_pick_mode = True
            self.edge_xray = False
            self.hover_edge = None
            self.hover_face = self.hover_surface = None
            self.selected_edges = []
            self._w, self._h = 2036 - 360, 1114
            self.cam_az = 170.87696587004527
            self.cam_el = 17.911718750000006
            self.cam_dist = 99.63236863613498
            self.cam_target = np.array([-4.469699859619141, 11.18025016784668, 5.0])

        def width(self):
            return self._w

        def height(self):
            return self._h

        def get_matrices(self):
            view = orbit_view(self.cam_target, self.cam_dist, self.cam_az, self.cam_el)
            proj = perspective(45.0, self._w / self._h, max(0.5, self.cam_dist * 0.01), self.cam_dist + 5000.0)
            return proj, view, np.eye(4)

        def world_to_screen(self, p):
            proj, view, _ = self.get_matrices()
            mvp = proj @ view
            v = mvp @ np.array([p[0], p[1], p[2], 1.0], dtype=np.float32)
            if v[3] <= 0:
                return None
            ndc = v[:3] / v[3]
            return ((ndc[0] * 0.5 + 0.5) * self._w, (1.0 - (ndc[1] * 0.5 + 0.5)) * self._h)

        def update(self):
            pass

    vp = MockViewport()
    face_edges = vp._edges_of_face(face44, b)
    assert sum(isinstance(e, LoopEdge) for e in face_edges) == 13
    assert sum(e.kind == "line" for e in face_edges) == 338

    interior_pt = np.array([-7.68197464, -26.07341804, 10.0])
    vp.cam_target, vp.cam_dist = interior_pt, 40.0
    scr = vp.world_to_screen(interior_pt)
    assert scr is not None
    sx, sy = scr

    assert vp._pick_edge(sx, sy) is None
    hit = vp._pick_face(sx, sy)
    assert hit is not None
    hit_body, hit_face = hit
    assert hit_face.index == face44.index

    vp._update_edge_hover(sx, sy)
    assert vp.hover_edge is None
    assert vp.hover_face is not None
    assert vp.hover_face.index == face44.index

    edges = vp._edges_of_face(hit_face, hit_body)
    for fe in edges:
        if not any(vp._same_edge(k, fe) for k in vp.selected_edges):
            vp.selected_edges.append(fe)

    assert len(vp.selected_edges) == len(face_edges)


def test_honeycomb_box_side_selects_every_cell_outline():
    from shapely.ops import unary_union
    doc = Exporter.load_project(str(DATA_DIR / "honeycomb_box_face_edges.omacad"))
    body = next(iter(doc.bodies.values()))
    side = max((f for f in body.faces if f.index >= 0 and abs(f.normal[1] + 1) < 1e-3), key=lambda f: f.area)
    edges = PickerMixin._edges_of_face(None, side, body)
    kinds = {e.kind for e in edges}
    assert "line" in kinds and kinds <= {"loop", "line"}

    def _outline_len(face):
        n = np.asarray(face.normal, dtype=float)
        u = np.cross(n, [0.0, 0.0, 1.0] if abs(n[2]) < 0.9 else [1.0, 0.0, 0.0])
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        region = unary_union([Polygon([(p @ u, p @ v) for p in t]).buffer(1e-6) for t in face.tris])
        return region.boundary.length

    total = sum(float(np.linalg.norm(np.diff(e.polyline(), axis=0), axis=1).sum()) for e in edges)
    assert abs(total - _outline_len(side)) < 1e-2 * _outline_len(side)


# ==============================================================================
# Live result in section view (Report 20261025-120548)
# ==============================================================================

def _cut_area(vp, bid):
    cap = next(c for c in vp.section["caps"] if c["body_id"] == bid)
    rings = [Polygon(p) for p in cap["polys"]]
    return sum(r.area if r.exterior.is_ccw else -r.area for r in rings)


def test_chamfer_result_is_cut_by_the_section_view(win):
    body = win.doc.add_box(30, 20, 10)
    x0, y0, z0, x1, y1, z1 = body.manifold.bounding_box()
    vp = win.viewport
    win.doc.add_section(((x0 + x1) / 2, 0, 0), (1, 0, 0), 0.0)
    whole = vp.section["meshes"][body.body_id]
    assert abs(_cut_area(vp, body.body_id) - 20 * 10) < 1e-6

    win.prompt_round_edges("chamfer")
    dlg = win._round_dlg
    dlg.spn_size.setValue(2.0)
    edge = next(e for e in body.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - z1) < 1e-6 and abs(e.p1[2] - z1) < 1e-6 and abs(e.p0[0] - e.p1[0]) > 1)
    vp.selected_edges = [edge]
    vp.edges_selection_changed.emit()
    assert vp.section is not None and body.body_id in vp.display_override
    cut = vp.section["meshes"][body.body_id]
    assert len(cut.vertices) > len(whole.vertices) and max(cut.vertices[:, 0]) <= (x0 + x1) / 2 + 1e-6
    assert abs(_cut_area(vp, body.body_id) - (20 * 10 - 2 * 2 / 2)) < 1e-6

    dlg.reject()
    QApplication.processEvents()
    assert vp.section is not None and len(vp.section["meshes"][body.body_id].vertices) == len(whole.vertices)
    assert abs(_cut_area(vp, body.body_id) - 20 * 10) < 1e-6


# ==============================================================================
# Live result & Chamfer types dialog interaction
# ==============================================================================

def test_live_result_and_chamfer_types(win):
    body = win.doc.add_box(30, 20, 10)
    win.prompt_round_edges("chamfer")
    dlg = win._round_dlg
    vp = win.viewport
    assert not dlg.spn_size2.isVisibleTo(dlg) and not dlg.chk_flip.isVisibleTo(dlg)
    top = body.manifold.bounding_box()[5]
    edge = next(e for e in body.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - top) < 1e-6 and abs(e.p1[2] - top) < 1e-6 and abs(e.p0[0] - e.p1[0]) > 1)
    vp.selected_edges = [edge]
    vp.edges_selection_changed.emit()
    shown = vp.display_override[body.body_id]
    assert len(shown.vertices) > len(body.render_mesh.vertices)
    assert vp.preview_mesh is None
    dlg.cmb_chamfer.setCurrentIndex(1)
    assert dlg.spn_size2.isVisibleTo(dlg) and dlg.chk_flip.isVisibleTo(dlg) and not dlg.spn_angle.isVisibleTo(dlg)
    dlg.spn_size.setValue(4.0)
    dlg.spn_size2.setValue(1.5)
    dlg.chk_chain.setChecked(False)
    assert vp.edge_tangent_chain is False
    dlg.accept()
    QApplication.processEvents()
    feat = win.doc.timeline.features[-1]
    assert (feat.kind, feat.chamfer_type, feat.size, feat.size2) == ("chamfer", "two", 4.0, 1.5)
    assert vp.display_override is None and vp.edge_tangent_chain is True
    vol = next(iter(win.doc.bodies.values())).manifold.volume()
    assert abs(vol - (30 * 20 * 10 - 0.5 * 4.0 * 1.5 * 30)) < 1e-6


# ==============================================================================
# Multi-edge picking marking lines (Report 20261101-100445, 20261103-203138)
# ==============================================================================

def test_fillet_marking_edges_shows_actual_edge_position():
    doc = Document()
    body = doc.add_box(70.0, 40.0, 10.0)

    picker = PickerMixin()
    picker.doc = doc

    top_edges = [
        e for e in body.edges
        if getattr(e, "kind", "") == "line" and abs(e.p0[2] - 10.0) < 1e-3 and abs(e.p1[2] - 10.0) < 1e-3
    ]
    assert len(top_edges) == 4

    picker.selected_edges = list(top_edges[:3])
    picker.hover_edge = top_edges[3]
    picker.fillet_rail_offset = 2.0

    edge_pick_cache = picker._edge_segments(body)
    assert len(edge_pick_cache) == 4
    assert len(edge_pick_cache[0]) == len(body.edges)

    hover_segs = np.array(picker._edge_render_lines([picker.hover_edge])).reshape(-1, 3)
    assert np.allclose(hover_segs[:, 2], 10.0, atol=1e-5)

    selected_segs = np.array(picker._edge_render_lines(picker.selected_edges, picker.fillet_rail_offset)).reshape(-1, 3)
    assert np.allclose(selected_segs[:, 2], 8.0, atol=1e-5)


def test_fillet_frame_follows_down_from_report_document():
    doc_path = Path(__file__).parent.parent / ".state" / "data" / "feedback" / "20261103-203138" / "document.omacad"
    if not doc_path.exists():
        pytest.skip("feedback document not present")
    doc = Exporter.load_project(str(doc_path))
    doc.timeline.step_to(1, doc)
    body = list(doc.bodies.values())[0]

    picker = PickerMixin()
    picker.doc = doc

    top_lines = [
        e for e in body.edges
        if getattr(e, "kind", "") == "line" and abs(e.p0[2] - 42.0) < 1e-3 and abs(e.p1[2] - 42.0) < 1e-3
    ]
    assert len(top_lines) == 4

    picker.selected_edges = list(top_lines)
    picker.fillet_rail_offset = 6.7

    selected_segs = np.array(picker._edge_render_lines(picker.selected_edges, picker.fillet_rail_offset)).reshape(-1, 3)
    assert np.allclose(selected_segs[:, 2], 42.0 - 6.7, atol=1e-4)


# ==============================================================================
# Fillet rail guide lines shift direction (Report 20261031-165820)
# ==============================================================================

def test_fillet_rail_offset_direction():
    picker = PickerMixin()

    corner_arc = CircularEdge(
        center=np.array([47.0, 32.0, 25.0]),
        axis=np.array([0.0, 0.0, 1.0]),
        radius=3.0,
        s1=-1.0,
        s2=-1.0,
        convex=True,
    )

    offset_val = 2.0
    orig_pts = corner_arc.polyline()
    shifted_pts = picker._offset_edge_polyline(corner_arc, offset_val)
    assert np.allclose(orig_pts[:, 2] - offset_val, shifted_pts[:, 2], atol=1e-5)


def test_fillet_rail_offset_from_report_document():
    doc_path = DATA_DIR / "fillet_corner_rail_offset.omacad"
    if not doc_path.exists():
        pytest.skip("fillet_corner_rail_offset.omacad not present")
    doc = Exporter.load_project(str(doc_path))
    doc.timeline.step_to(2, doc)
    body = list(doc.bodies.values())[0]

    picker = PickerMixin()
    top_lines = [e for e in body.edges if e.kind == "line" and abs(e.p0[2] - 25.0) < 1e-3 and abs(e.p1[2] - 25.0) < 1e-3]
    top_arcs = [e for e in body.edges if e.kind == "circle" and abs(e.center[2] - 25.0) < 1e-3]

    assert len(top_lines) > 0
    assert len(top_arcs) > 0

    offset_val = 3.0
    for line in top_lines:
        orig = line.polyline()
        shifted = picker._offset_edge_polyline(line, offset_val)
        assert np.allclose(orig[:, 2] - offset_val, shifted[:, 2], atol=1e-4)

    for arc in top_arcs:
        orig = arc.polyline()
        shifted = picker._offset_edge_polyline(arc, offset_val)
        assert np.allclose(orig[:, 2] - offset_val, shifted[:, 2], atol=1e-4)


# ==============================================================================
# Fillet/Chamfer arrow handles (Report 20261031-072053)
# ==============================================================================

def test_fillet_chamfer_arrow_direction():
    doc = Document()
    body = doc.add_box(10.0, 10.0, 10.0)

    convex_edges = [e for e in body.edges if hasattr(e, "p0") and getattr(e, "convex", True)]
    assert len(convex_edges) > 0
    for e in convex_edges:
        axis = e.d1 + e.d2
        assert np.linalg.norm(axis) > 1e-6
        assert (axis @ e.n1) <= 1e-6
        assert (axis @ e.n2) <= 1e-6


def test_fillet_arrow_vertical_along_wall_for_horizontal_edge(win):
    body = win.doc.add_box(30.0, 20.0, 10.0)
    win.prompt_round_edges("fillet")
    top_edges = [e for e in body.edges if hasattr(e, "p0") and abs(e.p0[2] - 10.0) < 1e-6 and abs(e.p1[2] - 10.0) < 1e-6]
    assert len(top_edges) > 0
    win.viewport.selected_edges = [top_edges[0]]
    win.viewport.edges_selection_changed.emit()

    handle = win.viewport.extrude_handle
    assert handle is not None
    assert np.allclose(handle["axis"], [0.0, 0.0, -1.0])

    bottom_edges = [e for e in body.edges if hasattr(e, "p0") and abs(e.p0[2]) < 1e-6 and abs(e.p1[2]) < 1e-6]
    assert len(bottom_edges) > 0
    win.viewport.selected_edges = [bottom_edges[0]]
    win.viewport.edges_selection_changed.emit()
    handle_bottom = win.viewport.extrude_handle
    assert handle_bottom is not None
    assert np.allclose(handle_bottom["axis"], [0.0, 0.0, 1.0])


def test_fillet_arrow_drag_up_and_down_clamps_not_flips(win):
    win.doc.add_box(30.0, 20.0, 10.0)
    win.prompt_round_edges("fillet")
    dlg = win._round_dlg
    vp = win.viewport

    vp.extrude_handle_dragged.emit(5.0)
    assert dlg.spn_size.value() == 5.0
    vp.extrude_handle_dragged.emit(1.5)
    assert dlg.spn_size.value() == 1.5
    vp.extrude_handle_dragged.emit(0.0)
    assert dlg.spn_size.value() == 0.2
    vp.extrude_handle_dragged.emit(-3.5)
    assert dlg.spn_size.value() == 0.2


# ==============================================================================
# Wrapped edge picking in Viewport3D
# ==============================================================================

def test_cylindrical_face_can_select_its_nonplanar_boundary():
    doc_path = str(DATA_DIR / "wrapped_deboss_fillet.omacad")
    doc = Exporter.load_project(doc_path)
    vp = Viewport3D(doc)
    vp.paintGL = lambda: None
    vp.initializeGL = lambda: None
    vp.resize(1000, 800)
    vp.azimuth, vp.elevation, vp.distance = 0.0, 0.0, 80.0
    vp.target = np.array([0.0, 0.0, 10.0], dtype=np.float32)
    vp.edge_pick_mode = True
    point = vp.world_to_screen(np.array([0.0, -19.0, 10.0]))
    body, face = vp._pick_face(*point)
    edges = vp._edges_of_face(face, body)
    assert len(edges) == 1 and edges[0].kind == "wrapped" and not edges[0].convex
    mouse = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(*point), QPointF(*point),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    vp.mousePressEvent(mouse)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(*point), QPointF(*point),
                          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    vp.mouseReleaseEvent(release)
    assert len(vp.selected_edges) == 1
    assert vp.selected_edges[0].same_as(edges[0])
    vp.edge_pick_mode = False
    hit = vp._pick_face(*point)
    assert hit is None or hit[1].index >= 0
    vp.close()
