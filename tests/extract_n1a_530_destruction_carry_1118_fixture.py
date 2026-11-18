"""Extract tests/fixtures/n1a-530-destruction-carry-1118/.

Source: n1-a life-530's town-arrival checkpoint of 2026-11-18 12:50:39 (turn 13141224), the
departure of the trip it died on (古城 51F, 12:50:56), copied read-only from the viewing server's
jsonlog/town-arrival/20261118-125039.034634291-turn13141224/ to
C:/hengband-backups/pdca/n1a-530-death-1118/cap/town-arrival/: the arrival policy, the visit's
first 17 journal rows (row 4 the Home catalogue shortage binder, row 16 the Recall read) and the
sidecar files the restored policy reads (the 72 MB loadout report was not captured),
xz-compressed (tests/support/town_arrival_fixture.py).

    PYTHONPATH="src;tests" python tests/extract_n1a_530_destruction_carry_1118_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1a-530-death-1118/cap/town-arrival/"
             "20261118-125039.034634291-turn13141224")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-destruction-carry-1118"
ROWS = 17


if __name__ == "__main__":
    extract(VISIT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))
