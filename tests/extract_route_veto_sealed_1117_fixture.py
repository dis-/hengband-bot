"""Freeze the n1-c life-216 62F livelock of 2026-11-17 (tests/test_route_veto_sealed_1117_recorded.py).

Source: the viewing Magic-Eater n1-c life-216 (Lv 47), Angband 62F (floor (1, 62, 0)).  The town's
Recall landed it at (3,29) at 04:19:21 in a dark room five cells from a sleeping 百足龍虫 (race
1257) in the corridor below; ``search`` / ``seek-secret-wall`` / ``stuck:wander`` walked the room's
top row until ``livelock:recall-escape`` read Recall at 04:19:25 (HP 934/934).  Copied read-only
from the viewing server to C:/hengband-backups/pdca/captures/n1c-216-route-veto-1117:

  snapshots-62f-arrival.jsonl.gz      the snapshot rows of turns 3897141-3897429 (jsonlog/snapshots)
  bot-decisions-0418-0420.jsonl.gz    the decision rows of 04:18-04:20 (jsonlog/bot-decisions.jsonl.1)

The fixture keeps the player-turn boards from the landing to the first board the explore found
nothing on (turns 3897141-3897167) and the compact decision rows of the floor visit (the landing
to the Recall's wait).  Only this extraction tool reads the copies; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-216-route-veto-1117")
OUTPUT = Path(__file__).with_name("fixtures") / "route-veto-sealed-20261117.json.gz"
FIRST, LAST_BOARD, LAST_DECISION = 3897141, 3897167, 3897423


def main():
    boards, seen = [], set()
    with gzip.open(ROOT / "snapshots-62f-arrival.jsonl.gz", "rt", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            if (row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST_BOARD
                    and row["turn"] not in seen):
                seen.add(row["turn"])
                boards.append(row)
    decisions = []
    with gzip.open(ROOT / "bot-decisions-0418-0420.jsonl.gz", "rt", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            if FIRST <= row.get("turn", 0) <= LAST_DECISION:
                decisions.append({"turn": row["turn"], "reason": row["reason"], "key": row["key"],
                                  "position": row.get("position"), "floor": row.get("floor"),
                                  "hp": row["player"]["hp"]})
    fixture = {
        "source": "n1-c life-216 snapshots and decision rows (copied from the viewing server)",
        "boards": boards,
        "decisions": decisions,
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(decisions))


if __name__ == "__main__":
    main()
