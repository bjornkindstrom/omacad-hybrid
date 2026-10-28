"""Pivot geometry and constraint updates for rigid sketch rotation."""

import math
import numpy as np
from shapely import build_area
from shapely.geometry import LineString
from shapely.ops import unary_union


def selection_pivots(entities):
    """Bounds centre and area centroid of only the selected curves, holes included."""
    segments = [s for e in entities for s in e.to_lines()]
    if not segments:
        return {}
    pts = np.asarray(segments).reshape(-1, 2)
    pivots = {"bounds": tuple((pts.min(axis=0) + pts.max(axis=0)) / 2)}
    area = build_area(unary_union([LineString(s) for s in segments]))
    if not area.is_empty and area.area > 1e-9:
        pivots["area"] = (area.centroid.x, area.centroid.y)
    return pivots


def face_centroid(plane, tris):
    """Area-weighted face centre in sketch coordinates, independent of tessellation."""
    tris = np.asarray(tris, dtype=float).reshape(-1, 3, 3)
    weights = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
    if weights.sum() < 1e-12:
        return None
    centre = np.average(tris.mean(axis=1), axis=0, weights=weights)
    return plane.world_to_uv(centre)


def sketch_face_pivot(doc, sketch):
    if sketch.face_center is not None:
        return tuple(sketch.face_center)
    # Older projects did not save the supporting face centre.
    if sketch.plane.name != "FACE":
        return None
    candidates = []
    for body in doc.bodies.values():
        if sketch.parent_body_id and body.body_id != sketch.parent_body_id:
            continue
        for face in body.faces:
            if abs(float(np.dot(face.normal, sketch.plane.normal))) < 0.9999:
                continue
            if abs(float(np.dot(face.origin - sketch.plane.origin, sketch.plane.normal))) > 1e-4:
                continue
            pivot = face_centroid(sketch.plane, face.tris)
            if pivot is not None:
                candidates.append(pivot)
    return min(candidates, key=lambda p: math.hypot(*p)) if candidates else None


def rotate_axis_constraints(sketch, ids, angle):
    """Keep rectangle shape while allowing its absolute horizontal/vertical direction to change.

    Quarter turns exchange H/V; other rotations retain their relative parallel/perpendicular
    relations. All other relations and dimensions remain for the solver to enforce.
    """
    if abs(angle) < 1e-9:
        return
    from omacad.model.sketch import SketchText
    if any(isinstance(e, SketchText) and e.path_id and e.entity_id in ids for e in sketch.entities):
        raise ValueError("Text on a path follows its curve. Detach the text from its path before rotating it.")
    if any(c.ctype == "FIX" and set(c.refs) & ids for c in sketch.constraints):
        raise ValueError("The selection contains fixed geometry. Remove its Fix constraint before rotating.")
    axes = [c for c in sketch.constraints if c.ctype in ("HORIZONTAL", "VERTICAL") and set(c.refs) <= ids]
    turns = round(angle / 90)
    if abs(angle - turns * 90) < 1e-7:
        if turns % 2:
            for c in axes:
                c.ctype = "VERTICAL" if c.ctype == "HORIZONTAL" else "HORIZONTAL"
        return
    if axes:
        anchor, kind = axes[0].refs[0], axes[0].ctype
        for c in axes[1:]:
            c.ctype = "PARALLEL" if c.ctype == kind else "PERPENDICULAR"
            c.refs = [anchor, c.refs[0]]
        sketch.constraints.remove(axes[0])


def validate_axis_dimensions(sketch, ids):
    """Do not silently invalidate driving distances measured along the sketch axes."""
    from omacad.model.sketch import point_of
    for dim in sketch.dimensions:
        if dim.dim_type not in ("HORIZ_DIST", "VERT_DIST") or not dim.refs or len(dim.pts) != 2:
            continue
        if not ({dim.target_entity_id, dim.refs[0]} & ids):
            continue
        a, b = sketch.get_entity(dim.target_entity_id), sketch.get_entity(dim.refs[0])
        if a is None or b is None:
            continue
        pa, pb = point_of(a, dim.pts[0]), point_of(b, dim.pts[1])
        if pa is None or pb is None:
            continue
        axis = 0 if dim.dim_type == "HORIZ_DIST" else 1
        if abs(abs(pa[axis] - pb[axis]) - dim.value) > 1e-4:
            raise ValueError("Rotation conflicts with a horizontal/vertical distance dimension.")
