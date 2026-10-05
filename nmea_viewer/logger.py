"""NMEA logging and replay.

Log format: one line per sentence, timestamp-prefixed, plain text:

    2026-10-05T06:44:00.123456+00:00 $GPGSV,3,1,11,02,17,228,45,1*7B

`ReplayReader` parses such a file back into (dt_seconds, line) events;
`NmeaReplayer` plays them through Qt with an adjustable speed multiplier.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

_LOG_LINE = re.compile(r"^(?P<ts>\S+)\s+(?P<nmea>\$.*)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NmeaLogger:
    """Append timestamped raw NMEA lines to a file."""

    def __init__(self) -> None:
        self._fh = None
        self.path: str | None = None

    @property
    def active(self) -> bool:
        return self._fh is not None

    def start(self, path: str) -> None:
        self.stop()
        self._fh = open(path, "a", encoding="ascii", errors="ignore")
        self.path = path
        self._fh.write(f"# nmea log started {_now_iso()}\n")

    def write(self, line: str) -> None:
        if self._fh is not None and line.startswith("$"):
            self._fh.write(f"{_now_iso()} {line}\n")

    def stop(self) -> None:
        if self._fh is not None:
            try:
                self._fh.write(f"# nmea log stopped {_now_iso()}\n")
                self._fh.close()
            finally:
                self._fh = None
                self.path = None


class ReplayReader:
    """Read a log file into timed events. Qt-free, so it is unit-testable."""

    def __init__(self, path: str) -> None:
        self.path = path

    def events(self) -> list[tuple[float, str]]:
        """Return [(seconds since first event, nmea line), ...] in order."""
        out: list[tuple[float, str]] = []
        t0: datetime | None = None
        with open(self.path, encoding="ascii", errors="ignore") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw or raw.startswith("#"):
                    continue
                m = _LOG_LINE.match(raw)
                if not m:
                    continue
                try:
                    ts = datetime.fromisoformat(m.group("ts"))
                except ValueError:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if t0 is None:
                    t0 = ts
                out.append(((ts - t0).total_seconds(), m.group("nmea")))
        return out


class NmeaReplayer(QObject):
    """Play a log file back through the app at `speed`x real time."""

    line_ready = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, path: str, speed: float = 1.0, parent=None) -> None:
        super().__init__(parent)
        self._events = ReplayReader(path).events()
        self._speed = max(speed, 0.01)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_next)
        self._idx = 0
        self._running = False

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def duration_s(self) -> float:
        return self._events[-1][0] if self._events else 0.0

    def start(self) -> None:
        if not self._events:
            self.finished.emit()
            return
        self._idx = 0
        self._running = True
        self._emit_next()

    def stop(self) -> None:
        self._running = False
        self._timer.stop()
        self.finished.emit()

    def _emit_next(self) -> None:
        if not self._running or self._idx >= len(self._events):
            self._running = False
            self.finished.emit()
            return
        dt, line = self._events[self._idx]
        self.line_ready.emit(line)
        self._idx += 1
        if self._idx < len(self._events):
            wait_ms = max(
                1, int((self._events[self._idx][0] - dt) * 1000 / self._speed))
            self._timer.start(wait_ms)
        else:
            self._running = False
            self.finished.emit()
