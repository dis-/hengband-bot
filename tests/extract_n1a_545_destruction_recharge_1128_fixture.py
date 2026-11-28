"""Extract tests/fixtures/n1a-545-destruction-recharge-1128/ (tests/test_n1a_545_destruction_recharge_1128_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL40, Sorcery), the town-arrival checkpoint
``jsonlog/town-arrival/20261128-151256.023002419-turn7780622`` copied read-only from the viewing
server to C:/hengband-backups/pdca/captures/n1a-545-destruction-recharge-1128/:

  town-arrival/           103 rows (arrival turn 7780622, 2026-11-28 15:12:56): row 59 bought a
                          Staff of *Destruction* (4 charges) at the Black Market for 77196 gold,
                          row 84 took 11 EMPTY staves from the Home's stack of 25 (the departure's
                          *Destruction* shortage counted one use per empty staff), row 87 put 8
                          back for the weight, and row 101 read the recall

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_destruction_recharge_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-destruction-recharge-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-destruction-recharge-1128"
ROWS = 103


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
