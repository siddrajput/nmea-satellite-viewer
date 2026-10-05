"""Skyplot math + track math tests. Run with: python3 tests/test_geo_views.py"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nmea_viewer.skyplot import azel_to_xy, cn0_color
from nmea_viewer.track_view import to_meters, track_stats


def _close(a, b, tol=1e-9):
    assert abs(a - b) < tol, (a, b)


def test_azel_to_xy_cardinals():
    # North (az 0) is up, East (az 90) is right, zenith at origin.
    x, y = azel_to_xy(0, 90)
    _close(x, 0.0); _close(y, 0.0)
    x, y = azel_to_xy(0, 0)     # north horizon
    _close(x, 0.0); _close(y, 1.0)
    x, y = azel_to_xy(90, 0)    # east horizon
    _close(x, 1.0); _close(y, 0.0)
    x, y = azel_to_xy(180, 0)   # south
    _close(x, 0.0); _close(y, -1.0)
    x, y = azel_to_xy(270, 0)   # west
    _close(x, -1.0); _close(y, 0.0)
    x, y = azel_to_xy(45, 45)   # NE at 45° elevation -> r = 0.5
    _close(math.hypot(x, y), 0.5)
    _close(x, y)                # symmetric NE
    assert x > 0 and y > 0
    print("PASS test_azel_to_xy_cardinals")


def test_azel_to_xy_clamps():
    x, y = azel_to_xy(0, -10)   # below horizon clamps to rim
    _close(math.hypot(x, y), 1.0)
    x, y = azel_to_xy(0, 120)   # above zenith clamps to center
    _close(x, 0.0); _close(y, 0.0)
    print("PASS test_azel_to_xy_clamps")


def test_cn0_color_ramps():
    weak = cn0_color(20.0)
    strong = cn0_color(52.0)
    assert weak.red() > weak.blue(), "weak should be reddish"
    assert strong.blue() > strong.red(), "strong should be bluish"
    mid1, mid2 = cn0_color(35.0), cn0_color(36.0)
    assert (mid1.red(), mid1.green(), mid1.blue()) != \
           (mid2.red(), mid2.green(), mid2.blue()), "ramp should vary"
    assert cn0_color(None).getRgb()[:3] == (151, 160, 175)
    print("PASS test_cn0_color_ramps")


def test_to_meters():
    # ~111 m per 0.001 deg latitude.
    x, y = to_meters(32.7167, -117.1611, 32.7157, -117.1611)
    _close(x, 0.0, tol=1e-6)
    assert 105.0 < y < 118.0, y
    x, y = to_meters(32.7157, -117.1611, 32.7157, -117.1611)
    _close(x, 0.0); _close(y, 0.0)
    print("PASS test_to_meters")


def test_track_stats():
    assert track_stats([]) == {}
    st = track_stats([(0.0, 0.0)])
    assert st["n"] == 1 and st["sigma_e"] == 0.0 and st["span"] == 0.0, st
    st = track_stats([(1.0, 0.0), (-1.0, 0.0)])
    _close(st["sigma_e"], 1.0)
    _close(st["sigma_n"], 0.0)
    _close(st["rms_2d"], 2.0)
    _close(st["span"], 2.0)
    print("PASS test_track_stats")


if __name__ == "__main__":
    test_azel_to_xy_cardinals()
    test_azel_to_xy_clamps()
    test_cn0_color_ramps()
    test_to_meters()
    test_track_stats()
    print("All geo view tests passed.")
