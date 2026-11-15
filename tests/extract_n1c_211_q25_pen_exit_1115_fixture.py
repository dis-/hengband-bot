"""Freeze the n1-c life-211 Quest 25 exit loop of 2026-11-15 14:01 (tests/test_n1c_211_q25_pen_exit_1115_recorded.py).

Source: the viewing Magic-Eater n1-c life-211 (build bot-138f619e1) on Quest 25 『幽霊屋敷』: a Nexus
quylthulg teleported the player into the Ipsissimus' pen [7,17], the quylthulg died and the quest was
won (turn 4077532); the exit walk held '5' (``quest:blocked:exit``) on [9,17] until the loop guard
stopped the bot three times (14:01:36, 14:01:43, 14:01:50) and the runner replaced the character.
Copied read-only from the viewing server to C:/hengband-backups/pdca/q25-sealed-loop-1115:

  captures/20261115-140136-loop-detected   the first stop (state rows 4076968-4077881, decisions)
  captures/20261115-140143-loop-detected   the second
  captures/20261115-140150-loop-detected   the third (the escalation)
  q25-battle-1401.json                     the battle record left (phase 11, every phase over)

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/q25-sealed-loop-1115")
CAPTURES = ("20261115-140136-loop-detected", "20261115-140143-loop-detected", "20261115-140150-loop-detected")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-211-q25-pen-exit-1115.json.gz"
FIRST, LAST = 4077522, 4077572     # the step before the teleport to the first holds


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def main():
    first = ROOT / "captures" / CAPTURES[0]
    boards = [row for row in _rows(first / "state.jsonl.gz")
              if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST]
    stops = {}
    for name in CAPTURES:
        decisions = [row for row in _rows(ROOT / "captures" / name / "bot-decisions.jsonl.gz") if "reason" in row]
        stops[name] = [[int(row["turn"]), row["reason"], row["key"], [row["position"]["y"], row["position"]["x"]]]
                       for row in decisions if row["time"] >= "2026-11-15T14:01:29"]
    fixture = {"boards": boards, "stops": stops,
               "battle_record": json.loads((ROOT / "q25-battle-1401.json").read_text(encoding="utf-8"))}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), {name: len(rows) for name, rows in stops.items()})


if __name__ == "__main__":
    main()
