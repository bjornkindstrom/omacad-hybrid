"""Fillet on the rim of a hole with a sharp (60 degree) corner, like the cells a honeycomb margin clips (report
20261024-081206): the two bands only overlapped behind the corner, so a ridge of unrounded rim stood there and
showed as spikes. The outline is the union of the two walls' half planes, each rounded on its own."""
import math
import os
from types import SimpleNamespace

import manifold3d as m3d
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.features.base import Body
from omacad.model.features.fillet import FilletFeature

DOC = os.path.join(os.path.dirname(__file__), "data", "fillet_honeycomb_margin.omacad")
R, TOP = 1.0, 5.0
APEX = np.array([20.0, 20.0])
SIDES = [np.array([-math.sin(math.radians(30)), -math.cos(math.radians(30))]),
         np.array([math.sin(math.radians(30)), -math.cos(math.radians(30))])]


def _notched_plate():
    plate = m3d.Manifold.cube((40.0, 40.0, TOP))
    far = [APEX + 30.0 * s for s in SIDES]
    notch = m3d.Manifold.extrude(m3d.CrossSection([[tuple(APEX), tuple(far[0]), tuple(far[1])]]), TOP + 2).translate((0, 0, -1))
    return plate - notch


def test_rim_of_a_sharp_notch_is_two_rounded_half_planes():
    body = Body("b", "plate", _notched_plate())
    body.update_render_mesh()
    rims = [e for e in body.edges if getattr(e, "kind", "") == "line" and abs(e.p0[2] - TOP) < 1e-6
            and abs(e.p1[2] - TOP) < 1e-6 and min(np.linalg.norm(e.p0[:2] - APEX), np.linalg.norm(e.p1[:2] - APEX)) < 1e-6]
    assert len(rims) == 2
    feat = FilletFeature("f", "Fillet", [e.ref() for e in rims], R)
    feat.execute(SimpleNamespace(bodies={"b": body}))
    assert feat.skipped == 0

    # independent build: each wall's half of the plate with its whole rim line rounded, then the union
    plate = m3d.Manifold.cube((40.0, 40.0, TOP))
    rod = m3d.Manifold.cylinder(200.0, R, circular_segments=2048, center=True)
    halves = []
    for k, s in enumerate(SIDES):
        wall = np.array([-s[1], s[0]]) * (1 if k == 0 else -1)          # out of the material, into the notch
        n3 = (float(-wall[0]), float(-wall[1]), 0.0)
        half = plate.trim_by_plane(n3, float(-wall @ APEX))
        # the band: a slab a radius deep along the whole rim line (local x into the material, y up, z along the
        # line), minus the rod rolling along it
        line = np.array([s[0], s[1], 0.0])
        inward = np.array([-wall[0], -wall[1], 0.0])
        if np.linalg.det(np.column_stack((inward, (0, 0, 1), line))) < 0:
            line = -line
        frame = np.column_stack((inward, (0.0, 0.0, 1.0), line, (APEX[0], APEX[1], TOP))).astype(float)
        slab = m3d.Manifold.cube((R + 1.0, R + 1.0, 400.0)).translate((-1.0, -R, -200.0))
        band = (slab - rod.translate((R, -R, 0.0))).transform(frame)
        halves.append(half - band)
    exact = (halves[0] + halves[1]).volume()
    assert body.manifold.genus() == 0
    assert body.manifold.volume() == pytest.approx(exact, abs=0.04)   # 24 facets a quarter turn: +0.026


def test_honeycomb_margin_corners_have_no_ridge():
    doc = Exporter.load_project(DOC)
    m = doc.bodies["body_box_1"].manifold
    # just below the corner of the clipped cell at x = 25, z = 13.07: the rim there is rounded like beside it
    for x, z, depth in ((24.8, 13.0, 0.4), (39.2, 13.0, 0.4), (24.8, 19.5, 0.4), (39.2, 19.5, 0.4)):
        probe = m3d.Manifold.cube((0.02, 2.0, 0.02)).translate((x - 0.01, 23.0, z - 0.01))
        top = 23.0 + (m ^ probe).volume() / 0.02 ** 2
        assert 25.0 - top == pytest.approx(depth, abs=0.08)
