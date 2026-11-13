"""Freeze the n1-a life-520 Q18 boards of 2026-11-14 02:1x into tests/fixtures/q18-life520-20261114.json.gz.

Source: the tail of the life's state.jsonl (copied gzipped to
C:/hengband-backups/pdca/captures/n1a-520-death-1114/st520.gz; warrior Lv28, accepted on the
second force row, died on (5,23) at turn 1340740).  The floor's first board (1339020), the dig at
(2,6) (1340339), the siren's unseen curse there (1340352, HP 585->522), the first board after it
(1340364, (1,7)), and the boards at (2,13) after the last Healing potion and the fled seahorse
(1340599, 1340602, HP 379/553).
Usage: python tests/extract_q18_life520_fixture.py <state.jsonl.gz>
"""
import gzip
import json
import sys
from pathlib import Path

TURNS = (1339020, 1340339, 1340352, 1340364, 1340599, 1340602)
OUT = Path(__file__).with_name("fixtures") / "q18-life520-20261114.json.gz"


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
            if board.get("type") == "player_turn" and board.get("turn") in TURNS:
                boards[board["turn"]] = board  # the last board of the turn, as the bot decided on it
    with gzip.open(OUT, "wt", encoding="utf-8", errors="surrogateescape") as stream:
        json.dump({"source": "n1-a life-520 state.jsonl tail (2026-11-14 02:1x, floor (0,35,18))",
                   "boards": [boards[turn] for turn in TURNS]}, stream)
    print(sorted(boards), OUT.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
