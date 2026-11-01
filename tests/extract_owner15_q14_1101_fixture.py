"""Freeze the n1-c life-092 Q14 boards (#47, owner15-survival-1101).

Source (read-only, copied from the viewing server with scp/ssh by the
owner15-survival-1101 diagnosis): C:/hengband-backups/pdca/captures/
owner15-survival-1101/n1-c/life-092/ -- the life's state.jsonl rows on
イークの洞穴5階 with quest 14 (ワーグを殱滅せよ, KILL_LEVEL) TAKEN, turns
2636850..2637300 (state-q14-2636850-2637300.jsonl), and the
jsonlog/bot-decisions.jsonl rows of the same turns
(decisions-q14-2636850-2637300.jsonl).  Build bot-b51bcda79 era (life-092,
Lv21-22 Magic-Eater, fifteen Scrolls of Teleportation).

The case keeps the player_turn boards of turns 2636950..2637028 (the
character explores the quest floor, no hostile in view; one board per turn,
the last of the turn) and the recorded decision rows of those turns.  Only
this extraction tool reads the copies; the committed test reads the frozen
fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_dungeon_1031_fixture import decisions_by_turn, sha, tail_rows


ROOT = Path("C:/hengband-backups/pdca/captures/owner15-survival-1101")
LIFE = ROOT / "n1-c/life-092"
STATE = LIFE / "state-q14-2636850-2637300.jsonl"
DECISIONS = LIFE / "decisions-q14-2636850-2637300.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "owner15-q14-1101.json.gz"
FIRST, LAST = 2636950, 2637028
QUEST_FLOOR = (2, 5)


def quest_floor_boards(rows: list[dict]) -> list[dict]:
    by_turn = {
        row["turn"]: row
        for row in rows
        if row.get("type") == "player_turn"
        and FIRST <= row["turn"] <= LAST
        and (row["floor"]["dungeon_id"], row["floor"]["level"]) == QUEST_FLOOR
    }
    return [by_turn[turn] for turn in sorted(by_turn)]


def main():
    boards = quest_floor_boards(tail_rows(STATE))
    decisions = decisions_by_turn(tail_rows(DECISIONS))
    case = dict(
        source=str(LIFE.relative_to(ROOT)).replace("\\", "/"),
        sources={STATE.name: sha(STATE), DECISIONS.name: sha(DECISIONS)},
        boards=boards,
        decisions=[decisions.get(board["turn"]) for board in boards],
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards))


if __name__ == "__main__":
    main()
