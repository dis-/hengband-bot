"""Extract the quest floor boards of n1-a life-485 (2026-11-05, random quest 45).

Input: the capture's jsonlog/snapshots/snapshots-current.jsonl.gz (a multi-member gzip
file), from C:\\hengband-backups\\pdca\\captures\\n1a-485-1105\\cap.tgz.
Output: every player_turn row of the floor, from the arrival to the loop's stop, once.

Usage (repository root):
  PYTHONPATH=src python tests/extract_hunt_walk_in_sight_1105_fixture.py <snapshots-current.jsonl.gz>
"""
import json
import lzma
from pathlib import Path
import sys
import zlib

OUTPUT = Path(__file__).with_name("fixtures") / "hunt-walk-in-sight-1105.json.xz"
FLOOR = {"dungeon_id": 1, "level": 38, "quest_id": 45}
CHUNK = 1 << 16
HEADER = bytes((0x1f, 0x8b, 0x08))


def _members(data: bytes) -> bytes:
    """Every decodable gzip member from the first header on (the file is a rotated tail)."""
    parts = []
    start = data.find(HEADER)
    while 0 <= start < len(data):
        stream = zlib.decompressobj(31)
        offset = start
        decoded = []
        try:
            while not stream.eof and offset < len(data):
                decoded.append(stream.decompress(data[offset:offset + CHUNK]))
                offset += CHUNK
        except zlib.error:
            start = data.find(HEADER, start + 1)
            continue
        parts.extend(decoded)
        if not stream.eof:
            break
        start = offset - len(stream.unused_data)
    return b"".join(parts)


def _on_floor(row: dict) -> bool:
    return row.get("type") == "player_turn" and all(
        row.get("floor", {}).get(name) == value for name, value in FLOOR.items())


def extract(path: Path) -> list:
    rows = {}
    for line in _members(path.read_bytes()).split(b"\n"):
        if b"player_turn" not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if _on_floor(row):
            rows.setdefault(row["turn"], line.decode("utf-8", "surrogateescape"))
    return [rows[turn] for turn in sorted(rows)]


if __name__ == "__main__":
    lines = extract(Path(sys.argv[1]))
    payload = json.dumps(lines, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape"), preset=9))
    print(OUTPUT, OUTPUT.stat().st_size, len(lines))
