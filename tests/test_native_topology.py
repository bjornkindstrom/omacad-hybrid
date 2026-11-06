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



def _patterned_bodies(tmp_path):
    """The shapes the native grouping is for: thousands of patches, slivers and strips from a pattern on a shell."""
    from omacad.model.document import Document
    from omacad.model.features.honeycomb import HoneycombFeature
    svg=tmp_path/"ring.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><ellipse cx="0" cy="0" rx="20" ry="12"/><ellipse cx="0" cy="0" rx="14" ry="8"/></svg>')
    doc=Document();body=doc.add_cylinder(25.,40.)
    doc.add_shell(body.body_id,2.,open_faces=[{"normal":[0,0,1],"origin":[0,0,40]}])
    shell=doc.bodies[body.body_id].manifold
    face={"kind":"cylinder","origin":[0,0,0],"axis":[0,0,1],"radius":25.,"length":40.,"internal":False}
    base=dict(shape="svg",svg_path=str(svg),size=10.,wall=2.,margin=3.,depth=1.,through=True,angle=0.,partial=False,randomness=100.,seed=1,
              style="even",fine_size=2.,inner_wall=.8,hotspots=1,rounding=0.,opening=100.,opening_end=100.,relaxation=0,hole="cell")
    for changes in ({},dict(through=False,random_rotation=180.),dict(shape="voronoi",size=6.),dict(shape="hexagon",size=5.)):
        yield HoneycombFeature.compute(shell,[face],{**base,**changes})[0]


def test_native_classes_and_the_whole_analysis_match_python_on_patterned_bodies(tmp_path,monkeypatch):
    from omacad.model import faces_surfaces
    assert accel.backend_name()=='rust'
    native=accel.classify_face_groups
    for solid in _patterned_bodies(tmp_path):
        mesh=solid.to_mesh64();v=np.asarray(mesh.vert_properties[:,:3],dtype=np.float64);f=np.asarray(mesh.tri_verts,dtype=np.int64)
        tm=trimesh.Trimesh(vertices=v,faces=f,process=False)
        faces_surfaces._TOPOLOGY_CACHE.clear()
        actual=_face_groups(v,f,tm)
        faces,edges=faces_surfaces.compute_planar_faces_and_edges(solid,"b")
        with monkeypatch.context() as ctx:
            ctx.setattr(accel,'classify_face_groups',lambda *args,**kwargs:None)
            faces_surfaces._TOPOLOGY_CACHE.clear()
            expected=_face_groups(v,f,tm)
            faces_expected,edges_expected=faces_surfaces.compute_planar_faces_and_edges(solid,"b")
        np.testing.assert_array_equal(actual[0],expected[0])
        assert list(actual[1].items())==list(expected[1].items())       # the same groups in the same order
        assert actual[2:]==expected[2:] and actual[4]                   # planar, slivers, curved; and there are curves
        assert [(x.index,x.area) for x in faces]==[(x.index,x.area) for x in faces_expected]
        assert [str(x.ref()) for x in edges]==[str(x.ref()) for x in edges_expected]
        faces_surfaces._TOPOLOGY_CACHE.clear()
    assert accel.classify_face_groups is native


def test_native_classes_look_through_a_chain_of_slivers_like_python():
    """Two strips of a curve whose only link is a chain of slivers, and a thin flat group: the awkward rules, on their own."""
    from omacad.model.faces_topology import _curved_roots,_sliver_roots
    # a fan of quads round a cylinder, with hair-thin quads between every second pair
    v,f=[],[]
    angle=0.
    for i in range(24):
        step=.002 if i%3==2 else .3
        a,b=angle,angle+step
        angle=b
        base=len(v)
        v+=[[20*np.cos(a),20*np.sin(a),0],[20*np.cos(b),20*np.sin(b),0],[20*np.cos(b),20*np.sin(b),30],[20*np.cos(a),20*np.sin(a),30]]
        f+=[[base,base+1,base+2],[base,base+2,base+3]]
    v=np.array(v,dtype=np.float64);f=np.array(f,dtype=np.int64)
    # weld the shared corners, so the strips are neighbours
    unique,inverse=np.unique(np.round(v,9),axis=0,return_inverse=True)
    v,f=unique,inverse.reshape(-1)[f]
    tm=trimesh.Trimesh(vertices=v,faces=f,process=False)
    tolerance=1e-6*max(1.,float(np.ptp(v,axis=0).max()))
    roots=accel.coplanar_roots(v,f,tm.face_normals,tm.area_faces,tm.face_adjacency,tolerance)
    groups={}
    for i,r in enumerate(roots.tolist()):groups.setdefault(r,[]).append(i)
    find=lambda i:int(roots[i])
    slivers=_sliver_roots(v,f,tm,groups)
    curved=_curved_roots(v,f,tm,find,groups,tm.face_adjacency,tm.face_adjacency_angles,slivers)
    assert slivers and curved
    native=accel.classify_face_groups(v,f,tm.face_normals,tm.area_faces,roots,tm.face_adjacency,tm.face_adjacency_angles,.03,.04,np.radians(25.))
    assert native==(slivers,curved)


def test_groups_of_roots_is_the_dict_a_loop_builds():
    from omacad.model.faces_topology import _groups_of_roots
    roots=np.array([5,5,0,7,0,5,7,9,0,9],dtype=np.int64)
    loop={}
    for i,r in enumerate(roots.tolist()):loop.setdefault(r,[]).append(i)
    assert list(_groups_of_roots(roots).items())==list(loop.items())
