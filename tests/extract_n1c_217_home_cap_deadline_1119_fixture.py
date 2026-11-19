"""Extract tests/fixtures/n1c-217-home-cap-deadline-1119/.

Source: n1-c life-217's stop of 2026-11-19 16:16:19 (town:blocked:stage-deadline:buy, bot main
53c53f00d8), its town-arrival directory 20261119-161501.015388709-turn4830134 (the live
capture's copy, read-only): the arrival
checkpoint (policy.pkl, a Linux pickle), all 283 journal rows (row 282 the stop) and the
sidecar files the restored policy reads, xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1c_217_home_cap_deadline_1119_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-home-cap-deadline-1119"
ROWS = 283


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
