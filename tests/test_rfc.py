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



def test_partial_upload_resumes_without_reuploading_files_or_duplicate_issue(tmp_path):
    import hashlib
    folder = make(tmp_path)
    remote = {}
    writes = []
    failures = [True]
    issue = {"html_url": "https://github.com/x/y/issues/190", "body": ""}
    def api(method, path, data, tok):
        if path.startswith("/search/issues?"):
            return {"items": [issue] if issue["body"] else []}
        if method == "GET":
            return remote.get(path, {})
        if method == "POST":
            issue["body"] = data["body"]
            return issue
        if path.endswith("document.omacad") and failures and failures.pop():
            raise TimeoutError("upload timed out")
        raw = base64.b64decode(data["content"])
        remote[path] = {"sha": hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()}
        writes.append(path)
        return {}
    ok, _ = rfc.send(folder, tok="T", api=api)
    assert not ok and "timed out" in (folder / rfc.ERROR_MARK).read_text()
    assert rfc.send(folder, tok="T", api=api)[0]
    assert sum(p.endswith("REQUEST.md") for p in writes) == 1
    assert not (folder / rfc.ERROR_MARK).exists()
    assert all(not p.endswith(rfc.ERROR_MARK) for p in writes)
    # Simulate losing the local acknowledgement after GitHub created the issue.
    (folder / rfc.SENT_MARK).unlink()
    (folder / rfc.PENDING_MARK).write_text("pending")
    before = list(writes)
    assert rfc.send(folder, tok="T", api=api)[0]
    assert writes == before


def test_existing_changed_file_uses_its_remote_sha(tmp_path):
    folder = make(tmp_path)
    puts = []
    def api(method, path, data, tok):
        if method == "GET" and "/contents/" in path:
            return {"sha": "existing-sha"}
        if method == "PUT":
            puts.append(data)
        return {}
    assert rfc.send(folder, tok="T", api=api)[0]
    assert puts and all(data["sha"] == "existing-sha" for data in puts)


def test_missing_remote_files_are_uploaded(tmp_path):
    import urllib.error
    folder = make(tmp_path)
    def api(method, path, data, tok):
        if method == "GET" and "/contents/" in path:
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
        return {}
    assert rfc.send(folder, tok="T", api=api)[0]



def test_rejected_token_is_reported_with_recovery_action(tmp_path):
    import urllib.error
    folder = make(tmp_path)
    def rejected(*args):
        raise urllib.error.HTTPError("github", 401, "Unauthorized", {}, None)
    ok, message = rfc.send(folder, tok="invalid", api=rejected)
    assert not ok and "Settings" in message and "401" in message
    assert (folder / rfc.PENDING_MARK).exists()
    assert "401" in json.loads((folder / rfc.ERROR_MARK).read_text())["error"]


def test_local_acknowledgement_clears_pending_after_interrupted_cleanup(tmp_path):
    folder = make(tmp_path)
    (folder / rfc.SENT_MARK).write_text('{"issue": "https://github.com/x/y/issues/190"}')
    def unexpected(*args):
        raise AssertionError("already sent requests must not call GitHub")
    assert rfc.send(folder, tok="T", api=unexpected)[0]
    assert not (folder / rfc.PENDING_MARK).exists()


def test_upload_timeout_allows_large_models(monkeypatch):
    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b"{}"
    def open_request(request, timeout):
        captured.append(timeout)
        return Response()
    monkeypatch.setattr(rfc.urllib.request, "urlopen", open_request)
    assert rfc._api("PUT", "/example", {"content": "x"}, "T") == {}
    assert captured == [180]



def test_model_upload_omits_indentation_without_changing_project(tmp_path):
    folder = make(tmp_path)
    original = (folder / "document.omacad").read_bytes()
    uploaded = []
    def api(method, path, data, tok):
        if method == "PUT" and path.endswith("document.omacad"):
            uploaded.append(base64.b64decode(data["content"]))
        return {}
    assert rfc.send(folder, tok="T", api=api)[0]
    assert json.loads(uploaded[0]) == json.loads(original)
    assert len(uploaded[0]) < len(original)
    assert (folder / "document.omacad").read_bytes() == original



def test_request_upload_is_deferred_and_does_not_retry_failed_folder_immediately(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from omacad.ui.main_window import MainWindow
    folder = tmp_path / "new-request"
    scheduled, sent, retries = [], [], []
    monkeypatch.setattr(rfc, "token", lambda: "T")
    monkeypatch.setattr(rfc, "send", lambda path, tok: sent.append((path, tok)) or (False, "saved"))
    monkeypatch.setattr(rfc, "send_pending", lambda **kwargs: retries.append(kwargs))
    window = SimpleNamespace(run_async=lambda fn, **kwargs: scheduled.append((fn, kwargs)))
    MainWindow.retry_requests(window, folder)
    assert window._request_upload_active and not sent and not retries
    assert len(scheduled) == 1
    work, callbacks = scheduled[0]
    assert work() == (False, "saved")
    assert sent == [(folder, "T")]
    assert retries == [{"tok": "T", "exclude": folder}]
    status = []
    window.status_label = SimpleNamespace(setText=status.append)
    callbacks["on_error"]("offline")
    assert not window._request_upload_active and "offline" in status[-1]
