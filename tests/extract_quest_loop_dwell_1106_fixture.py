"""Build tests/fixtures/quest-loop-dwell-1106.json.xz from the boards of n1-b life-317.

Usage: extract_quest_loop_dwell_1106_fixture.py <quest40-boards-all.jsonl.gz> <state.jsonl.gz>

The first file holds every snapshot of Angband 50F, RANDOM quest 40 (the rolling snapshots of
the life); the second is state.jsonl.gz of 20261105-220306-stall-floor-dwell-quest-search-loop.
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

ENTRY = (2344266, 2345300)  # the arrival, the retreats that left the column of vetoes, the give-up
WEST = 2429363              # the first recorded board past the column, after the restart

OUTPUT = Path(__file__).parent / "fixtures" / "quest-loop-dwell-1106.json.xz"


def main(boards_path: str, state_path: str) -> None:
    entry, west = [], None
    with gzip.open(boards_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            turn = json.loads(line)["turn"]
            if ENTRY[0] <= turn <= ENTRY[1]:
                entry.append(line.rstrip("\n"))
            elif turn == WEST and west is None:
                west = line.rstrip("\n")
    with gzip.open(state_path, "rt", encoding="utf-8") as stream:
        stop = stream.read().splitlines()[-1]
    OUTPUT.write_bytes(lzma.compress(json.dumps(
        {"entry": entry, "stop": stop, "west": west}, ensure_ascii=False).encode("utf-8")))
    print(len(entry), OUTPUT.stat().st_size)


if __name__ == "__main__":
    main(*sys.argv[1:])
