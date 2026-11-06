"""Tests for SVG import into sketches and SVG pattern in Surface Texture (Cells)."""

import tempfile
import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.sketch_entities import SketchLine
from omacad.model.features.extrude import ExtrudeFeature
from omacad.model.features.honeycomb import HoneycombFeature
from omacad.model.svg_importer import parse_svg_to_geometry, parse_svg_to_sketch_entities, svg_to_template
from omacad.io.exporter import Exporter
from tests.test_curved_surface_texture import _build_spline_wall_doc


SVG_SAMPLE = """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="10" y="10" width="80" height="80"/>
  <circle cx="50" cy="50" r="15"/>
</svg>"""

SVG_STAR = """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <polygon points="50,5 64,36 98,36 70,57 81,91 50,70 19,91 30,57 2,36 36,36"/>
</svg>"""


def test_svg_geometry_parsing():
    geom = parse_svg_to_geometry(SVG_SAMPLE)
    assert geom is not None
    assert geom.area > 0
    # Outer rect 80x80 = 6400 minus circle pi*15^2 ~ 706.86 -> ~ 5693
    assert 5500 < geom.area < 6000

    polys, (w, h) = svg_to_template(geom, 20.0)
    assert len(polys) == 1
    assert max(w, h) == 20.0


def test_svg_import_to_sketch():
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(SVG_SAMPLE)
        f.flush()
        doc = Document()
        sketch = Exporter.import_svg_to_sketch(f.name, doc)
        assert sketch is not None
        assert len(sketch.entities) > 0
        assert len(sketch.profiles) == 2


def test_svg_surface_texture_flat_face():
    doc = Document()
    sk = Sketch("s1", "Sketch 1", SketchPlane.create_named("XY"))
    l1 = SketchLine("l1", (0, 0), (100, 0))
    l2 = SketchLine("l2", (100, 0), (100, 100))
    l3 = SketchLine("l3", (100, 100), (0, 100))
    l4 = SketchLine("l4", (0, 100), (0, 0))
    for l in (l1, l2, l3, l4):
        sk.entities.append(l)
    sk.solve_profiles()
    doc.sketches[sk.sketch_id] = sk
    feat = ExtrudeFeature("e1", "Extrude", sk.sketch_id, 0, 10.0, "new_body")
    feat.execute(doc)
    body = doc.bodies["body_e1"]

    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(SVG_STAR)
        f.flush()
        params = {
            "shape": "svg", "svg_path": f.name, "size": 15.0, "wall": 3.0, "margin": 5.0, "depth": 2.0, "through": False,
            "angle": 0.0, "partial": False, "randomness": 100.0, "seed": 1, "style": "even",
            "fine_size": 2.0, "inner_wall": 0.8, "hotspots": 1, "rounding": 0.0, "opening": 100.0,
            "opening_end": 100.0, "relaxation": 0, "hole": "cell"
        }
        ref = {"kind": "plane", "origin": [50.0, 50.0, 10.0], "normal": [0.0, 0.0, 1.0]}
        res, cells, skipped = HoneycombFeature.compute(body.manifold, [ref], params)
        assert skipped == 0
        assert cells > 0
        assert res.volume() < body.manifold.volume()


def test_svg_surface_texture_curved_wall():
    doc = _build_spline_wall_doc()
    body = doc.bodies["body_e1"]
    ref = {"kind": "surface", "point": [35.0, 25.0, 25.0], "normal": [0.0, -1.0, 0.0]}

    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(SVG_STAR)
        f.flush()
        params = {
            "shape": "svg", "svg_path": f.name, "size": 10.0, "wall": 2.5, "margin": 3.0, "depth": 1.0, "through": True,
            "angle": 0.0, "partial": False, "randomness": 100.0, "seed": 1, "style": "even",
            "fine_size": 2.0, "inner_wall": 0.8, "hotspots": 1, "rounding": 0.0, "opening": 100.0,
            "opening_end": 100.0, "relaxation": 0, "hole": "cell"
        }
        res, cells, skipped = HoneycombFeature.compute(body.manifold, [ref], params)
        assert skipped == 0
        assert cells > 0
        assert res.volume() < body.manifold.volume()
