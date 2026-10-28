"""Emboss on a flat wall of a tapered hex prism must stay flat: the wall's normals form a ring around the axis
(the taper tilts them), which used to pass as a big-radius cylinder and bent the letters. Document from problem
report 20261021-205724."""
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import detect_cylinder_surface, ray_mesh_hit
from omacad.model.features.emboss import EmbossFeature

DATA = Path(__file__).parent / "data" / "emboss_on_tapered_prism.omacad"


def test_flat_wall_of_tapered_prism_is_not_a_cylinder():
    doc = Exporter.load_project(str(DATA))
    mesh = list(doc.bodies.values())[0].render_mesh
    # The sketch plane's normal points into the body: ray down the -normal from the sketch's centroid.
    sketch = doc.sketches["sketch_1"]
    origin = np.asarray(sketch.plane.origin, dtype=float)
    normal = np.asarray(sketch.plane.normal, dtype=float)
    hit = ray_mesh_hit(mesh, origin + normal * 60.0, -normal)
    assert hit is not None
    assert detect_cylinder_surface(mesh, hit[1]) is None


def test_emboss_on_tapered_prism_extrudes_straight_from_the_flat_wall():
    doc = Exporter.load_project(str(DATA))
    feat = EmbossFeature("t", "t", "sketch_1", 0, 1.0)
    tool = feat.build_solid(doc)
    assert tool is not None
    sketch = doc.sketches["sketch_1"]
    M = np.vstack([np.asarray(sketch.plane.get_transform_matrix_3x4(), dtype=float).reshape(3, 4), [0, 0, 0, 1]])
    local = (np.linalg.inv(M) @ np.hstack([np.asarray(tool.to_mesh().vert_properties)[:, :3],
                                           np.ones((len(tool.to_mesh().vert_properties), 1))]).T).T[:, 2]
    # Straight along the sketch normal: the letters span the depth plus the 0.02 mm start behind the face, no bend.
    assert abs((local.max() - local.min()) - (1.0 + 0.02)) < 1e-3
