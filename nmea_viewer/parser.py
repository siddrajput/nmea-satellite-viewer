"""NMEA 0183 sentence parsing for GNSS monitoring.

Handles the sentences needed for a live sky view:
  - GSV: satellites in view, incl. C/No and (NMEA 4.1+) signal ID used to
         tell L1 apart from L5
  - GGA: fix data (time, position, quality, sats used, HDOP, altitude)
  - RMC: recommended minimum data (date/time, status, speed, course)
  - GSA: fix mode, satellites used in fix, PDOP/HDOP/VDOP

Signal ID -> band mapping follows NMEA 0183 v4.10:
  1 = L1 C/A, 2 = L1 P(Y), 3 = L1 M        -> L1
  4 = L2 P(Y), 5 = L2C-M, 6 = L2C-L        -> L2
  7 = L5-I, 8 = L5-Q                       -> L5
  0 / missing                              -> Unknown
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


# Talker ID -> (constellation name, short display code)
CONSTELLATIONS = {
    "GP": ("GPS", "G"),
    "GL": ("GLONASS", "R"),
    "GA": ("Galileo", "E"),
    "GB": ("BeiDou", "C"),
    "BD": ("BeiDou", "C"),   # legacy talker id, still seen in the wild
    "GQ": ("QZSS", "J"),
    "GI": ("NavIC", "I"),
    "GN": ("Combined", "N"),
}

# NMEA 0183 signal ID -> (band label, human description)
SIGNAL_IDS = {
    0: ("Unknown", "All signals"),
    1: ("L1", "L1 C/A"),
    2: ("L1", "L1 P(Y)"),
    3: ("L1", "L1 M"),
    4: ("L2", "L2 P(Y)"),
    5: ("L2", "L2C-M"),
    6: ("L2", "L2C-L"),
    7: ("L5", "L5-I"),
    8: ("L5", "L5-Q"),
}

FIX_QUALITY = {
    0: "Invalid",
    1: "GNSS fix",
    2: "DGPS fix",
    3: "PPS fix",
    4: "RTK fixed",
    5: "RTK float",
    6: "Dead reckoning",
    7: "Manual",
    8: "Simulation",
}

BAND_ORDER = {"L1": 0, "L5": 1, "L2": 2, "Unknown": 3}


@dataclass
class Satellite:
    """One satellite signal (a PRN may appear twice: once per band)."""

    constellation: str          # e.g. "GPS"
    code: str                   # short code, e.g. "G"
    prn: int
    elevation: float | None     # degrees
    azimuth: float | None       # degrees
    cn0: float | None           # dB-Hz
    signal_id: int | None
    signal_name: str            # e.g. "L1 C/A"
    band: str                   # L1 / L2 / L5 / Unknown
    last_update: float = field(default_factory=time.time)

    @property
    def label(self) -> str:
        return f"{self.code}{self.prn:02d}"


def _to_float(value: str) -> float | None:
    try:
        return float(value) if value not in ("", None) else None
    except (ValueError, TypeError):
        return None


def _to_int(value: str) -> int | None:
    try:
        return int(value) if value not in ("", None) else None
    except (ValueError, TypeError):
        return None


def _degmin_to_decimal(degmin: str, hemi: str) -> float | None:
    """Convert NMEA ddmm.mmmm / dddmm.mmmm to signed decimal degrees."""
    if not degmin or not hemi:
        return None
    try:
        head, _, frac = degmin.partition(".")
        degrees = int(head[:-2])
        minutes = float(head[-2:] + ("." + frac if frac else ""))
        decimal = degrees + minutes / 60.0
        if hemi.upper() in ("S", "W"):
            decimal = -decimal
        return decimal
    except (ValueError, IndexError):
        return None


def _parse_time(t: str) -> str | None:
    if not t or len(t) < 6:
        return None
    try:
        return f"{t[0:2]}:{t[2:4]}:{t[4:6]}"
    except (ValueError, IndexError):
        return None


def _parse_date(d: str) -> str | None:
    if not d or len(d) != 6:
        return None
    try:
        return f"20{d[4:6]}-{d[2:4]}-{d[0:2]}"
    except (ValueError, IndexError):
        return None


def checksum_ok(line: str) -> bool:
    """Verify the NMEA checksum when one is present."""
    if "*" not in line:
        return True  # nothing to verify against
    body, cksum = line.rsplit("*", 1)
    body = body[1:] if body[:1] in ("$", "!") else body
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(cksum[:2], 16)
    except ValueError:
        return False


class NmeaParser:
    """Stateful NMEA parser. Feed it lines; read back satellites and fix."""

    def __init__(self) -> None:
        # (talker, prn, signal_id) -> Satellite. signal_id None stored as -1
        # so the same PRN on L1 and L5 stays two separate entries.
        self.satellites: dict[tuple[str, int, int], Satellite] = {}
        self.fix: dict = {}
        self.gsa: dict = {}
        self.sentences_seen: int = 0
        self.checksum_failures: int = 0

    # ------------------------------------------------------------------ feed
    def feed_line(self, line: str) -> str | None:
        """Parse one NMEA line. Returns the sentence type, or None."""
        line = line.strip()
        if not line or line[0] not in ("$", "!"):
            return None
        if not checksum_ok(line):
            self.checksum_failures += 1
            return None

        body = line[1:].split("*", 1)[0]
        fields = body.split(",")
        if len(fields[0]) < 5:
            return None
        talker, stype = fields[0][:2], fields[0][2:]
        data = fields[1:]

        handler = {
            "GSV": self._parse_gsv,
            "GGA": self._parse_gga,
            "RMC": self._parse_rmc,
            "GSA": self._parse_gsa,
        }.get(stype)
        if handler is None:
            return None
        handler(talker, data)
        self.sentences_seen += 1
        return stype

    # ------------------------------------------------------------- snapshots
    def get_satellites(self, max_age: float = 15.0) -> list[Satellite]:
        """Satellites updated within max_age seconds, sorted L1, L5, L2..."""
        now = time.time()
        sats = [s for s in self.satellites.values() if now - s.last_update <= max_age]
        sats.sort(key=lambda s: (BAND_ORDER.get(s.band, 9), s.code, s.prn))
        return sats

    def prune(self, max_age: float = 15.0) -> None:
        now = time.time()
        stale = [k for k, s in self.satellites.items() if now - s.last_update > max_age]
        for k in stale:
            del self.satellites[k]

    # ------------------------------------------------------------------- GSV
    def _parse_gsv(self, talker: str, fields: list[str]) -> None:
        if len(fields) < 3:
            return
        name, code = CONSTELLATIONS.get(talker, (talker, talker))
        blocks = fields[3:]

        # NMEA 4.1+ appends a signal-ID field to each satellite block.
        # A legacy 2.x sentence always carries a multiple of 4 fields, and
        # can never be a multiple of 5 (max 4 sats per sentence), so the
        # modulo test below is unambiguous.
        n = len(blocks)
        if n % 5 == 0:
            width = 5
        elif n % 4 == 0:
            width = 4
        else:
            width = 5  # best effort on ragged input

        for i in range(0, n, width):
            chunk = blocks[i:i + width] + [""] * (width - len(blocks[i:i + width]))
            prn = _to_int(chunk[0])
            if prn is None:
                continue
            signal_id = _to_int(chunk[4]) if width == 5 else None
            band, signal_name = SIGNAL_IDS.get(
                signal_id if signal_id is not None else 0,
                ("Unknown", f"ID {signal_id}"),
            )
            if width == 4:  # legacy sentence: no signal info at all
                band, signal_name = "Unknown", "n/a"
                key_sig = -1
            else:
                key_sig = signal_id if signal_id is not None else -1

            key = (talker, prn, key_sig)
            self.satellites[key] = Satellite(
                constellation=name,
                code=code,
                prn=prn,
                elevation=_to_float(chunk[1]),
                azimuth=_to_float(chunk[2]),
                cn0=_to_float(chunk[3]),
                signal_id=signal_id,
                signal_name=signal_name,
                band=band,
            )

    # ------------------------------------------------------------------- GGA
    def _parse_gga(self, talker: str, f: list[str]) -> None:
        f += [""] * (15 - len(f))
        quality = _to_int(f[5])
        self.fix.update({
            "utc_time": _parse_time(f[0]),
            "latitude": _degmin_to_decimal(f[1], f[2]),
            "longitude": _degmin_to_decimal(f[3], f[4]),
            "fix_quality": FIX_QUALITY.get(quality, f"Unknown ({quality})")
            if quality is not None else None,
            "sats_used": _to_int(f[6]),
            "hdop": _to_float(f[7]),
            "altitude_m": _to_float(f[8]),
        })

    # ------------------------------------------------------------------- RMC
    def _parse_rmc(self, talker: str, f: list[str]) -> None:
        f += [""] * (12 - len(f))
        if f[1] != "A":  # void / no fix
            self.fix["status"] = "Void"
            return
        self.fix.update({
            "status": "Active",
            "utc_time": _parse_time(f[0]) or self.fix.get("utc_time"),
            "utc_date": _parse_date(f[8]),
            "latitude": _degmin_to_decimal(f[2], f[3]),
            "longitude": _degmin_to_decimal(f[4], f[5]),
            "speed_knots": _to_float(f[6]),
            "course_deg": _to_float(f[7]),
        })

    # ------------------------------------------------------------------- GSA
    def _parse_gsa(self, talker: str, f: list[str]) -> None:
        f += [""] * (18 - len(f))
        fix_type = _to_int(f[1])
        prns = [_to_int(p) for p in f[2:14]]
        self.gsa = {
            "mode": f[0],
            "fix_type": {1: "No fix", 2: "2D", 3: "3D"}.get(fix_type, "?"),
            "sats_in_fix": [p for p in prns if p is not None],
            "pdop": _to_float(f[14]),
            "hdop": _to_float(f[15]),
            "vdop": _to_float(f[16]),
        }
