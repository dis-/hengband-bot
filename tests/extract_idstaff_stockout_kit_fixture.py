"""Freeze the 2026-10-30 18:00 n1-b life-260 departure-unsatisfiable stop (D29).

Source: the automatic capture incident-captures/20261030-180026-departure-
unsatisfiable of the viewing warrior n1-b life-260 (Lv25, 17,784 gold, four
Identify staves of 3 charges = 12 of the 20 required, bot-5ab8b27d3).  The
process restarted on the previous stop at turn 729490; the frozen suffix is
every ring row from that restart board to the stop board (turn 732860).

On the restarted process the Identify-staff stockout time-pass was installed
at 729908 (``town:identify-staff-stockout-mining``, fundraising ``prepare``),
but its mining kit lacked the one Treasure Detection scroll.  Above the
15,000-gold fundraising target the kit's town needs were not produced, so the
run neither fetched the scroll (Home holds 18) nor left; after the Magic
restock wait the departure terminal stopped with departure_block.failed
["identify_staff_ready"].

Frozen: the rows, the indices of the recorded decision boards, the recorded
decisions, the last observed Home and Alchemist pages (the replies when the
test enters them) and the store entrances.  Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/unfixed-24h-1031/n1-b/life-260/"
               "incident-captures/20261030-180026-departure-unsatisfiable")
RING = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
TAIL = CAPTURE / "decision-tail.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "idstaff-stockout-kit-20261030.json.gz"
RESTART_TURN, STOP_TURN = 729490, 732860
# Ring rows (relative to the restart board) on which the recorded process
# decided; the others are executor observations of the posted keys.
DECISION_ROWS = (0, 6, 8, 11, 12, 13, 15, 16, 19, 20, 21, 22)


def main():
    rows = ring_rows(RING.read_bytes())
    # The copied ring repeats an older member; keep the final ascending run.
    start = max(i for i, row in enumerate(rows) if i == 0 or row["turn"] < rows[i - 1]["turn"])
    rows = rows[start:]
    first = next(i for i, row in enumerate(rows)
                 if row["turn"] == RESTART_TURN and row["type"] == "player_turn")
    suffix = rows[first:]
    assert suffix[-1]["turn"] == STOP_TURN and suffix[-1]["type"] == "player_turn"
    decisions = []
    for line in TAIL.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a JSON record.
        if row.get("turn", 0) >= RESTART_TURN and row.get("reason"):
            decisions.append(row)
    # The first one is the previous process's stop at the restart board.
    assert decisions[0]["reason"] == "town:blocked:departure-unsatisfiable"
    decisions = decisions[1:]
    assert len(decisions) == len(DECISION_ROWS), len(decisions)
    pages = {}
    for row in rows:
        if row["type"] == "store":
            pages[str(row["store"]["store_type"])] = row["store"]
    cells = [[c["y"], c["x"], c["s"]] for c in suffix[-1]["grid_map"]["cells"] if "s" in c]
    case = dict(
        source="incident-20261030-180026-departure-unsatisfiable (n1-b life-260)",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (RING, TAIL)},
        rows=suffix,
        decision_rows=list(DECISION_ROWS),
        decisions=[dict(turn=row["turn"], key=row["key"], reason=row["reason"],
                        decision_sequence=row["decision_sequence"],
                        fundraising=row.get("fundraising"),
                        procurement_requirements=row.get("procurement_requirements"),
                        departure_block=row.get("departure_block"))
                   for row in decisions],
        pages={key: pages[key] for key in ("4", "7")},
        store_cells=cells,
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(suffix), "rows")


if __name__ == "__main__":
    main()
