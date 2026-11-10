"""Freeze the boards of n1-a life-506's death (2026-11-10 07:59, 鉄獄38階, random quest 45).

Source, read-only, the analysis folder C:/hengband-backups/pdca/captures/n1a-506-death-1110
(REPORT.txt):

  20261110-075950-exit-no-marker/state.jsonl.gz          the player_turn boards of the 38F visit
                                                         (turns 2623781-2624228)
  20261110-075950-exit-no-marker/bot-decisions.jsonl.gz  the live decision rows of the same turns
                                                         (decisions 4044-4105)

One board per decision row: the last board of the row's game turn, its messages replaced by the
row's messages (the live process merges the messages of a board it did not decide on into the
next decision).  The rows keep sequence, turn, reason, key and the recorded threat_tiers' tier /
instant_death.  Only this tool reads the copies; the tests read the fixture.

    python tests/extract_scroll_lock_1110_fixture.py <capture directory>
"""

from __future__ import annotations

import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "scroll-lock-n1a-506-1110.json.xz"
STOP = "20261110-075950-exit-no-marker"
ARRIVAL = 2623781  # decision 4044: descended to 38F


def main() -> None:
    capture = Path(sys.argv[1]) / STOP
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, stream) if row.get("type") == "player_turn"]
    with gzip.open(capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    decided, decisions = [], []
    for row in rows:
        if row["turn"] < ARRIVAL:
            continue
        board = [raw for raw in boards if raw["turn"] == row["turn"]][-1]
        decided.append(dict(board, messages=row["messages"]))
        tiers = row.get("threat_tiers") or {}
        decisions.append({
            "sequence": row["decision_sequence"], "turn": row["turn"], "reason": row["reason"],
            "key": row["key"], "tier": tiers.get("tier"),
            "instant_death": tiers.get("instant_death"),
        })
    FIXTURE.write_bytes(lzma.compress(
        json.dumps({"boards": decided, "decisions": decisions}, ensure_ascii=False).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
