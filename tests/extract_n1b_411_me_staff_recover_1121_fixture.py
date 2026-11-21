"""Extract tests/fixtures/n1b-411-me-staff-recover-1121/.

Source: n1-b life-411's stop of 2026-11-21 09:28:34 (quest:blocked:me-staff, bot main 9e5e69774),
its town-arrival directory 20261121-092830.662491761-turn11335422 (the local copy of the capture
n1b-411-20261121-092837-quest-blocked-me-staff): the arrival checkpoint (policy.pkl), all 9 journal
rows (row 8 the stop) and the sidecar files the restored policy reads, xz-compressed
(tests/support/town_arrival_fixture.py).

    python tests/extract_n1b_411_me_staff_recover_1121_fixture.py <town-arrival directory>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-me-staff-recover-1121"
ROWS = 9


if __name__ == "__main__":
    extract(Path(sys.argv[1]), FIXTURE, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
