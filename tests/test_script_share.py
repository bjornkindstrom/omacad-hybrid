"""Own scripts are uploaded to the requests repository once per content, bundled examples and hidden files never."""
import base64
import json
import urllib.error

from omacad import rfc, script_share
from omacad.scripting.folder import EXAMPLES


class FakeGitHub:
    def __init__(self):
        self.files, self.calls = {}, []

    def __call__(self, method, path, data, tok):
        self.calls.append((method, path, tok))
        if method == "GET":
            if path not in self.files:
                raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
            return {"sha": script_share.blob_sha(self.files[path])}
        if data.get("sha") and data["sha"] != script_share.blob_sha(self.files.get(path, b"")):
            raise urllib.error.HTTPError(path, 409, "Conflict", {}, None)
        self.files[path] = base64.b64decode(data["content"])
        return {}


def setup(tmp_path):
    folder, data = tmp_path / "scripts", tmp_path / "data"
    folder.mkdir()
    (folder / "my_bracket.py").write_text("NAME = 'Bracket'\n")
    (folder / "my_bracket.png").write_bytes(b"\x89PNGpic")
    (folder / "_helper.py").write_text("x = 1\n")
    (folder / "my_bracket.check.txt").write_text("OK")
    bundled = next(EXAMPLES.glob("*.py"))
    (folder / bundled.name).write_bytes(bundled.read_bytes())
    return folder, data


def test_own_scripts_and_pictures_go_up_once_examples_and_hidden_files_never(tmp_path):
    folder, data = setup(tmp_path)
    gh = FakeGitHub()
    n, msg = script_share.upload(folder, "Anna Test", tok="T", api=gh, data_dir=data)
    remote = f"/repos/{rfc.REPO}/contents/scripts/anna-test-{script_share.install_id(data)}"
    assert n == 2 and "Shared" in msg
    assert set(gh.files) == {f"{remote}/my_bracket.py", f"{remote}/my_bracket.png"}
    assert gh.files[f"{remote}/my_bracket.py"] == b"NAME = 'Bracket'\n"
    assert all(c[2] == "T" for c in gh.calls)
    assert script_share.pending(folder, data) == []
    gh.calls.clear()
    assert script_share.upload(folder, "Anna Test", tok="T", api=gh, data_dir=data)[0] == 0 and not gh.calls


def test_a_changed_script_is_uploaded_again_over_the_old_one(tmp_path):
    folder, data = setup(tmp_path)
    gh = FakeGitHub()
    script_share.upload(folder, "", tok="T", api=gh, data_dir=data)
    (folder / "my_bracket.py").write_text("NAME = 'Bracket 2'\n")
    assert [p.name for p in script_share.pending(folder, data)] == ["my_bracket.py"]
    n, _ = script_share.upload(folder, "", tok="T", api=gh, data_dir=data)
    assert n == 1
    assert b"Bracket 2" in next(v for k, v in gh.files.items() if k.endswith("/anonymous-" + script_share.install_id(data) + "/my_bracket.py"))


def test_no_token_or_no_network_sends_nothing_and_keeps_it_for_later(tmp_path, monkeypatch):
    folder, data = setup(tmp_path)
    monkeypatch.setattr(rfc, "token", lambda: "")
    assert script_share.upload(folder, "x", api=FakeGitHub(), data_dir=data)[0] == 0

    def down(*a):
        raise OSError("no network")

    n, msg = script_share.upload(folder, "x", tok="T", api=down, data_dir=data)
    assert n == 0 and "later" in msg
    assert len(script_share.pending(folder, data)) == 2
    assert not (data / script_share.STATE_FILE).exists() or json.loads((data / script_share.STATE_FILE).read_text()).get("files") == {}


def test_install_id_is_stable(tmp_path):
    assert script_share.install_id(tmp_path) == script_share.install_id(tmp_path)


# ---- Get Scripts --------------------------------------------------------------------------------------------------
class FakeRepo:
    """trees + blobs API over a dict of repo path -> bytes."""

    def __init__(self, files):
        self.files = dict(files)
        self.blob_calls = 0

    def __call__(self, method, path, data, tok):
        if "/git/trees/" in path:
            return {"tree": [{"path": p, "type": "blob", "sha": script_share.blob_sha(c)} for p, c in self.files.items()]}
        if "/git/blobs/" in path:
            self.blob_calls += 1
            sha = path.rsplit("/", 1)[-1]
            c = next(c for c in self.files.values() if script_share.blob_sha(c) == sha)
            return {"content": base64.b64encode(c).decode()}
        raise AssertionError(path)


def repo_for(data):
    own = f"scripts/me-{script_share.install_id(data)}"
    return FakeRepo({
        "scripts/README.md": b"# readme",
        "scripts/lisa-a1b2c3/hook.py": b"NAME = 'Wall hook'\nDESCRIPTION = 'A hook'\n",
        "scripts/lisa-a1b2c3/hook.png": b"\x89PNGhook",
        "scripts/olle-d4e5f6/bracket.py": b"NAME = 'Olle bracket'\n",
        f"{own}/mine.py": b"NAME = 'Mine'\n",
    })


