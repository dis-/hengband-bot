"""Extract the town board of n1-b life-367 that recalled to the Mountain 50F (2026-11-10 20:52).

Input: snapshots-20261110-210702-165f14.jsonl.gz of the life's jsonlog/snapshots (a
multi-member gzip file; a slice of its lines also works).
Output: the player_turn state row of turn 5332164 (decision 11796, town:recall-to-alt-dungeon
"rgg": the Mountain, whose recall landing is its last floor, 50F, the guardian
大鷲王『ソロンドール』's).
"""
import json
import lzma
from pathlib import Path
import sys
import zlib

OUTPUT = Path(__file__).with_name("fixtures") / "mountain-guardian-landing-1110.json.xz"
TURNS = (5332164,)


def _members(data: bytes) -> bytes:
    decoded = b""
    while data:
        stream = zlib.decompressobj(31)
        decoded += stream.decompress(data)
        data = stream.unused_data
    return decoded


def extract(path: Path) -> list:
    lines = _members(path.read_bytes()).decode("utf-8", "surrogateescape").splitlines()
    return list(dict.fromkeys(
        line for line in lines
        if line.strip() and json.loads(line).get("turn") in TURNS and json.loads(line).get("type") == "player_turn"))


if __name__ == "__main__":
    rows = extract(Path(sys.argv[1]))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(rows))
