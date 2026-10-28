"""Round surfaces light up under the cursor like flat faces (problem report 20261025-125125: the arcs of an
extruded sketch, one of them a sketch fillet running tangent into a larger arc, stayed dark)."""
from pathlib import Path

import numpy as np
import trimesh

from omacad.io.exporter import Exporter
from omacad.model.faces_surfaces import curved_surface_ids
from omacad.ui.math3d import orbit_view, perspective
from omacad.ui.viewport.viewport import Viewport3D

DOC = str(Path(__file__).parent / "data" / "rounded_slot_hover.omacad")


def _arc_lengths(doc):
    """Length of every sketch arc (three points -> circle)."""
    out = []
    for e in next(iter(doc.sketches.values())).entities:
        if e.entity_type != "arc":
            continue
        a, m, b = (np.asarray(p, dtype=float) for p in (e.p_start, e.p_mid, e.p_end))
        ab, am, mb = np.linalg.norm(b - a), np.linalg.norm(m - a), np.linalg.norm(b - m)
        cross = (m - a)[0] * (b - a)[1] - (m - a)[1] * (b - a)[0]
        r = ab * am * mb / (2 * abs(cross))
        ang = 2 * np.arcsin(min(am / (2 * r), 1)) + 2 * np.arcsin(min(mb / (2 * r), 1))
        out.append(r * ang)
    return sorted(out)


def test_each_sketch_arc_is_its_own_curved_surface():
    doc = Exporter.load_project(DOC)
    v, f, _ = next(iter(doc.bodies.values())).render_mesh.source
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
    ids = curved_surface_ids(v, f, tm, 20.0)
    surfaces = sorted(set(ids.tolist()) - {-1})
    # four arcs (the R23 fillet stays apart from the arc it runs into), flat walls, top and bottom are -1
    assert len(surfaces) == 4
    areas = sorted(float(tm.area_faces[ids == s].sum()) for s in surfaces)
    # chords lie inside the arc: the tessellated area is a little under arc length x 50 mm
    assert np.allclose(areas, [50 * a for a in _arc_lengths(doc)], rtol=2e-3)


class _View(Viewport3D):
    def __init__(self, doc):   # the camera from the report, no GL context
        self.doc = doc
        self.edge_pick_mode = False
        self.edge_xray = False
        self.hover_edge = self.hover_face = self.hover_surface = None
        self.selected_edges = []
        self.section = None
        self._w, self._h = 1640, 1050
        self.cam_az, self.cam_el, self.cam_dist = 48.509765625, 23.982031250000006, 281.8636461216757
        self.cam_target = np.array([103.76851654052734, 42.86438751220703, 26.28328514099121])

    def width(self):
        return self._w

    def height(self):
        return self._h

    def get_matrices(self):
        view = orbit_view(self.cam_target, self.cam_dist, self.cam_az, self.cam_el)
        proj = perspective(45.0, self._w / self._h, max(0.5, self.cam_dist * 0.01), self.cam_dist + 5000.0)
        return proj, view, np.eye(4)

    def to_screen(self, p):
        proj, view, _ = self.get_matrices()
        c = proj @ view @ np.array([*p, 1.0])
        ndc = c[:3] / c[3]
        return (ndc[0] * 0.5 + 0.5) * self._w, (1.0 - (ndc[1] * 0.5 + 0.5)) * self._h

    def update(self):
        pass


def test_hovering_the_round_end_lights_up_that_arc_only():
    doc = Exporter.load_project(DOC)
    vp = _View(doc)
    # the large arc at the front (start (60, 5), mid (83.6, 11.2)), half way up the 50 mm wall
    vp._update_edge_hover(*vp.to_screen((83.60754009823624, 11.1828976193434, 25.0)))
    assert vp.hover_edge is None and vp.hover_face is None
    assert vp.hover_surface is not None
    tris = vp.hover_surface[1]
    assert np.isclose(tris[..., 2].min(), 0.0) and np.isclose(tris[..., 2].max(), 50.0)
    pts = tris.reshape(-1, 3)[:, :2]
    # its ends are the arc's: (60, 5) and where the R23 fillet starts, not the fillet's far end at the side wall
    assert np.linalg.norm(pts - [60.0, 5.0], axis=1).min() < 1e-3
    assert np.linalg.norm(pts - [103.12892042222, 25.82734648939286], axis=1).min() < 1e-3
    assert np.linalg.norm(pts - [108.86534776903596, 44.077217847712326], axis=1).min() > 5.0

    # on a flat wall: the face is lit, no curved surface
    vp._update_edge_hover(*vp.to_screen((20.0, 2.5, 25.0)))
    assert vp.hover_face is not None and vp.hover_surface is None
