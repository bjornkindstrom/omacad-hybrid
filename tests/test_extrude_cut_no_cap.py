"""Extruded cut on a planar face must cut cleanly through without leaving a zero-thickness coplanar cap (request 20261013-220451)."""
from pathlib import Path
from omacad.io.exporter import Exporter

DOC = Path(__file__).parent / "data" / "extrude_cut_coplanar_cap.omacad"


def test_extrude_cut_has_no_coplanar_cap():
    doc = Exporter.load_project(str(DOC))
    doc.timeline.recompute(doc)
    b = next(iter(doc.bodies.values()))
    # The polygon cut on the face at x=77.9547 must not leave an unpenetrated cap
    has_cap = any(abs(f.normal[0] + 1.0) < 1e-3 and abs(f.origin[0] - 77.9547) < 1e-3 and abs(f.area - 90.077) < 1e-2 for f in b.faces)
    assert not has_cap
    front_wall = [f for f in b.faces if abs(f.normal[0] - 1.0) < 1e-3 and abs(f.origin[0] - 77.9547) < 1e-3]
    assert len(front_wall) == 1
    # Front wall has polygon hole cut out of it: 890.05 - 90.08 = 799.97 mm2
    assert abs(front_wall[0].area - 799.97689) < 1e-2
