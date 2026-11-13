"""Extract tests/fixtures/n1c-205-equip-swap-loop-1113/.

Source: n1-c life-205's town-arrival checkpoint of the visit that began
2026-11-13 20:06:16 (turn 4687314, build of main c50cd91dc4's predecessor
running on the viewing server), whose Home glove swap the loop detector
stopped at 20:09:23 (captures/20261113-200923-loop-detected), copied
read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-205-equip-swap-loop-1113/: journal rows
0-24 (row 2 plans the Gauntlets of Slaying with the Cestus worn, row 24 plans
the Cestus back with the Gauntlets worn).  The loadout report (an
append-only log the policy only writes) is left out.

    PYTHONPATH="src;tests" python tests/extract_n1c_205_equip_swap_loop_1113_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1c-205-equip-swap-loop-1113/jsonlog/town-arrival/"
             "20261113-200616.650232396-turn4687314")
TARGET = Path(__file__).with_name("fixtures") / "n1c-205-equip-swap-loop-1113"


if __name__ == "__main__":
    extract(VISIT, TARGET, 25, frozenset({"_loadout_report_path"}))
    print(sorted(path.name for path in TARGET.iterdir()))
