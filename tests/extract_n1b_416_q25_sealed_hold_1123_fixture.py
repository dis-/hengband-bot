"""Freeze the n1-b life-416 Quest 25 sealed-pocket hold of 2026-11-23 (tests/test_n1b_416_q25_sealed_hold_1123_recorded.py).

Source: the viewing Magic-Eater n1-b life-416 (Lv39) on Quest 25 『幽霊屋敷』 (floor (0, 48, 25)), the
plan's sweep (battle phase 8) holding on [8,21] from turn 2507392 until the server's
``stall:floor-dwell:quest-strategy:hold`` (2026-11-23 01:19:27, turn 2598087).  Copied read-only
from the viewing server to C:/hengband-backups/pdca/n1b-416-q25-1123:

  window-snapshots.jsonl.gz   jsonlog/snapshots/snapshots-20261123-005708-cc7974.jsonl.gz turns
                              2507060-2507600 (the sweep's walk, the second-to-last quylthulg's
                              kill, the detection that showed the last one on [8,3], the hold) and
                              snapshots-current.jsonl.gz from turn 2597900 (the stop)
  window-decisions.jsonl.gz   jsonlog/bot-decisions.jsonl{,.2}, the same turns (turn, reason, key)
  q25-battle.json             jsonlog/q25-battle.json at the stop (phase 8, detected [8,3])

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/n1b-416-q25-1123")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-416-q25-sealed-hold-1123.json.gz"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    boards = [row for row in _rows(ROOT / "window-snapshots.jsonl.gz") if row.get("type") == "player_turn"]
    decisions = [{"turn": int(row["turn"]), "reason": row["reason"], "key": row["key"]}
                 for row in _rows(ROOT / "window-decisions.jsonl.gz")]
    fixture = {
        "window": {"source": "n1-b life-416 snapshots turns 2507060-2507600 and 2597900-2598087 "
                             "(copied from the viewing server)",
                   "boards": boards, "decisions": decisions},
        "battle_record": json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
