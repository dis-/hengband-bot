"""Freeze the hourly-2300-1102 boards (n1-a life-466, 2026-11-02 23:18).

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/hourly-2300-1102/n1-a/life-466/:

  captures/20261102-231848-town-blocked-departure-unsatisfiable/state.jsonl.gz
      the stop board (turn 676638, town:blocked:departure-unsatisfiable),
      the Home list read on it and the skill row.
  incident-captures/20261102-231856-posting-contract-recall-already-active/
  snapshots/snapshots-current.jsonl.gz
      the restarted session's recall read board (turn 677221, decision 12
      town:recall-to-yeek-cave ``rgb``) and the next board (677231, decision
      13 town:cancel-wrong-recall-destination ``rg``).

Only this extraction tool reads the captures; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


LIFE = Path("C:/hengband-backups/pdca/captures/hourly-2300-1102/n1-a/life-466")
STOP = LIFE / "captures" / "20261102-231848-town-blocked-departure-unsatisfiable"
RECALL = (LIFE / "incident-captures"
          / "20261102-231856-posting-contract-recall-already-active")
OUTPUT = Path(__file__).with_name("fixtures") / "hourly-2300-1102.json.gz"


def rows_of(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def board(rows, turn):
    return [row for row in rows if row["type"] == "player_turn" and row["turn"] == turn][-1]


def knowledge(rows, category):
    return [row for row in rows if row["type"] == "knowledge"
            and row["knowledge"]["category"] == category][-1]


def main():
    stop = rows_of(STOP / "state.jsonl.gz")
    recall = ring_rows(RECALL / "snapshots" / "snapshots-current.jsonl.gz")
    write(OUTPUT, dict(
        source="state.jsonl.gz of the n1-a life-466 hourly-2300-1102 captures",
        identify=dict(stop=board(stop, 676638), home=knowledge(stop, "home"),
                      skill=knowledge(stop, "skill_exp")),
        recall=dict(read=board(recall, 677221), next=board(recall, 677231),
                    skill=knowledge(recall, "skill_exp"))))


if __name__ == "__main__":
    main()
