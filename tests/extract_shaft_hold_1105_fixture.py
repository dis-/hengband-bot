"""Freeze the n1-b life-313 boards of 2026-11-05 (shaft-hold-1105).

Source: the viewing Magic-Eater n1-b life-313, rows copied read-only to
C:/hengband-backups/pdca/captures/n1b-313-shaft-1105/ from its snapshot rings.
SHAFT: the walk on 鉄獄4階 onto the down shaft [51,56] (terrain 14), '>' at turn
704848, and the arrival on 鉄獄6階, random quest 49, at turn 704849.
RECALL: the boards of the town visit up to the arrival on 鉄獄1階 at turn 594591,
read at 12:22:28 as ``town:recall-to-angband`` (posted-descent-recall-rows.jsonl).

The fixture keeps those boards, the last skill-proficiency and Home knowledge
rows before each span, the absorbed-staff record of the life's later policy
state, the monster knowledge of their monsters and the RANDOM quest rows of
lib/edit/quests (the production quest knowledge).  Only this extraction tool
reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.quest_knowledge import (
    QUEST_TYPE_RANDOM, find_quest_definitions, load_quest_knowledge,
)


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-313-shaft-1105")
SHAFT = (704795, 704849)
RECALL = (591324, 594591)
OUTPUT = Path(__file__).with_name("fixtures") / "shaft-hold-n1b-313-1105.json.gz"


def span_boards(rows, first, last):
    boards, turns = [], set()
    for row in rows:
        if first <= row["turn"] <= last and row["turn"] not in turns:
            turns.add(row["turn"])
            boards.append(row)
    return boards


def main():
    rows = []
    for name in ("rows-town-visit-591300.jsonl.gz", "rows-spans.jsonl.gz"):
        with gzip.open(CAPTURE / name, "rt", encoding="utf-8") as stream:
            rows.extend(json.loads(line) for line in stream)
    knowledge = {}
    sequence = None
    for line in (CAPTURE / "knowledge-rows.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "sequence" in row:
            sequence = row["sequence"]
        else:
            knowledge[(row["before"], row["row"]["knowledge"]["category"])] = row["row"]
    shaft, recall = span_boards(rows, *SHAFT), span_boards(rows, *RECALL)
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = {row["race_id"] for board in (*shaft, *recall)
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    quests = load_quest_knowledge(find_quest_definitions(Path.cwd()))
    fixture = dict(
        source="n1-b life-313 snapshot rings of 2026-11-05 (copied from the viewing server)",
        shaft=shaft,
        recall=recall,
        skill=knowledge[(704700, "skill_exp")],
        home=knowledge[(704700, "home")],
        recall_skill=knowledge[(593900, "skill_exp")],
        recall_home=knowledge[(593900, "home")],
        sequence=sequence,
        monraces={key: asdict(races[key]) for key in sorted(ids)},
        random_quests=[asdict(info) for info in quests.values() if info.type == QUEST_TYPE_RANDOM],
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
