"""Regression test for problem report 20261031-160743:
'Fillet i slot ger fula övergångar' (Fillet on slot gives ugly transitions).

When an extruded slot or rounded outline is filleted along its profile, selecting
all outline pieces (e.g. through tangent chaining or picking individual segments)
should be promoted to a single continuous loop rounding (CadKernel.loop_round_tool).
Without this, cutting straight lines (with margin m = 0.002) and circular arcs
(with chord sag margin m ~ 0.02) produces hundreds of sharp facet edges / micro-strips
at the transitions between lines and arcs.
"""

from pathlib import Path
from omacad.io.exporter import Exporter


def test_slot_fillet_transitions_are_smooth():
    project_path = Path(__file__).parent / "data" / "slot_fillet_transitions.omacad"
    doc = Exporter.load_project(str(project_path))
    doc.timeline.recompute(doc)

    # The document has one body with a filleted slot cut.
    body = next(iter(doc.bodies.values()))
    assert body is not None
    assert body.manifold is not None

    # Verify that the sharp edges around the slot filleted loop do not have
    # hundreds of facet seam lines. Prior to promoting outline pieces to loop,
    # there were 470 sharp line points in the slot fillet region due to transition seams.
    # With loop promotion, the entire slot is rounded smoothly with 0 facet seam lines.
    sl = body.render_mesh.sharp_lines
    slot_fillet_pts = [p for p in sl if 2.9 <= p[2] <= 5.1 and 19 <= p[0] <= 46 and 34 <= p[1] <= 41]
    assert len(slot_fillet_pts) == 0, f"Expected clean loop transition without facet seam lines, got {len(slot_fillet_pts)} points"
