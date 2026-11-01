"""Freeze the recorded town boards of the town defined end (2026-11-02).

Owner 2026-11-02 「決まった終わり方だけにする」: a town board on which no
owner answers ends by departure or a named stop, never by the dungeon wander
fallbacks.  Only this tool reads the captures (copied read-only):

- C:/hengband-backups/pdca/captures/n1c-home-loop-1101: the n1-c life-098
  Outpost visit of 23:49:17- (Magic-Eater Lv26, the D61 build), whose
  home:route-claim-unfulfilled / boxed-breakout-travel / breakout:least-
  visited loop ran once a second until the 23:51 loop-detected stop.
  snapshots/snapshots-20261101-235057-f7ceaf.jsonl.gz is the jsonlog ring
  (arrival turn 2138131), bot-decisions-tail.jsonl.gz the decision log, and
  life-098/.../20261101-220445-loop-detected/policy-state.json the life's
  staff sequence record (22:04).

- C:/hengband-backups/pdca/captures/n1b-1031-2323/life-283/captures/
  20261031-233452-town-blocked-owner-retired-burst: the n1-b life-283
  Outpost stop of 23:34:48 (a new warrior waiting for the General Store's
  restock, turn 105377).  state.jsonl.gz is the bot's snapshot tail (its
  last row is the stop board), bot-decisions.jsonl.gz the decision log and
  bot-stderr.log the three owner-retired-log-only rows.

Frozen per case: the arrival board, every store/knowledge/character row of
the visit up to the named board (the boundary consumes those; later shop
pages answer the replayed entries), the named board, the store entrances,
the last ~9 Home answer before the board and the recorded decision facts.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


CAPTURES = Path("C:/hengband-backups/pdca/captures")
FIXTURES = Path(__file__).with_name("fixtures")
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position",
                   "home_candidate_waiting", "identification_need", "departure_block",
                   "store_type")


def _decision_rows(path: Path, span: tuple[int, int]) -> list[dict]:
    found = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if span[0] <= (row.get("decision_sequence") or 0) <= span[1]:
                found.append({key: row.get(key) for key in DECISION_FIELDS})
    return found


def home_loop_2350() -> None:
    root = CAPTURES / "n1c-home-loop-1101"
    ring = root / "snapshots" / "snapshots-20261101-235057-f7ceaf.jsonl.gz"
    decisions = root / "bot-decisions-tail.jsonl.gz"
    policy_state = (root / "life-098" / "20261101-220445-loop-detected"
                    / "policy-state.json")
    arrival_turn = 2138131
    # Outside Home after the fourth home:route-claim-unfulfilled exit
    # (decision 26098); decision 26099 chose breakout:least-visited on it.
    board_turn = 2143614
    rows = ring_rows(ring.read_bytes())
    arrival = next(i for i, row in enumerate(rows)
                   if row["turn"] >= arrival_turn and row["type"] == "player_turn")
    board = [row for row in rows if row["turn"] == board_turn
             and row["type"] == "player_turn"][-1]
    visit = rows[arrival + 1:]
    home_answer = [row for row in visit if row["type"] == "knowledge"
                   and row["knowledge"]["category"] == "home"
                   and row["turn"] <= board_turn][-1]
    state = json.loads(policy_state.read_text(encoding="utf-8"))
    case = dict(
        id="n1c/life-098/20261101-2349-outpost",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (ring, decisions, policy_state)},
        arrival=rows[arrival],
        observations=[row for row in visit
                      if row["type"] in ("store", "knowledge", "character")],
        boards={"left-home": board},
        home_answer=home_answer,
        store_cells=[[c["y"], c["x"], c["s"]] for c in board["grid_map"]["cells"]
                     if "s" in c],
        decisions=_decision_rows(decisions, (26086, 26101)),
        me_staff_sequence=state["state"]["_me_staff_sequence"],
    )
    output = FIXTURES / "town-defined-end-home-loop-2350.json.gz"
    with gzip.open(output, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(output, output.stat().st_size, len(case["observations"]), "observations",
          len(case["decisions"]), "decisions")


def retired_burst_2334() -> None:
    root = (CAPTURES / "n1b-1031-2323" / "life-283" / "captures"
            / "20261031-233452-town-blocked-owner-retired-burst")
    state = root / "state.jsonl.gz"
    decisions = root / "bot-decisions.jsonl.gz"
    with gzip.open(state, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    board = rows[-1]
    assert board["turn"] == 105377, board["turn"]
    case = dict(
        id="n1b/life-283/20261031-2334-outpost",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (state, decisions)},
        board=board,
        decisions=_decision_rows(decisions, (1222, 1226)),
        retirements=[line for line in (root / "bot-stderr.log").read_text(
            encoding="utf-8", errors="replace").splitlines()
            if line.startswith("<owner-retired-log-only>")],
    )
    output = FIXTURES / "town-defined-end-retired-burst-2334.json.gz"
    with gzip.open(output, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(output, output.stat().st_size, len(case["decisions"]), "decisions")


if __name__ == "__main__":
    home_loop_2350()
    retired_burst_2334()
