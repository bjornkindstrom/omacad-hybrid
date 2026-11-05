"""Long work stays off the main thread, so the window system never offers to kill the app, and it looks like a plain call."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import threading
import time

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from omacad import busy
from omacad.model.document import Document
from omacad.ui import busy_dialog

app = QApplication.instance() or QApplication([])


@pytest.fixture
def keeper():
    window = QWidget()
    window.show()
    made = busy_dialog.install(window)
    yield made
    busy.install(None)
    window.close()


def slowly(seconds, value=None):
    time.sleep(seconds)
    return value


def test_without_the_app_it_is_a_plain_call():
    busy.install(None)
    assert busy.run("x", threading.current_thread) is threading.current_thread()


def test_work_runs_off_the_main_thread_and_gives_back_its_result(keeper):
    worker = busy.run("x", threading.current_thread)
    assert worker is not threading.main_thread() and not busy.active()
    assert busy.run("x", lambda: slowly(0.1, 42)) == 42


def test_an_exception_comes_back_to_the_caller(keeper):
    def fail():
        time.sleep(0.05)
        raise ValueError("no room")
    with pytest.raises(ValueError, match="no room"):
        busy.run("x", fail)
    assert not busy.active() and keeper.window.updatesEnabled()


def test_the_main_thread_keeps_running_and_the_window_isnt_painted(keeper):
    seen = []
    tick = keeper.tick

    def counted(elapsed):
        seen.append((time.monotonic(), keeper.window.updatesEnabled(), busy.active()))
        tick(elapsed)
    keeper.tick = counted
    busy.run("x", lambda: slowly(0.4))
    assert len(seen) >= 8 and all(not enabled and running for _, enabled, running in seen)
    assert max(b[0] - a[0] for a, b in zip(seen, seen[1:])) < 0.15
    assert keeper.window.updatesEnabled()


def test_the_box_shows_only_when_it_takes_a_while(keeper):
    shown = []
    busy.run("Short", lambda: (slowly(0.1), shown.append(keeper.dialog))[0])
    assert shown == [None] and keeper.dialog is None

    def look():
        time.sleep(busy_dialog.SHOW_AFTER + 0.3)
        shown.append((keeper.dialog.isVisible(), keeper.dialog.label.text()))
    busy.run("Japandi", look)
    assert shown[-1] == (True, "Japandi…")
    assert keeper.dialog is None


def test_a_quick_step_never_touches_the_window(keeper):
    begun = []
    keeper.begin = begun.append
    assert busy.run("x", lambda: 1) == 1
    assert begun == []


def test_input_and_closing_are_dropped_meanwhile(keeper):
    clicks = []
    keeper.window.mousePressEvent = clicks.append
    closed = []
    keeper.window.closeEvent = lambda e: closed.append(e)

    def press():
        time.sleep(0.05)
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1), Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.postEvent(keeper.window, event)
        app.postEvent(keeper.window, QEvent(QEvent.Type.Close))
        time.sleep(0.15)
    busy.run("x", press)
    app.processEvents()
    assert clicks == [] and closed == []
    keeper.window.show()


def test_timers_wait_until_the_work_is_done(keeper):
    fired = []
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: fired.append(busy.active()))
    timer.start(10)
    busy.run("x", lambda: slowly(0.2))
    assert fired == []
    deadline = time.monotonic() + 1.0
    while not fired and time.monotonic() < deadline:
        app.processEvents()
    assert fired == [False]



def test_a_step_is_one_undo_step_and_the_ui_refreshes_after_it_on_the_main_thread(keeper):
    doc = Document()
    calls = []
    doc.add_change_listener(lambda: calls.append((threading.current_thread(), busy.active(), len(doc.bodies))))
    body = doc.add_box(10, 10, 10)
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(1000.0)
    assert calls and all(thread is threading.main_thread() and not running and bodies == 1 for thread, running, bodies in calls)
    assert doc.undo_label() == "Box"
    doc.undo()
    assert not doc.bodies
    doc.redo()
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(1000.0)


def test_a_step_that_fails_leaves_the_document_as_it_was(keeper):
    doc = Document()
    body = doc.add_cylinder(30.0, 50.0)
    volume = body.manifold.volume()
    ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 30.0, "length": 50.0, "internal": False}
    with pytest.raises(ValueError, match="margin"):
        doc.add_japandi(body.body_id, [ref], margin=30.0)
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(volume)
    assert not [f for f in doc.timeline.features if f.feature_type == "japandi"]


def test_a_step_inside_a_step_stays_on_its_thread(keeper):
    doc = Document()
    threads = []

    def outer():
        threads.append(threading.current_thread())
        busy.run("inner", lambda: threads.append(threading.current_thread()))
    busy.run("outer", outer)
    assert threads[0] is threads[1] and threads[0] is not threading.main_thread() and doc is not None


def test_a_queued_step_waits_for_the_running_one_so_there_is_never_two_writers(keeper):
    order = []

    def first():
        order.append("first starts")
        time.sleep(0.2)
        order.append("first ends")

    def second():
        order.append(("second", threading.current_thread() is threading.main_thread()))
    QTimer.singleShot(0, lambda: busy.run("second", second))
    busy.run("first", first)
    assert order == ["first starts", "first ends", ("second", True)]


def test_autosave_keeps_off_a_half_built_document(keeper):
    from omacad.ui.controllers.file_session import FileSessionMixin
    ran = []

    class Host(FileSessionMixin):
        pass
    host = Host()

    def during():
        ran.append(busy.active())
        FileSessionMixin.autosave_now(host)     # would fail on this bare host if it looked at the document
        time.sleep(0.05)
    busy.run("x", during)
    assert ran == [True]
