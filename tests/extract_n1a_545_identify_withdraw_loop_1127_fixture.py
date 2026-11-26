"""Extract tests/fixtures/n1a-545-identify-withdraw-loop-1127/ (tests/test_n1a_545_identify_withdraw_loop_1127_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL23, Sorcery, ordinary food), the incident capture
``incident-captures/20261127-031146-town-blocked-stage-deadline-home`` copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1a-545-identify-withdraw-loop-1127/:

  town-arrival/20261127-031101.328348043-turn1620579/
                          the town-arrival checkpoint of 2026-11-27 03:11:01: 174 rows; from row 27
                          the Home take of the 5-charge Identify staff (queued as fundraising food)
                          was refused as overweight, re-queued and refused again (shop:approach,
                          home:leave-for-pending-withdraw, the entrance step-off, policy:none-wait)
                          until town:blocked:stage-deadline:home

Kept: the first 40 journal rows (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_identify_withdraw_loop_1127_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-identify-withdraw-loop-1127/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-identify-withdraw-loop-1127"
ROWS = 40


def main():
    extract(ROOT / "20261127-031101.328348043-turn1620579", FIXTURE, ROWS,
            frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
