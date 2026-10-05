"""Rolling history of C/No, DOP, and position fixes.

Sampled once per UI refresh tick (1 Hz). Everything is time-windowed so
memory stays bounded; the views read plain series out of here.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass
class FixPoint:
    t: float
    lat: float
    lon: float
    fix_quality: str | None
    sats_used: int | None


class HistoryRecorder:
    """Keep the last `window_s` seconds of per-sat C/No, DOP, and fixes."""

    def __init__(self, window_s: float = 300.0) -> None:
        self.window_s = window_s
        # (constellation code, prn, band) -> deque[(t, cn0)]
        self.cn0: dict[tuple[str, int, str], deque] = {}
        # deque[(t, hdop, pdop, vdop)]
        self.dop: deque = deque()
        # deque[FixPoint]
        self.fixes: deque = deque()

    # ------------------------------------------------------------------ feed
    def record_tick(
        self,
        sats: list,
        fix: dict,
        gsa: dict,
        now: float | None = None,
    ) -> None:
        """Record one 1 Hz sample. `sats` are the currently visible satellites."""
        now = time.time() if now is None else now

        for s in sats:
            if s.cn0 is None:
                continue
            key = (s.code, s.prn, s.band)
            dq = self.cn0.get(key)
            if dq is None:
                dq = self.cn0[key] = deque()
            dq.append((now, s.cn0))

        self.dop.append(
            (now, fix.get("hdop"), gsa.get("pdop"), gsa.get("vdop")))
        lat, lon = fix.get("latitude"), fix.get("longitude")
        if lat is not None and lon is not None:
            self.fixes.append(FixPoint(
                t=now, lat=lat, lon=lon,
                fix_quality=fix.get("fix_quality"),
                sats_used=fix.get("sats_used"),
            ))

        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_s
        while self.dop and self.dop[0][0] < cutoff:
            self.dop.popleft()
        while self.fixes and self.fixes[0].t < cutoff:
            self.fixes.popleft()
        stale_keys = []
        for key, dq in self.cn0.items():
            while dq and dq[0][0] < cutoff:
                dq.popleft()
            if not dq:
                stale_keys.append(key)
        for key in stale_keys:
            del self.cn0[key]

    def clear(self) -> None:
        self.cn0.clear()
        self.dop.clear()
        self.fixes.clear()

    # ---------------------------------------------------------------- series
    def cn0_series(self) -> dict[tuple[str, int, str], list[tuple[float, float]]]:
        return {k: list(dq) for k, dq in self.cn0.items()}

    def dop_series(self) -> list[tuple[float, float | None, float | None, float | None]]:
        return list(self.dop)

    def fix_points(self) -> list[FixPoint]:
        return list(self.fixes)
