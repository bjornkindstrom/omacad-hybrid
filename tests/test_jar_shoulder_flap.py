import pytest
import numpy as np
from omacad.model.document import Document
from omacad.model.jar import JarSpec

@pytest.mark.parametrize("diameter,neck_height,pitch", [(40., 10., 2.5), (20., 5., 4.)])
def test_jar_shoulder_has_clean_circle(diameter, neck_height, pitch):
    spec = JarSpec(
        diameter=diameter,
        height=30.0,
        neck_diameter=15.0,
        neck_height=neck_height,
        pitch=pitch,
        wall=2.0,
    )
    doc = Document()
    ids = doc.add_jar(spec)
    body = doc.bodies[ids["jar"]]

    # Shoulder is at z = height = 30.0, neck radius = 15/2 = 7.5
    shoulder_edges = [
        e for e in body.edges
        if getattr(e, "kind", "") == "circle"
        and abs(e.center[2] - 30.0) < 1e-3
        and abs(e.radius - 7.5) < 1e-2
    ]
    assert len(shoulder_edges) >= 1
    # Check that it's a full 2*pi circle (not broken by a thread flap into partial fragments)
    full_circle = any(abs(e.sweep - 2 * np.pi) < 1e-3 for e in shoulder_edges)
    assert full_circle, "Shoulder circle at neck base should be a full 360-degree circle with no flap disruption"
