"""Extract tests/fixtures/n1a-545-withdraw-overweight-1127/ (tests/test_n1a_545_withdraw_overweight_1127_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL34, Sorcery, gold 24683), the incident capture
``incident-captures/20261127-165915-livelock-exhausted`` copied read-only from the viewing server
to C:/hengband-backups/pdca/captures/n1a-545-withdraw-overweight-1127/:

  town-arrival/           71 rows (arrival turn 5302903): the equipment transaction swapped two
                          pieces through Home, took the weapon off and deposited it, and row 69
                          refused the next Home withdrawal (equipment-transaction:withdraw-overweight);
                          row 70 stopped under livelock:exhausted

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_withdraw_overweight_1127_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-withdraw-overweight-1127/"
            "20261127-165915-livelock-exhausted")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-withdraw-overweight-1127"
ROWS = 71


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
