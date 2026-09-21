"""Extract the minimal choke-hold incident sequence from the live JSONL log."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = Path("jsonlog/bot-state-fixed.jsonl")
OUTPUT = Path("tests/fixtures/choke-hold-lower-bound-20260921.jsonl")
TURNS = {4324256, 4324267, 4324273, 4324277}


rows = []
with SOURCE.open(encoding="utf-8") as stream:
    for line in stream:
        row = json.loads(line)
        if row.get("turn") in TURNS:
            rows.append(row)

if {row["turn"] for row in rows} != TURNS:
    raise SystemExit("not all requested incident turns were found")
OUTPUT.write_text(
    "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows),
    encoding="utf-8",
)
