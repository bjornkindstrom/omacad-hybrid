"""
Omacad - Sketch Scale helper
Scales selected sketch entities and driving dimensions around a pivot.
"""

from typing import Iterable, Set, Tuple, Optional
import copy
from omacad.model.sketch import Sketch, scale_entity, scale_point
from omacad.model.sketch_rotate import selection_pivots, sketch_face_pivot


def scale_sketch_entities(
    sketch: Sketch,
    entity_ids: Iterable[str],
    scale: float,
    pivot: Tuple[float, float] = (0.0, 0.0),
) -> None:
    """Scales specified entities and updates associated driving dimensions in place."""
    ids: Set[str] = set(entity_ids)
    if not ids or abs(scale - 1.0) < 1e-9:
        return

    s = float(scale)

    # 1. Scale entities
    for ent in sketch.entities:
        if ent.entity_id in ids and not getattr(ent, "projected", False):
            scale_entity(ent, s, pivot)

    # 2. Scale driving dimensions that apply solely to scaled entities
    # LENGTH, DIAMETER, RADIUS
    for dim in sketch.dimensions:
        if dim.target_entity_id in ids:
            if dim.dim_type in ("LENGTH", "DIAMETER", "RADIUS", "DISTANCE", "HORIZ_DIST", "VERT_DIST"):
                dim.value = float(dim.value) * abs(s)

    sketch._bind_texts()
    sketch.solve_profiles()
