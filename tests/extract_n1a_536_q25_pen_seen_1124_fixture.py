"""Freeze n1-a life-536's Quest 25 boards from the floor's first decision to its phase-2 pen shots.

Source: n1-a life-536 (Zombie warrior Lv38, build of main 6680ef109d's day) on hengband.net, died
2026-11-24 20:53:20 in Quest 25.  Copied to C:/hengband-backups/pdca/captures/n1a-536-q25-death-1124:
``snapshots-current.jsonl.gz`` (~/hengbot-soak/n1-a/life-536/jsonlog/snapshots, 20:41:47-20:53:20,
every board of the quest), ``n1a536-q25-decisions.jsonl.gz`` (the rows of jsonlog/bot-decisions.jsonl
on the quest floor, decisions 10525-11126, one process) and ``q25-battle.json`` (the record the
process left at the death).  Boards are matched to decisions by turn as
tests/extract_n1b_382_q25_patrol_owner_1113_fixture.py ``process`` matches them; the cut is the
quest's first decision through ``LAST`` (the first board of the long hold on [5,1] after the phase
2 shots).  The skill knowledge is the last ``skill_exp`` row before the first board.

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

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-536-q25-pen-seen-1124.json.gz"
QUEST = 25
LAST = 10910


def _rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue   # the live file's last line may be cut


def main():
    decisions = [row for row in _rows(ROOT / "n1a536-q25-decisions.jsonl.gz")
                 if row.get("floor", {}).get("quest_id") == QUEST and row["decision_sequence"] <= LAST]
    sequences = [row["decision_sequence"] for row in decisions]
    assert sequences == list(range(sequences[0], sequences[0] + len(sequences))), sequences[:3]
    first_turn = decisions[0]["turn"]
    by_turn = collections.defaultdict(list)
    skill = None
    for row in _rows(ROOT / "snapshots-current.jsonl.gz"):
        if row.get("type") == "player_turn":
            by_turn[row["turn"]].append(row)
        elif (row.get("type") == "knowledge" and row["knowledge"].get("category") == "skill_exp"
              and row.get("turn", 0) <= first_turn):
            skill = row
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
    assert skill is not None
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1a-536-q25-death-1124", second=dict(boards=boards, recorded=recorded),
                skill=skill, monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                death_record=json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")))
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']}\n")


if __name__ == "__main__":
    main()
