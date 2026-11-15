"""Freeze the boards of n1-a life-525's death (2026-11-15 21:05, ガラスの城 49F).

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1a-525-death-1115/20261115-210559-player-death:

  snapshots/snapshots-current.jsonl.gz   the raw boards of the life's last generation
  decision-tail.jsonl                    the live decision rows of the same window

The window is the floor's whole stay (arrival turn 12040635 to the death at 12041369).  One
board per decision row: the last player_turn board of the row's game turn, its messages
replaced by the row's messages (the live process merges the messages of a board it did not
decide on into the next decision).  The rows keep sequence, turn, reason, key and the recorded
threat_tiers' tier / instant_death.  Only this tool reads the copies; the tests read the fixture.

    python tests/extract_n1a_525_flee_haste_1115_fixture.py
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/captures/n1a-525-death-1115/"
              "20261115-210559-player-death")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-flee-haste-1115.json.xz"
FLOOR_ARRIVAL = 12040635


def main() -> None:
    with gzip.open(SOURCE / "snapshots" / "snapshots-current.jsonl.gz", "rt",
                   encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream]
    boards = [raw for raw in boards
              if raw["turn"] >= FLOOR_ARRIVAL and raw["type"] == "player_turn"]
    rows = []
    with open(SOURCE / "decision-tail.jsonl", encoding="utf-8") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # the tail's first line is cut by the size cap
    decided, decisions = [], []
    for row in rows:
        if row["turn"] < FLOOR_ARRIVAL:
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
        json.dumps({"boards": decided, "decisions": decisions}, ensure_ascii=False)
        .encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
