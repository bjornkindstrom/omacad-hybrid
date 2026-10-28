"""Restart with a new version without losing work: the document, the sketch being edited and the camera are saved to a
session file, the app starts again, and the new process puts everything back. `code_version` is what tells the running
app that the code on disk has moved on (a new commit, e.g. from the agent that fixed a reported problem)."""
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from omacad import applog

SESSION_FILE = Path.home() / ".local" / "share" / "omacad" / "session.json"
RESUME_FLAG = "--resume"


def code_version(root: Path) -> Optional[str]:
    """The commit the source tree is at, or None when it is not a git checkout (an installed or built copy)."""
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        applog.log("session", f"git rev-parse failed: {e}")
        return None
    return out.stdout.strip() or None


def save(doc, path: Optional[str], camera: dict, file: Path = SESSION_FILE) -> None:
    """Writes the whole state atomically, so an interrupted restart never leaves a half-written session."""
    from omacad.io.exporter import Exporter
    data = {"document": Exporter.document_to_dict(doc), "path": path, "camera": camera}
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, file)


def load(file: Path = SESSION_FILE) -> Optional[dict]:
    """The saved session, or None. The file is kept until the next save, so a crash right after the restart can resume again."""
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        applog.log("ERROR", f"unreadable session file {file}: {e}")
        return None
