"""Freeze the n1-a life-516 Q18 boards of 2026-11-12 17:39 into tests/fixtures/q18-life516-20261112.json.gz.

Source: the player-death capture's snapshots/snapshots-current.jsonl.gz (warrior Lv28, max HP 564,
accepted on the second force row with 7 Potions of Speed against its 6; died on the choke (1,12) at
turn 1371193 with 3 left, max HP drained to 417 by the seahorses' bites).  The last town board
before the entrance (1369361, decision 17065, quest 18 taken) and the floor's first board
(1369362, decision 17066).
Usage: python tests/extract_q18_life516_fixture.py <snapshots-current.jsonl.gz>
"""
import gzip
import json
import sys
from pathlib import Path

TURNS = (1369361, 1369362)
OUT = Path(__file__).with_name("fixtures") / "q18-life516-20261112.json.gz"


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
        json.dump({"source": "n1-a life-516 player-death capture snapshots/snapshots-current.jsonl.gz "
                             "(2026-11-12 17:39, floor (0,35,18))",
                   "boards": [boards[turn] for turn in TURNS]}, stream)
    print(sorted(boards), OUT.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
