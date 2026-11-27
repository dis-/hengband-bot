"""Extract tests/fixtures/n1a-545-overflow-no-disposal-1128/ (tests/test_n1a_545_overflow_no_disposal_1128_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL39, Sorcery, gold 24237), the incident capture
``incident-captures/20261128-030108-town-blocked-overflow-no-legal-disposal`` copied read-only
from the viewing server to C:/hengband-backups/pdca/captures/n1a-545-overflow-no-disposal-1128/:

  town-arrival/           13 rows (arrival turn 6761472): the town visit after a dive; row 10 bought
                          at the Alchemist, and row 12 stopped under
                          town:blocked:overflow-no-legal-disposal with 21 of 23 pack slots used

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_overflow_no_disposal_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-overflow-no-disposal-1128/"
            "20261128-030108-town-blocked-overflow-no-legal-disposal")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-overflow-no-disposal-1128"
ROWS = 13


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
