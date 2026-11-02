"""Freeze the n1-c life-107 town end of 2026-11-02 18:38 (town-end-purchase-only-1102).

Source: the viewing Magic-Eater n1-c (life-107, Lv15), copied read-only to
C:/hengband-backups/pdca/captures/town-end-purchase-only-1102/:

  snapshots-20261102-185240-f9e580.jsonl.gz
      the snapshot ring of jsonlog/snapshots covering 18:38:11-18:52:40.
      The bot process restarted at 18:38:33 on the save of turn 949749.
  decisions-949982.jsonl
      bot-decisions.jsonl.4 lines 7850-7960: the new process's decisions
      0-9 (shop:travel to the Black Market, shop:observe-and-leave, the town
      end's mining cycle on the Black Market entrance at turn 949982,
      town:travel-entrance, and only then home:request-knowledge-scan).
  town-end-mining.json, keep-running-events.jsonl
      the cycle's record (unmet equipment_departure_ready and
      home_catalog_ready) and the departure-unsatisfiable mining_cycle row.

Kept: the new process's boards of turns 949749 (the restart, rows 127-135),
949973 (the Black Market page) and 949982 (its entrance), the skill row the
process read first and the Home knowledge row its later ``~9`` read, and the
decision rows 0-9 with their departure_block.

Only this extraction tool reads the captures; the committed test reads the
fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


ROOT = Path("C:/hengband-backups/pdca/captures/town-end-purchase-only-1102")
RING = ROOT / "snapshots-20261102-185240-f9e580.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "town-end-purchase-only-1102.json.gz"
RESTART_TURN, END_TURN = 949749, 949982
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position",
                   "departure_block", "fundraising", "procurement_requirements",
                   "home_scan")


def main():
    rows = ring_rows(RING)
    start = next(index for index, row in enumerate(rows) if row["turn"] == RESTART_TURN)
    end = max(index for index, row in enumerate(rows) if row["turn"] == END_TURN)
    boards = [row for row in rows[start:end + 1] if row["type"] in ("player_turn", "store")]
    skill = next(row for row in rows[start:end] if row["type"] == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp")
    home = next(row for row in rows[end:] if row["type"] == "knowledge"
                and row["knowledge"]["category"] == "home")
    decisions = []
    seen_restart = False
    for line in (ROOT / "decisions-949982.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        seen_restart = seen_restart or row.get("turn") == RESTART_TURN
        if seen_restart and row.get("reason") and row["decision_sequence"] <= 9:
            decisions.append({field: row.get(field) for field in DECISION_FIELDS})
    record = json.loads((ROOT / "town-end-mining.json").read_text(encoding="utf-8"))
    write(OUTPUT, dict(
        source=f"{RING.name} (copied from the viewing server)",
        boards=boards, decisions=decisions, skill=skill, home=home, cycle=record))


if __name__ == "__main__":
    main()
