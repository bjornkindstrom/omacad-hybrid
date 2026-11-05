"""The window's side of `omacad.busy`: keeps answering the window system while work runs, and shows a small box when it takes
a while. The work can't be stopped halfway, as the document would be left half built, so the box has no Cancel."""

from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout

from omacad import busy

SHOW_AFTER = 0.5        # seconds of work before the box shows: a quick step shouldn't flash one
BAR_SECONDS = 1.5       # one sweep of the bar. Not an indeterminate bar: it animates on a timer, and timers wait
DROPPED = {QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick,
           QEvent.Type.MouseMove, QEvent.Type.Wheel, QEvent.Type.KeyPress, QEvent.Type.KeyRelease,
           QEvent.Type.ShortcutOverride, QEvent.Type.Close, QEvent.Type.ContextMenu, QEvent.Type.DragEnter,
           QEvent.Type.Drop, QEvent.Type.TouchBegin, QEvent.Type.TouchEnd}
# only what can't touch the half-built document. Windows has no way to hold timers back, so the app's own repeating timers
# also check busy.active()
FLAGS = QEventLoop.ProcessEventsFlag.X11ExcludeTimers


class BusyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Omacad Hybrid")
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)
        self.time = QLabel()
        layout.addWidget(self.time)

    def show_progress(self, label: str, elapsed: float) -> None:
        self.label.setText(f"{label}…")
        sweep = (elapsed / BAR_SECONDS) % 2.0
        self.bar.setValue(int(1000 * (sweep if sweep <= 1.0 else 2.0 - sweep)))
        self.time.setText(f"{int(elapsed)} s. Omacad is still working.")


class BusyWindowKeeper(QObject):
    """`begin`, `tick` and `end` for `busy.run`."""

    def __init__(self, window=None):
        super().__init__()
        self.window = window
        self.dialog = None
        self.label = ""

    def begin(self, label: str) -> None:
        self.label = label
        if self.window is not None:
            self.window.setUpdatesEnabled(False)        # the last picture stays; the window's own windows still paint
        QApplication.instance().installEventFilter(self)

    def tick(self, elapsed: float) -> None:
        if elapsed >= SHOW_AFTER:
            if self.dialog is None:
                self.dialog = BusyDialog(self.window)
                self.dialog.show()
            self.dialog.show_progress(self.label, elapsed)
        QApplication.processEvents(FLAGS, 10)

    def end(self) -> None:
        QApplication.instance().removeEventFilter(self)
        if self.dialog is not None:
            self.dialog.hide()
            self.dialog.deleteLater()
            self.dialog = None
        if self.window is not None:
            self.window.setUpdatesEnabled(True)
            self.window.update()

    def eventFilter(self, watched, event) -> bool:
        return event.type() in DROPPED


def install(window=None) -> BusyWindowKeeper:
    keeper = BusyWindowKeeper(window)
    busy.install(keeper)
    return keeper
