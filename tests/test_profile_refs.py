"""Extrude and Revolve find their profile again when a sketch's profiles are numbered differently
(e.g. after changing the curve smoothness)."""
import pytest

from omacad.io.exporter import Exporter
from omacad.model import quality
from omacad.model.document import Document


def two_profile_doc():
    d = Document()
    d.auto_include_edges = False
    sk = d.start_sketch("XY")
    sk.add_rect((0, 0), (40, 30))
    sk.add_circle((60, 15), 6)
    d.finish_sketch()
    sid = list(d.sketches)[-1]
    sk = d.sketches[sid]
    circle_idx = min(range(len(sk.profiles)), key=lambda i: sk.profiles[i].area)
    d.extrude_profile(sid, circle_idx, 10, "new_body")
    d.timeline.recompute(d)
    return d, sid


def volume(d):
    return sum(b.manifold.volume() for b in d.bodies.values())


def test_extrude_follows_its_profile_when_the_order_changes(monkeypatch):
    from omacad.model.sketch import Sketch
    d, sid = two_profile_doc()
    before = volume(d)
    original = Sketch.solve_profiles

    def solve(self):
        profiles = original(self)
        profiles.reverse()
        return profiles
    monkeypatch.setattr(Sketch, "solve_profiles", solve)
    d.timeline.recompute(d)
    assert volume(d) == pytest.approx(before, rel=1e-9)
    feat = next(f for f in d.timeline.features if f.feature_type == "extrude")
    assert d.sketches[sid].profiles[feat.profile_idx].area < 200


def test_extrude_survives_a_new_curve_smoothness():
    d, sid = two_profile_doc()
    try:
        quality.set_circle_segments(32)
        d.sketches[sid].solve_profiles()
        d.timeline.recompute(d)
        assert 1000 < volume(d) < 1200                 # the 6 mm circle (about 1131), not the 40x30 rectangle
    finally:
        quality.set_circle_segments(quality.DEFAULT_SEGMENTS)


def test_signatures_survive_save_and_load(tmp_path, monkeypatch):
    d, sid = two_profile_doc()
    path = str(tmp_path / "a.omacad")
    Exporter.save_project(d, path)
    d2 = Exporter.load_project(path)
    feat = next(f for f in d2.timeline.features if f.feature_type == "extrude")
    assert feat.profile_sigs
    from omacad.model.sketch import Sketch
    original = Sketch.solve_profiles

    def solve(self):
        profiles = original(self)
        profiles.reverse()
        return profiles
    monkeypatch.setattr(Sketch, "solve_profiles", solve)
    d2.timeline.recompute(d2)
    assert volume(d2) == pytest.approx(volume(d), rel=1e-9)


def test_old_file_without_signatures_keeps_its_profiles_under_another_smoothness(tmp_path, monkeypatch):
    """A file made at 48 pieces per circle (no signatures saved) opens right at 96."""
    import json
    from omacad.model.sketch import Sketch
    original = Sketch.solve_profiles

    def solve(self):
        profiles = original(self)
        if quality.circle_segments() != 48:        # the numbering differs from the one the file was made with
            profiles.reverse()
        return profiles
    monkeypatch.setattr(Sketch, "solve_profiles", solve)
    quality.set_circle_segments(48)
    try:
        d, _ = two_profile_doc()
        want = volume(d)
        path = tmp_path / "old.omacad"
        Exporter.save_project(d, str(path))
        data = json.loads(path.read_text())
        data.pop("curve_segments", None)
        for f in data["timeline"]:
            f.pop("profile_sigs", None)
            f.pop("profile_sigs_for", None)
        path.write_text(json.dumps(data))
        quality.set_circle_segments(96)
        assert volume(Exporter.load_project(str(path))) == pytest.approx(want, rel=0.02)
    finally:
        quality.set_circle_segments(quality.DEFAULT_SEGMENTS)
