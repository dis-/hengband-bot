"""Extract the *Destruction* boards of n1-c life-140 (2026-11-05, random quest 40).

Input: the capture archive's snapshots-current.jsonl.gz (a multi-member gzip file).
Output: the state rows of the use (turn 3969877), of the flash board after it, and of the
following decisions in the pocket (the recorded searches and rests).
"""
import json
import lzma
from pathlib import Path
import sys
import zlib

OUTPUT = Path(__file__).with_name("fixtures") / "area-mapping-1105.json.xz"
TURNS = (3969877, 3969879, 3969886, 3969891, 3970066, 3970272)


def _members(data: bytes) -> bytes:
    decoded = b""
    start = data.find(b"\x1f\x8b")
    while start >= 0 and start < len(data):
        stream = zlib.decompressobj(31)
        decoded += stream.decompress(data[start:])
        if not stream.unused_data:
            break
        start = len(data) - len(stream.unused_data)
    return decoded


def extract(path: Path) -> list:
    lines = _members(path.read_bytes()).decode("utf-8", "surrogateescape").splitlines()
    # The archive's members overlap: each row once.
    return list(dict.fromkeys(line for line in lines if line.strip() and json.loads(line).get("turn") in TURNS))


if __name__ == "__main__":
    rows = extract(Path(sys.argv[1]))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_bytes(lzma.compress(payload.encode("utf-8", "surrogateescape")))
    print(OUTPUT, OUTPUT.stat().st_size, len(rows))
