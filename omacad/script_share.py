"""Shares the user's own scripts: every new or changed script in the local scripts folder is uploaded to the private
requests repository (the same one and the same token as Request a change, see `rfc.py`), in
`scripts/<name>-<install id>/<file>.py` (plus its `<stem>.png` picture when there is one).

Omacad's bundled examples, hidden files (`_x.py`, `.x.py`) and test reports are never sent. What was uploaded is
remembered as git blob hashes in `DATA_DIR/script_uploads.json`, so a script is sent again only when its content changes.
Only the standard library is used, so it works the same on Windows and Linux. Off with the setting `share_scripts`.

The other way, `list_remote` + `download` (Scripts > Get Scripts…) fetch scripts other people shared, only the ones
the user picks. A fetched script is remembered in the same state file (`downloaded`) and is not shared back unless the
user changes it.
"""
import base64
import hashlib
import json
import threading
import urllib.error
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from omacad import applog, rfc

FOLDER = "scripts"
STATE_FILE = "script_uploads.json"
INSTALL_ID_FILE = "install_id.txt"
PICTURE_SUFFIX = ".png"
_LOCK = threading.Lock()


def _data_dir() -> Path:
    from omacad.hybrid_paths import DATA_DIR
    return DATA_DIR


def install_id(data_dir: Optional[Path] = None) -> str:
    """A short random id for this installation, so two people with the same name (or none) don't overwrite each other."""
    path = Path(data_dir or _data_dir()) / INSTALL_ID_FILE
    try:
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    text = uuid.uuid4().hex[:6]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text


def remote_folder(name: str, data_dir: Optional[Path] = None) -> str:
    return f"{FOLDER}/{rfc._slug(name or '')}-{install_id(data_dir)}"


def blob_sha(content: bytes) -> str:
    """GitHub's sha for a file's content, so an unchanged file is recognised without downloading it."""
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


