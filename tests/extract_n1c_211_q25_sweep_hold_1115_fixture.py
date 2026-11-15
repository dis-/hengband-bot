"""Freeze the n1-c life-211 Quest 25 sweep hold of 2026-11-15 09:25-09:36
(tests/test_n1c_211_q25_sweep_hold_1115_recorded.py).

Source: the viewing Magic-Eater n1-c life-211 (build bot-30aeba85b) on Quest 25 『幽霊屋敷』, the sweep
phase (PHASES index 8) holding on [5,2] from 09:25:23 until the supervisor stopped it at 09:36
(``n1-c.paused``).  Copied read-only from the viewing server to C:/hengband-backups/pdca/q25-sweep-hold-1115:

  state-0925.jsonl.gz            the boards of turns 4076000-4076300 (the sweep's detect-all at
                                 4076115, its result board 4076127, the holds after it)
  state-last20.jsonl.gz          the last 20 boards before the stop
  decisions-0924-0936.jsonl.gz   every decision row from 09:24
  q25-battle-0936.json           the battle record at the stop (phase 8, the detection's cells)

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/q25-sweep-hold-1115")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-211-q25-sweep-hold-1115.json.gz"


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _decision(row):
    return {"turn": int(row["turn"]), "reason": row["reason"], "key": row["key"],
            "cell": [row["position"]["y"], row["position"]["x"]], "messages": row.get("messages", [])}


def main():
    boards = [row for row in _rows(ROOT / "state-0925.jsonl.gz") if row.get("type") == "player_turn"]
    last = [row for row in _rows(ROOT / "state-last20.jsonl.gz") if row.get("type") == "player_turn"]
    decisions = [row for row in _rows(ROOT / "decisions-0924-0936.jsonl.gz") if "reason" in row]
    turns = {board["turn"] for board in boards} | {board["turn"] for board in last}
    fixture = {
        "boards": boards,
        "last": last,
        "decisions": [_decision(row) for row in decisions if int(row["turn"]) in turns],
        "after_detection": [[int(row["turn"]), row["reason"], row["key"],
                             [row["position"]["y"], row["position"]["x"]]]
                            for row in decisions if int(row["turn"]) >= 4076127],
        "stop_record": json.loads((ROOT / "q25-battle-0936.json").read_text(encoding="utf-8")),
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(last), len(fixture["decisions"]), len(fixture["after_detection"]))


if __name__ == "__main__":
    main()
