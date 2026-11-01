"""Freeze the 2026-11-01 n1-a life-453 departure-unsatisfiable stop (D54).

Source: the automatic capture incident-captures/20261101-005741-departure-
unsatisfiable of the viewing warrior n1-a life-453 (Lv26, 20,202 gold, build
bot-f9c921d32), copied read-only to C:/hengband-backups/pdca/captures/
fix-depart-1101.  The Magic shop sold out of Identify staves at 16 of the 20
charges a 10F+ departure needs; the Identify-staff stock-out time-pass took
Yeek cave 1F's stairs down at turn 885633 and straight back up at 885634
(fundraise:ascend, gold above the 15,000 target), so no restock time passed.
The next visit (arrival 885635) found Magic still sold out, skipped the Black
Market on its earlier-visit shelf, and stopped at 886291 with
departure_block.failed ["identify_staff_ready"].

Frozen in the shape tests/extract_unid_deposit_fixture.py writes (arrival,
the visit's store pages and knowledge, the stop board and decision), plus the
Black Market page of the earlier visit (turn 883949, the shelf evidence the
visit's planner read), the Yeek cave 1F board (885634) and the recorded
descend / fundraise:ascend decisions.  Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.model import STORE_BLACK
from tests.extract_recall_dungeon_prompt_fixture import ring_rows
from tests.extract_unid_deposit_fixture import freeze


CAPTURE = Path("C:/hengband-backups/pdca/captures/fix-depart-1101/n1-a/life-453/"
               "incident-captures/20261101-005741-departure-unsatisfiable")
OUTPUT = Path(__file__).with_name("fixtures") / "idstaff-stockout-run-20261101.json.gz"
ARRIVAL_TURN, STOP_TURN = 885635, 886291
BLACK_MARKET_TURN, DESCEND_TURN, YEEK_TURN = 883949, 885633, 885634


def main():
    freeze(CAPTURE, OUTPUT, ARRIVAL_TURN, STOP_TURN,
           "incident-20261101-005741-departure-unsatisfiable (n1-a life-453)")
    rows = ring_rows((CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes())
    start = max(i for i, row in enumerate(rows) if i == 0 or row["turn"] < rows[i - 1]["turn"])
    rows = rows[start:]
    black_market = [row for row in rows if row["type"] == "store" and row["turn"] == BLACK_MARKET_TURN
                    and row["store"]["store_type"] == STORE_BLACK][-1]
    yeek = [row for row in rows if row["type"] == "player_turn" and row["turn"] == YEEK_TURN
            and row["floor"]["dungeon_id"] == 2][-1]
    decisions = []
    for line in (CAPTURE / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a JSON record.
        if row.get("turn") in (DESCEND_TURN, YEEK_TURN) and row.get("reason"):
            decisions.append({key: row.get(key) for key in (
                "turn", "key", "reason", "fundraising", "mining", "player")})
    assert [row["reason"] for row in decisions] == ["descend", "fundraise:ascend"], decisions
    with gzip.open(OUTPUT, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    case.update(earlier_black_market=black_market, yeek_board=yeek, yeek_decisions=decisions)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
