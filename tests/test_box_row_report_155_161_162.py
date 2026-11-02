"""Requests #155 (honeycomb in walls and lid), #161 (lead-in chamfer in the box), #162 (no snap detent)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from omacad.model.features.primitives import BoxFeature

BOX = dict(center="bottom_center", length=60.0, width=40.0, height=30.0, wall_thickness=2.0,
           bottom_thickness=2.0, outer_round=2.0, inner_round=1.0, lip_height=2.2, lip_step=1.0, clearance=0.2)


def test_snap_detent_is_gone_from_box_and_lid():
    for is_lid in (False, True):
        a = BoxFeature("a", "A", snap_size=0.6, is_lid=is_lid, **BOX).build_solid()
        b = BoxFeature("b", "B", snap_size=1.5, is_lid=is_lid, **BOX).build_solid()
        assert abs(a.volume() - b.volume()) < 1e-6   # the size of a detent changes nothing now


def test_groove_back_corners_are_chamfered_only_at_lid_level():
    import manifold3d as m3d
    box = BoxFeature("b", "B", **BOX).build_solid()
    x_back, y_edge = -(60.0 - 4.0) / 2.0, 40.0 / 2.0 - 2.0 + 1.0     # groove back wall and side wall
    z_lid = 30.0 - 2.2 + 0.1    # just above the groove floor, where the groove is full width

    def probe(z, x0, y0, size=0.3):
        sq = m3d.CrossSection.square((size, size)).translate((x0, y0))
        return (box.slice(z) ^ sq).area()

    # up at lid level the very corner of the groove is filled by the chamfer ...
    assert probe(z_lid, x_back, y_edge - 0.3) > 0.08
    assert probe(z_lid, x_back, -y_edge) > 0.08
    # ... but only a chamfer wide: further along the back wall the groove is open again
    assert probe(z_lid, x_back + 2.5, y_edge - 0.3) < 1e-6
    # the box below the groove is untouched by it (cavity corner still the plain inner round)
    assert probe(10.0, x_back, 17.7) < 0.09


def test_honeycomb_cuts_walls_and_lid():
    plain_box = BoxFeature("b", "B", **BOX).build_solid()
    hc_box = BoxFeature("b", "B", honeycomb=True, honeycomb_size=5.0, honeycomb_wall=1.2, **BOX).build_solid()
    assert hc_box.volume() < plain_box.volume()
    # z = 10 is below the groove, inside the wall cells' height range: the section lost wall material
    assert hc_box.slice(10.0).area() < plain_box.slice(10.0).area() - 5.0

    plain_lid = BoxFeature("l", "L", is_lid=True, **BOX).build_solid()
    hc_lid = BoxFeature("l", "L", is_lid=True, honeycomb=True, honeycomb_size=5.0, honeycomb_wall=1.2, **BOX).build_solid()
    assert hc_lid.volume() < plain_lid.volume() * 0.9


def test_honeycomb_is_editable_in_box_row_settings():
    from PySide6.QtWidgets import QApplication
    from omacad.model.document import Document
    from omacad.ui.history_delegate import apply_dimension
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(count=2, length=60.0, width=40.0, height=30.0, has_lid=True)
    gid = doc.object_groups[0]["id"]
    assert doc.box_row_group_params(gid)["honeycomb"] is False
    boxes, lids = doc.box_row_features(gid)
    assert apply_dimension(doc, "group_param", (gid, "honeycomb"), "1") is True
    assert doc.box_row_group_params(gid)["honeycomb"] is True
    assert apply_dimension(doc, "group_param", (gid, "honeycomb_size"), "6") is True
    boxes, lids = doc.box_row_features(gid)
    assert all(f.honeycomb and f.honeycomb_size == 6.0 for f in boxes + lids)
    assert apply_dimension(doc, "group_param", (gid, "honeycomb"), "0") is True
    assert not any(f.honeycomb for f in doc.box_row_features(gid)[0])
