"""Parser fuzz test: malformed input must never raise and must not corrupt
good state. Deterministic (fixed seed). Run with: python3 tests/test_fuzz.py"""

import os
import random
import string
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nmea_viewer.io import _sentence
from nmea_viewer.parser import NmeaParser, checksum_ok

random.seed(20261005)
GOOD = _sentence("GPGSV,1,1,02,02,17,228,45,1,04,40,070,47,1")


def _rand_field():
    return "".join(random.choice(string.printable.strip() + ",.*$")
                   for _ in range(random.randint(0, 12)))


def _rand_line():
    kind = random.random()
    if kind < 0.4:
        return "".join(random.choice(string.printable)
                       for _ in range(random.randint(0, 200)))
    body = "$" + ",".join(_rand_field() for _ in range(random.randint(0, 25)))
    if random.random() < 0.5:
        body += "*" + "".join(random.choice("0123456789ABCDEFabcdefGZ")
                              for _ in range(random.randint(0, 4)))
    return body


def test_fuzz_no_raise():
    p = NmeaParser()
    p.feed_line(GOOD)
    for i in range(3000):
        line = _rand_line()
        p.feed_line(line)  # must never raise
        p.get_satellites()
        if i % 7 == 0:
            p.prune()
    sats = {s.label: s for s in p.get_satellites(max_age=3600)}
    g02 = sats.get("G02")
    assert g02 is not None and g02.cn0 == 45.0 and g02.band == "L1", \
        "good state must survive the fuzz storm"
    print("PASS test_fuzz_no_raise")


def test_checksum_edges():
    assert checksum_ok("no star here") is True
    assert checksum_ok("$A*ZZ") is False
    assert checksum_ok("$A*") is False
    assert checksum_ok("") is True
    print("PASS test_checksum_edges")


if __name__ == "__main__":
    test_fuzz_no_raise()
    test_checksum_edges()
    print("All fuzz tests passed.")
