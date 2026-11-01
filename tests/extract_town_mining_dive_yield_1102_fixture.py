"""Freeze the n1-a life-464 town stop of 2026-11-02 05:49 (town-mining-dive-yield-1102).

Source: the viewing warrior n1-a (build bot-10ac9173a), copied read-only to
C:/hengband-backups/pdca/captures/hourly-0600-1102/
n1-a-life-464-20261102-054907-town-blocked-departure-unsatisfiable/:

  incident-captures/20261102-054906-departure-unsatisfiable
      the snapshot ring and the policy-state checkpoint
      (``_town_end_mining_cycle``, ``_town_visit_epoch``).
  bot-decisions.jsonl.gz
      the recorded decision rows 5453 (``town:entrance-step-off:town:end-
      mining-cycle``) and 5454 (``town:blocked:departure-unsatisfiable``).

Kept: the Outpost boards of turns 2870486 (the cycle's start, on the Home
entrance) and 2870501 (the stop), the skill and Home knowledge rows the
visit read last (turns 2869366 and 2870474), the checkpoint's cycle record
and the two decision rows with their departure_block.

Only this extraction tool reads the captures; the committed test reads the
fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import knowledge, ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0600-1102/"
            "n1-a-life-464-20261102-054907-town-blocked-departure-unsatisfiable")
CAPTURE = ROOT / "incident-captures/20261102-054906-departure-unsatisfiable"
OUTPUT = Path(__file__).with_name("fixtures") / "town-mining-dive-yield-1102.json.gz"
START_TURN, STOP_TURN = 2870486, 2870501
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position",
                   "departure_block", "fundraising", "procurement_requirements")


def main():
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    boards = {}
    for index, row in enumerate(rows):
        if row["type"] == "player_turn" and row["turn"] in (START_TURN, STOP_TURN):
            boards.setdefault(row["turn"], (index, row))
    start = boards[START_TURN][0]
    with gzip.open(ROOT / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        decisions = [{field: row.get(field) for field in DECISION_FIELDS}
                     for row in map(json.loads, stream)
                     if row.get("turn") in (START_TURN, STOP_TURN) and row.get("reason")]
    state = json.loads((CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    write(OUTPUT, dict(
        source=f"{CAPTURE.relative_to(ROOT.parent)} (copied from the viewing server)",
        boards=[boards[START_TURN][1], boards[STOP_TURN][1]],
        decisions=decisions,
        skill=knowledge(rows, start, "skill_exp"),
        home=knowledge(rows, start, "home"),
        cycle=state["state"]["_town_end_mining_cycle"],
        visit_epoch=state["modes_and_latches"]["_town_visit_epoch"],
    ))


if __name__ == "__main__":
    main()
