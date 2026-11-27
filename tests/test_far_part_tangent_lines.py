"""Rapport 20261127-161058: a scalloped cup placed ~540 mm from the origin (a script's print layout) showed tangent
lines down single facets of its round wall. The render mesh analysed the float32 mesh, and float32 noise out there
tipped the thin wall facets off their plane, so a facet became a "flat face" with a tangent edge on each side.
Scripted bodies were also stored and rebuilt in float32 (ImportMeshFeature)."""
import math

import manifold3d as m3d
import numpy as np

from omacad.model.document import Document
from omacad.model.kernel import CadKernel


def _crown_cutter(count=10, per=24, r_in=41.0, r_out=47.0, height=15.0):
    """Ring whose top edge has `count` round lobes: cut from the bottom of a cup it leaves a scalloped skirt."""
    m = count * per
    verts, tris = [], []
    for i in range(m):
        th = 2 * math.pi * i / m
        c, s = math.cos(th), math.sin(th)
        t = 2.0 * ((i % per) / per) - 1.0
        zt = -0.02 + height * (1.0 - math.sqrt(max(0.0, 1.0 - t * t)))
        verts += [(r_in * c, r_in * s, -1.0), (r_out * c, r_out * s, -1.0), (r_out * c, r_out * s, zt), (r_in * c, r_in * s, zt)]
        a, b = 4 * i, 4 * ((i + 1) % m)
        for j in range(4):
            q = (j + 1) % 4
            tris += [(a + j, b + q, b + j), (a + j, a + q, b + q)]
    make = lambda t: m3d.Manifold(m3d.Mesh64(vert_properties=np.array(verts, float), tri_verts=np.array(t, np.uint64)))
    out = make(tris)
    return out if out.volume() > 0 else make([x[::-1] for x in tris])


def _scalloped_cup(x: float) -> m3d.Manifold:
    cup = (m3d.Manifold.cylinder(50, 45.5, 45.5, circular_segments=96)
           - m3d.Manifold.cylinder(60, 43, 43, circular_segments=96).translate((0, 0, -5)))
    return (cup - _crown_cutter()).rotate((180, 0, 0)).translate((x, 0, 50))


def _long_lines(lines: np.ndarray, length: float = 10.0) -> int:
    seg = np.asarray(lines, dtype=float).reshape(-1, 2, 3)
    return int((np.linalg.norm(seg[:, 1] - seg[:, 0], axis=1) > length).sum())


def test_round_wall_far_from_the_origin_gets_no_tangent_lines_down_its_facets():
    for x in (0.0, 538.0, 1000.0):
        mesh = CadKernel.extract_render_mesh(_scalloped_cup(x))
        assert _long_lines(mesh.tangent_lines()) == 0, x
        assert _long_lines(mesh.sharp_lines) == 0, x


def test_imported_mesh_keeps_double_precision():
    shape = _scalloped_cup(538.0)
    mesh = shape.to_mesh64()
    doc = Document()
    feat = doc.import_mesh("cup", mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist(), source_file="script")
    body = doc.bodies[feat.created_body_id]
    got = np.asarray(body.manifold.to_mesh64().vert_properties[:, :3])
    assert np.abs(np.sort(got, axis=0) - np.sort(np.asarray(mesh.vert_properties[:, :3]), axis=0)).max() < 1e-9
    assert _long_lines(body.render_mesh.tangent_lines()) == 0
