"""Extract tests/fixtures/n1b-421-weapon-flipflop-1128/ (tests/test_n1b_421_weapon_flipflop_1128_recorded.py).

Source: n1-b life-421 (Klackon Magic-Eater CL20), the incident capture
``incident-captures/20261128-110736-town-blocked-equipment-slot-flipflop-main_hand`` copied
read-only from the viewing server to C:/hengband-backups/pdca/captures/n1b-421-weapon-flipflop-1128/:

  town-arrival/   53 rows: the equipment transaction wields the worn two shovels' set (rows 37-49),
                  town:restore-combat-weapon wields the long sword (rows 45, 46, 51), and row 52
                  stops under town:blocked:equipment-slot-flipflop:main_hand

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1b_421_weapon_flipflop_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-421-weapon-flipflop-1128/"
            "20261128-110736-town-blocked-equipment-slot-flipflop-main_hand")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-421-weapon-flipflop-1128"
ROWS = 53


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
