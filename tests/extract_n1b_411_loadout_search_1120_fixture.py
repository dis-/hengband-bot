"""Extract tests/fixtures/n1b-411-loadout-search-1120/.

Source: n1-b life-411's town-arrival checkpoint of the visit that began
2026-11-20 06:01:06 (turn 9902041; Magic-Eater Lv50, home from 95F, 235
owned equipment items), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-411-loadout-1120/: journal rows 0-1
(row 1 runs the equipment optimizer on the full catalog and keeps the worn
set).  The loadout report (an append-only log the policy only writes; it was
over the sidecar limit) is left out.

    PYTHONPATH="src;tests" python tests/extract_n1b_411_loadout_search_1120_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1b-411-loadout-1120/"
             "20261120-060106.982277260-turn9902041")
TARGET = Path(__file__).with_name("fixtures") / "n1b-411-loadout-search-1120"


if __name__ == "__main__":
    extract(VISIT, TARGET, 2, frozenset({"_loadout_report_path"}))
    print(sorted(path.name for path in TARGET.iterdir()))
