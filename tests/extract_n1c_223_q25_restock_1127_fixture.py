"""Freeze n1-c life-223's Quest 25 boards from the floor's first decision to the restock's Recall read.

Source: n1-c life-223 (Zombie Magic-Eater CL42, build bot-f108be477) on hengband.net, Quest 25 taken
2026-11-27 06:55:56, entered 06:56:13 (turn 4300490), failed 06:56:41 (turn 4303971).  Copied to
C:/hengband-backups/pdca/captures/n1c-223-q25-restock-1127: ``n1c223-q25-decisions.jsonl.gz`` (the rows
of ~/hengbot-soak/n1-c/life-223/jsonlog/bot-decisions.jsonl.5 for turns 4300400-4304300, decisions
3950-4377, one process), ``n1c223-q25-snapshots.jsonl.gz`` (the last ``skill_exp`` knowledge row before
the floor, then the ``player_turn`` boards of turns 4300400-4304000 of jsonlog/snapshots
snapshots-20261127-064323-8ed2d8 and -070525-c4936f) and ``quest-attempts.jsonl``.  Boards are matched
to decisions by turn as tests/extract_n1a_536_q25_pen_seen_1124_fixture.py matches them; the cut is the
quest's first decision (3958) through ``LAST`` (4340, ``quest25:restock-recall``).

The life's logs keep no magic-eater device list (bA/bB/bC screens are not in the boards and no
checkpoint was written in the window), so the fixture has none.

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
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-223-q25-restock-1127.json.gz"
QUEST = 25
LAST = 4340


def _rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    decisions = [row for row in _rows(ROOT / "n1c223-q25-decisions.jsonl.gz")
                 if row.get("floor", {}).get("quest_id") == QUEST and row["decision_sequence"] <= LAST]
    sequences = [row["decision_sequence"] for row in decisions]
    assert sequences == list(range(sequences[0], sequences[0] + len(sequences))), sequences[:3]
    snapshots = list(_rows(ROOT / "n1c223-q25-snapshots.jsonl.gz"))
    skill = snapshots[0]
    assert skill.get("type") == "knowledge" and skill["knowledge"].get("category") == "skill_exp"
    by_turn = collections.defaultdict(list)
    for row in snapshots[1:]:
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
                         "reason": row["reason"], "key": row["key"],
                         "heal_potions": row["fixedquest_readiness"]["strategy_force"]["heal_potions"]})
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    attempts = [json.loads(line) for line in
                (ROOT / "quest-attempts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    case = dict(source="n1c-223-q25-restock-1127", second=dict(boards=boards, recorded=recorded),
                skill=skill, monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                attempts=attempts)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']}\n")


if __name__ == "__main__":
    main()
