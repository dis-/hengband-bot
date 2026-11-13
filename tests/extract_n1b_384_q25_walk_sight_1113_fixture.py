"""Freeze n1-b life-384's Quest 25 boards (2026-11-13 08:42) for the stairway walk test.

Source: n1-b life-384 (Magic-Eater Lv37, the resumed life-382, build bot-30771c7cc) on
hengband.net, the loop-detected stops ~/hengbot-soak/n1-b/life-384/captures/
20261113-084238-loop-detected (the first process: every decision its state ring holds) and
20261113-084257-loop-detected (the last restart, decisions 0 to its stop), copied to
C:/hengband-backups/pdca/captures/n1b-384-q25-walk-sight-1113 with
~/hengbot-soak/n1-b/life-384/jsonlog/q25-battle.json as the last process left it (phase 9, the
stairway).  The boards are cut as tests/extract_n1b_382_q25_patrol_owner_1113_fixture.py cuts
them (its ``process``).

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests import extract_n1b_382_q25_patrol_owner_1113_fixture as cut

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-384-q25-walk-sight-1113.json.gz"
FIRST = "20261113-084238-loop-detected"
LAST = "20261113-084257-loop-detected"


def main():
    cut.ROOT = ROOT
    first_boards, first_recorded, _ = cut.process(FIRST, restarted=False)
    boards, recorded, knowledge = cut.process(LAST, restarted=True)
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in (*first_boards, *boards)
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1b-384-q25-walk-sight-1113",
                first=dict(boards=first_boards, recorded=first_recorded),
                second=dict(boards=boards, recorded=recorded),
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                battle_record=json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")))
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(first_boards)} {len(boards)} "
                     f"{first_recorded[0]['sequence']}-{first_recorded[-1]['sequence']} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
