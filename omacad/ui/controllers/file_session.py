"""File handling mixin for MainWindow: "unsaved changes?" questions and the Open Recent list.

A document counts as changed when its saved form differs from the form it had when it was opened or last saved
(`_clean_state`), so view-only things like selection or camera never trigger the question.
"""

import json
from typing import Optional
import numpy as np
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QFileDialog

from omacad import busy
from omacad.io.exporter import Exporter
from omacad.model.document import Document

RECENT_LIMIT = 10


class FileSessionMixin:

    # ---- unsaved changes ----------------------------------------------------

    @staticmethod
    def _state_of(doc: Document) -> str:
        return json.dumps(Exporter.document_to_dict(doc), sort_keys=True, default=str)

    def mark_clean(self, baseline: str = None) -> None:
        """The current document is what is on disk (or `baseline` says what the clean state looks like)."""
        self._clean_state = baseline if baseline is not None else self._state_of(self.doc)

    def is_dirty(self) -> bool:
        clean = getattr(self, "_clean_state", None)
        if clean is None:                   # nothing opened or saved yet: clean means an empty design
            clean = self._state_of(Document())
        return self._state_of(self.doc) != clean

    def _ask_save_changes(self, name: str) -> str:
        """'save', 'discard' or 'cancel'."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"Do you want to save the changes to {name}?")
        box.setInformativeText("If you don't save, your changes will be lost.")
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        return "save" if clicked is save else "discard" if clicked is discard else "cancel"

    def confirm_discard_changes(self) -> bool:
        """True when it is fine to replace the current document: nothing changed, saved now, or discarded on purpose."""
        if not self.is_dirty():
            return True
        name = Path(self.current_path).name if self.current_path else (self.doc.name or "Untitled")
        answer = self._ask_save_changes(name)
        if answer == "cancel":
            return False
        if answer == "save":
            self.on_file_save()
            return not self.is_dirty()      # a cancelled Save As or a failed write keeps everything as it was
        return True

    def closeEvent(self, event):
        # a restart has saved the session already and the new process resumes it: no question
        if getattr(self, "_restarting", False) or self.confirm_discard_changes():
            if getattr(self, "_autosave", None) is not None:
                self._autosave.release()        # closed normally: nothing to recover next time
            event.accept()
        else:
            event.ignore()

    # ---- autosave -----------------------------------------------------------

    def start_autosave(self, check_ms: int = 30000, folder=None) -> None:
        """Write unsaved work to a recovery file every `autosave_minutes` (Settings > General; 0 = off)."""
        import time
        from omacad import autosave
        self._autosave = autosave.Autosave(folder or autosave.AUTOSAVE_DIR)
        self._autosave_at = time.monotonic()
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self.autosave_now)
        self._autosave_timer.start(check_ms)

    def autosave_now(self, force: bool = False) -> None:
        """Called by the timer; `force` writes at once (e.g. right after resuming)."""
        if busy.active():       # the document is half built; the next tick saves it
            return
        import time
        from omacad import applog, autosave
        from omacad.ui.settings import get_settings
        auto = getattr(self, "_autosave", None)
        if auto is None:
            return
        minutes = get_settings().get("autosave_minutes", autosave.DEFAULT_MINUTES)
        try:
            minutes = float(minutes)
        except (TypeError, ValueError):
            minutes = autosave.DEFAULT_MINUTES
        if not force and (minutes <= 0 or time.monotonic() - self._autosave_at < minutes * 60):
            return
        self._autosave_at = time.monotonic()
        state = self._state_of(self.doc)
        clean = getattr(self, "_clean_state", None) or self._state_of(Document())
        if state == clean:
            auto.clear()                        # everything is on disk already
            return
        if state == auto.last_state:
            return
        try:
            auto.write(self.doc, self.current_path, self._camera_state())
            auto.last_state = state
        except (OSError, TypeError, ValueError) as e:
            applog.log("ERROR", f"autosave failed: {e}")
            self.status_label.setText(f"Autosave failed: {e}")

    def _forget_autosave(self) -> None:
        if getattr(self, "_autosave", None) is not None:
            self._autosave.clear()

    def offer_autosave_resume(self) -> bool:
        """After a crash: offer the newest recovery file another Omacad left behind. Returns whether it was resumed."""
        import datetime
        from omacad import autosave
        own = self._autosave.file if getattr(self, "_autosave", None) is not None else None
        files = autosave.orphans(self._autosave.folder if own else autosave.AUTOSAVE_DIR, own)
        if not files:
            return False
        file = files[0]
        data = autosave.load(file)
        if not data or "document" not in data:
            autosave.discard(file)
            return False
        name = Path(data["path"]).name if data.get("path") else (data["document"].get("name") or "Untitled")
        when = datetime.datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        answer = self._ask_resume_autosave(name, when)
        if answer == "resume":
            self._restore_state(data, f"Resumed autosaved work ({name}, {when}). Save it to keep it.")
            autosave.discard(file)
            self.autosave_now(force=True)       # the recovered work is protected again right away
            return True
        if answer == "discard":
            autosave.discard(file)
        return False

    def _ask_resume_autosave(self, name: str, when: str) -> str:
        """'resume', 'discard' or 'later' (keep the file and ask again next start)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Resume autosave")
        box.setText(f"Omacad did not close normally. Resume the autosaved work on {name}?")
        box.setInformativeText(f"Autosaved {when}.")
        resume = box.addButton("Resume", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(resume)
        box.exec()
        clicked = box.clickedButton()
        return "resume" if clicked is resume else "discard" if clicked is discard else "later"

    # ---- recent files -------------------------------------------------------

    def recent_files(self) -> list:
        from omacad.ui.settings import get_settings
        return [p for p in get_settings().get("recent_files", []) if isinstance(p, str)]

    def add_recent_file(self, path: str) -> None:
        from omacad.ui.settings import get_settings
        path = str(Path(path).resolve())
        files = [path] + [p for p in self.recent_files() if p != path]
        get_settings().set("recent_files", files[:RECENT_LIMIT])
        self.rebuild_recent_menu()

    def forget_recent_file(self, path: str) -> None:
        from omacad.ui.settings import get_settings
        get_settings().set("recent_files", [p for p in self.recent_files() if p != path])
        self.rebuild_recent_menu()

    def clear_recent_files(self) -> None:
        from omacad.ui.settings import get_settings
        get_settings().set("recent_files", [])
        self.rebuild_recent_menu()

    def rebuild_recent_menu(self) -> None:
        menu = getattr(self, "menu_recent", None)
        if menu is None:
            return
        menu.clear()
        files = self.recent_files()
        for path in files:
            act = menu.addAction(f"{Path(path).name}    ({Path(path).parent})")
            act.setToolTip(path)
            act.triggered.connect(lambda _=False, p=path: self.open_recent(p))
        if not files:
            menu.addAction("(no recent files)").setEnabled(False)
        menu.addSeparator()
        clear = menu.addAction("Clear Recent Files")
        clear.setEnabled(bool(files))
        clear.triggered.connect(self.clear_recent_files)

    def open_recent(self, path: str) -> None:
        if not Path(path).exists():
            QMessageBox.warning(self, "Open Recent", f"{path}\n\nThe file no longer exists and is removed from the list.")
            self.forget_recent_file(path)
            return
        self.open_path(path)


    def attach_document(self, doc: Document, path: Optional[str] = None, clean: bool = True) -> None:
        """Make `doc` the document every panel shows (used by New and Open). `clean`: it equals what is on disk."""
        self.doc = doc
        self.current_path = path
        if clean:
            self.mark_clean()
        self.viewport.set_document(doc)
        self.inspector.doc = doc
        doc.add_change_listener(self.inspector.refresh_info)
        doc.add_change_listener(self.sync_sketch_status)
        doc.history_listeners.append(self._update_undo_actions)
        self._update_undo_actions()
        for panel, refresh in ((self.browser, "refresh_tree"), (self.timeline_bar, "refresh_timeline"),
                               (self.ribbon, "sync_active_tab")):
            panel.doc = doc
            doc.add_change_listener(getattr(panel, refresh))
        self.update_window_title()
        doc.notify_changed()

    def update_window_title(self):
        name = Path(self.current_path).name if getattr(self, "current_path", None) else (getattr(self.doc, "name", "Untitled") or "Untitled")
        from omacad import __version__
        self.setWindowTitle(f"{name} - Omacad Hybrid {__version__}")
        if hasattr(self, "lbl_doc_title") and self.lbl_doc_title:
            doc_display = f"📄  {name}" if getattr(self, "current_path", None) else f"📄  {name}*"
            self.lbl_doc_title.setText(doc_display)

    def on_file_new(self):
        if not self.confirm_discard_changes():
            return
        self._forget_autosave()
        self.attach_document(Document("Omacad - Untitled"))
        self.status_label.setText("Created new design.")

    def on_file_save(self):
        """Ctrl+S: save to the current file, or ask for a name the first time."""
        if getattr(self, "current_path", None):
            self._save_to(self.current_path)
        else:
            self.on_file_save_as()

    def on_file_save_as(self):
        start = self.current_path if getattr(self, "current_path", None) else f"{self.doc.name.replace('Omacad - ', '')}.omacad"
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Project As", start, "Omacad (*.omacad)")
        if filepath:
            if not filepath.endswith(".omacad"):
                filepath += ".omacad"
            self._save_to(filepath)

    def _save_to(self, filepath: str):
        if self.doc.active_sketch:
            self.on_finish_sketch()  # an unfinished sketch is not part of the history and would be lost
        try:
            self.doc.name = Path(filepath).stem
            Exporter.save_project(self.doc, filepath)
        except OSError as e:
            QMessageBox.critical(self, "Save failed", f"Could not save {filepath}:\n{e}")
            return
        self.current_path = filepath
        self.mark_clean()
        self._forget_autosave()
        self.add_recent_file(filepath)
        self.update_window_title()
        self.doc.notify_changed()
        self.status_label.setText(f"Saved {filepath}")

    def on_file_open(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Omacad (*.omacad *.om360)")
        if filepath:
            self.open_path(filepath)

    def open_path(self, filepath: str):
        """Open a project file, first asking what to do with unsaved changes (also from Open Recent)."""
        if not self.confirm_discard_changes():
            return
        try:
            doc = busy.run("Opening " + Path(filepath).name, lambda: Exporter.load_project(filepath))
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.critical(self, "Open failed", f"Could not open {filepath}:\n{e}")
            return
        self._forget_autosave()
        self.attach_document(doc, filepath)
        self.add_recent_file(filepath)
        self.viewport.zoom_fit()
        self.status_label.setText(f"Opened {filepath}")

    def on_export_all_stl(self):
        if not self.doc.bodies:
            QMessageBox.information(self, "Export STL", "No bodies to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(self, "Export All Bodies to STL", "", "STL Files (*.stl)")
        if filepath:
            if not filepath.endswith(".stl"):
                filepath += ".stl"
            ok = Exporter.export_all_to_stl(self.doc, filepath)
            if ok:
                QMessageBox.information(self, "Export STL", f"Successfully exported STL to:\n{filepath}")
                self.status_label.setText(f"Exported STL to {filepath}")

    def export_single_body_stl(self, body_id: str):
        body = self.doc.bodies.get(body_id)
        if not body:
            return

        filepath, _ = QFileDialog.getSaveFileName(self, f"Export {body.name} to STL", f"{body.name}.stl", "STL Files (*.stl)")
        if filepath:
            ok = Exporter.export_body_to_stl(body, filepath)
            if ok:
                QMessageBox.information(self, "Export STL", f"Successfully exported {body.name} to:\n{filepath}")

    def on_import_svg(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Import SVG Vector", "", "SVG Files (*.svg)")
        if not filepath:
            return
        try:
            sketch = Exporter.import_svg_to_sketch(filepath, self.doc)
            if sketch:
                self.viewport.zoom_fit()
                self.viewport.update()
                self.status_label.setText(f"Imported SVG curves from {Path(filepath).name} into {sketch.name} ({len(sketch.entities)} entities).")
            else:
                QMessageBox.warning(self, "Import SVG", "No usable paths or shapes found in SVG file.")
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Could not import {filepath}:\n{e}")

    def on_import_3mf(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Import 3MF Model", "", "3MF Files (*.3mf)")
        if not filepath:
            return
        try:
            bodies = Exporter.import_3mf(filepath, self.doc)
            if bodies:
                self.viewport.zoom_fit()
                names = ", ".join(b.name for b in bodies)
                self.status_label.setText(f"Imported {len(bodies)} body(s) from {Path(filepath).name}: {names}")
            else:
                QMessageBox.warning(self, "Import 3MF", "No 3D meshes found in 3MF archive.")
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Could not import {filepath}:\n{e}")

    def on_export_all_step(self):
        if not self.doc.bodies:
            QMessageBox.information(self, "Export STEP", "No bodies to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(self, "Export All Bodies to STEP", "", "STEP Files (*.step *.stp)")
        if filepath:
            if not (filepath.endswith(".step") or filepath.endswith(".stp")):
                filepath += ".step"
            ok = Exporter.export_all_to_step(self.doc, filepath)
            if ok:
                QMessageBox.information(self, "Export STEP", f"Successfully exported STEP to:\n{filepath}")
                self.status_label.setText(f"Exported STEP to {filepath}")

    def export_single_body_step(self, body_id: str):
        body = self.doc.bodies.get(body_id)
        if not body:
            return

        filepath, _ = QFileDialog.getSaveFileName(self, f"Export {body.name} to STEP", f"{body.name}.step", "STEP Files (*.step *.stp)")
        if filepath:
            if not (filepath.endswith(".step") or filepath.endswith(".stp")):
                filepath += ".step"
            ok = Exporter.export_body_to_step(body, filepath)
            if ok:
                QMessageBox.information(self, "Export STEP", f"Successfully exported {body.name} to:\n{filepath}")
                self.status_label.setText(f"Exported {body.name} to {filepath}")

    def start_restart_watch(self, interval_ms: int = 3000) -> None:
        """When the source tree gets a new commit (the agent finished a fix), save everything and restart on it."""
        from omacad import feedback, session
        self._code_root = feedback.repo_root()
        self._code_version = session.code_version(self._code_root)
        if self._code_version is None:
            return                                  # not a source checkout: nothing to watch
        self._restart_timer = QTimer(self)
        self._restart_timer.timeout.connect(self._check_code_version)
        self._restart_timer.start(interval_ms)

    def _check_code_version(self) -> None:
        if busy.active():       # a restart saves the document, which is half built; the next tick looks again
            return
        from PySide6.QtWidgets import QApplication
        from omacad import session
        from omacad.ui.settings import get_settings
        if not get_settings().get("auto_restart", True) or QApplication.activeModalWidget() is not None:
            return                                  # never pull the app away under an open dialog
        version = session.code_version(self._code_root)
        if version and version != self._code_version:
            self._restart_timer.stop()
            self.status_label.setText("New version committed: saving your work and restarting ...")
            QTimer.singleShot(1500, self.restart_app)

    def restart_app(self) -> None:
        """Saves the session and starts a fresh process that resumes it, then closes this one."""
        import sys
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication
        from omacad import applog, session
        try:
            session.save(self.doc, self.current_path, self._camera_state())
        except (OSError, TypeError, ValueError) as e:      # no restart if the work could not be saved
            applog.log("ERROR", f"restart cancelled, could not save the session: {e}")
            self.status_label.setText(f"Restart cancelled, could not save the session: {e}")
            self._restart_timer.start()
            return
        script = str(Path(self._code_root) / "app.py")
        if QProcess.startDetached(sys.executable, [script, session.RESUME_FLAG], str(self._code_root)):
            self._restarting = True
            QApplication.quit()
        else:
            applog.log("ERROR", "restart cancelled, could not start the new process")
            self.status_label.setText("Restart cancelled, could not start the new process.")
            self._restart_timer.start()

    def restore_session(self) -> bool:
        """Puts back what restart_app saved (document, sketch being edited, camera). Returns whether there was one."""
        from omacad import session
        data = session.load()
        if not data:
            return False
        self._restore_state(data, f"Restarted on Omacad {__import__('omacad').__version__}; your work is back.")
        return True

    def _camera_state(self) -> dict:
        v = self.viewport
        return {"azimuth": v.azimuth, "elevation": v.elevation, "distance": v.distance,
                "target": [float(x) for x in v.target]}

    def _restore_state(self, data: dict, message: str) -> None:
        """Document, open sketch and camera from a session or autosave file; unsaved compared to its own file."""
        doc = Document()
        Exporter.apply_dict(doc, data["document"])
        self.attach_document(doc, data.get("path"), clean=False)
        self.mark_clean(self._session_baseline(data.get("path")))
        cam = data.get("camera") or {}
        v = self.viewport
        v.azimuth = cam.get("azimuth", v.azimuth)
        v.elevation = cam.get("elevation", v.elevation)
        v.distance = cam.get("distance", v.distance)
        if "target" in cam:
            v.target = np.array(cam["target"], dtype=np.float32)
        v.update()
        self.status_label.setText(message)

    def _session_baseline(self, path: Optional[str]) -> str:
        """What "unchanged" means for a restored session: the file it was opened from, or an empty design."""
        try:
            if path and Path(path).exists():
                return self._state_of(Exporter.load_project(path))
        except (OSError, ValueError, KeyError):
            pass
        return self._state_of(Document())
