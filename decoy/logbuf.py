"""
tiny in-memory log buffer. we tee stdout/stderr into it so anything python
prints (including the pymobiledevice3 import error and tunnel gripes) can be
shown inside the app's Logs tab, not just the terminal.
"""

import itertools
import sys
import threading
from collections import deque

_lock = threading.Lock()
_lines = deque(maxlen=800)
_counter = itertools.count(1)


def log_line(text):
    with _lock:
        parts = str(text).rstrip("\n").splitlines() or [""]
        for p in parts:
            _lines.append((next(_counter), p))


def get_logs(since=0):
    # only hand back lines newer than the caller's cursor
    with _lock:
        return [{"id": i, "text": t} for (i, t) in _lines if i > since]


class _Tee:
    def __init__(self, stream):
        self.stream = stream

    def write(self, s):
        try:
            self.stream.write(s)
        except Exception:
            pass
        if s and s.strip():
            log_line(s)
        return len(s) if s else 0

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass


def install():
    sys.stdout = _Tee(sys.stdout)
    sys.stderr = _Tee(sys.stderr)
