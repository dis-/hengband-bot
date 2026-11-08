"""Freeze the n1-b life-338 Q2 boards of 2026-11-07 (the white crocodile's phase wait).

Source: the viewing Magic-Eater n1-b life-338 (Lv22), 鉄獄15階 fixed quest 2 (floor
(0, 15, 2)), stopped at 17:01:56 with ``loop-detected`` after waiting at [21,21] under
``quest:blocked:q2-phase-1044``.  Copied read-only from the viewing server:

  BOARDS     every quest-2 player board of the ring generations
             snapshots-20261107-170136-bc22af.jsonl.gz and snapshots-current.jsonl.gz
             of life-338/incident-captures/20261107-170155-loop-detected/snapshots
             (turns 1157684-1163042: the whole quest visit, entry to the stop)
  DECISIONS  the same capture's decision-tail.jsonl (the decision rows of those turns)

The fixture keeps the boards, the compact decision rows (turn, reason, key) and the
monster knowledge (lib/edit/MonraceDefinitions.jsonc) of every race on the boards and
of the quest's placements.  Only this extraction tool reads the copies; the committed
test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.quest_knowledge import load_quest_knowledge


EVIDENCE = Path("C:/Users/user/AppData/Local/Temp/claude/n1b-stops/life-338")
BOARDS = EVIDENCE / "q2-338-boards.jsonl.gz"
DECISIONS = EVIDENCE / "incident-captures/20261107-170155-loop-detected/decision-tail.jsonl"
GAME = Path("C:/hengband/lib/edit")
OUTPUT = Path(__file__).with_name("fixtures") / "q2-crocodile-kill-20261107.json.gz"


def main():
    with gzip.open(BOARDS, "rt", encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream]
    assert all(board["floor"]["quest_id"] == 2 for board in boards)
    turns = {board["turn"] for board in boards}
    decisions = []
    for line in DECISIONS.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue  # the tail's first line is cut
        if row.get("turn") in turns and row.get("floor", {}).get("quest_id") == 2:
            decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"]})
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    quest = load_quest_knowledge(GAME / "quests")[2]
    ids = {race for _, race in quest.battlefield.monster_placements}
    ids |= {row["race_id"] for board in boards
            for field in ("visible_monsters", "detected_monsters")
            for row in board.get(field, [])}
    fixture = {
        "source": f"{EVIDENCE} (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main()
