"""Freeze the 2026-09-23 18:23 unsafe-recall depth-gate board.

Live incident: a bot process started at 18:23:29 stopped 25 seconds later on
``town:blocked:owner-retired`` (16 decisions).  Its four decisions before the
stop are ``town:blocked:depth-gate:destination-50:missing-destruction``: the
objective is Angband, whose recall arrival depth is 50, and the character
carries no *Destruction* method, so ``_recall_destination_safe`` is false and
``_activate_safe_recall_fallback`` found no alternate dungeon.

Only the last emitter rows are frozen.  The process's own decisions are too few
to rebuild the live policy and the retained snapshot ring covers the previous
process as well, so this is an input-row fixture: the tests observe the final
board through the public response path on a fresh policy and run the producer
under test on it, in the manner of the entrance-travel-retired fixture.

The snapshot ring decompresses whole from the first gzip magic; the decision
tail is a byte ring whose first line can be partial, so everything before its
first newline is dropped.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# The preserved copy of the automatic capture (byte-identical to the live one).
CAPTURE = Path(
    "C:/hengband-backups/incident-captures/20260923-182351-town-blocked-owner-retired"
)
OUTPUT = ROOT / "tests" / "fixtures" / "unsafe-recall-fallback-20260923.jsonl.gz"
BOUNDARIES = OUTPUT.with_suffix(".boundaries.json")
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
# The board rows kept: the final decision's input plus the five before it, which
# is every emitter row of the stopped process's last four decisions.
KEPT_ROWS = 6
# The recorded reasons of the decisions the fixture pins, newest last.
RECORDED_TAIL = 5


def _decision_rows() -> list[dict]:
    raw = (CAPTURE / "decision-tail.jsonl").read_bytes()
    newline = raw.find(b"\n")
    if newline < 0:
        raise RuntimeError("decision tail holds no complete row")
    rows = []
    for line in raw[newline + 1 :].split(b"\n"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return rows


def _snapshot_lines() -> list[bytes]:
    raw = (CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()
    offset = raw.find(b"\x1f\x8b\x08")
    if offset < 0:
        raise RuntimeError("capture contains no intact gzip member")
    decoded = gzip.GzipFile(fileobj=io.BytesIO(raw[offset:])).read()
    lines = []
    for line in decoded.splitlines(keepends=True):
        try:
            json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        lines.append(line)
    return lines


def main() -> None:
    decisions = _decision_rows()
    final = decisions[-1]
    if final["reason"] != "town:blocked:owner-retired":
        raise RuntimeError("the capture's final decision changed")
    lines = _snapshot_lines()
    selected = lines[-KEPT_ROWS:]
    last_board = json.loads(selected[-1])
    if last_board.get("turn") != final["turn"]:
        raise RuntimeError("the final emitter row is not the stop's input")
    payload = b"".join(selected)
    with OUTPUT.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
            zipped.write(payload)
    recorded = [
        [row["key"], row["reason"]] for row in decisions[-RECORDED_TAIL:]
    ]
    progress = last_board.get("progress") or {}
    BOUNDARIES.write_text(
        json.dumps(
            {
                "input_rows": len(selected),
                "stop_turn": final["turn"],
                "stop_position": final["position"],
                "recorded": recorded,
                "recorded_arbiter": final["arbiter"],
                "recorded_procurement": final["procurement_requirements"],
                "dungeon_recall_depths": progress.get("dungeon_recall_depths"),
                "entered_dungeon_ids": sorted(
                    progress.get("entered_dungeon_ids") or ()
                ),
                "conquered_dungeon_ids": sorted(
                    progress.get("conquered_dungeon_ids") or ()
                ),
                "angband_recall_unlocked": progress.get(
                    "angband_recall_unlocked"
                ),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    tail_sha = hashlib.sha256(
        (CAPTURE / "decision-tail.jsonl").read_bytes()
    ).hexdigest()
    ring_sha = hashlib.sha256(
        (CAPTURE / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()
    ).hexdigest()
    PROVENANCE.write_text(
        "Source: incident-captures/20260923-182351-town-blocked-owner-retired/ "
        "(read from the backup copy under C:/hengband-backups/).\n"
        f"decision-tail.jsonl sha256 {tail_sha}; "
        f"snapshots/snapshots-current.jsonl.gz sha256 {ring_sha}\n"
        f"Selection: the last {KEPT_ROWS} emitter rows of the retained ring; "
        f"the last one carries the stop's turn ({final['turn']}).\n"
        f"Recorded decisions kept: the final {RECORDED_TAIL} "
        f"(reasons {[reason for _key, reason in recorded]}).\n"
        f"Emitter rows: {len(selected)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(selected)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
