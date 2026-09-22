"""Freeze the 2026-09-22 16:02:57-16:16:04 bot process at recorded boundaries.

The automatic capture (incident-captures/20260922-161604-town-blocked-owner-
retired/) keeps only a 16 MiB snapshot tail and decisions from sequence 2599,
so it cannot seed the process from its start.  The live recorder's current
snapshot generation and the decision log still held the whole lifetime (both
untouched since 16:16:04); this script reads them, verifies their sha256, and
freezes every decision input of that one process (sequence 0..4267; the four
``periodic:skill-exp-knowledge`` probes reuse their neighbour's sequence).

Boundary rule: walking back from the final emitter row, each decision's input
ends ``timing.jsonl_drain_records`` (previous decision) rows earlier; when that
row's turn differs from the decision record's turn the boundary moves back to
the matching row.  Every decision's input row carries the decision's turn.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RING = ROOT / "jsonlog" / "snapshots" / "snapshots-current.jsonl.gz"
RING_SHA256 = "929c927461449c9c45f952124f9a2c3d4631389682b5965e990b18e4995af4bd"
DECISIONS = ROOT / "jsonlog" / "bot-decisions.jsonl"
SESSION_START = "2026-09-22T16:02:57+0900"
FINAL_TURN = 4_410_511
CALIBRATION_SOURCE = ROOT / "jsonlog" / "character-calibration.json"
OUTPUT = ROOT / "tests" / "fixtures" / "unaffordable-claim-tour-20260922.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
CALIBRATION = ROOT / "tests" / "fixtures" / (
    "unaffordable-claim-tour-20260922.character-calibration.json"
)


def _decision_rows() -> list[dict]:
    rows: list[dict] = []
    started = False
    with DECISIONS.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("kind") == "session-start":
                if started:
                    break
                started = row.get("time") == SESSION_START
                continue
            if started and "decision_sequence" in row:
                rows.append(row)
    if not rows or rows[-1]["turn"] != FINAL_TURN:
        raise RuntimeError("decision log does not end at the recorded stop")
    if rows[-1]["reason"] != "town:blocked:owner-retired":
        raise RuntimeError("final decision is not the recorded owner retirement")
    return rows


def _snapshot_rows() -> list[tuple[dict, bytes]]:
    raw = RING.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RING_SHA256:
        raise RuntimeError("live snapshot generation changed since the incident")
    decoded = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    rows = []
    for line in decoded.splitlines(keepends=True):
        try:
            rows.append((json.loads(line), line))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return rows


def _input_ends(decisions: list[dict], rows: list[tuple[dict, bytes]]) -> list[int]:
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
            raise RuntimeError(
                f"turn mismatch at decision {decision['decision_sequence']}"
            )
    return ends


def main() -> None:
    decisions = _decision_rows()
    rows = _snapshot_rows()
    if rows[-1][0].get("turn") != FINAL_TURN:
        raise RuntimeError("snapshot generation does not end at the recorded stop")
    ends = _input_ends(decisions, rows)
    selected = [line for _row, line in rows[ends[0]:]]
    if any(
        row.get("protocol_version") != 3 for row, _line in rows[ends[0]:]
    ):
        raise RuntimeError("expected protocol 3 rows only")
    counts = [1] + [ends[i] - ends[i - 1] for i in range(1, len(ends))]
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records") or 0)
        for row in decisions
    ]
    uncounted = [
        i for i in range(1, len(decisions)) if counts[i] != drains[i - 1]
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
                "recorded": [[row["key"], row["reason"]] for row in decisions],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    CALIBRATION.write_bytes(
        CALIBRATION_SOURCE.read_bytes().replace(b"\r\n", b"\n")
    )
    PROVENANCE.write_text(
        "Source: jsonlog/snapshots/snapshots-current.jsonl.gz (sha256 "
        f"{RING_SHA256}) and jsonlog/bot-decisions.jsonl rows after the "
        f"session-start marker {SESSION_START} (git_commit e89f087).  Backup "
        "copies: C:/hengband-backups/incident-captures/"
        "20260922-161604-town-blocked-owner-retired/lifetime-sources/.\n"
        "Selection: every decision of that bot process (list indices "
        f"0..{len(decisions) - 1}; decision_sequence 0..4267, the four "
        "periodic:skill-exp-knowledge probes share a sequence), protocol 3 rows.\n"
        "Boundary rule: walking back from the final emitter row, each "
        "decision's input ends drain(previous decision) rows earlier; when that "
        "row's turn differs from the decision's turn the boundary moves back to "
        f"the matching row (list indices {uncounted}).\n"
        f"Decisions: {len(decisions)}; emitter rows: {len(selected)}; "
        f"decompressed sha256: {hashlib.sha256(payload).hexdigest()}\n"
        "Calibration: jsonlog/character-calibration.json as rewritten by this "
        "process's own recalibration at 16:11:02 (the file loaded at 16:02:57 "
        "was not retained); the replay reproduces the recorded lifetime with it "
        "(see the test's KNOWN_HARNESS_DIVERGENCES) sha256 "
        f"{hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
