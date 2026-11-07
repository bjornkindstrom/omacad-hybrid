"""Real Qt worker completion must release the upload queue on the GUI thread."""
import threading
import time

import pytest
from PySide6.QtCore import QThread, QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QProgressBar

from omacad import rfc
from omacad.ui.main_window import MainWindow


class UploadWindow(QMainWindow):
    run_async = MainWindow.run_async
    retry_requests = MainWindow.retry_requests

    def __init__(self):
        super().__init__()
        self.status_label = QLabel(self)
        self.progress_bar = QProgressBar(self)
        self.thread_pool = QThreadPool(self)


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.mark.parametrize("fail", [False, True])
def test_worker_completion_reaches_gui_and_releases_queue(monkeypatch, fail):
    app = QApplication.instance() or QApplication([])
    window = UploadWindow()
    calls = []
    monkeypatch.setattr(rfc, "token", lambda: "T")

    def pending(**kwargs):
        calls.append(QThread.currentThread() == app.thread())
        if fail:
            raise RuntimeError("offline")

    monkeypatch.setattr(rfc, "send_pending", pending)
    window.retry_requests()
    try:
        wait_until(lambda: not window._request_upload_active)
        assert calls == [False]
        assert window.status_label.thread() == app.thread()
        window.retry_requests()
        wait_until(lambda: not window._request_upload_active)
        assert calls == [False, False]
    finally:
        window.thread_pool.waitForDone(3000)
        window.close()


def test_request_arriving_after_queue_snapshot_is_sent_next(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    window = UploadWindow()
    entered, release = threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(rfc, "token", lambda: "T")

    def pending(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)

    monkeypatch.setattr(rfc, "send_pending", pending)
    window.retry_requests()
    try:
        wait_until(entered.is_set)
        window.retry_requests(tmp_path / "new-request")
        release.set()
        wait_until(lambda: len(calls) == 2 and not window._request_upload_active)
    finally:
        release.set()
        window.thread_pool.waitForDone(3000)
        window.close()


@pytest.mark.parametrize("fail", [False, True])
def test_async_callback_runs_on_gui_thread(fail):
    app = QApplication.instance() or QApplication([])
    window = UploadWindow()
    completed = []

    def work():
        if fail:
            raise RuntimeError("offline")
        return "sent"

    def finished(result):
        completed.append((QThread.currentThread() == app.thread(), result))

    window.run_async(work, on_success=finished, on_error=finished)
    try:
        wait_until(lambda: bool(completed))
        assert completed == [(True, "offline" if fail else "sent")]
    finally:
        window.thread_pool.waitForDone(3000)
        window.close()
