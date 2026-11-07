"""Tests for SolidCraft-style face selection, boundary edge outlines, and body rendering."""
from pathlib import Path
import numpy as np

from omacad.io.exporter import Exporter
from omacad.ui.viewport.picker_mixin import PickerMixin, patch_boundary_segments
from omacad.ui.viewport.shaders import FRAGMENT_SHADER_SOLID


FIXTURE = Path(__file__).parent / "data" / "solidcraft_face_selection_fillet_box.omacad"


class DummySignal:
    def emit(self, *args, **kwargs):
        pass


class DummyViewport(PickerMixin):
    def __init__(self, doc):
        self.doc = doc
        self.selected_faces = []
        self.selected_edges = []
        self.hover_edge = None
        self.hover_face = None
        self.hover_surface = None
        self.edge_pick_mode = False
        self.plane_pick_mode = False
        self.hover_info_changed = DummySignal()
        self._matrices = None
        self._w = 1200
        self._h = 800

    def width(self):
        return self._w

    def height(self):
        return self._h

    def update(self):
        pass


def test_solidcraft_studio_shader_has_view_lighting_and_specular():
    assert "u_eye_dir" in FRAGMENT_SHADER_SOLID
    assert "spec" in FRAGMENT_SHADER_SOLID
    assert "dot(n, v) < 0.0" in FRAGMENT_SHADER_SOLID


def test_patch_boundary_segments_extracts_outer_edges():
    # 2-triangle quad
    quad = np.array([
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]],
        [[10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [0.0, 10.0, 0.0]]
    ], dtype=np.float32)
    b = patch_boundary_segments(quad)
    assert len(b) == 4
    # Empty patch
    assert len(patch_boundary_segments(None)) == 0
    assert len(patch_boundary_segments(np.zeros((0, 3, 3)))) == 0


def test_face_selection_and_boundary_edges_on_report_document():
    doc = Exporter.load_project(str(FIXTURE))
    vp = DummyViewport(doc)
    body = next(iter(doc.bodies.values()))

    # Find planar faces
    planar_faces = [f for f in body.faces if f.index >= 0]
    assert len(planar_faces) > 0
    top_face = max(planar_faces, key=lambda f: f.area)

    # 1. Select face
    vp.select_face(body.body_id, top_face, multi=False)
    assert len(vp.selected_faces) == 1
    assert vp.selected_faces[0][0] == body.body_id
    assert vp.selected_faces[0][1].index == top_face.index

    # 2. Extract boundary edges of the face
    edges = vp._edges_of_face(top_face, body)
    assert len(edges) > 0

    # 3. Multi-selection: add another face
    other_face = next(f for f in planar_faces if f.index != top_face.index)
    vp.select_face(body.body_id, other_face, multi=True)
    assert len(vp.selected_faces) == 2

    # Toggle off the second face
    vp.select_face(body.body_id, other_face, multi=True)
    assert len(vp.selected_faces) == 1
    assert vp.selected_faces[0][1].index == top_face.index

    # Clear selection
    vp.clear_face_selection()
    assert len(vp.selected_faces) == 0


def test_curved_surface_with_normals_and_tangent_settings():
    from omacad.ui.settings import get_settings
    # Tangent edges are enabled by default like SolidCraft
    assert get_settings().get("show_tangent_edges") is True

    doc = Exporter.load_project(str(FIXTURE))
    body = next(iter(doc.bodies.values()))
    rm = body.render_mesh
    assert rm is not None
    # If there are curved surface triangles (e.g. fillet), curved_surface_with_normals returns vertices and normals
    if rm.source is not None:
        v, f, keep = rm.source
        from omacad.model.faces_surfaces import curved_surface_ids
        import trimesh
        from omacad.model.kernel import CadKernel
        ids = curved_surface_ids(v, f, trimesh.Trimesh(vertices=v, faces=f, process=False), CadKernel.SHARP_EDGE_DEG)
        curved_tris = np.where(ids >= 0)[0]
        if len(curved_tris) > 0:
            res = rm.curved_surface_with_normals(int(curved_tris[0]))
            assert res is not None
            verts, norms = res
            assert verts.shape == norms.shape
            assert verts.ndim == 3 and verts.shape[1:] == (3, 3)
            assert norms.dtype == np.float32


def test_idle_hover_precedence_over_edges():
    doc = Exporter.load_project(str(FIXTURE))
    vp = DummyViewport(doc)
    body = next(iter(doc.bodies.values()))
    planar_faces = [f for f in body.faces if f.index >= 0]
    top_face = max(planar_faces, key=lambda f: f.area)

    # In idle mode (edge_pick_mode = False), mock _pick_face returning top_face
    # and _pick_edge returning an edge: face should take precedence
    vp._pick_face = lambda x, y: (body, top_face)
    vp._pick_edge = lambda x, y: "dummy_edge"
    vp._pick_curved_surface = lambda x, y: None

    vp._update_edge_hover(100.0, 100.0)
    assert vp.hover_face is top_face
    assert vp.hover_edge is None

    # In edge pick mode, edge takes precedence
    vp.edge_pick_mode = True
    vp._update_edge_hover(100.0, 100.0)
    assert vp.hover_edge == "dummy_edge"
