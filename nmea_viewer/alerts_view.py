"""Alerts tab: threshold configuration and the alert log."""

from __future__ import annotations

from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .alerts import Alert


class AlertsView(QWidget):
    """Configure thresholds and show timestamped alerts (newest first)."""

    MAX_ENTRIES = 200

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._engine = engine
        layout = QVBoxLayout(self)

        cfg = QGroupBox("Alert thresholds")
        form = QFormLayout(cfg)
        self.cn0_spin = QDoubleSpinBox()
        self.cn0_spin.setRange(10, 55)
        self.cn0_spin.setValue(engine.cn0_min)
        self.cn0_spin.setSuffix(" dB-Hz")
        self.cn0_spin.valueChanged.connect(self._apply)
        form.addRow("C/No below", self.cn0_spin)

        self.sats_spin = QSpinBox()
        self.sats_spin.setRange(1, 30)
        self.sats_spin.setValue(engine.min_sats_view)
        self.sats_spin.valueChanged.connect(self._apply)
        form.addRow("Sats in view below", self.sats_spin)

        self.fix_spin = QSpinBox()
        self.fix_spin.setRange(2, 120)
        self.fix_spin.setValue(int(engine.fix_lost_timeout_s))
        self.fix_spin.setSuffix(" s")
        self.fix_spin.valueChanged.connect(self._apply)
        form.addRow("Fix lost after", self.fix_spin)
        layout.addWidget(cfg)

        row = QHBoxLayout()
        self.status_label = QLabel("No alerts")
        row.addWidget(self.status_label, 1)
        layout.addLayout(row)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        layout.addWidget(self._list, 1)

        clear_btn = QPushButton("Clear log")
        clear_btn.clicked.connect(self._list.clear)
        row.addWidget(clear_btn)

    # ------------------------------------------------------------------ slots
    def _apply(self) -> None:
        self._engine.cn0_min = self.cn0_spin.value()
        self._engine.min_sats_view = self.sats_spin.value()
        self._engine.fix_lost_timeout_s = float(self.fix_spin.value())

    def push(self, alerts: list[Alert]) -> None:
        for a in alerts:
            ts = datetime.fromtimestamp(a.t).strftime("%H:%M:%S")
            item = QListWidgetItem(f"[{ts}] {a.message}")
            color = QColor(214, 48, 49) if a.severity == "crit" else QColor(200, 120, 0)
            item.setForeground(color)
            self._list.insertItem(0, item)
        while self._list.count() > self.MAX_ENTRIES:
            self._list.takeItem(self._list.count() - 1)
        self._refresh_status()

    def _refresh_status(self) -> None:
        n = self._list.count()
        if n == 0:
            self.status_label.setText("No alerts")
            self.status_label.setStyleSheet("")
        else:
            self.status_label.setText(f"{n} alert{'s' if n != 1 else ''}")
            self.status_label.setStyleSheet("color: #c41e1e; font-weight: bold;")
