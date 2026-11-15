"""Extract tests/fixtures/bm-telepathy-priority-1115/n1a-526-2245/.

Source: n1-a life-526's town-arrival checkpoint of 2026-11-15 22:45:21 (warrior Lv28,
turn 1,040,122), copied read-only from the viewing server's
jsonlog/town-arrival/20261115-224521.444067637-turn1040122/ to
C:/hengband-backups/pdca/bm-telepathy-priority-1115/n1a-526-turn1040122/.

Row 25 of the journal is the visit's Black Market page with an Amulet of ESP
(テレパシーのアミュレット {~感}, TR_TELEPATHY) at 221,344 and 18,784 gold; live, the
visit bought a Potion of Cure Critical Wounds (k, 3,983) and a Potion of Resistance
(3,319) on that page and recalled.  The fixture keeps journal rows 0-27 with the
checkpoint (``policy.pkl``) and the sidecar files, all xz-compressed
(tests/support/town_arrival_fixture.extract).

DECLARED LOSS: the server rotated the checkpoint away while it was copied; the sidecars
named in ``LOST`` never arrived and are written as not copied (``left-out``), with the
large loadout report.

    python tests/extract_bm_telepathy_priority_1115_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/bm-telepathy-priority-1115/n1a-526-turn1040122")
TARGET = Path(__file__).with_name("fixtures") / "bm-telepathy-priority-1115" / "n1a-526-2245"
ROWS = 28
LOST = frozenset({
    "_breeder_floor_record_path", "_character_calibration_path", "_character_dump_path",
    "_town_visit_purchase_path", "_warning_cell_record_path",
    "_overweight_surplus_ledger_path", "_exploration_ledger.path",
    "_home_disposal.history_path",
})


def main() -> None:
    extract(VISIT, TARGET, ROWS, LOST | {"_loadout_report_path"})
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
