"""Freeze the n1-c life-113 stall:town:restore-combat-weapon boards (2026-11-03 01:35).

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/hourly-0100-1103/n1-c/life-113/ (build
476464048):

  captures/20261103-013536-stall-town-restore-combat-weapon/
      state.jsonl.gz: the first five town boards after the restart (turns
      352524-352566: サーベル / タルワール in the main hand, 穴掘りのドワーフの
      つるはし in the off hand, 19 pack items);
      bot-decisions.jsonl.gz: the decisions of the same turns (``wna``
      town:restore-combat-weapon, each swapping the two weapons).
  incident-captures/20261103-012317-town-blocked-survival-cure_critical_ready/
      snapshots/snapshots-current.jsonl.gz: the last skill row of the life
      (turn 263388); policy-state.json: the staff sequence record then.

Only this extraction tool reads the captures; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import knowledge, ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


LIFE = Path("C:/hengband-backups/pdca/captures/hourly-0100-1103/n1-c/life-113")
CAPTURE = LIFE / "captures" / "20261103-013536-stall-town-restore-combat-weapon"
INCIDENT = LIFE / "incident-captures" / "20261103-012317-town-blocked-survival-cure_critical_ready"
BOARDS = 5
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-offhand-digger-1103.json.gz"


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
    boards = [row for row in rows_of(CAPTURE / "state.jsonl.gz")
              if row["type"] == "player_turn"][:BOARDS]
    turns = {board["turn"] for board in boards}
    decisions = [{key: row[key] for key in ("decision_sequence", "turn", "reason", "key", "messages")}
                 for row in rows_of(CAPTURE / "bot-decisions.jsonl.gz")
                 if row.get("turn") in turns and "reason" in row]
    ring = ring_rows(INCIDENT / "snapshots" / "snapshots-current.jsonl.gz")
    record = json.loads((INCIDENT / "policy-state.json").read_text(encoding="utf-8"))
    write(OUTPUT, dict(
        source="n1-c life-113 hourly-0100-1103 stall-town-restore-combat-weapon (01:35:36)",
        boards=boards, decisions=decisions, skill=knowledge(ring, len(ring), "skill_exp"),
        sequence=record["state"]["_me_staff_sequence"]))


if __name__ == "__main__":
    main()
