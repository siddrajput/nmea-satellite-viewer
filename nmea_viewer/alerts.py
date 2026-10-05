"""Alert engine: C/No drop, fix lost, satellites-in-view collapse.

Evaluated once per refresh tick. Each rule fires once per episode and
re-arms when the signal recovers, so a flapping satellite does not spam
the alert list.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Alert:
    t: float          # epoch seconds
    severity: str     # "warn" or "crit"
    message: str


class AlertEngine:
    def __init__(
        self,
        cn0_min: float = 30.0,
        cn0_hysteresis: float = 3.0,
        min_sats_view: int = 4,
        fix_lost_timeout_s: float = 10.0,
    ) -> None:
        self.cn0_min = cn0_min
        self.cn0_hysteresis = cn0_hysteresis
        self.min_sats_view = min_sats_view
        self.fix_lost_timeout_s = fix_lost_timeout_s

        self._low_cn0: set[tuple[str, int, str]] = set()
        self._fix_lost_since: float | None = None
        self._fix_lost_alerted = False
        self._sats_low_alerted = False

    # ------------------------------------------------------------------ check
    def check(self, now: float, sats: list, fix: dict) -> list[Alert]:
        alerts: list[Alert] = []
        alerts += self._check_cn0(now, sats)
        alerts += self._check_fix(now, fix)
        alerts += self._check_sats_view(now, sats)
        return alerts

    # ------------------------------------------------------------------ rules
    def _sat_key(self, s) -> tuple[str, int, str]:
        return (s.code, s.prn, s.band)

    def _check_cn0(self, now: float, sats: list) -> list[Alert]:
        alerts: list[Alert] = []
        for s in sats:
            if s.cn0 is None:
                continue
            key = self._sat_key(s)
            if key in self._low_cn0:
                if s.cn0 >= self.cn0_min + self.cn0_hysteresis:
                    self._low_cn0.discard(key)  # recovered, re-arm
            elif s.cn0 < self.cn0_min:
                self._low_cn0.add(key)
                alerts.append(Alert(
                    now, "warn",
                    f"{s.label} ({s.band}): C/No {s.cn0:.0f} dB-Hz "
                    f"below {self.cn0_min:.0f} dB-Hz"))
        # Forget sats that disappeared from view entirely.
        visible = {self._sat_key(s) for s in sats}
        self._low_cn0 &= visible
        return alerts

    def _check_fix(self, now: float, fix: dict) -> list[Alert]:
        quality = fix.get("fix_quality")
        ok = quality not in (None, "Invalid") and fix.get("status") != "Void"
        if ok:
            self._fix_lost_since = None
            self._fix_lost_alerted = False
            return []
        if self._fix_lost_since is None:
            self._fix_lost_since = now
            return []
        if not self._fix_lost_alerted and \
                now - self._fix_lost_since >= self.fix_lost_timeout_s:
            self._fix_lost_alerted = True
            return [Alert(
                now, "crit",
                f"No valid fix for {self.fix_lost_timeout_s:.0f} s")]
        return []

    def _check_sats_view(self, now: float, sats: list) -> list[Alert]:
        n = len(sats)
        if n < self.min_sats_view:
            if not self._sats_low_alerted:
                self._sats_low_alerted = True
                return [Alert(
                    now, "warn",
                    f"Only {n} sat{'s' if n != 1 else ''} in view "
                    f"(min {self.min_sats_view})")]
            return []
        self._sats_low_alerted = False
        return []
