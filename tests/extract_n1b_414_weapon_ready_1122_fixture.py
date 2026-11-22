"""Freeze the two town:blocked:survival:combat_weapon_ready visits of 2026-11-22.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-414-weapon-ready-1122/:

- n1-b/life-414/town-arrival/20261122-084821.496358536-turn1565228/ (build bot-ede1d0935,
  08:48) -- the town visit a staff stock-out mining run came back to with シャベル /
  ドワーフのシャベル in the hands, its 13 journal rows (the stop is the last).
- n1-c/life-220/town-arrival/20261122-091513.917039717-turn1669669/ (build e7f776dd7, 09:15)
  -- the same stop after a staff stock-out mining run with シャベル in both hands, its 83
  journal rows (the stop is the last).

Only this extraction tool reads the captures; the committed test reads the fixtures.
"""

from __future__ import annotations

from pathlib import Path

from support.town_arrival_fixture import extract

CAPTURES = Path("C:/hengband-backups/pdca/captures/n1b-414-weapon-ready-1122")
FIXTURES = Path(__file__).with_name("fixtures")
VISITS = (
    (CAPTURES / "n1-b/life-414/town-arrival/20261122-084821.496358536-turn1565228",
     FIXTURES / "n1b-414-weapon-ready-1122", 13),
    (CAPTURES / "n1-c/life-220/town-arrival/20261122-091513.917039717-turn1669669",
     FIXTURES / "n1c-220-weapon-ready-1122", 83),
)


def main():
    for visit, output, rows in VISITS:
        extract(visit, output, rows)


if __name__ == "__main__":
    main()
