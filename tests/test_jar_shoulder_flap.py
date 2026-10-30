import pytest
import numpy as np
from omacad.model.document import Document
from omacad.model.jar import JarSpec

def test_jar_shoulder_has_clean_circle():
    spec = JarSpec(
        diameter=40.0,
        height=30.0,
        neck_diameter=15.0,
        neck_height=10.0,
        pitch=2.5,
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
