"""Extract the Mountain 50F sensed-T1 board of n1-b life-367 (2026-11-10 20:57:23).

Input: snapshots-20261110-210702-165f14.jsonl.gz of the life's jsonlog/snapshots (a
multi-member gzip file; a slice of its lines also works).
Output: the player_turn rows of the arrival (turn 5346951, decision 12800) through turn 5347005
(decision 12807, the live sensed-t1:teleport "rf" at 629/629 HP: ハヤブサ (Ki-43, vision 100)
detected, none in view).
"""
import json
import lzma
from pathlib import Path
import sys
import zlib

OUTPUT = Path(__file__).with_name("fixtures") / "sensed-t1-approach-1110.json.xz"
TURNS = (5346951, 5346957, 5346966, 5346974, 5346981, 5346989, 5346999, 5347005)


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
