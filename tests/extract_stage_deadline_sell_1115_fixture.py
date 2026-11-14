"""Extract tests/fixtures/stage-deadline-sell-1115/<name>/.

Source: the viewing bot's incident capture of 2026-11-15 that stopped at
town:blocked:stage-deadline:sell in the middle of a run of sales, copied read-only to
C:/hengband-backups/pdca/captures/stage-deadline-sell-1115/:

 * ``n1b397`` - n1-b/life-397/incident-captures/20261115-004836-town-blocked-stage-deadline-
   sell/town-arrival, rows 0-203 (row 203 the recorded stop).

    python tests/extract_stage_deadline_sell_1115_fixture.py <town-arrival dir> <name> <rows>
"""
import sys
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path(__file__).with_name("fixtures") / "stage-deadline-sell-1115"


if __name__ == "__main__":
    extract(Path(sys.argv[1]), ROOT / sys.argv[2], int(sys.argv[3]),
            frozenset({"_loadout_report_path"}))
