"""Emboss wrapped onto a bowl (a revolved spline with a filleted rim): the letters must stand upright on the wall.

The cylinder fit took the band of normals round a leaning axis (20 degrees off the bowl's Z axis), so the wrap bent
the letters sideways and stretched them ("Den warpar texten lite väl mycket"). Every normal line of a surface of
revolution meets its axis; `_revolution_axis` finds it. Document from problem report 20261101-122337."""
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import detect_cylinder_surface, ray_mesh_hit

DATA = Path(__file__).parent / "data" / "emboss_on_bowl.omacad"


def _before_emboss():
    doc = Exporter.load_project(str(DATA))
    emboss = next(f for f in doc.timeline.features if f.feature_type == "emboss")
    doc.timeline.marker_index = doc.timeline.features.index(emboss)
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    sketch = doc.sketches[emboss.sketch_id]
    region = emboss.region(doc, sketch, [emboss.profile_idx] + list(emboss.extra_profiles))
    return doc, emboss, body, sketch, region


def test_bowl_wall_is_found_round_its_own_axis():
    doc, emboss, body, sketch, region = _before_emboss()
    hit = ray_mesh_hit(body.render_mesh, np.array([200.0, 0.0, 20.0]), np.array([-1.0, 0.0, 0.0]))
    cyl = detect_cylinder_surface(body.render_mesh, hit[1])
    assert cyl is not None and not cyl["is_internal"]
    assert abs(cyl["axis"] @ [0.0, 0.0, 1.0]) > 1 - 1e-9
    p = np.asarray(cyl["origin"])
    assert np.hypot(p[0], p[1]) < 1e-6                        # on the revolve axis
    assert abs(cyl["radius"] - (200.0 - hit[0])) < 0.5        # the wall's radius where the ray met it


def test_letters_stand_upright_on_the_wall():
    doc, emboss, body, sketch, region = _before_emboss()
    tool = emboss.build_solid(doc)
    letters = tool.decompose()
    assert len(letters) == len(region.geoms) == 4
    z0 = sketch.plane.origin[2]
    _, miny, _, maxy = region.bounds
    lo, hi = tool.bounding_box()[2], tool.bounding_box()[5]
    assert abs(lo - (z0 + miny)) < 0.02 and abs(hi - (z0 + maxy)) < 0.02     # as tall as the sketch, not skewed
    for letter in letters:
        assert (letter ^ body.manifold).volume() > 1.0          # starts inside the wall, not above it
    raised = (tool - body.manifold).volume()
    assert 0.97 * region.area * emboss.depth <= raised <= 1.05 * region.area * emboss.depth
    assert len((tool + body.manifold).decompose()) == 1
