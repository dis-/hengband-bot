"""Freeze the n1-c life-217 80F approach / seek-loot loop of 2026-11-19
(tests/test_n1c_217_approach_loot_1119_recorded.py).

Source: the viewing Magic-Eater n1-c life-217 (Lv 42), Angband 80F (floor (1, 80, 0)), stopped with
``loop-detected`` at 12:40:28 (build bot-23df91ff8): ``sensed-t1:approach-destruction`` '1'
(13,37)->(14,36) and ``seek-loot`` '9' back, about 20 times.  Copied read-only from the viewing
server (captures/20261119-124029-loop-detected) to
C:/hengband-backups/pdca/captures/n1c-217-approach-loot-1119:

  state.jsonl.gz            the player-turn boards of turns 4546126-4546192 (Recall running)
  bot-decisions.jsonl.gz    their decision rows

The fixture keeps the player-turn boards up to turn 4546136 (two rounds of the alternation) and
the compact decision rows of the floor (from turn 4545971).  Only this extraction tool reads the
copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-217-approach-loot-1119")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-217-approach-loot-20261119.json.gz"
LAST_BOARD = 4546136
FIRST_DECISION = 4545971


def main():
    with gzip.open(ROOT / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, stream)
                  if row.get("type") == "player_turn" and row["turn"] <= LAST_BOARD]
    with gzip.open(ROOT / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        decisions = [{"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                      "position": row.get("position"),
                      "recalling": (row.get("player") or {}).get("recalling"),
                      "loot_target": (row.get("loot") or {}).get("target")}
                     for row in map(json.loads, stream) if row["turn"] >= FIRST_DECISION]
    fixture = {"source": "n1-c life-217 captures/20261119-124029-loop-detected",
               "boards": boards, "decisions": decisions}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
