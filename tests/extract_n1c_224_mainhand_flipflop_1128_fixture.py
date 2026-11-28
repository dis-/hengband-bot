"""Extract tests/fixtures/n1c-224-mainhand-flipflop-1128/ (tests/test_n1c_224_mainhand_flipflop_1128_recorded.py).

Source: n1-c life-224 (Zombie Magic-Eater CL44), the incident capture
``incident-captures/20261128-152426-town-blocked-equipment-slot-flipflop-main_hand`` copied
read-only from the viewing server to C:/hengband-backups/pdca/captures/n1c-224-mainhand-flipflop-1128/:

  town-arrival/   91 rows: the equipment transaction wears ★ハーゲンのスピア and スピードの指輪 (+6)
                  (rows 10-24), ★フーリン王のビークド・アックス and 『炎の鉄ゲタ』 (rows 55-68), the spear and
                  スピードの軟革ブーツ again (rows 76-89), and row 90 stops under
                  town:blocked:equipment-slot-flipflop:main_hand

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1c_224_mainhand_flipflop_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-224-mainhand-flipflop-1128/incident-captures/"
            "20261128-152426-town-blocked-equipment-slot-flipflop-main_hand")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-224-mainhand-flipflop-1128"
ROWS = 91


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
