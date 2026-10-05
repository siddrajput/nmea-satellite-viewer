"""PyQt5 main window: live C/No bar graphs with L1/L5 band separation,
plus skyplot, C/No history, DOP trends, position track, alerts,
NMEA logging/replay, and a live map."""

from __future__ import annotations

import os
import time
from datetime import datetime

import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QMainWindow, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .alerts import AlertEngine
from .alerts_view import AlertsView
from .cn0_history_view import Cn0HistoryView
from .dop_view import DopView
from .history import HistoryRecorder
from .io import BAUD_RATES, NmeaSimulator, SerialReader, list_serial_ports
from .logger import NmeaLogger, NmeaReplayer
from .map_view import MapView
from .parser import BAND_ORDER, NmeaParser
from .skyplot import SkyplotView
from .track_view import TrackView

BAND_COLORS = {
    "L1": QColor(76, 154, 255),    # blue
    "L5": QColor(255, 86, 48),     # red-orange
    "L2": QColor(54, 179, 126),    # green
    "Unknown": QColor(151, 160, 175),  # gray
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NMEA Satellite Viewer")
        self.resize(1100, 800)

        self.parser = NmeaParser()
        self.reader: SerialReader | None = None
        self.sim: NmeaSimulator | None = None
        self._bars = None

        self.history = HistoryRecorder(window_s=300.0)
        self.alert_engine = AlertEngine()
        self.nmea_logger = NmeaLogger()
        self.replayer: NmeaReplayer | None = None

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addLayout(self._build_connection_bar())
        layout.addWidget(self._build_info_panel())

        splitter = QSplitter(Qt.Vertical)

        chart_box = QGroupBox("C/No per satellite (dB-Hz)")
        chart_layout = QVBoxLayout(chart_box)
        chart_layout.addLayout(self._build_band_filters())
        pg.setConfigOptions(antialias=True)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("left", "C/No", units="dB-Hz")
        self.plot.setLabel("bottom", "Satellite")
        self.plot.setYRange(0, 60)
        self.plot.showGrid(x=False, y=True, alpha=0.3)
        chart_layout.addWidget(self.plot)

        tabs = QTabWidget()
        tabs.addTab(chart_box, "C/No")
        self.skyplot_view = SkyplotView()
        tabs.addTab(self.skyplot_view, "Skyplot")
        self.cn0_history_view = Cn0HistoryView()
        tabs.addTab(self.cn0_history_view, "C/No history")
        self.dop_view = DopView()
        tabs.addTab(self.dop_view, "DOP")
        self.track_view = TrackView()
        self.track_view.on_clear(lambda: self.history.fixes.clear())
        tabs.addTab(self.track_view, "Track")
        self.alerts_view = AlertsView(self.alert_engine)
        tabs.addTab(self.alerts_view, "Alerts")
        self.map_view = MapView()
        tabs.addTab(self.map_view, "Map")
        splitter.addWidget(tabs)

        table_box = QGroupBox("Satellites in view")
        table_layout = QVBoxLayout(table_box)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Sat", "Constellation", "Band", "Signal", "Elev (°)", "Azim (°)", "C/No"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_box)

        splitter.setSizes([520, 220])
        layout.addWidget(splitter)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(1000)

    # ------------------------------------------------------------ builders
    def _build_connection_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(140)
        self._refresh_ports()
        bar.addWidget(self.port_combo)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(32)
        refresh_btn.setToolTip("Rescan serial ports")
        refresh_btn.clicked.connect(self._refresh_ports)
        bar.addWidget(refresh_btn)

        bar.addWidget(QLabel("Baud:"))
        self.baud_combo = QComboBox()
        for b in BAUD_RATES:
            self.baud_combo.addItem(str(b), b)
        self.baud_combo.setCurrentText("115200")
        bar.addWidget(self.baud_combo)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        bar.addWidget(self.connect_btn)

        self.sim_check = QCheckBox("Simulate NMEA (no hardware)")
        self.sim_check.toggled.connect(self._on_sim_toggled)
        bar.addWidget(self.sim_check)

        self.log_btn = QPushButton("Log")
        self.log_btn.setCheckable(True)
        self.log_btn.setToolTip("Log raw NMEA sentences to a timestamped file")
        self.log_btn.clicked.connect(self._toggle_logging)
        self.log_btn.setEnabled(False)
        bar.addWidget(self.log_btn)

        self.replay_btn = QPushButton("Replay…")
        self.replay_btn.setToolTip("Replay a logged NMEA file through the UI")
        self.replay_btn.clicked.connect(self._start_replay)
        bar.addWidget(self.replay_btn)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["1×", "4×", "10×", "60×"])
        self.speed_combo.setCurrentText("4×")
        self.speed_combo.setToolTip("Replay speed")
        bar.addWidget(self.speed_combo)

        bar.addStretch(1)
        self.alert_status = QLabel("Alerts: OK")
        bar.addWidget(self.alert_status)
        self.status_label = QLabel("Disconnected")
        bar.addWidget(self.status_label)
        return bar

    def _build_info_panel(self) -> QGroupBox:
        box = QGroupBox("Receiver fix")
        grid = QGridLayout(box)
        self.info_labels: dict[str, QLabel] = {}
        fields = [
            ("utc", "UTC time"), ("date", "Date"),
            ("lat", "Latitude"), ("lon", "Longitude"),
            ("fix", "Fix"), ("sats", "Sats used/view"),
            ("hdop", "HDOP"), ("dop", "PDOP/VDOP"),
            ("speed", "Speed (kn)"), ("course", "Course (°)"),
        ]
        for i, (key, title) in enumerate(fields):
            grid.addWidget(QLabel(f"<b>{title}:</b>"), i // 5, (i % 5) * 2)
            val = QLabel("—")
            self.info_labels[key] = val
            grid.addWidget(val, i // 5, (i % 5) * 2 + 1)
        return box

    def _build_band_filters(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Show bands:"))
        self.band_checks: dict[str, QCheckBox] = {}
        for band in ("L1", "L5", "L2", "Unknown"):
            cb = QCheckBox(band)
            cb.setChecked(True)
            color = BAND_COLORS[band]
            cb.setStyleSheet(
                f"QCheckBox {{ color: rgb({color.red()},{color.green()},{color.blue()}); "
                f"font-weight: bold; }}")
            self.band_checks[band] = cb
            row.addWidget(cb)
        row.addStretch(1)
        self.count_label = QLabel("")
        row.addWidget(self.count_label)
        return row

    # ------------------------------------------------------------ connection
    def _refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = list_serial_ports()
        self.port_combo.addItems(ports)
        if current in ports:
            self.port_combo.setCurrentText(current)

    def _on_sim_toggled(self, on: bool) -> None:
        self.port_combo.setEnabled(not on)
        self.baud_combo.setEnabled(not on)

    def _toggle_connection(self) -> None:
        if self.reader or self.sim:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        if self.sim_check.isChecked():
            self.sim = NmeaSimulator(self)
            self.sim.line_generated.connect(self._on_line)
            self.sim.start()
            self.status_label.setText("Simulating NMEA data")
            self.connect_btn.setText("Disconnect")
            self.log_btn.setEnabled(True)
            return
        port = self.port_combo.currentText()
        if not port:
            self.status_label.setText("No serial port selected")
            return
        baud = self.baud_combo.currentData()
        self.reader = SerialReader(port, baud, self)
        self.reader.line_received.connect(self._on_line)
        self.reader.connection_error.connect(self._on_conn_error)
        self.reader.disconnected.connect(self._on_disconnected)
        self.reader.start()
        self.status_label.setText(f"Opening {port} @ {baud}…")
        self.connect_btn.setText("Disconnect")
        self.log_btn.setEnabled(True)

    def _disconnect(self) -> None:
        self._stop_logging()
        self._stop_replay()
        if self.sim:
            self.sim.stop()
            self.sim = None
        if self.reader:
            self.reader.stop()
            self.reader = None
        self.log_btn.setEnabled(False)
        self.status_label.setText("Disconnected")
        self.connect_btn.setText("Connect")

    def _on_conn_error(self, msg: str) -> None:
        self.status_label.setText(msg)
        self._disconnect()

    def _on_disconnected(self) -> None:
        if self.connect_btn.text() == "Disconnect":
            self.status_label.setText("Disconnected")
            self.connect_btn.setText("Connect")
        self.reader = None

    def _on_line(self, line: str) -> None:
        self.parser.feed_line(line)
        self.nmea_logger.write(line)

    # --------------------------------------------------- logging and replay
    def _toggle_logging(self) -> None:
        if self.nmea_logger.active:
            self._stop_logging()
        else:
            os.makedirs("logs", exist_ok=True)
            path = os.path.join(
                "logs",
                "nmea-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".log")
            self.nmea_logger.start(path)
            self.log_btn.setChecked(True)
            self.log_btn.setText("Logging…")
            self.status_label.setText(f"Logging to {path}")

    def _stop_logging(self) -> None:
        if self.nmea_logger.active:
            self.nmea_logger.stop()
        self.log_btn.setChecked(False)
        self.log_btn.setText("Log")

    def _start_replay(self) -> None:
        if self.replayer is not None:
            self._stop_replay()
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Replay NMEA log", "logs", "NMEA logs (*.log);;All files (*)")
        if not path:
            return
        speed = float(self.speed_combo.currentText().replace("×", ""))
        self.replayer = NmeaReplayer(path, speed=speed, parent=self)
        if self.replayer.event_count == 0:
            self.status_label.setText("Replay file has no NMEA sentences")
            self.replayer = None
            return
        self.replayer.line_ready.connect(self._on_line)
        self.replayer.finished.connect(self._on_replay_done)
        self.replay_btn.setText("Stop replay")
        self.connect_btn.setEnabled(False)
        mins = self.replayer.duration_s / 60
        self.status_label.setText(
            f"Replaying {os.path.basename(path)} @ {speed:g}× "
            f"({self.replayer.event_count} sentences, {mins:.1f} min logged)")
        self.replayer.start()

    def _stop_replay(self) -> None:
        if self.replayer is not None:
            try:
                self.replayer.finished.disconnect(self._on_replay_done)
            except TypeError:
                pass
            self.replayer.stop()
            self.replayer = None
        self.replay_btn.setText("Replay…")
        self.connect_btn.setEnabled(True)

    def _on_replay_done(self) -> None:
        self.replayer = None
        self.replay_btn.setText("Replay…")
        self.connect_btn.setEnabled(True)
        self.status_label.setText("Replay finished")

    # --------------------------------------------------------------- refresh
    def _enabled_bands(self) -> set[str]:
        return {b for b, cb in self.band_checks.items() if cb.isChecked()}

    def refresh(self) -> None:
        now = time.time()
        self.parser.prune()
        sats = self.parser.get_satellites()
        enabled = self._enabled_bands()
        visible = [s for s in sats if s.band in enabled]

        counts = {b: sum(1 for s in sats if s.band == b) for b in BAND_ORDER}
        self.count_label.setText(
            "   ".join(f"{b}: {counts[b]}" for b in ("L1", "L5", "L2", "Unknown")))

        self.history.record_tick(sats, self.parser.fix, self.parser.gsa, now=now)

        self._update_bars(visible)
        self._update_table(sats)
        self._update_info()
        self.skyplot_view.update(visible)
        self.cn0_history_view.update(self.history)
        self.dop_view.update(self.history)
        self.track_view.update(self.history)
        self.map_view.update_position(
            self.parser.fix.get("latitude"), self.parser.fix.get("longitude"))

        new_alerts = self.alert_engine.check(now, sats, self.parser.fix)
        if new_alerts:
            self.alerts_view.push(new_alerts)
            n_crit = sum(1 for a in new_alerts if a.severity == "crit")
            self.alert_status.setText(
                f"Alerts: {len(new_alerts)} new"
                + (" (CRIT)" if n_crit else ""))
            self.alert_status.setStyleSheet(
                "color: #c41e1e; font-weight: bold;")
        elif self.alerts_view._list.count() == 0:
            self.alert_status.setText("Alerts: OK")
            self.alert_status.setStyleSheet("")

    def _update_bars(self, sats: list) -> None:
        if self._bars is not None:
            self.plot.removeItem(self._bars)
            self._bars = None
        if not sats:
            self.plot.getAxis("bottom").setTicks([[]])
            return
        xs = list(range(len(sats)))
        heights = [s.cn0 if s.cn0 is not None else 0 for s in sats]
        brushes = [pg.mkBrush(BAND_COLORS[s.band]) for s in sats]
        self._bars = pg.BarGraphItem(x=xs, height=heights, width=0.6, brushes=brushes)
        self.plot.addItem(self._bars)
        ticks = [[(i, f"{s.label}\n{s.band}") for i, s in enumerate(sats)]]
        self.plot.getAxis("bottom").setTicks(ticks)

    def _update_table(self, sats: list) -> None:
        self.table.setRowCount(len(sats))
        for r, s in enumerate(sats):
            vals = [
                s.label,
                s.constellation,
                s.band,
                s.signal_name,
                f"{s.elevation:.0f}" if s.elevation is not None else "—",
                f"{s.azimuth:.0f}" if s.azimuth is not None else "—",
                f"{s.cn0:.0f}" if s.cn0 is not None else "—",
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c == 2:  # band column tint
                    color = BAND_COLORS[s.band]
                    item.setBackground(color.lighter(170))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()

    def _update_info(self) -> None:
        fix, gsa = self.parser.fix, self.parser.gsa
        lat, lon = fix.get("latitude"), fix.get("longitude")
        sats_used = fix.get("sats_used")
        sats_view = len(self.parser.get_satellites())
        set_text = self.info_labels
        set_text["utc"].setText(fix.get("utc_time") or "—")
        set_text["date"].setText(fix.get("utc_date") or "—")
        set_text["lat"].setText(f"{lat:.6f}" if lat is not None else "—")
        set_text["lon"].setText(f"{lon:.6f}" if lon is not None else "—")
        set_text["fix"].setText(
            f"{fix.get('fix_quality') or '—'}"
            + (f" ({gsa.get('fix_type')})" if gsa.get("fix_type") else ""))
        set_text["sats"].setText(
            f"{sats_used if sats_used is not None else '—'} / {sats_view}")
        hdop = fix.get("hdop")
        set_text["hdop"].setText(f"{hdop:.1f}" if hdop is not None else "—")
        pdop, vdop = gsa.get("pdop"), gsa.get("vdop")
        set_text["dop"].setText(
            f"{pdop:.1f} / {vdop:.1f}" if pdop is not None and vdop is not None else "—")
        spd = fix.get("speed_knots")
        set_text["speed"].setText(f"{spd:.1f}" if spd is not None else "—")
        crs = fix.get("course_deg")
        set_text["course"].setText(f"{crs:.0f}" if crs is not None else "—")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._stop_logging()
        self._stop_replay()
        self._disconnect()
        super().closeEvent(event)
