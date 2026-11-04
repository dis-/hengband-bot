"""Freeze the n1-a Q18 boards of 2026-11-04 18:40 into tests/fixtures/q18-live-20261104.json.gz.

Source: the incident capture's snapshot tail (a multi-member gzip cut at its start).
Usage: python tests/extract_q18_live_fixture.py <snapshots-current.jsonl.gz>
"""
import gzip
import json
import re
import sys
import zlib
from pathlib import Path

TURNS = {2723388, 2723443, 2723620, 2723779}
OUT = Path(__file__).with_name("fixtures") / "q18-live-20261104.json.gz"


def main(path: str) -> None:
    data = Path(path).read_bytes()
    starts = [match.start() for match in re.finditer(b"\x1f\x8b\x08", data)]
    boards = {}
    for start, end in zip(starts, [*starts[1:], len(data)]):
        try:
            text = zlib.decompressobj(31).decompress(data[start:end])
        except zlib.error:
            continue
        for line in text.split(b"\n"):
            if not line.startswith(b"{"):
                continue
            try:
                board = json.loads(line.decode("utf-8", "surrogateescape"))
            except ValueError:
                continue
            if board.get("turn") in TURNS and board.get("floor", {}).get("quest_id") == 18:
                boards[board["turn"]] = board
    with gzip.open(OUT, "wt", encoding="utf-8", errors="surrogateescape") as stream:
        json.dump({"source": "n1-a life-479 incident 20261104-184034-player-death",
                   "boards": [boards[turn] for turn in sorted(boards)]}, stream)
    print(sorted(boards), OUT.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
