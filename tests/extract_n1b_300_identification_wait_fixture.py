"""Freeze the n1-b life-300 town visit of 2026-11-03 02:08-02:23 (the Outpost).

Source: the automatic town:blocked:unmet:home_candidate_resolved capture of
the viewing warrior n1-b, copied read-only to
C:/hengband-backups/pdca/captures/hourly-0200-1103/n1-b/life-300/incident-captures/
20261103-022345-town-blocked-unmet-home_candidate_resolved/:

  snapshots/snapshots-current.jsonl.gz
      every row of the visit from its arrival board (turn 754636) to the stop
      (756154): the player boards, the store pages and the knowledge replies,
      in the order the bot read them; the first skill-proficiency and Home
      knowledge rows of the visit prime the policy;
  decision-tail.jsonl
      the recorded decision rows of the same turns (with their Home latch,
      identification need and failed departure leaves).

Only this extraction tool reads the capture; the committed test reads the
fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-0200-1103/n1-b/life-300/"
               "incident-captures/20261103-022345-town-blocked-unmet-home_candidate_resolved")
SPAN = (754636, 756154)
FIELDS = ("decision_sequence", "turn", "reason", "key",
          "home_candidate_waiting", "identification_need")
OUTPUT = Path(__file__).with_name("fixtures") / "identification-wait-n1b-300-1103.json.gz"


def decision_rows(path: Path, turns: set[int]) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a record.
        if row.get("turn") in turns and "reason" in row:
            rows.append({field: row.get(field) for field in FIELDS}
                        | {"failed": (row.get("departure_block") or {}).get("failed")})
    return rows


def first_knowledge(rows, category):
    return next(row for row in rows if row["type"] == "knowledge"
                and row["knowledge"]["category"] == category)


def main():
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    start = next(index for index, row in enumerate(rows)
                 if row["type"] == "player_turn" and row["turn"] >= SPAN[0])
    visit = [row for row in rows[start:]
             if row["type"] in ("player_turn", "store", "knowledge")
             and row.get("turn", SPAN[0]) <= SPAN[1]]
    turns = {row["turn"] for row in visit if row["type"] == "player_turn"}
    assert {*SPAN} <= turns, SPAN
    case = dict(
        source=f"{CAPTURE.name} (copied from the viewing server)",
        rows=visit,
        skill=first_knowledge(rows[start:], "skill_exp"),
        home=first_knowledge(rows[start:], "home"),
        decisions=decision_rows(CAPTURE / "decision-tail.jsonl", turns),
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(visit))


if __name__ == "__main__":
    main()
