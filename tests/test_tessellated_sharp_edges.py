import numpy as np
import pytest
from omacad.model.kernel import CadKernel
from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.faces import in_plane_edges
from omacad.model.features.base import Body


def test_tessellated_curved_edges_sharp_lines_preserved():
    """Tessellated fillets / rounded rect extrusions should retain all boundary sharp lines without gaps."""
    # Create a rounded box extrusion
    pts = Sketch.rounded_rect_outline((-45, -30), (45, 30), 5.0)
    poly = np.array(pts, dtype=np.float64)
    # Extrude with manifold
    import manifold3d as m3d
    cross = m3d.CrossSection([poly])
    m = m3d.Manifold.extrude(cross, height=8.0)
    
    mesh = CadKernel.extract_render_mesh(m)
    body = Body("test", "test", m, mesh)
    
    # Check bottom face at Z=0
    plane = SketchPlane("test_plane", origin=np.array([0., 0., 0.]), normal=np.array([0., 0., -1.]))
    segs = in_plane_edges([body], plane)
    
    # All segments should form a closed loop (every point has degree 2)
    def key(p): return (round(p[0], 3), round(p[1], 3))
    adj = {}
    for a, b in segs:
        adj.setdefault(key(a), []).append(key(b))
        adj.setdefault(key(b), []).append(key(a))
    
    # Verify no dead ends (degree 1)
    d1 = [k for k, v in adj.items() if len(v) == 1]
    assert len(d1) == 0, f"Found {len(d1)} dead-end gaps in in-plane edges"
    
    # Include in sketch and check that offset works
    sk = Sketch("s", "s", plane)
    new_ents = sk.include_reference_edges(segs)
    assert len(new_ents) > 0
    
    loop = sk.connected_entities(new_ents[0].entity_id)
    assert len(loop) == len(new_ents)
    
    # Offset by -2.5 mm inward
    offset_ents = sk.offset_entities(loop, -2.5)
    assert len(offset_ents) > 0
    assert len(sk.profiles) > 0
