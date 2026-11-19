"""Extract tests/fixtures/n1c-217-store-full-1119/boards.jsonl.xz.

Source: n1-c life-217's stop of 2026-11-19 16:44:00 (no-key-exhausted, bot main 96e6938927),
the live capture's state.jsonl.gz (read-only copy): its last six boards (lines 15-20, turns
4835659-4835664): the Magic shop page the one-shot sale entered, the two refusal boards
(「すいませんが、店にはもう置く場所がありません。」, 「そのコマンドは店の中では使えません。」), the
outside boards after the exit and the re-entered page.

    python tests/extract_n1c_217_store_full_1119_fixture.py <capture directory>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-store-full-1119" / "boards.jsonl.xz"
FIRST, LAST = 15, 20


if __name__ == "__main__":
    lines = gzip.decompress((Path(sys.argv[1]) / "state.jsonl.gz").read_bytes()).splitlines(True)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_bytes(lzma.compress(b"".join(lines[FIRST:LAST + 1]), preset=9 | lzma.PRESET_EXTREME))
    print(FIXTURE, FIXTURE.stat().st_size)
