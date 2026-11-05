"""Freeze the n1-b life-323 corridor boards of 2026-11-06 (Orc cave 23F).

Source: the viewing Magic-Eater n1-b life-323 (Lv34, 504 HP, build
bot-038a35897), Orc cave 23F (not a quest floor), 07:18-07:22: ``explore``
stepped (22,92)/(23,92) and (21,94)/(22,94) back and forth between searches and
breakouts.  Copied read-only to
C:/hengband-backups/pdca/captures/n1b-323-osc-1106/:

  floor-snapshots.jsonl.gz  the floor's boards (turns 2853841-2862830)
  floor-decisions.jsonl.gz  the floor's decision rows

The fixture keeps the boards of turns 2861370-2861436 as recorded lines (the
warm-up after the pickup at (23,95), then the live alternation) and the compact
decision rows of the same turns.  Only this tool reads the captures; the test
reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-323-osc-1106")
OUTPUT = Path(__file__).with_name("fixtures") / "explore-frontier-kind-20261106.json.gz"
FIRST, LAST = 2861370, 2861436


def main():
    boards = []
    with gzip.open(CAPTURE / "floor-snapshots.jsonl.gz", "rt", encoding="utf-8",
                   errors="surrogateescape") as stream:
        for line in stream:
            if line.strip() and FIRST <= json.loads(line)["turn"] <= LAST:
                boards.append(line.rstrip("\n"))
    turns = {json.loads(line)["turn"] for line in boards}
    decisions = []
    with gzip.open(CAPTURE / "floor-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["turn"] in turns:
                decisions.append({
                    "turn": row["turn"],
                    "reason": row["reason"],
                    "key": row["key"],
                    "position": [row["position"]["y"], row["position"]["x"]],
                })
    fixture = {
        "source": f"{CAPTURE} (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", errors="surrogateescape",
                   newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main()
