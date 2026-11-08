"""Extract the n1-c life-166 wilderness Recall boards (2026-11-08 09:36:01).

Usage:
    python tests/extract_wilderness_recall_1108_fixture.py \
        <life-166>/jsonlog/snapshots/snapshots-current.jsonl.gz \
        <life-166>/jsonlog/bot-decisions.jsonl

The third session after the reload (turn 3079866) posted '<'
(wilderness:enter-global), read the refusal 「敵がすぐ近くにいるときは広域
マップに入れない！ <x3>」 and read Word of Recall as wilderness:recall ('rg',
no destination letter); the executor cancelled the chooser and stopped as
stuck-prompt:wilderness:recall.  The fixture keeps that session's first board
and its refusal board, and the recorded decision rows of the three sessions.
"""

import gzip
import json
import sys
from pathlib import Path

TURN = 3079866
OUT = Path(__file__).with_name("fixtures") / "wilderness-recall-1108.json.gz"


def main(snapshots: str, decisions: str) -> None:
    boards = []
    with gzip.open(snapshots, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.startswith("{"):
                continue
            row = json.loads(line)
            if row["turn"] == TURN and row.get("type") == "player_turn":
                boards.append(row)
    boards = [boards[0], next(row for row in boards if row["messages"])]
    rows = []
    with open(decisions, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.startswith("{"):
                continue
            row = json.loads(line)
            if "2026-11-08T09:35:45" <= str(row.get("time", "")) and row.get("reason", "").startswith("wilderness:"):
                rows.append({"time": row["time"], "turn": row["turn"],
                             "reason": row["reason"], "key": row["key"]})
    with gzip.open(OUT, "wt", encoding="utf-8") as stream:
        json.dump({"boards": boards, "decisions": rows}, stream, ensure_ascii=False)


if __name__ == "__main__":
    main(*sys.argv[1:3])
