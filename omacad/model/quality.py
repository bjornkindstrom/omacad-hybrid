"""How finely round shapes are cut into flat pieces (the 'Curve smoothness' setting). The model has no
Qt, so the settings manager pushes the value in here."""
import math
from contextlib import contextmanager

DEFAULT_SEGMENTS = 96
DEFAULT_VIEW_SEGMENTS = 72
_segments = DEFAULT_SEGMENTS
_interactive_mode: bool = False
# "Fast view, exact export": the model in the view is built with fewer pieces (faster booleans and face analysis) and
# drawn smoothed (kernel.RenderMesh.display_arrays); exports rebuild it with `_segments` inside `exact()`.
_fast_view: bool = False
_view_segments = DEFAULT_VIEW_SEGMENTS
_exact_depth = 0


def set_fast_view(enabled: bool, view_segments: int = None) -> None:
    global _fast_view, _view_segments
    _fast_view = bool(enabled)
    if view_segments is not None:
        _view_segments = max(16, min(720, int(view_segments)))


def fast_view_enabled() -> bool:
    """The setting is on (the view is drawn smoothed), whether or not the model is actually built coarser."""
    return _fast_view and _exact_depth == 0


def fast_view_active() -> bool:
    """The model being built now is coarser than the curve smoothness setting, so an export must rebuild it."""
    return fast_view_enabled() and _view_segments < _segments


def full_segments() -> int:
    """The curve smoothness setting: what exports are built with."""
    return _segments


@contextmanager
def exact():
    """Inside this block everything is built at the full curve smoothness, whatever the view uses."""
    global _exact_depth
    _exact_depth += 1
    try:
        yield
    finally:
        _exact_depth -= 1


def set_interactive_mode(enabled: bool) -> None:
    """When enabled (e.g. during mouse dragging / interactive preview), curves use lower segment counts for speed."""
    global _interactive_mode
    _interactive_mode = bool(enabled)


def is_interactive_mode() -> bool:
    return _interactive_mode


def set_circle_segments(n: int) -> None:
    global _segments
    _segments = max(16, min(720, int(n)))


def circle_segments() -> int:
    """Flat pieces around a full circle."""
    base = _view_segments if fast_view_active() else _segments
    if _interactive_mode:
        return min(base, max(24, base // 3))
    return base


def arc_segments(sweep: float) -> int:
    """Pieces for an arc of `sweep` radians: the same fineness as a circle, never fewer than 32."""
    base = circle_segments()
    min_segs = 16 if _interactive_mode else 32
    return max(min_segs, round(base * abs(sweep) / (2.0 * math.pi)))


def sphere_segments() -> int:
    base = circle_segments()
    min_segs = 18 if _interactive_mode else 36
    return max(min_segs, base * 3 // 4)
