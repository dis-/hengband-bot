"""Freeze the 2026-09-25 10:11-10:22 bot process at recorded decision boundaries.

The capture is jsonlog/incident-20260925-1022-overweight-home-unreachable.*
(copies of the live logs taken right after the stop) plus the automatic
capture incident-captures/20260925-102213-town-blocked-overweight-home-
unreachable.  The bot process was started at 10:11:24 onto the game that had
been left running since the 06:23 stop, so the state log also holds the rows
of the earlier processes.  This process read nothing before its attach board:
the CLI reads the state log's last row as its initial snapshot and then seeks
to the end.

The decision log rotated at 10:19:52 during the process: its decisions
0..3239 (sequence 0..3239) are the tail of jsonlog/bot-decisions.jsonl.1 (the
rotated generation, from the sequence-0 row written at 10:11:24), and its
decisions 3240..3780 are the capture's decision-tail.jsonl (the live
generation, byte-identical to jsonlog/bot-decisions.jsonl after the stop).

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn.  The walk starts from the last row carrying the last
decision's turn and validates for every logged decision; decision 0's input is
the attach row alone (the last row the 06:23 process left behind).
Decisions are addressed by their index in the log, never by
``decision_sequence``: the first town decision after a landing reuses the
countdown's last sequence (3695 twice, for example).

Frozen window: the whole process.  It holds the town visit from the recall
landing (sequence 3695) to the ``town:blocked:overweight-home-unreachable``
stop (sequence 3780).

The live process loaded jsonlog/character-calibration.json.  No decision of
the 06:15 or the 10:11 process before sequence 3755 wrote it (neither ran
``calibration:request-naked-character`` earlier), so the loaded bytes are the
ones frozen as tests/fixtures/guardian-recall-pingpong-20260925.character-
calibration.json (last written 2026-09-24 05:24); the file the stop left
behind differs from them only by the ``observed_turn`` the 3755 calibration
wrote.  This tool checks that.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE = next(
    candidate
    for candidate in (ROOT / "jsonlog", Path("C:/hengband/bot-client/jsonlog"))
    if (
        candidate / "incident-20260925-1022-overweight-home-unreachable.state.jsonl.gz"
    ).is_file()
)
CAPTURE_NAME = "incident-20260925-1022-overweight-home-unreachable"
STATE = LIVE / f"{CAPTURE_NAME}.state.jsonl.gz"
ROTATED_DECISIONS = LIVE / "bot-decisions.jsonl.1"
AUTOMATIC = LIVE.parent / "incident-captures" / (
    "20260925-102213-town-blocked-overweight-home-unreachable"
)
TAIL_DECISIONS = AUTOMATIC / "decision-tail.jsonl"
CALIBRATION_SOURCE = LIVE / "character-calibration.json"
OUTPUT = ROOT / "tests" / "fixtures" / "overweight-home-unreachable-20260925.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "guardian-recall-pingpong-20260925.character-calibration.json"
)
PROCESS_START = "2026-09-25T10:11:24+0900"
RECORDED_FIELDS = [
    "decision_sequence",
    "key",
    "reason",
    "y",
    "x",
    "dungeon_id",
    "level",
    "store_type",
    "inventory_used",
    "home_approach_fails",
    "home_visit_limit",
    "home_unsatisfied_passes",
    "home_blocked",
    "outstanding_equipment_work",
]


def _decision_rows() -> list[dict]:
    rows = []
    started = False
    with ROTATED_DECISIONS.open("rb") as stream:
        for line in stream:
            row = json.loads(line)
            if "decision_sequence" not in row:
                continue
            if row["decision_sequence"] == 0 and row["time"] == PROCESS_START:
                started = True
            if started:
                rows.append(row)
    if not rows:
        raise RuntimeError("the 10:11 process start is not in the rotated log")
    tail = [
        json.loads(line)
        for line in TAIL_DECISIONS.read_text(encoding="utf-8").splitlines()
    ]
    if tail[0]["decision_sequence"] != rows[-1]["decision_sequence"] + 1:
        raise RuntimeError("the rotated and live decision logs do not join")
    rows.extend(row for row in tail if "decision_sequence" in row)
    return rows


def _input_ends(decisions: list[dict], rows: list[dict]) -> list[int]:
    """Walk back from the last row carrying the last decision's turn."""
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    last = len(rows) - 1
    while rows[last].get("turn") != decisions[-1]["turn"]:
        last -= 1
    ends = [last]
    for index in range(len(decisions) - 1, 0, -1):
        end = max(0, ends[-1] - drains[index - 1])
        while end > 0 and rows[end].get("turn") != decisions[index - 1]["turn"]:
            end -= 1
        ends.append(end)
    ends.reverse()
    return ends


