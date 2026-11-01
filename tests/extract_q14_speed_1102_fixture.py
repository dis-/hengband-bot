"""Freeze the 2026-11-02 n1-c life-102 Outpost board that refused Q14 for a Potion of Speed.

Source: read-only copies from the viewing zombie Magic-Eater n1-c (Lv8,
max HP 137 at the board) in
C:/hengband-backups/pdca/captures/n1c-q14-speed-1102/n1-c/life-102/
(server ~/hengbot-soak/n1-c/life-102/):

  snapshots-20261102-040305-b15d21.jsonl.gz
                          jsonlog/snapshots/: the snapshot ring rotated at
                          04:03; it holds the player_turn boards of turn
                          860272 and the last skill_exp / Home knowledge rows
                          before it.
  decisions-0359.jsonl    the jsonlog/bot-decisions.jsonl rows of 03:59:2x-3x
                          (decisions 5574-5708).
  policy-state-0347.json  incident-captures/20261102-034727-loop-detected/:
                          the newest diagnostic checkpoint before the board;
                          its ``_me_staff_sequence`` is the staff record.

Decision 5697 (turn 860272, after the Temple bought ten Potions of Cure
Critical Wounds) recorded fixedquest_readiness quest 14 ``strategy-force``
failed ["speed_potions"] measured 0 required 1: no store but the Black
market sells a Potion of Speed (store/articles-on-sale.cpp), and its shelf
had none.

Only this extraction tool reads the copies; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_dungeon_1031_fixture import ring_rows, sha


LIFE = Path("C:/hengband-backups/pdca/captures/n1c-q14-speed-1102/n1-c/life-102")
RING = LIFE / "snapshots-20261102-040305-b15d21.jsonl.gz"
DECISIONS = LIFE / "decisions-0359.jsonl"
STATE = LIFE / "policy-state-0347.json"
OUTPUT = Path(__file__).with_name("fixtures") / "q14-speed-1102.json.gz"
BOARD_TURN = 860272
DECISION = 5697
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "objective",
                   "fixedquest_readiness", "procurement_requirements")


def main():
    rows = list(ring_rows(RING.read_bytes()))
    board = [row for row in rows
             if row.get("type") == "player_turn" and row["turn"] == BOARD_TURN][-1]
    knowledge = [row for row in rows
                 if row.get("type") == "knowledge" and row["turn"] <= BOARD_TURN]
    skill = [row for row in knowledge if row["knowledge"]["category"] == "skill_exp"][-1]
    home = [row for row in knowledge if row["knowledge"]["category"] == "home"][-1]
    decision = next(row for row in map(json.loads, DECISIONS.read_text(encoding="utf-8").splitlines())
                    if row["decision_sequence"] == DECISION)
    assert decision["turn"] == BOARD_TURN, decision["turn"]
    sequence = json.loads(STATE.read_text(encoding="utf-8"))["state"]["_me_staff_sequence"]
    case = dict(
        source="n1-c life-102 (2026-11-02 03:59:36, the Outpost after the visit of decisions 5670-5697)",
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
