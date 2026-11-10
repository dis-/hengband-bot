"""Extract the Anaguma (穴熊) recorded boards (tests/test_anaguma_recorded.py).

Usage::

    python tests/extract_anaguma_fixture.py <capture snapshots .jsonl.gz> <first turn> <count> <out name>

The capture's snapshot files are often a copied tail of a gzip stream (the
first member cut), so the members are decoded one by one from the first gzip
header (zlib.decompressobj(31) chained on unused_data).  The rows from the one
whose ``turn`` is ``first turn`` (and the three before it, which prime the
policy) are written verbatim, one JSON line each, to tests/fixtures/<out name>
(gzip), and the SHA-256 of the uncompressed text is printed for the pin.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import zlib
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PRIME = 3


def members(path: Path):
    data = path.read_bytes()
    start = data.find(b"\x1f\x8b\x08")
    buffer = data[start:] if start >= 0 else b""
    while buffer:
        decoder = zlib.decompressobj(31)
        try:
            yield decoder.decompress(buffer)
        except zlib.error:
            return
        buffer = decoder.unused_data
        nxt = buffer.find(b"\x1f\x8b\x08")
        if nxt < 0:
            return
        buffer = buffer[nxt:]


def rows(path: Path) -> list[bytes]:
    found, rest = [], b""
    for chunk in members(path):
        lines = (rest + chunk).split(b"\n")
        rest = lines.pop()
        for line in lines:
            try:
                json.loads(line)
            except ValueError:
                continue
            found.append(line)
    return found


def main(argv) -> None:
    source, first, count, name = Path(argv[1]), int(argv[2]), int(argv[3]), argv[4]
    lines = rows(source)
    index = next(i for i, line in enumerate(lines) if json.loads(line).get("turn") == first)
    picked = lines[max(0, index - PRIME):index + count]
    text = b"\n".join(picked) + b"\n"
    (FIXTURES / name).write_bytes(gzip.compress(text, mtime=0))
    print(name, len(picked), hashlib.sha256(text).hexdigest())


if __name__ == "__main__":
    main(sys.argv)
