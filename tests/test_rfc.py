"""Request for change: the folder is built, uploaded to the requests repo with an issue, and kept for later when it cannot be sent."""
import base64
import json

from omacad import rfc
from omacad.model.document import Document


def make(tmp_path):
    d = Document()
    d.add_box(10, 20, 30)
    return rfc.build_request(d, "Please let me copy a hole along a curve.\nIt would save time.", "Anna Test",
                             {"screenshot_view.png": b"\x89PNGfake", "screenshot_marked.png": b"\x89PNGmarked"}, {"kind": "request"}, base_dir=tmp_path)


def test_request_folder_has_request_md_and_no_ai_prompt(tmp_path):
    folder = make(tmp_path)
    names = {p.name for p in folder.iterdir()}
    assert {"REQUEST.md", "document.omacad", "report.json", "log.txt", "screenshot_marked.png", "pending", "name.txt"} <= names
    assert "PROMPT.md" not in names
    text = (folder / "REQUEST.md").read_text()
    assert "Anna Test" in text and "copy a hole along a curve" in text


def test_send_uploads_every_file_and_opens_an_issue(tmp_path):
    folder = make(tmp_path)
    calls = []

    def fake(method, path, data, tok):
        calls.append((method, path, data, tok))
        return {"html_url": "https://github.com/x/y/issues/1"} if path.endswith("/issues") else {}

    ok, msg = rfc.send(folder, tok="T0KEN", api=fake)
    assert ok and "sent" in msg.lower()
    puts = [c for c in calls if c[0] == "PUT"]
    assert all(c[1].startswith(f"/repos/{rfc.REPO}/contents/request-for-change/{folder.name}-anna-test/") for c in puts)
    assert puts[0][1].endswith("/REQUEST.md")                                   # readable even if the rest fails
    assert "document.json" not in " ".join(c[1] for c in puts)                  # the .omacad file is enough
    assert base64.b64decode(next(c[2]["content"] for c in puts if c[1].endswith("screenshot_marked.png"))) == b"\x89PNGmarked"
    issue = [c for c in calls if c[0] == "POST"][0]
    assert issue[2]["labels"] == ["request"] and issue[2]["title"].startswith("Request: Please let me copy")
    assert all(c[3] == "T0KEN" for c in calls)
    assert not (folder / "pending").exists() and json.loads((folder / "sent.json").read_text())["issue"].endswith("/issues/1")


def test_without_a_token_the_request_stays_pending(tmp_path, monkeypatch):
    monkeypatch.delenv("OMACAD_RFC_TOKEN", raising=False)
    monkeypatch.setattr(rfc, "token", lambda: "")
    folder = make(tmp_path)
    ok, msg = rfc.send(folder)
    assert not ok and "saved" in msg and (folder / "pending").exists()


def test_network_failure_keeps_it_for_later_and_pending_requests_go_out_later(tmp_path, monkeypatch):
    folder = make(tmp_path)

    def down(*a):
        raise OSError("no network")

    ok, msg = rfc.send(folder, tok="T", api=down)
    assert not ok and (folder / "pending").exists()
    monkeypatch.setattr(rfc, "token", lambda: "T")
    sent = []
    assert rfc.send_pending(tmp_path, api=lambda m, p, d, t: sent.append(p) or {}) == 1
    assert sent and not (folder / "pending").exists()
    assert rfc.send_pending(tmp_path, api=lambda *a: {}) == 0                  # nothing left to send


def test_token_comes_from_the_environment_first(monkeypatch):
    monkeypatch.setenv("OMACAD_RFC_TOKEN", " abc ")
    assert rfc.token() == "abc"
