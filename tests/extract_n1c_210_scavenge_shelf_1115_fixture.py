"""Extract tests/fixtures/n1c-210-scavenge-shelf-1115/.

Source: n1-c life-210's incident capture 20261115-045756-town-blocked-survival-recall_departure_ready (build 62c26842b), copied read-only from the
viewing server to C:/hengband-backups/pdca/n1c-209-death-1115/life-210/incident-captures/: the
town-arrival checkpoint and its journal rows 0-7, the loadout report left out.

    PYTHONPATH="src;tests" python tests/extract_n1c_210_scavenge_shelf_1115_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1c-209-death-1115/life-210/incident-captures/"
             "20261115-045756-town-blocked-survival-recall_departure_ready/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1c-210-scavenge-shelf-1115"
ROWS = 8


if __name__ == "__main__":
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
