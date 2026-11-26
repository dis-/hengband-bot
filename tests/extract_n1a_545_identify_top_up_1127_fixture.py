"""Extract tests/fixtures/n1a-545-identify-top-up-1127/ (tests/test_n1a_545_identify_top_up_1127_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL21, Sorcery), the incident capture
``incident-captures/20261127-020911-town-blocked-survival-identify_staff_ready`` copied read-only
from the viewing server to C:/hengband-backups/pdca/captures/n1a-545-identify-staff-1127/:

  town-arrival/20261127-020835.367828876-turn1405824/
                          the town-arrival checkpoint of 2026-11-27 02:08:35 (decision 41388):
                          134 rows; row 133 stopped under
                          town:blocked:survival:identify_staff_ready with 18 of the 20 Identify
                          staff charges, the pack at 1432 of its 1450 weight limit

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_identify_top_up_1127_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-identify-staff-1127/town-arrival")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-identify-top-up-1127"
ROWS = 134


def main():
    extract(ROOT / "20261127-020835.367828876-turn1405824", FIXTURE, ROWS,
            frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
