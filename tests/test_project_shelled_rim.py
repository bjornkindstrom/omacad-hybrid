"""Project on the rim of a shelled box takes the inner outline and the holes too, not only the outer outline (#103)."""
from pathlib import Path

import pytest

from omacad.io.exporter import Exporter
from omacad.model.sketch_editing import _snap_ends

DOC = str(Path(__file__).parent / "data" / "project_shelled_rim.omacad")


def test_project_takes_the_whole_rim_face():
    doc = Exporter.load_project(DOC)
    sk = doc.sketches["sketch_3"]
    rim = next(f for f in next(iter(doc.bodies.values())).faces
               if f.normal[2] > 0.999 and abs(f.origin[2] - 25.0) < 1e-3)
    sk.entities = [e for e in sk.entities if not getattr(e, "projected", False)]
    doc.refresh_sketch_references(sk)
    new = sk.include_reference_edges()
    sk.solve_profiles()
    assert sum(e.entity_type == "circle" for e in new) == 4          # the four screw holes
    areas = sorted(p.area for p in sk.profiles)
    assert len(areas) == 6                                             # 4 holes, the opening, the rim; no slivers
    assert areas[-1] > 3000.0                                          # the opening inside the walls
    assert areas[-2] == pytest.approx(rim.area, rel=2e-3)              # the rim itself


def test_snap_ends_joins_ends_a_hair_apart():
    segs = [((0, 0), (1, 0)), ((1.0007, 0.0004), (1, 1)), ((1, 1), (0, 0))]
    out = _snap_ends(segs, 2.5e-3)
    ends = {p for ab in out for p in ab}
    assert len(ends) == 3
