"""P3: native union-find labels equal the Python loop's exactly, and the contours found with them too."""
import math

import numpy as np
import pytest

from omacad import viewport_accel


def _python_labels(n, pairs):
    parents = list(range(n))

    def root(a):
        while parents[a] != a:
            parents[a] = parents[parents[a]]
            a = parents[a]
        return a
    for a, b in pairs:
        parents[root(a)] = root(b)
    return np.array([root(i) for i in range(n)], dtype=np.int64)


@pytest.mark.skipif(getattr(viewport_accel._NATIVE, "union_labels", None) is None, reason="native module not built")
def test_labels_match_the_python_union_find():
    rng = np.random.default_rng(3)
    for n, m in ((1, 0), (2, 1), (50, 30), (5000, 9000), (20000, 15000)):
        pairs = rng.integers(0, n, (m, 2))
        got = viewport_accel.union_labels(n, pairs)
        assert np.array_equal(got, _python_labels(n, pairs.tolist()))


def test_cylindrical_contours_are_the_same_on_both_paths(monkeypatch):
    import manifold3d as m3d
    import trimesh
    from omacad.model.wrapped_edges import cylindrical_contours
    body = m3d.Manifold.cylinder(20.0, 10.0, circular_segments=96) - \
        m3d.Manifold.cube((4.0, 30.0, 4.0), True).translate((0.0, 0.0, 10.0))
    mesh = body.to_mesh64()
    v = np.asarray(mesh.vert_properties[:, :3], dtype=float)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    native = cylindrical_contours(v, f, trimesh.Trimesh(vertices=v, faces=f, process=False))
    monkeypatch.setattr(viewport_accel, "_NATIVE", None)
    python = cylindrical_contours(v, f, trimesh.Trimesh(vertices=v, faces=f, process=False))
    assert repr(native) == repr(python)


def _propagated(n, join):
    label = np.arange(n)
    while len(join):
        low = np.minimum(label[join[:, 0]], label[join[:, 1]])
        new = label.copy()
        np.minimum.at(new, join[:, 0], low)
        np.minimum.at(new, join[:, 1], low)
        new = new[new]
        if np.array_equal(new, label):
            break
        label = new
    return label


@pytest.mark.skipif(getattr(viewport_accel._NATIVE, "min_labels", None) is None, reason="native module not built")
def test_min_labels_are_the_propagations_fixed_point():
    rng = np.random.default_rng(5)
    chain = np.c_[np.arange(2999), np.arange(1, 3000)][rng.permutation(2999)]        # one long chain, shuffled
    for n, join in ((1, np.zeros((0, 2), np.int64)), (3000, chain), (4000, rng.integers(0, 4000, (2500, 2))),
                    (10000, rng.integers(0, 10000, (12000, 2)))):
        got = viewport_accel.min_labels(n, join) if len(join) else np.arange(n)
        assert np.array_equal(got, _propagated(n, join))


def test_patches_are_the_same_on_both_paths(monkeypatch):
    import manifold3d as m3d
    from omacad.model.kernel import CadKernel
    body = m3d.Manifold.cylinder(20.0, 10.0, circular_segments=128) + m3d.Manifold.cube((30.0, 4.0, 30.0), True)
    mesh = body.to_mesh64()
    v = np.asarray(mesh.vert_properties[:, :3], dtype=float)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    native = CadKernel._patches(v, f)
    monkeypatch.setattr(viewport_accel, "_NATIVE", None)
    python = CadKernel._patches(v, f)
    for key in ("inv", "planar", "width", "pa", "pb", "normal"):
        assert np.array_equal(native[key], python[key]), key
    assert native["k"] == python["k"]


def test_vertex_weld_is_the_same_on_both_paths(monkeypatch):
    from omacad.model.kernel import CadKernel
    rng = np.random.default_rng(9)
    v = np.repeat(rng.uniform(0, 50, (400, 3)), 3, axis=0) + rng.normal(0, 1e-5, (1200, 3))
    native = CadKernel._weld(v, 1e-3)
    monkeypatch.setattr(viewport_accel, "_NATIVE", None)
    assert np.array_equal(native, CadKernel._weld(v, 1e-3))
