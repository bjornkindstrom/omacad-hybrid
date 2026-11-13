"""Get Scripts… (from the Scripts window): the scripts other Omacad users shared, with what each does, by whom, and
whether it is new, already here, or updated. Only what the user ticks is fetched into the scripts folder."""
import threading
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)

from omacad import script_share
from omacad.scripting.loader import read_info

STATUS_TEXT = {"new": "New", "update": "Update", "have": "✓ Have"}


class GetScriptsDialog(QDialog):
    loaded = Signal(object, str)          # list of RemoteScript (or None), error text

    def __init__(self, parent, folder: Path, list_fn: Optional[Callable] = None, download_fn: Optional[Callable] = None):
        super().__init__(parent)
        self.folder = Path(folder)
        self.list_fn = list_fn or (lambda: script_share.list_remote(self.folder))
        self.download_fn = download_fn or (lambda items: script_share.download(items, self.folder))
        self.items: List[script_share.RemoteScript] = []
        self.fetched: List[Path] = []
        self.setWindowTitle("Get Scripts")
        self.resize(720, 440)
        lay = QVBoxLayout(self)
        intro = QLabel("Scripts other Omacad users made. Tick the ones you want and press Get; they are put in your "
                       "scripts folder. Omacad asks before a new script runs the first time.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(260)
        self.list.currentItemChanged.connect(lambda *_: self._show())
        self.list.itemChanged.connect(lambda *_: self._sync_buttons())
        body.addWidget(self.list)
        right = QVBoxLayout()
        self.lbl_title = QLabel()
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.lbl_by = QLabel()
        self.lbl_image = QLabel()
        self.lbl_image.hide()
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.lbl_params = QLabel()
        self.lbl_params.setWordWrap(True)
        for w in (self.lbl_title, self.lbl_by, self.lbl_image, self.lbl_desc, self.lbl_params):
            right.addWidget(w)
        right.addStretch()
        body.addLayout(right, 1)
        lay.addLayout(body, 1)
        self.lbl_status = QLabel("Loading the shared scripts…")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)
        row = QHBoxLayout()
        self.btn_all = QPushButton("Tick all new and updated")
        self.btn_all.clicked.connect(self._tick_all)
        self.btn_reload = QPushButton("Reload")
        self.btn_reload.clicked.connect(self.reload)
        row.addWidget(self.btn_all)
        row.addWidget(self.btn_reload)
        row.addStretch()
        self.btn_get = QPushButton("Get")
        self.btn_get.setDefault(True)
        self.btn_get.clicked.connect(self._get)
        btn_close = QPushButton("Close")
        btn_close.setAutoDefault(False)
        btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_get)
        row.addWidget(btn_close)
        lay.addLayout(row)
        self.loaded.connect(self._on_loaded, Qt.ConnectionType.QueuedConnection)
        self.reload()

    # ---- loading --------------------------------------------------------------------------------------------------
    def reload(self) -> None:
        self.btn_reload.setEnabled(False)
        self.btn_get.setEnabled(False)
        self.lbl_status.setText("Loading the shared scripts…")

        def work():
            try:
                self.loaded.emit(self.list_fn(), "")
            except Exception as e:          # no token, no network: shown in the window
                self.loaded.emit(None, str(e) or type(e).__name__)

        threading.Thread(target=work, daemon=True).start()

    def _on_loaded(self, items, error: str) -> None:
        self.btn_reload.setEnabled(True)
        if items is None:
            self.lbl_status.setText(f"Could not load the shared scripts: {error}")
            self._sync_buttons()
            return
        self.items = list(items)
        self.infos = {}
        for it in self.items:
            try:
                self.infos[it.path] = read_info(it.cached) if it.cached else None
            except Exception:
                self.infos[it.path] = None
        order = {"update": 0, "new": 1, "have": 2}
        self.items.sort(key=lambda it: (order.get(it.status, 3), self._name(it).lower()))
        self.list.blockSignals(True)
        self.list.clear()
        for it in self.items:
            item = QListWidgetItem(f"{self._name(it)}  ·  {STATUS_TEXT.get(it.status, it.status)}")
            item.setData(Qt.ItemDataRole.UserRole, it.path)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if it.status == "have":
                flags &= ~Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            if it.status != "have":
                item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(0)
        new = sum(it.status == "new" for it in self.items)
        upd = sum(it.status == "update" for it in self.items)
        self.lbl_status.setText(f"{len(self.items)} shared scripts: {new} new, {upd} updated." if self.items
                                else "Nobody has shared a script yet.")
        self._show()
        self._sync_buttons()

    # ---- showing --------------------------------------------------------------------------------------------------
    def _name(self, it) -> str:
        info = getattr(self, "infos", {}).get(it.path)
        return (info.name if info is not None and info.name else it.file_name[:-3])

    def _current(self):
        item = self.list.currentItem()
        path = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return next((it for it in self.items if it.path == path), None)

    def _show(self) -> None:
        it = self._current()
        if it is None:
            for w in (self.lbl_title, self.lbl_by, self.lbl_desc, self.lbl_params):
                w.setText("")
            self.lbl_image.hide()
            return
        info = self.infos.get(it.path)
        self.lbl_title.setText(self._name(it))
        state = {"new": "", "have": " · already in your folder", "update": " · a newer version than yours"}
        self.lbl_by.setText(f"by {it.author} · {it.file_name}{state.get(it.status, '')}")
        self.lbl_desc.setText(info.description if info is not None else "")
        self.lbl_params.setText(("Values: " + ", ".join(p.title for p in info.params)) if info is not None and info.params else "")
        show_picture(self.lbl_image, it.picture_cached)

    def checked(self) -> List["script_share.RemoteScript"]:
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.checkState() == Qt.CheckState.Checked:
                it = next((x for x in self.items if x.path == item.data(Qt.ItemDataRole.UserRole)), None)
                if it is not None:
                    out.append(it)
        return out

    def _sync_buttons(self) -> None:
        self.btn_get.setEnabled(bool(self.checked()))
        self.btn_all.setEnabled(any(it.status != "have" for it in self.items))

    def _tick_all(self) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Checked)

    def _get(self) -> None:
        chosen = self.checked()
        if not chosen:
            return
        try:
            written = self.download_fn(chosen)
        except Exception as e:
            self.lbl_status.setText(f"Could not get the scripts: {e}")
            return
        self.fetched.extend(written)
        self.lbl_status.setText("Got " + ", ".join(p.name for p in written) + ". They are in your Scripts list now.")
        self.reload()


def show_picture(label: QLabel, path: Optional[Path]) -> None:
    if path is None or not Path(path).exists():
        label.hide()
        return
    pix = QPixmap(str(path))
    if pix.isNull():
        label.hide()
        return
    label.setPixmap(pix.scaled(240, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    label.show()
