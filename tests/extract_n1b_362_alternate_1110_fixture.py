"""Extract tests/fixtures/alternate-deepest-1110/.

Source: n1-b life-362 2026-11-10 08:01:28, the town arrival after the third
over-extended Angband dive in a row (Angband 70F, emergency-repeat), on which
the over-extension valve switched the recall target.  The town-arrival
checkpoint 20261110-080128.560636743-turn4943001 on the viewing server
(~/hengbot-soak/n1-b/life-362/jsonlog/town-arrival/), copied read-only to
C:/hengband-backups/pdca/captures/n1b-362-alternate-1110/visit/town-arrival/.
(The checkpoint 20261110-080128.208518663 of the same turn holds only the
``~f`` skill request decided before the arrival was observed.)

- ``visit``: the arrival policy and the journal rows 0-11 (row 0 observes the
  arrival and runs the switch; row 11 is the recall read, ``rgc``
  town:recall-to-alt-dungeon).

    python tests/extract_n1b_362_alternate_1110_fixture.py <capture>/visit
"""
import sys
from pathlib import Path

import extract_stops_1109_town_fixtures as base

base.OUTPUT = Path(__file__).with_name("fixtures") / "alternate-deepest-1110"
base.ROWS = {"visit": 12}


def main() -> None:
    base.extract("visit", Path(sys.argv[1]))


if __name__ == "__main__":
    main()
