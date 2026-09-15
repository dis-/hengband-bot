"""Freeze the live restore-weapon incident boards with deterministic gzip."""

import gzip
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jsonlog" / "bot-state-fixed.jsonl"
TARGET = ROOT / "tests" / "fixtures" / "restore-weapon-stale-takeoff.jsonl.gz"
SOURCE_LINES = range(6329, 6334)  # physical lines 6330-6334, one-based


def main() -> None:
    selected = []
    with SOURCE.open("rb") as stream:
        for index, line in enumerate(stream):
            if index in SOURCE_LINES:
                selected.append(line)
    if len(selected) != len(SOURCE_LINES):
        raise AssertionError(f"expected {len(SOURCE_LINES)} rows, got {len(selected)}")
    with TARGET.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            zipped.writelines(selected)


if __name__ == "__main__":
    main()
