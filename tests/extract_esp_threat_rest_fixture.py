"""Freeze the 41F detected-threat rest loop at recorded decision boundaries.

The capture covers the whole bot-process lifetime (627 decisions, 2026-09-21
22:45:39-22:48:39).  Emitter rows are not decisions: each decision's input ends
where the previous decision's ``timing.jsonl_drain_records`` says, and every
decision's input row must carry the decision record's turn.  The capture's
final ``loop-detected`` record repeats decision 627's sequence and is the stop
report, not a decision; it is excluded.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "incident-captures" / "20260921-224839-loop-detected"
OUTPUT = ROOT / "tests" / "fixtures" / "esp-threat-rest-20260921.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
# The live process rewrote jsonlog/character-calibration.json during this run
# (22:47:43, decision 476), so the file it loaded at start is gone.  The last
# preserved pre-run content is the 19:33 run's frozen copy; its fields equal
# the rewritten file's except observed_turn.
CALIBRATION_SOURCE = (
    ROOT / "tests" / "fixtures"
    / "recall-stockout-set-end-20260921.character-calibration.json"
)
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "esp-threat-rest-20260921.character-calibration.json"
)


def _decision_rows() -> list[dict]:
    rows = []
    for line in (CAPTURE / "decision-tail.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            row.get("decision_sequence")
            and row.get("time", "")[11:19] >= "22:45:00"
            and row.get("reason") != "loop-detected"
        ):
            rows.append(row)
    return rows


def _snapshot_rows() -> list[tuple[dict, bytes]]:
    raw = (CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()
    # Recover complete members even if the retained suffix began mid-member.
    offset = raw.find(b"\x1f\x8b\x08")
    if offset < 0:
        raise RuntimeError("capture contains no intact gzip member")
    decoded = gzip.GzipFile(fileobj=io.BytesIO(raw[offset:])).read()
    rows = []
    for line in decoded.splitlines(keepends=True):
        try:
            rows.append((json.loads(line), line))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return rows


def _input_ends(decisions: list[dict], rows: list[tuple[dict, bytes]]) -> list[int]:
    """Walk back from the final row: last decision's input is the last row."""
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    ends = [len(rows) - 1]
    for index in range(len(decisions) - 1, 0, -1):
        # Decision 1's own drain predates the retained rows: clamp at row 0.
        end = max(0, ends[-1] - drains[index - 1])
        while end > 0 and rows[end][0].get("turn") != decisions[index - 1]["turn"]:
            end -= 1
        ends.append(end)
    ends.reverse()
    for decision, end in zip(decisions, ends):
        if rows[end][0].get("turn") != decision["turn"]:
            raise RuntimeError(f"turn mismatch at decision {decision['decision_sequence']}")
    return ends


def main() -> None:
    decisions = _decision_rows()
    if [row["decision_sequence"] for row in decisions] != list(
        range(1, len(decisions) + 1)
    ):
        raise RuntimeError("decision sequence is not the whole process lifetime")
    rows = _snapshot_rows()
    ends = _input_ends(decisions, rows)
    first = ends[0]
    selected = [line for _row, line in rows[first:]]
    counts = [1] + [ends[i] - ends[i - 1] for i in range(1, len(ends))]
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    uncounted = [
        decisions[i]["decision_sequence"]
        for i in range(1, len(decisions))
        if counts[i] != drains[i - 1]
    ]
    payload = b"".join(selected)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    BOUNDARIES.write_text(
        json.dumps(
            {
                "decision_count": len(decisions),
                "input_rows": counts,
                "uncounted_row_decisions": uncounted,
                "recorded": [
                    [row["key"], row["reason"]] for row in decisions
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    # LF bytes: git normalizes committed text and the tests hash the bytes.
    CALIBRATION.write_bytes(
        CALIBRATION_SOURCE.read_bytes().replace(b"\r\n", b"\n")
    )
    PROVENANCE.write_text(
        "Source: incident-captures/20260921-224839-loop-detected/\n"
        "Selection: every decision of the bot process started 2026-09-21 "
        "22:45:39+09:00 (sequence 1..627; the loop-detected stop record is "
        "excluded).\n"
        "Boundary rule: walking back from the final emitter row, each "
        "decision's input ends drain(previous decision) rows earlier; when that "
        "row's turn differs from the decision record's turn the boundary moves "
        f"back to the matching row (decisions {uncounted}).\n"
        f"Decisions: {len(decisions)}; emitter rows: {len(selected)} of "
        f"{len(rows)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        "Calibration: the live file was rewritten mid-run (22:47:43); the "
        "fixture is the last preserved pre-run content "
        "(recall-stockout-set-end-20260921.character-calibration.json, fields "
        "equal to the rewritten file except observed_turn) sha256 "
        f"{hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
