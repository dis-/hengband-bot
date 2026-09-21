"""Freeze the 03:11-03:15 Morivant-travel retirement at recorded decision boundaries.

The capture covers the whole bot-process lifetime (708 decisions, 2026-09-22
03:11:43-03:15:09).  Emitter rows are not decisions: each decision's input ends
where the previous decision's ``timing.jsonl_drain_records`` says, and every
decision's input row must carry the decision record's turn.

The automatic capture kept only the last 16 MiB of the live snapshot
generation, which begins inside decision 1's input row.  The full generation
(the live ``snapshots-current.jsonl.gz`` after the stop, bot held) was copied
next to the capture as ``snapshots-current-full-generation.jsonl.gz``; this
script refuses it unless the capture's bytes are exactly its suffix.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "incident-captures" / "20260922-031509-town-blocked-owner-retired"
FULL_GENERATION = CAPTURE / "snapshots-current-full-generation.jsonl.gz"
FULL_GENERATION_SHA256 = (
    "6bfdeb13e375c08fa9a81db84d16db2be474cfdc28d4f3212a4dd11c07455001"
)
OUTPUT = ROOT / "tests" / "fixtures" / "morivant-travel-retired-20260922.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
# The live process rewrote jsonlog/character-calibration.json during this run
# (03:13:09, decision ~281), so the file it loaded at start is gone.  The tests
# reuse the esp-threat-rest fixture copy (last preserved pre-run content); its
# fields equal the rewritten file's except observed_turn.
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
            and row.get("time", "") >= "2026-09-22T03:11:40"
        ):
            rows.append(row)
    return rows


def _snapshot_rows() -> list[tuple[dict, bytes]]:
    raw = FULL_GENERATION.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FULL_GENERATION_SHA256:
        raise RuntimeError("full generation copy changed")
    tail = (CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()
    if raw[-len(tail):] != tail:
        raise RuntimeError("capture is not a suffix of the full generation")
    decoded = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
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
                "recorded_positions": [
                    [row["position"]["y"], row["position"]["x"]]
                    for row in decisions
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    PROVENANCE.write_text(
        "Source: incident-captures/20260922-031509-town-blocked-owner-retired/ "
        "(decision-tail.jsonl) and its snapshots-current-full-generation."
        "jsonl.gz (the live generation after the stop, sha256 "
        f"{FULL_GENERATION_SHA256}; the capture's 16 MiB snapshot tail is its "
        "exact byte suffix).\n"
        "Selection: every decision of the bot process started 2026-09-22 "
        f"03:11:43+09:00 (sequence 1..{len(decisions)}).\n"
        "Boundary rule: walking back from the final emitter row, each "
        "decision's input ends drain(previous decision) rows earlier; when that "
        "row's turn differs from the decision record's turn the boundary moves "
        f"back to the matching row (decisions {uncounted}).\n"
        f"Decisions: {len(decisions)}; emitter rows: {len(selected)} of "
        f"{len(rows)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        "Calibration: the live file was rewritten mid-run (03:13:09); the tests "
        "use tests/fixtures/esp-threat-rest-20260921.character-calibration.json "
        "(fields equal to the rewritten file except observed_turn) sha256 "
        f"{hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
