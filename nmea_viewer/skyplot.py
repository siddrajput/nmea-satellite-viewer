"""Skyplot: polar plot of satellite azimuth/elevation.

0° azimuth (North) is up, elevation 90° at the center, horizon at the rim.
Points can be colored by C/No or by band.
"""

from __future__ import annotations

import math

import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def azel_to_xy(azimuth_deg: float, elevation_deg: float) -> tuple[float, float]:
    """Map (az, el) to unit-disc coords: x east, y north, r=(90-el)/90."""
    el = min(max(elevation_deg, 0.0), 90.0)
    r = (90.0 - el) / 90.0
    az = math.radians(azimuth_deg % 360.0)
    return r * math.sin(az), r * math.cos(az)


def cn0_color(cn0: float | None) -> QColor:
    """Red (weak) -> yellow -> green -> blue (strong) ramp over ~15..55 dB-Hz."""
    if cn0 is None:
        return QColor(151, 160, 175)
    stops = [  # (cn0, color)
        (15.0, QColor(214, 48, 49)),
        (30.0, QColor(255, 193, 7)),
        (40.0, QColor(54, 179, 126)),
        (50.0, QColor(76, 154, 255)),
        (55.0, QColor(101, 84, 192)),
    ]
    if cn0 <= stops[0][0]:
        return stops[0][1]
    for (c0, col0), (c1, col1) in zip(stops, stops[1:]):
        if cn0 <= c1:
            f = (cn0 - c0) / (c1 - c0)
            return QColor(
                round(col0.red() + f * (col1.red() - col0.red())),
                round(col0.green() + f * (col1.green() - col0.green())),
                round(col0.blue() + f * (col1.blue() - col0.blue())),
            )
    return stops[-1][1]


BAND_QCOLORS = {
    "L1": QColor(76, 154, 255),
    "L5": QColor(255, 86, 48),
    "L2": QColor(54, 179, 126),
    "Unknown": QColor(151, 160, 175),
}


class SkyplotView(QWidget):
    """Polar sky view of satellites in view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Color by:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["C/No", "Band"])
        top.addWidget(self.color_combo)
        top.addStretch(1)
        layout.addLayout(top)

        self.plot = pg.PlotWidget()
        self.plot.setAspectLocked(True)
        self.plot.setXRange(-1.15, 1.15)
        self.plot.setYRange(-1.15, 1.15)
        self.plot.hideAxis("bottom")
        self.plot.hideAxis("left")
        self._draw_graticule()
        self.scatter = pg.ScatterPlotItem(pxMode=True)
        self.plot.addItem(self.scatter)
        layout.addWidget(self.plot)

    def _draw_graticule(self) -> None:
        pen = pg.mkPen(QColor(180, 180, 180), width=1)
        # Elevation rings: 0° (rim), 30°, 60°.
        for el, r in ((0, 1.0), (30, 2 / 3), (60, 1 / 3)):
            circle = pg.PlotDataItem(
                [r * math.cos(a) for a in _circle_angles()],
                [r * math.sin(a) for a in _circle_angles()],
                pen=pen)
            self.plot.addItem(circle)
            if el:
                lbl = pg.TextItem(f"{el}°", color=(120, 120, 120), anchor=(0.5, 0.5))
                lbl.setPos(r + 0.03, 0)
                self.plot.addItem(lbl)
        # Cross hairs + cardinal labels.
        self.plot.addItem(pg.PlotDataItem([-1, 1], [0, 0], pen=pen))
        self.plot.addItem(pg.PlotDataItem([0, 0], [-1, 1], pen=pen))
        for txt, x, y in (("N", 0, 1.08), ("E", 1.08, 0),
                          ("S", 0, -1.08), ("W", -1.08, 0)):
            lbl = pg.TextItem(txt, color=(80, 80, 80), anchor=(0.5, 0.5))
            lbl.setPos(x, y)
            self.plot.addItem(lbl)

    def update(self, sats: list) -> None:
        mode = self.color_combo.currentText()
        spots = []
        for s in sats:
            if s.azimuth is None or s.elevation is None:
                continue
            x, y = azel_to_xy(s.azimuth, s.elevation)
            brush = (cn0_color(s.cn0) if mode == "C/No"
                     else BAND_QCOLORS.get(s.band, BAND_QCOLORS["Unknown"]))
            tip = (f"{s.label} {s.band}\n"
                   f"Az {s.azimuth:.0f}° El {s.elevation:.0f}°\n"
                   f"C/No {s.cn0:.0f} dB-Hz" if s.cn0 is not None
                   else f"{s.label} {s.band}\nAz/El known, no C/No")
            spots.append({"pos": (x, y), "brush": pg.mkBrush(brush),
                          "pen": pg.mkPen("w"), "size": 14,
                          "symbol": "o", "data": tip})
        self.scatter.setData(spots)


def _circle_angles(n: int = 128) -> list[float]:
    return [2 * math.pi * i / n for i in range(n + 1)]
