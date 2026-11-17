"""Freeze the n1-c life-216 80F approach loop of 2026-11-17 (tests/test_approach_subject_1117_recorded.py).

Source: the viewing Magic-Eater n1-c life-216 (Lv 50), Angband 80F (floor (1, 80, 0)), stopped with
``loop-detected`` at 08:47:28: ``sensed-t1:approach-destruction`` stepped '1', '7', '3', '9' round
(36,79)-(37,78)-(36,77)-(37,78).  Copied read-only from the viewing server
(captures/20261117-084728-loop-detected) to
C:/hengband-backups/pdca/captures/n1c-216-approach-loop-1117:

  state.jsonl.gz            the player-turn boards of turns 4551838-4552140
  bot-decisions.jsonl.gz    their decision rows

The fixture keeps the player-turn boards up to turn 4552007 (the round's first four steps) and the
compact decision rows of the capture.  Only this extraction tool reads the copies; the committed
test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-216-approach-loop-1117")
OUTPUT = Path(__file__).with_name("fixtures") / "approach-subject-20261117.json.gz"
LAST_BOARD = 4552007


def main():
    with gzip.open(ROOT / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, stream)
                  if row.get("type") == "player_turn" and row["turn"] <= LAST_BOARD]
    with gzip.open(ROOT / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        decisions = [{"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                      "position": row.get("position")} for row in map(json.loads, stream)]
    fixture = {"source": "n1-c life-216 captures/20261117-084728-loop-detected",
               "boards": boards, "decisions": decisions}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
