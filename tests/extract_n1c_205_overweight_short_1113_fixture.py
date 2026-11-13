"""Extract tests/fixtures/n1c-205-overweight-short-1113/<name>/.

Source: n1-c life-205's incident capture of 2026-11-13 18:07:34
(town:blocked:overweight-home-full-no-legal-relief), copied read-only to
C:/hengband-backups/pdca/captures/town-stops-1113pm/n1c-205/incident/
20261113-180734-town-blocked-overweight-home-full-no-legal-relief/town-arrival/:

 * ``i1807`` - the town-arrival checkpoint (turn 4483477), rows 0-10: row 6 the Home
   deposit, row 10 the board outside Home on which the recorded bot stopped.

The same layout as tests/extract_n1c_205_item_use_route_1113_fixture.py (its ``main``):

    python tests/extract_n1c_205_overweight_short_1113_fixture.py <town-arrival dir> <name> <rows>
"""
import sys
from pathlib import Path

import extract_n1c_205_item_use_route_1113_fixture as layout

layout.ROOT = Path(__file__).with_name("fixtures") / "n1c-205-overweight-short-1113"


if __name__ == "__main__":
    layout.main(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
