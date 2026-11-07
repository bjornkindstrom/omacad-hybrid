"""Fast view, exact export: the view builds round shapes coarser and draws them smoothed; exports are exact."""
import math

import numpy as np
import manifold3d as m3d

from omacad.model import quality
from omacad.model.kernel import CadKernel
from omacad.model.display_smooth import smooth_arrays
from omacad.model.document import Document
from omacad.io.exporter import Exporter


def _cylinder_mesh(segments, r=10.0, h=20.0):
    return CadKernel.extract_render_mesh(m3d.Manifold.cylinder(h, r, r, circular_segments=segments))


def test_smoothed_cylinder_is_round_and_its_caps_follow_the_wall():
    r, n = 10.0, 24
    mesh = _cylinder_mesh(n, r)
    verts, normals, lines = smooth_arrays(mesh.vertices, mesh.normals, mesh.sharp_lines)
    assert len(verts) > len(mesh.vertices)
    radial = np.hypot(verts[:, 0], verts[:, 1])
    on_rim = np.abs(normals[:, 2]) < 0.5               # the wall's corners (cap corners point up/down)
    sag = r * (1 - math.cos(math.pi / n))             # how far the 24 chords sag inside the circle
    # every drawn point near the wall lies on the true circle, far closer than the chords did
    assert np.abs(radial[on_rim] - r).max() < sag / 20
    # cap rims moved out with the wall, in the cap plane: the caps stay flat
    caps = np.abs(normals[:, 2]) > 0.5
    assert np.all(np.isclose(verts[caps, 2], 0.0, atol=1e-5) | np.isclose(verts[caps, 2], 20.0, atol=1e-5))
    # no crack: the cap's outermost points reach the wall's
    cap = np.abs(verts[:, 2] - 20.0) < 1e-6
    assert abs(radial[cap].max() - r) < sag / 20
    # the edge lines (rims) are smoothed too and stay on the circle
    lr = np.hypot(lines[:, 0], lines[:, 1])
    assert len(lines) == 4 * len(mesh.sharp_lines) and np.abs(lr - r).max() < sag / 20
    # normals are unit length
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-5)


def test_box_is_drawn_unchanged():
    mesh = CadKernel.extract_render_mesh(m3d.Manifold.cube((10, 10, 10)))
    verts, _, lines = smooth_arrays(mesh.vertices, mesh.normals, mesh.sharp_lines)
    assert len(verts) == len(mesh.vertices) and len(lines) == len(mesh.sharp_lines)


def test_view_is_coarser_but_the_export_is_built_at_full_smoothness(tmp_path):
    quality.set_circle_segments(96)
    quality.set_fast_view(True, 32)
    try:
        assert quality.circle_segments() == 32 and quality.fast_view_active()
        doc = Document()
        doc.add_cylinder(radius=10.0, height=20.0)
        body = next(iter(doc.bodies.values()))
        view_volume = body.manifold.volume()
        exact = Exporter.exact_document(doc)
        exact_volume = next(iter(exact.bodies.values())).manifold.volume()
        polygon = lambda n: 0.5 * n * 100.0 * math.sin(2 * math.pi / n) * 20.0
        assert math.isclose(view_volume, polygon(32), rel_tol=1e-6)
        assert math.isclose(exact_volume, polygon(96), rel_tol=1e-6)
        assert quality.circle_segments() == 32      # the view goes on coarse after the export
        path = tmp_path / "c.stl"
        assert Exporter.export_all_to_stl(doc, str(path))
        import trimesh
        assert math.isclose(trimesh.load(str(path)).volume, polygon(96), rel_tol=1e-5)
        # the live document is untouched
        assert math.isclose(next(iter(doc.bodies.values())).manifold.volume(), view_volume, rel_tol=1e-9)
    finally:
        quality.set_fast_view(False)


def test_without_fast_view_the_export_uses_the_document_itself():
    quality.set_fast_view(False)
    doc = Document()
    assert Exporter.exact_document(doc) is doc
