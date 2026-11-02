"""Freeze the hourly-0000-1103 boards (n1-c life-112, 2026-11-03 00:25).

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/hourly-0000-1103/n1-c/life-112/:

  captures/20261103-002549-town-blocked-owner-retired-burst/
      state.jsonl.gz: the town boards of decisions 9158 (turn 822001, the
      Home travel ``\\x1b`n(.``) and 9161 (turn 822220, ``5``
      shop:travel:await-entry on the Home entrance after the identify);
      bot-decisions.jsonl.gz: the facts of decisions 9158-9181 (reason,
      key, store visit and the equipment session's next action).
  incident-captures/20261103-002545-town-blocked-owner-retired-burst/
  snapshots/snapshots-current.jsonl.gz
      the last Home list (turn 814522) and skill row before the stop.
  captures/20261103-000601-quest-blocked-me-staff/
      state.jsonl.gz: the town board after the recall (turn 605456), its
      Home list and skill row; bot-decisions.jsonl.gz: decisions 467 (the
      9F ``bA`` browse) and 544-549 (to quest:blocked:me-staff).
  incident-captures/20261103-000449-loop-detected/policy-state.json and
  incident-captures/20261103-000557-quest-blocked-me-staff/policy-state.json
      the staff sequence record before the restart (its absorbed staffs) and
      at the stop.

Only this extraction tool reads the captures; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


LIFE = Path("C:/hengband-backups/pdca/captures/hourly-0000-1103/n1-c/life-112")
BURST = LIFE / "captures" / "20261103-002549-town-blocked-owner-retired-burst"
RING = (LIFE / "incident-captures" / "20261103-002545-town-blocked-owner-retired-burst"
        / "snapshots" / "snapshots-current.jsonl.gz")
BOARD_TURNS = {"travel": 822001, "entrance": 822220}
DECISIONS = (9158, 9181)
STAFF = LIFE / "captures" / "20261103-000601-quest-blocked-me-staff"
STAFF_TURN = 605456
STAFF_DECISIONS = (467, 544, 545, 546, 547, 548, 549)
BEFORE_RESTART = LIFE / "incident-captures" / "20261103-000449-loop-detected" / "policy-state.json"
AT_STOP = LIFE / "incident-captures" / "20261103-000557-quest-blocked-me-staff" / "policy-state.json"
OUTPUT = Path(__file__).with_name("fixtures") / "hourly-0000-1103.json.gz"


def rows_of(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a torn tail of the previous session
    return rows


def board(rows, turn):
    return [row for row in rows if row["type"] == "player_turn" and row["turn"] == turn][-1]


def knowledge(rows, category, before):
    return [row for row in rows if row["type"] == "knowledge"
            and row["knowledge"]["category"] == category and row["turn"] <= before][-1]


def decision_facts(row):
    equipment = row.get("equipment_optimization") or {}
    return {"decision_sequence": row["decision_sequence"], "turn": row["turn"],
            "reason": row["reason"], "key": row["key"], "store_visit": row.get("store_visit"),
            "transaction_next": equipment.get("transaction_next"),
            "context": (equipment.get("equipment_transaction") or {}).get("context")}


def sequence_record(path):
    return json.loads(path.read_text(encoding="utf-8"))["state"]["_me_staff_sequence"]


def staff_case():
    state = rows_of(STAFF / "state.jsonl.gz")
    return dict(
        board=board(state, STAFF_TURN), home=knowledge(state, "home", STAFF_TURN),
        skill=knowledge(state, "skill_exp", STAFF_TURN),
        decisions=[{key: row[key] for key in ("decision_sequence", "turn", "reason", "key", "floor")}
                   for row in rows_of(STAFF / "bot-decisions.jsonl.gz")
                   if row.get("decision_sequence") in STAFF_DECISIONS and "reason" in row],
        before_restart=sequence_record(BEFORE_RESTART), at_stop=sequence_record(AT_STOP))


def main():
    state = rows_of(BURST / "state.jsonl.gz")
    ring = ring_rows(RING)
    first, last = DECISIONS
    decisions = [decision_facts(row) for row in rows_of(BURST / "bot-decisions.jsonl.gz")
                 if first <= (row.get("decision_sequence") or 0) <= last
                 and "reason" in row]
    write(OUTPUT, dict(
        source="n1-c life-112 hourly-0000-1103 owner-retired-burst (00:25:49)",
        equip=dict(boards={name: board(state, turn) for name, turn in BOARD_TURNS.items()},
                   home=knowledge(ring, "home", BOARD_TURNS["entrance"]),
                   skill=knowledge(ring, "skill_exp", BOARD_TURNS["entrance"]),
                   decisions=decisions),
        staff=staff_case()))


if __name__ == "__main__":
    main()
