"""Freeze the 2026-11-01 n1-c life-092 town stops (D59) and its 13:18 restart.

Source: the automatic captures of the viewing Magic-Eater n1-c life-092
(Lv21-22, build bot-394c491c7), copied read-only to C:/hengband-backups/pdca/
captures/fix-depart2-1101/n1-c/life-092:

- incident-captures/20261101-134754-departure-unsatisfiable (13:47:59): the
  equipment transaction withdrew one cloak of a Home stack of four, then
  refused to wear it (equip-item-missing); the visit stopped later on the
  departure-unsatisfiable latch.  The forced departure's minimum failed
  identify_staff_ready only (keep-running-events.jsonl turn 2609730).
- incident-captures/20261101-135436-departure-unsatisfiable (13:54:41): the
  random-teleport suppression inscribed the trident the open transaction was
  depositing, the Home deposit could not find it (deposit-missing) and the
  visit closure left equipment_departure_ready false; the forced departure's
  minimum again failed identify_staff_ready only (turn 2648425).
- captures/20261101-131854-stuck-prompt-quest-strategy-ranged-fire-magic-eater
  (13:18:56): the absorbed wand failed (no direction asked) and the recall
  moved the character to town before the screen was read.

Frozen per stop: the town board the boundary primes on, every store page,
knowledge and character answer of the visit after it, the named boards the
tests start from, the store entrances and the recorded decision facts.
Only this tool reads the captures.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/fix-depart2-1101/n1-c/life-092")
OUTPUT = Path(__file__).with_name("fixtures") / "depart2-1101.json.gz"
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "departure_block",
                   "procurement_requirements", "position", "player", "inventory", "over_extension")
STATE_KEYS = ("_me_staff_sequence", "_equipment_transaction_failed_items", "_town_blocked_reason")
MODE_KEYS = ("_town_supplier_stock", "_town_supplier_stock_observations")
EQUIPMENT_FIELDS = ("transaction_next", "transaction_actions", "failed_transaction_item_ids",
                    "result_source", "blockers")
# (case, capture, arrival turn, {board name: (turn, row type, occurrence)}, decisions)
CASES = (
    ("cloak", "20261101-134754-departure-unsatisfiable", 2608568,
     # The Home page with the four-cloak stack, then the page after the take.
     {"stack": (2609615, "store", 0), "taken": (2609624, "store", 0),
      "stop": (2609774, "player_turn", -1)},
     (13420, 13470)),
    ("trident", "20261101-135436-departure-unsatisfiable", 2646422,
     # The pack before the inscription, the Home page of the failed deposit.
     {"plain": (2647476, "player_turn", 0), "home": (2647884, "store", 0),
      "stop": (2648425, "player_turn", -1)},
     (3019, 3061)),
)
STUCK = ROOT / "captures" / "20261101-131854-stuck-prompt-quest-strategy-ranged-fire-magic-eater"


def ascending(rows):
    """The copied ring repeats an older member; keep the final ascending run."""
    start = max(i for i, row in enumerate(rows) if i == 0 or row["turn"] < rows[i - 1]["turn"])
    return rows[start:]


def decisions(path, first, last):
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # The bounded tail starts in the middle of a JSON record.
        if first <= (row.get("decision_sequence") or 0) <= last:
            kept = {key: row.get(key) for key in DECISION_FIELDS}
            kept["equipment"] = {key: row["equipment_optimization"].get(key)
                                 for key in EQUIPMENT_FIELDS}
            found.append(kept)
    return found


def town_case(name, capture_name, arrival_turn, boards, span):
    capture = ROOT / "incident-captures" / capture_name
    ring = capture / "snapshots" / "snapshots-current.jsonl.gz"
    tail = capture / "decision-tail.jsonl"
    rows = ascending(ring_rows(ring.read_bytes()))
    arrival = next(i for i, row in enumerate(rows)
                   if row["turn"] >= arrival_turn and row["type"] == "player_turn")
    named = {}
    for board, (turn, kind, occurrence) in boards.items():
        matches = [row for row in rows if row["turn"] == turn and row["type"] == kind]
        named[board] = matches[occurrence]
    stop = named["stop"]
    policy_state = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
    recorded = policy_state["state"]
    return dict(
        # The capture's policy state at the stop: the staff sequence's record
        # (the absorbed Identify staff) and the failed transaction items.
        state={key: recorded[key] for key in STATE_KEYS},
        modes={key: policy_state["modes_and_latches"][key] for key in MODE_KEYS},
        id=f"{name}/{capture_name}",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ring, tail)},
        arrival=rows[arrival],
        observations=[row for row in rows[arrival + 1:] if row["type"] in (
            "store", "knowledge", "character") and row["turn"] <= stop["turn"]],
        boards=named,
        store_cells=[[c["y"], c["x"], c["s"]] for c in stop["grid_map"]["cells"] if "s" in c],
        decisions=decisions(tail, *span),
        # The forced departure's record of this stop (policy_town
        # _record_visit_departure, jsonlog/keep-running-events.jsonl).
        keep_running=[row for row in map(json.loads, (ROOT / "keep-running-events.jsonl")
                                         .read_text(encoding="utf-8").splitlines())
                      if arrival_turn <= row["turn"] <= stop["turn"]],
    )


def stuck_case():
    with gzip.open(STUCK / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        states = [json.loads(line) for line in stream if line.strip()]
    with gzip.open(STUCK / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
        control = json.load(stream)
    stderr = (STUCK / "bot-stderr.log").read_text(encoding="utf-8", errors="replace")
    return dict(
        id=f"stuck/{STUCK.name}",
        # The last dungeon board (the failed wand use) and the town board the
        # recall produced before the executor read the next screen.
        dungeon=states[-2], town=states[-1],
        stop_screen=control["screen"],
        stuck_line=next(line for line in stderr.splitlines() if line.startswith("<stuck-prompt>")),
    )


def main():
    cases = [town_case(*case) for case in CASES]
    cases.append(stuck_case())
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)
    for case in cases[:2]:
        print(case["id"], len(case["observations"]), "observations",
              {name: row["turn"] for name, row in case["boards"].items()})


if __name__ == "__main__":
    main()
