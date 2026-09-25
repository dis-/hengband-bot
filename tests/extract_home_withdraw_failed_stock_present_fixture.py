"""Freeze the 2026-09-25 17:29-17:30 Home withdrawal stop at recorded boundaries.

The capture is jsonlog/incident-20260925-1730-home-withdraw-failed-stock-
present.* (copies of the live logs taken after the stop) plus the automatic
capture incident-captures/20260925-173037-town-blocked-home-withdraw-failed-
stock-present.  The decision copy starts at 14:21 and so also holds the
earlier processes; the bot process of the incident was started at 17:29:14
(``-Action resume``) onto a game waiting on its Home page, and its decisions
are the 66 rows from the sequence-0 row written at 17:29:20 to the stop,
sequence 65 ``town:blocked:home-withdraw-failed-stock-present`` (17:30:37).
The automatic capture's decision tail ends with the same rows.

Boards: each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, walking back from the last state row
carrying the last decision's turn; the walk validates (every boundary row
carries the decision record's turn) for all 66 decisions.  Decision 0 reads
the attach pair the resume bound (14fe7a19): the player_turn row and the
pre-attach Home store row the game wrote before the reader attached.

What is frozen: the input rows of decisions 0..33 (the first 33 decisions
lead to the stop's first step: decision 33 deferred the just-taken Treasure
Detection scroll and 36/47 the queued shovel), and the recorded facts of all
66 decisions.  The calibration file is the one the 14:22 process wrote at
14:23:36; nothing wrote it since, and it equals tests/fixtures/recall-read-
cancel-pingpong-20260925.character-calibration.json (checked here).

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "incident-20260925-1730-home-withdraw-failed-stock-present"
LIVE = next(
    candidate
    for candidate in (ROOT / "jsonlog", Path("C:/hengband/bot-client/jsonlog"))
    if (candidate / f"{CAPTURE_NAME}.state.jsonl.gz").is_file()
)
STATE = LIVE / f"{CAPTURE_NAME}.state.jsonl.gz"
DECISIONS = LIVE / f"{CAPTURE_NAME}.decisions.jsonl.gz"
CALIBRATION_SOURCE = LIVE / "character-calibration.json"
AUTOMATIC = LIVE.parent / "incident-captures" / (
    "20260925-173037-town-blocked-home-withdraw-failed-stock-present"
)
TAIL_DECISIONS = AUTOMATIC / "decision-tail.jsonl"
OUTPUT = ROOT / "tests" / "fixtures" / (
    "home-withdraw-failed-stock-present-20260925.jsonl.gz"
)
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "recall-read-cancel-pingpong-20260925.character-calibration.json"
)
PROCESS_START = "2026-09-25T17:29:20+0900"
REPLAYED = 34  # decisions 0..33
RECORDED_FIELDS = [
    "decision_sequence",
    "turn",
    "key",
    "reason",
    "y",
    "x",
    "store_type",
    "inventory_used",
    "messages",
    "withdraw_selected_signature",
    "withdraw_selecting_branch",
    "withdraw_resolved_index",
    "withdraw_resolved_letter",
    "deferred_home_item_signatures",
    "home_scan_item_count",
    "home_gate_branch",
    "home_gate_deferred_matches",
    "home_gate_deferred_retry",
]


def _decisions() -> list[dict]:
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        raw = [json.loads(line) for line in stream]
    start = max(
        index
        for index, row in enumerate(raw)
        if row.get("decision_sequence") == 0 and row.get("time") == PROCESS_START
    )
    decisions = raw[start:]
    if any("decision_sequence" not in row for row in decisions):
        raise RuntimeError("a non-decision row inside the 17:29 process")
    if [row["decision_sequence"] for row in decisions] != list(range(66)):
        raise RuntimeError("the 17:29 process is not sequences 0..65")
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
    atomic = row.get("home_atomic_withdraw") or {}
    gate = row.get("home_gate") or {}
    optimization = row.get("equipment_optimization") or {}
    return [
        row["decision_sequence"],
        row["turn"],
        row["key"],
        row["reason"],
        row["position"]["y"],
        row["position"]["x"],
        row.get("store_type"),
        (row.get("inventory") or {}).get("used"),
        row.get("messages") or [],
        atomic.get("selected_signature"),
        atomic.get("selecting_branch"),
        atomic.get("resolved_index"),
        atomic.get("resolved_letter"),
        optimization.get("deferred_home_item_signatures"),
        (row.get("home_scan") or {}).get("item_count"),
        gate.get("branch"),
        gate.get("deferred_matches"),
        gate.get("deferred_retry"),
    ]


def main() -> None:
    source_calibration = CALIBRATION_SOURCE.read_bytes()
    if json.loads(source_calibration) != json.loads(CALIBRATION.read_bytes()):
        raise RuntimeError("the loaded calibration differs from the frozen one")
    decisions = _decisions()
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
        raise RuntimeError(f"unexpected boundary mismatches {mismatched}")
    attach = ends[0] - 1
    if (rows[attach].get("type"), rows[ends[0]].get("type")) != (
        "player_turn", "store",
    ) or rows[ends[0]]["store"]["store_type"] != 7:
        raise RuntimeError("decision 0 does not read the Home attach pair")
    counts = [ends[0] - attach + 1] + [
        ends[index] - ends[index - 1] for index in range(1, REPLAYED)
    ]
    if min(counts) < 1:
        raise RuntimeError("a decision reads no row")
    selected = lines[attach : ends[REPLAYED - 1] + 1]
    payload = b"".join(selected)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    BOUNDARIES.write_text(
        json.dumps(
            {
                "replayed_decisions": REPLAYED,
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
    PROVENANCE.write_text(
        f"Source: jsonlog/{CAPTURE_NAME}.state.jsonl.gz and .decisions.jsonl.gz "
        "(copies of the live logs taken after the 17:30 stop); the automatic "
        "capture incident-captures/20260925-173037-town-blocked-home-withdraw-"
        "failed-stock-present/decision-tail.jsonl ends with the same row.\n"
        f"state.jsonl.gz sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decisions.jsonl.gz sha256 "
        f"{hashlib.sha256(DECISIONS.read_bytes()).hexdigest()}; "
        f"decision-tail.jsonl sha256 "
        f"{hashlib.sha256(TAIL_DECISIONS.read_bytes()).hexdigest()}\n"
        f"Process: the {PROCESS_START} sequence-0 row to sequence 65 "
        f"(turn {decisions[0]['turn']}-{decisions[-1]['turn']}); the boundary "
        "walk validates for all 66 decisions.\n"
        f"Frozen input rows: decisions 0..{REPLAYED - 1}, state rows "
        f"{attach}..{ends[REPLAYED - 1]} ({len(selected)} emitter rows; "
        f"decision 0 reads the attach pair {attach}, {ends[0]}); decompressed "
        f"sha256 {hashlib.sha256(payload).hexdigest()}.\n"
        "Recorded facts: all 66 decisions.\n"
        "Calibration: jsonlog/character-calibration.json as the 14:22 process "
        "wrote it at 14:23:36 (unwritten since), equal to tests/fixtures/"
        "recall-read-cancel-pingpong-20260925.character-calibration.json; "
        f"source sha256 {hashlib.sha256(source_calibration).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    print(BOUNDARIES.name, hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest())
    print("rows", len(selected), "attach", attach)


if __name__ == "__main__":
    main()
