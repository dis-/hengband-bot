"""Extract the *Destruction* pocket boards of n1-b life-367 (2026-11-10 20:54, Mountain 50F).

Input: snapshots-20261110-210702-165f14.jsonl.gz of the life's jsonlog/snapshots (a
multi-member gzip file; a slice of its lines also works).
Output: the state rows of the *Destruction* (decision 11842, turn 5332475), the flash board
(turn 5332483, decision 11843 map-area), the mapped board (turn 5332490, decision 11844
before-secret-search) and the stuck board (turn 5332907, decision 11905 stuck:recall-escape).
"""
import json
import lzma
from pathlib import Path
import sys
import zlib

OUTPUT = Path(__file__).with_name("fixtures") / "destroyed-pocket-1110.json.xz"
TURNS = (5332475, 5332483, 5332490, 5332907)


def _members(data: bytes) -> bytes:
    decoded = b""
    while data:
        stream = zlib.decompressobj(31)
        decoded += stream.decompress(data)
        data = stream.unused_data
    return decoded


def extract(path: Path) -> list:
    lines = _members(path.read_bytes()).decode("utf-8", "surrogateescape").splitlines()
    return list(dict.fromkeys(line for line in lines if line.strip() and json.loads(line).get("turn") in TURNS))


if __name__ == "__main__":
    rows = extract(Path(sys.argv[1]))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(rows))
