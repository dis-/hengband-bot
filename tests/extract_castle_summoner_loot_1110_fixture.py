"""Extract the Castle 48F summoner boards of n1-b life-367 (2026-11-10 20:43:29).

Input: snapshots-20261110-205136-741f0b.jsonl.gz of the life's jsonlog/snapshots (a
multi-member gzip file; a slice of its lines also works).
Output: the player_turn rows of turns 5245987-5245999 (decisions 7302-7305; the last is the
live emergency:destruction:absorbed-power under emergency-summoner at 629/629 HP, tier T3).
"""
import json
import lzma
from pathlib import Path
import sys
import zlib

OUTPUT = Path(__file__).with_name("fixtures") / "castle-summoner-loot-1110.json.xz"
TURNS = (5245987, 5245990, 5245995, 5245999)


def _members(data: bytes) -> bytes:
    decoded = b""
    while data:
        stream = zlib.decompressobj(31)
        decoded += stream.decompress(data)
        data = stream.unused_data
    return decoded


def _row(line: str):
    try:
        return json.loads(line)
    except ValueError:
        return None  # a line cut at the slice's edge


def extract(path: Path) -> list:
    lines = _members(path.read_bytes()).decode("utf-8", "surrogateescape").splitlines()
    rows = {}
    for line in lines:
        row = _row(line) if line.strip() else None
        if row is not None and row.get("turn") in TURNS and row.get("type") == "player_turn":
            rows.setdefault(row["turn"], line)
    return [rows[turn] for turn in TURNS]


if __name__ == "__main__":
    rows = extract(Path(sys.argv[1]))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(rows))
