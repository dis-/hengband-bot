"""Extract tests/fixtures/n1a-525-departure-1115/.

Source: n1-a life-525's town-arrival checkpoint of 2026-11-15 21:05:39 (turn 12038122), the
departure of the trip it died on (ガラスの城 49F, 21:06:00), copied read-only from the viewing
server's jsonlog/town-arrival/20261115-210539.396042856-turn12038122/ to
C:/hengband-backups/pdca/n1a-525-rules-1115/cap/town-arrival/: the arrival policy, the visit's
first 7 journal rows (row 5 the character dump, row 6 the first board the equipment optimizer
reads with a calibration) and the sidecar files the restored policy reads, the 38 MB loadout
report left out, xz-compressed (tests/support/town_arrival_fixture.py).

    PYTHONPATH="src;tests" python tests/extract_n1a_525_departure_1115_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1a-525-rules-1115/cap/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-departure-1115"
ROWS = 7


if __name__ == "__main__":
    extract(VISIT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
