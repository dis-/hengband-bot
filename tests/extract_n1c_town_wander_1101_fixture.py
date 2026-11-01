"""Freeze the 2026-11-01 21:01 n1-c life-098 Outpost visit (D61, town stuck:wander).

Source: the viewing Magic-Eater n1-c life-098 (Lv26, build bot-64e63b6cf),
copied read-only to C:/hengband-backups/pdca/captures/n1c-town-wander-1101/:

- snapshots/snapshots-20261101-211825-25901d.jsonl.gz: the jsonlog snapshot
  ring of 20:49:36-21:18:25 (every board, store page, knowledge and
  character answer of the visit that arrived at turn 1579927).
- bot-decisions.1-2047-2110.jsonl.gz: the decision log of 20:47:57-21:10:03
  (decisions 22893-22975 are this visit's arrival, Home passes and wander).
- life-098/incident-captures/20261101-200240-livelock-exhausted/
  policy-state.json: the staff sequence record of this life (20:02).

Frozen: the arrival board, every store/knowledge/character row of the visit
up to the last repeated pass (turn 1584200; the boundary consumes those
before the named board, the replies read the later shop pages), the named
board, the store entrances, the ~9 Home answer and the recorded decision
facts.  Only this tool reads the captures.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-town-wander-1101")
RING = ROOT / "snapshots" / "snapshots-20261101-211825-25901d.jsonl.gz"
DECISIONS = ROOT / "bot-decisions.1-2047-2110.jsonl.gz"
POLICY_STATE = (ROOT / "life-098" / "incident-captures"
                / "20261101-200240-livelock-exhausted" / "policy-state.json")
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-town-wander-1101.json.gz"
ARRIVAL_TURN = 1579927
# (board name, turn, row type, occurrence among the rows of that turn and type)
BOARDS = (
    # Outside Home after the second Home page closed as
    # home:route-claim-unfulfilled (decisions 22938-22939).
    ("left-home", 1581957, "player_turn", -1),
)
DECISION_SPAN = (22893, 22975)
PAGES_UNTIL = 1584200
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position",
                   "home_candidate_waiting", "identification_need", "departure_block",
                   "town_plan", "procurement_requirements", "store_visit", "claim")


def decisions():
    found = []
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if DECISION_SPAN[0] <= (row.get("decision_sequence") or 0) <= DECISION_SPAN[1]:
                found.append({key: row.get(key) for key in DECISION_FIELDS})
    return found


def main():
    rows = ring_rows(RING.read_bytes())
    arrival = next(i for i, row in enumerate(rows)
                   if row["turn"] >= ARRIVAL_TURN and row["type"] == "player_turn")
    named = {}
    for name, turn, kind, occurrence in BOARDS:
        matches = [row for row in rows if row["turn"] == turn and row["type"] == kind]
        named[name] = matches[occurrence]
    # The pages of the repeated passes after the last board (Black Market,
    # Weaponsmith, Alchemist, General Store) answer the replayed entries.
    last = PAGES_UNTIL
    policy_state = json.loads(POLICY_STATE.read_text(encoding="utf-8"))
    home_answer = next(row for row in rows[arrival:] if row["type"] == "knowledge"
                       and row["knowledge"]["category"] == "home")
    case = dict(
        id="life-098/20261101-2101-outpost",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (RING, DECISIONS, POLICY_STATE)},
        arrival=rows[arrival],
        observations=[row for row in rows[arrival + 1:] if row["type"] in (
            "store", "knowledge", "character") and row["turn"] <= last],
        boards=named,
        home_answer=home_answer,
        store_cells=[[c["y"], c["x"], c["s"]] for c in named["left-home"]["grid_map"]["cells"]
                     if "s" in c],
        decisions=decisions(),
        me_staff_sequence=policy_state["state"]["_me_staff_sequence"],
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["observations"]), "observations",
          {name: row["turn"] for name, row in named.items()}, len(case["decisions"]), "decisions")


if __name__ == "__main__":
    main()
