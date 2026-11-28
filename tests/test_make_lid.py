import math
import pytest
import manifold3d as m3d
from omacad.model.features.lid import LidFeature
from omacad.model.document import Document


def test_rectangle_volume_and_clearance():
    source = m3d.Manifold.cube((30, 20, 20))
    lid = LidFeature('lid', 'Lid', 'source').build(source)
    expected = (34.5 * 24.5 - 30.5 * 20.5) * 5.25 + 34.5 * 24.5 * 2
    assert lid.volume() == pytest.approx(expected)
    assert (source ^ lid).volume() == pytest.approx(0)
    assert lid.bounding_box()[2] == pytest.approx(15)


@pytest.mark.parametrize('direction', list(LidFeature.DIRECTIONS))
def test_directions(direction):
    source = m3d.Manifold.cube((20, 20, 20)).translate((7, 13, -4))
    lid = LidFeature('lid', 'Lid', 'source', direction=direction).build(source)
    assert lid.volume() > 0
    assert (source ^ lid).volume() == pytest.approx(0)


@pytest.mark.parametrize('kind', ['concave', 'hollow', 'tapered', 'round'])
def test_shapes(kind):
    if kind == 'concave':
        cs = m3d.CrossSection([[(0,0),(30,0),(30,10),(10,10),(10,30),(0,30)]])
        source = cs.extrude(20)
    elif kind == 'hollow':
        source = m3d.Manifold.cube((30,30,20)) - m3d.Manifold.cube((26,26,20)).translate((2,2,2))
    elif kind == 'tapered':
        source = m3d.CrossSection.square((30,30)).extrude(20, scale_top=(.7,.7))
    else:
        source = m3d.Manifold.cylinder(20, 15, 15, 64)
    lid = LidFeature('lid', 'Lid', 'source').build(source)
    assert lid.status() == m3d.Error.NoError
    assert len(lid.decompose()) == 1
    assert (source ^ lid).volume() == pytest.approx(0, abs=1e-6)
    if kind == 'concave':
        assert lid.slice(21).area() < 30*30  # preserves the reentrant corner
    if kind == 'hollow':
        assert lid.slice(21).area() == pytest.approx(34.5**2)  # closes opening


def test_document_roundtrip_undo_and_rebuild():
    doc = Document()
    doc.add_box(30, 20, 20)
    bid = next(iter(doc.bodies))
    source_volume = doc.bodies[bid].manifold.volume()
    feat = doc.add_lid(bid)
    lid_id = 'body_' + feat.feature_id
    volume = doc.bodies[lid_id].manifold.volume()
    snapshot = doc.snapshot()
    assert len(doc.bodies) == 2
    doc.undo()
    assert len(doc.bodies) == 1
    doc.redo()
    assert doc.bodies[lid_id].manifold.volume() == pytest.approx(volume)
    doc.restore(snapshot)
    doc.timeline.recompute(doc)
    assert doc.bodies[lid_id].manifold.volume() == pytest.approx(volume)
    assert doc.bodies[bid].manifold.volume() == pytest.approx(source_volume)


@pytest.mark.parametrize('params', [dict(clearance=-1), dict(overlap=25), dict(thickness=0), dict(clearance=math.nan)])
def test_invalid_is_atomic(params):
    doc = Document()
    doc.add_box(30,20,20)
    before = doc.snapshot()
    with pytest.raises(ValueError):
        doc.add_lid(next(iter(doc.bodies)), **params)
    assert doc.snapshot() == before


def test_edit_and_source_rebuild():
    doc = Document()
    doc.add_box(30,20,20)
    bid = next(iter(doc.bodies))
    feat = doc.add_lid(bid)
    lid_id = 'body_' + feat.feature_id
    initial = doc.bodies[lid_id].manifold.volume()
    assert doc.edit_feature(1, thickness=3)
    assert doc.bodies[lid_id].manifold.volume() > initial
    assert doc.edit_feature(0, length=40)
    assert doc.bodies[lid_id].manifold.bounding_box()[3] - doc.bodies[lid_id].manifold.bounding_box()[0] == pytest.approx(46.5)


def test_project_file_roundtrip(tmp_path):
    from omacad.io.exporter import Exporter
    doc = Document()
    doc.add_box(30,20,20)
    feat = doc.add_lid(next(iter(doc.bodies)), clearance=.4, direction='-X')
    path = str(tmp_path / 'lid.omacad')
    assert Exporter.save_project(doc, path)
    loaded = Exporter.load_project(path)
    assert loaded.timeline.features[-1].to_dict() == feat.to_dict()
    lid_id = 'body_' + feat.feature_id
    assert loaded.bodies[lid_id].manifold.volume() == pytest.approx(doc.bodies[lid_id].manifold.volume())


def test_disconnected_end_is_rejected():
    source = m3d.Manifold.cube((10,10,20)) + m3d.Manifold.cube((10,10,20)).translate((20,0,0))
    with pytest.raises(ValueError, match='connected outline'):
        LidFeature('lid', 'Lid', 'source').build(source)


@pytest.mark.parametrize('edge_kind', ['chamfer', 'fillet'])
@pytest.mark.parametrize('shape', ['box', 'circle', 'concave'])
def test_top_finish(edge_kind, shape):
    if shape == 'box':
        source = m3d.Manifold.cube((30,20,20))
    elif shape == 'circle':
        source = m3d.Manifold.cylinder(20,15,15,64)
    else:
        source = m3d.CrossSection([[(0,0),(30,0),(30,10),(10,10),(10,30),(0,30)]]).extrude(20)
    plain = LidFeature('lid','Lid','source').build(source)
    finished = LidFeature('lid','Lid','source', edge_kind=edge_kind, edge_size=.5).build(source)
    assert finished.volume() < plain.volume()
    assert finished.status() == m3d.Error.NoError
    assert len(finished.decompose()) == 1
    assert (source ^ finished).volume() == pytest.approx(0, abs=1e-6)
    assert finished.slice(16).area() == pytest.approx(plain.slice(16).area())
    if shape == 'box' and edge_kind == 'chamfer':
        removed = (34.5 + 24.5)*.5**2 - 4*.5**3/3
        assert plain.volume() - finished.volume() == pytest.approx(removed, abs=1e-5)


def test_lid_owns_object_after_reload_and_edit():
    doc = Document()
    doc.add_box(30,20,20)
    bid = next(iter(doc.bodies))
    feat = doc.add_lid(bid, edge_kind='fillet', edge_size=.4)
    lid_id = 'body_' + feat.feature_id
    for restore in (False, True):
        if restore:
            doc.restore(doc.snapshot())
        h = doc.object_history
        lid_object = h.owners[feat.feature_id]
        assert lid_object != h.owners[doc.timeline.features[0].feature_id]
        assert h.objects[lid_object].body_ids == [lid_id]
        assert doc.timeline.features[-1].edge_kind == 'fillet'
    assert doc.edit_feature(1, edge_kind='chamfer', edge_size=.6)
    assert doc.timeline.features[-1].edge_size == .6
