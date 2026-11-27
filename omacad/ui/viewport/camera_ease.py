"""Smooth camera moves for view presets, Fit and Find: the camera state changes at once (code and tests read the
final values), only the drawn camera eases from where it was over a short time. Any other camera change (orbit,
pan, zoom with the mouse) ends the move on the spot."""
from __future__ import annotations

import math
import time
from typing import Optional, Tuple

import numpy as np

DURATION = 0.28         # seconds


def _wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def _ease(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3     # ease-out cubic: quick start, soft landing


def state(view) -> tuple:
    return (np.array(view.target, dtype=np.float64), float(view.distance), float(view.azimuth), float(view.elevation))


class CameraEase:
    def __init__(self):
        self._from: Optional[tuple] = None
        self._to: Optional[tuple] = None
        self._start = 0.0

    def start(self, view, before: tuple) -> None:
        """Eases from `before` (a `state`) to the view's current camera, unless the move is too small to notice
        or animation is off in Settings."""
        after = state(view)
        if not enabled() or not view.isVisible():
            self._from = None
            return
        moved = (np.linalg.norm(after[0] - before[0]) > 1e-6 or abs(after[1] - before[1]) > 1e-6
                 or abs(_wrap(after[2] - before[2])) > 1e-3 or abs(_wrap(after[3] - before[3])) > 1e-3)
        if not moved:
            return
        current = self.current(view)       # a move that starts mid-way continues from what is on screen
        self._from = current if current is not None else before
        self._to = after
        self._start = time.perf_counter()

    def current(self, view) -> Optional[Tuple[np.ndarray, float, float, float]]:
        """The camera to draw now, or None when no move runs (draw the view's own camera)."""
        if self._from is None:
            return None
        now = state(view)
        to = self._to
        if (np.linalg.norm(now[0] - to[0]) > 1e-9 or now[1] != to[1] or now[2] != to[2] or now[3] != to[3]):
            self._from = None           # the user moved the camera: theirs wins
            return None
        t = (time.perf_counter() - self._start) / DURATION
        if t >= 1.0:
            self._from = None
            return None
        k = _ease(max(0.0, t))
        f = self._from
        target = f[0] + (to[0] - f[0]) * k
        # distance eases in log space, so zooming far in or out feels even
        distance = math.exp(math.log(max(f[1], 1e-9)) + (math.log(max(to[1], 1e-9)) - math.log(max(f[1], 1e-9))) * k)
        azimuth = f[2] + _wrap(to[2] - f[2]) * k
        elevation = f[3] + _wrap(to[3] - f[3]) * k
        return target.astype(np.float32), distance, azimuth, elevation

    @property
    def active(self) -> bool:
        return self._from is not None


def enabled() -> bool:
    try:
        from omacad.ui.settings import get_settings
        return bool(get_settings().get("camera_animation", True))
    except Exception:
        return True
