"""A flat cap must stay one face even when float noise tilts a few tiny triangles by 1e-9, otherwise its rim
circle is cut into pieces and cannot be picked for Fillet/Chamfer (report 20261015-185451)."""
import os

from omacad.io.exporter import Exporter

DOC = os.path.join(os.path.dirname(__file__), "data", "cylinder_cap_noise.omacad")


def test_tilted_cylinder_top_rim_is_a_pickable_circle():
    body = next(iter(Exporter.load_project(DOC).bodies.values()))
    top = [e for e in body.edges if e.kind == "circle" and e.center[2] > 50.0]
    assert top, "top rim of the tilted cylinder has no circle edge"
    assert abs(top[0].radius - 10.0) < 1e-2
