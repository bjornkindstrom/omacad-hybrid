"""A body with a pattern has thousands of patches: edge analysis must not do whole-mesh work per patch or per pair.

A shelled cylinder with 119 SVG cells took minutes on OK of the next step. These tests count the expensive calls instead
of the seconds, so they neither depend on the machine nor pass by luck.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import trimesh
from PySide6.QtWidgets import QApplication
from shapely.geometry import LineString, Point

from omacad import viewport_accel
from omacad.model import wrapped_edges
from omacad.model.document import Document
from omacad.model.faces_surfaces import compute_planar_faces_and_edges
from omacad.model.features.honeycomb import HoneycombFeature
from omacad.model.kernel import CadKernel
from omacad.model.svg_importer import CELL_CHORD_ERROR, parse_svg_to_geometry, svg_to_template
from omacad.ui.main_window import MainWindow
from omacad.ui.viewport import profile_mixin

R, H, WALL = 40.0, 80.0, 2.5
# a ring, as the report's logo is: the island left inside each cell is what has a closed rim on the cylinder
RING = ('<svg xmlns="http://www.w3.org/2000/svg"><ellipse cx="0" cy="0" rx="20" ry="12"/>'
        '<ellipse cx="0" cy="0" rx="14" ry="8"/></svg>')


def _params(svg, **changes):
    return {"shape": "svg", "svg_path": str(svg), "size": 12.0, "wall": 2.0, "margin": 5.0, "depth": 1.0, "through": True,
            "angle": 0.0, "partial": False, "randomness": 100.0, "seed": 1, "style": "even", "fine_size": 2.0,
            "inner_wall": 0.8, "hotspots": 1, "rounding": 0.0, "opening": 100.0, "opening_end": 100.0, "relaxation": 0,
            "hole": "cell", **changes}


@pytest.fixture(scope="module")
def patterned(tmp_path_factory):
    """(solid, cells): a shelled cylinder with ring shaped cells cut right through its wall."""
    svg = tmp_path_factory.mktemp("svg") / "ring.svg"
    svg.write_text(RING)
    doc = Document()
    body = doc.add_cylinder(R, H)
    doc.add_shell(body.body_id, WALL, open_faces=[{"normal": [0, 0, 1], "origin": [0, 0, H]}])
    ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": R, "length": H, "internal": False}
    solid, cells, skipped = HoneycombFeature.compute(doc.bodies[body.body_id].manifold, [ref], _params(svg))
    assert cells > 50 and skipped == 0
    return solid, cells


def _arrays(solid):
    mesh = solid.to_mesh64()
    v = np.asarray(mesh.vert_properties[:, :3], dtype=np.float64)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    return v, f, trimesh.Trimesh(vertices=v, faces=f, process=False)


def _count_calls(monkeypatch, name, keep=lambda *a, **k: True):
    calls = []
    original = getattr(np, name)

    def counted(*args, **kwargs):
        if keep(*args, **kwargs):
            calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(np, name, counted)
    return calls


def test_contours_are_not_tried_patch_by_frame_with_a_full_point_list(patterned, monkeypatch):
    solid, cells = patterned
    v, f, tm = _arrays(solid)
    tm.face_adjacency, tm.face_adjacency_angles, tm.face_adjacency_edges, tm.face_adjacency_convex, tm.area_faces
    calls = _count_calls(monkeypatch, "unique")
    wrapped_edges.cylindrical_contours(v, f, tm)
    assert len(calls) < 12 * len(f) ** 0.5 + 40 * cells     # about one per patch; per pair it was 250 000


def test_each_cell_rim_is_still_found_on_the_cylinder(patterned):
    solid, cells = patterned
    v, f, tm = _arrays(solid)
    contours = wrapped_edges.cylindrical_contours(v, f, tm)
    assert len(contours) == 2 * cells                       # the ring's outer and inner rim
    assert all(c.radius == pytest.approx(R, abs=0.05) and c.convex for c in contours)   # chords lie just inside R


def test_analysis_measures_the_mesh_once_not_per_face(patterned, monkeypatch):
    solid, _ = patterned
    v, f, _tm = _arrays(solid)
    whole = len(v)
    # a new mesh, as the analysis caches by content
    moved = solid.translate((1.0, 2.0, 3.0))
    calls = _count_calls(monkeypatch, "ptp", lambda a, *rest, **k: np.shape(a)[0] == whole)
    faces, edges = compute_planar_faces_and_edges(moved, "b")
    assert faces and edges
    assert len(calls) < 20


@pytest.mark.skipif(viewport_accel.backend_name() != "rust", reason="native backend only")
def test_snapping_only_the_used_vertices_gives_the_same_segments():
    # a duplicate of vertex 2 within tolerance (5), a duplicate segment and some vertices no segment uses
    v = np.array([[9.0, 9, 9], [0, 0, 0], [1, 0, 0], [7, 7, 7], [2, 0, 0], [1 + 1e-7, 0, 0], [8, 8, 8]])
    segments = [[1, 2], [5, 4], [2, 4], [4, 2], [1, 1]]
    full = np.frombuffer(viewport_accel._NATIVE.snap_and_clean_segments(
        np.ascontiguousarray(v, dtype="<f8").tobytes(), np.ascontiguousarray(segments, dtype="<u8").tobytes(), 1e-5),
        dtype="<u8").reshape(-1, 3)
    assert viewport_accel.snap_and_clean_segments(v, segments, 1e-5).tolist() == full.tolist()


def test_a_cell_stays_on_its_curve_without_needless_points(tmp_path):
    svg = tmp_path / "circle.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><circle cx="0" cy="0" r="500"/></svg>')
    polys, _ = svg_to_template(parse_svg_to_geometry(str(svg)), 12.0)
    ring = polys[0].exterior
    round_outline = Point(0.0, 0.0).buffer(6.0, quad_segs=256).exterior
    assert ring.hausdorff_distance(round_outline) <= CELL_CHORD_ERROR * 1.1
    assert len(ring.coords) < 60
    assert LineString(ring.coords).length == pytest.approx(2 * np.pi * 6.0, rel=2e-3)


def test_a_flat_shaded_mesh_is_the_same_mesh(patterned):
    solid, _ = patterned
    smooth = CadKernel.extract_render_mesh(solid)
    flat = CadKernel.extract_render_mesh(solid, smooth=False)
    assert flat.vertices.shape == smooth.vertices.shape and flat.normals.shape == smooth.normals.shape
    assert len(flat.sharp_lines) == len(smooth.sharp_lines)
    tris = flat.vertices.reshape(-1, 3, 3)
    normals = flat.normals.reshape(-1, 3, 3)
    assert np.array_equal(normals[:, 0], normals[:, 1]) and np.array_equal(normals[:, 1], normals[:, 2])
    cross = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    big = np.linalg.norm(cross, axis=1) > 1e-2
    assert (np.einsum("ij,ij->i", cross[big], normals[big, 0]) > 0).all()


def test_a_preview_is_flat_above_the_limit_and_smooth_below_it(patterned, monkeypatch):
    QApplication.instance() or QApplication([])
    solid, _ = patterned
    window = MainWindow()
    seen = []
    original = CadKernel.extract_render_mesh

    def spy(manifold, *args, **kwargs):
        seen.append(kwargs.get("smooth", True))
        return original(manifold, *args, **kwargs)
    monkeypatch.setattr(profile_mixin.CadKernel, "extract_render_mesh", staticmethod(spy))
    monkeypatch.setattr(profile_mixin, "PREVIEW_SMOOTH_TRIANGLES", solid.num_tri() - 1)
    window.viewport.set_display_override({"b": solid})
    monkeypatch.setattr(profile_mixin, "PREVIEW_SMOOTH_TRIANGLES", solid.num_tri())
    window.viewport.set_display_override({"b": solid})
    window.viewport.set_display_override(None)
    window.close()
    assert seen == [False, True]
