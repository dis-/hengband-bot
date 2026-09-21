"""Freeze the 18:02 town-loot incident at recorded decision boundaries."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "incident-captures" / "20260921-180239-town-blocked-owner-retired"
OUTPUT = ROOT / "tests" / "fixtures" / "town-loot-supplier-alternation-20260921.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
FIRST_TURN = 4_308_714


def _decision_rows() -> list[dict]:
    rows = []
    for line in (CAPTURE / "decision-tail.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("decision_sequence") and row.get("time", "")[11:19] >= "18:02:00":
            rows.append(row)
    return rows


def _snapshot_tail() -> list[bytes]:
    raw = (CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()
    # The automatic cap retained a suffix beginning inside an older member.
    # Each later response is its own gzip member, so start at the first intact
    # member and discard its one partial leading JSON row.
    offset = raw.find(b"\x1f\x8b\x08")
    if offset < 0:
        raise RuntimeError("capture contains no intact gzip member")
    decoded = gzip.GzipFile(fileobj=io.BytesIO(raw[offset:])).read()
    rows = []
    for line in decoded.splitlines(keepends=True):
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if int(row.get("turn", -1)) >= FIRST_TURN:
            rows.append(line)
    return rows


def main() -> None:
    decisions = _decision_rows()
    snapshots = _snapshot_tail()
    drains = [
        int(row.get("timing", {}).get("jsonl_drain_records", 0))
        for row in decisions[:-1]
    ]
    # The first of two identical FIRST_TURN rows is the preceding command's
    # response.  The second is decision 1's input; later inputs are delimited
    # by the previous decision's measured drain count.
    selected = snapshots[1:]
    expected = 1 + sum(drains)
    if len(selected) != expected:
        raise RuntimeError(f"expected {expected} emitter rows, got {len(selected)}")
    payload = b"".join(selected)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    BOUNDARIES.write_text(
        json.dumps({"decision_count": len(decisions), "drains": drains}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    PROVENANCE.write_text(
        "Source: incident-captures/20260921-180239-town-blocked-owner-retired/\n"
        "Selection: decision inputs from 2026-09-21 18:02:23+09:00 onward.\n"
        "Boundary rule: the initial input row plus each previous decision's "
        "timing.jsonl_drain_records emitter rows; emitter rows are not decisions.\n"
        f"Decisions: {len(decisions)}; emitter rows: {len(selected)}; "
        f"decompressed sha256: {hashlib.sha256(payload).hexdigest()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
