"""Extract tests/fixtures/n1a-545-recall-contradiction-1128/ (tests/test_n1a_545_recall_contradiction_1128_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL38, Sorcery), the incident capture
``incident-captures/20261128-093452-town-blocked-recall-readiness-contradiction`` copied read-only
from the viewing server to C:/hengband-backups/pdca/captures/n1a-545-recall-contradiction-1128/:

  town-arrival/           29 rows (build bot-b60919d45): row 17 zapped the Rod of Recall, row 20
                          ate during the countdown, row 21 cancelled the recall as unready and
                          row 28 stopped under town:blocked:recall-readiness-contradiction

``arrival-dungeon-board.json`` is the last dungeon board of the capture's snapshot ring (the
Mountain 45F before this town visit), the base of the test's constructed arrival board.

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_recall_contradiction_1128_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-recall-contradiction-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-recall-contradiction-1128"
ROWS = 29


def main():
    extract(ROOT / "town-arrival", FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
