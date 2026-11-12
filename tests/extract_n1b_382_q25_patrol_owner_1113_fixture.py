"""Freeze n1-b life-382's Quest 25 boards (2026-11-13 05:38-05:39) for the plan-owns-its-floor test.

Source: n1-b life-382 (Magic-Eater Lv37, the resumed life-378, build main 784d60f71) on
hengband.net, the loop-detected stops ~/hengbot-soak/n1-b/life-382/captures/
20261113-053907-loop-detected (the first process: every decision its state ring holds, to its
stop) and 20261113-053914-loop-detected (the restarted process, decisions 0-48 to its stop),
copied to the implementer's scratch with ~/hengbot-soak/n1-b/life-382/jsonlog/q25-battle.json
as the last process left it (05:39:14: phase 5, the tome; 26 recharge rests spent in it).

One board per recorded decision (the decisions of one turn take that turn's last rows in order)
with its decision row's messages and the recorded reason and key, and the battle record.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import collections
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_174_q25_loops_1109_fixture import ring_rows

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-382-q25-patrol-owner-1113.json.gz"
QUEST = 25
FIRST = "20261113-053907-loop-detected"
SECOND = "20261113-053914-loop-detected"


def _decisions(path: Path) -> list[dict]:
    found = []
    with gzip.open(path, "rt", encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "decision_sequence" in row and "reason" in row and row["reason"] != "loop-detected":
                found.append(row)
    return found


def process(directory: str, *, restarted: bool):
    capture = ROOT / directory
    rows = ring_rows(capture / "state.jsonl.gz")
    first_turn = min(row["turn"] for row in rows if row.get("type") == "player_turn")
    decisions = [row for row in _decisions(capture / "bot-decisions.jsonl.gz")
                 if row["turn"] >= first_turn and row.get("floor", {}).get("quest_id") == QUEST]
    if restarted:
        start = max(index for index, row in enumerate(decisions) if row["decision_sequence"] == 0)
        decisions = decisions[start:]
    sequences = [row["decision_sequence"] for row in decisions]
    assert sequences == list(range(sequences[0], sequences[0] + len(sequences))), directory
    by_turn = collections.defaultdict(list)
    for row in rows:
        if row.get("type") == "player_turn":
            by_turn[row["turn"]].append(row)
    need = collections.Counter(row["turn"] for row in decisions)
    used = collections.Counter()
    boards, recorded = [], []
    for row in decisions:
        same = by_turn[row["turn"]]
        board = same[len(same) - need[row["turn"]] + used[row["turn"]]]
        used[row["turn"]] += 1
        position = row["position"]
        assert (board["player"]["y"], board["player"]["x"]) == (position["y"], position["x"]), row
        boards.append(dict(board, messages=row["messages"]))
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"]})
    knowledge = {}
    for row in rows:
        if row.get("type") == "knowledge":
            knowledge[row["knowledge"]["category"]] = row
    return boards, recorded, knowledge


def main():
    first_boards, first_recorded, _ = process(FIRST, restarted=False)
    second_boards, second_recorded, knowledge = process(SECOND, restarted=True)
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in (*first_boards, *second_boards)
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1b-382-q25-patrol-owner-1113",
                first=dict(boards=first_boards, recorded=first_recorded),
                second=dict(boards=second_boards, recorded=second_recorded),
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                battle_record=json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")))
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(first_boards)} {len(second_boards)} "
                     f"{first_recorded[0]['sequence']}-{first_recorded[-1]['sequence']} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
