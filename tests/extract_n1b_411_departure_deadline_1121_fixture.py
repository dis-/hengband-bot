"""Extract tests/fixtures/n1b-411-departure-deadline-1121/.

Source: n1-b life-411's stop of 2026-11-21 05:51:37 (town:blocked:stage-deadline:departure, bot
main a473e70fd), its town-arrival directory 20261121-055019.992594560-turn11279683 (the local copy
of the capture n1b-411-20261121-055141-town-blocked-stage-deadline-departure): the arrival
checkpoint (policy.pkl), all 267 journal rows (row 266 the stop) and the sidecar files the
restored policy reads, xz-compressed (tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_411_departure_deadline_1121_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-departure-deadline-1121"
ROWS = 267


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
