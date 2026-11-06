"""Build tests/fixtures/immobile-kill-1106.jsonl.xz from the boards of n1-c life-156.

Usage: extract_immobile_kill_1106_fixture.py <boards.jsonl.gz>

The input holds the rolling snapshots of n1-c life-156 around its Labyrinth 10F visit
(build 87d9fd576); the fixture keeps every Labyrinth 10F board from the arrival through
the first board of the stall (turn 1034095).
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

LABYRINTH, LEVEL = 4, 10
LAST_TURN = 1034095

OUTPUT = Path(__file__).parent / "fixtures" / "immobile-kill-1106.jsonl.xz"


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
