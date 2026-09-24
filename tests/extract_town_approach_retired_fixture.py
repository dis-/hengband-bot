"""Freeze the 2026-09-25 06:15-06:23 bot process at recorded decision boundaries.

The capture is a copy of the live logs taken right after the stop
(jsonlog/incident-20260925-0624-town-owner-retired.*).  The bot process was
started at 06:15:50 onto the game that had been left running since the
previous process stopped at 02:01, so the state log also holds that earlier
process's rows (the 01:54 capture incident-20260925-0201-guardian-recall-
pingpong).  This process read nothing before its attach board: the CLI reads
the state log's last row as its initial snapshot and then seeks to the end.

Each decision's input ends where the previous decision's
``timing.jsonl_drain_records`` says, and every boundary row must carry the
decision record's turn.  The walk starts from the last row carrying the last
decision's turn and validates for every logged decision; decision 0's input is
the attach row alone (the state log's row 746, turn 5328134, the last row the
02:01 process left behind).
Decisions are addressed by their index in the log, never by
``decision_sequence``: the first town decision after a landing reuses the
countdown's last sequence (2021 twice, for example).

Frozen window: the whole process, decisions 0..2051 (sequence 0..2047).  It
holds the conquest latch onto the Orc cave (index 1893, sequence 1890), the
recall into its guardian floor (1966, sequence 1963), the
guardian-kit-insufficient return (1991, sequence 1988), the store-7 approach
walk (2036..2050, sequence 2032..2046) and the ``town:blocked:owner-retired``
stop (2051, sequence 2047).

The live process loaded jsonlog/character-calibration.json, last written
2026-09-24 05:24, before both processes; its bytes are the ones already frozen
as tests/fixtures/guardian-recall-pingpong-20260925.character-calibration.json
(checked here by hash).

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NAME = "incident-20260925-0624-town-owner-retired"
CAPTURE = next(
    candidate
    for candidate in (
        ROOT / "jsonlog" / CAPTURE_NAME,
        Path("C:/hengband/bot-client/jsonlog") / CAPTURE_NAME,
    )
    if candidate.with_suffix(".state.jsonl").is_file()
)
STATE = CAPTURE.with_suffix(".state.jsonl")
DECISIONS = CAPTURE.with_suffix(".decisions.jsonl")
CALIBRATION_SOURCE = CAPTURE.parent / "character-calibration.json"
OUTPUT = ROOT / "tests" / "fixtures" / "town-approach-retired-20260925.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "guardian-recall-pingpong-20260925.character-calibration.json"
)
RECORDED_FIELDS = [
    "decision_sequence",
    "key",
    "reason",
    "y",
    "x",
    "dungeon_id",
    "level",
    "producer_owner",
    "progress",
    "budget_remaining_estimate",
    "retirement_set",
    "claim_id",
    "claim_owner",
    "claim_goal",
    "claim_distance",
    "target_dungeon_id",
    "alternate_dungeon_id",
    "over_extended_dive_streak",
    "last_return_trigger",
]


def _decision_rows() -> list[dict]:
    rows = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "decision_sequence" in row:
            rows.append(row)
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
    arbiter = row.get("arbiter") or {}
    claim = row.get("claim") or {}
    goal = claim.get("goal") or {}
    over = row.get("over_extension") or {}
    return [
        row["decision_sequence"],
        row["key"],
        row["reason"],
        row["position"]["y"],
        row["position"]["x"],
        row["floor"]["dungeon_id"],
        row["floor"]["level"],
        arbiter.get("producer_owner"),
        arbiter.get("progress"),
        arbiter.get("budget_remaining_estimate"),
        arbiter.get("retirement_set"),
        claim.get("claim_id"),
        claim.get("owner"),
        goal.get("cell") if goal.get("kind") == "Reach" else None,
        claim.get("distance"),
        over.get("target_dungeon_id"),
        over.get("alternate_dungeon_id"),
        over.get("over_extended_dive_streak"),
        over.get("last_return_trigger"),
    ]


def main() -> None:
    if hashlib.sha256(CALIBRATION_SOURCE.read_bytes().replace(b"\r\n", b"\n")).digest() != (
        hashlib.sha256(CALIBRATION.read_bytes()).digest()
    ):
        raise RuntimeError("the live calibration file is not the frozen one")
    decisions = _decision_rows()
    lines = STATE.read_bytes().splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    ends = _input_ends(decisions, rows)
    mismatched = [
        index
        for index, (decision, end) in enumerate(zip(decisions, ends))
        if rows[end].get("turn") != decision["turn"]
    ]
    if mismatched:
        raise RuntimeError(f"unexpected boundary mismatches {mismatched}")
    attach = ends[0]
    # 746: the 02:01 process's last row, i.e. the state log's last row when
    # this process attached (its guardian-recall-pingpong capture has 747).
    if rows[attach]["turn"] != decisions[0]["turn"] or attach != 746:
        raise RuntimeError("decision 0 does not read the attach row")
    counts = [1] + [ends[i] - ends[i - 1] for i in range(1, len(decisions))]
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
        f"Source: jsonlog/{CAPTURE_NAME}.{{state,decisions}}.jsonl "
        "(copies of the live logs taken at the 06:23 stop).\n"
        f"state.jsonl sha256 {hashlib.sha256(STATE.read_bytes()).hexdigest()}; "
        f"decisions.jsonl sha256 "
        f"{hashlib.sha256(DECISIONS.read_bytes()).hexdigest()}\n"
        f"Selection: the whole 06:15:50 process, decisions 0..{len(decisions) - 1} "
        f"by log index ({first['time']} - {last['time']}, turn "
        f"{first['turn']}-{last['turn']}).\n"
        "Boundary rule: walking back from the last emitter row that carries "
        "the last decision's turn, each decision's input ends "
        "drain(previous decision) rows earlier and must carry the decision "
        f"record's turn; the walk validates for all {len(decisions)} logged "
        f"decisions.  Decision 0 reads the attach row alone (state log row "
        f"{attach}, the last row the 02:01 process left).\n"
        f"Emitter rows: {len(selected)} of {len(lines)} (rows {attach}.."
        f"{ends[-1]}); decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        "Calibration: jsonlog/character-calibration.json as loaded by the "
        "process (last written 2026-09-24 05:24), byte-identical to "
        "tests/fixtures/guardian-recall-pingpong-20260925.character-"
        "calibration.json, sha256 "
        f"{hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(OUTPUT.name, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    print(BOUNDARIES.name, hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
