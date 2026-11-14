"""Freeze the n1-a life-523 Q18 boards of 2026-11-15 05:37 into tests/fixtures/q18-life523-20261115.json.gz.

Source: the state.jsonl tail of the loop stop capture 20261115-053739-loop-detected (build
62c26842b; copied read-only from the viewing server to
C:/hengband-backups/pdca/n1a-523-loop-1115/captures/): warrior Lv35, floor (0,35,18), the second
of three runs that each held the choke (1,19) for 200 actions with the giant squid 482 on (5,26)
known by ESP only, then stepped (1,19) '1' exit-to-choke, (2,18) '9' exit-walk until the stop.
Its 135 boards: 131 on (1,19) and 4 on (2,18), turns 3772857..3774195.
Usage: python tests/extract_q18_life523_fixture.py <state.jsonl.gz>
"""
import gzip
import json
import sys
from pathlib import Path

OUT = Path(__file__).with_name("fixtures") / "q18-life523-20261115.json.gz"


def main(path: str) -> None:
    boards = []
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            if not line.startswith("{"):
                continue
            try:
                board = json.loads(line)
            except ValueError:
                continue
            if board.get("type") == "player_turn" and board.get("floor", {}).get("quest_id") == 18:
                boards.append(board)
    with gzip.open(OUT, "wt", encoding="utf-8", errors="surrogateescape") as stream:
        json.dump({"source": "n1-a life-523 captures/20261115-053739-loop-detected/state.jsonl.gz "
                             "(2026-11-15 05:37, floor (0,35,18))",
                   "boards": boards}, stream)
    print(len(boards), boards[0]["turn"], boards[-1]["turn"], OUT.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
