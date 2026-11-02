"""Freeze the n1-a life-464 dark cave sweep boards of 2026-11-02.

Source: the viewing warrior n1-a life-464 (Lv41, 922 max HP, build
bot-ec1f68398), オークの洞窟 23階 (the dungeon's maxDepth), stopped at 19:18:34
with ``stall:floor-dwell:explore``.  Copied read-only to
C:/hengband-backups/pdca/captures/hourly-1900-1102/<stamp>/:

  state.jsonl.gz          the last 53 boards before the stop (turns
                          5161652-5162085, light radius 3, no hostile)
  bot-decisions.jsonl.gz  the decision rows of the same window

The fixture keeps the boards as recorded lines and the compact decision rows
(turn, reason, key, the explore claim's goal cell).  Only this extraction tool
reads the captures; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


CAPTURE = Path(
    "C:/hengband-backups/pdca/captures/hourly-1900-1102/"
    "20261102-191834-stall-floor-dwell-explore"
)
OUTPUT = Path(__file__).with_name("fixtures") / "explore-lit-floor-sweep-20261102.json.gz"


def main():
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [line.rstrip("\n") for line in stream if line.strip()]
    turns = {json.loads(line)["turn"] for line in boards}
    decisions = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["turn"] not in turns:
                continue
            claim = row.get("claim") or {}
            goal = claim.get("goal") or {}
            decisions.append({
                "turn": row["turn"],
                "reason": row["reason"],
                "key": row["key"],
                "owner": claim.get("owner"),
                "goal": goal.get("cell"),
            })
    fixture = {
        "source": f"{CAPTURE} (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(boards), len(decisions))


if __name__ == "__main__":
    main()
