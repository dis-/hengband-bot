"""Cut the supply-ledger observer-memo fixture from two recorded captures.

Sources (copies of the live jsonlog captures, never modified):
  autorecover-20261003-031558-town-blocked-owner-retired.bot-state-fixed.jsonl.gz
  autorecover-20261003-051503-loop-detected.bot-state-fixed.jsonl.gz

Writes tests/fixtures/supply-ledger-memo-20261003.jsonl.gz: one JSON object
per line, {"segment": "town"|"dungeon", "board": <recorded board>}, and prints
the LF-normalized sha256 for FIXTURE_SHA256.

Run: PYTHONPATH=src;tests;scripts python tests/extract_supply_ledger_memo_fixture.py <capture dir>
"""
import gzip
import hashlib
import json
import sys
from pathlib import Path

TOWN = "autorecover-20261003-031558-town-blocked-owner-retired.bot-state-fixed.jsonl.gz"
DUNGEON = "autorecover-20261003-051503-loop-detected.bot-state-fixed.jsonl.gz"
TOWN_LINES = range(0, 8)  # walking plus three store pages
DUNGEON_LINES = range(0, 4)
OUT = Path(__file__).parent / "fixtures" / "supply-ledger-memo-20261003.jsonl.gz"


def main() -> None:
    source = Path(sys.argv[1])
    rows = []
    for segment, name, wanted in (
        ("town", TOWN, TOWN_LINES),
        ("dungeon", DUNGEON, DUNGEON_LINES),
    ):
        with gzip.open(source / name, "rt", encoding="utf-8") as file:
            boards = [json.loads(line) for line in file]
        rows.extend({"segment": segment, "board": boards[index]} for index in wanted)
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    ).encode("utf-8")
    OUT.write_bytes(gzip.compress(payload, mtime=0))
    print(OUT.name, len(rows), hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    main()
