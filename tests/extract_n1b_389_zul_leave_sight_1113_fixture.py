"""Extract tests/fixtures/n1b-389-zul-leave-sight-1113/<name>/.

Source: n1-b life-389's town-arrival checkpoint on the viewing server
(~/hengbot-soak/n1-b/life-389/jsonlog/town-arrival/, copied read-only to
C:/hengband-backups/pdca/captures/town-stops-1113pm/n1b-389/town-arrival/):

 * ``r1632`` - 20261113-163237.476259041-turn4181764 (the first restart in Zul after
   equipment-transaction:home-route-repeat-terminal), rows 0-5: rows 3 and 5 read '<'
   (town:zul:enter-global), row 4's board shows the refusal.

The same layout as tests/extract_n1c_205_item_use_route_1113_fixture.py (its ``main``):

    python tests/extract_n1b_389_zul_leave_sight_1113_fixture.py <town-arrival dir> <name> <rows>
"""
import sys
from pathlib import Path

import extract_n1c_205_item_use_route_1113_fixture as layout

layout.ROOT = Path(__file__).with_name("fixtures") / "n1b-389-zul-leave-sight-1113"


if __name__ == "__main__":
    layout.main(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
