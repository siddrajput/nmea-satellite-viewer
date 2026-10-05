"""Alert engine tests. Run with: python3 tests/test_alerts.py"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nmea_viewer.alerts import AlertEngine
from nmea_viewer.parser import Satellite


def _sat(code="G", prn=4, band="L1", cn0=45.0):
    return Satellite(constellation="GPS", code=code, prn=prn,
                     elevation=40.0, azimuth=70.0, cn0=cn0,
                     signal_id=1, signal_name="L1 C/A", band=band,
                     last_update=time.time())


def _good_fix():
    return {"fix_quality": "GNSS fix", "status": "Active"}


def test_cn0_drop_fires_once_and_rearms():
    e = AlertEngine(cn0_min=30.0, cn0_hysteresis=3.0)
    healthy = [_sat(prn=i, cn0=45.0) for i in range(5)]
    assert e.check(1000.0, healthy, _good_fix()) == []
    # Drop one sat below threshold -> one alert.
    low = [_sat(prn=0, cn0=25.0)] + [_sat(prn=i, cn0=45.0) for i in range(1, 5)]
    a = e.check(1001.0, low, _good_fix())
    assert len(a) == 1 and "G00" in a[0].message and a[0].severity == "warn", a
    # Still low -> no repeat.
    assert e.check(1002.0, low, _good_fix()) == []
    # Partial recovery (below re-arm level) -> still no new alert.
    recovering = [_sat(prn=0, cn0=31.0)] + [_sat(prn=i, cn0=45.0) for i in range(1, 5)]
    assert e.check(1003.0, recovering, _good_fix()) == []
    # Full recovery above threshold + hysteresis -> re-arms silently.
    recovered = [_sat(prn=0, cn0=34.0)] + [_sat(prn=i, cn0=45.0) for i in range(1, 5)]
    assert e.check(1004.0, recovered, _good_fix()) == []
    # Drop again -> fires again.
    a = e.check(1005.0, low, _good_fix())
    assert len(a) == 1, a
    print("PASS test_cn0_drop_fires_once_and_rearms")


def test_fix_lost_needs_timeout_then_rearms():
    e = AlertEngine(fix_lost_timeout_s=10.0)
    sats = [_sat(prn=i) for i in range(5)]  # healthy sky: only the fix rule fires
    bad = {"fix_quality": "Invalid", "status": "Active"}
    assert e.check(1000.0, sats, bad) == []          # starts the clock
    assert e.check(1005.0, sats, bad) == []          # not yet 10 s
    a = e.check(1011.0, sats, bad)                   # past timeout
    assert len(a) == 1 and a[0].severity == "crit", a
    assert e.check(1020.0, sats, bad) == []          # no repeat
    assert e.check(1030.0, sats, _good_fix()) == []   # fix back, re-arm
    a = e.check(1041.0, sats, bad)                   # lost again: clock restarts
    assert a == []
    a = e.check(1052.0, sats, bad)
    assert len(a) == 1, a
    print("PASS test_fix_lost_needs_timeout_then_rearms")


def test_sats_in_view_collapse():
    e = AlertEngine(min_sats_view=4)
    sats = [_sat(prn=i) for i in range(5)]
    assert e.check(1000.0, sats, _good_fix()) == []
    a = e.check(1001.0, sats[:2], _good_fix())
    assert len(a) == 1 and "2 sats" in a[0].message, a
    assert e.check(1002.0, sats[:2], _good_fix()) == []  # no repeat
    assert e.check(1003.0, sats, _good_fix()) == []     # recovered
    a = e.check(1004.0, [], _good_fix())
    assert len(a) == 1 and "0 sats" in a[0].message, a
    print("PASS test_sats_in_view_collapse")


def test_no_spurious_alerts_when_healthy():
    e = AlertEngine()
    sats = [_sat(prn=i, cn0=40.0 + i) for i in range(8)]
    assert e.check(1000.0, sats, _good_fix()) == []
    assert e.check(1001.0, sats, _good_fix()) == []
    print("PASS test_no_spurious_alerts_when_healthy")


if __name__ == "__main__":
    test_cn0_drop_fires_once_and_rearms()
    test_fix_lost_needs_timeout_then_rearms()
    test_sats_in_view_collapse()
    test_no_spurious_alerts_when_healthy()
    print("All alert tests passed.")