def test_list_shows_others_scripts_with_author_and_skips_this_installation(tmp_path):
    folder, data = setup(tmp_path)
    repo = repo_for(data)
    items = script_share.list_remote(folder, tok="T", api=repo, data_dir=data)
    assert [(i.file_name, i.author, i.status) for i in items] == [("hook.py", "lisa", "new"), ("bracket.py", "olle", "new")]
    assert items[0].cached.read_bytes().startswith(b"NAME = 'Wall hook'") and items[0].picture_cached.read_bytes() == b"\x89PNGhook"
    calls = repo.blob_calls
    script_share.list_remote(folder, tok="T", api=repo, data_dir=data)
    assert repo.blob_calls == calls                       # cached by sha


def test_fetched_scripts_land_in_the_folder_are_not_shared_back_and_updates_are_offered(tmp_path):
    folder, data = setup(tmp_path)
    (folder / "bracket.py").write_text("NAME = 'My own bracket'\n")       # same file name as Olle's
    repo = repo_for(data)
    items = script_share.list_remote(folder, tok="T", api=repo, data_dir=data)
    written = script_share.download(items, folder, tok="T", api=repo, data_dir=data)
    assert [p.name for p in written] == ["hook.py", "bracket_olle.py"]
    assert (folder / "hook.png").read_bytes() == b"\x89PNGhook"
    assert (folder / "bracket.py").read_text() == "NAME = 'My own bracket'\n"          # never overwritten
    assert {p.name for p in script_share.pending(folder, data)} == {"my_bracket.py", "my_bracket.png", "bracket.py"}
    assert {i.status for i in script_share.list_remote(folder, tok="T", api=repo, data_dir=data)} == {"have"}

    repo.files["scripts/lisa-a1b2c3/hook.py"] = b"NAME = 'Wall hook 2'\n"
    items = script_share.list_remote(folder, tok="T", api=repo, data_dir=data)
    hook = next(i for i in items if i.file_name == "hook.py")
    assert hook.status == "update" and hook.local_name == "hook.py"
    script_share.download([hook], folder, tok="T", api=repo, data_dir=data)
    assert (folder / "hook.py").read_text() == "NAME = 'Wall hook 2'\n"

    (folder / "hook.py").write_text("NAME = 'Wall hook, my way'\n")        # the user changes their copy
    assert "hook.py" in {p.name for p in script_share.pending(folder, data)}   # now it is theirs: shared
    repo.files["scripts/lisa-a1b2c3/hook.py"] = b"NAME = 'Wall hook 3'\n"
    hook = next(i for i in script_share.list_remote(folder, tok="T", api=repo, data_dir=data) if i.file_name == "hook.py")
    [new] = script_share.download([hook], folder, tok="T", api=repo, data_dir=data)
    assert (folder / "hook.py").read_text() == "NAME = 'Wall hook, my way'\n" and new.name == "hook_lisa.py"


def test_get_scripts_window_lists_ticks_and_fetches(tmp_path, qtbot=None):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from omacad.ui.shared_scripts_dialog import GetScriptsDialog
    app = QApplication.instance() or QApplication([])
    folder, data = setup(tmp_path)
    repo = repo_for(data)
    dlg = GetScriptsDialog(None, folder, list_fn=lambda: script_share.list_remote(folder, tok="T", api=repo, data_dir=data),
                           download_fn=lambda items: script_share.download(items, folder, tok="T", api=repo, data_dir=data))
    for _ in range(200):
        app.processEvents()
        if dlg.list.count():
            break
        import time
        time.sleep(0.01)
    assert dlg.list.count() == 2 and not dlg.btn_get.isEnabled()
    assert dlg.list.item(0).text().startswith("Olle bracket")          # sorted by name
    dlg.list.setCurrentRow(1)
    assert dlg.lbl_title.text() == "Wall hook" and "lisa" in dlg.lbl_by.text() and dlg.lbl_desc.text() == "A hook"
    dlg.list.item(1).setCheckState(Qt.CheckState.Checked)
    assert dlg.btn_get.isEnabled()
    dlg._get()
    assert (folder / "hook.py").exists() and not (folder / "bracket.py").exists()
    assert [p.name for p in dlg.fetched] == ["hook.py"]
    dlg.close()


def test_get_scripts_window_says_why_when_it_cannot_load(tmp_path):
    from PySide6.QtWidgets import QApplication
    from omacad.ui.shared_scripts_dialog import GetScriptsDialog
    app = QApplication.instance() or QApplication([])

    def fail():
        raise RuntimeError("No GitHub token is set")

    dlg = GetScriptsDialog(None, tmp_path, list_fn=fail, download_fn=lambda items: [])
    import time
    for _ in range(200):
        app.processEvents()
        if "Could not" in dlg.lbl_status.text():
            break
        time.sleep(0.01)
    assert "No GitHub token" in dlg.lbl_status.text()
    dlg.close()
