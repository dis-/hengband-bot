"""Freeze the n1-b life-298 departure-unsatisfiable board of 2026-11-02 23:46.

Source: the automatic capture of the viewing warrior n1-b, copied read-only
to C:/hengband-backups/pdca/captures/hourly-0000-1103/n1-b/life-298/
incident-captures/20261102-234627-departure-unsatisfiable/:

  snapshots/snapshots-current.jsonl.gz
      the stop board (turn 263976) and the last skill-proficiency and Home
      knowledge rows before it;
  decision-tail.jsonl
      the recorded rows of decisions 2730-2773 (reason, key, the optimizer's
      blockers and deferred Home items, the failed departure leaves).

Only this extraction tool reads the capture; the committed test reads the
fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import knowledge, ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-0000-1103/n1-b/life-298/"
               "incident-captures/20261102-234627-departure-unsatisfiable")
STOP = 263976
FIRST_DECISION = 2730
OUTPUT = Path(__file__).with_name("fixtures") / "suppression-wait-n1b-298-1102.json.gz"


def decision_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a record.
        if row.get("decision_sequence", 0) >= FIRST_DECISION and "reason" in row:
            optimization = row.get("equipment_optimization") or {}
            rows.append(dict(
                decision_sequence=row["decision_sequence"], turn=row["turn"],
                reason=row["reason"], key=row["key"],
                blockers=optimization.get("blockers"),
                deferred=optimization.get("deferred_home_item_signatures"),
                calibration=optimization.get("calibration"),
                failed=(row.get("departure_block") or {}).get("failed")))
    return rows


def main():
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    index = max(i for i, row in enumerate(rows)
                if row["type"] == "player_turn" and row["turn"] == STOP)
    case = dict(
        source=f"{CAPTURE.name} (copied from the viewing server)",
        board=rows[index],
        skill=knowledge(rows, index, "skill_exp"),
        home=knowledge(rows, index, "home"),
        decisions=decision_rows(CAPTURE / "decision-tail.jsonl"),
    )
    assert case["skill"] and case["home"]
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
