"""Freeze n1-c life-200's last two Quest 25 processes (2026-11-12 12:03:00-12:03:13) for the warning test.

Source: n1-c life-200 (Magic-Eater Lv36) on hengband.net, the stop captures
captures/20261112-120256-no-key-exhausted (the first process, decisions 18062-18188), captures/20261112-120308-no-key-exhausted (the second process of the floor, decisions 0-54, from
its restart at 12:03:00 to its no-key stop) and captures/20261112-120315-exit-no-marker (the third
process, decisions 0-8, from its restart at 12:03:12 to the death), copied to
C:/hengband-backups/pdca/captures/n1c-200-death-1112/.

One board per recorded decision of each process (the decisions of one turn take that turn's last
rows in order) with its decision row's messages and the recorded reason and key; the state ring of
each capture is a tail shared by the processes, so a process's rows are those at or after the turn
of its first decision whose sequence restarted at 0.

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

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-200-death-1112/captures")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-200-q25-warning-restart-1112.json.gz"
QUEST = 25
# The first process from the board after the hound fell (decision 18062, the first its state ring
# holds) through its no-key stop (18188); added 2026-11-12 for the Q25 no-teleport plan.
FIRST = ("20261112-120256-no-key-exhausted", 18062, 18188, 3187217)
SECOND = ("20261112-120308-no-key-exhausted", 0, 54, 3188057)
THIRD = ("20261112-120315-exit-no-marker", 0, 8, 3188301)


def _decisions(path: Path) -> list[dict]:
    found = []
    with gzip.open(path, "rt", encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            try:
                found.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return found


def process(directory: str, first: int, last: int, start_turn: int):
    capture = ROOT / directory
    rows = ring_rows(capture / "state.jsonl.gz")
    decisions = [row for row in _decisions(capture / "bot-decisions.jsonl.gz")
                 if "decision_sequence" in row and first <= row["decision_sequence"] <= last
                 and row["turn"] >= start_turn and row.get("floor", {}).get("quest_id") == QUEST]
    assert [row["decision_sequence"] for row in decisions] == list(range(first, last + 1)), directory
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
    first_boards, first_recorded, _ = process(*FIRST)
    second_boards, second_recorded, knowledge = process(*SECOND)
    third_boards, third_recorded, _ = process(*THIRD)
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in (*first_boards, *second_boards, *third_boards)
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1c-200-q25-warning-restart-1112",
                first=dict(boards=first_boards, recorded=first_recorded),
                second=dict(boards=second_boards, recorded=second_recorded),
                third=dict(boards=third_boards, recorded=third_recorded),
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(first_boards)} {len(second_boards)} {len(third_boards)} "
                     f"{sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
