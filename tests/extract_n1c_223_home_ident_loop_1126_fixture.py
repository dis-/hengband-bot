"""Extract tests/fixtures/n1c-223-home-ident-loop-1126/ (tests/test_n1c_223_home_ident_loop_1126_recorded.py).

Source: n1-c life-223 (Zombie Magic-Eater Lv32), the incident capture
``incident-captures/20261126-191705-town-blocked-stage-deadline-home/`` of the owner halt on
town:blocked:stage-deadline:home at 2026-11-26 19:17:05, a read-only copy in
C:/hengband-backups/pdca/captures/n1c-223-home-ident-loop-1126/:

  town-arrival/           the town-arrival checkpoint of 19:16:41 (turn 2153829, decision 117536):
                          the *Identify* take of 電撃の魔法を防ぐクローク filed at row 23, and from
                          row 25 on the takes of it and ☆陣笠『太陽の衣』 going out and back in
                          turn (withdraw, deposit, knowledge) up to the stop at row 52

Kept: all 53 journal rows of the checkpoint, the loadout report left out, as the other
town-arrival fixtures.

    python tests/extract_n1c_223_home_ident_loop_1126_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-223-home-ident-loop-1126/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1c-223-home-ident-loop-1126"
ROWS = 53


def main():
    extract(ROOT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
