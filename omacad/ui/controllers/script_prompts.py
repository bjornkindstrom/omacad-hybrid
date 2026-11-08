"""Scripts in the main window: Scripts… (Shift+S), New Script with AI…, Open Scripts Folder, and running a script."""
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from omacad import applog


class ScriptPromptsMixin:

    # ---- folder and watcher ---------------------------------------------------------------------------------------
    def scripts_folder(self) -> Path:
        from omacad.scripting.folder import resolve_folder
        from omacad.ui.settings import get_settings
        try:
            return resolve_folder(get_settings().get("scripts_folder") or "")
        except OSError as e:          # a folder that can't be made (a removed drive): fall back to the default
            applog.log("scripts", f"scripts folder unusable ({e}); using the default")
            return resolve_folder("")

    @property
    def script_watcher(self):
        from omacad.ui.scripts_ui import ScriptWatcher
        folder = self.scripts_folder()
        if getattr(self, "_script_watcher", None) is None:
            self._script_watcher = ScriptWatcher(folder, self)
            self._script_watcher.checked.connect(self._on_script_checked)
        else:
            self._script_watcher.set_folder(folder)
        return self._script_watcher

    def on_script_command(self, kind: str) -> None:
        {"run": self.show_scripts, "ai": self.prompt_new_script_ai, "folder": self.open_scripts_folder}.get(
            kind, self.show_scripts)()

    def open_scripts_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.scripts_folder())))

    # ---- Scripts window -------------------------------------------------------------------------------------------
    def show_scripts(self) -> None:
        from omacad.ui.scripts_ui import ScriptsDialog
        dlg = ScriptsDialog(self, self.script_watcher)
        dlg.exec()
        dlg.deleteLater()
        if dlg.action == "run" and dlg.chosen is not None:
            self.run_user_script(dlg.chosen)
        elif dlg.action == "modify" and dlg.chosen is not None:
            from omacad.scripting.loader import read_info
            self.prompt_modify_script(read_info(dlg.chosen).family, dlg.chosen)
        elif dlg.action == "ai":
            self.prompt_new_script_ai()

    def family_scripts(self, family: str) -> list:
        """Scripts that are versions of a built-in tool (its submenu)."""
        from omacad.scripting.folder import family_scripts
        return family_scripts(self.scripts_folder(), family)

    def confirm_script_trust(self, path) -> bool:
        """Scripts are Python and can do anything on the computer: ask once per new or changed script."""
        from omacad.scripting.folder import is_trusted, trust
        from omacad.ui.settings import get_settings
        settings = get_settings()
        trusted = dict(settings.get("trusted_scripts") or {})
        if is_trusted(trusted, path):
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Run this script?")
        box.setText(f"“{Path(path).name}” is new or has changed since you last ran it.")
        box.setInformativeText("Scripts are Python programs and can do anything on your computer. Only run scripts "
                               "you wrote, asked an AI to write, or otherwise trust.")
        run = box.addButton("Run", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(run)
        box.exec()
        if box.clickedButton() is not run:
            return False
        settings.set("trusted_scripts", trust(trusted, path))
        return True

    def manage_user_script(self, what: str, path: str) -> None:
        """Right-click on a script in a menu: rename, modify (with AI, a copy) or delete it."""
        if what == "rename":
            self.rename_user_script(path)
        elif what == "delete":
            self.delete_user_script(path)
        elif what == "modify":
            from omacad.scripting.loader import read_info
            self.prompt_modify_script(read_info(Path(path)).family, base=path)

    def rename_user_script(self, path, new_name: Optional[str] = None) -> bool:
        """Rename… (right-click in a menu or in Scripts): sets the name the menus show; the file stays. A script the user
        trusted stays trusted (only its NAME line changed, by Omacad)."""
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        from omacad.scripting.folder import is_trusted, rename_script, trust
        from omacad.scripting.loader import read_info
        from omacad.ui.settings import get_settings
        path = Path(path)
        if new_name is None:
            text, ok = QInputDialog.getText(self, "Rename Script", "Name shown in the menus:", QLineEdit.EchoMode.Normal,
                                            read_info(path).name)
            if not ok:
                return False
            new_name = text
        if not " ".join(str(new_name).split()):
            return False
        settings = get_settings()
        trusted = dict(settings.get("trusted_scripts") or {})
        was_trusted = is_trusted(trusted, path)
        try:
            rename_script(path, new_name)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Rename Script", f"The script could not be renamed: {e}")
            return False
        if was_trusted:
            settings.set("trusted_scripts", trust(trusted, path))
        self.status_label.setText(f"Renamed {path.name} to “{read_info(path).name}”.")
        return True

    def delete_user_script(self, path, confirm: bool = True) -> bool:
        """Delete… for the user's own scripts (Omacad's own can't be deleted): to the trash after a question."""
        from omacad.scripting.folder import delete_script, is_own
        from omacad.scripting.loader import read_info
        from omacad.ui.settings import get_settings
        path = Path(path)
        if not is_own(path):
            QMessageBox.information(self, "Delete Script", "This is one of Omacad's own scripts and can't be deleted. "
                                    "Rename it or make a changed copy with Modify with AI… instead.")
            return False
        if confirm:
            answer = QMessageBox.question(self, "Delete Script", f"Delete “{read_info(path).name}” ({path.name})?\n"
                                          "It goes to the trash where the system has one.",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                          QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                return False
        try:
            gone = delete_script(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Delete Script", f"The script could not be deleted: {e}")
            return False
        settings = get_settings()
        key = str(path.resolve())
        for setting in ("trusted_scripts", "script_values"):
            entries = dict(settings.get(setting) or {})
            if entries.pop(key, None) is not None:
                settings.set(setting, entries)
        self.status_label.setText(f"Deleted {path.name}.")
        return gone

    def run_user_script(self, path, values: Optional[dict] = None, name: Optional[str] = None) -> bool:
        """Asks for the name of what it makes and the script's values, then runs it on the model as one undo step.
        With `values` given the panel is skipped."""
        from omacad.scripting.loader import read_info, resolve_values
        from omacad.scripting.runner import ScriptRunError, run_script
        from omacad.ui.scripts_ui import ScriptParamsDialog
        from omacad.ui.settings import get_settings
        path = Path(path)
        info = read_info(path)
        if info.error:
            self._show_script_error(info.name, path, f"RESULT: FAILED\nError: {info.error}", info.error)
            return False
        if not self.confirm_script_trust(path):
            return False
        settings = get_settings()
        saved = dict(settings.get("script_values") or {})
        key = str(path.resolve())
        last = dict(saved.get(key) or {})
        if values is None:
            values = resolve_values(info.params, last)
            dlg = ScriptParamsDialog(info, values, self, name=last.get("__name__", ""))
            self._script_preview(dlg, path)
            ok = dlg.exec()
            self.viewport.set_preview(None)
            self.viewport.update()
            if not ok:
                return False
            values, name = dlg.values(), dlg.name()
        name = (name or "").strip() or last.get("__name__") or info.default_name
        saved[key] = dict(values, __name__=name)
        settings.set("script_values", saved)
        if self.doc.active_sketch is not None:
            self.on_finish_sketch()
        had_bodies = bool(self.doc.bodies)
        try:
            res = run_script(self.doc, path, values, log=lambda m: applog.log("script", m), name=name)
        except ScriptRunError as e:
            r = e.result
            report = f"RESULT: FAILED\nScript name: {r.name}\nError: {r.error}\nValues used: {r.values}\n\n{r.details}"
            self._show_script_error(r.name, path, report, r.error)
            return False
        if not had_bodies and self.doc.bodies:
            self.viewport.zoom_fit()
        note = f"Script “{res.name}” done ({res.seconds:.1f} s) — Ctrl+Z undoes it."
        if res.messages:
            note += "  " + " · ".join(res.messages[-3:])
        self.status_label.setText(note)
        return True

    def _script_preview(self, dlg, path: Path) -> None:
        """Live preview while the values are set: the script runs on a private document after each change."""
        from omacad.scripting.runner import ScriptRunError, preview_solid

        done = []
        dlg.finished.connect(lambda *_: done.append(True))

        def refresh():
            if done:
                return
            try:
                values, name = dlg.values(), dlg.name()
            except RuntimeError:         # the panel is already closed
                return
            try:
                solid = preview_solid(path, values, name)
                dlg.lbl_problem.setText("" if solid is not None else "Preview: the script makes nothing new.")
            except ScriptRunError as e:
                r = e.result
                solid = None
                where = f" (line {r.line})" if r.line else ""
                dlg.lbl_problem.setText(f"Preview: {r.error}{where}")
            except Exception as e:      # never let a preview break the panel
                solid = None
                dlg.lbl_problem.setText(f"Preview: {e}")
            self.viewport.set_preview(solid)
            self.viewport.update()

        self._connect_debounced_preview(dlg, refresh, interval_ms=150)
        QTimer.singleShot(0, dlg, refresh)      # dropped if the panel is gone first

    def _show_script_error(self, name: str, path: Path, report: str, short: str) -> None:
        from omacad.scripting.prompt import error_for_ai
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Script failed")
        box.setText(f"“{name}” stopped with an error; the model is unchanged.")
        box.setInformativeText(short)
        box.setDetailedText(report)
        copy = box.addButton("Copy error for AI", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is copy:
            QApplication.clipboard().setText(error_for_ai(Path(path).name, report))
            self.status_label.setText("Error copied: paste it into the AI chat to get a fixed script.")

    # ---- New Script with AI ---------------------------------------------------------------------------------------
    def _agent_name(self) -> Optional[str]:
        """The name of the AI agent New Script with AI would start, or None if none can be started here."""
        from omacad import feedback
        from omacad.ui.settings import get_settings
        choice = get_settings().get("ai_agent", "omarchy")
        if feedback.agent_command_for_text("x", choice) is None:
            return None
        names = dict(feedback.available_agents())
        return names.get(choice) or names.get("omarchy")

    def prompt_new_script_ai(self) -> None:
        from omacad import feedback
        from omacad.scripting.prompt import agent_instruction, build_prompt, write_agent_prompt
        from omacad.ui.scripts_ui import AiScriptDialog
        folder = self.scripts_folder()
        dlg = AiScriptDialog(self, folder, self._agent_name(), grab_view=self.viewport.grabFramebuffer)
        if not dlg.exec():
            return
        wish, name = dlg.wish(), dlg.file_name()
        images = self._save_ai_images(dlg, folder, name)
        watcher = self.script_watcher
        if dlg.mode == "agent":
            prompt = write_agent_prompt(wish, folder, name, images=images)
            if feedback.launch_agent_text(agent_instruction(prompt), folder):
                watcher.arm()
                self.status_label.setText(f"The AI agent is writing {name}. Omacad tests it as soon as it is saved; "
                                          "then it is under Scripts (Shift+S).")
                return
            QMessageBox.warning(self, "No AI agent", "The AI agent could not be started. The instructions are copied "
                                "instead: paste them into an AI chat.")
        QApplication.clipboard().setText(build_prompt(wish, folder, name, for_agent=False, images=images))
        watcher.arm()
        self._copied_box("The instructions for the AI are on the clipboard.",
                         f"Save the script it answers with as a .py file (e.g. {name}) in the scripts folder.\n3. Omacad "
                         "tests it right away; if it fails, open Scripts (Shift+S) and use “Copy error for AI”.", images)

    def _save_ai_images(self, dlg, folder: Path, name: str) -> list:
        from omacad.scripting.folder import save_images
        try:
            return save_images(dlg.images(), folder, name)
        except OSError as e:
            QMessageBox.warning(self, "Pictures", f"The pictures could not be saved for the AI: {e}")
            return []

    def _copied_box(self, text: str, steps: str, images: list) -> None:
        """After the instructions went to the clipboard: what to do in the web chat (attach the pictures too)."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        box = QMessageBox(self)
        box.setWindowTitle("Instructions copied")
        box.setText(text)
        pics = (f" and attach the {len(images)} picture{'s' if len(images) > 1 else ''} (button below opens their folder)"
                if images else "")
        box.setInformativeText(f"1. Paste them into an AI chat (ChatGPT, Claude …){pics}.\n2. {steps}")
        pic_btn = box.addButton("Open Pictures", QMessageBox.ButtonRole.ActionRole) if images else None
        open_btn = box.addButton("Open Scripts Folder", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if pic_btn is not None and box.clickedButton() is pic_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(images[0].parent)))
        elif box.clickedButton() is open_btn:
            self.open_scripts_folder()

    def prompt_modify_script(self, family: str = "", base=None) -> None:
        """Modify with AI…: copy a script (a tool's script or the one picked), let an AI change the copy."""
        from omacad import feedback
        from omacad.scripting.folder import family_scripts, list_scripts
        from omacad.scripting.prompt import agent_instruction, build_modify_prompt, make_copy, write_agent_prompt
        from omacad.ui.scripts_ui import AiScriptDialog
        folder = self.scripts_folder()
        bases = family_scripts(folder, family) if family else [i for i in list_scripts(folder) if not i.error]
        if not bases:
            QMessageBox.information(self, "Modify with AI", "There is no script to start from in the scripts folder "
                                    "(it may have been deleted). Open Scripts to see what is there.")
            return
        dlg = AiScriptDialog(self, folder, self._agent_name(), bases=bases, base=Path(base) if base else None,
                             grab_view=self.viewport.grabFramebuffer)
        if not dlg.exec():
            return
        wish, name, src = dlg.wish(), dlg.file_name(), dlg.base()
        images = self._save_ai_images(dlg, folder, name)
        watcher = self.script_watcher
        if dlg.mode == "agent":
            target = make_copy(src, folder, name, wish)
            prompt = write_agent_prompt(wish, folder, name,
                                        text=build_modify_prompt(wish, folder, src, target, True, images=images))
            if feedback.launch_agent_text(agent_instruction(prompt), folder):
                watcher.arm()
                watcher.check(str(target))           # the unchanged copy works: shows up as tested at once
                self.status_label.setText(f"The AI agent is changing {target.name} (a copy of {src.name}). Omacad "
                                          "tests every saved version; the copy is in the tool's menu.")
                return
            target.unlink(missing_ok=True)
            QMessageBox.warning(self, "No AI agent", "The AI agent could not be started. The instructions are copied "
                                "instead: paste them into an AI chat.")
        QApplication.clipboard().setText(build_modify_prompt(wish, folder, src, folder / name, False, images=images))
        watcher.arm()
        self._copied_box("The instructions for the AI, with the whole script, are on the clipboard.",
                         f"Save the script it answers with as {name} in the scripts folder.\n3. Omacad tests it right "
                         "away; it appears in the tool's menu. If it fails, open Scripts (Shift+S) and use “Copy error "
                         "for AI”.", images)

    def _on_script_checked(self, path: str, ok: bool, report: str) -> None:
        from omacad.ui.scripts_ui import report_error_line
        name = Path(path).name
        if ok:
            self.status_label.setText(f"{name}: test OK — run it from Scripts (Shift+S).")
        else:
            self.status_label.setText(f"{name}: test failed ({report_error_line(report)}). The AI agent reads the "
                                      "report; with a web chat use Scripts › Copy error for AI.")
        applog.log("scripts", f"check {name}: {'OK' if ok else 'FAILED'}")
