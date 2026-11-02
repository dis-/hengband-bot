"""Freeze the hourly-0700-1103 boards (n1-a life-468, 2026-11-03 07:26).

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/hourly-0700-1103/n1-a/life-468/
incident-captures/20261103-072649-town-blocked-survival-identify_staff_ready/:

  snapshots/snapshots-current.jsonl.gz
      the rows of the previous Outpost visit (ring 1874-1912, turns
      424653-426285, to its town-end step-off before the recall), the skill
      row and last 13F boards before the recall arrival (2387, 2405-2412,
      turns 430874-431117) and every row of the stop visit (2413-2433, turns
      431126-431488): player boards, store pages and knowledge replies in
      the order the bot read them; the ring's only Home list (row 1903, turn
      426075) and the first skill row (1876) prime the policy;
  decision-tail.jsonl
      the recorded decisions 2635 (town:entrance-step-off:town:end-step-off)
      and 2636 (town:blocked:survival:identify_staff_ready) with their town
      plan, departure block and terminal admissions.

Only this extraction tool reads the capture; the committed test reads the
fixture alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-0700-1103/n1-a/life-468/"
               "incident-captures/20261103-072649-town-blocked-survival-identify_staff_ready")
SPANS = ((1874, 1912), (2387, 2387), (2405, 2433))
HOME_ROW, SKILL_ROW = 1903, 1876
DECISIONS = (2635, 2636)
FIELDS = ("decision_sequence", "turn", "reason", "key", "identification_need",
          "town_plan", "terminal_admission")
OUTPUT = Path(__file__).with_name("fixtures") / "hourly-0700-1103.json.gz"


def decision_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a record.
        if row.get("decision_sequence") in DECISIONS and "reason" in row:
            rows.append({field: row.get(field) for field in FIELDS}
                        | {"failed": (row.get("departure_block") or {}).get("failed")})
    return rows


def main():
    ring = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    write(OUTPUT, dict(
        source="n1-a life-468 hourly-0700-1103 identify_staff_ready (07:26:49)",
        identify_staff=dict(
            rows=[ring[index] for first, last in SPANS for index in range(first, last + 1)],
            home=ring[HOME_ROW], skill=ring[SKILL_ROW],
            decisions=decision_rows(CAPTURE / "decision-tail.jsonl"))))


if __name__ == "__main__":
    main()
