"""Placement of reference images on named planes or planar body faces."""
import numpy as np

from omacad.model.sketch import SketchPlane


def face_plane_data(face):
    plane = SketchPlane.from_face(face.normal, face.origin).centered_on(face.tris)
    return {key: getattr(plane, key).tolist() for key in ("origin", "u_axis", "v_axis", "normal")}


def canvas_plane(doc, canvas):
    data = canvas.get("face_plane")
    if data:
        return SketchPlane(name="FACE", **{key: np.asarray(value, dtype=float) for key, value in data.items()})
    pid = canvas.get("plane_id", "XY")
    if pid in doc.origin_planes:
        return doc.origin_planes[pid]
    if pid in doc.construction_planes:
        return doc.construction_plane(pid)
    return None
