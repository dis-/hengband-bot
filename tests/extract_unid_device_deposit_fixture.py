"""Freeze the 2026-11-01 00:55 n1-b life-284 departure-unsatisfiable stop (D54).

Source: the automatic capture incident-captures/20261101-005532-departure-
unsatisfiable of the viewing warrior n1-b life-284 (Lv25, 13,858 gold, build
bot-f9c921d32), copied read-only to C:/hengband-backups/pdca/captures/
fix-depart-1101.  The pack held 19 items (4 free, the terminal reserve):
four unknown devices (a rod, a wand, two staves) waited for Identify, the
Identify staves held 12 of the 20 charges a 10F+ departure needs, and only
the two kept diggers were depositable.  The Alchemist's Identify scroll and
the Magic shop's staves each needed a fifth free slot.
departure_block.failed was ["identify_staff_ready", "home_candidate_resolved",
"identification_need_clear", "departure_identification_need_clear"].

Frozen in the shape tests/extract_unid_deposit_fixture.py writes, plus every
ring row from the town arrival board (609552) to the stop board (610826), the
indices of the rows the recorded process decided on (a knowledge or character
request decides on the board before its answer row, an in-store operation on
its own store row, a step on the board at its position), the recorded
decisions, and the last Weapon Smith, Magic shop and Black Market pages of
the rotated ring (the character's earlier visits; this visit entered none of
them).
Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.model import STORE_BLACK, STORE_MAGIC, STORE_WEAPON
from tests.extract_recall_dungeon_prompt_fixture import ring_rows
from tests.extract_unid_deposit_fixture import freeze


CAPTURE = Path("C:/hengband-backups/pdca/captures/fix-depart-1101/n1-b/life-284/"
               "incident-captures/20261101-005532-departure-unsatisfiable")
OUTPUT = Path(__file__).with_name("fixtures") / "unid-device-deposit-20261101.json.gz"
ARRIVAL_TURN, STOP_TURN = 609552, 610826
DECISION_ROWS = (1, 3, 5, 7, 9, 11, 12, 15, 16, 18, 20, 21, 23, 25, 26, 27, 29, 31, 32, 33, 34)
ROTATED_RING = "snapshots-20261101-004048-a29e0d.jsonl.gz"
PREVIOUS_STORES = (STORE_WEAPON, STORE_MAGIC, STORE_BLACK)


def ascending(rows):
    """The copied ring repeats an older member; keep the final ascending run."""
    start = max(i for i, row in enumerate(rows) if i == 0 or row["turn"] < rows[i - 1]["turn"])
    return rows[start:]


def main():
    older = ring_rows((CAPTURE / "snapshots" / ROTATED_RING).read_bytes())
    # The visit read Home from its open page only; the rotated ring's last ~9
    # Home answer is the shape of the replies the test constructs.
    home_answer = [row for row in older if row["type"] == "knowledge"
                   and row["knowledge"]["category"] == "home"][-1]
    previous = {str(store): [row for row in older if row["type"] == "store"
                             and row["store"]["store_type"] == store][-1]["store"]
                for store in PREVIOUS_STORES}
    freeze(CAPTURE, OUTPUT, ARRIVAL_TURN, STOP_TURN,
           "incident-20261101-005532-departure-unsatisfiable (n1-b life-284)",
           home_answer=home_answer)
    rows = ascending(ring_rows((CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()))
    first = next(i for i, row in enumerate(rows)
                 if row["turn"] == ARRIVAL_TURN and row["type"] == "player_turn")
    rows = rows[first:]
    assert rows[-1]["turn"] == STOP_TURN and rows[-1]["type"] == "player_turn"
    decisions = []
    for line in (CAPTURE / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a JSON record.
        if row.get("reason"):
            decisions.append(row)
    # The stop process's consecutive decisions back to the arrival (the tail
    # also holds a later process of the same character).
    end = max(i for i, row in enumerate(decisions)
              if row["turn"] == STOP_TURN and row["reason"].startswith("town:blocked:"))
    begin = end
    while (begin and decisions[begin - 1]["turn"] >= ARRIVAL_TURN
           and decisions[begin - 1]["decision_sequence"] == decisions[begin]["decision_sequence"] - 1):
        begin -= 1
    decisions = decisions[begin:end + 1]
    assert len(decisions) == len(DECISION_ROWS), len(decisions)
    for row, index in zip(decisions, DECISION_ROWS):
        assert rows[index]["turn"] == row["turn"], (index, row["turn"])
    with gzip.open(OUTPUT, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    case.update(
        rows=rows, decision_rows=list(DECISION_ROWS),
        decisions=[{key: row.get(key) for key in (
            "turn", "key", "reason", "decision_sequence", "departure_block",
            "procurement_requirements")} for row in decisions],
        previous_pages=previous,
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(rows), "rows")


if __name__ == "__main__":
    main()
