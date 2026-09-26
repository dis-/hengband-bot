"""Freeze the 2026-09-26 02:51-02:52 bot process at recorded decision boundaries.

Sources (read-only):
- jsonlog/incident-20260926-0252-departure-unsatisfiable-weight.state.jsonl.gz
  and .decisions.jsonl.gz (copies of the live logs taken right after the
  stop; the decision copy holds the whole game since 2026-09-25 20:12,
  including the 01:56 and the 02:51 processes);
- incident-captures/20260926-025228-departure-unsatisfiable/decision-tail.jsonl
  (the automatic capture).

The 02:51:39 process (decision_sequence 0 at 02:51:39) was attached to the
running game while the character waited for the recall out of Orc cave 23F.
It read nothing before its attach board: the CLI reads the state log's last
row as its initial snapshot and then seeks to the end.  Its decisions are
the decision copy's rows from that sequence-0 row to the end; the tool checks
that the last of them equals the capture tail's last row (the
``town:blocked:departure-unsatisfiable`` stop, sequence 115).

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn.  The walk starts from the last row carrying the last
decision's turn and validates for every logged decision; decision 0's input
is the attach row alone (the last row the 01:56 process left behind).

The process loaded jsonlog/character-calibration.json, last written
2026-09-25 20:39 (before either process of this game): the stop left the
loaded bytes behind, frozen as tests/fixtures/departure-unsatisfiable-
weight-20260926.character-calibration.json.

Only this extraction tool reads the capture; the committed test reads the
frozen fixtures alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "incident-20260926-0252-departure-unsatisfiable-weight"
LIVE = next(
    candidate
    for candidate in (ROOT / "jsonlog", Path("C:/hengband/bot-client/jsonlog"))
    if (candidate / f"{CAPTURE_NAME}.state.jsonl.gz").is_file()
)
STATE = LIVE / f"{CAPTURE_NAME}.state.jsonl.gz"
DECISIONS = LIVE / f"{CAPTURE_NAME}.decisions.jsonl.gz"
AUTOMATIC = LIVE.parent / "incident-captures" / (
    "20260926-025228-departure-unsatisfiable"
)
TAIL_DECISIONS = AUTOMATIC / "decision-tail.jsonl"
CALIBRATION_SOURCE = LIVE / "character-calibration.json"
OUTPUT = ROOT / "tests" / "fixtures" / "departure-unsatisfiable-weight-20260926.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "departure-unsatisfiable-weight-20260926.character-calibration.json"
)
PROCESS_START = "2026-09-26T02:51:39+0900"
STOP_SEQUENCE = 115
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
    "departure_failed",
    "need_attempts",
    "home_unsatisfied_passes",
    "home_blocked",
    "messages",
]


def _decision_rows() -> list[dict]:
    rows = []
    started = False
    with gzip.open(DECISIONS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if "decision_sequence" not in row:
                continue
            if row["decision_sequence"] == 0 and row["time"] == PROCESS_START:
                started = True
            if started:
                rows.append(row)
    if not rows:
        raise RuntimeError("the 02:51 process start is not in the decision copy")
    # The capture keeps the last bytes of the log: its first line may be the
    # cut remainder of a row and is not compared.
    tail = [
        json.loads(line)
        for line in TAIL_DECISIONS.read_text(encoding="utf-8").splitlines()[1:]
    ]
    tail = [row for row in tail if "decision_sequence" in row]
    if tail[-1] != rows[-1]:
        raise RuntimeError("the decision copy and the capture tail disagree")
    stop = rows[-1]
    if (stop["decision_sequence"], stop["reason"]) != (
        STOP_SEQUENCE, "town:blocked:departure-unsatisfiable"
    ):
        raise RuntimeError("the last decision is not the recorded stop")
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
    block = row.get("departure_block") or {}
    ledger = block.get("town_ledger") or {}
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
        block.get("failed"),
        ledger.get("need_attempts"),
        projection.get("home_unsatisfied_passes"),
        projection.get("home_blocked"),
        row.get("messages") or [],
    ]


def main() -> None:
    # The live file is written with CRLF; the fixture is stored with LF like
    # every other calibration fixture (JSON content unchanged, checked).
    source = CALIBRATION_SOURCE.read_bytes()
    CALIBRATION.write_bytes(source.replace(b"\r\n", b"\n"))
    if json.loads(CALIBRATION.read_bytes()) != json.loads(source):
        raise RuntimeError("the frozen calibration differs from the loaded one")
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
        f"Source: jsonlog/{CAPTURE_NAME}.state.jsonl.gz and .decisions.jsonl.gz "
        "(copies of the live logs taken at the 02:52 stop); the stop row equals "
        "the last row of incident-captures/20260926-025228-departure-"
        "unsatisfiable/decision-tail.jsonl.\n"
        f"state.jsonl.gz sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decisions.jsonl.gz sha256 "
        f"{hashlib.sha256(DECISIONS.read_bytes()).hexdigest()}; "
        f"decision-tail.jsonl sha256 "
        f"{hashlib.sha256(TAIL_DECISIONS.read_bytes()).hexdigest()}\n"
        f"Selection: the whole 02:51:39 process, decisions 0..{len(decisions) - 1} "
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
        "process (last written 2026-09-25 20:39; CRLF normalized to LF, "
        "JSON-equal), sha256 "
        f"{hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    print(BOUNDARIES.name, hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest())
    print(CALIBRATION.name, hashlib.sha256(CALIBRATION.read_bytes()).hexdigest())
    print("decisions", len(decisions), "rows", len(selected), "attach", attach)


if __name__ == "__main__":
    main()
