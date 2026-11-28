"""Extract tests/fixtures/n1b-421-dual-wield-1128/ (tests/test_n1b_421_dual_wield_1128_recorded.py).

Source: n1-b life-421 (Klackon Magic-Eater CL31), the jsonlog town-arrival checkpoint of
2026-11-28 18:12:50 (turn 4963925), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/dual-wield-valuation-1128/:

  66 rows: quest 31 accepted (row 20), the equipment transaction wields ☆鎖つき鉄球『超兄貴』 in the
  sub hand beside ★ブロード・スピア『ロンギヌス』 (rows 24-50), and the travel to Zul (rows 62-65)

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1b_421_dual_wield_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/dual-wield-valuation-1128/"
            "20261128-181250.710626115-turn4963925")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-421-dual-wield-1128"
ROWS = 66


def main():
    extract(ROOT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
