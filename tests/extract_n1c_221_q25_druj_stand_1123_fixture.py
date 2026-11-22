"""Freeze the n1-c life-221 Quest 25 stairway and druj of 2026-11-23 (tests/test_n1c_221_q25_druj_stand_1123_recorded.py).

Source: the viewing Magic-Eater n1-c life-221 (Lv39) on Quest 25 『幽霊屋敷』 (floor (0, 48, 25)),
2026-11-23 04:59:27-05:03:52.  Copied read-only from the viewing server to
C:/hengband-backups/pdca/n1c-221-q25-1123:

  n1c221-boards.jsonl.gz      jsonlog/snapshots/snapshots-current.jsonl.gz, the player_turn boards of
                              the turns the test names (the stairway door 3191505-3191524, the walk to
                              a sight 3201809-3202271, the druj 3207164-3207646)
  n1c221-decisions.jsonl.gz   jsonlog/bot-decisions.jsonl, every Quest 25 decision (turn, sequence,
                              reason, key, position, messages)

The battle record of those turns was not kept (q25-battle.json holds only the town's at the end).
Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/n1c-221-q25-1123")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-221-q25-druj-stand-1123.json.gz"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    boards = {}
    for row in _rows(ROOT / "n1c221-boards.jsonl.gz"):
        if row.get("type") == "player_turn":
            boards.setdefault(int(row["turn"]), row)
    decisions = _rows(ROOT / "n1c221-decisions.jsonl.gz")
    fixture = {"source": "n1-c life-221 Quest 25, 2026-11-23 04:59-05:03 (copied from the viewing server)",
               "boards": [boards[turn] for turn in sorted(boards)], "decisions": decisions}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
