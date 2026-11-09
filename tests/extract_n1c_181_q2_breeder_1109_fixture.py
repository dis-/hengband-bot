"""Freeze the n1-c life-181 Q2 boards of 2026-11-09 (the corpse masses and the Recall).

Source: the viewing Magic-Eater n1-c life-181 (Lv20-21, 285 max HP), 鉄獄 fixed quest 2
(下水道), 12:52:52-12:53:30.  It shot the corpse masses (race 202) from the west end of their
room, walked between kills, and read Recall (``breeder-breakthrough:recall``) at full HP on
turn 767148.  Copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-181-q2-breeder-1109/n1c181:

  BOARDS     every quest-2 ``player_turn`` line of life-181/state.jsonl (turns 763280-767346)
  SKILL      the quest-2 ``knowledge`` line of the same file (the ~f reply of turn 766344)
  DECISIONS  the quest-2 rows of life-181/jsonlog/bot-decisions.jsonl (turn, reason, key)

The fixture keeps the boards, the compact decision rows and the monster knowledge
(lib/edit/MonraceDefinitions.jsonc) of every race on the boards and of the quest's
placements.  Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.quest_knowledge import load_quest_knowledge


EVIDENCE = Path("C:/hengband-backups/pdca/captures/n1c-181-q2-breeder-1109/n1c181")
BOARDS = EVIDENCE / "q2-state.jsonl"
DECISIONS = EVIDENCE / "q2-decisions.jsonl"
GAME = Path("C:/hengband/lib/edit")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-181-q2-breeder-20261109.json.gz"


def main():
    boards, skills = [], []
    for line in BOARDS.read_text(encoding="utf-8").splitlines():
        board = json.loads(line)
        if board["floor"]["quest_id"] != 2:
            continue
        if board.get("type") == "player_turn":
            boards.append(board)
        elif board.get("type") == "knowledge":
            skills.append(board)
    (skill,) = skills
    decisions = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
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
        "skill": skill,
        "decisions": decisions,
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main()
