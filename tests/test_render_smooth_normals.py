"""#61: curved surfaces are shaded smooth (shared vertex normals), sharp CAD edges stay crisp."""
import numpy as np
import manifold3d as m3d

from omacad.model.kernel import CadKernel


def test_box_keeps_flat_faces():
    rm = CadKernel.extract_render_mesh(m3d.Manifold.cube((10, 20, 5)))
    tri = rm.vertices.reshape(-1, 3, 3)
    face = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    face /= np.linalg.norm(face, axis=1, keepdims=True)
    assert np.allclose(rm.normals.reshape(-1, 3, 3), face[:, None, :], atol=1e-5)


def test_cylinder_wall_normals_point_radially():
    cyl = m3d.Manifold.cylinder(10.0, 5.0, circular_segments=48)
    rm = CadKernel.extract_render_mesh(cyl)
    p, n = rm.vertices, rm.normals
    wall = np.abs(n[:, 2]) < 0.5
    radial = p[wall, :2] / np.linalg.norm(p[wall, :2], axis=1, keepdims=True)
    assert np.allclose(n[wall, :2], radial, atol=1e-4) and np.allclose(n[wall, 2], 0.0, atol=1e-4)
    caps = np.abs(n[:, 2]) > 0.5
    assert np.allclose(np.abs(n[caps, 2]), 1.0, atol=1e-6)    # the rim stays a sharp edge


def test_flat_wall_touching_a_twisted_extrude_stays_flat():
    """A box wall that meets a twisted surface at a shallow angle must not borrow its tilted vertex normals."""
    box = m3d.Manifold.cube((50, 50, 25))
    sq = m3d.CrossSection.square((50, 50))
    twisted = m3d.Manifold.extrude(sq.translate((0, 0)), 42.5, 40, 90.0).translate((0, 0, 25))
    rm = CadKernel.extract_render_mesh(box + twisted)
    tri = rm.vertices.reshape(-1, 3, 3)
    face = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    face /= np.linalg.norm(face, axis=1, keepdims=True) + 1e-30
    wall = (tri[:, :, 2].max(axis=1) <= 25 + 1e-6) & (np.abs(face[:, 2]) < 1e-3)
    assert wall.any()
    assert np.allclose(rm.normals.reshape(-1, 3, 3)[wall], face[wall][:, None, :], atol=1e-4)


def test_hollow_sphere_star_cutouts_stay_smoothly_shaded(monkeypatch):
    """Report 20261124-181021: sharp-cornered star cutouts on a hollow sphere must not cause
    adjacent sphere facets to be flat-shaded by _flat_triangles."""
    from pathlib import Path
    from omacad import viewport_accel as accel
    from omacad.io.exporter import Exporter

    fixture = Path(__file__).parent / "data" / "hollow_sphere_stars_shading.omacad"
    doc = Exporter.load_project(str(fixture))
    body = doc.bodies["body_sphere_1"]
    m = body.manifold
    assert m.is_empty() is False and m.genus() == 40

    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties[:, :3], dtype=np.float64)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    flat_rust = CadKernel._flat_triangles(v, f)
    with monkeypatch.context() as ctx:
        ctx.setattr(accel, "_NATIVE", None)
        flat_py = CadKernel._flat_triangles(v, f)
    np.testing.assert_array_equal(flat_rust, flat_py)

    rm = CadKernel.extract_render_mesh(m)
    tri = rm.vertices.reshape(-1, 3, 3)
    nrm = rm.normals.reshape(-1, 3, 3)
    cent = tri.mean(axis=1)
    r = np.linalg.norm(cent, axis=1)
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    rad_c = cent / np.maximum(r[:, None], 1e-12)

    true_outer = (r > 24.5) & (np.sum(fn * rad_c, axis=1) > 0.8)
    true_inner = (r < 23.5) & (np.sum(fn * (-rad_c), axis=1) > 0.8)
    assert int(np.sum(flat_rust & true_outer)) < 10
    assert int(np.sum(flat_rust & true_inner)) < 10

    flat_shaded = np.all(np.linalg.norm(nrm - fn[:, None, :], axis=2) < 1e-4, axis=1)
    # Virtually all outer/inner sphere triangles must remain smooth-shaded (not flat-patched)
    assert int(np.sum(flat_shaded & true_outer)) < 50
    assert int(np.sum(flat_shaded & true_inner)) < 50
