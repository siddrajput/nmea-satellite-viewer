"""Serial port reader (QThread) and a built-in NMEA simulator.

The simulator lets you try the UI with no hardware attached: it generates a
realistic multi-constellation sky with L1 and L5 signals (NMEA 4.1 GSV signal
IDs), plus GGA/RMC/GSA sentences.
"""

from __future__ import annotations

import math
import random
import time

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal

try:
    import serial
    import serial.tools.list_ports
    _HAVE_SERIAL = True
except ImportError:  # pragma: no cover
    _HAVE_SERIAL = False


def list_serial_ports() -> list[str]:
    if not _HAVE_SERIAL:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


BAUD_RATES = [4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]


class SerialReader(QThread):
    """Read NMEA lines from a serial port in the background."""

    line_received = pyqtSignal(str)
    connection_error = pyqtSignal(str)
    disconnected = pyqtSignal()

    def __init__(self, port: str, baudrate: int, parent=None):
        super().__init__(parent)
        self._port = port
        self._baudrate = baudrate
        self._stop = False
        self._ser = None

    def run(self) -> None:
        if not _HAVE_SERIAL:
            self.connection_error.emit("pyserial is not installed")
            return
        try:
            self._ser = serial.Serial(self._port, self._baudrate, timeout=1.0)
        except Exception as exc:  # SerialException and friends
            self.connection_error.emit(f"Could not open {self._port}: {exc}")
            return
        while not self._stop:
            try:
                raw = self._ser.readline()
            except Exception as exc:
                if not self._stop:
                    self.connection_error.emit(f"Read error: {exc}")
                break
            if raw:
                line = raw.decode("ascii", errors="ignore").strip()
                if line:
                    self.line_received.emit(line)
        try:
            self._ser.close()
        except Exception:
            pass
        self.disconnected.emit()

    def stop(self) -> None:
        self._stop = True
        self.wait(3000)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def _checksum(body: str) -> str:
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"{cs:02X}"


def _sentence(body: str) -> str:
    return f"${body}*{_checksum(body)}"


def _latlon(lat: float, lon: float) -> tuple[str, str, str, str]:
    lat_hemi = "N" if lat >= 0 else "S"
    lon_hemi = "E" if lon >= 0 else "W"
    lat_a, lon_a = abs(lat), abs(lon)
    lat_d, lon_d = int(lat_a), int(lon_a)
    return (f"{lat_d:02d}{ (lat_a - lat_d) * 60:07.4f}", lat_hemi,
            f"{lon_d:03d}{ (lon_a - lon_d) * 60:07.4f}", lon_hemi)


class NmeaSimulator(QObject):
    """Generate a plausible live NMEA stream (L1 + L5) on a timer."""

    line_generated = pyqtSignal(str)

    # (talker, prn, elev_deg, azim_deg, base_cn0, signal_id)
    _SKY = [
        # GPS L1 C/A
        ("GP", 2, 17, 228, 45, 1), ("GP", 4, 40, 70, 47, 1),
        ("GP", 5, 52, 150, 44, 1), ("GP", 9, 13, 23, 37, 1),
        ("GP", 12, 64, 300, 48, 1), ("GP", 24, 28, 190, 41, 1),
        ("GP", 25, 71, 110, 46, 1),
        # GPS L5 (same sats, second frequency)
        ("GP", 4, 40, 70, 43, 7), ("GP", 5, 52, 150, 40, 7),
        ("GP", 9, 13, 23, 33, 7), ("GP", 12, 64, 300, 44, 7),
        ("GP", 25, 71, 110, 42, 7),
        # Galileo E1 / E5a
        ("GA", 11, 33, 250, 44, 1), ("GA", 19, 58, 40, 46, 1),
        ("GA", 22, 21, 320, 38, 1),
        ("GA", 11, 33, 250, 40, 7), ("GA", 19, 58, 40, 42, 7),
        # GLONASS L1
        ("GL", 3, 45, 180, 43, 1), ("GL", 8, 25, 90, 39, 1),
        ("GL", 15, 60, 270, 45, 1),
        # QZSS L1 / L5
        ("GQ", 1, 55, 200, 42, 1), ("GQ", 1, 55, 200, 38, 7),
    ]

    def __init__(self, parent=None, lat: float = 32.7157, lon: float = -117.1611):
        super().__init__(parent)
        self._lat = lat
        self._lon = lon
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._t0 = time.time()

    def start(self, interval_ms: int = 200) -> None:
        self._t0 = time.time()
        self._timer.start(interval_ms)

    def stop(self) -> None:
        self._timer.stop()

    # -- sentence builders --------------------------------------------------
    def _tick(self) -> None:
        t = time.time() - self._t0
        now = time.gmtime()

        # GSV, grouped by (talker, signal) the way real receivers do it.
        groups: dict[tuple[str, int], list] = {}
        for talker, prn, el, az, base, sig in self._SKY:
            cn0 = base + 2.0 * math.sin(t / 7.0 + prn) + random.uniform(-0.8, 0.8)
            groups.setdefault((talker, sig), []).append((prn, el, az, cn0, sig))

        for (talker, _sig), sats in sorted(groups.items()):
            n_msg = (len(sats) + 3) // 4
            for m in range(n_msg):
                chunk = sats[m * 4:(m + 1) * 4]
                body = f"{talker}GSV,{n_msg},{m + 1},{len(sats)}"
                for prn, el, az, cn0, sig in chunk:
                    body += f",{prn:02d},{el},{az},{cn0:.0f},{sig}"
                self.line_generated.emit(_sentence(body))

        # GGA / RMC / GSA once per second-ish (every 5th tick at 200 ms)
        if int(t * 5) % 5 == 0:
            hhmmss = f"{now.tm_hour:02d}{now.tm_min:02d}{now.tm_sec:02d}"
            ddmmyy = f"{now.tm_mday:02d}{now.tm_mon:02d}{now.tm_year % 100:02d}"
            la, la_h, lo, lo_h = _latlon(self._lat, self._lon)
            n_sats = len({(tk, pr) for tk, pr, *_ in self._SKY})
            self.line_generated.emit(_sentence(
                f"GPGGA,{hhmmss},{la},{la_h},{lo},{lo_h},1,"
                f"{n_sats:02d},0.8,20.0,M,0.0,M,,"))
            self.line_generated.emit(_sentence(
                f"GPRMC,{hhmmss},A,{la},{la_h},{lo},{lo_h},"
                f"0.0,0.0,{ddmmyy},,,A"))
            prns = ",".join(f"{pr:02d}" for _, pr, *_ in self._SKY[:12])
            self.line_generated.emit(_sentence(
                f"GPGSA,A,3,{prns},2.5,1.3,2.1"))
