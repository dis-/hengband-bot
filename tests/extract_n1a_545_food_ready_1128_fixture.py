"""Extract tests/fixtures/n1a-545-food-ready-1128/ (tests/test_n1a_545_food_ready_1128_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL39, Sorcery), the incident capture
``incident-captures/20261128-040157-town-blocked-survival-food_ready`` copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1a-545-food-ready-1128/:

  town-arrival/           276 rows (arrival turn 6836403): the town visit after a 45F dive; the
                          Black Market tour to the second town (row 65) bought a *Destruction* staff
                          and Potions of Speed, row 203 left that town's General Store without the
                          Elvish Waybread on its shelf, and row 275 stopped under
                          town:blocked:survival:food_ready with food 8 of 9 Rations' worth

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_food_ready_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-food-ready-1128/"
            "20261128-040157-town-blocked-survival-food_ready")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-food-ready-1128"
ROWS = 276


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
