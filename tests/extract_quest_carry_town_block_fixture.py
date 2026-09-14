"""Extract the frozen 2026-09-15 quest-carry town-block replay window."""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jsonlog" / "bot-state-fixed.jsonl"
TARGET = ROOT / "tests" / "fixtures" / "quest-carry-town-block-20260915.jsonl.gz"
FIRST_TURN = 2_870_615
LAST_TURN = 2_873_626
RECORDED_ARRIVAL_TURNS = {2_864_676, 2_864_686}


def main() -> None:
    rows: list[str] = []
    with SOURCE.open("rt", encoding="utf-8-sig", newline="") as stream:
        for line in stream:
            record = json.loads(line)
            turn = int(record.get("turn", -1))
            if FIRST_TURN <= turn <= LAST_TURN or turn in RECORDED_ARRIVAL_TURNS:
                rows.append(line.rstrip("\r\n"))
    if not rows:
        raise AssertionError("recorded quest-carry town-block window is empty")
    with TARGET.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(("\n".join(rows) + "\n").encode("utf-8"))
    print(f"wrote {len(rows)} records to {TARGET}")


if __name__ == "__main__":
    main()
