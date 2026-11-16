"""Freeze n1-a life-528's Quest 25 boards (2026-11-16 13:12:58-13:13:03) for the rally's rest test.

Source: n1-a life-528 (warrior Lv41, build bot-0f3b00a68) on hengband.net, the loop-detected
stop ~/hengbot-soak/n1-a/life-528/captures/20261116-131306-loop-detected (the restarted process;
its ring holds decisions 26-105, to its stop), copied to
C:/hengband-backups/pdca/captures/n1a-528-q25-death-1116/captures with
~/hengbot-soak/n1-a/life-528/jsonlog/q25-battle.json as the last process left it (13:13:13: phase
2, Ipsissimus, rallying).  The boards are cut as tests/extract_n1b_382_q25_patrol_owner_1113_fixture.py
cuts them (its ``process``).

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
from tests.extract_n1c_174_q25_loops_1109_fixture import ring_rows

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-528-q25-rally-rest-1116.json.gz"
LAST = "20261116-131306-loop-detected"
# The restarted process's ring holds no knowledge rows; the next process (started at turn 3684472,
# the same character and equipment, five seconds later) dumped its skill_exp knowledge.
SKILL_FROM = "20261116-131318-exit-no-marker"


def main():
    cut.ROOT = ROOT
    # The ring holds the restarted process only from its decision 20 on (the old process
    # stopped at turn 3683797, before the ring's first board), so no restart cut is needed.
    boards, recorded, knowledge = cut.process(LAST, restarted=False)
    if "skill_exp" not in knowledge:
        knowledge["skill_exp"] = next(
            row for row in ring_rows(ROOT / SKILL_FROM / "state.jsonl.gz")
            if row.get("type") == "knowledge" and row["knowledge"]["category"] == "skill_exp")
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1a-528-q25-rally-rest-1116",
                second=dict(boards=boards, recorded=recorded),
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                battle_record=json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")))
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