def _recorded(row: dict) -> list:
    projection = (
        (row.get("equipment_optimization") or {}).get("home_route_projection")
        or {}
    )
    return [
        row["decision_sequence"],
        row["key"],
        row["reason"],
        row["position"]["y"],
        row["position"]["x"],
        row["floor"]["dungeon_id"],
        row["floor"]["level"],
        row.get("store_type"),
        (row.get("inventory") or {}).get("used"),
        projection.get("home_approach_fails"),
        projection.get("home_visit_limit"),
        projection.get("home_unsatisfied_passes"),
        projection.get("home_blocked"),
        projection.get("outstanding_equipment_work"),
    ]


def main() -> None:
    frozen = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    left = json.loads(CALIBRATION_SOURCE.read_text(encoding="utf-8"))
    if {k: v for k, v in frozen.items() if k != "observed_turn"} != {
        k: v for k, v in left.items() if k != "observed_turn"
    }:
        raise RuntimeError("the calibration differs beyond observed_turn")
    decisions = _decision_rows()
    with gzip.open(STATE, "rb") as stream:
        lines = stream.read().splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    ends = _input_ends(decisions, rows)
    mismatched = [
        index
        for index, (decision, end) in enumerate(zip(decisions, ends))
        if rows[end].get("turn") != decision["turn"]
    ]
    if mismatched:
        raise RuntimeError(f"unexpected boundary mismatches {mismatched[:20]}")
    attach = ends[0]
    counts = [1] + [ends[i] - ends[i - 1] for i in range(1, len(decisions))]
    if min(counts) < 1:
        raise RuntimeError("a decision reads no row")
    selected = lines[attach : ends[-1] + 1]
    payload = b"".join(selected)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    BOUNDARIES.write_text(
        json.dumps(
            {
                "decision_count": len(decisions),
                "input_rows": counts,
                "recorded_fields": RECORDED_FIELDS,
                "recorded": [_recorded(row) for row in decisions],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    first, last = decisions[0], decisions[-1]
    PROVENANCE.write_text(
        f"Source: jsonlog/{CAPTURE_NAME}.state.jsonl.gz (copy of the live "
        "state log taken at the 10:22 stop); decisions: jsonlog/bot-decisions."
        "jsonl.1 (rotated 10:19:52) from the 10:11:24 sequence-0 row, joined "
        "with incident-captures/20260925-102213-town-blocked-overweight-home-"
        "unreachable/decision-tail.jsonl.\n"
        f"state.jsonl.gz sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decision-tail.jsonl sha256 "
        f"{hashlib.sha256(TAIL_DECISIONS.read_bytes()).hexdigest()}\n"
        f"Selection: the whole 10:11:24 process, decisions 0..{len(decisions) - 1} "
        f"by log index ({first['time']} - {last['time']}, turn "
        f"{first['turn']}-{last['turn']}).\n"
        "Boundary rule: walking back from the last emitter row that carries "
        "the last decision's turn, each decision's input ends "
        "drain(previous decision) rows earlier and must carry the decision "
        f"record's turn; the walk validates for all {len(decisions)} logged "
        f"decisions.  Decision 0 reads the attach row alone (state log row "
        f"{attach}).\n"
        f"Emitter rows: {len(selected)} of {len(lines)} (rows {attach}.."
        f"{ends[-1]}); decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        "Calibration: jsonlog/character-calibration.json as loaded by the "
        "process (unwritten by either process before sequence 3755), equal "
        "to tests/fixtures/guardian-recall-pingpong-20260925.character-"
        "calibration.json but for the observed_turn the 3755 calibration "
        "wrote, sha256 "
        f"{hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    print(BOUNDARIES.name, hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest())
    print("decisions", len(decisions), "rows", len(selected), "attach", attach)


if __name__ == "__main__":
    main()
