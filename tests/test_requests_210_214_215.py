"""Requests #214/#215 (graphics bugs on a jar with lid and a Japandi box) and the stray-line filter; #210's
"Planes" branch is tested in test_browser_tree.py."""
from pathlib import Path

import numpy as np
import trimesh

from omacad.io.exporter import Exporter
from omacad.model import faces_surfaces as fs
from omacad.model.display_smooth import smooth_arrays
from omacad.model.kernel import stray_line_mask
from omacad.ui.viewport.picker_mixin import patch_boundary_segments

DATA = Path(__file__).parent / "data"
JAR = str(DATA / "jar_lid_streaks_214.omacad")
BOX = str(DATA / "japandi_box_rib_select_215.omacad")


def _tri_mesh(body):
    v, f, _ = body.render_mesh.source
    return v, f, trimesh.Trimesh(v, f, process=False)


def test_fast_view_smoothing_keeps_the_jar_wall_round():
    """#214: needles of the shell/thread seams pushed smoothed points up to 0.9 mm out of the Ø40 wall (streaks)."""
    doc = Exporter.load_project(JAR)
    rm = doc.bodies["body_cylinder_1"].render_mesh
    verts, normals, _ = smooth_arrays(rm.vertices, rm.normals, rm.sharp_lines)
    radius = np.linalg.norm(np.asarray(verts, float)[:, :2], axis=1)
    assert radius.max() < 20.0 + 1e-3
    # and a plain cylinder is still drawn round: the midpoints of its chords land on the circle
    import manifold3d as m3d
    from omacad.model.kernel import CadKernel
    cyl = CadKernel.extract_render_mesh(m3d.Manifold.cylinder(10, 5, circular_segments=24))
    v2, _, _ = smooth_arrays(cyl.vertices, cyl.normals, cyl.sharp_lines)
    v2 = np.asarray(v2, float)
    wall = (v2[:, 2] > 0.01) & (v2[:, 2] < 9.99)
    r2 = np.linalg.norm(v2[wall, :2], axis=1)
    assert np.allclose(r2, 5.0, atol=2e-3)


def test_no_tangent_lines_down_the_facets_of_the_jar_cone():
    """#214: a boolean left single cone facets as "flat faces", and tangent lines were drawn down their sides."""
    doc = Exporter.load_project(JAR)
    for bid in ("body_cylinder_1", "body_cylinder_7"):
        seg = doc.bodies[bid].render_mesh.tangent_lines().reshape(-1, 2, 3)
        cone = (seg[:, :, 2].min(1) < 5.99) & (seg[:, :, 2].max(1) > 2.01) & (np.abs(seg[:, 0, 2] - seg[:, 1, 2]) > 0.05)
        assert not cone.any() if bid == "body_cylinder_1" else True
    assert len(doc.bodies["body_cylinder_1"].render_mesh.tangent_lines()) == 0


def test_a_bent_japandi_rib_is_one_surface_without_holes():
    """#215: the rib face was dotted with two-triangle "surfaces", drawn as zigzag holes when selected."""
    doc = Exporter.load_project(BOX)
    body = next(iter(doc.bodies.values()))
    v, f, tm = _tri_mesh(body)
    ids = fs.curved_surface_ids(v, f, tm, 20.0)
    centroids = v[f].mean(1)
    rib = ids[int(np.argmin(np.linalg.norm(centroids - [70.0, 24.0, 12.0], axis=1)))]
    assert rib >= 0
    seg = patch_boundary_segments(v[f][ids == rib])
    q = {}
    for s in np.round(seg * 1000).astype(np.int64):
        a, b = tuple(s[0]), tuple(s[1])
        q.setdefault(a, []).append(b)
        q.setdefault(b, []).append(a)
    seen, loops = set(), 0
    for start in q:
        if start in seen:
            continue
        loops += 1
        stack = [start]
        while stack:
            x = stack.pop()
            if x not in seen:
                seen.add(x)
                stack += q[x]
    assert loops == 1
    # no small curved crumb runs smoothly into a much bigger surface any more
    labels, counts = np.unique(ids[ids >= 0], return_counts=True)
    crumbs = set(labels[counts <= fs.CRUMB_TRIANGLES].tolist())
    fa = tm.face_adjacency
    smooth = tm.face_adjacency_angles <= np.radians(20)
    la, lb = ids[fa[:, 0]], ids[fa[:, 1]]
    big = {int(l) for l, c in zip(labels, counts) if c > 50}
    touching = {int(x) for x, y in zip(la[smooth], lb[smooth]) if x in crumbs and y in big}
    assert len(touching) < 0.05 * len(crumbs) + 15


def test_stray_bits_of_edge_lines_are_not_drawn():
    long_run = [[[0, 0, 0], [50, 0, 0]], [[50, 0, 0], [50, 50, 0]]]
    dash = [[[10, 10, 5], [10.5, 10, 5]]]
    ring = [[[np.cos(a) * 2, np.sin(a) * 2, 0], [np.cos(b) * 2, np.sin(b) * 2, 0]]
            for a, b in zip(np.linspace(0, 2 * np.pi, 25)[:-1], np.linspace(0, 2 * np.pi, 25)[1:])]
    seg = np.array(long_run + dash + ring, dtype=float)
    mask = stray_line_mask(seg, 100.0)
    assert list(mask[:2]) == [False, False] and mask[2] and not mask[3:].any()
    doc = Exporter.load_project(BOX)
    rm = next(iter(doc.bodies.values())).render_mesh
    drawn, every = len(rm.drawn_edges(True)), len(rm.sharp_lines) + len(rm.tangent_lines())
    assert 0.9 * every < drawn < every
