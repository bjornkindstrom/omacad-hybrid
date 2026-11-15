"""Requests #237-#240 (Björn, 0.9.9.80.179): a cup shelled, split at half height, a 1 mm lip extruded from the
projected rim of the lower half and cut from the upper half.

#237: the cut left "fuzz" (fnas) on the inner wall: the lip's inner face, re-tessellated from the projected circle,
missed the wall by nanometres and the kernel kept a skin that thin. #238: that skin broke the inner wall into
pieces, so a click lit up only part of it. #239: with the upper half hidden the floor could not be selected: the
visible sketch's projected disc (a bare copy of the cut face) caught the click, and the hidden body was picked
instead. #240: the outline of a traced logo (a spline) could not be selected for a fillet: free-form outlines
with square walls were dismissed as "a circle", and a needle at a wing tip spoiled the outline's walls."""
import os

import numpy as np
import manifold3d as m3d
import pytest

from omacad.io.exporter import Exporter
from omacad.model import quality
from omacad.model.kernel import CadKernel
from omacad.ui.math3d import camera_matrices
from omacad.ui.viewport.viewport import Viewport3D

DATA = os.path.join(os.path.dirname(__file__), "data")
CUP = os.path.join(DATA, "lip_cut_fnas_237.omacad")            # before the Combine (cut)
LOGO = os.path.join(DATA, "logo_outline_fillet_240.omacad")


class _Viewport(Viewport3D):
    """Picking only: the camera of the report, no window."""

    def __init__(self, doc, az, el, dist, target, edge_pick=False):
        self.doc = doc
        self.edge_pick_mode = edge_pick
        self.plane_pick_mode = False
        self.edge_xray = False
        self._w, self._h = 1600, 900
        self.cam_az, self.cam_el, self.cam_dist = az, el, dist
        self.cam_target = np.asarray(target, dtype=float)
        self.active_tool_title = lambda: None

    def width(self):
        return self._w

    def height(self):
        return self._h

    def get_matrices(self):
        proj, view = camera_matrices(self.cam_target, self.cam_dist, self.cam_az, self.cam_el, self._w / self._h)
        return proj, view, np.eye(4)


def _triangles(manifold):
    mesh = manifold.to_mesh64()
    return np.asarray(mesh.vert_properties[:, :3], dtype=float)[np.asarray(mesh.tri_verts, dtype=np.int64)]


def _skin_in_groove(manifold):
    """Triangles on the inner wall (r < 33.9) between the lip's bottom and top (z 10..15): there must be none."""
    tris = _triangles(manifold)
    c = tris.mean(axis=1)
    sel = (c[:, 2] > 10.05) & (c[:, 2] < 14.95) & (np.linalg.norm(c[:, :2], axis=1) < 33.9)
    return int(sel.sum())


def test_237_lip_cut_from_a_projected_rim_leaves_no_skin():
    quality.set_circle_segments(72)      # the smoothness the report was made at: the mismatch is 25 nm there
    doc = Exporter.load_project(CUP)
    upper, lower = doc.bodies["body_cylinder_1"], doc.bodies["body_cylinder_3"]
    # the lip was joined from the lower half's projected rim: welded on, it leaves no hair-thin face
    assert not CadKernel.has_needles(lower.manifold) and not CadKernel.has_sheets(lower.manifold)
    assert len(lower.faces) == 4                        # bottom, floor, rim at z=10, lip top at z=15
    before = upper.manifold.volume()
    lip = np.pi * (34.0 ** 2 - 32.998 ** 2) * 5.0

    doc.combine_bodies(upper.body_id, lower.body_id, "cut", keep_tool=True)

    cut = doc.bodies["body_cylinder_1"].manifold
    assert _skin_in_groove(cut) == 0
    assert not CadKernel.has_needles(cut) and not CadKernel.has_sheets(cut)
    assert abs((before - cut.volume()) - lip) < 2.0    # polygon area, not the true circle's
    faces = doc.bodies["body_cylinder_1"].faces
    assert sorted(round(float(f.origin[2]), 3) for f in faces) == [10.0, 15.0, 18.0, 20.0]


def test_237_weld_moves_only_vertices_that_almost_touch_the_target():
    target = m3d.Manifold.cube([10.0, 10.0, 10.0])
    tool = m3d.Manifold.cube([4.0, 4.0, 4.0]).translate([10.0 + 1e-3, 3.0, 3.0])   # a micron off the wall x=10
    far = m3d.Manifold.cube([4.0, 4.0, 4.0]).translate([10.0 + 0.1, 3.0, 3.0])
    welded = CadKernel.weld_to(tool, target)
    xs = np.asarray(welded.to_mesh64().vert_properties[:, 0])
    assert np.isclose(xs.min(), 10.0)                   # its near face now lies exactly in the wall
    assert np.isclose(xs.max(), 14.0 + 1e-3)            # the far face was out of reach and stayed
    assert np.allclose(np.asarray(CadKernel.weld_to(far, target).to_mesh64().vert_properties[:, :3]),
                       np.asarray(far.to_mesh64().vert_properties[:, :3]))


