"""Extract tests/fixtures/failed-quest-report-1114/.

Source: n1-c life-207's town-arrival checkpoint of the Outpost visit that began
2026-11-14 15:56:51 (turn 7630682, decision 6121), copied read-only from the
viewing server to C:/hengband-backups/pdca/q25-why-1114/data/n1-c/: all six
journal rows (rows 0-3 restore the weapon and look into the General Store,
row 4 travels to the dungeon entrance and row 5 descends).  Q18 is FAILED
(status 5: the character recalled out of it 2026-11-14 05:13 -> 05:17), the
castle still holds it (building specials [18, 32]) and the visit leaves town
without reporting it.

    PYTHONPATH="src;tests" python tests/extract_failed_quest_report_1114_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/q25-why-1114/data/n1-c/"
             "20261114-155651.621034692-turn7630682")
TARGET = Path(__file__).with_name("fixtures") / "failed-quest-report-1114"


if __name__ == "__main__":
    extract(VISIT, TARGET, 6, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
