"""Freeze the hourly-0700-1103 follow-up boards (n1-c life-115 07:21).

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/hourly-0700-1103/n1-c/life-115/
incident-captures/20261103-072143-town-blocked-unmet-home_candidate_resolved/:

  snapshots/snapshots-current.jsonl.gz
      the Home pages of the visit's Home passes that did not take the
      unknown long sword (ring 1850, 1868, 1869, 1876, 1877; turns
      497396-498133), the visit's last Home list (1880, turn 498154), its
      first skill row (1797) and the stop board (1896, turn 498983);
  policy-state.json
      the Magic-Eater staff sequence record at the stop;
  decision-tail.jsonl
      decisions 137 (town:entrance-step-off:town:end-step-off) and 138
      (town:blocked:unmet:home_candidate_resolved) with their departure
      block and town plan.

Only this extraction tool reads the captures; the committed test reads the
fixture alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


CANDIDATE = Path("C:/hengband-backups/pdca/captures/hourly-0700-1103/n1-c/life-115/"
                 "incident-captures/20261103-072143-town-blocked-unmet-home_candidate_resolved")
PASS_ROWS = (1850, 1868, 1869, 1876, 1877)
HOME_ROW, SKILL_ROW, STOP_ROW = 1880, 1797, 1896
DECISIONS = (137, 138)
OUTPUT = Path(__file__).with_name("fixtures") / "hourly-0700b-1103.json.gz"


def tail_rows(path: Path, sequences) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a record.
        if row.get("decision_sequence") in sequences and "reason" in row:
            rows.append({key: row.get(key) for key in (
                "decision_sequence", "turn", "reason", "key", "home_candidate_waiting",
                "identification_need", "town_plan", "departure_block")})
    return rows


def candidate_case():
    ring = ring_rows(CANDIDATE / "snapshots" / "snapshots-current.jsonl.gz")
    record = json.loads((CANDIDATE / "policy-state.json").read_text(encoding="utf-8"))
    return dict(passes=[ring[index] for index in PASS_ROWS], home=ring[HOME_ROW],
                skill=ring[SKILL_ROW], stop=ring[STOP_ROW],
                sequence=record["state"]["_me_staff_sequence"],
                decisions=tail_rows(CANDIDATE / "decision-tail.jsonl", DECISIONS))


def main():
    write(OUTPUT, dict(source="hourly-0700-1103 follow-up (n1-c life-115, n1-a life-468/469)",
                       home_candidate=candidate_case()))


if __name__ == "__main__":
    main()
