"""Map view tests. Run with: python3 tests/test_map.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nmea_viewer.map_view import _distance_m, map_embed_html, map_embed_url


def test_embed_url():
    u = map_embed_url(32.7157, -117.1611)
    assert u == "https://maps.google.com/maps?q=32.715700,-117.161100&z=16&output=embed", u
    u2 = map_embed_url(0.0, 0.0, zoom=10)
    assert "z=10" in u2 and "q=0.000000,0.000000" in u2, u2
    print("PASS test_embed_url")


def test_embed_html():
    html = map_embed_html(32.7157, -117.1611)
    assert "<iframe" in html and "</iframe>" in html, html[:120]
    assert "https://maps.google.com/maps?q=32.715700,-117.161100&z=16&output=embed" in html
    print("PASS test_embed_html")


def test_distance():
    assert _distance_m(32.0, -117.0, 32.0, -117.0) == 0.0
    d = _distance_m(32.7157, -117.1611, 32.7158, -117.1611)
    assert 8.0 < d < 15.0, d  # 0.0001 deg latitude ~= 11 m
    print("PASS test_distance")


if __name__ == "__main__":
    test_embed_url()
    test_embed_html()
    test_distance()
    print("All map tests passed.")
