"""Rolling the marker back and forward again reuses the checkpoints past the marker: no step runs again and the
bodies are exactly the ones built before. An edit while rolled back still rebuilds what follows it."""
from omacad.model.document import Document


def _doc():
    doc = Document()
    doc.add_box(20, 20, 10)
    doc.add_cylinder(4, 30)
    doc.add_box(5, 5, 40, name="Post")
    return doc


def _count_executes(doc, monkeypatch):
    calls = []
    for feat in doc.timeline.features:
        original = feat.execute

        def counted(d, _orig=original, _f=feat):
            calls.append(_f.name)
            return _orig(d)
        monkeypatch.setattr(feat, "execute", counted)
    return calls


def test_roll_back_and_forward_runs_nothing_again(monkeypatch):
    doc = _doc()
    t = doc.timeline
    t.recompute(doc)
    before = {bid: b.manifold for bid, b in doc.bodies.items()}
    calls = _count_executes(doc, monkeypatch)
    t.marker_index = 1
    t.recompute(doc)
    assert len(doc.bodies) == 1 and calls == []
    t.marker_index = len(t.features)
    t.recompute(doc)
    assert calls == []
    assert {bid: b.manifold for bid, b in doc.bodies.items()} == before     # the very same solids


def test_an_edit_while_rolled_back_rebuilds_what_follows():
    doc = _doc()
    t = doc.timeline
    t.recompute(doc)
    t.marker_index = 2
    t.recompute(doc)
    t.features[0].length = 30.0               # a changed first step while rolled back
    t.marker_index = len(t.features)
    t.recompute(doc)
    kept = {bid: round(b.manifold.volume(), 6) for bid, b in doc.bodies.items()}
    t.clear_cache()
    t.recompute(doc)
    fresh = {bid: round(b.manifold.volume(), 6) for bid, b in doc.bodies.items()}
    assert kept == fresh and len(kept) == 3
    assert abs(kept[next(iter(kept))] - 30 * 20 * 10) < 1e-6
