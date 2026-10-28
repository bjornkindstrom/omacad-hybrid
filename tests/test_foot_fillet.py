"""A foot fillet on a shelf that an earlier rim fillet has already narrowed must not hang over it."""
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter

DOC = Path(__file__).parent / "data" / "foot_fillet_over_rim_fillet.omacad"


def test_foot_fillet_runs_out_into_the_rim_fillet():
    # report 20261011-222411: a 2 mm rim fillet leaves 0.5 mm of flat shelf, the 2 mm foot fillet needs 2 mm
    doc = Exporter.load_project(str(DOC))
    doc.timeline.recompute(doc)
    m = next(iter(doc.bodies.values())).manifold
    assert m.status().name == "NoError" and len(m.decompose()) == 1
    # just below the shelf plane the outline follows the rim fillet (x = -13.44); a lip would reach x = -14.5
    xs = np.concatenate([p[:, 0] for p in m.slice(9.95).to_polygons()])
    assert xs.min() > -13.8
    # the fillet still adds material, and no more than the full-size one would
    fillet2 = next(f for f in doc.timeline.features if f.name == "Fillet 2")
    fillet2.suppressed = True
    doc.timeline.recompute(doc)
    without = next(iter(doc.bodies.values())).manifold.volume()
    assert 0 < m.volume() - without < 144
