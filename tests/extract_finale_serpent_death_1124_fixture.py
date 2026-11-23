"""Build tests/fixtures/finale-serpent-death-n1b-416-1124.jsonl.gz (n1-b life-416's whole Angband 100F
floor up to the death, 2026-11-24 05:24:28).

Sources: the boards of tests/fixtures/finale-100f-pingpong-n1b-416-1124.jsonl.gz (turns
4775263-4778564, the floor from its arrival) and the player_turn lines of the death capture's
snapshot ring (incident-captures/20261124-052428-player-death/snapshots/snapshots-current.jsonl.gz,
turns 4777025-4781304) past the last of those.  The ring was copied while it was written: its
first member is cut, so the decoder skips to the next gzip header.  Each row keeps only the fields
that differ from the previous row and names the rest in ``_same`` (tests/support/finale_416.boards).

Usage: python tests/extract_finale_serpent_death_1124_fixture.py <snapshots-current.jsonl.gz>
"""
from __future__ import annotations

import gzip
import json
import sys
import zlib
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EARLIER = "finale-100f-pingpong-n1b-416-1124.jsonl.gz"
OUT = "finale-serpent-death-n1b-416-1124.jsonl.gz"


def ring_lines(path: Path):
    data = path.read_bytes()
    position, pending = 0, b""
    while position < len(data):
        stream = zlib.decompressobj(31)
        try:
            pending += stream.decompress(data[position:])
        except zlib.error:
            following = data.find(b"\x1f\x8b\x08", position + 1)
            if following < 0:
                break
            position = following
            continue
        if not stream.eof:
            break
        position = len(data) - len(stream.unused_data)
    for line in pending.split(b"\n"):
        if line.strip():
            yield line


def main(ring: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.support.finale_416 import boards
    rows = boards(EARLIER)
    last = rows[-1]["turn"]
    for line in ring_lines(Path(ring)):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("type") == "player_turn" and row["turn"] > last:
            rows.append(row)
    previous = None
    with gzip.open(FIXTURES / OUT, "wt", encoding="utf-8") as stream:
        for row in rows:
            written = row
            if previous is not None:
                same = [key for key in row if key in previous and previous[key] == row[key]
                        and key not in ("type", "turn")]
                written = {key: value for key, value in row.items() if key not in same}
                if same:
                    written["_same"] = same
            stream.write(json.dumps(written, ensure_ascii=False, separators=(",", ":")) + "\n")
            previous = row
    print(len(rows), rows[0]["turn"], rows[-1]["turn"])


if __name__ == "__main__":
    main(sys.argv[1])
