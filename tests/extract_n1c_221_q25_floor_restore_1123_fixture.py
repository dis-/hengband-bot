"""Freeze the n1-c life-221 Quest 25 board beside the floor Restore Intelligence (2026-11-23).

For tests/test_n1c_221_q25_floor_restore_1123_recorded.py.  Source: the viewing Magic-Eater n1-c
life-221 (Lv39) on Quest 25 『幽霊屋敷』 (floor (0, 48, 25)), read-only from the viewing server
(~/hengbot-soak/n1-c/life-221/jsonlog):

  raw-0500-boards.jsonl.gz  the player_turn boards of turns 3181971-3184441, taken from
                            snapshots/snapshots-20261123-051535-c5dec8.jsonl.gz with
                            ``zcat ... | grep -E '"turn":(3181971|3181976|3182246|3183351|3184427|3184441)[,}]'``
                            (a local copy at the worktree's top, not committed)
  decisions-0500.jsonl      bot-decisions.jsonl's rows from 05:00:00, copied by the me-ranged-ev-1123
                            work to C:/hengband/bot-client/.worktrees/me-ranged-ev-1123/scratch/raw

The fixture keeps the last board of turn 3184427 (decision 61363, ``quest-strategy:hold`` '5' on [5,1],
no hostile in view; INT and WIS drained by the shadow demon at 05:00:11; the found Restore Intelligence
on [7,1], sval 43, two steps off) and the decision rows 61351 and 61359 (``quest25:rest-recharge`` on
the same cell) and 61363.

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

BOARDS = Path(__file__).parents[1] / "raw-0500-boards.jsonl.gz"
DECISIONS = Path("C:/hengband/bot-client/.worktrees/me-ranged-ev-1123/scratch/raw/decisions-0500.jsonl")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-221-q25-floor-restore-1123.json.gz"
SEQUENCES = (61351, 61359, 61363)
BOARD_TURN = 3184427


def main():
    kept = {}
    with open(DECISIONS, encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["decision_sequence"] in SEQUENCES:
                kept[row["decision_sequence"]] = {
                    "decision_sequence": row["decision_sequence"], "turn": row["turn"],
                    "time": row["time"], "reason": row["reason"], "key": row["key"],
                    "position": row["position"], "messages": row["messages"]}
            if row["decision_sequence"] > max(SEQUENCES):
                break
    board = None
    with gzip.open(BOARDS, "rt", encoding="utf-8") as stream:
        for line in stream:
            raw = json.loads(line)
            if raw["turn"] == BOARD_TURN:
                board = raw   # the last board of the turn
    fixture = {"source": "n1-c life-221 Q25 decisions 61351-61363 and the board of turn 3184427 "
                         "(copied from the viewing server)",
               "board": board, "decisions": [kept[sequence] for sequence in SEQUENCES]}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(kept))


if __name__ == "__main__":
    main()
