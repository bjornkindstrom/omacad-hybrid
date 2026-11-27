"""Slow kernel results (Shell's Minkowski erosion) are kept in memory and on disk, keyed by the input mesh."""
import manifold3d as m3d
import numpy as np

from omacad.model import solid_cache
from omacad.model.features.shell import ShellFeature


def _body():
    return m3d.Manifold.cube((10, 10, 10)) - m3d.Manifold.cylinder(20, 3, 3, 32).translate((5, 5, -5))


def test_same_input_is_computed_once_then_read_from_memory_and_disk(monkeypatch):
    monkeypatch.setattr(solid_cache, "MIN_SECONDS", 0.0)
    calls = []

    def compute():
        calls.append(1)
        return _body().minkowski_difference(m3d.Manifold.sphere(1, 12))
    first = solid_cache.cached("op", _body(), (1.0,), compute)
    again = solid_cache.cached("op", _body(), (1.0,), compute)
    solid_cache.clear_memory()
    from_disk = solid_cache.cached("op", _body(), (1.0,), compute)
    assert len(calls) == 1
    for solid in (again, from_disk):
        assert np.isclose(solid.volume(), first.volume()) and solid.genus() == first.genus()
        assert np.array_equal(solid.to_mesh64().vert_properties, first.to_mesh64().vert_properties)
    solid_cache.cached("op", _body(), (2.0,), compute)              # other numbers: computed
    assert len(calls) == 2


def test_a_damaged_file_is_dropped_and_rebuilt(monkeypatch):
    monkeypatch.setattr(solid_cache, "MIN_SECONDS", 0.0)
    solid_cache.cached("op", _body(), (1.0,), lambda: _body().translate((1, 0, 0)))
    solid_cache.clear_memory()
    (path,) = solid_cache.disk_dir().glob("*.npz")
    path.write_bytes(b"broken")
    solid = solid_cache.cached("op", _body(), (1.0,), lambda: _body().translate((2, 0, 0)))
    assert np.isclose(solid.bounding_box()[0], 2.0)


def test_shell_of_a_non_convex_body_uses_the_cache(monkeypatch):
    monkeypatch.setattr(solid_cache, "MIN_SECONDS", 0.0)
    a = ShellFeature._shrink(_body(), 1.0)
    solid_cache.clear_memory()
    monkeypatch.setattr(m3d.Manifold, "minkowski_difference", lambda *a: (_ for _ in ()).throw(AssertionError("recomputed")))
    b = ShellFeature._shrink(_body(), 1.0)
    assert np.isclose(a.volume(), b.volume())
