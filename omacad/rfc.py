"""Request for change: the user describes a change or a new feature, and everything about the moment (screenshot, the
model, the log) is sent to a private GitHub repository, in a folder `request-for-change/<date>-<name>/`, plus an issue
labelled `request`. The owner reviews them later and approves the ones to build.

Only the standard library is used (urllib), so it works the same on Windows and Linux. A request that cannot be sent
(no token, no network) stays in the local folder and is sent the next time the app starts or a request is made.

The token (GitHub fine-grained token, Contents + Issues write on the requests repository only) comes from, in order:
the environment (OMACAD_RFC_TOKEN), the setting `rfc_token`, or the file `omacad/_rfc_secret.py` that the release build writes.
"""
import base64
import json
import hashlib
import threading
import urllib.parse
import os
import platform
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from omacad import __version__, applog

REPO = "bjornkindstrom/omacad-requests"
API = "https://api.github.com"
FOLDER = "request-for-change"
PENDING_MARK = "pending"
SENT_MARK = "sent.json"
ERROR_MARK = "last_error.json"
_SEND_LOCK = threading.Lock()


def requests_dir() -> Path:
    from omacad.hybrid_paths import DATA_DIR
    return DATA_DIR / "requests"


def token() -> str:
    t = os.environ.get("OMACAD_RFC_TOKEN", "").strip()
    if t:
        return t
    try:
        from omacad.ui.settings import get_settings
        t = str(get_settings().get("rfc_token") or "").strip()
        if t:
            return t
    except Exception:
        pass
    try:
        from omacad import _rfc_secret
        return str(getattr(_rfc_secret, "TOKEN", "") or "").strip()
    except Exception:
        return ""


def _slug(text: str, limit: int = 30) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].strip("-") or "anonymous"


def _api(method: str, path: str, data: Optional[dict], tok: str, timeout: int = 180) -> dict:
    """One GitHub REST call; returns the decoded JSON answer."""
    req = urllib.request.Request(API + path, method=method, headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": f"Omacad/{__version__}",
        "Content-Type": "application/json"}, data=json.dumps(data).encode("utf-8") if data is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body else {}


def build_request(doc, note: str, name: str, images: dict, extra: Optional[dict] = None, base_dir: Optional[Path] = None) -> Path:
    """Writes the request folder (same content as a problem report, with REQUEST.md instead of an agent prompt)."""
    from omacad import feedback
    folder = feedback.build_bundle(doc, note, images, extra, base_dir=Path(base_dir or requests_dir()))
    (folder / "PROMPT.md").unlink(missing_ok=True)          # that file is for the AI fixer, not for requests
    (folder / "REQUEST.md").write_text(
        f"# Request for change\n\n**From:** {name.strip() or 'anonymous'}  \n**Omacad:** {__version__}  \n"
        f"**System:** {platform.platform()}  \n**Sent:** {time.strftime('%Y-%m-%d %H:%M')}\n\n{note.strip()}\n", encoding="utf-8")
    (folder / "name.txt").write_text(name.strip(), encoding="utf-8")
    (folder / PENDING_MARK).write_text("not sent yet", encoding="utf-8")
    return folder


def send(folder: Path, tok: Optional[str] = None, api: Callable = _api) -> Tuple[bool, str]:
    """Uploads one request folder and opens its issue. Returns (ok, message). The folder keeps a `sent.json` afterwards."""
    with _SEND_LOCK:
        return _send(folder, tok, api)


def _send(folder: Path, tok: Optional[str], api: Callable) -> Tuple[bool, str]:
    if (folder / SENT_MARK).exists():
        (folder / PENDING_MARK).unlink(missing_ok=True)
        (folder / ERROR_MARK).unlink(missing_ok=True)
        return True, "Request already sent."
    tok = tok or token()
    if not tok:
        return False, "No GitHub token is set, so the request is saved here and will be sent later: " + str(folder)
    name = (folder / "name.txt").read_text(encoding="utf-8").strip() if (folder / "name.txt").exists() else ""
    remote = f"{FOLDER}/{folder.name}-{_slug(name)}"
    try:
        files: List[Path] = sorted(p for p in folder.iterdir() if p.is_file() and p.name not in (PENDING_MARK, SENT_MARK, ERROR_MARK, "sent.tmp", "name.txt", "document.json"))
        for p in files:                     # REQUEST.md first so the folder is readable even if the rest fails
            if p.name == "REQUEST.md":
                files.remove(p)
                files.insert(0, p)
                break
        for p in files:
            path = f"/repos/{REPO}/contents/{remote}/{p.name}"
            content = p.read_bytes()
            if p.suffix == ".omacad":
                # Project files are JSON. Omit indentation in transit without changing the model.
                content = json.dumps(json.loads(content), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            try:
                existing = api("GET", path, None, tok)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                existing = {}
            sha = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            if existing.get("sha") == sha:
                continue
            data = {"message": f"Request {folder.name}: {p.name}",
                    "content": base64.b64encode(content).decode("ascii")}
            if existing.get("sha"):
                data["sha"] = existing["sha"]
            api("PUT", path, data, tok)
        note = (folder / "REQUEST.md").read_text(encoding="utf-8")
        first = next((ln for ln in note.splitlines()[6:] if ln.strip()), "Request for change")
        query = urllib.parse.urlencode({"q": f'repo:{REPO} is:issue in:body "{remote}"'})
        matches = api("GET", "/search/issues?" + query, None, tok).get("items", [])
        issue = next((item for item in matches if remote in (item.get("body") or "")), None)
        if issue is None:
            issue = api("POST", f"/repos/{REPO}/issues", {
                "title": f"Request: {first[:80]}", "labels": ["request"],
                "body": f"{note}\n\n[Open the folder](https://github.com/{REPO}/tree/main/{remote})"}, tok)
        acknowledgement = folder / "sent.tmp"
        acknowledgement.write_text(json.dumps({"remote": remote, "issue": issue.get("html_url", "")}), encoding="utf-8")
        acknowledgement.replace(folder / SENT_MARK)
        (folder / PENDING_MARK).unlink(missing_ok=True)
        (folder / ERROR_MARK).unlink(missing_ok=True)
        applog.log("rfc", f"request sent: {remote}")
        return True, f"Request sent. Thank you! ({remote})"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:2000]
        _save_error(folder, f"HTTP {e.code} at {e.filename}: {e.reason}; {detail}")
        if e.code == 401:
            return False, f"GitHub rejected the token (HTTP 401). Update the GitHub token in Settings. Your request is saved: {folder}"
        return False, f"GitHub refused the request (HTTP {e.code}); it is saved and will be tried again: {folder}"
    except Exception as e:                  # no network, timeouts, DNS ...
        _save_error(folder, str(e))
        return False, f"Could not reach GitHub; the request is saved and will be sent later: {folder}"


def _save_error(folder: Path, message: str) -> None:
    applog.log("rfc", f"could not send {folder.name}: {message}")
    (folder / ERROR_MARK).write_text(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                               "error": message}), encoding="utf-8")


def send_pending(base_dir: Optional[Path] = None, api: Callable = _api, tok: Optional[str] = None, exclude: Optional[Path] = None) -> int:
    """Tries every request that was saved but not sent. Returns how many went out."""
    root = Path(base_dir or requests_dir())
    tok = tok or token()
    if not root.exists() or not tok:
        return 0
    done = 0
    for folder in sorted(root.iterdir()):
        if folder != exclude and (folder / PENDING_MARK).exists():
            ok, _ = send(folder, tok=tok, api=api)
            done += int(ok)
    return done
