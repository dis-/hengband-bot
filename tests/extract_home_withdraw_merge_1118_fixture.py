"""Extract tests/fixtures/home-withdraw-merge-1118/n1c-216-0200/.

Source: n1-c life-216's town-arrival checkpoint of 2026-11-18 02:00:58 (Magic-Eater Lv50,
turn 6,173,662, about 1.65M gold), the ``town-arrival/`` of incident capture
20261118-020143-town-blocked-home-withdraw-failed-stock-present, copied read-only from the
viewing server to C:/hengband-backups/pdca/n1c-216-home-withdraw-1118/.  Journal rows 0-70
are kept: row 68 is the Home screen holding 耐性の薬 {50%引き} x80, row 69 the posted take
(``5pp1``, the pack's 耐性の薬 {75%引き} x13) and row 70 the board outside (x14).

    python tests/extract_home_withdraw_merge_1118_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1c-216-home-withdraw-1118/"
             "20261118-020143-town-blocked-home-withdraw-failed-stock-present/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "home-withdraw-merge-1118" / "n1c-216-0200"
ROWS = 71


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
