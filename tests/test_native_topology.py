"""Native topology must preserve root IDs, flat-face flags and final render buffers."""
import numpy as np
import pytest
import trimesh
from omacad import viewport_accel as accel
from omacad.model.kernel import CadKernel
from omacad.model.faces_topology import _coplanar
from omacad.model.faces_surfaces import _face_groups


def reference_roots(v,f,normals,areas,adj,tolerance):
    parent=np.arange(len(f))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for a,b in adj:
        if _coplanar(a,b,normals,v,f,areas,tolerance):
            ra,rb=find(int(a)),find(int(b))
            if ra!=rb:parent[rb]=ra
    return np.array([find(i)for i in range(len(f))])


def test_group_roots_and_shading_match_reference_on_cad_shapes(monkeypatch):
    import manifold3d as m3d
    assert accel.backend_name()=='rust'
    shapes=[m3d.Manifold.cube((30,20,10)),m3d.Manifold.cylinder(20,10,circular_segments=96),m3d.Manifold.sphere(20,96),m3d.Manifold.cube((40,30,20))-m3d.Manifold.cylinder(40,5,circular_segments=96).translate((20,15,-10)),m3d.Manifold.cube((20,20,.001))]
    twisted=m3d.Manifold.extrude(m3d.CrossSection.square((20,20)),20,20,60).translate((0,0,10))
    shapes.append(m3d.Manifold.cube((20,20,10))+twisted)
    for shape in shapes:
        raw=shape.to_mesh();v=np.asarray(raw.vert_properties[:,:3]);f=np.asarray(raw.tri_verts)
        tm=trimesh.Trimesh(vertices=v,faces=f,process=False)
        tolerance=1e-6*max(1.,float(np.ptp(v,axis=0).max()))
        expected=reference_roots(v,f,tm.face_normals,tm.area_faces,tm.face_adjacency,tolerance)
        actual=accel.coplanar_roots(v,f,tm.face_normals,tm.area_faces,tm.face_adjacency,tolerance)
        np.testing.assert_array_equal(actual,expected)
        for vertices in [v.astype(np.float32),v.astype(np.float64)]:
            with monkeypatch.context() as ctx:
                ctx.setattr(accel,'_NATIVE',None)
                flat_reference=CadKernel._flat_triangles(vertices,f)
            np.testing.assert_array_equal(CadKernel._flat_triangles(vertices,f),flat_reference)
        with monkeypatch.context() as ctx:
            ctx.setattr(accel,'_NATIVE',None)
            reference=CadKernel.extract_render_mesh(shape)
            groups_reference=_face_groups(v,f,tm)
        native=CadKernel.extract_render_mesh(shape)
        for key in ['vertices','normals','sharp_lines']:
            np.testing.assert_array_equal(getattr(native,key),getattr(reference,key))
        groups_native=_face_groups(v,f,tm)
        np.testing.assert_array_equal(groups_native[0],groups_reference[0])
        assert groups_native[1:]==groups_reference[1:]


def test_coplanar_noise_slivers_and_tolerance_thresholds_match_reference():
    rng=np.random.default_rng(720)
    for scale in [1e-3,1.,1e3]:
        count=240
        tris=rng.uniform(-1,1,(count,3,3))*scale
        tris[:80,:,2]=rng.choice([0.,1e-8,1e-6,1e-4],(80,1))*scale
        v=tris.reshape(-1,3);f=np.arange(len(v)).reshape(-1,3)
        tm=trimesh.Trimesh(vertices=v,faces=f,process=False)
        adj=np.array([[i,i+1]for i in range(count-1)],dtype=np.int64)
        for tolerance in [1e-9,1e-6,1e-3]:
            np.testing.assert_array_equal(accel.coplanar_roots(v,f,tm.face_normals,tm.area_faces,adj,tolerance),reference_roots(v,f,tm.face_normals,tm.area_faces,adj,tolerance))


def test_invalid_topology_inputs_are_exceptions():
    import _viewport_native as native
    with pytest.raises(ValueError):native.flat_patch_mask(1,b'bad',b'',b'',False)
    with pytest.raises(ValueError):native.flat_patch_mask(1,b'',np.array([[0,3]],dtype='<u8').tobytes(),np.zeros((1,3),dtype='<f8').tobytes(),False)
    with pytest.raises(ValueError):native.coplanar_roots(b'',b'',b'',b'',float('nan'))
    assert native.flat_patch_mask(0,b'',b'',b'',False)==b''


def test_native_snap_and_clean_segments_parity():
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.000000001, 0.0, 0.0],
        [2.0, 0.0, 0.0]
    ], dtype=np.float64)
    segs = [[0, 1], [1, 2], [2, 3]]
    cleaned = accel.snap_and_clean_segments(vertices, segs, 1e-5)
    assert cleaned is not None
    assert len(cleaned) == 2
    assert cleaned[0][0] == 0 and cleaned[0][1] == 0 and cleaned[0][2] == 1
    assert cleaned[1][0] == 2 and cleaned[1][1] == 1 and cleaned[1][2] == 3

