"""Picking a face for Hole looks straight at that face and zooms it to fill the view, as sketching on a face does."""
from types import SimpleNamespace

import numpy as np

from omacad.ui.viewport.overlay_mixin import OverlayMixin


class _View(SimpleNamespace):
    """Records the camera calls instead of drawing (no GL context needed)."""

    def __init__(self):
        super().__init__(calls=[])

    def align_to_plane(self, plane):
        self.calls.append(("align", plane))

    def frame_face(self, plane, tris, fill=0.8):
        self.calls.append(("frame", plane, tris))


def _face_plane():
    tris = np.array([[[0, 0, 25], [10, 0, 25], [0, 10, 25]]], dtype=float)
    face = SimpleNamespace(tris=tris)
    plane = SimpleNamespace(normal=np.array([0.0, 0.0, 1.0]), face=face)
    return plane, tris


def test_picked_body_face_is_aligned_and_framed():
    view = _View()
    plane, tris = _face_plane()
    OverlayMixin.frame_picked_plane(view, plane)
    assert view.calls[0] == ("align", plane)
    assert view.calls[1][0] == "frame"
    assert np.array_equal(view.calls[1][2], tris)


def test_picked_origin_plane_is_only_aligned():
    view = _View()
    plane = SimpleNamespace(normal=np.array([0.0, 0.0, 1.0]), face=None)
    OverlayMixin.frame_picked_plane(view, plane)
    assert view.calls == [("align", plane)]
