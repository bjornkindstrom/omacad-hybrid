"""A small in-memory log of what the app has been doing (status messages, undo steps, errors, printed output).
It travels with every problem report so the AI can see what led up to the problem."""
import collections
import sys
import threading
import time
import traceback

_LINES = collections.deque(maxlen=400)
_LOCK = threading.Lock()


def log(kind: str, text: str) -> None:
    text = str(text).rstrip()
    if not text:
        return
    with _LOCK:
        _LINES.append(f"{time.strftime('%H:%M:%S')} [{kind}] {text}")


def tail(n: int = 150) -> str:
    with _LOCK:
        return "\n".join(list(_LINES)[-n:])


class _Tee:
    """Copies what is printed into the log, then passes it on."""

    def __init__(self, stream, kind: str):
        self._stream, self._kind = stream, kind

    def write(self, s):
        try:
            if s.strip():
                log(self._kind, s)
        except Exception:
            pass
        return self._stream.write(s) if self._stream else len(s)

    def flush(self):
        if self._stream:
            self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install() -> None:
    """Record printed output and uncaught errors; errors are logged and shown, the app keeps running."""
    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout, "out")
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr, "err")
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        log("ERROR", "".join(traceback.format_exception(exc_type, exc, tb)))
        previous(exc_type, exc, tb)

    sys.excepthook = hook
