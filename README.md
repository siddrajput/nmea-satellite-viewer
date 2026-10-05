# NMEA Satellite Viewer

A PyQt5 desktop app for live GNSS monitoring. It reads NMEA 0183 data from a
serial port, parses it, and shows a live sky view: C/No bar graphs per
satellite with **L1 vs L5 band separation**, a satellite table, and receiver
fix info.

No hardware? Tick **"Simulate NMEA (no hardware)"** to try it with generated
data.

## Features

- Live NMEA 0183 parsing from any serial port (configurable baud rate)
- C/No (dB-Hz) bar graph, color-coded by band: **L1** blue, **L5** red-orange,
  L2 green, unknown gray
- L1/L5 distinction via the NMEA 4.1+ GSV **signal ID** field
  (1 = L1 C/A, 7/8 = L5; also covers Galileo E1/E5a, BeiDou B1I/B2a, QZSS L1/L5)
- Per-band show/hide filters and live satellite counts
- Satellite table: PRN, constellation, band, signal, elevation, azimuth, C/No
- Fix panel: UTC time/date, lat/lon, fix quality, sats used/in view,
  HDOP, PDOP/VDOP, speed, course
- **Skyplot** tab: polar plot of satellite azimuth/elevation, colored by
  C/No or band
- **C/No history** tab: per-satellite strip charts over a rolling 5-minute
  window — spot fading, blockage, or multipath
- **DOP** tab: HDOP/PDOP/VDOP trending over the same window
- **Track** tab: position path in meters from the first fix, fix scatter
  colored by fix quality, and accuracy stats (σE/σN, 2DRMS, span)
- **Alerts** tab: configurable thresholds with a timestamped alert log —
  C/No drops below a threshold, fix lost, satellites-in-view collapse
- **Logging & replay**: record timestamped raw NMEA to `logs/`, then replay
  any capture through the UI at 1×/4×/10×/60× speed
- Live Google Map tab centered on the fix (no API key needed;
  requires PyQtWebEngine)
- Built-in NMEA simulator for testing without a receiver

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requirements: `PyQt5`, `pyqtgraph`, `pyserial`. Python 3.9+.

## Run

```bash
python3 main.py
```

1. Pick the serial port your GNSS receiver is on (↻ rescans) and its baud
   rate (common: 9600, 38400, 115200).
2. Press **Connect**. Or tick **Simulate NMEA** first to use fake data.

## How L1/L5 separation works

NMEA 0183 v4.10 GSV sentences carry a signal ID after each satellite's C/No:

```
$GPGSV,1,1,02,04,40,070,43,7,05,52,150,40,7*...
                                    ^  ^
                              C/No --+  +-- signal ID (7 = L5-I)
```

| Signal ID | Band | Meaning |
|-----------|------|---------|
| 1, 2, 3   | L1   | L1 C/A, L1 P(Y), L1 M (also G1/E1/B1I) |
| 4, 5, 6   | L2   | L2 P(Y), L2C-M, L2C-L |
| 7, 8      | L5   | L5-I, L5-Q (also E5a, B2a) |

Receivers on older NMEA 2.x firmware omit the signal ID; those satellites show
as band **Unknown** (gray). The same PRN tracked on two bands appears as two
bars (e.g. G04 on L1 and L5).

## Project layout

```
main.py                  entry point
nmea_viewer/
  parser.py              NMEA parsing (GSV/GGA/RMC/GSA), signal-ID -> band map
  io.py                  serial reader thread + NMEA simulator
  main_window.py         PyQt5 UI, pyqtgraph bar charts
  map_view.py            live Google Map of the fix (embed API, no key)
tests/
  test_parser.py         parser unit tests (run: python3 tests/test_parser.py)
```

## License

MIT.
