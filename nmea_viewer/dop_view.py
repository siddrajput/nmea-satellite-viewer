"""DOP trending: HDOP / PDOP / VDOP history over the rolling window."""

from __future__ import annotations

from datetime import datetime

import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget


class DopView(QWidget):
    """Time plot of HDOP, PDOP, VDOP from the history recorder."""

    CURVES = (
        ("HDOP", (76, 154, 255)),
        ("PDOP", (255, 86, 48)),
        ("VDOP", (54, 179, 126)),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("left", "DOP")
        self.plot.setLabel("bottom", "Time")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.addLegend(offset=(10, 10))
        self.plot.setYRange(0, 10)
        layout.addWidget(self.plot)
        self._curves = {
            name: self.plot.plot([], [], pen=pg.mkPen(color, width=2), name=name)
            for name, color in self.CURVES
        }

    def update(self, history) -> None:
        pts = history.dop_series()
        if not pts:
            return
        now_ts = datetime.now().timestamp()
        t0 = now_ts - history.window_s
        xs = [t - t0 for t, _, _, _ in pts]
        for name, idx in (("HDOP", 1), ("PDOP", 2), ("VDOP", 3)):
            ys = [p[idx] if p[idx] is not None else float("nan") for p in pts]
            self._curves[name].setData(xs, ys)
        self.plot.setXRange(0, history.window_s)
