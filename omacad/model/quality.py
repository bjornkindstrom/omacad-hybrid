"""How finely round shapes are cut into flat pieces (the 'Curve smoothness' setting). The model has no
Qt, so the settings manager pushes the value in here."""
import math

DEFAULT_SEGMENTS = 96
_segments = DEFAULT_SEGMENTS
_interactive_mode: bool = False


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
    if _interactive_mode:
        return max(24, _segments // 3)
    return _segments


def arc_segments(sweep: float) -> int:
    """Pieces for an arc of `sweep` radians: the same fineness as a circle, never fewer than 32."""
    base = circle_segments()
    min_segs = 16 if _interactive_mode else 32
    return max(min_segs, round(base * abs(sweep) / (2.0 * math.pi)))


def sphere_segments() -> int:
    base = circle_segments()
    min_segs = 18 if _interactive_mode else 36
    return max(min_segs, base * 3 // 4)
