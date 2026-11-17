"""Extract tests/fixtures/bm-tour-loop-1117/n1c-216-1715/.

Source: n1-c life-216's town-arrival checkpoint of 2026-11-17 17:15:15 (Magic-Eater,
turn 5,750,562, about 2.66M gold), the ``town-arrival/`` of incident capture
20261117-172801-loop-detected (the Black Market tour's Outpost <-> Telmora loop), copied
read-only from the viewing server to C:/hengband-backups/pdca/bm-tour-loop-1117/.
Journal rows 0-179 are kept: the tour's first inn leg is rows 169-170, row 171 the
arrival in Telmora (answered ``fixedquest:q2-teleport`` back to the Outpost), and the
round repeats every four rows.

    python tests/extract_bm_tour_loop_1117_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/bm-tour-loop-1117/incident-captures/"
             "20261117-172801-loop-detected/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "bm-tour-loop-1117" / "n1c-216-1715"
ROWS = 180


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
