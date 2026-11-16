"""Freeze n1-a life-529's Quest 25 boards (2026-11-17 00:10:37-00:10:51) for the Recall wait's test.

Source: n1-a life-529 (warrior Lv40, build bot-945ab02d2) on hengband.net, the death's stop
~/hengbot-soak/n1-a/life-529/captures/20261117-001053-exit-no-marker (its ring holds decisions
36435-36547, to the death), copied to C:/hengband-backups/pdca/captures/n1a-529-death-1117/captures
with ~/hengbot-soak/n1-a/life-529/jsonlog/q25-battle.json as the process left it at the death
(00:10:51: phase 2, Ipsissimus, rallying).  The boards are cut as
tests/extract_n1b_382_q25_patrol_owner_1113_fixture.py cuts them (its ``process``).

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
from tests import extract_n1b_382_q25_patrol_owner_1113_fixture as cut
from tests.extract_n1c_174_q25_loops_1109_fixture import ring_rows

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-529-q25-recall-wait-1117.json.gz"
LAST = "20261117-001053-exit-no-marker"


def process(directory: str):
    """``cut.process`` with one difference: decision 36486 is logged twice (the periodic skill
    browse ``periodic:skill-exp-knowledge`` and the blow after it, the same turn), so the
    sequences are only non-decreasing; the periodic browse's board is dropped (a replay posts its
    own browse when it asks for one)."""
    capture = ROOT / directory
    rows = ring_rows(capture / "state.jsonl.gz")
    first_turn = min(row["turn"] for row in rows if row.get("type") == "player_turn")
    decisions = [row for row in cut._decisions(capture / "bot-decisions.jsonl.gz")
                 if row["turn"] >= first_turn and row.get("floor", {}).get("quest_id") == cut.QUEST]
    sequences = [row["decision_sequence"] for row in decisions]
    assert sorted(set(sequences)) == list(range(sequences[0], sequences[-1] + 1)), directory
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
        if row["reason"].startswith("periodic:"):
            continue
        boards.append(dict(board, messages=row["messages"]))
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"]})
    knowledge = {}
    for row in rows:
        if row.get("type") == "knowledge":
            knowledge[row["knowledge"]["category"]] = row
    return boards, recorded, knowledge


def main():
    boards, recorded, knowledge = process(LAST)
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1a-529-q25-recall-wait-1117",
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
