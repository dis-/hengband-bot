"""Build tests/fixtures/maze-seal-1106.jsonl.xz from the boards of n1-c life-153.

Usage: extract_maze_seal_1106_fixture.py <boards.jsonl.gz>

The input holds the snapshots of n1-c life-153's 20:50:46 incident capture (build
bot-cbdf723f5; snapshots-current.jsonl.gz, a tail whose first gzip member starts past its
first bytes) between turns 888815 and 889640; the fixture keeps every Labyrinth 13F board
from the arrival (turn 888821) through turn 889635, four boards into the stuck:wander.
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

LABYRINTH, LEVEL = 4, 13
LAST_TURN = 889635

OUTPUT = Path(__file__).parent / "fixtures" / "maze-seal-1106.jsonl.xz"


def main(boards_path: str) -> None:
    lines = []
    with gzip.open(boards_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.startswith("{"):
                continue
            raw = json.loads(line)
            floor = raw["floor"]
            if (floor["dungeon_id"], floor["level"]) == (LABYRINTH, LEVEL) and raw["turn"] <= LAST_TURN:
                lines.append(line.rstrip("\n"))
    OUTPUT.write_bytes(lzma.compress("\n".join(lines).encode("utf-8")))
    print(len(lines), OUTPUT.stat().st_size)


if __name__ == "__main__":
    main(*sys.argv[1:])
