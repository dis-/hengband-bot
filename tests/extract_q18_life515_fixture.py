"""Freeze the n1-a life-515 Q18 boards of 2026-11-12 15:14 into tests/fixtures/q18-life515-20261112.json.gz.

Source: the player-death capture's full-snapshots/snapshots-current.jsonl.gz (warrior Lv33 died on
(3,20) at turn 1806425, meleeing two seahorses 443 and a giant squid 482 at once; max HP
drained 716 -> 641 -> 485 by the seahorses' bites).  The floor's first board (1803953, max HP 716)
and the boards of decisions 48623-48633 (1806342 .. 1806416).
Usage: python tests/extract_q18_life515_fixture.py <snapshots-current.jsonl.gz>
"""
import gzip
import json
import sys
from pathlib import Path

TURNS = (1803953, 1806342, 1806351, 1806356, 1806366, 1806375, 1806383, 1806389, 1806393,
         1806402, 1806410, 1806416)
OUT = Path(__file__).with_name("fixtures") / "q18-life515-20261112.json.gz"


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
            if (board.get("type") == "player_turn" and board.get("turn") in TURNS
                    and board.get("floor", {}).get("quest_id") == 18):
                boards[board["turn"]] = board  # the last board of the turn, as the bot decided on it
    with gzip.open(OUT, "wt", encoding="utf-8", errors="surrogateescape") as stream:
        json.dump({"source": "n1-a life-515 player-death capture full-snapshots/snapshots-current.jsonl.gz "
                             "(2026-11-12 15:14, floor (0,35,18))",
                   "boards": [boards[turn] for turn in TURNS]}, stream)
    print(sorted(boards), OUT.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
