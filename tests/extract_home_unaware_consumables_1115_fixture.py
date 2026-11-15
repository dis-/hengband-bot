"""Extract tests/fixtures/home-unaware-consumables-1115/<name>/.

Source: the viewing bots' town-arrival checkpoints of 2026-11-15 (jsonlog/town-arrival), copied
read-only to C:/hengband-backups/pdca/captures/home-unaware-consumables-1115/:

 * ``n1b405`` - n1-b/life-405/jsonlog/town-arrival/20261115-232122.196279197-turn2775795,
   rows 0-2 (row 2 the carried unaware scroll's identification);
 * ``n1c214`` - n1-c/life-214/jsonlog/town-arrival/20261115-233929.502537181-turn5781865,
   rows 0-4 (row 3 the Home sweep's take of the unaware 紺碧の薬, row 4 the outside board after
   the recorded take).

    python tests/extract_home_unaware_consumables_1115_fixture.py <town-arrival dir> <name> <rows>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path(__file__).with_name("fixtures") / "home-unaware-consumables-1115"


if __name__ == "__main__":
    extract(Path(sys.argv[1]), ROOT / sys.argv[2], int(sys.argv[3]))
