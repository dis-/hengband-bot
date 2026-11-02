"""Freeze the n1-c life-112 quest:blocked:me-staff boards of 2026-11-03 01:12.

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/hourly-0100-1103/n1-c/life-112/ (build
476464048):

  captures/20261103-011234-quest-blocked-me-staff/
      state.jsonl.gz: the town boards of turns 1287061-1287139 (the dump,
      the Word of Recall read to Angband, the step off the entrance and the
      eight waits on (36, 90)) and the last Home list (turn 1286325);
      bot-decisions.jsonl.gz: decisions 4719-4729 (to the stop).
  incident-captures/20261103-011232-quest-blocked-me-staff/
      snapshots/snapshots-current.jsonl.gz: the last skill row (1285138);
      policy-state.json: the staff sequence record at the stop.

Only this extraction tool reads the captures; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import knowledge, ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


LIFE = Path("C:/hengband-backups/pdca/captures/hourly-0100-1103/n1-c/life-112")
CAPTURE = LIFE / "captures" / "20261103-011234-quest-blocked-me-staff"
INCIDENT = LIFE / "incident-captures" / "20261103-011232-quest-blocked-me-staff"
TURNS = (1287061, 1287139)
DECISIONS = (4719, 4729)
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-staff-travel-wait-1103.json.gz"


def rows_of(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a torn tail of the previous session
    return rows


def main():
    state = rows_of(CAPTURE / "state.jsonl.gz")
    first, last = TURNS
    boards = {}
    for row in state:
        if row["type"] == "player_turn" and first <= row["turn"] <= last:
            boards[row["turn"]] = row  # the last board of each turn
    home = [row for row in state if row["type"] == "knowledge"
            and row["knowledge"]["category"] == "home"][-1]
    ring = ring_rows(INCIDENT / "snapshots" / "snapshots-current.jsonl.gz")
    record = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))
    low, high = DECISIONS
    decisions = [{key: row[key] for key in ("decision_sequence", "turn", "reason", "key", "rung")}
                 for row in rows_of(CAPTURE / "bot-decisions.jsonl.gz")
                 if low <= (row.get("decision_sequence") or 0) <= high and "reason" in row]
    write(OUTPUT, dict(
        source="n1-c life-112 hourly-0100-1103 quest-blocked-me-staff (01:12:34)",
        boards=[boards[turn] for turn in sorted(boards)], home=home,
        skill=knowledge(ring, len(ring), "skill_exp"),
        sequence=record["state"]["_me_staff_sequence"], decisions=decisions))


if __name__ == "__main__":
    main()
