"""Parser tests. Run with: python3 tests/test_parser.py"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nmea_viewer.parser import NmeaParser, checksum_ok


def sent(body: str) -> str:
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"${body}*{cs:02X}"


def test_l1_l5_gsv():
    p = NmeaParser()
    # GPS L1 C/A (signal id 1)
    p.feed_line(sent("GPGSV,1,1,02,04,40,070,47,1,05,52,150,44,1"))
    # GPS L5 (signal id 7)
    p.feed_line(sent("GPGSV,1,1,02,04,40,070,43,7,05,52,150,40,7"))
    sats = p.get_satellites()
    assert len(sats) == 4, f"expected 4 entries, got {len(sats)}"
    by_band = {}
    for s in sats:
        by_band.setdefault(s.band, []).append(s.label)
    assert sorted(by_band["L1"]) == ["G04", "G05"], by_band
    assert sorted(by_band["L5"]) == ["G04", "G05"], by_band
    # same PRN on two bands -> separate entries
    g04 = [s for s in sats if s.label == "G04"]
    assert len(g04) == 2
    l5 = [s for s in g04 if s.band == "L5"][0]
    assert l5.signal_id == 7 and l5.signal_name == "L5-I"
    assert l5.cn0 == 43.0 and l5.elevation == 40.0 and l5.azimuth == 70.0
    print("PASS test_l1_l5_gsv")


def test_legacy_gsv_no_signal_id():
    p = NmeaParser()
    p.feed_line(sent("GPGSV,1,1,02,04,40,070,47,05,52,150,44"))
    sats = p.get_satellites()
    assert len(sats) == 2
    assert all(s.band == "Unknown" for s in sats), [s.band for s in sats]
    assert all(s.signal_id is None for s in sats)
    print("PASS test_legacy_gsv_no_signal_id")


def test_multi_constellation():
    p = NmeaParser()
    p.feed_line(sent("GLGSV,1,1,01,03,45,180,43,1"))
    p.feed_line(sent("GAGSV,1,1,02,11,33,250,44,1,19,58,040,42,7"))
    sats = p.get_satellites()
    labels = sorted(s.label for s in sats)
    assert labels == ["E11", "E19", "R03"], labels
    consts = {s.label: s.constellation for s in sats}
    assert consts == {"E11": "Galileo", "E19": "Galileo", "R03": "GLONASS"}
    e19 = [s for s in sats if s.label == "E19"][0]
    assert e19.band == "L5"  # Galileo E5a shares signal id 7
    print("PASS test_multi_constellation")


def test_gga():
    p = NmeaParser()
    p.feed_line(sent("GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"))
    f = p.fix
    assert f["utc_time"] == "12:35:19", f
    assert abs(f["latitude"] - 48.1173) < 1e-4, f
    assert abs(f["longitude"] - 11.5167) < 1e-4, f
    assert f["fix_quality"] == "GNSS fix"
    assert f["sats_used"] == 8
    assert f["hdop"] == 0.9
    assert f["altitude_m"] == 545.4
    print("PASS test_gga")


def test_rmc():
    p = NmeaParser()
    p.feed_line(sent("GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W"))
    f = p.fix
    assert f["status"] == "Active"
    assert f["utc_date"] == "2094-03-23", f
    assert f["speed_knots"] == 22.4
    assert f["course_deg"] == 84.4
    print("PASS test_rmc")


def test_gsa():
    p = NmeaParser()
    prns = ["04", "05", "09", "12", "24"] + [""] * 7  # 12 PRN slots
    assert len(prns) == 12
    body = "GPGSA,A,3," + ",".join(prns) + ",2.5,1.3,2.1"
    p.feed_line(sent(body))
    g = p.gsa
    assert g["fix_type"] == "3D", g
    assert g["sats_in_fix"] == [4, 5, 9, 12, 24], g
    assert g["pdop"] == 2.5 and g["hdop"] == 1.3 and g["vdop"] == 2.1
    print("PASS test_gsa")


def test_bad_checksum_rejected():
    p = NmeaParser()
    good = sent("GPGSV,1,1,01,04,40,070,47,1")
    bad = good[:-2] + "00"  # corrupt checksum
    assert checksum_ok(good)
    assert not checksum_ok(bad)
    assert p.feed_line(bad) is None
    assert p.get_satellites() == []
    assert p.feed_line(good) == "GSV"
    assert len(p.get_satellites()) == 1
    print("PASS test_bad_checksum_rejected")


def test_signal_id_8_l5q():
    p = NmeaParser()
    p.feed_line(sent("GPGSV,1,1,01,04,40,070,42,8"))
    sats = p.get_satellites()
    assert len(sats) == 1
    s = sats[0]
    assert s.signal_id == 8
    assert s.band == "L5", s.band
    assert s.signal_name == "L5-Q", s.signal_name
    print("PASS test_signal_id_8_l5q")


def test_empty_snr_kept():
    p = NmeaParser()
    # satellite visible but no C/No reported
    p.feed_line(sent("GPGSV,1,1,01,04,40,070,,1"))
    sats = p.get_satellites()
    assert len(sats) == 1 and sats[0].cn0 is None
    print("PASS test_empty_snr_kept")


if __name__ == "__main__":
    test_l1_l5_gsv()
    test_legacy_gsv_no_signal_id()
    test_multi_constellation()
    test_gga()
    test_rmc()
    test_gsa()
    test_bad_checksum_rejected()
    test_signal_id_8_l5q()
    test_empty_snr_kept()
    print("All parser tests passed.")
