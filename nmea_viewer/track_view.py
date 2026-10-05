"""Position track: lat/lon path in meters, fix scatter, accuracy stats."""

from __future__ import annotations

import math

import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


def to_meters(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Equirectangular projection around (lat0, lon0); returns (east, north) m."""
    x = math.radians(lon - lon0) * 6371000.0 * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * 6371000.0
    return x, y


def track_stats(points: list[tuple[float, float]]) -> dict:
    """Accuracy stats for [(east_m, north_m), ...]. Empty -> {}."""
    n = len(points)
    if not n:
        return {}
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = sum(xs) / n, sum(ys) / n
    if n > 1:
        sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
        sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n)
    else:
        sx = sy = 0.0
    return {
        "n": n,
        "sigma_e": sx,
        "sigma_n": sy,
        "rms_2d": 2 * math.hypot(sx, sy),
        "span": max(max(xs) - min(xs), max(ys) - min(ys)),
    }


class TrackView(QWidget):
    """Path of the fix in meters from the first point, with scatter + stats."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.stats_label = QLabel("No fixes yet")
        self.stats_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top.addWidget(self.stats_label, 1)
        clear_btn = QPushButton("Clear track")
        clear_btn.clicked.connect(self._on_clear)
        top.addWidget(clear_btn)
        layout.addLayout(top)

        self.plot = pg.PlotWidget()
        self.plot.setAspectLocked(True)
        self.plot.setLabel("left", "North", units="m")
        self.plot.setLabel("bottom", "East", units="m")
        # Keep plain meters on the axes; don't let pyqtgraph rescale to mm/km.
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.plot)

        self._line = self.plot.plot([], [], pen=pg.mkPen((76, 154, 255), width=2))
        self._scatter = pg.ScatterPlotItem(pxMode=True)
        self.plot.addItem(self._scatter)
        self._on_clear_cb = None

    def on_clear(self, cb) -> None:
        """Register callback invoked when the user clears the track."""
        self._on_clear_cb = cb

    def _on_clear(self) -> None:
        if self._on_clear_cb:
            self._on_clear_cb()
        self._line.setData([], [])
        self._scatter.setData([])
        self.stats_label.setText("No fixes yet")

    def update(self, history) -> None:
        fixes = history.fix_points()
        if not fixes:
            return
        lat0, lon0 = fixes[0].lat, fixes[0].lon
        pts = [to_meters(f.lat, f.lon, lat0, lon0) for f in fixes]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self._line.setData(xs, ys)

        spots = []
        for (x, y), f in zip(pts, fixes):
            good = f.fix_quality not in (None, "Invalid")
            spots.append({
                "pos": (x, y), "size": 7, "symbol": "o",
                "brush": pg.mkBrush((54, 179, 126) if good else (214, 48, 49)),
                "pen": pg.mkPen(None),
            })
        self._scatter.setData(spots)

        st = track_stats(pts)
        mean_lat = sum(f.lat for f in fixes) / len(fixes)
        mean_lon = sum(f.lon for f in fixes) / len(fixes)
        self.stats_label.setText(
            f"n={st['n']}  mean {mean_lat:.6f}, {mean_lon:.6f}  "
            f"σE {st['sigma_e']:.2f} m  σN {st['sigma_n']:.2f} m  "
            f"2DRMS {st['rms_2d']:.2f} m  span {st['span']:.1f} m")
