"""Freeze the 2026-09-16 Alchemist alternation window byte-for-byte."""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jsonlog" / "bot-state-fixed.jsonl"
TARGET = (
    ROOT / "tests" / "fixtures" /
    "alchemist-observed-shop-alternation-20260916.jsonl.gz"
)
FIRST_TURN = 3_024_656
LAST_TURN = 3_024_766


def main() -> None:
    selected: list[bytes] = []
    with SOURCE.open("rb") as stream:
        for line in stream:
            record = json.loads(line)
            turn = int(record.get("turn", -1))
            if FIRST_TURN <= turn <= LAST_TURN:
                selected.append(line)
    turns = [json.loads(line)["turn"] for line in selected]
    if len(selected) != 17 or turns[0] != FIRST_TURN or turns[-1] != LAST_TURN:
        raise AssertionError(f"recorded alternation window changed: {turns!r}")
    with TARGET.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            zipped.writelines(selected)
    with gzip.open(TARGET, "rb") as zipped:
        if zipped.read() != b"".join(selected):
            raise AssertionError("gzip fixture is not byte-faithful")
    print(f"wrote {len(selected)} records to {TARGET}")


if __name__ == "__main__":
    main()
