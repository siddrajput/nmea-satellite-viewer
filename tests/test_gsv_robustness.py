"""GSV robustness tests: trailing commas, PRN remapping, staleness.
Run with: python3 tests/test_gsv_robustness.py"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nmea_viewer.io import _sentence
from nmea_viewer.parser import _detect_gsv_width, NmeaParser


def _feed(body):
    p = NmeaParser()
    assert p.feed_line(_sentence(body)) == "GSV"
    return p


def _sats(p):
    return {s.label: s for s in p.get_satellites(max_age=3600)}


def test_detect_width():
    assert _detect_gsv_width(["02", "17", "228", "45"] * 4) == 4
    assert _detect_gsv_width(["02", "17", "228", "45", "1"] * 4) == 5
    assert _detect_gsv_width(["02", "17", "228", "45"] * 3) == 4
    assert _detect_gsv_width(["02", "17", "228", "45", "1"] * 3) == 5
    # Single trailing comma: strip the minimum to disambiguate.
    assert _detect_gsv_width(
        ["02", "17", "228", "45", "04", "40", "070", "47", ""]) == 4
    assert _detect_gsv_width(
        ["02", "17", "228", "45", "1", "04", "40", "070", "47", "1", ""]) == 5
    # Legitimately empty final C/No must NOT be stripped into ambiguity.
    assert _detect_gsv_width(
        ["03", "03", "111", "", "04", "15", "270", "",
         "06", "01", "010", "", "13", "06", "292", ""]) == 4
    print("PASS test_detect_width")


def test_trailing_comma_legacy():
    # The reported bug: phantom PRN 40, wrong band, lost C/No.
    p = _feed("GPGSV,1,1,02,02,17,228,45,04,40,070,47,")
    sats = _sats(p)
    assert set(sats) == {"G02", "G04"}, sats.keys()
    assert sats["G02"].cn0 == 45.0 and sats["G02"].band == "Unknown"
    assert sats["G04"].cn0 == 47.0
    assert sats["G04"].elevation == 40.0 and sats["G04"].azimuth == 70.0
    print("PASS test_trailing_comma_legacy")


def test_trailing_comma_41():
    p = _feed("GPGSV,1,1,02,02,17,228,45,1,04,40,070,47,1,")
    sats = _sats(p)
    assert set(sats) == {"G02", "G04"}, sats.keys()
    assert sats["G02"].band == "L1" and sats["G02"].signal_name == "L1 C/A"
    assert sats["G04"].cn0 == 47.0
    print("PASS test_trailing_comma_41")


def test_ublox_empty_cn0_untouched():
    p = _feed("GPGSV,3,1,11,03,03,111,,04,15,270,,06,01,010,,13,06,292,")
    sats = _sats(p)
    assert set(sats) == {"G03", "G04", "G06", "G13"}, sats.keys()
    assert all(s.cn0 is None for s in sats.values())
    assert sats["G13"].elevation == 6.0 and sats["G13"].azimuth == 292.0
    print("PASS test_ublox_empty_cn0_untouched")


def test_sbas_prn_remap():
    p = _feed("GPGSV,1,1,02,35,45,180,40,1,36,22,090,38,1")
    sats = _sats(p)
    assert set(sats) == {"S35", "S36"}, sats.keys()
    assert sats["S35"].constellation == "SBAS"
    assert sats["S35"].band == "L1"  # SBAS is L1
    print("PASS test_sbas_prn_remap")


def test_glonass_legacy_prn_remap():
    # NMEA 2.3 packing: GPGSV PRN 65-96 = GLONASS slot + 64.
    p = _feed("GPGSV,1,1,02,65,52,090,44,1,66,12,344,38,1")
    sats = _sats(p)
    assert set(sats) == {"R01", "R02"}, sats.keys()
    assert sats["R01"].constellation == "GLONASS"
    print("PASS test_glonass_legacy_prn_remap")


def test_qzss_high_prn_remap():
    p = _feed("GPGSV,1,1,01,194,55,200,42,1")
    sats = _sats(p)
    assert set(sats) == {"J194"}, sats.keys()
    assert sats["J194"].constellation == "QZSS"
    print("PASS test_qzss_high_prn_remap")


def test_staleness_window_30s():
    p = NmeaParser()
    p.feed_line(_sentence("GPGSV,1,1,01,02,17,228,45,1"))
    key = ("GP", 2, 1)
    # Simulate a slow receiver: last update 20 s ago.
    p.satellites[key].last_update = time.time() - 20.0
    assert len(p.get_satellites()) == 1, "20 s old sat must survive (30 s window)"
    p.satellites[key].last_update = time.time() - 31.0
    assert p.get_satellites() == [], "31 s old sat must be gone"
    print("PASS test_staleness_window_30s")


if __name__ == "__main__":
    test_detect_width()
    test_trailing_comma_legacy()
    test_trailing_comma_41()
    test_ublox_empty_cn0_untouched()
    test_sbas_prn_remap()
    test_glonass_legacy_prn_remap()
    test_qzss_high_prn_remap()
    test_staleness_window_30s()
    print("All GSV robustness tests passed.")
