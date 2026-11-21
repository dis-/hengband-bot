"""Freeze the n1-b life-413 Quest 25 patrol stop of 2026-11-22 (tests/test_n1b_413_q25_patrol_1122_recorded.py).

Source: the viewing Magic-Eater n1-b life-413 (Lv37, Zombie, build bot-28c801fdd) on Quest 25
『幽霊屋敷』 (floor (0, 48, 25)), every phase of the plan over (battle phase 11), the KILL_ALL patrol
owning the floor until ``quest:blocked:quest-patrol-rounds`` (2026-11-22 01:48:17, turn 2589517).
Copied read-only from the viewing server to C:/hengband-backups/pdca/n1b-413-q25-1122:

  window-snapshots.jsonl.gz   jsonlog/snapshots/snapshots-current.jsonl.gz, turns 2585590-2589517
                              (the patrol's whole life: the Druj killed, the Rod of Detection cast,
                              five rounds, the stop)
  window-decisions.jsonl.gz   jsonlog/bot-decisions.jsonl, the same turns
  q25-battle.json             jsonlog/q25-battle.json at the stop (kills, phase)

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/n1b-413-q25-1122")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-413-q25-patrol-1122.json.gz"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    boards = [row for row in _rows(ROOT / "window-snapshots.jsonl.gz") if row.get("type") == "player_turn"]
    turns = {board["turn"] for board in boards}
    decisions = [{"turn": int(row["turn"]), "reason": row["reason"], "key": row["key"]}
                 for row in _rows(ROOT / "window-decisions.jsonl.gz")
                 if row.get("turn") is not None and int(row["turn"]) in turns]
    fixture = {
        "window": {"source": "n1-b life-413 snapshots-current turns 2585590-2589517 (copied from the viewing server)",
                   "boards": boards, "decisions": decisions},
        "battle_record": json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
