"""Freeze the 2026-10-30 08:37 n1-a life-427 departure-unsatisfiable stop (D29).

Source: the automatic capture incident-captures/20261030-083722-departure-
unsatisfiable of the viewing warrior n1-a life-427 (Lv15, 5,346 gold).  The
pack held 19 items (4 free, MIN_TERMINAL_FREE_PACK_SLOTS) with Identify
staves of 16 charges; Magic sold a 16-charge staff (910 gold), but the
purchase needed a fifth free slot.  Four carried equipment items waited for
*Identify* the Alchemist did not sell (a lantern of long life, the gloves of
slaying, a poisoned main gauche and the artifact sabre), and Home's deposit
pass kept them as identification-flow candidates.  departure_block.failed
was ["identify_staff_ready"].

Frozen: the town-arrival board (turn 404797), every store page and knowledge
answer observed during the visit, the last ~9 Home answer before the stop, the stop board (turn 406215), the store
entrances and the recorded stop decision facts.  Only this tool reads the
capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


CAPTURE = Path("C:/hengband-backups/pdca/captures/unfixed-24h-1031/n1-a/life-427/"
               "incident-captures/20261030-083722-departure-unsatisfiable")
RING = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
TAIL = CAPTURE / "decision-tail.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "unid-deposit-20261030.json.gz"
ARRIVAL_TURN, STOP_TURN = 404797, 406215


def main():
    rows = ring_rows(RING.read_bytes())
    # The copied ring repeats an older member; keep the final ascending run.
    start = max(i for i, row in enumerate(rows) if i == 0 or row["turn"] < rows[i - 1]["turn"])
    rows = rows[start:]
    arrival = next(i for i, row in enumerate(rows)
                   if row["turn"] >= ARRIVAL_TURN and row["type"] == "player_turn")
    stop = max(i for i, row in enumerate(rows) if row["type"] == "player_turn")
    assert rows[stop]["turn"] == STOP_TURN, rows[stop]["turn"]
    observations = [row for row in rows[arrival + 1:stop] if row["type"] in ("store", "knowledge")]
    decision = None
    for line in TAIL.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a JSON record.
        if row.get("reason") == "town:blocked:departure-unsatisfiable":
            decision = row
    assert decision is not None and decision["turn"] == STOP_TURN
    case = dict(
        source="incident-20261030-083722-departure-unsatisfiable (n1-a life-427)",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (RING, TAIL)},
        arrival=rows[arrival],
        observations=observations,
        # The last ~9 Home answer before the stop: the shape of the replies
        # the test constructs for later ~9 requests.
        home_answer=next(row for row in reversed(rows[:stop]) if row["type"] == "knowledge"
                         and row["knowledge"]["category"] == "home"),
        board=rows[stop],
        store_cells=[[c["y"], c["x"], c["s"]] for c in rows[stop]["grid_map"]["cells"] if "s" in c],
        decision=dict(turn=decision["turn"], key=decision["key"], reason=decision["reason"],
                      departure_block=decision["departure_block"],
                      procurement_requirements=decision["procurement_requirements"],
                      shop_selector=decision["shop_selector"], inventory=decision["inventory"]),
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(observations), "observations")


if __name__ == "__main__":
    main()
