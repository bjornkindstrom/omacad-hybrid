"""Scripts UI: the folder watcher that test-runs AI-written scripts, the Scripts window (Shift+S), the panel that asks
for a script's values, and the "New Script with AI" dialog."""
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QObject, QProcess, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from omacad.scripting.folder import IMAGE_SUFFIXES, list_scripts, safe_file_name
from omacad.scripting.loader import Param, ScriptInfo
from omacad.scripting.runner import check_file_for
from omacad.ui.dialogs.base import BaseFeatureDialog

CHECK_TIMEOUT_MS = 120_000
POLL_MS = 1500


class ScriptWatcher(QObject):
    """Watches the scripts folder. After "New Script with AI" (arm()), every .py saved there is test-run in a separate
    process (`--check-script`), which writes `<script>.check.txt` for the AI; `checked` reports the result here."""

    scripts_changed = Signal()
    checked = Signal(str, bool, str)          # script path, ok, report

    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self.folder = Path(folder)
        self.armed_since: Optional[float] = None
        self.results: Dict[str, Tuple[bool, str]] = {}
        self._seen: Dict[str, float] = {}         # path -> mtime when last listed
        self._checked_mtime: Dict[str, float] = {}
        self._running: Dict[str, QProcess] = {}
        self._again: set = set()
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.poll)
        self._listeners = 0
        self._snapshot()

    # ---- watching -------------------------------------------------------------------------------------------------
    def set_folder(self, folder: Path) -> None:
        if Path(folder) != self.folder:
            self.folder = Path(folder)
            self._seen.clear()
            self.results.clear()
            self.scripts_changed.emit()

    def arm(self) -> None:
        """From now on (this session) every script saved after this moment is test-run automatically; the files as
        they are now are left alone."""
        if self.armed_since is None:
            self._checked_mtime.update(self._scripts())
        self.armed_since = time.time()
        self._snapshot()
        self._timer.start()

    def listen(self, on: bool) -> None:
        """A window showing the list wants refreshes while it is open."""
        self._listeners += 1 if on else -1
        if self._listeners > 0 or self.armed_since is not None:
            self._timer.start()
        else:
            self._timer.stop()

    def _scripts(self):
        try:
            return {str(p): p.stat().st_mtime for p in self.folder.glob("*.py") if not p.name.startswith((".", "_"))}
        except OSError:
            return {}

    def _snapshot(self):
        self._seen = self._scripts()

    def poll(self) -> None:
        now = self._scripts()
        if now != self._seen:
            self._seen = now
            self.scripts_changed.emit()
        if self.armed_since is None:
            return
        for path, mtime in now.items():
            if self._checked_mtime.get(path) != mtime:
                self._checked_mtime[path] = mtime
                self.check(path)

    # ---- test runs ------------------------------------------------------------------------------------------------
    def check(self, path: str) -> None:
        from omacad.scripting.prompt import check_command
        path = str(path)
        try:
            self._checked_mtime[path] = Path(path).stat().st_mtime    # the poll need not test this version again
        except OSError:
            pass
        if path in self._running:
            self._again.add(path)
            return
        out = check_file_for(path)
        cmd = check_command(path, out)
        proc = QProcess(self)
        proc.setWorkingDirectory(str(self.folder))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._running[path] = proc
        killer = QTimer(proc)
        killer.setSingleShot(True)
        killer.timeout.connect(proc.kill)
        proc.finished.connect(lambda code, _status, p=path, o=out, k=killer: self._done(p, o, code, k))
        proc.errorOccurred.connect(lambda e, p=path, o=out, k=killer: self._done(p, o, -1, k)
                                   if e == QProcess.ProcessError.FailedToStart else None)   # else finished follows
        proc.start(cmd[0], cmd[1:])
        killer.start(CHECK_TIMEOUT_MS)

    def _done(self, path: str, out: Path, code: int, killer: QTimer) -> None:
        proc = self._running.pop(path, None)
        if proc is None:
            return
        try:                                   # the window may be closing: the process object can already be gone
            killer.stop()
            output = bytes(proc.readAll()).decode("utf-8", "replace")
            proc.deleteLater()
        except RuntimeError:
            return
        try:
            report = Path(out).read_text(encoding="utf-8")
        except OSError:
            report = ""
        fresh = report and Path(out).stat().st_mtime >= Path(path).stat().st_mtime - 1 if Path(path).exists() else False
        if not fresh:
            report = (f"Omacad script check: {Path(path).name}\nRESULT: FAILED\nThe test run stopped without a report "
                      f"(exit code {code}; killed after {CHECK_TIMEOUT_MS // 1000} s if it hung).\n{output[-3000:]}")
            try:
                Path(out).write_text(report, encoding="utf-8")
            except OSError:
                pass
        ok = "RESULT: OK" in report
        self.results[path] = (ok, report)
        self.checked.emit(path, ok, report)
        if path in self._again:
            self._again.discard(path)
            self.check(path)

    def result_for(self, path) -> Optional[Tuple[bool, str]]:
        """The last result this session, else the .check.txt left next to the script if it is newer than the script."""
        path = str(path)
        if path in self.results:
            return self.results[path]
        cf = check_file_for(path)
        try:
            if cf.stat().st_mtime >= Path(path).stat().st_mtime:
                report = cf.read_text(encoding="utf-8")
                return "RESULT: OK" in report, report
        except OSError:
            pass
        return None

    def running(self, path) -> bool:
        return str(path) in self._running


