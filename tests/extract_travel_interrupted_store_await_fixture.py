"""Extract the frozen 2026-09-15 interrupted Home-travel window."""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jsonlog" / "bot-state-fixed.jsonl"
TARGET = (
    ROOT / "tests" / "fixtures" /
    "travel-interrupted-store-await-20260915.jsonl.gz"
)
TURNS = {2_898_514, 2_898_719}


def main() -> None:
    rows: list[str] = []
    with SOURCE.open("rt", encoding="utf-8-sig", newline="") as stream:
        for line in stream:
            record = json.loads(line)
            if int(record.get("turn", -1)) in TURNS:
                rows.append(line.rstrip("\r\n"))
    if [json.loads(row)["turn"] for row in rows] != [
        2_898_514, 2_898_514, 2_898_514, 2_898_719,
    ]:
        raise AssertionError("recorded interrupted-travel window changed")
    with TARGET.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(("\n".join(rows) + "\n").encode("utf-8"))
    print(f"wrote {len(rows)} records to {TARGET}")


if __name__ == "__main__":
    main()
