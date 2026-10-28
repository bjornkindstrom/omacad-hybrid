from pathlib import Path

from omacad.io.exporter import Exporter
from omacad.model.timeline import FilletFeature


def test_fillet_overrun_capped_to_adjacent_clearance():
    # Load user's test document where 50x50 box has a pocket with 2 mm wall
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "fillet_clearance.omacad"))
    # Last feature is the outer top edge fillet
    fillet = doc.timeline.features[-1]
    assert isinstance(fillet, FilletFeature)
    # Set an exaggerated fillet radius (e.g. 20 mm on a 2 mm wall)
    fillet.size = 20.0
    doc.timeline.recompute(doc)
    
    body = list(doc.bodies.values())[0]
    # Verify the body is valid and watertight
    assert not body.manifold.is_empty()
    assert body.manifold.volume() > 8800.0
