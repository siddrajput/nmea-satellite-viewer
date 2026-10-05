"""History recorder tests. Run with: python3 tests/test_history.py"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nmea_viewer.history import HistoryRecorder
from nmea_viewer.parser import Satellite


def _sat(code="G", prn=4, band="L1", cn0=45.0):
    return Satellite(constellation="GPS", code=code, prn=prn,
                     elevation=40.0, azimuth=70.0, cn0=cn0,
                     signal_id=1, signal_name="L1 C/A", band=band,
                     last_update=time.time())


def test_cn0_series_recorded():
    h = HistoryRecorder(window_s=60.0)
    t = 1000.0
    h.record_tick([_sat(cn0=45.0)], {"hdop": 1.0}, {"pdop": 2.0, "vdop": 1.5}, now=t)
    h.record_tick([_sat(cn0=44.0)], {"hdop": 1.1}, {"pdop": 2.1, "vdop": 1.6}, now=t + 1)
    s = h.cn0_series()
    assert ("G", 4, "L1") in s, s.keys()
    assert [c for _, c in s[("G", 4, "L1")]] == [45.0, 44.0]
    d = h.dop_series()
    assert d == [(t, 1.0, 2.0, 1.5), (t + 1, 1.1, 2.1, 1.6)], d
    print("PASS test_cn0_series_recorded")


def test_window_prunes_old_samples():
    h = HistoryRecorder(window_s=10.0)
    h.record_tick([_sat(cn0=45.0)], {"hdop": 1.0}, {"pdop": 2.0, "vdop": 1.5},
                  now=1000.0)
    h.record_tick([_sat(cn0=44.0)], {"hdop": 1.0}, {"pdop": 2.0, "vdop": 1.5},
                  now=1020.0)
    s = h.cn0_series()
    # Old sample aged out; only the fresh one remains.
    assert s[("G", 4, "L1")] == [(1020.0, 44.0)], s
    assert len(h.dop_series()) == 1, h.dop_series()
    print("PASS test_window_prunes_old_samples")


def test_fix_points_only_with_position():
    h = HistoryRecorder(window_s=60.0)
    h.record_tick([], {"latitude": None, "longitude": None, "fix_quality": "Invalid"},
                  {}, now=1000.0)
    assert h.fix_points() == []
    h.record_tick([], {"latitude": 32.7, "longitude": -117.1,
                       "fix_quality": "GNSS fix", "sats_used": 9},
                  {}, now=1001.0)
    pts = h.fix_points()
    assert len(pts) == 1 and pts[0].lat == 32.7 and pts[0].sats_used == 9
    print("PASS test_fix_points_only_with_position")


def test_clear():
    h = HistoryRecorder(window_s=60.0)
    h.record_tick([_sat()], {"hdop": 1.0, "latitude": 1.0, "longitude": 2.0},
                  {"pdop": 2.0, "vdop": 1.5}, now=1000.0)
    h.clear()
    assert h.cn0_series() == {} and h.dop_series() == [] and h.fix_points() == []
    print("PASS test_clear")


if __name__ == "__main__":
    test_cn0_series_recorded()
    test_window_prunes_old_samples()
    test_fix_points_only_with_position()
    test_clear()
    print("All history tests passed.")
