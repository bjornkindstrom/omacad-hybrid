"""Emboss on a cylinder wall whose top edge has a fillet: the wall behind the letters must be found.

The fillet joins the wall into one smooth patch, so the cylinder fit used to give up and the letters fell back to a
flat face 36 mm away (floating, "can't emboss on what's behind"). Document from problem report 20261021-204118."""
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import detect_cylinder_surface, ray_mesh_hit
from omacad.model.features.emboss import EmbossFeature

DATA = Path(__file__).parent / "data" / "emboss_behind_fillet_wall.omacad"


def _wall_hit():
    doc = Exporter.load_project(str(DATA))
    mesh = doc.bodies["body_cylinder_1"].render_mesh
    hit = ray_mesh_hit(mesh, np.array([1e4, -3.0, 19.0]), np.array([-1.0, 0.0, 0.0]))
    return mesh, hit


def test_cylinder_fit_ignores_the_fillet_that_joins_the_wall():
    mesh, (t, tri) = _wall_hit()
    cyl = detect_cylinder_surface(mesh, tri)
    assert cyl is not None
    assert abs(cyl["radius"] - 20.0) < 0.05
    assert abs(abs(cyl["axis"][2]) - 1.0) < 1e-3       # the wall's axis is Z


def test_emboss_wraps_the_letters_onto_the_wall_not_the_plane_behind():
    doc = Exporter.load_project(str(DATA))
    sketch = doc.sketches["sketch_2"]
    feat = EmbossFeature("t", "t", "sketch_2", 0, 1.0)
    tool = feat.build_solid(doc)
    assert tool is not None
    v = np.asarray(tool.to_mesh().vert_properties)[:, :3]
    radial = np.hypot(v[:, 0], v[:, 1])
    # Letters sit on the R=20 wall and stand 1 mm out; the flat plane lies at x = 36 (radius >= 36).
    assert radial.max() < 21.5
    assert radial.min() < 20.5
    assert len(sketch.profiles) == 5
