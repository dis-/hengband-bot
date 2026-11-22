"""Extract tests/fixtures/n1b-415-q18-entry-walk-1122/n1b-415-1434/.

Source: n1-b life-415's town-arrival checkpoint of 2026-11-22 14:34:42 (Magic-Eater Lv34,
turn 1,965,921, build bot-53f7a340e), the ``town-arrival/`` of incident capture
20261122-143605-loop-detected (Quest 18 taken, its entry refused for the absorbed Speed's
charges, the walk to its entrance alternating with the shops until loop-detected at 14:36),
copied read-only from the viewing server to C:/hengband-backups/pdca/n1b-415-loop/.
Journal rows 0-3 are kept: the arrival's walk to the shop and the Word of Recall purchase
(rows 0-2) and row 3, the first step of the walk to Q18's entrance.

    python tests/extract_n1b_415_q18_entry_walk_1122_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1b-415-loop/incident-captures/"
             "20261122-143605-loop-detected/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1b-415-q18-entry-walk-1122" / "n1b-415-1434"
ROWS = 4


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
