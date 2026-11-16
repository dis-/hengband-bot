"""Extract tests/fixtures/n1b-410-tower-hunger-1116/.

Source: n1-b life-410's incident capture 20261116-220954-town-blocked-stage-deadline-buy
(build 1f6038371), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1b-410-buy-deadline-1116/incident-captures/: the town-arrival
checkpoint of the Outpost visit (turn 6213593) and its journal rows 0-6 (row 1 the inn
teleport to Morivant, row 4 the first hungry Morivant board), the loadout report left out.

    PYTHONPATH="src;tests" python tests/extract_n1b_410_tower_hunger_1116_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1b-410-buy-deadline-1116/incident-captures/"
             "20261116-220954-town-blocked-stage-deadline-buy/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1b-410-tower-hunger-1116"
ROWS = 7


if __name__ == "__main__":
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
