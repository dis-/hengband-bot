"""Extract tests/fixtures/n1c-207-q25-straggler-rest-cut-1114.json.gz (q25-straggler-rest-cut-1114).

Source (copies in C:/hengband-backups/pdca/q25-phase3-hold-1114, from ~/hengbot-soak/n1-c/life-207):

 * ``capture-212431``: the capture 20261114-212431-stall-floor-dwell-quest-strategy-hold, its 109
   decisions (16660-16768, turns 8108265-8108911), every one '5' ``quest-strategy:hold`` on [5,1],
   cut as tests/extract_n1b_382_q25_patrol_owner_1113_fixture ``process`` cuts a capture.  Between
   the boards only ``turn`` and ``clock`` change (checked).
 * ``q25-battle-2129.json``: jsonlog/q25-battle.json after the stop (phase 3, ready false, quiet 0,
   rest_cut true; the record of the stop's process carried on past it unchanged but its turn).
 * ``warning-cells-2129.json``: jsonlog/warning-cells.json (nothing refused).

Run: python tests/extract_n1c_207_q25_straggler_rest_cut_1114_fixture.py [ROOT]
"""
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests import extract_n1b_382_q25_patrol_owner_1113_fixture as capture

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/hengband-backups/pdca/q25-phase3-hold-1114")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-207-q25-straggler-rest-cut-1114.json.gz"
CHANGED = ("turn", "clock")


def main():
    capture.ROOT = ROOT
    boards, recorded, _knowledge = capture.process("capture-212431", restarted=False)
    base = boards[0]
    changes = [{key: board[key] for key in CHANGED} for board in boards]
    for board, change in zip(boards, changes):
        assert dict(base, **change) == board, board["turn"]
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1c-207-q25-straggler-rest-cut-1114",
                hold=dict(base=base, changes=changes, recorded=recorded),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                battle_record=json.loads((ROOT / "q25-battle-2129.json").read_text(encoding="utf-8")),
                warning_record=json.loads((ROOT / "warning-cells-2129.json").read_text(encoding="utf-8")))
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']}\n")


if __name__ == "__main__":
    main()
