"""Reports 20261101-205314 (stub), -221011 (slot size) for Box in a row (the snap skin test left with the snap, #162)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from omacad.model.features.primitives import BoxFeature

BOX = dict(center="bottom_center", length=60.0, width=40.0, height=34.1, wall_thickness=2.0,
           bottom_thickness=2.0, outer_round=2.0, inner_round=1.0, lip_height=2.2, lip_step=1.0, clearance=0.2)


def test_front_rail_stub_is_gone():
    s = BoxFeature("b", "Box", snap_size=0.8, **BOX).build_solid()
    z = 34.1 - 2.2 + 1.0  # rail peak height
    for poly in s.slice(z).to_polygons():
        # nothing of the rail ridge (inside y 17.3..18.2) reaches the front wall
        pts = poly[(poly[:, 0] > 27.1) & (np.abs(poly[:, 1]) < 18.9)]
        assert len(pts) == 0, pts


def test_slot_size_is_adjustable():
    def lid(**kw):
        f = BoxFeature("l", "Lid", is_lid=True, **BOX, **kw)
        return f.build_solid()
    auto, big, wide = lid(), lid(slot_length=20.0, slot_width=5.0), lid(slot_length=20.0, slot_width=8.0)
    assert big.volume() < auto.volume()
    assert wide.volume() < big.volume()
    dv = big.volume() - wide.volume()
    assert dv > 0 and abs(dv) < 20.0 * 3.0 * 4.0  # extra width x slot length x lid thickness
    assert BoxFeature("l", "Lid", is_lid=True, slot_length=20, slot_width=5, **BOX).to_dict()["slot_width"] == 5.0
