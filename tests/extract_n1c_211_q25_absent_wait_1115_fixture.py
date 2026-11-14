"""Freeze the n1-c life-211 Quest 25 ambush wait of 2026-11-15 (tests/test_n1c_211_q25_absent_wait_1115_recorded.py).

Source: the viewing Magic-Eater n1-c life-211 (life-208 resumed at 05:57, Lv33, builds bot-85e92a221,
bot-46e949d2e, bot-3d81d8a78) on Quest 25 『幽霊屋敷』 (floor (0, 48, 25)), stopped by the owner at
06:53 (``n1-c.paused``).  Copied read-only from the viewing server to
C:/hengband-backups/pdca/q25-absent-wait-1115:

  state-last300.jsonl.gz      the last 300 boards of the 06:33 process (turns 41329xx-4136145,
                              every one on [10,1], quest-strategy:hold '5')
  decisions-last300.jsonl.gz  their decision rows
  state-first80.jsonl.gz      the first 80 boards of that process (the save's turn 4034788 on [11,19])
  q25-battle.json             the battle record at the stop (turn 4136145, phase 0)
  life208-decisions-3909700-3968400.jsonl.gz
                              life-208's decision rows from the ambush's kills to the shadow demons'
                              (the ambush's 4,995 holds, the tyrannosaurus burnt by the fire aura)

and from C:/hengband-backups/pdca/n1c-208-q25-1115/jsonlog/q25-battle.json, life-208's record at its
last decision (turn 4035146, phase 11).

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/q25-absent-wait-1115")
LIFE_208_RECORD = Path("C:/hengband-backups/pdca/n1c-208-q25-1115/jsonlog/q25-battle.json")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-211-q25-absent-wait-1115.json.gz"
HOLD_BOARDS = 12          # the last boards kept (the stop's board last)
RELOAD_BOARDS = 3         # the save's first boards kept
AMBUSH_FROM, AMBUSH_TO = 3909947, 3965767   # the skeletal tyrannosaur's kill to the first spectre's
AURA_FROM, AURA_TO = 3965880, 3965910       # the tyrannosaurus's last fight


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _decision(row):
    position = row.get("position") or {}
    return {"turn": int(row["turn"]), "reason": row["reason"], "key": row["key"],
            "cell": [position.get("y"), position.get("x")], "messages": row.get("messages", [])}


def main():
    boards = [row for row in _rows(ROOT / "state-last300.jsonl.gz") if row.get("type") == "player_turn"]
    hold = boards[-HOLD_BOARDS:]
    turns = {board["turn"] for board in boards}
    decisions = [_decision(row) for row in _rows(ROOT / "decisions-last300.jsonl.gz")
                 if row.get("turn") is not None and int(row["turn"]) in turns]
    first = [row for row in _rows(ROOT / "state-first80.jsonl.gz") if row.get("type") == "player_turn"]
    life208 = [row for row in _rows(ROOT / "life208-decisions-3909700-3968400.jsonl.gz")
               if row.get("turn") is not None]
    ambush = [[int(row["turn"]), row["reason"], row["key"]] for row in life208
              if AMBUSH_FROM < int(row["turn"]) < AMBUSH_TO]
    aura = [_decision(row) for row in life208 if AURA_FROM <= int(row["turn"]) <= AURA_TO]
    fixture = {
        "hold": {"boards": hold, "decisions": decisions},
        "reload": {"boards": first[:RELOAD_BOARDS]},
        "battle_record": json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")),
        "life208_record": json.loads(LIFE_208_RECORD.read_text(encoding="utf-8")),
        "life208_ambush": ambush,
        "life208_aura": aura,
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(hold), len(decisions), len(fixture["reload"]["boards"]), len(ambush), len(aura))


if __name__ == "__main__":
    main()
