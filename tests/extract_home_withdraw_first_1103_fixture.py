"""Freeze the n1-c life-112 owner-retired-burst boards of 2026-11-02 23:43.

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/hourly-0000-1103/n1-c/life-112/captures/
20261102-234354-town-blocked-owner-retired-burst/ (build 476464048):

  state.jsonl.gz: the town boards of decisions 628 (turn 81343, the step
      off the General store's entrance toward the Armoury) and 629 (turn
      81353, the first ``5`` shop:approach), the Home list (turn 81154) and
      the skill row (80969);
  bot-decisions.jsonl.gz: decisions 626-671 (to town:blocked:
      owner-retired-burst) with their store visit and the equipment
      session's next action.

Only this extraction tool reads the capture; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_n1c_loops_0336_1102_fixtures import write


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-0000-1103/n1-c/life-112/captures"
               "/20261102-234354-town-blocked-owner-retired-burst")
BOARD_TURNS = {"step_off": 81343, "approach": 81353}
DECISIONS = (626, 671)
OUTPUT = Path(__file__).with_name("fixtures") / "home-withdraw-first-1103.json.gz"


def rows_of(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a torn tail of the previous session
    return rows


def last(rows, kind, category):
    return [row for row in rows if row["type"] == kind
            and row["knowledge"]["category"] == category][-1]


def main():
    state = rows_of(CAPTURE / "state.jsonl.gz")
    boards = {name: [row for row in state if row["type"] == "player_turn"
                     and row["turn"] == turn][-1] for name, turn in BOARD_TURNS.items()}
    low, high = DECISIONS
    decisions = []
    for row in rows_of(CAPTURE / "bot-decisions.jsonl.gz"):
        if "reason" in row and low <= row["decision_sequence"] <= high:
            equipment = row.get("equipment_optimization") or {}
            decisions.append({
                "decision_sequence": row["decision_sequence"], "turn": row["turn"],
                "reason": row["reason"], "key": row["key"],
                "store_type": (row.get("store_visit") or {}).get("store_type"),
                "transaction_next": equipment.get("transaction_next"),
                "context": (equipment.get("equipment_transaction") or {}).get("context")})
    write(OUTPUT, dict(
        source="n1-c life-112 hourly-0000-1103 owner-retired-burst (23:43:54)",
        boards=boards, home=last(state, "knowledge", "home"),
        skill=last(state, "knowledge", "skill_exp"), decisions=decisions))


if __name__ == "__main__":
    main()
