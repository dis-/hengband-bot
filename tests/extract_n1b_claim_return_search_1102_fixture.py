"""Freeze the n1-b life-293 quest-claim return boards (2026-11-02 13:06).

Source: C:/hengband-backups/pdca/captures/n1b-churn-1102/life-293-incidents/
20261102-130635-loop-detected (bot-1f15e98d1, warrior Lv16, Yeek cave 1F).
Walking back to claim the completed quest 14 (walking out of 1F), the
return searched the walls for a hidden up staircase ('s' eight times per
cell, one step to the next cell) under the claim's label
fixedquest:claim:return until the cell guard stopped it.  Frozen: the ring
boards of turns 205579 and 205592 (two recorded 's' at (3,38)), the
capture's remembered terrain, return modes and escape owner
(policy-state.json), the last skill row before the boards and the recorded
decision rows of those turns.  Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-churn-1102/life-293-incidents/"
               "20261102-130635-loop-detected")
RING = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-claim-return-search-1102.json.gz"
TURNS = (205579, 205592)
MODE_FIELDS = ("_returning_to_town", "_fundraising_mode", "_crossarea_fundraising_enforced",
               "_emergency_return_active", "_last_return_trigger", "_conquest_committed")
DECISION_FACTS = ("decision_sequence", "turn", "reason", "key", "position")


def main() -> None:
    rows = ring_rows(RING.read_bytes())
    boards = [[row for row in rows if row["type"] == "player_turn" and row["turn"] == turn][-1]
              for turn in TURNS]
    skill = [row for row in rows if row["type"] == "knowledge"
             and row["knowledge"]["category"] == "skill_exp" and row["turn"] <= TURNS[0]]
    state = json.loads((CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    decisions = []
    for line in (CAPTURE / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # the bounded tail starts inside a record
        if row.get("turn") in TURNS:
            decisions.append({key: row.get(key) for key in DECISION_FACTS})
    case = dict(
        sources={name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
                 for name in ("snapshots/snapshots-current.jsonl.gz", "policy-state.json",
                              "decision-tail.jsonl")},
        boards=boards, skill=skill[-1] if skill else None, terrain=state["terrain"],
        modes={field: state["modes_and_latches"].get(field) for field in MODE_FIELDS},
        escape_state=state["state"]["_escape_state"], decisions=decisions,
    )
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, [(d["reason"], d["key"]) for d in decisions])


if __name__ == "__main__":
    main()