def report_error_line(report: str) -> str:
    for line in report.splitlines():
        if line.startswith("Error:"):
            return line[6:].strip()
    return "see the report"


class ScriptsDialog(QDialog):
    """Scripts (Shift+S): the scripts in the folder, what each does, its last test result, and Run / Test / Edit."""

    def __init__(self, window, watcher: ScriptWatcher):
        super().__init__(window)
        self.window_ = window
        self.watcher = watcher
        self.chosen: Optional[Path] = None
        self.action = ""                       # "run" or "ai" when the dialog closes with a request
        self.setWindowTitle("Scripts")
        self.resize(720, 440)
        lay = QVBoxLayout(self)
        intro = QLabel(f"Your scripts in <a href='folder'>{watcher.folder}</a>. Pick one and press Run; right-click "
                       "it to rename or delete it.")
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.linkActivated.connect(lambda _l: window.open_scripts_folder())
        intro.setWordWrap(True)
        lay.addWidget(intro)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(230)
        self.list.currentItemChanged.connect(lambda *_: self._show())
        self.list.itemDoubleClicked.connect(lambda *_: self._run())
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        body.addWidget(self.list)
        right = QVBoxLayout()
        self.lbl_title = QLabel()
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.lbl_file = QLabel()
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.lbl_image.hide()
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.lbl_params = QLabel()
        self.lbl_params.setWordWrap(True)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for w in (self.lbl_title, self.lbl_file, self.lbl_image, self.lbl_desc, self.lbl_params, self.lbl_status):
            right.addWidget(w)
        right.addStretch()
        body.addLayout(right, 1)
        lay.addLayout(body, 1)

        row = QHBoxLayout()
        self.btn_ai = QPushButton("New Script with AI…")
        self.btn_ai.clicked.connect(self._ai)
        self.btn_folder = QPushButton("Open Folder")
        self.btn_folder.clicked.connect(window.open_scripts_folder)
        self.btn_get = QPushButton("Get Scripts…")
        self.btn_get.setToolTip("Scripts other Omacad users shared: pick the ones you want")
        self.btn_get.clicked.connect(self._get_scripts)
        row.addWidget(self.btn_ai)
        row.addWidget(self.btn_get)
        row.addWidget(self.btn_folder)
        row.addStretch()
        self.btn_modify = QPushButton("Modify with AI…")
        self.btn_modify.setToolTip("An AI makes a changed copy of the selected script (the original stays as it is)")
        self.btn_modify.clicked.connect(self._modify)
        row.addWidget(self.btn_modify)
        self.btn_copy = QPushButton("Copy error for AI")
        self.btn_copy.setToolTip("Copies the test report so you can paste it into the AI chat and get a fixed script")
        self.btn_copy.clicked.connect(self._copy_error)
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self._edit)
        self.btn_pic = QPushButton("Create Picture")
        self.btn_pic.setToolTip("Renders a 3D illustration picture of this script for its explanation")
        self.btn_pic.clicked.connect(self._create_picture)
        self.btn_test = QPushButton("Test")
        self.btn_test.setToolTip("Test-run the script on an empty model with its default values")
        self.btn_test.clicked.connect(self._test)
        self.btn_easy = QPushButton("Easy")
        self.btn_easy.setToolTip("Open directly in Easy mode")
        self.btn_easy.clicked.connect(lambda: self._run("easy"))
        self.btn_run = QPushButton("Run")
        self.btn_run.setDefault(True)
        self.btn_run.clicked.connect(self._run)
        btn_close = QPushButton("Close")
        btn_close.setAutoDefault(False)
        btn_close.clicked.connect(self.reject)
        for b in (self.btn_copy, self.btn_edit, self.btn_pic, self.btn_test, self.btn_run, self.btn_easy, btn_close):
            row.addWidget(b)
        lay.addLayout(row)

        self._on_checked = lambda *_: self._show()
        watcher.scripts_changed.connect(self.refresh)
        watcher.checked.connect(self._on_checked)
        watcher.listen(True)
        self.finished.connect(lambda _r: self._stop_listening())
        self.refresh()

    def _stop_listening(self):
        for signal, slot in ((self.watcher.scripts_changed, self.refresh), (self.watcher.checked, self._on_checked)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self.watcher.listen(False)

    def refresh(self) -> None:
        current = self._info().path if self._info() else None
        self.infos = sorted(list_scripts(self.watcher.folder), key=lambda i: self._label(i).lower())
        self.list.clear()
        for info in self.infos:
            item = QListWidgetItem(self._mark(info) + self._label(info))
            item.setData(Qt.ItemDataRole.UserRole, str(info.path))
            item.setToolTip(info.description or info.path.name)
            self.list.addItem(item)
            if current is not None and info.path == current:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self._show()

    @staticmethod
    def _label(info: ScriptInfo) -> str:
        """The name, after its tool for scripts that are versions of a built-in tool (sorted together)."""
        from omacad.ui import commands, script_menus
        tool = next((c for c, f in script_menus.FAMILIES.items() if f == info.family), None)
        return f"{commands.label(tool)} › {info.name}" if tool else info.name

    def _mark(self, info: ScriptInfo) -> str:
        if info.error:
            return "⚠ "
        res = self.watcher.result_for(info.path)
        return "" if res is None else ("✓ " if res[0] else "✗ ")

    def _info(self) -> Optional[ScriptInfo]:
        item = self.list.currentItem() if hasattr(self, "list") else None
        if item is None:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        return next((i for i in getattr(self, "infos", []) if str(i.path) == path), None)

    def _show(self) -> None:
        info = self._info()
        has = info is not None
        for b in (self.btn_run, self.btn_easy, self.btn_test, self.btn_edit, self.btn_modify, self.btn_pic):
            b.setEnabled(has)
        self.btn_copy.setEnabled(False)
        if not has:
            self.lbl_title.setText("No scripts yet")
            self.lbl_file.setText("")
            self.lbl_image.clear()
            self.lbl_image.hide()
            self.lbl_desc.setText("Press “New Script with AI…” and describe a tool you want, or put a .py file in the folder.")
            self.lbl_params.setText("")
            self.lbl_status.setText("")
            return
        self.lbl_title.setText(info.name)
        self.lbl_file.setText(info.path.name)
        img_path = getattr(info, "image_path", None)
        if img_path and img_path.exists():
            pix = QPixmap(str(img_path))
            if not pix.isNull():
                scaled = pix.scaled(240, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.lbl_image.setPixmap(scaled)
                self.lbl_image.show()
            else:
                self.lbl_image.clear()
                self.lbl_image.hide()
        else:
            self.lbl_image.clear()
            self.lbl_image.hide()
        self.lbl_desc.setText(info.description)
        self.lbl_params.setText(("Values: " + ", ".join(p.title for p in info.params)) if info.params else "")
        if info.error:
            self.btn_run.setEnabled(False)
            self.btn_easy.setEnabled(False)
            self.btn_pic.setEnabled(False)
            self.lbl_status.setText(f"⚠ Can't run: {info.error}")
            self.btn_copy.setEnabled(True)
            return
        if self.watcher.running(info.path):
            self.lbl_status.setText("Testing…")
            return
        res = self.watcher.result_for(info.path)
        if res is None:
            self.lbl_status.setText("")
        elif res[0]:
            self.lbl_status.setText("✓ Last test: OK")
        else:
            self.lbl_status.setText(f"✗ Last test failed: {report_error_line(res[1])}")
            self.btn_copy.setEnabled(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            inf = next((x for x in self.infos if str(x.path) == item.data(Qt.ItemDataRole.UserRole)), None)
            if inf is not None:
                item.setText(self._mark(inf) + self._label(inf))

    def _context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        from omacad.scripting.folder import is_own
        item = self.list.itemAt(pos)
        if item is None:
            return
        self.list.setCurrentItem(item)
        info = self._info()
        menu = QMenu(self)
        easy = menu.addAction("Easy mode settings…")
        run = menu.addAction("Run")
        run.setEnabled(not info.error)
        rename = menu.addAction("Rename…  (F2)")
        modify = menu.addAction("Modify with AI…")
        pic = menu.addAction("Create Picture")
        pic.setEnabled(not info.error)
        pic.setToolTip("Renders a 3D illustration picture for this script's explanation")
        menu.addSeparator()
        delete = menu.addAction("Delete…  (Del)")
        delete.setEnabled(is_own(info.path))
        delete.setToolTip("" if is_own(info.path) else "Omacad's own scripts can't be deleted")
        menu.setToolTipsVisible(True)
        chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
        if chosen is easy:
            self.window_.manage_user_script("easy", str(info.path))
            self.refresh()
        elif chosen is run:
            self._run()
        elif chosen is pic:
            self._create_picture()
        elif chosen is rename:
            self._rename()
        elif chosen is modify:
            self._modify()
        elif chosen is delete:
            self._delete()

    def _get_scripts(self) -> None:
        from omacad.ui.shared_scripts_dialog import GetScriptsDialog
        dlg = GetScriptsDialog(self, self.watcher.folder)
        dlg.exec()
        dlg.deleteLater()
        self.refresh()
        if dlg.fetched:
            names = {str(p) for p in dlg.fetched}
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.ItemDataRole.UserRole) in names:
                    self.list.setCurrentRow(i)
                    break

    def _create_picture(self) -> None:
        info = self._info()
        if info is None or info.error:
            return
        if hasattr(self.window_, "create_script_picture"):
            self.window_.create_script_picture(info.path)
        else:
            from omacad.scripting.images import render_script_image
            if hasattr(self.window_, "viewport"):
                render_script_image(self.window_.viewport, info.path)
        self.refresh()

    def _rename(self) -> None:
        info = self._info()
        if info is not None and self.window_.rename_user_script(info.path):
            self.refresh()

    def _delete(self) -> None:
        from omacad.scripting.folder import is_own
        info = self._info()
        if info is not None and is_own(info.path) and self.window_.delete_user_script(info.path):
            self.refresh()

    def keyPressEvent(self, event) -> None:
        if self.list.hasFocus() and event.key() == Qt.Key.Key_F2:
            self._rename()
            return
        if self.list.hasFocus() and event.key() == Qt.Key.Key_Delete:
            self._delete()
            return
        super().keyPressEvent(event)

    def _run(self, mode="run") -> None:
        info = self._info()
        if info is not None and not info.error:
            self.chosen, self.action = info.path, "easy" if mode == "easy" else "run"
            self.accept()

    def _ai(self) -> None:
        self.action = "ai"
        self.accept()

    def _modify(self) -> None:
        info = self._info()
        if info is not None:
            self.chosen, self.action = info.path, "modify"
            self.accept()

    def _test(self) -> None:
        info = self._info()
        if info is not None and self.window_.confirm_script_trust(info.path):
            self.watcher.check(str(info.path))
            self._show()

    def _edit(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        info = self._info()
        if info is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(info.path)))

    def _copy_error(self) -> None:
        from PySide6.QtWidgets import QApplication
        from omacad.scripting.prompt import error_for_ai
        info = self._info()
        if info is None:
            return
        res = self.watcher.result_for(info.path)
        report = res[1] if res is not None and not res[0] else f"RESULT: FAILED\nError: {info.error}"
        QApplication.clipboard().setText(error_for_ai(info.path.name, report))
        self.lbl_status.setText(self.lbl_status.text() + "\n(Copied: paste it into the AI chat.)")


class ScriptParamsDialog(BaseFeatureDialog):
    """The values a script asks for (its PARAMS), docked in the side panel like every tool. `changed` fires when a value
    changes (the live preview follows it)."""

    changed = Signal()

    def __init__(self, info: ScriptInfo, values: Dict, parent=None, name: str = "", mode: str = "Advanced"):
        super().__init__(info.name, parent)
        self.info = info
        self.fields = {}
        self._values = {p.name: p.coerce(values.get(p.name, p.default)) for p in info.params}
        self.lbl_image = None
        if getattr(info, "image_path", None) and info.image_path.exists():
            pix = QPixmap(str(info.image_path))
            if not pix.isNull():
                self.lbl_image = QLabel()
                self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scaled = pix.scaled(280, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.lbl_image.setPixmap(scaled)
                self.lbl_image.setStyleSheet("QLabel { background-color: rgba(0, 0, 0, 0.08); border-radius: 6px; padding: 2px; }")
                self.lbl_image.setToolTip(info.name)
                self.main_layout.addWidget(self.lbl_image)
        if info.description:
            desc = QLabel(info.description)
            desc.setWordWrap(True)
            self.main_layout.addWidget(desc)
        self.mode = QComboBox()
        self.mode.addItems(["Advanced", "Easy"])
        self.main_layout.addWidget(self.mode)
        form = QFormLayout()
        self.edt_name = QLineEdit(name or info.default_name)
        self.edt_name.setPlaceholderText(info.default_name)
        self.edt_name.setToolTip("What the things this script makes are called in the browser (several get numbers or "
                                 "the script adds its own words, e.g. “… lid”)")
        form.addRow("Name", self.edt_name)
        self.param_form = form
        self.mode.setCurrentText(mode)
        self._set_mode(mode)
        self.mode.currentTextChanged.connect(self._set_mode)
        self.main_layout.addLayout(form)
        self.lbl_problem = QLabel("")
        self.lbl_problem.setWordWrap(True)
        self.lbl_problem.setStyleSheet("color: #d9534f;")
        self.main_layout.addWidget(self.lbl_problem)
        self.add_buttons()
        self.btn_ok.setText("Run")

    def _set_mode(self, mode):
        form = self.param_form
        wanted = {p.name for p in self.info.params} if mode == "Advanced" or self.info.easy_params is None else set(self.info.easy_params)
        for p in self.info.params:
            if p.name in self.fields or p.name not in wanted:
                continue
            w = self._field(p, self._values[p.name])
            w.setToolTip(p.help)
            label = p.title + (f" ({p.unit})" if p.unit and p.type in ("float", "int") else "")
            form.addRow(label, w)
            self.fields[p.name] = (p, w)
            sig = (w.toggled if isinstance(w, QCheckBox) else w.currentIndexChanged if isinstance(w, QComboBox)
                   else w.textChanged if isinstance(w, QLineEdit) else w.valueChanged)
            sig.connect(lambda *_: self.changed.emit())
        names = [p.name for p in self.info.params if p.name in self.fields]
        if mode == "Easy" and self.info.easy_params is not None:
            names = list(dict.fromkeys([n for n in self.info.easy_params if n in self.fields] + names))
        rows = {}
        for key, (_, widget) in self.fields.items():
            form.setRowVisible(widget, True)
            row = form.takeRow(widget)
            rows[key] = row.labelItem.widget()
        for key in names:
            widget = self.fields[key][1]
            form.addRow(rows[key], widget)
            form.setRowVisible(widget, mode == "Advanced" or self.info.easy_params is None
                               or key in self.info.easy_params)

    @staticmethod
    def _field(p: Param, value) -> QWidget:
        value = p.coerce(value)
        if p.type == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
        elif p.type == "choice":
            w = QComboBox()
            w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)    # the whole choice shows
            for c in p.choices:
                w.addItem(str(c), c)
            w.setCurrentIndex(max(0, p.choices.index(value) if value in p.choices else 0))
        elif p.type == "str":
            w = QLineEdit(str(value))
        elif p.type == "int":
            w = QSpinBox()
            w.setRange(int(p.min) if p.min is not None else -1_000_000, int(p.max) if p.max is not None else 1_000_000)
            w.setSingleStep(int(p.step or 1))
            w.setValue(int(value))
        else:
            w = QDoubleSpinBox()
            decimals = p.decimals if p.decimals is not None else 3
            w.setDecimals(decimals)
            w.setRange(float(p.min) if p.min is not None else -1e6, float(p.max) if p.max is not None else 1e6)
            w.setSingleStep(float(p.step or 1.0))
            w.setValue(float(value))
        return w

    def name(self) -> str:
        return self.edt_name.text().strip() or self.info.default_name

    def values(self) -> Dict:
        out = dict(self._values)
        for name, (p, w) in self.fields.items():
            if isinstance(w, QCheckBox):
                out[name] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[name] = w.currentData()
            elif isinstance(w, QLineEdit):
                out[name] = w.text()
            else:
                out[name] = w.value()
        return out


def _images_in(mime) -> list:
    """Pictures in pasted or dropped data: image files (paths) or a copied image (QImage)."""
    from PySide6.QtGui import QImage
    found = [u.toLocalFile() for u in (mime.urls() if mime.hasUrls() else [])
             if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES]
    if not found and mime.hasImage():
        img = QImage(mime.imageData())
        if not img.isNull():
            found.append(img)
    return found


class _WishEdit(QPlainTextEdit):
    """The wish text: a pasted or dropped picture goes to the pictures for the AI instead of into the text."""
    picture = Signal(object)

    def canInsertFromMimeData(self, source) -> bool:
        return bool(_images_in(source)) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source) -> None:
        images = _images_in(source)
        if images:
            for img in images:
                self.picture.emit(img)
        else:
            super().insertFromMimeData(source)


