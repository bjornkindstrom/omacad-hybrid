"""A pocket cut with the same outline as a moved prism must not leave the prism's walls standing above the floor
(report 20261020-220439: "Extrude hänger face kvar på prism"). The moved body's corners sit 3e-5 mm off the sketch,
so a thin skin of the wall survived as a 15 mm high hanging face; the volume was right, the faces were not."""
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter

DOC = Path(__file__).parent / "data" / "extrude_cut_moved_hex_skin.omacad"


def test_pocket_cut_on_moved_prism_leaves_no_wall_above_floor():
    doc = Exporter.load_project(str(DOC))
    doc.timeline.recompute(doc)
    body = doc.bodies["body_prism_1"]
    # Hexagon 20 across flats, 40 high, cut 15 mm down from the top: 346.41 mm2 * 25 mm. The 1 um cutter
    # clearance removes ~0.34 mm3 more (perimeter 69.3 mm * 1e-3 mm * 15 mm).
    assert abs(body.manifold.volume() - 346.41016 * 25.0) < 0.5
    verts = np.asarray(body.manifold.to_mesh().vert_properties)[:, :3]
    assert not np.any(verts[:, 2] > 25.0 + 1e-3)
    # No wall face may reach above the floor (a 40 mm wall is the hanging skin)
    walls = [f for f in body.faces if abs(f.normal[2]) < 1e-3]
    assert walls and max(f.area for f in walls) < 25.0 * 11.6
