"""Freeze the n1-a life-495 Q18 boards of 2026-11-08 00:15 into tests/fixtures/q18-life495-20261108.json.gz.

Source: life-495/jsonlog/snapshots/snapshots-current.jsonl.gz (the swordfish 88 on (10,13) in
view from (3,20) only; the bot rocked (3,20) <-> (2,20) until the loop guard stopped it).
Usage: python tests/extract_q18_life495_fixture.py <snapshots-current.jsonl.gz>
"""
import gzip
import json
import sys
from pathlib import Path

TURNS = (1413514, 1413519, 1413558)  # on (3,20), (2,20), (1,19)
OUT = Path(__file__).with_name("fixtures") / "q18-life495-20261108.json.gz"


def main(path: str) -> None:
    boards = {}
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            if not line.startswith("{"):
                continue
            try:
                board = json.loads(line)
            except ValueError:
                continue
            if board.get("turn") in TURNS and board.get("floor", {}).get("quest_id") == 18:
                boards.setdefault(board["turn"], board)
    with gzip.open(OUT, "wt", encoding="utf-8", errors="surrogateescape") as stream:
        json.dump({"source": "n1-a life-495 jsonlog/snapshots/snapshots-current.jsonl.gz "
                             "(2026-11-08 00:15, floor (0,35,18))",
                   "boards": [boards[turn] for turn in TURNS]}, stream)
    print(sorted(boards), OUT.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
