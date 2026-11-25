"""Extract tests/fixtures/n1b-418-shop-entrance-1125/ (tests/test_n1b_418_shop_entrance_1125_recorded.py).

Source: n1-b life-418 (Zombie Magic-Eater Lv42), the incident capture
``incident-captures/20261125-111837-town-blocked-stage-deadline-buy/`` of the owner halt on
town:blocked:stage-deadline:buy at 2026-11-25 11:18:37, a read-only copy in
C:/hengband-backups/pdca/captures/n1b-418-town-shop-entrance-1125/:

  town-arrival/           the town-arrival checkpoint of 11:17:17 (turn 5021475, decision
                          80890): seek-loot stepped onto the store 5 entrance (34,90) from
                          row 114 on and town:kill-mob-approach stepped off it, to the stage
                          deadline (the last row)

Kept: every journal row of the checkpoint (170; the loadout report left out, as the other
town-arrival fixtures).

    python tests/extract_n1b_418_shop_entrance_1125_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-418-town-shop-entrance-1125/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-418-shop-entrance-1125"
ROWS = 170


def main():
    extract(ROOT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
