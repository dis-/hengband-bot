"""Freeze the 2026-11-02 n1-c life-102 Outpost board that recalled past Q14.

Source: read-only copies from the viewing zombie Magic-Eater n1-c (Lv11,
max HP 146 at the board, one Potion of Speed carried) in
C:/hengband-backups/pdca/captures/q14-lv8-1102/n1-c/life-102/
(server ~/hengbot-soak/n1-c/life-102/):

  snapshots-20261102-041827-23dbdf.jsonl.gz
                          jsonlog/snapshots/: the ring rotated at 04:18; it
                          holds the player_turn boards from turn 873773 on,
                          with the skill_exp row of turn 909296 and the Home
                          knowledge row of turn 875082.
  decisions-0413.jsonl    the jsonlog/bot-decisions.jsonl.3/.2 rows of turns
                          874000-927000 (04:04-04:18).

  policy-state-0427.json  incident-captures/20261102-042759-posting-contract-
                          recall-already-active/policy-state.json: the
                          nearest diagnostic checkpoint (after the board);
                          its ``_me_staff_sequence`` has every sequence staff
                          absorbed (the Morivant visit of 04:09).

Decision 1783 (turn 910377, 04:12:50, town errands done) read Word of Recall
to the dungeon: fixedquest_readiness quest 14 ``three-turn-threat``,
worst_adjacent 116 (four Wargs, three turns, hasted) >= max HP 146 x 0.50.

Only this extraction tool reads the copies; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_dungeon_1031_fixture import ring_rows, sha


LIFE = Path("C:/hengband-backups/pdca/captures/q14-lv8-1102/n1-c/life-102")
RING = LIFE / "snapshots-20261102-041827-23dbdf.jsonl.gz"
DECISIONS = LIFE / "decisions-0413.jsonl"
STATE = LIFE / "policy-state-0427.json"
OUTPUT = Path(__file__).with_name("fixtures") / "q14-lv8-1102.json.gz"
BOARD_TURN = 910377
DECISION = 1783
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "objective",
                   "fixedquest_readiness")


def main():
    rows = list(ring_rows(RING.read_bytes()))
    board = [row for row in rows
             if row.get("type") == "player_turn" and row["turn"] == BOARD_TURN][-1]
    knowledge = [row for row in rows
                 if row.get("type") == "knowledge" and row["turn"] <= BOARD_TURN]
    skill = [row for row in knowledge if row["knowledge"]["category"] == "skill_exp"][-1]
    home = [row for row in knowledge if row["knowledge"]["category"] == "home"][-1]
    decision = next(row for row in map(json.loads, DECISIONS.read_text(encoding="utf-8").splitlines())
                    if row["decision_sequence"] == DECISION and row["turn"] == BOARD_TURN)
    sequence = json.loads(STATE.read_text(encoding="utf-8"))["state"]["_me_staff_sequence"]
    case = dict(
        source="n1-c life-102 (2026-11-02 04:12:50, the Outpost after the visit of decisions 1764-1782)",
        sources={path.name: sha(path) for path in (RING, DECISIONS, STATE)},
        board=board,
        skill=skill,
        home=home,
        decision={key: decision.get(key) for key in DECISION_FIELDS},
        staff_sequence={key: sequence.get(key) for key in ("absorbed", "stage", "powers_read")},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, board["turn"], OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