class AiScriptDialog(QDialog):
    """New Script with AI: what the user wants, then start the AI agent or copy the instructions for a web chat."""

    def __init__(self, parent, folder: Path, agent_name: Optional[str], bases: Optional[list] = None,
                 base: Optional[Path] = None, grab_view=None):
        """bases: ScriptInfo objects to choose the script to change from ("Modify with AI…"); None = a new script.
        grab_view: gives a QImage of the 3D view (the "From 3D view" picture button); None hides it."""
        super().__init__(parent)
        self.folder = Path(folder)
        self.mode = ""
        self.bases = list(bases or [])
        modifying = bases is not None
        self.setWindowTitle("Modify with AI" if modifying else "New Script with AI")
        self.resize(560, 440)
        lay = QVBoxLayout(self)
        intro = QLabel(("Describe the change you want. Omacad makes a copy of the script, an AI changes the copy (the "
                        "original stays as it is), Omacad tests it automatically and it appears in the same menu.")
                       if modifying else
                       ("Describe the tool you want, e.g. what it makes and which values you want to set. An AI writes "
                        "it as a script; Omacad tests it automatically and it appears under Scripts (Shift+S)."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.cmb_base = None
        if modifying:
            row = QHBoxLayout()
            row.addWidget(QLabel("Script to change:"))
            self.cmb_base = QComboBox()
            for info in self.bases:
                self.cmb_base.addItem(info.name, str(info.path))
            if base is not None:
                idx = self.cmb_base.findData(str(base))
                if idx >= 0:
                    self.cmb_base.setCurrentIndex(idx)
            self.cmb_base.currentIndexChanged.connect(lambda _i: self._suggest_name())
            row.addWidget(self.cmb_base, 1)
            lay.addLayout(row)
        self.edt_wish = _WishEdit()
        self.edt_wish.picture.connect(self.add_image)
        self.edt_wish.setPlaceholderText(
            "Example: Make the lid's grip ribbed and add a hole for a cord in the lid. (Paste or drop a picture here to "
            "show what you mean.)" if modifying else
            "Example: A storage box with a sliding lid. Values: inside length, width and height, wall thickness, "
            "number of compartments.")
        self.edt_wish.textChanged.connect(self._suggest_name)
        lay.addWidget(self.edt_wish, 1)
        self._images = []                       # file paths (str) and pasted pictures (QImage), in order
        pic_row = QHBoxLayout()
        self.lst_images = QListWidget()
        self.lst_images.setViewMode(QListWidget.ViewMode.IconMode)
        self.lst_images.setFlow(QListWidget.Flow.LeftToRight)
        self.lst_images.setWrapping(False)
        self.lst_images.setIconSize(QSize(64, 64))
        self.lst_images.setFixedHeight(92)
        self.lst_images.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.lst_images.setToolTip("Pictures that show the AI what you mean (a sketch, a photo, a screenshot)")
        self.lst_images.hide()
        pic_row.addWidget(self.lst_images, 1)
        pic_buttons = QVBoxLayout()
        self.btn_add_images = QPushButton("Add pictures…")
        self.btn_add_images.setToolTip("Show the AI what you mean with pictures: a sketch, a photo or a screenshot. "
                                       "You can also paste (Ctrl+V) or drop pictures into the text.")
        self.btn_add_images.setAutoDefault(False)
        self.btn_add_images.clicked.connect(self._pick_images)
        self.btn_remove_images = QPushButton("Remove")
        self.btn_remove_images.setAutoDefault(False)
        self.btn_remove_images.clicked.connect(self._remove_images)
        self.btn_remove_images.hide()
        pic_buttons.addWidget(self.btn_add_images)
        self.btn_grab_view = QPushButton("From 3D view")
        self.btn_grab_view.setToolTip("Adds a picture of the 3D view as it looks now (turn and zoom it first to show "
                                      "what you mean)")
        self.btn_grab_view.setAutoDefault(False)
        self._grab_view = grab_view
        self.btn_grab_view.clicked.connect(self._grab_from_view)
        self.btn_grab_view.setVisible(grab_view is not None)
        pic_buttons.addWidget(self.btn_grab_view)
        pic_buttons.addWidget(self.btn_remove_images)
        pic_buttons.addStretch()
        pic_row.addLayout(pic_buttons)
        lay.addLayout(pic_row)
        self.setAcceptDrops(True)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("File name:"))
        self.edt_name = QLineEdit("my_script.py")
        self.edt_name.textEdited.connect(lambda _t: setattr(self, "_name_edited", True))
        self._name_edited = False
        name_row.addWidget(self.edt_name, 1)
        lay.addLayout(name_row)
        if self.cmb_base is not None:
            self._suggest_name()
        where = QLabel(f"Saved in: {self.folder}")
        where.setWordWrap(True)
        where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(where)
        agent_text = (f"AI agent: {agent_name} (change it in Settings › General)." if agent_name else
                      "No AI agent program was found on this computer: copy the instructions and paste them into an "
                      "AI chat (ChatGPT, Claude …) in your browser.")
        lbl_agent = QLabel(agent_text)
        lbl_agent.setWordWrap(True)
        lay.addWidget(lbl_agent)
        row = QHBoxLayout()
        row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setAutoDefault(False)
        btn_cancel.clicked.connect(self.reject)
        self.btn_copy = QPushButton("Copy to clipboard")
        self.btn_copy.setToolTip("For an AI chat in the browser: paste it there, save the answer as a .py file in the "
                                 "scripts folder")
        self.btn_copy.setAutoDefault(False)
        self.btn_copy.clicked.connect(lambda: self._done("copy"))
        self.btn_agent = QPushButton("Start AI agent")
        self.btn_agent.setEnabled(bool(agent_name))
        self.btn_agent.setDefault(bool(agent_name))
        self.btn_agent.clicked.connect(lambda: self._done("agent"))
        for b in (btn_cancel, self.btn_copy, self.btn_agent):
            row.addWidget(b)
        lay.addLayout(row)

    # ---- pictures for the AI ----
    def add_image(self, img) -> None:
        """Adds a picture: a file path or a QImage (pasted)."""
        from PySide6.QtGui import QIcon, QImage, QPixmap
        pix = QPixmap(str(img)) if isinstance(img, (str, Path)) else QPixmap.fromImage(QImage(img))
        if pix.isNull():
            return
        self._images.append(str(img) if isinstance(img, (str, Path)) else QImage(img))
        name = Path(img).name if isinstance(img, (str, Path)) else f"Picture {len(self._images)}"
        item = QListWidgetItem(QIcon(pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)), "")
        item.setToolTip(name)
        self.lst_images.addItem(item)
        self._show_images()

    def images(self) -> list:
        return list(self._images)

    def _grab_from_view(self) -> None:
        try:
            img = self._grab_view()
        except Exception:
            img = None
        if img is not None and not img.isNull():
            self.add_image(img)

    def _show_images(self) -> None:
        has = bool(self._images)
        self.lst_images.setVisible(has)
        self.btn_remove_images.setVisible(has)
        self.btn_add_images.setText("Add more…" if has else "Add pictures…")

    def _pick_images(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        pattern = " ".join(f"*{s}" for s in IMAGE_SUFFIXES)
        files, _f = QFileDialog.getOpenFileNames(self, "Pictures for the AI", str(Path.home()),
                                                 f"Pictures ({pattern})")
        for f in files:
            self.add_image(f)

    def _remove_images(self) -> None:
        rows = sorted({self.lst_images.row(i) for i in self.lst_images.selectedItems()} or
                      ({self.lst_images.count() - 1} if self.lst_images.count() else set()), reverse=True)
        for r in rows:
            self.lst_images.takeItem(r)
            del self._images[r]
        self._show_images()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete and self.lst_images.hasFocus():
            self._remove_images()
            return
        if event.matches(QKeySequence.StandardKey.Paste) and not self.edt_wish.hasFocus():
            from PySide6.QtWidgets import QApplication
            for img in _images_in(QApplication.clipboard().mimeData()):
                self.add_image(img)
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event) -> None:
        if _images_in(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for img in _images_in(event.mimeData()):
            self.add_image(img)
        event.acceptProposedAction()

    def base(self) -> Optional[Path]:
        return Path(self.cmb_base.currentData()) if self.cmb_base is not None and self.cmb_base.count() else None

    def _suggest_name(self) -> None:
        if self._name_edited:
            return
        words = self.edt_wish.toPlainText().split()[:3 if self.cmb_base is not None else 4]
        base = self.base()
        prefix = (base.stem + " ") if base is not None else ""
        self.edt_name.setText(safe_file_name(prefix + " ".join(words)) if (words or prefix) else "my_script.py")

    def wish(self) -> str:
        return self.edt_wish.toPlainText().strip()

    def file_name(self) -> str:
        """A free name in the folder (my_script.py, my_script_2.py …)."""
        name = safe_file_name(Path(self.edt_name.text().strip() or "my_script").stem.replace("_", " "))
        stem, n = Path(name).stem, 2
        while (self.folder / name).exists():
            name = f"{stem}_{n}.py"
            n += 1
        return name

    def _done(self, mode: str) -> None:
        if not self.wish():
            self.edt_wish.setFocus()
            self.edt_wish.setPlaceholderText("Write what the script should make first.")
            return
        self.mode = mode
        self.accept()
