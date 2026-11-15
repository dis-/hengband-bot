"""Extract tests/fixtures/n1b-402-me-staff-pack-1115/.

Source: n1-b life-402's incident capture 20261115-173147-quest-blocked-me-staff (build
abcba1e76), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1b-402-me-staff-1115/incident-captures/: the town-arrival checkpoint
(turn 427466) and its journal rows 0-69 (row 64 the board after the Staff of Detect Traps was
bought in town 3), the loadout report left out.

    PYTHONPATH="src;tests" python tests/extract_n1b_402_me_staff_pack_1115_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1b-402-me-staff-1115/incident-captures/"
             "20261115-173147-quest-blocked-me-staff/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1b-402-me-staff-pack-1115"
ROWS = 70


if __name__ == "__main__":
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
