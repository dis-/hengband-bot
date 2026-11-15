"""Extract tests/fixtures/n1b-399-torch20-1115/.

Source: n1-b life-399's incident capture 20261115-114159-town-blocked-survival-
inventory_weight_ready (build 3b52c43f0), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1b-398-399-1115/life-399/: the town-arrival checkpoint of the
11:4x Outpost visit and its whole journal (136 rows, row 135 the board of the stop), the
loadout report left out.

    PYTHONPATH="src;tests" python tests/extract_n1b_399_torch20_1115_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1b-398-399-1115/life-399/incident-captures/"
             "20261115-114159-town-blocked-survival-inventory_weight_ready/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1b-399-torch20-1115"
ROWS = 136


if __name__ == "__main__":
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
