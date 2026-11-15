"""Freeze the n1-c life-211 Quest 25 empty detections of 2026-11-15 09:03-09:08
(tests/test_n1c_211_q25_absent_empty_1115_recorded.py).

Source: the viewing Magic-Eater n1-c life-211 (build bot-6e4387a44) on Quest 25 『幽霊屋敷』 after the
09:03 restart, stopped by the supervisor at 09:08 (``n1-c.paused``).  Copied read-only from the viewing
server to C:/hengband-backups/pdca/q25-absent-empty-1115:

  state-first120.jsonl.gz      the process's first 120 boards (the save's turn 4034788 on [11,19])
  decisions-0903-0908.jsonl.gz  every decision row of the process (2,489; 51 empty Detect Evil casts)
  q25-battle-0908.json          the battle record at the stop (phase 0, quiet 2376, nothing absent)

The battle the process restored at 09:03 is the 06:53 record the earlier fixture holds
(tests/fixtures/n1c-211-q25-absent-wait-1115.json.gz ``battle_record``: nothing ran in between).

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/q25-absent-empty-1115")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-211-q25-absent-empty-1115.json.gz"
BOARDS = 12                    # the save's boards and the first walk after the first cast
CAST_REASON = "me-power:quest25-presence:detect-evil"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def main():
    boards = [row for row in _rows(ROOT / "state-first120.jsonl.gz") if row.get("type") == "player_turn"]
    decisions = [row for row in _rows(ROOT / "decisions-0903-0908.jsonl.gz") if "reason" in row]
    first = boards[:BOARDS]
    turns = {board["turn"] for board in first}
    cut = [{"turn": int(row["turn"]), "sequence": row.get("decision_sequence"), "reason": row["reason"],
            "key": row["key"], "cell": [row["position"]["y"], row["position"]["x"]],
            "messages": row.get("messages", [])}
           for row in decisions if int(row["turn"]) in turns]
    casts = [{"turn": int(row["turn"]), "cell": [row["position"]["y"], row["position"]["x"]],
              "key": row["key"], "messages": row.get("messages", [])}
             for row in decisions if row["reason"] == CAST_REASON]
    after = [{"turn": int(row["turn"]), "cell": [row["position"]["y"], row["position"]["x"]],
              "messages": row.get("messages", [])}
             for previous, row in zip(decisions, decisions[1:]) if previous["reason"] == CAST_REASON]
    fixture = {
        "boards": first,
        "decisions": cut,
        "casts": casts,
        "after_casts": after,
        "stop_record": json.loads((ROOT / "q25-battle-0908.json").read_text(encoding="utf-8")),
        "counts": {"decisions": len(decisions)},
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(first), len(cut), len(casts), len(after))


if __name__ == "__main__":
    main()
