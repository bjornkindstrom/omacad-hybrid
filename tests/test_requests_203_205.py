"""Requests #203–#205: hover and selection artefacts with "Fast view" display smoothing."""
from pathlib import Path

import numpy as np
import pytest
import trimesh

from omacad.io.exporter import Exporter
from omacad.model import quality
from omacad.model.display_smooth import smooth_arrays
from omacad.model.kernel import CadKernel
from omacad.ui.viewport.picker_mixin import patch_boundary_segments

DATA = Path(__file__).parent / "data"


def _body(name):
    quality.set_fast_view(True, 72)
    doc = Exporter.load_project(str(DATA / name))
    return doc, next(iter(doc.bodies.values()))


def _drawn_points(mesh):
    base = np.ascontiguousarray(np.round(mesh.display_arrays(mesh.sharp_lines)[0], 4))
    return base, np.dtype((np.void, 3 * base.dtype.itemsize))


def test_box_side_beside_rounded_corners_is_drawn_flat():
    """#203: the side's two big triangles borrowed 0.7° tilted normals from the rounded corners and were bulged
    0.1 mm off the face, so the hover highlight (on the real face) showed only in stripes."""
    _, body = _body("hover_chamfered_box_203.omacad")
    mesh = body.render_mesh
    xmin = float(mesh.vertices[:, 0].min())
    side = next(f for f in body.faces if f.normal[0] < -0.99)
    v, n, _ = mesh.display_arrays(mesh.sharp_lines)
    t = v.reshape(-1, 3, 3)
    own = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    own /= np.maximum(np.linalg.norm(own, axis=1, keepdims=True), 1e-12)
    facing = (own[:, 0] < -0.9999) & (t[:, :, 0].mean(axis=1) < xmin + 1.0)
    centres = t[facing].mean(axis=1)
    on_side = (centres[:, 1] > side.tris[:, :, 1].min() + 1e-3) & (centres[:, 1] < side.tris[:, :, 1].max() - 1e-3)
    assert on_side.sum() >= 2
    assert np.allclose(t[facing][on_side][:, :, 0], xmin, atol=1e-4)


def test_curved_triangles_are_still_smoothed():
    """A real curve (72 pieces a circle, corners 2.5° off the chord) keeps its Phong bulge."""
    a0, a1 = 0.0, np.radians(5.0)
    p = np.array([[np.cos(a0), np.sin(a0), 0], [np.cos(a1), np.sin(a1), 0], [np.cos(a1), np.sin(a1), 1],
                  [np.cos(a0), np.sin(a0), 0], [np.cos(a1), np.sin(a1), 1], [np.cos(a0), np.sin(a0), 1]]) * 10
    n = p.copy()
    n[:, 2] = 0
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    v, _, _ = smooth_arrays(p.astype(np.float32), n.astype(np.float32), np.zeros((0, 3), np.float32))
    radius = np.linalg.norm(v[:, :2], axis=1)
    assert len(v) > len(p) and radius.max() == pytest.approx(10.0, abs=1e-3)


@pytest.mark.parametrize("name", ["hover_chamfered_box_203.omacad", "hover_box_row_204.omacad"])
def test_hovered_face_is_drawn_on_the_bodys_own_display_geometry(name):
    """#203/#204: the hover patch goes through `display_patch_arrays` and, like the body around it, stays in the
    face's plane (before, the smoothed body bulged in front of the raw patch)."""
    _, body = _body(name)
    mesh = body.render_mesh
    base, dtype = _drawn_points(mesh)
    for face in body.faces:
        if np.sort(np.ptp(face.tris.reshape(-1, 3), axis=0))[1] < 1.0:
            continue                # a 0.2 mm strip of a rounded corner is curved and drawn so
        drawn, _, _ = mesh.display_patch_arrays(face.tris, np.zeros((0, 3), np.float32))
        drawn = np.asarray(drawn, dtype=np.float64).reshape(-1, 3)
        assert np.abs((drawn - face.origin) @ face.normal).max() < 1e-3, face.index
        pts = np.ascontiguousarray(np.round(drawn.astype(np.float32), 4))
        assert np.isin(pts.view(dtype).ravel(), base.view(dtype).ravel()).mean() > 0.9, face.index


def test_inner_wall_of_shelled_loft_is_one_surface_outlined_only_at_its_rim():
    """#205: ~800 specks inside the inner wall each drew their own outline, plus a zigzag along the rim."""
    _, body = _body("selection_loft_shell_205.omacad")
    mesh = body.render_mesh
    v, f, _ = mesh.source
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
    triangles = np.asarray(mesh.vertices).reshape(-1, 3, 3)
    centres = triangles.mean(axis=1)
    own = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    own /= np.maximum(np.linalg.norm(own, axis=1, keepdims=True), 1e-12)
    # inner wall: high up, facing in towards the axis
    inside = np.flatnonzero((centres[:, 2] > 120) & ((centres[:, :2] * own[:, :2]).sum(axis=1) < -1.)
                            & (np.abs(own[:, 2]) < .9))
    mesh.curved_surface_with_normals(int(inside[0]))
    labels, counts = np.unique(mesh._surface_ids[inside], return_counts=True)
    label = int(labels[np.argmax(counts)])
    # the smooth region this surface lies in (bounded by sharp creases) is that one surface, with no specks left
    smooth = tm.face_adjacency[tm.face_adjacency_angles <= np.radians(CadKernel.SHARP_EDGE_DEG)]
    region = np.arange(len(f))
    while True:
        low = np.minimum(region[smooth[:, 0]], region[smooth[:, 1]])
        new = region.copy()
        np.minimum.at(new, smooth[:, 0], low)
        np.minimum.at(new, smooth[:, 1], low)
        new = new[new]
        if np.array_equal(new, region):
            break
        region = new
    wall = region == region[np.flatnonzero(mesh._surface_ids == label)[0]]
    assert wall.sum() > 5000
    assert np.all(mesh._surface_ids[wall] == label)
    patch, _ = mesh.curved_surface_with_normals(int(np.flatnonzero(mesh._surface_ids == label)[0]))
    boundary = patch_boundary_segments(patch)
    # every outline piece runs along a sharp crease of the body (rim, floor), none across the smooth wall
    sharp = tm.face_adjacency_edges[tm.face_adjacency_angles > np.radians(CadKernel.SHARP_EDGE_DEG)]
    keys = {tuple(sorted((tuple(np.round(v[a], 3)), tuple(np.round(v[b], 3))))) for a, b in sharp.tolist()}
    seg = {tuple(sorted((tuple(np.round(s[0].astype(np.float64), 3)), tuple(np.round(s[1].astype(np.float64), 3)))))
           for s in boundary}
    assert len(boundary) > 100
    assert len(seg - keys) <= 0.02 * len(seg), len(seg - keys)
