"""Extract tests/fixtures/n1c-208-weight-purchase-1115/.

Source: n1-c life-208's incident capture 20261114-231143-town-blocked-survival-
inventory_weight_ready (build e897edf2d), copied read-only from the viewing
server to C:/hengband-backups/pdca/captures/n1b-397-overweight-home-1114/n1c-208/:
the town-arrival checkpoint of the 23:11:27 Outpost visit (turn 512629) and its
whole journal (91 rows, row 90 the board of the stop), the loadout report left out.

    PYTHONPATH="src;tests" python tests/extract_n1c_208_weight_purchase_1115_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1b-397-overweight-home-1114/n1c-208/"
             "incident-captures/20261114-231143-town-blocked-survival-inventory_weight_ready/"
             "town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1c-208-weight-purchase-1115"
ROWS = 91


if __name__ == "__main__":
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
