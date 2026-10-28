"""Restart with a new version: the work survives the restart, and a new commit is noticed."""
import subprocess

from omacad import session
from omacad.io.exporter import Exporter
from omacad.model.document import Document


def test_session_round_trip_keeps_document_and_open_sketch(tmp_path):
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rounded_rect((0, 0), (30, 20), 3.0)
    file = tmp_path / "session.json"
    session.save(d, "/tmp/x.omacad", {"azimuth": 12.0}, file)

    data = session.load(file)
    assert data["path"] == "/tmp/x.omacad" and data["camera"] == {"azimuth": 12.0}
    d2 = Document()
    Exporter.apply_dict(d2, data["document"])
    assert d2.active_sketch is not None and d2.active_sketch.sketch_id == sk.sketch_id
    assert len(d2.active_sketch.entities) == len(sk.entities)


def test_missing_or_broken_session_is_none(tmp_path):
    assert session.load(tmp_path / "none.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert session.load(bad) is None


def test_code_version_changes_on_commit(tmp_path):
    def git(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True, capture_output=True)
    assert session.code_version(tmp_path) is None            # not a checkout
    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "one")
    v1 = session.code_version(tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "two")
    assert v1 and session.code_version(tmp_path) not in (None, v1)
