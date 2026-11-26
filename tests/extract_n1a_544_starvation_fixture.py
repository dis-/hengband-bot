"""Extract tests/fixtures/n1a-544-starvation-1126/.

Source: n1-a life-544's death capture 20261126-234538-player-death (Amberite rogue CL14,
starved in the Outpost, 2026-11-26 23:45:38), copied read-only from the viewing server.

* ``town-arrival/`` (the recall arrival of 23:42:43, turn 310571): journal rows 0-12 kept
  (row 8 the first General Store page, rows 9-11 the first round of the step-off/step-on loop).
* ``boards.jsonl.gz``: three player_turn boards of the last dive from
  ``snapshots/snapshots-current.jsonl.gz`` (a tail-capped ring: decoded from its first whole gzip
  member): turn 287247 (Yeek cave 10F, 2 Jerky + 1 Ration + 1 Slime Mold carried),
  304358 (12F, hungry, the Slime Mold left) and 310257 (10F, hungry, nothing edible).

    python tests/extract_n1a_544_starvation_fixture.py <incident-capture-dir>
"""
import gzip
import json
import sys
import zlib
from pathlib import Path

from support.town_arrival_fixture import extract

TARGET = Path(__file__).with_name("fixtures") / "n1a-544-starvation-1126"
ROWS = 13
TURNS = (287247, 304358, 310257)


def ring_rows(path: Path):
    data = path.read_bytes()
    start = data.find(b"\x1f\x8b\x08")
    while start >= 0:
        try:
            zlib.decompressobj(31).decompress(data[start:start + 65536])
            break
        except zlib.error:
            start = data.find(b"\x1f\x8b\x08", start + 1)
    rest, text = data[start:], b""
    while rest:
        member = zlib.decompressobj(31)
        try:
            text += member.decompress(rest)
        except zlib.error:
            break
        rest = member.unused_data
    for line in text.splitlines():
        try:
            yield json.loads(line)
        except ValueError:
            continue


def main(capture: str) -> None:
    capture = Path(capture)
    extract(capture / "town-arrival", TARGET, ROWS)
    boards = {}
    for row in ring_rows(capture / "snapshots" / "snapshots-current.jsonl.gz"):
        if row.get("type") == "player_turn" and row["turn"] in TURNS:
            boards.setdefault(row["turn"], row)
    with gzip.open(TARGET / "boards.jsonl.gz", "wt", encoding="utf-8") as stream:
        for turn in TURNS:
            stream.write(json.dumps(boards[turn], ensure_ascii=False, separators=(",", ":")) + "\n")
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main(*sys.argv[1:])
