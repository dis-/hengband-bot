"""Extract tests/fixtures/stage-deadline-equipment-1115/<name>/.

Source: the viewing bot's incident capture of 2026-11-15 that stopped at
town:blocked:stage-deadline:equipment in a Home withdraw/deposit ping-pong, copied read-only to
C:/hengband-backups/pdca/captures/stage-deadline-equipment-1115/:

 * ``n1c214`` - n1-c/life-214/incident-captures/20261115-180352-town-blocked-stage-deadline-
   equipment/town-arrival, rows 0-109 (row 109 the recorded stop).

    python tests/extract_stage_deadline_equipment_1115_fixture.py <town-arrival dir> <name> <rows>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path(__file__).with_name("fixtures") / "stage-deadline-equipment-1115"


if __name__ == "__main__":
    extract(Path(sys.argv[1]), ROOT / sys.argv[2], int(sys.argv[3]),
            frozenset({"_loadout_report_path"}))
