"""Freeze the n1-c life-220 Quest 25 failed Speed cast of 2026-11-22 (tests/test_n1c_220_q25_speed_retry_1122_recorded.py).

Source: the viewing Magic-Eater n1-c life-220 (Lv36, Zombie, build bot-57ba99c2c) on Quest 25 『幽霊屋敷』
(floor (0, 48, 25)), copied read-only from the viewing server to
C:/hengband-backups/pdca/n1c-220-q25-fail:

  q25-snapshots.jsonl   the player_turn boards of the quest floor (turns 2078906-2084691)
  q25-decisions.jsonl   bot-decisions.jsonl's rows of the same floor (decisions 1771-2247)

The fixture keeps the boards of decision 2071 (the absorbed Speed cast that failed), 2072 (its failure
message), 2196 and 2220 (phase 2 on [7,1], walked on unhasted), 2205 and 2206 (the summons fight with
a 3-turn operational damage of 513), and the decision rows of the same turns (sequence, turn, reason, key,
the recorded 3-turn prediction and HP).  The last board of a turn is the decided one (the periodic
magic-eater lists of 2193-2195 and 2217-2219 share the turn).

Only this extraction tool reads the copies; the committed test reads the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/n1c-220-q25-fail")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-220-q25-speed-retry-1122.json.gz"
SEQUENCES = (2071, 2072, 2196, 2205, 2206, 2220)


def _rows(name):
    with open(SOURCE / name, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    decisions = {row["decision_sequence"]: row for row in _rows("q25-decisions.jsonl")}
    turns = {decisions[sequence]["turn"] for sequence in SEQUENCES}
    boards = {}
    for board in _rows("q25-snapshots.jsonl"):
        if board["turn"] in turns:
            boards[board["turn"]] = board   # the last board of the turn
    kept = []
    for sequence in SEQUENCES:
        row = decisions[sequence]
        prediction = row["threat_prediction"]
        kept.append({"decision_sequence": sequence, "turn": row["turn"], "reason": row["reason"],
                     "key": row["key"], "hp": row["player"]["hp"],
                     "operational_total": prediction["operational_total"]})
    fixture = {"source": "n1-c life-220 Q25 snapshots and decisions 2071-2220 "
                         "(copied from the viewing server)",
               "boards": [boards[turn] for turn in sorted(boards)], "decisions": kept}
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, sort_keys=True)
    print(OUTPUT.name, len(boards), len(kept))


if __name__ == "__main__":
    main()
