"""Freeze the 2026-11-02 n1-c life-102 Outpost board refused by toughest-kill-time.

Source: read-only copies from the viewing zombie Magic-Eater n1-c (Lv12,
max HP 151, War Hammer (3d3) (+3,+5) wielded, the Shovel in the pack):

  C:/hengband-backups/pdca/captures/q14-digger-dps-1102/snap-0422-board.jsonl
      the rows of turns 1055400-1057400 (and the knowledge rows) of server
      ~/hengbot-soak/n1-c/life-102/incident-captures/20261102-044105-posting-
      contract-recall-already-active/snapshots/snapshots-20261102-043631-
      fec48d.jsonl.gz (the ring of 04:18:27-04:36:31): the town board of
      turn 1057356, the skill_exp row of turn 1055440 and the Home row of
      turn 1056903.
  C:/hengband-backups/pdca/captures/q14-lv8-1102/n1-c/life-102/
      decisions-0421.jsonl   bot-decisions rows 2640-3549 (04:21-04:22).
      policy-state-0427.json the 04:27 incident checkpoint (every sequence
                             staff absorbed, stage 3).

Decision 3141 (turn 1057356, 04:22:13) left the General Store for the
Morivant tower: fixedquest_readiness quest 14 ``toughest-kill-time``,
main_hand_melee_output 3.0 (hasted) while the force gate measured 24.0 DPS
with the same War Hammer at the profile's reference_ac 20.

Only this extraction tool reads the copies; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_dungeon_1031_fixture import sha


BOARD_ROWS = Path("C:/hengband-backups/pdca/captures/q14-digger-dps-1102/snap-0422-board.jsonl")
LIFE = Path("C:/hengband-backups/pdca/captures/q14-lv8-1102/n1-c/life-102")
DECISIONS = LIFE / "decisions-0421.jsonl"
STATE = LIFE / "policy-state-0427.json"
OUTPUT = Path(__file__).with_name("fixtures") / "q14-kill-time-ac-1102.json.gz"
BOARD_TURN = 1057356
DECISION = 3141
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "objective",
                   "fixedquest_readiness")


def main():
    rows = [json.loads(line) for line in BOARD_ROWS.read_text(encoding="utf-8").splitlines()]
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
        source="n1-c life-102 (2026-11-02 04:22:13, the Outpost after the General Store visit of decisions 3137-3140)",
        sources={path.name: sha(path) for path in (BOARD_ROWS, DECISIONS, STATE)},
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
