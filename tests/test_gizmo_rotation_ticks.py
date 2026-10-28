"""Move gizmo: muted until hovered, smaller, and rotation snaps to ticks only outside the ring."""
import numpy as np
from omacad.ui.viewport import gizmo_mixin
from omacad.ui.viewport.gizmo_mixin import GizmoMixin


class _Stub(GizmoMixin):
    def __init__(self):
        self.move_gizmo = {"origin": np.zeros(3), "length": 20.0}

    def get_matrices(self):
        return None, None, None

    def width(self):
        return 100

    def height(self):
        return 100


def test_colours_muted_until_lit():
    base = (0.95, 0.25, 0.25)
    dim, lit = GizmoMixin._gizmo_color(base, False, 0.3), GizmoMixin._gizmo_color(base, True, 0.3)
    assert dim[3] < 1.0 and lit[3] == 1.0 and dim[0] < lit[0]


def test_snap_only_outside_ring(monkeypatch):
    # the "mouse ray" looks down -z and hits the RZ plane (z=0) at (x, y) in mm
    monkeypatch.setattr(gizmo_mixin, "ray_from_screen", lambda x, y, *a: ((x, y, 10.0), (0.0, 0.0, -1.0)))
    vp = _Stub()
    ring = 20.0 * 0.72
    assert vp.gizmo_snapped_delta(ring * 0.9, 0, "RZ", 7.3) == 7.3          # inside: free
    assert vp.gizmo_snapped_delta(ring * 1.5, 0, "RZ", 7.3) == 0.0          # outside: nearest 15 deg tick
    assert vp.gizmo_snapped_delta(ring * 1.5, 0, "RZ", 8.0) == 15.0
    assert vp.gizmo_snapped_delta(ring * 1.5, 0, "X", 7.3) == 7.3           # translation untouched
