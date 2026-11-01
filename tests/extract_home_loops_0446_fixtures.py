"""Freeze the 2026-11-02 04:35/04:47 town owner-retired-burst visits.

Sources (copied read-only from the viewing bots to
C:/hengband-backups/pdca/captures/burst-0446-1102/):

- n1-a life-464 (Lv38, bot-3aec0670c), 04:35:28: the Home junk sweep took
  the three empty capture balls one per Home entry and destroyed each
  outside (decisions 3438-3455); the third retirement without credited
  progress stopped the visit as town:blocked:owner-retired-burst.  The
  incident capture's snapshot ring (n1-a-life-464-incident-20261102-043526/
  snapshots/snapshots-current.jsonl.gz) holds the visit and the shop pages
  of the visit before it (the shelf evidence the live plan used); the
  automatic capture holds the decision log.
- n1-b life-291 (Lv26, bot-ff4196953), 04:47:45: a restarted process
  (decision 0 is its first decision) closed both Home passes as
  home:scan-complete-from-open-page / home:route-claim-unfulfilled, opened
  the no-safe-destination fundraising set (decision 8) and stopped at the
  depth gate (decisions 10-18).  The automatic capture's state log holds the
  whole run.

Frozen per case: the town-arrival board, the store pages and knowledge
answers before the named board (the latest page of each store before the
arrival, then every row of the visit), the named board, the store pages
observed after it, the store entrances, the ~9 Home answer of the named
board's Home entry and the recorded decision facts.  Only this
tool reads the captures; the committed test reads the fixtures alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/burst-0446-1102")
FIXTURES = Path(__file__).with_name("fixtures")
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position", "claim",
                   "town_plan", "fundraising", "procurement_requirements", "store_visit",
                   "arbiter", "home_scan", "messages")
JUNK_SWEEP = dict(
    source=ROOT / "n1-a-life-464-incident-20261102-043526" / "snapshots" / "snapshots-current.jsonl.gz",
    log=ROOT / "n1-a-20261102-043528-town-blocked-owner-retired-burst" / "bot-decisions.jsonl.gz",
    output="home-loops-0446-junk-sweep.json.gz",
    # The return from the dungeon (decision 3417) and the board leaving the
    # Temple for Home (decision 3427, shop:travel; the visit's Home entries
    # 3428-3455 follow).
    arrival=(2566862, None), board=(2567963, (31, 77)), span=(3417, 3455),
)
FUNDRAISE_PLAN = dict(
    source=ROOT / "n1-b-20261102-044745-town-blocked-owner-retired-burst" / "state.jsonl.gz",
    log=ROOT / "n1-b-20261102-044745-town-blocked-owner-retired-burst" / "bot-decisions.jsonl.gz",
    output="home-loops-0446-fundraise-plan.json.gz",
    # Decision 0 of the restarted process is the arrival board.
    arrival=(7765525, None), board=(7765525, None), span=(0, 18),
)


def gz_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def board_index(rows, turn, position):
    return next(i for i, row in enumerate(rows)
                if row["type"] == "player_turn" and row["turn"] == turn
                and (position is None
                     or (row["player"]["y"], row["player"]["x"]) == position))


def freeze(source, log, output, arrival, board, span):
    rows = (ring_rows(source.read_bytes()) if "snapshots" in source.parts
            else gz_lines(source))
    decisions = [{key: row.get(key) for key in DECISION_FIELDS} for row in gz_lines(log)
                 if row.get("decision_sequence") is not None
                 and span[0] <= row["decision_sequence"] <= span[1]]
    # A restarted process numbers from 0 again: keep the last run of the span.
    start = max(i for i, row in enumerate(decisions) if row["decision_sequence"] == span[0])
    decisions = decisions[start:]
    first = board_index(rows, *arrival)
    named = board_index(rows, *board)
    earlier = {}
    for row in rows[:first]:
        if row["type"] == "store":
            earlier[row["store"]["store_type"]] = row
    home_answer = next((row for row in rows[named:] if row["type"] == "knowledge"
                        and row["knowledge"]["category"] == "home"), None)
    case = dict(
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (source, log)},
        arrival=rows[first],
        observations=[*sorted(earlier.values(), key=lambda row: row["turn"]),
                      *(row for row in rows[first + 1:named]
                        if row["type"] in ("store", "knowledge"))],
        board=rows[named],
        # The store pages observed from the named board on: the pages the
        # constructed replies serve on a later entry.
        replies=[row for row in rows[named:] if row["type"] == "store"],
        home_answer=home_answer,
        store_cells=[[c["y"], c["x"], c["s"]] for c in rows[named]["grid_map"]["cells"]
                     if "s" in c],
        decisions=decisions,
    )
    with gzip.open(FIXTURES / output, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(output, (FIXTURES / output).stat().st_size, len(case["observations"]),
          "observations", rows[named]["turn"], len(decisions), "decisions")


def main():
    freeze(**JUNK_SWEEP)
    freeze(**FUNDRAISE_PLAN)


if __name__ == "__main__":
    main()
