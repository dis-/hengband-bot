"""Freeze the boards of n1-a life-530's death (2026-11-18 12:50, 古城 51F).

Source, copied read-only from the viewing server to C:/hengband-backups/pdca/n1a-530-death-1118/:

  cap/n1a530_tail_snap.jsonl.gz   the raw boards of the life's jsonlog/snapshots/snapshots-current
                                  from game turn 13142000 on (the capture's own copy is cut by
                                  its size cap)
  dec.jsonl                       the live decision rows of the same window

The window is the floor's whole stay (the arrival's Recall read, turn 13142081, to the death at
13142245).  One board per decision row: the last player_turn board of the row's game turn, its
messages replaced by the row's messages (the live process merges the messages of a board it did
not decide on into the next decision).  The rows keep sequence, turn, reason and key.  Only this
tool reads the copies; the tests read the fixture.

    python tests/extract_n1a_530_flee_haste_1118_fixture.py
"""

from __future__ import annotations

import gzip
import json
import lzma
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/n1a-530-death-1118")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-flee-haste-1118.json.xz"
FLOOR_ARRIVAL = 13142081


def main() -> None:
    with gzip.open(SOURCE / "cap" / "n1a530_tail_snap.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [json.loads(line) for line in stream]
    boards = [raw for raw in boards
              if raw["turn"] >= FLOOR_ARRIVAL and raw["type"] == "player_turn"]
    with open(SOURCE / "dec.jsonl", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    decided, decisions = [], []
    for row in rows:
        if row["turn"] < FLOOR_ARRIVAL:
            continue
        board = [raw for raw in boards if raw["turn"] == row["turn"]][-1]
        decided.append(dict(board, messages=row["messages"]))
        decisions.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                          "reason": row["reason"], "key": row["key"]})
    FIXTURE.write_bytes(lzma.compress(
        json.dumps({"boards": decided, "decisions": decisions}, ensure_ascii=False)
        .encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
