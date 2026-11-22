"""Freeze the n1-c life-221 Quest 25 INT drain of 2026-11-23 (tests/test_n1c_221_q25_int_drain_1123_recorded.py).

Source: the viewing Magic-Eater n1-c life-221 (Lv39) on Quest 25 『幽霊屋敷』 (floor (0, 48, 25)), copied
read-only from the viewing server (~/hengbot-soak/n1-c/life-221/jsonlog) by the me-ranged-ev-1123 work
to C:/hengband/bot-client/.worktrees/me-ranged-ev-1123/scratch/raw:

  decisions-0500.jsonl     bot-decisions.jsonl's rows from 05:00:00 (decisions 61207-)
  snapshots-0500.jsonl.gz  the player_turn boards from turn 3191403 (after the drain)

The fixture keeps the board of decision 62859 (turn 3202357, [1,3]: no hostile in view, only the Druj sensed
far off, INT and WIS drained, ``quest25:rest-recharge``) and the decision rows that tell the case: 61207 (the
Potion of Restore Intelligence under the player on [7,1] before the drain), 61340 and 61345 (the shadow
demon's touches 「ひどく愚かになった気がする。」 / 「ひどく無知になった気がする。」), 61828 (the first
recharge rest after it, at the stairway door), 62859, and 63089
(the potion picked up only by the closing sweep, 05:03:48).

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband/bot-client/.worktrees/me-ranged-ev-1123/scratch/raw")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-221-q25-int-drain-1123.json.gz"
SEQUENCES = (61207, 61340, 61345, 61828, 62859, 63089)
BOARD_TURN = 3202357


def main():
    kept = {}
    with open(SOURCE / "decisions-0500.jsonl", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["decision_sequence"] in SEQUENCES:
                kept[row["decision_sequence"]] = {
                    "decision_sequence": row["decision_sequence"], "turn": row["turn"],
                    "time": row["time"], "reason": row["reason"], "key": row["key"],
                    "position": row["position"], "messages": row["messages"]}
    board = None
    with gzip.open(SOURCE / "snapshots-0500.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            raw = json.loads(line)
            if raw["turn"] == BOARD_TURN:
                board = raw   # the last board of the turn
    fixture = {"source": "n1-c life-221 Q25 decisions 61207-63089 and the board of turn 3202357 "
                         "(copied from the viewing server)",
               "board": board, "decisions": [kept[sequence] for sequence in SEQUENCES]}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(kept))


if __name__ == "__main__":
    main()
