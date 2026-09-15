"""Extract the frozen 2026-09-15 unaffordable-supplies town window."""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jsonlog" / "bot-state-fixed.jsonl"
TARGET = ROOT / "tests" / "fixtures" / "town-unaffordable-supplies-20260915.jsonl.gz"
TURNS = {2_902_792, 2_911_088, 2_911_096, 2_911_106, 2_911_111}


def main() -> None:
    rows: list[str] = []
    with SOURCE.open("rt", encoding="utf-8-sig", newline="") as stream:
        for line in stream:
            record = json.loads(line)
            turn = int(record.get("turn", -1))
            if turn in TURNS and (
                turn != 2_902_792 or record.get("type") == "knowledge"
            ):
                rows.append(line.rstrip("\r\n"))
    expected = [
        ("knowledge", 2_902_792),
        ("player_turn", 2_911_088),
        ("player_turn", 2_911_096),
        ("player_turn", 2_911_096),
        ("player_turn", 2_911_106),
        ("player_turn", 2_911_106),
        ("store", 2_911_106),
        ("player_turn", 2_911_111),
    ]
    if [(json.loads(row).get("type"), json.loads(row)["turn"]) for row in rows] != expected:
        raise AssertionError("recorded unaffordable-supplies window changed")
    with TARGET.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(("\n".join(rows) + "\n").encode("utf-8"))
    print(f"wrote {len(rows)} records to {TARGET}")


if __name__ == "__main__":
    main()
