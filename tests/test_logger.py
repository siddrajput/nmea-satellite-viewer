"""Logger + replay-reader tests. Run with: python3 tests/test_logger.py"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nmea_viewer.logger import NmeaLogger, ReplayReader


def _write_sample(path):
    with open(path, "w") as fh:
        fh.write("# nmea log started 2026-10-05T00:00:00+00:00\n")
        fh.write("2026-10-05T00:00:00+00:00 $GPGSV,1,1,02,04,40,070,45,1*00\n")
        fh.write("2026-10-05T00:00:02.500000+00:00 $GPGSV,1,1,02,04,40,070,44,1*00\n")
        fh.write("garbage line without timestamp\n")
        fh.write("2026-10-05T00:00:05+00:00 $GPGGA,000005,,,,,,0,,,,,,*00\n")
        fh.write("# nmea log stopped 2026-10-05T00:00:06+00:00\n")


def test_logger_writes_timestamped_lines():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nmea-test.log")
        lg = NmeaLogger()
        assert not lg.active
        lg.start(path)
        assert lg.active
        lg.write("$GPGSV,1,1,02,04,40,070,45,1*00")
        lg.write("not a sentence")  # ignored: must start with $
        lg.stop()
        assert not lg.active
        with open(path) as fh:
            lines = [l for l in fh.read().splitlines() if not l.startswith("#")]
        assert len(lines) == 1, lines
        assert lines[0].endswith("$GPGSV,1,1,02,04,40,070,45,1*00"), lines[0]
    print("PASS test_logger_writes_timestamped_lines")


def test_replay_reader_events_and_timing():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nmea-test.log")
        _write_sample(path)
        evts = ReplayReader(path).events()
        assert len(evts) == 3, evts
        dts = [e[0] for e in evts]
        assert dts[0] == 0.0, dts
        assert abs(dts[1] - 2.5) < 1e-6, dts
        assert abs(dts[2] - 5.0) < 1e-6, dts
        assert evts[0][1].startswith("$GPGSV")
        assert evts[2][1].startswith("$GPGGA")
    print("PASS test_replay_reader_events_and_timing")


def test_replay_reader_empty_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "empty.log")
        open(path, "w").write("# nothing here\n")
        assert ReplayReader(path).events() == []
    print("PASS test_replay_reader_empty_file")


if __name__ == "__main__":
    test_logger_writes_timestamped_lines()
    test_replay_reader_events_and_timing()
    test_replay_reader_empty_file()
    print("All logger tests passed.")
