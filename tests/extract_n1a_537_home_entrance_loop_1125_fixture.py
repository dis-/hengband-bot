"""Extract tests/fixtures/n1a-537-home-entrance-loop-1125/ (tests/test_n1a_537_home_entrance_loop_1125_recorded.py).

Source: n1-a life-537 (Zombie Warrior Lv48), the incident capture
``incident-captures/20261125-231035-town-blocked-stage-deadline-home/`` of the owner halt on
town:blocked:stage-deadline:home at 2026-11-25 23:10:35 (build bot-5951fde8b), a read-only copy
in C:/hengband-backups/pdca/captures/n1a-537-home-entrance-loop-1125/:

  town-arrival/           the town-arrival checkpoint of 23:09:16 (turn 4329817, decision 522),
                          the return from Q33: the Home ammo top-up bound at row 6 (4 free
                          slots), the Q33 reward pickup at row 25 (3 free), and shop:approach
                          stepping on and off the Home entrance (45,123) from row 35 on

Kept: the first 40 journal rows of the checkpoint (98; the loop is in rows 35-39), the loadout
report left out, as the other town-arrival fixtures.

    python tests/extract_n1a_537_home_entrance_loop_1125_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-537-home-entrance-loop-1125/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-537-home-entrance-loop-1125"
ROWS = 40


def main():
    extract(ROOT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