def test_238_inner_wall_above_the_groove_is_one_whole_surface():
    quality.set_circle_segments(72)
    doc = Exporter.load_project(CUP)
    doc.combine_bodies("body_cylinder_1", "body_cylinder_3", "cut", keep_tool=True)
    mesh = doc.bodies["body_cylinder_1"].render_mesh
    tris = np.asarray(mesh.vertices, dtype=float).reshape(-1, 3, 3)
    c = tris.mean(axis=1)
    on_wall = np.flatnonzero((abs(np.linalg.norm(c[:, :2], axis=1) - 33.0) < 0.3) & (c[:, 2] > 15.2) & (c[:, 2] < 17.8))
    patch = np.asarray(mesh.curved_surface(int(on_wall[0]))).reshape(-1, 3, 3)
    pc = patch.mean(axis=1)
    assert pc[:, 2].min() > 14.9 and pc[:, 2].max() < 18.1       # the whole band between groove and ceiling
    area = 0.5 * np.linalg.norm(np.cross(patch[:, 1] - patch[:, 0], patch[:, 2] - patch[:, 0]), axis=1).sum()
    assert abs(area - 2 * np.pi * 33.0 * 3.0) < 0.02 * 2 * np.pi * 33.0 * 3.0
    assert len(patch) == 2 * 72                                   # one strip per segment, nothing split


def test_239_floor_is_selected_through_the_projected_disc_and_hidden_bodies_are_not_clicked():
    doc = Exporter.load_project(CUP)
    sketch = doc.sketches["sketch_1"]
    sketch.visible = True                                          # as in the report
    vp = _Viewport(doc, 30.0, 35.0, 140.0, [0.0, 0.0, 5.0])
    disc = next(i for i, p in enumerate(sketch.profiles) if p.area > 3000)   # inside the projected inner circle
    assert vp.bare_face_profile(("sketch_1", disc))
    assert not any(vp.bare_face_profile(("sketch_1", i)) for i in range(len(sketch.profiles)) if i != disc)

    sx, sy = vp.world_to_screen(np.array([5.0, -3.0, 2.0]))        # a point on the floor
    doc.bodies["body_cylinder_1"].visible = False                  # the upper half hidden
    assert vp.pick_profile(sx, sy) == ("sketch_1", disc)           # the disc floats where the cut face was ...
    assert vp.click_profile(sx, sy) is None                        # ... but a click goes to the floor behind it
    body, face = vp._pick_face(sx, sy)
    assert body.body_id == "body_cylinder_3" and abs(face.origin[2] - 2.0) < 1e-6
    assert vp.pick_body(sx, sy) == "body_cylinder_3"               # not the hidden upper half in front
    doc.bodies["body_cylinder_3"].visible = False
    assert vp.pick_body(sx, sy) is None
    doc.bodies["body_cylinder_1"].visible = True
    assert vp.pick_body(sx, sy) == "body_cylinder_1"
    doc.bodies["body_cylinder_3"].visible = True
    vp.active_tool_title = lambda: "Extrude"
    assert vp.click_profile(sx, sy) is None or vp.click_profile(sx, sy) == ("sketch_1", disc)
    doc.bodies["body_cylinder_1"].visible = False
    assert vp.click_profile(sx, sy) == ("sketch_1", disc)          # a tool that wants a profile still gets it


def _rim_and_foot(doc):
    loops = [e for e in doc.bodies["body_cylinder_1"].edges if e.kind == "loop" and abs(e.perimeter - 159.5) < 1.0]
    rim = next(e for e in loops if abs(e.pts[:, 2].mean() - 21.0) < 1e-6)
    foot = next(e for e in loops if abs(e.pts[:, 2].mean() - 20.0) < 1e-6)
    return rim, foot


def test_240_free_form_outline_is_a_loop_edge_that_can_be_picked():
    doc = Exporter.load_project(LOGO)
    rim, foot = _rim_and_foot(doc)
    assert rim.convex and not foot.convex and rim.walls is None and len(rim.pts) > 100
    logo = [e for e in doc.bodies["body_cylinder_1"].edges if e.kind == "loop" and abs(e.perimeter - 200.0) < 1.0]
    assert sorted(round(float(e.pts[:, 2].mean())) for e in logo) == [20, 21]    # the logo's own outline, top and foot

    vp = _Viewport(doc, 20.0, 40.0, 120.0, [0.0, 0.0, 15.0], edge_pick=True)
    k = int(np.argmin(rim.pts[:, 1]))                              # the piece nearest the camera
    sx, sy = vp.world_to_screen((rim.pts[k] + rim.pts[(k + 1) % len(rim.pts)]) / 2.0)
    picked = vp._pick_edge(sx, sy)
    assert picked is not None and picked.same_as(rim)


@pytest.mark.parametrize("kind,expected", [("fillet", (1 - np.pi / 4) * 0.5 ** 2), ("chamfer", 0.5 * 0.5 ** 2)])
def test_240_the_outline_can_be_rounded_and_bevelled(kind, expected):
    doc = Exporter.load_project(LOGO)
    rim, _ = _rim_and_foot(doc)
    before = doc.bodies["body_cylinder_1"].manifold.volume()
    feat = doc.add_fillet([rim.ref()], 0.5, kind=kind)
    assert feat.skipped == 0
    removed = before - doc.bodies["body_cylinder_1"].manifold.volume()
    assert abs(removed - expected * rim.perimeter) < 0.05 * expected * rim.perimeter
