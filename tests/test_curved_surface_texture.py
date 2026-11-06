"""Tests for applying surface textures (Cells, Knurl, Japandi) on curved spline surfaces."""

import math
import numpy as np
import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.sketch_entities import SketchSpline, SketchLine
from omacad.model.features.extrude import ExtrudeFeature
from omacad.model.features.curved_surface import curved_wall
from omacad.model.features.honeycomb import HoneycombFeature
from omacad.model.features.knurl import apply_knurl
from omacad.model.features.japandi import apply_japandi
from omacad.ui.dialogs.surface_texture_dlg import outer_round


def _build_spline_wall_doc():
    doc = Document()
    sk = Sketch("s1", "Sketch 1", SketchPlane.create_named("XY"))
    s1 = SketchSpline("sp1", [(0.0, 0.0), (35.0, 25.0), (75.0, -10.0), (111.25, 15.0)])
    s2 = SketchSpline("sp2", [(111.25, 25.0), (75.0, 0.0), (35.0, 35.0), (0.0, 10.0)])
    l1 = SketchLine("l1", (111.25, 15.0), (111.25, 25.0))
    l2 = SketchLine("l2", (0.0, 10.0), (0.0, 0.0))
    for e in (s1, s2, l1, l2):
        sk.entities.append(e)
    sk.solve_profiles()
    doc.sketches[sk.sketch_id] = sk
    feat = ExtrudeFeature("e1", "Extrude", sk.sketch_id, 0, 50.0, "new_body")
    feat.execute(doc)
    return doc


def test_curved_wall_detection():
    doc = _build_spline_wall_doc()
    body = doc.bodies["body_e1"]
    ref = {"kind": "surface", "point": [35.0, 25.0, 25.0], "normal": [0.0, -1.0, 0.0]}
    assert outer_round(ref) is True

    wall = curved_wall(body.manifold, ref)
    assert wall is not None
    assert wall.L > 100.0
    assert abs(wall.height - 50.0) < 1e-3
    assert wall.closed is False


def test_curved_honeycomb():
    doc = _build_spline_wall_doc()
    body = doc.bodies["body_e1"]
    ref = {"kind": "surface", "point": [35.0, 25.0, 25.0], "normal": [0.0, -1.0, 0.0]}
    params = {
        "shape": "hexagon", "size": 6.0, "wall": 1.5, "margin": 3.0, "depth": 1.0, "through": True,
        "angle": 0.0, "partial": False, "randomness": 100.0, "seed": 1, "style": "even",
        "fine_size": 2.0, "inner_wall": 0.8, "hotspots": 1, "rounding": 0.0, "opening": 100.0,
        "opening_end": 100.0, "relaxation": 0, "hole": "cell"
    }
    result, cells, skipped = HoneycombFeature.compute(body.manifold, [ref], params)
    assert skipped == 0
    assert cells > 10
    assert result.volume() < body.manifold.volume()


def test_curved_knurl():
    doc = _build_spline_wall_doc()
    body = doc.bodies["body_e1"]
    ref = {"kind": "surface", "point": [35.0, 25.0, 25.0], "normal": [0.0, -1.0, 0.0]}
    params = {"pattern": "diamond", "pitch": 3.0, "depth": 0.8, "angle": 30.0, "margin": 0.0}
    result, teeth, notes = apply_knurl(body.manifold, [ref], params)
    assert teeth > 0
    assert not notes
    assert result.volume() < body.manifold.volume()


def test_curved_japandi():
    doc = _build_spline_wall_doc()
    body = doc.bodies["body_e1"]
    ref = {"kind": "surface", "point": [35.0, 25.0, 25.0], "normal": [0.0, -1.0, 0.0]}
    params = {
        "shape": "half-round", "direction": "inward", "radius": 1.5, "width": 2.0, "depth": 2.0,
        "spacing": 1.0, "twist": 0.0, "margin": 0.0
    }
    result, ribs, notes = apply_japandi(body.manifold, [ref], params)
    assert ribs > 0
    assert not notes
    assert result.volume() < body.manifold.volume()
