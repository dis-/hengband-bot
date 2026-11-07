"""Freeze the n1-c life-164 boards of Quest 25 (2026-11-08 03:29:46-03:29:49) for the mass-recall test.

Source: n1-c life-164 (build bot-b09646c96) on hengband.net, ~/hengbot-soak/n1-c/life-164/jsonlog,
copied to C:/hengband-backups/pdca/captures/n1c-164-q25-recall-1108/
(snapshots-20261108-033049-f86972.jsonl.gz, the snapshot ring; bot-decisions-0329.jsonl.gz, the
decision log of the process started at 03:29:46).  The process resumed the save on [1,18] of the
quest floor at turn 2903272, struck the corpse masses beside it, held, and on decision 43 read Word
of Recall for ``breeder-breakthrough:recall``.  One board per recorded decision of that process on
the quest floor through ``LAST_SEQUENCE``: the ring's last row of that turn written by this process
(the ring also holds the 11-07 15:36 process's boards of the same turns), with the decision row's
messages.  The recorded reason and key of each board are kept.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-164-q25-recall-1108")
OUTPUT = Path(__file__).with_name("fixtures") / "q25-recall-n1c-164-1108.json.gz"
QUEST = 25
START_TURN = 2903272
LAST_SEQUENCE = 50


def gz_rows(path: Path) -> list[dict]:
    found = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        try:
            for line in stream:
                try:
                    found.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # The live ring may end in a partial line.
        except EOFError:
            pass
    return found


def main():
    rows = gz_rows(ROOT / "snapshots-20261108-033049-f86972.jsonl.gz")
    decisions = [row for row in gz_rows(ROOT / "bot-decisions-0329.jsonl.gz")
                 if "decision_sequence" in row and row.get("floor", {}).get("quest_id") == QUEST
                 and 1 <= row["decision_sequence"] <= LAST_SEQUENCE]
    # The process's first board: the last time the ring's turns went back to the resumed save.
    turns = [(index, row["turn"]) for index, row in enumerate(rows) if row["type"] == "player_turn"]
    begin = max(index for (index, turn), (_before, previous) in zip(turns[1:], turns)
                if turn == START_TURN and previous > turn)
    last = {row["turn"]: row for row in rows[begin:]
            if row["type"] == "player_turn" and row.get("floor", {}).get("quest_id") == QUEST}
    boards, recorded = [], []
    for row in decisions:
        boards.append(dict(last[row["turn"]], messages=row["messages"]))
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"], "rung": row.get("rung")})
    knowledge = {}
    for row in rows[:begin + 4]:
        if row["type"] == "knowledge":
            knowledge[row["knowledge"]["category"]] = row
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1c-164-q25-recall-1108", boards=boards, recorded=recorded,
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"),
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races})
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(boards)} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
