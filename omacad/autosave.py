"""Autosave: unsaved work is written to a recovery file every few minutes, and offered back when Omacad starts after a
crash or a power cut.

Every running Omacad writes its own file (`<pid>.json`) and holds a lock next to it (`<pid>.lock`, QLockFile). A file
whose lock can be taken belongs to a process that is gone without closing normally, so it is an orphan to offer.
Saving, closing normally or discarding on purpose removes the file; nothing is ever written over the user's own file.
"""
import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QLockFile

from omacad import applog, session
from omacad.hybrid_paths import DATA_DIR

AUTOSAVE_DIR = DATA_DIR / "autosave"
DEFAULT_MINUTES = 2


def _lock_for(file: Path) -> QLockFile:
    lock = QLockFile(str(file.with_suffix(".lock")))
    lock.setStaleLockTime(0)        # never stale by age: only a lock whose process has died is free
    return lock


class Autosave:
    """The recovery file of this process."""

    def __init__(self, folder: Path = AUTOSAVE_DIR):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.file = self.folder / f"{os.getpid()}.json"
        self._lock = _lock_for(self.file)
        if not self._lock.tryLock(0):
            applog.log("autosave", f"could not lock {self.file}")
        self.last_state: Optional[str] = None

    def write(self, doc, path: Optional[str], camera: dict) -> None:
        session.save(doc, path, camera, self.file)

    def clear(self) -> None:
        """The work is saved or given up on purpose: nothing to recover."""
        self.last_state = None
        try:
            self.file.unlink(missing_ok=True)
        except OSError as e:
            applog.log("ERROR", f"could not remove autosave {self.file}: {e}")

    def release(self) -> None:
        self.clear()
        self._lock.unlock()


def orphans(folder: Path = AUTOSAVE_DIR, own: Optional[Path] = None) -> List[Path]:
    """Recovery files left by Omacad processes that did not close normally, newest first."""
    found = []
    for file in Path(folder).glob("*.json"):
        if own is not None and file == own:
            continue
        lock = _lock_for(file)
        if lock.tryLock(0):          # its process is gone
            lock.unlock()
            found.append(file)
    return sorted(found, key=lambda f: f.stat().st_mtime, reverse=True)


def load(file: Path) -> Optional[dict]:
    return session.load(file)


def discard(file: Path) -> None:
    try:
        file.unlink(missing_ok=True)
        file.with_suffix(".lock").unlink(missing_ok=True)
    except OSError as e:
        applog.log("ERROR", f"could not remove autosave {file}: {e}")
