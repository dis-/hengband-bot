"""Freeze the n1-b life-419 Quest 25 patrol stop of 2026-11-26 (tests/test_n1b_419_q25_patrol_1126_recorded.py).

Source: the viewing Magic-Eater n1-b life-419 (Lv40, Zombie, build bot-12d92ad85) on Quest 25
『幽霊屋敷』 (floor (0, 48, 25)), every phase of the plan over (battle phase 11), the KILL_ALL patrol
owning the floor until ``quest:blocked:quest-patrol-rounds`` (2026-11-26 05:01:32, turn 3663324).
Copied read-only from the viewing server's incident capture
(life-419/incident-captures/20261126-050132-quest-blocked-quest-patrol-rounds, and jsonlog/q25-battle.json)
to C:/hengband-backups/pdca/n1b-419-q25-1126:

  window-snapshots.jsonl.gz   snapshots/snapshots-current.jsonl.gz (turns up to the stop)
  window-decisions.jsonl.gz   decision-tail.jsonl, gzipped
  q25-battle.json             jsonlog/q25-battle.json at the stop (kills, phase)

Only this extraction tool reads the copies; the committed test reads the fixture.  The boards kept:
the patrol's first detection (the powered Rod of Detection cast on 3661154 and the board after it),
the walk boards up to 3661211, the second round's detection boards (3661456-3661473) and the stop.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/n1b-419-q25-1126")
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-419-q25-patrol-1126.json.gz"
WINDOWS = ((3661151, 3661211), (3661456, 3661473), (3663324, 3663324))


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        # The decision tail is cut at a byte cap: its first line is the end of a row.
        return [json.loads(line) for line in stream if line.startswith("{")]


def _kept(turn):
    return any(first <= turn <= last for first, last in WINDOWS)


def main():
    boards = [row for row in _rows(ROOT / "window-snapshots.jsonl.gz")
              if row.get("type") == "player_turn" and _kept(int(row["turn"]))]
    turns = {board["turn"] for board in boards}
    decisions = [{"turn": int(row["turn"]), "reason": row["reason"], "key": row["key"],
                  "position": row["position"]}
                 for row in _rows(ROOT / "window-decisions.jsonl.gz")
                 if row.get("turn") is not None and int(row["turn"]) in turns]
    fixture = {
        "window": {"source": "n1-b life-419 snapshots-current and decision-tail (incident capture "
                             "20261126-050132), turns " + ", ".join(f"{a}-{b}" for a, b in WINDOWS),
                   "boards": boards, "decisions": decisions},
        "battle_record": json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
