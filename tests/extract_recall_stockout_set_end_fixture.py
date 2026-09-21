"""Freeze the 19:33-19:38 stockout/set-end incident at recorded decision boundaries.

The capture covers the whole bot-process lifetime (1431 decisions).  Emitter
rows are not decisions: each decision's input ends where the previous
decision's ``timing.jsonl_drain_records`` says, and every decision's input row
must carry the decision record's turn.  Four emitter rows were drained outside
an active operation (uncounted); the walk carries each into the following
decision's input, which the turn check proves.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "incident-captures" / "20260921-193842-town-blocked-owner-retired"
OUTPUT = ROOT / "tests" / "fixtures" / "recall-stockout-set-end-20260921.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
# The live process loaded this file at start; its mtime (17:08) predates the run.
CALIBRATION_SOURCE = ROOT / "jsonlog" / "character-calibration.json"
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "recall-stockout-set-end-20260921.character-calibration.json"
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
        if row.get("decision_sequence") and row.get("time", "")[11:19] >= "19:33:00":
            rows.append(row)
    return rows


def _snapshot_rows() -> list[tuple[dict, bytes]]:
    raw = (CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()
    # The automatic cap retained a suffix beginning inside an older member.
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
        end = ends[-1] - drains[index - 1]
        while rows[end][0].get("turn") != decisions[index - 1]["turn"]:
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
    )
    shutil.copyfile(CALIBRATION_SOURCE, CALIBRATION)
    PROVENANCE.write_text(
        "Source: incident-captures/20260921-193842-town-blocked-owner-retired/\n"
        "Selection: every decision of the bot process started 2026-09-21 "
        "19:33:56+09:00 (sequence 1..1431).\n"
        "Boundary rule: walking back from the final emitter row, each "
        "decision's input ends drain(previous decision) rows earlier; when that "
        "row's turn differs from the decision record's turn the boundary moves "
        f"back to the matching row (decisions {uncounted} received one row "
        "drained outside an active operation).\n"
        f"Decisions: {len(decisions)}; emitter rows: {len(selected)}; "
        f"decompressed sha256: {hashlib.sha256(payload).hexdigest()}\n"
        "Calibration: jsonlog/character-calibration.json (mtime 2026-09-21 "
        "17:08, before the run) sha256 "
        f"{hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
