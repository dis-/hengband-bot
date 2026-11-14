"""Extract tests/fixtures/stage-deadline-walk-1114/<name>/.

Source: the viewing bots' incident captures of 2026-11-14 that stopped at
town:blocked:stage-deadline:equipment while walking to Home, copied read-only to
C:/hengband-backups/pdca/captures/stage-deadline-1114/:

 * ``n1a522`` - n1-a/life-522/incident-captures/20261114-083453-town-blocked-stage-deadline-
   equipment/town-arrival, rows 0-65 (row 65 the recorded stop);
 * ``n1b396`` - n1-b/life-396/incident-captures/20261114-110217-town-blocked-stage-deadline-
   equipment/town-arrival, rows 0-67 (row 67 the recorded stop).

The same layout as tests/extract_n1c_205_item_use_route_1113_fixture.py (its ``main``):

    python tests/extract_stage_deadline_walk_1114_fixture.py <town-arrival dir> <name> <rows>
"""
import sys
from pathlib import Path

import extract_n1c_205_item_use_route_1113_fixture as layout

layout.ROOT = Path(__file__).with_name("fixtures") / "stage-deadline-walk-1114"


if __name__ == "__main__":
    layout.main(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