def _load_state(data_dir: Path) -> dict:
    try:
        data = json.loads((data_dir / STATE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(data_dir: Path, state: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = data_dir / (STATE_FILE + ".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(data_dir / STATE_FILE)


def shareable_files(folder: Path) -> List[Path]:
    """The user's own scripts in the folder and their pictures: no bundled examples, hidden files or test reports."""
    from omacad.scripting.folder import is_bundled
    out: List[Path] = []
    try:
        scripts = sorted(Path(folder).glob("*.py"), key=lambda p: p.name.lower())
    except OSError:
        return out
    for p in scripts:
        if p.name.startswith(("_", ".")) or not p.is_file() or is_bundled(p):
            continue
        out.append(p)
        pic = p.with_suffix(PICTURE_SUFFIX)
        if pic.is_file():
            out.append(pic)
    return out


def pending(folder: Path, data_dir: Optional[Path] = None) -> List[Path]:
    """Files that are new or changed since they were last uploaded. Cheap enough to call on the GUI thread."""
    data_dir = Path(data_dir or _data_dir())
    state = _load_state(data_dir)
    sent = state.get("files", {})
    todo = []
    for p in shareable_files(folder):
        try:
            if is_downloaded_unchanged(p, state=state):
                continue
            if sent.get(p.name) != blob_sha(p.read_bytes()):
                todo.append(p)
        except OSError:
            continue
    return todo


def upload(folder: Path, name: str, tok: Optional[str] = None, api: Callable = rfc._api,
           data_dir: Optional[Path] = None) -> Tuple[int, str]:
    """Uploads every new or changed script. Returns (how many files went up, message). Safe to call from a thread."""
    with _LOCK:
        return _upload(Path(folder), name, tok, api, Path(data_dir or _data_dir()))


def _upload(folder: Path, name: str, tok: Optional[str], api: Callable, data_dir: Path) -> Tuple[int, str]:
    tok = tok or rfc.token()
    if not tok:
        return 0, "No GitHub token is set; scripts are not shared."
    todo = pending(folder, data_dir)
    if not todo:
        return 0, "All scripts are already shared."
    state = _load_state(data_dir)
    sent = state.setdefault("files", {})
    remote = remote_folder(name, data_dir)
    done = 0
    try:
        for p in todo:
            content = p.read_bytes()
            sha = blob_sha(content)
            path = f"/repos/{rfc.REPO}/contents/{remote}/{p.name}"
            try:
                existing = api("GET", path, None, tok)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                existing = {}
            if existing.get("sha") != sha:
                data = {"message": f"Script from {name.strip() or 'anonymous'}: {p.name}",
                        "content": base64.b64encode(content).decode("ascii")}
                if existing.get("sha"):
                    data["sha"] = existing["sha"]
                api("PUT", path, data, tok)
                done += 1
            sent[p.name] = sha
            _save_state(data_dir, state)      # after each file, so a broken connection doesn't resend the rest
    except urllib.error.HTTPError as e:
        applog.log("scripts", f"script upload refused: HTTP {e.code} {e.reason}")
        if e.code == 401:
            return done, "GitHub rejected the token (HTTP 401); scripts will be shared when it is updated in Settings."
        return done, f"GitHub refused a script upload (HTTP {e.code}); it is tried again later."
    except Exception as e:                    # no network, timeouts, DNS ...
        applog.log("scripts", f"script upload failed: {e}")
        return done, "Could not reach GitHub; scripts are shared later."
    if done:
        applog.log("scripts", f"shared {done} script file(s) in {remote}")
    return done, f"Shared {done} script file(s) with Omacad." if done else "All scripts are already shared."


# ---- getting other people's scripts ("Get Scripts…") --------------------------------------------------------------
CACHE_DIR = "shared_scripts_cache"
BRANCH = "main"


@dataclass
class RemoteScript:
    """One script in the requests repository's `scripts/` folder."""
    path: str                       # "scripts/anna-1a2b3c/bracket.py"
    sha: str                        # git blob sha of the .py
    author: str                     # the folder's name without the install id ("anna")
    picture: Optional[str] = None   # repo path of `<stem>.png`, when there is one
    picture_sha: str = ""
    cached: Optional[Path] = None   # local copy of the .py (for its NAME / DESCRIPTION)
    picture_cached: Optional[Path] = None
    status: str = "new"             # "new", "have" (same content in the folder), "update" (newer than the one fetched)
    local_name: str = ""            # the file name it gets (or has) in the scripts folder

    @property
    def file_name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


def _author(folder_name: str) -> str:
    base, _, tail = folder_name.rpartition("-")
    return (base if base and len(tail) == 6 else folder_name).replace("-", " ") or "anonymous"


def _blob(sha: str, tok: str, api: Callable, data_dir: Path) -> bytes:
    """A file's content by its blob sha, from the local cache when it was fetched before."""
    cache = data_dir / CACHE_DIR / sha
    if cache.exists():
        return cache.read_bytes()
    raw = base64.b64decode(api("GET", f"/repos/{rfc.REPO}/git/blobs/{sha}", None, tok).get("content", ""))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(raw)
    return raw


def list_remote(folder: Path, tok: Optional[str] = None, api: Callable = rfc._api,
                data_dir: Optional[Path] = None) -> List[RemoteScript]:
    """Every script other installations shared, newest folder layout from one tree call; this installation's own
    folder is left out. Each .py is downloaded (once, cached by sha) so the list can show its name and description.
    Raises on no token / no network so the window can say why."""
    data_dir = Path(data_dir or _data_dir())
    tok = tok or rfc.token()
    if not tok:
        raise RuntimeError("No GitHub token is set (Settings > General).")
    tree = api("GET", f"/repos/{rfc.REPO}/git/trees/{BRANCH}?recursive=1", None, tok).get("tree", [])
    blobs = {t["path"]: t["sha"] for t in tree if t.get("type") == "blob" and str(t.get("path", "")).startswith(FOLDER + "/")}
    own = "-" + install_id(data_dir)
    fetched = _load_state(data_dir).get("downloaded", {})
    out: List[RemoteScript] = []
    for path, sha in sorted(blobs.items()):
        parts = path.split("/")
        if len(parts) != 3 or not parts[2].endswith(".py") or parts[2].startswith(("_", ".")) or parts[1].endswith(own):
            continue
        pic = path[:-3] + PICTURE_SUFFIX
        item = RemoteScript(path, sha, _author(parts[1]), pic if pic in blobs else None, blobs.get(pic, ""))
        item.cached = data_dir / CACHE_DIR / sha
        _blob(sha, tok, api, data_dir)
        if item.picture_sha:
            try:
                _blob(item.picture_sha, tok, api, data_dir)
                item.picture_cached = data_dir / CACHE_DIR / item.picture_sha
            except Exception:           # a missing picture never hides the script
                pass
        local_name, status = parts[2], "new"
        for name, rec in fetched.items():
            if rec.get("remote") == path:
                local_name = name
                status = "have" if rec.get("sha") == sha else "update"
                break
        else:
            target = Path(folder) / local_name
            if target.exists() and blob_sha(target.read_bytes()) == sha:
                status = "have"
        item.local_name, item.status = local_name, status
        out.append(item)
    return out


def _free_name(folder: Path, item: RemoteScript, fetched: dict) -> str:
    """The file name for a new download: its own name, or `<stem>_<author>.py` when the user already has another
    script with that name."""
    name = item.file_name
    if not (folder / name).exists() and name not in fetched:
        return name
    stem = name[:-3] + "_" + rfc._slug(item.author, 20).replace("-", "_")
    candidate, n = stem + ".py", 2
    while (folder / candidate).exists() and fetched.get(candidate, {}).get("remote") != item.path:
        candidate, n = f"{stem}_{n}.py", n + 1
    return candidate


def download(items: List[RemoteScript], folder: Path, tok: Optional[str] = None, api: Callable = rfc._api,
             data_dir: Optional[Path] = None) -> List[Path]:
    """Puts the chosen scripts (and their pictures) in the scripts folder and remembers where they came from, so they
    are not shared back and an update can be offered. An update replaces the file only if the user has not changed it;
    otherwise the new version is saved next to it. Returns the scripts written."""
    data_dir = Path(data_dir or _data_dir())
    folder = Path(folder)
    tok = tok or rfc.token()
    with _LOCK:
        state = _load_state(data_dir)
        fetched = state.setdefault("downloaded", {})
        written = []
        for item in items:
            content = _blob(item.sha, tok, api, data_dir)
            name = item.local_name if item.status == "update" else ""
            if name:
                old = folder / name
                if old.exists() and blob_sha(old.read_bytes()) != fetched.get(name, {}).get("sha"):
                    name = ""                    # the user changed their copy: keep it, save the update beside it
            if not name:
                name = _free_name(folder, item, fetched)
            target = folder / name
            target.write_bytes(content)
            if item.picture and item.picture_sha:
                target.with_suffix(PICTURE_SUFFIX).write_bytes(_blob(item.picture_sha, tok, api, data_dir))
            fetched[name] = {"remote": item.path, "sha": item.sha, "picture_sha": item.picture_sha}
            written.append(target)
        _save_state(data_dir, state)
    return written


def is_downloaded_unchanged(path: Path, data_dir: Optional[Path] = None, state: Optional[dict] = None) -> bool:
    """True for a script (or its picture) fetched from someone else and not changed since: it is not shared back."""
    state = _load_state(Path(data_dir or _data_dir())) if state is None else state
    fetched = state.get("downloaded", {})
    path = Path(path)
    rec = fetched.get(path.with_suffix(".py").name)
    if not rec:
        return False
    try:
        sha = blob_sha(path.read_bytes())
    except OSError:
        return False
    return sha == (rec.get("sha") if path.suffix == ".py" else rec.get("picture_sha"))
