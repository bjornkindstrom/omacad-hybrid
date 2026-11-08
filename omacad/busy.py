"""Long work without a frozen window. A frozen main thread stops answering the window system, which then offers to kill the
app (Terminate / Wait on Omarchy, "not responding" on Windows). `run` does the work on another thread and keeps the main
thread alive, yet still returns its result like a plain call, so callers need no changes.

The model knows nothing of Qt: the app hands in the part that keeps the window alive with `install`. Without it, as in
scripts and most tests, `run` is just a call. While work runs the document is half built, so nothing on the main thread may
look at it: the window isn't painted, input is dropped, timers wait, and whatever would refresh the UI waits for the end.
Callbacks already queued with no delay can still run meanwhile (Qt has no way to hold them): those that change the document
come through `run` and wait; the others only set focus or open an editor."""

import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Hashable, Optional

STACK_BYTES = 64 * 1024 * 1024     # as deep as the main thread may go: a Windows thread only gets 1 MB by default
QUICK_SECONDS = 0.03               # work this short never touches the window
POLL_SECONDS = 0.02

_ui: Any = None                    # has begin(label), tick(elapsed) and end()
_worker: Optional[threading.Thread] = None
_deferred: Dict[Hashable, Callable[[], None]] = {}


def install(ui: Any) -> None:
    global _ui
    _ui = ui


def active() -> bool:
    """Work is running: the document may be half built."""
    return _worker is not None


def in_worker() -> bool:
    return threading.current_thread() is _worker


def defer(key: Hashable, fn: Callable[[], None]) -> None:
    """Calls fn on the main thread when the work is done, once per key."""
    _deferred[key] = fn


@contextmanager
def inline():
    """Work inside runs as plain calls on this thread (short work on a private document, e.g. a tool's preview)."""
    global _ui
    saved, _ui = _ui, None
    try:
        yield
    finally:
        _ui = saved


def run(label: str, fn: Callable[[], Any]) -> Any:
    """fn(), keeping the window alive however long it takes. Its result or exception comes back as from a plain call."""
    global _worker
    if _ui is None or threading.current_thread() is not threading.main_thread():
        return fn()
    if _worker is not None:     # a queued callback while the window is kept alive: never two writers to the document
        _worker.join()
        return fn()
    outcome: Dict[str, Any] = {}

    def work():
        try:
            outcome["result"] = fn()
        except BaseException as e:      # handed to the caller below, as if fn had run there
            outcome["error"] = e

    previous_stack = threading.stack_size(STACK_BYTES)
    try:
        worker = _worker = threading.Thread(target=work, name=f"omacad: {label}", daemon=True)
        worker.start()
    finally:
        threading.stack_size(previous_stack)
    try:
        worker.join(QUICK_SECONDS)
        if worker.is_alive():
            start = time.monotonic()
            _ui.begin(label)
            try:
                while worker.is_alive():
                    _ui.tick(time.monotonic() - start)
                    worker.join(POLL_SECONDS)
            finally:
                _ui.end()
    finally:
        _worker = None
    waiting = list(_deferred.values())
    _deferred.clear()
    for later in waiting:
        later()
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")
