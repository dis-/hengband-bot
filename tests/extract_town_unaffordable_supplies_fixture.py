"""Extract the frozen 2026-09-15 unaffordable-supplies town window."""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jsonlog" / "bot-state-fixed.jsonl"
TARGET = ROOT / "tests" / "fixtures" / "town-unaffordable-supplies-20260915.jsonl.gz"
RESTART_TARGET = (
    ROOT / "tests" / "fixtures"
    / "town-unaffordable-supplies-restart-20260915.jsonl.gz"
)
TURNS = {
    2_902_792, 2_911_088, 2_911_096, 2_911_106, 2_911_111,
    2_911_293, 2_911_306,
}


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
        ("player_turn", 2_911_293),
        ("player_turn", 2_911_293),
        ("store", 2_911_293),
        ("player_turn", 2_911_306),
    ]
    if [(json.loads(row).get("type"), json.loads(row)["turn"]) for row in rows] != expected:
        raise AssertionError("recorded unaffordable-supplies window changed")
    with TARGET.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(("\n".join(rows) + "\n").encode("utf-8"))
    print(f"wrote {len(rows)} records to {TARGET}")

    restart_rows: list[str] = []
    with SOURCE.open("rt", encoding="utf-8-sig", newline="") as stream:
        for line_number, line in enumerate(stream, 1):
            if 4681 <= line_number <= 4687:
                restart_rows.append(line.rstrip("\r\n"))
    restart_expected = [
        ("player_turn", 2_911_458),
        ("knowledge", 2_911_458),
        ("player_turn", 2_911_458),
        ("player_turn", 2_911_458),
        ("player_turn", 2_911_809),
        ("store", 2_911_809),
        ("player_turn", 2_911_820),
    ]
    if [
        (json.loads(row).get("type"), json.loads(row)["turn"])
        for row in restart_rows
    ] != restart_expected:
        raise AssertionError("recorded restart poverty window changed")
    with RESTART_TARGET.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(("\n".join(restart_rows) + "\n").encode("utf-8"))
    print(f"wrote {len(restart_rows)} records to {RESTART_TARGET}")


if __name__ == "__main__":
    main()
