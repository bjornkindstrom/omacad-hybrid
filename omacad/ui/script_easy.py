"""Choose visible script parameters; persist plain metadata without executing code."""
import ast
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView, QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QMessageBox


def save_easy(path, names):
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Replace value expressions only, preserving comments and unrelated assignments.
    data = source.encode("utf-8")
    lines = data.splitlines(keepends=True)
    spans = []
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "EASY_PARAMS" for t in targets) and node.value is not None:
            v = node.value
            start = sum(map(len, lines[:v.lineno - 1])) + v.col_offset
            end = sum(map(len, lines[:v.end_lineno - 1])) + v.end_col_offset
            spans.append((start, end))
    replacement = repr(names).encode("utf-8")
    for start, end in reversed(spans):
        data = data[:start] + replacement + data[end:]
    if not spans:
        data += b"\nEASY_PARAMS = " + replacement + b"\n"
    path.write_bytes(data)


def configure_easy(parent, path):
    from omacad.scripting.loader import read_info
    info = read_info(path)
    if info.error:
        QMessageBox.warning(parent, "Easy mode", info.error)
        return
    dlg = QDialog(parent)
    dlg.setWindowTitle("Easy mode settings — " + info.name)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("Select the settings to show in Easy mode.\nHidden settings keep their values."))
    listing = QListWidget()
    listing.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
    layout.addWidget(QLabel("Drag settings up or down to change their order."))
    layout.addWidget(listing)
    by_name = {p.name: p for p in info.params}
    order = list(dict.fromkeys((info.easy_params or []) + list(by_name)))
    for name in order:
        if name not in by_name:
            continue
        item = QListWidgetItem(by_name[name].title, listing)
        item.setData(Qt.ItemDataRole.UserRole, name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if info.easy_params is None or name in info.easy_params
                           else Qt.CheckState.Unchecked)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    if dlg.exec():
        try:
            save_easy(path, [listing.item(i).data(Qt.ItemDataRole.UserRole) for i in range(listing.count())
                             if listing.item(i).checkState() == Qt.CheckState.Checked])
        except (OSError, ValueError, SyntaxError) as exc:
            QMessageBox.warning(parent, "Easy mode", str(exc))
    dlg.deleteLater()
