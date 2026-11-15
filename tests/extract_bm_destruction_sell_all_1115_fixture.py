"""Extract tests/fixtures/bm-destruction-sell-all-1115/n1c-214-1745/.

Source: n1-c life-214's town-arrival checkpoint of 2026-11-15 17:45:12 (Magic-Eater Lv40,
the Outpost, build bot-d89dedaff), copied read-only from the viewing server's
jsonlog/town-arrival/20261115-174512.723112642-turn5473145/ to
C:/hengband-backups/pdca/bm-destruction-sell-all-1115/n1c-214-turn5473145/.

Row 27 of the journal is the visit's Black Market page with a Staff of *Destruction* (4
charges) at 70,297 and 76,060 gold; the visit then bought a Wand of Stone to Mud (3,011)
and a Staff of Speed (27,617) on that page and left for Morivant without the staff.  The
fixture keeps journal rows 0-37 (row 36 delivers the visit's Home census, row 37 is its
Home page) with the checkpoint (``policy.pkl``) and the sidecar files, all xz-compressed
(tests/support/town_arrival_fixture.extract).

    python tests/extract_bm_destruction_sell_all_1115_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/bm-destruction-sell-all-1115/n1c-214-turn5473145")
TARGET = Path(__file__).with_name("fixtures") / "bm-destruction-sell-all-1115" / "n1c-214-1745"
ROWS = 38


def main() -> None:
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
