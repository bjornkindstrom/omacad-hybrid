"""Snap detent in the box sill keeps material outside and opens towards the cavity (report 20261101-211334)."""
import manifold3d as m3d
from omacad.model.features.primitives import BoxFeature, _snap_center_x


def _box(snap):
    f = BoxFeature("f1", "Box", center="bottom_center", length=71.0, width=46.0, height=11.0 + 1.5 + 2.06,
                   wall_thickness=2.0, bottom_thickness=1.5, outer_round=5.0, inner_round=3.0,
                   lip_height=2.26, lip_step=1.0, clearance=0.2, snap_size=snap)
    return f.build_solid()


def _solid_at(solid, x, z):
    probe = m3d.Manifold.cube((0.05, 0.05, 0.05)).translate((x, 0.0, z))
    return (solid ^ probe).volume() > 1e-6


def test_detent_leaves_outer_material_and_opens_to_cavity():
    r = 0.6
    cx = _snap_center_x(71.0, 2.0, r)
    assert 35.5 - (cx + r) >= 0.2 - 1e-9
    solid = _box(r)
    z_shelf = 14.56 - 2.26
    z = z_shelf - 0.2
    assert _solid_at(solid, 35.5 - 0.1, z)            # outer wall intact
    assert not _solid_at(solid, cx, z)                # pocket itself
    assert not _solid_at(solid, 35.5 - 2.0 - 0.1, z)  # ramp opens towards the cavity
    assert _solid_at(solid, cx, z_shelf - r - 0.3)    # floor of the pocket remains
