"""C/No-over-time strip charts: one curve per satellite, rolling window."""

from __future__ import annotations

from datetime import datetime

import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from .skyplot import BAND_QCOLORS


class Cn0HistoryView(QWidget):
    """Strip chart of C/No per satellite over the history window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("left", "C/No", units="dB-Hz")
        self.plot.setLabel("bottom", "Time")
        self.plot.setYRange(0, 60)
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.addLegend(offset=(10, 10))
        layout.addWidget(self.plot)
        self._curves: dict[tuple[str, int, str], pg.PlotDataItem] = {}

    def update(self, history) -> None:
        series = history.cn0_series()
        now_ts = datetime.now().timestamp()
        t0 = now_ts - history.window_s
        for key, pts in series.items():
            xs = [t - t0 for t, _ in pts]
            ys = [c for _, c in pts]
            curve = self._curves.get(key)
            if curve is None:
                code, prn, band = key
                curve = self.plot.plot(
                    xs, ys,
                    pen=pg.mkPen(BAND_QCOLORS.get(band, BAND_QCOLORS["Unknown"]),
                                 width=1.5),
                    name=f"{code}{prn:02d} {band}")
                self._curves[key] = curve
            else:
                curve.setData(xs, ys)
        # Drop curves for sats that aged out of the window.
        for key in list(self._curves):
            if key not in series:
                self.plot.removeItem(self._curves.pop(key))
        self.plot.setXRange(0, history.window_s)
