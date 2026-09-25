"""Freeze the 2026-09-25 20:38-20:41 town visit at recorded decision boundaries.

The capture is jsonlog/incident-20260925-2041-morivant-return-walks-away.*
(copies of the live logs taken after the stop) plus the automatic capture
incident-captures/20260925-204146-town-blocked-owner-retired.  The bot process
was resumed at 19:39, but the decision copy starts at 20:15:34 (sequence 10083,
6,660 rows) and the state copy at turn 5677481: the process's beginning is not
in the capture, so its lifetime cannot be replayed.

What can be replayed is the routing terrain.  Decision index 6441 (sequence
16522, the second row of that sequence, 20:38:26) is the first board after the
Word of Recall landing in the Outpost (floor (12, 33, 0) -> (0, 0, 0)); that
floor change reset every remembered terrain set, so from there the terrain the
router holds is built from the boards alone.  The window is the landing through
the stop: decisions 6441..6659 (sequence 16522..16740), i.e. the Outpost errands,
the *Identify* walk to the Outpost Inn (16677..16711, '3mc' teleports to
Morivant), the Morivant errands (16712..16730), the return walk
``town:morivant-full-identify:return`` (16731..16739) and the stop
``town:blocked:owner-retired`` (16740).

Boards: each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, walking back from the last state row
carrying the last decision's turn; the walk validates (every boundary row
carries the decision record's turn) for every decision of the window.  Decision
6441's input starts at the first surface row (state row 9903, the landing).

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "incident-20260925-2041-morivant-return-walks-away"
LIVE = next(
    candidate
    for candidate in (ROOT / "jsonlog", Path("C:/hengband/bot-client/jsonlog"))
    if (candidate / f"{CAPTURE_NAME}.state.jsonl.gz").is_file()
)
STATE = LIVE / f"{CAPTURE_NAME}.state.jsonl.gz"
DECISIONS = LIVE / f"{CAPTURE_NAME}.decisions.jsonl.gz"
AUTOMATIC = LIVE.parent / "incident-captures" / (
    "20260925-204146-town-blocked-owner-retired"
)
TAIL_DECISIONS = AUTOMATIC / "decision-tail.jsonl"
OUTPUT = ROOT / "tests" / "fixtures" / "morivant-return-walks-away-20260925.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
FIRST_INDEX = 6441  # sequence 16522, the first board after the landing
FIRST_ROW = 9903  # the first surface row of the state copy after the landing
RECORDED_FIELDS = [
    "decision_sequence",
    "turn",
    "key",
    "reason",
    "y",
    "x",
    "dungeon_id",
    "level",
    "producer_owner",
    "progress",
    "budget_remaining_estimate",
    "retired",
    "retirement_set",
    "claim_id",
    "claim_owner",
    "claim_goal",
    "claim_distance",
    "known_cells",
    "down_stairs",
]


def _decisions() -> list[dict]:
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        decisions = [json.loads(line) for line in stream]
    if any("decision_sequence" not in row for row in decisions):
        raise RuntimeError("a non-decision row in the decision copy")
    tail_lines = TAIL_DECISIONS.read_text(encoding="utf-8").splitlines()
    if json.loads(tail_lines[-1]) != decisions[-1]:
        raise RuntimeError("the automatic capture tail differs from the copy")
    return decisions


def _input_ends(decisions: list[dict], rows: list[dict]) -> list[int]:
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    last = len(rows) - 1
    while rows[last].get("turn") != decisions[-1]["turn"]:
        last -= 1
    ends = [last]
    for index in range(len(decisions) - 1, 0, -1):
        ends.append(ends[-1] - drains[index - 1])
    ends.reverse()
    return ends


def _recorded(row: dict) -> list:
    arbiter = row.get("arbiter") or {}
    claim = row.get("claim") or {}
    goal = claim.get("goal") or {}
    memory = row.get("map_memory") or {}
    return [
        row["decision_sequence"],
        row["turn"],
        row["key"],
        row["reason"],
        row["position"]["y"],
        row["position"]["x"],
        row["floor"]["dungeon_id"],
        row["floor"]["level"],
        arbiter.get("producer_owner"),
        arbiter.get("progress"),
        arbiter.get("budget_remaining_estimate"),
        arbiter.get("retired"),
        arbiter.get("retirement_set"),
        claim.get("claim_id"),
        claim.get("owner"),
        goal.get("cell") if goal.get("kind") == "Reach" else None,
        claim.get("distance"),
        (memory.get("known_cells") or {}).get("known"),
        memory.get("down_stairs"),
    ]


def main() -> None:
    decisions = _decisions()
    with gzip.open(STATE, "rb") as stream:
        lines = stream.read().splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    ends = _input_ends(decisions, rows)
    window = decisions[FIRST_INDEX:]
    window_ends = ends[FIRST_INDEX:]
    mismatched = [
        FIRST_INDEX + index
        for index, (decision, end) in enumerate(zip(window, window_ends))
        if rows[end].get("turn") != decision["turn"]
    ]
    if mismatched:
        raise RuntimeError(f"unexpected boundary mismatches {mismatched}")
    landing = rows[FIRST_ROW - 1]["floor"], rows[FIRST_ROW]["floor"]
    if (landing[0]["level"], landing[1]["level"], landing[1]["dungeon_id"]) != (33, 0, 0):
        raise RuntimeError("the window does not start at the landing row")
    if any(row["floor"]["level"] != 0 for row in rows[FIRST_ROW : window_ends[-1] + 1]):
        raise RuntimeError("a non-surface row inside the window")
    if (window[0]["decision_sequence"], window[0]["reason"]) != (
        16522, "periodic:skill-exp-knowledge"
    ) or window[-1]["reason"] != "town:blocked:owner-retired":
        raise RuntimeError("the window is not the landing through the stop")
    counts = [window_ends[0] - FIRST_ROW + 1] + [
        window_ends[index] - window_ends[index - 1]
        for index in range(1, len(window))
    ]
    if min(counts) < 1:
        raise RuntimeError("a decision reads no row")
    selected = lines[FIRST_ROW : window_ends[-1] + 1]
    payload = b"".join(selected)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    BOUNDARIES.write_text(
        json.dumps(
            {
                "first_decision_index": FIRST_INDEX,
                "input_rows": counts,
                "recorded_fields": RECORDED_FIELDS,
                "recorded": [_recorded(row) for row in window],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    PROVENANCE.write_text(
        f"Source: jsonlog/{CAPTURE_NAME}.state.jsonl.gz and .decisions.jsonl.gz "
        "(copies of the live logs taken after the 20:41 stop); the automatic "
        "capture incident-captures/20260925-204146-town-blocked-owner-retired/"
        "decision-tail.jsonl ends with the same row.\n"
        f"state.jsonl.gz sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decisions.jsonl.gz sha256 "
        f"{hashlib.sha256(DECISIONS.read_bytes()).hexdigest()}; "
        f"decision-tail.jsonl sha256 "
        f"{hashlib.sha256(TAIL_DECISIONS.read_bytes()).hexdigest()}\n"
        f"Window: decision indices {FIRST_INDEX}..{len(decisions) - 1} "
        f"(sequence {window[0]['decision_sequence']}..{window[-1]['decision_sequence']}, "
        f"turn {window[0]['turn']}-{window[-1]['turn']}), from the first surface "
        "row after the Word of Recall landing to the stop; the boundary walk "
        f"validates for all {len(window)} decisions.\n"
        f"Frozen rows: state rows {FIRST_ROW}..{window_ends[-1]} "
        f"({len(selected)} emitter rows); decompressed sha256 "
        f"{hashlib.sha256(payload).hexdigest()}.\n"
        f"Recorded facts: all {len(window)} decisions of the window.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    print(BOUNDARIES.name, hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest())
    print("rows", len(selected), "decisions", len(window))


if __name__ == "__main__":
    main()
