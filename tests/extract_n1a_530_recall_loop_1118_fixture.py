"""Freeze the boards of two of n1-a life-530's spent-at-once dives (2026-11-18 12:50, 古城 51F).

Source, copied read-only from the viewing server's life-530 jsonlog (snapshots/
snapshots-current.jsonl.gz and bot-decisions.jsonl) to C:/hengband-backups/pdca/
n1a-530-death-1118/cap/: n1a530_loop_boards.jsonl.gz (the player_turn boards of the game turns
below) and n1a530_loop_decisions.jsonl (their decision rows).

The turns: the last town board before a dive (13135700, decision 4441), its 51F arrival board
(13135701, 4442, return:recall on the board it landed on), the next town arrival (13135933,
4490), the last town board before the next dive (13140979, 4541), that dive's arrival
(13140981, 4542, return:recall again) and the next town arrival (13141224, 4595), whose visit
read Recall to the same 51F (12:50:43) for the fatal dive.  One board per turn: the last
player_turn board of the turn, its messages replaced by the turn's first decision row's
messages.  Only this tool reads the copies; the tests read the fixture.

    python tests/extract_n1a_530_recall_loop_1118_fixture.py
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/n1a-530-death-1118/cap")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-recall-loop-1118.json.xz"
TURNS = (13135700, 13135701, 13135933, 13140979, 13140981, 13141224)


def main() -> None:
    with gzip.open(SOURCE / "n1a530_loop_boards.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream]
    with open(SOURCE / "n1a530_loop_decisions.jsonl", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    decided, decisions = [], []
    for turn in TURNS:
        board = [raw for raw in boards if raw["turn"] == turn and raw["type"] == "player_turn"][-1]
        row = next(row for row in rows if row["turn"] == turn)
        decided.append(dict(board, messages=row["messages"]))
        decisions.append({"sequence": row["decision_sequence"], "turn": turn,
                          "reason": row["reason"], "key": row["key"]})
    FIXTURE.write_bytes(lzma.compress(
        json.dumps({"boards": decided, "decisions": decisions}, ensure_ascii=False)
        .encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
