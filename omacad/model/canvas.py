"""Placement of reference images on named planes or planar body faces."""
import numpy as np

from omacad.model.sketch import SketchPlane


def face_plane_data(face):
    plane = SketchPlane.from_face(face.normal, face.origin).centered_on(face.tris)
    return {key: getattr(plane, key).tolist() for key in ("origin", "u_axis", "v_axis", "normal")}


def face_size_uv(face):
    """Centre (cu, cv) and size (w, h) in mm of a body face, measured in the plane face_plane_data gives it."""
    plane = SketchPlane.from_face(face.normal, face.origin).centered_on(face.tris)
    pts = np.asarray(face.tris, dtype=float).reshape(-1, 3) - np.asarray(plane.origin, dtype=float)
    u = pts @ np.asarray(plane.u_axis, dtype=float)
    v = pts @ np.asarray(plane.v_axis, dtype=float)
    return (float(u.min() + u.max()) / 2.0, float(v.min() + v.max()) / 2.0,
            float(np.ptp(u)), float(np.ptp(v)))


def face_for_plane(doc, data):
    """The visible body face whose canvas plane is `data` (a face_plane dict), or None."""
    origin, normal = np.asarray(data["origin"], dtype=float), np.asarray(data["normal"], dtype=float)
    for body in doc.bodies.values():
        for face in body.faces:
            if face.index < 0:
                continue
            fp = face_plane_data(face)
            if np.allclose(fp["origin"], origin, atol=1e-6) and np.allclose(fp["normal"], normal, atol=1e-6):
                return face
    return None


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
