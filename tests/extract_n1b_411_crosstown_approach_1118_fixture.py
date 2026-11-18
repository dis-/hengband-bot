"""Extract tests/fixtures/n1b-411-crosstown-approach-1118/n1b-411-0749/.

Source: n1-b life-411's town-arrival checkpoint of 2026-11-18 07:49:55 (Magic-Eater
Lv50, turn 6,954,314, 126,856 gold, the Outpost), from incident capture
20261118-075035-loop-detected, copied read-only from the viewing server to
C:/hengband-backups/pdca/n1b-411-crosstown-1118/.  Journal rows 0-53 are kept: the
Temple's Word of Recall stock-out sends the circuit on (rows 11-12), the inn leg to
Telmora (row 13), the Weapon Smiths page that left again (row 15) and the Black Market
page that left again (row 53).

    python tests/extract_n1b_411_crosstown_approach_1118_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/n1b-411-crosstown-1118/incident-captures/"
             "20261118-075035-loop-detected/town-arrival-all/"
             "20261118-074955.118716106-turn6954314")
TARGET = Path(__file__).with_name("fixtures") / "n1b-411-crosstown-approach-1118" / "n1b-411-0749"
ROWS = 54


def main() -> None:
    extract(VISIT, TARGET, ROWS)
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
