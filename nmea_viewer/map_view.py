"""Live Google Map of the GNSS fix.

Uses the Google Maps embed endpoint, so no API key is needed. The map
recenters (throttled by distance) as the receiver moves.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    _HAVE_WEBENGINE = True
except ImportError:  # PyQtWebEngine not installed
    _HAVE_WEBENGINE = False


def map_embed_url(lat: float, lon: float, zoom: int = 16) -> str:
    """Google Maps embed URL centered on lat/lon. No API key required."""
    return f"https://maps.google.com/maps?q={lat:.6f},{lon:.6f}&z={zoom}&output=embed"


def map_embed_html(lat: float, lon: float, zoom: int = 16) -> str:
    """Full-page wrapper for the embed URL.

    Google's embed endpoint refuses to render as a top-level page
    ("The Google Maps Embed API must be used in an iframe"), so the
    map view loads this iframe wrapper instead. No API key required.
    """
    url = map_embed_url(lat, lon, zoom)
    return (
        "<html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;height:100%}"
        "iframe{border:0;width:100vw;height:100vh}</style>"
        "</head><body>"
        f"<iframe src='{url}' allowfullscreen></iframe>"
        "</body></html>"
    )


def _distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Equirectangular distance approximation; fine for short hops."""
    r = 6371000.0
    x = math.radians(b_lon - a_lon) * math.cos(math.radians((a_lat + b_lat) / 2.0))
    y = math.radians(b_lat - a_lat)
    return r * math.hypot(x, y)


class MapView(QWidget):
    """A Google Map that follows the receiver's position fix."""

    # Only reload the embed once the fix has moved this far, to avoid
    # hammering maps.google.com on every refresh tick.
    RELOAD_THRESHOLD_M = 25.0

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self._status = QLabel("Waiting for GNSS fix…")
        layout.addWidget(self._status)
        self._lat: float | None = None
        self._lon: float | None = None
        if _HAVE_WEBENGINE:
            self._view = QWebEngineView(self)
            layout.addWidget(self._view, 1)
        else:
            self._view = None
            missing = QLabel(
                "Map unavailable — install PyQtWebEngine:\n\npip install PyQtWebEngine")
            missing.setAlignment(Qt.AlignCenter)
            layout.addWidget(missing, 1)

    def update_position(self, lat: float | None, lon: float | None) -> None:
        if lat is None or lon is None:
            return
        self._status.setText(f"{lat:.6f}, {lon:.6f}")
        if not _HAVE_WEBENGINE or self._view is None:
            return
        if (self._lat is None
                or _distance_m(self._lat, self._lon, lat, lon) >= self.RELOAD_THRESHOLD_M):
            self._lat, self._lon = lat, lon
            # setHtml (not load): the embed URL must live inside an iframe.
            self._view.setHtml(map_embed_html(lat, lon), QUrl("https://localhost/"))
