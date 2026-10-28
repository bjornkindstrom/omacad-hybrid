"""The native boundary must preserve Omacad's hit distances, face order and triangle IDs."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import pytest

from omacad import viewport_accel as accel
from omacad.model import faces_hit_tests as picking


def reference_faces(faces, origin, direction, tolerance=1e-9):
    out = np.full(len(faces), np.inf)
    for i, face in enumerate(faces):
        hits = picking._ray_triangles(np.asarray(face.tris).reshape(-1, 3, 3), origin, direction, tolerance)
        if len(hits):
            out[i] = hits.min()
    return out


def reference_mesh(mesh, origin, direction):
    hits = picking._ray_triangles(np.asarray(mesh.vertices, dtype=np.float64).reshape(-1, 3, 3), origin, direction)
    if not len(hits) or not np.isfinite(hits.min()):
        return None
    index = int(hits.argmin())
    return float(hits[index]), index


@pytest.fixture
def native():
    import _viewport_native
    assert accel.backend_name() == "rust", "Run with OMACAD_VIEWPORT_BACKEND=rust"
    picking._FACE_STACKS.clear()
    return _viewport_native


def test_random_rays_and_every_face_match_numpy(native):
    rng = np.random.default_rng(3014)
    triangles = rng.normal(size=(1200, 3, 3)) * 40.0
    # Empty faces, degenerate triangles and non-contiguous face arrays are intentional.
    triangles[4] = 0
    faces = [SimpleNamespace(tris=triangles[i::19]) for i in range(19)]
    faces.append(SimpleNamespace(tris=np.empty((0, 3, 3))))
    mesh = SimpleNamespace(vertices=triangles.reshape(-1, 3).astype(np.float32))
    rays = [(rng.normal(size=3) * 100.0, rng.normal(size=3)) for _ in range(80)]
    rays += [(np.array([0., 0., 100.]), np.array([0., 0., -1.])), (np.zeros(3), np.zeros(3))]
    for origin, direction in rays:
        for tolerance in [0.0, 1e-9, 1e-3, -1e-3]:
            np.testing.assert_allclose(picking.ray_hit_faces(faces, origin, direction, tolerance), reference_faces(faces, origin, direction, tolerance), rtol=1e-10, atol=1e-8)
        expected = reference_mesh(mesh, origin, direction)
        actual = picking.ray_mesh_hit(mesh, origin, direction)
        if expected is None:
            assert actual is None
        else:
            assert actual[1] == expected[1]
            assert actual[0] == pytest.approx(expected[0], rel=1e-10, abs=1e-8)


def test_cad_meshes_holes_curves_and_moved_geometry_match(native):
    from omacad.model.kernel import CadKernel
    from omacad.model.faces import compute_planar_faces_and_edges
    box = CadKernel.create_box(40, 30, 20)
    cylinder = CadKernel.create_cylinder(5, 40).translate((20, 15, -10))
    shapes = [box, box - cylinder, CadKernel.create_sphere(15, 48), (box-cylinder).translate((500, -70, 8))]
    rng = np.random.default_rng(5)
    for i, shape in enumerate(shapes):
        mesh = CadKernel.extract_render_mesh(shape)
        faces, _ = compute_planar_faces_and_edges(shape, str(i))
        for _ in range(20):
            origin = mesh.center + rng.normal(size=3)*100
            direction = mesh.center-origin
            direction /= np.linalg.norm(direction)
            np.testing.assert_allclose(picking.ray_hit_faces(faces, origin, direction), reference_faces(faces, origin, direction), rtol=1e-10, atol=1e-8)
            expected = reference_mesh(mesh, origin, direction)
            actual = picking.ray_mesh_hit(mesh, origin, direction)
            if expected is None:  # A ray through the drilled centre can miss the entire body.
                assert actual is None
            else:
                assert actual is not None
                assert actual[0] == pytest.approx(expected[0], abs=1e-8)
                assert actual[1] == expected[1]


def test_boundary_tolerance_inside_origins_ties_and_face_order(native):
    triangle = np.array([[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]])
    faces = [SimpleNamespace(tris=triangle.copy()) for _ in range(50)]
    faces[17] = SimpleNamespace(tris=np.empty((0,3,3)))
    for origin in [[0.,0.,1.],[-5e-5,.2,1.],[.5,.5,1.],[.2,.2,0.],[.2,.2,-1.]]:
        for direction in [[0.,0.,-1.],[0.,0.,1.],[1.,0.,0.]]:
            np.testing.assert_allclose(picking.ray_hit_faces(faces, origin, direction, 1e-4), reference_faces(faces, origin, direction, 1e-4))
    mesh = SimpleNamespace(vertices=np.concatenate([triangle]*40).reshape(-1,3))
    assert picking.ray_mesh_hit(mesh,[.2,.2,1.],[0.,0.,-1.]) == (1.,0)


def test_replaced_vertex_array_and_face_list_build_new_indices(native):
    triangle = np.array([[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]])
    mesh = SimpleNamespace(vertices=triangle.reshape(-1,3).copy())
    assert picking.ray_mesh_hit(mesh,[.2,.2,5.],[0.,0.,-1.])[0] == 5
    old = mesh._native_pick_index[1]
    mesh.vertices = mesh.vertices + np.array([0,0,2])
    assert picking.ray_mesh_hit(mesh,[.2,.2,5.],[0.,0.,-1.])[0] == 3
    assert mesh._native_pick_index[1] is not old
    faces = [SimpleNamespace(tris=triangle)]
    assert picking.ray_hit_faces(faces,[.2,.2,5.],[0.,0.,-1.])[0] == 5
    faces = [SimpleNamespace(tris=triangle+np.array([0,0,2]))]
    assert picking.ray_hit_faces(faces,[.2,.2,5.],[0.,0.,-1.])[0] == 3


def test_native_owns_snapshot_and_can_be_queried_from_threads(native):
    tri = np.array([[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]])
    index = accel.build_index(tri,[0],1)
    tri[:] = 99
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: index.nearest([.2,.2,5.],[0.,0.,-1.]), range(80)))
    assert results == [(5.,0)]*80


def test_invalid_native_buffers_are_python_errors(native):
    with pytest.raises(ValueError):
        native.TriangleIndex(b"bad",b"",1)
    tri = np.zeros((1,3,3),dtype="<f8")
    with pytest.raises(ValueError):
        native.TriangleIndex(tri.tobytes(),np.array([2],dtype="<u4").tobytes(),1)
    tri[0,0,0] = np.nan
    with pytest.raises(ValueError):
        accel.build_index(tri,[0],1)
    index = accel.build_index(np.zeros((0,3,3)),[],0)
    assert index.nearest([0,0,0],[0,0,1]) is None
    assert accel.face_hits(index,[0,0,0],[0,0,1],1e-9).shape == (0,)
    with pytest.raises(ValueError):
        index.nearest([np.nan,0,0],[0,0,1])


def test_existing_qt_viewport_uses_rust_for_picking_after_move(native):
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1400,900)
    window.viewport.resize(900,700)
    body = window.doc.add_box(40,30,20)
    center = window.viewport.world_to_screen(np.array([20.,15.,20.]))
    assert window.viewport.pick_body(*center) == body.body_id
    assert getattr(body.render_mesh,"_native_pick_index",None) is not None
    assert any(entry[3] is not None for entry in picking._FACE_STACKS.values())
    window.doc.move_body(body.body_id,dx=100)
    assert window.viewport.pick_body(*center) is None
    window.close()


def test_python_fallback_and_forced_native_failures_are_explicit():
    import subprocess
    import sys
    script = '''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname == "_viewport_native":
            raise ModuleNotFoundError("simulated missing Rust extension", name=fullname)
sys.meta_path.insert(0, Block())
from omacad import viewport_accel
print(viewport_accel.backend_name())
'''
    for mode in ["python", "auto", "rust"]:
        result = subprocess.run([sys.executable,"-c",script],env={**os.environ,"OMACAD_VIEWPORT_BACKEND":mode},text=True,capture_output=True)
        if mode == "rust":
            assert result.returncode != 0
            assert "Rust picking requested but unavailable" in result.stderr
        else:
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == "python"
            if mode == "auto":
                assert "using Python" in result.stderr
