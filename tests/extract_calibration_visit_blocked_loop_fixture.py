"""Freeze the 2026-09-23 03:44 calibration visit-blocked loop (loop-detected).

Source: the automatic capture
incident-captures/20260923-034402-loop-detected/ (backup copy under
C:/hengband-backups/incident-captures/).  Both source files are verified by
sha256 before anything is read.  Pass the capture directory as the only
argument when running from a worktree without that directory.

Boundary rule (snapshot rows are not one per decision): walking back from the
final ring row, which is the input of the final decision, each earlier
decision's input ends ``timing.jsonl_drain_records`` of that earlier decision
rows before the later decision's input.  Every derived input row must carry
its decision's recorded turn, player position and store page type; the script
fails otherwise, and the frozen decisions must need no adjustment at all.

Frozen records (one JSON object per line, gzip, mtime 0):
  role "home-knowledge": the two recorded ``~9`` Home catalogues the live bot
      consumed on either side of the calibration attempt (turns 4734609 and
      4741084);
  role "decision-input": the boards of decisions 559 (the last recorded
      ``strip`` phase), 560 (the strip end that aborts on the still-worn
      cursed boots), 628 (the Remove Curse read) and 629 (the first board
      whose equipment is no longer cursed);
  role "blocked-window": the boards of decisions 639-662, the recorded
      ``town:blocked:equipment-calibration-required`` repetition that the
      driver stopped as ``loop-detected``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "incident-captures" / "20260923-034402-loop-detected"
RING_NAME = "snapshots/snapshots-current.jsonl.gz"
RING_SHA256 = "a41824e4ee2f46af18f7ff10bce833c8710f38cc35cfbb1fa858c1523a640b91"
TAIL_NAME = "decision-tail.jsonl"
TAIL_SHA256 = "f28fb19eb82496ea326190ab310daf28bc15bbe56728e6fbcf2fced68cd787a5"
OUTPUT = (
    ROOT / "tests" / "fixtures" /
    "calibration-visit-blocked-loop-20260923.jsonl.gz"
)
INPUT_DECISIONS = (559, 560, 628, 629)
BLOCKED_WINDOW = tuple(range(639, 663))
# The recorded ``~9`` Home catalogues consumed before and after the strip.
HOME_KNOWLEDGE_TURNS = (4_734_609, 4_741_084)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decision_facts(record: dict) -> dict:
    optimization = record.get("equipment_optimization") or {}
    return {
        "decision_sequence": record["decision_sequence"],
        "turn": record["turn"],
        "position": record["position"],
        "store_type": record["store_type"],
        "key": record["key"],
        "reason": record["reason"],
        "messages": record.get("messages"),
        "visible_hostiles": record["visible_hostiles"],
        "calibration": optimization.get("calibration"),
        "equipment_blockers": optimization.get("blockers"),
        "home_scan_complete": optimization.get("home_scan_complete"),
        "departure_block": record.get("departure_block"),
        "arbiter": record.get("arbiter"),
        "jsonl_drain_records": (record.get("timing") or {}).get(
            "jsonl_drain_records"
        ),
    }


def main() -> None:
    capture = Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURE
    ring_path = capture / RING_NAME
    tail_path = capture / TAIL_NAME
    if _sha256(ring_path) != RING_SHA256:
        raise AssertionError("snapshot ring changed")
    if _sha256(tail_path) != TAIL_SHA256:
        raise AssertionError("decision tail changed")

    with gzip.open(ring_path, "rb") as stream:
        ring = [line.rstrip(b"\r\n") for line in stream if line.strip()]
    boards = [json.loads(line) for line in ring]

    rows: list[dict] = []
    for line in tail_path.read_bytes().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # the capped tail starts mid-record
    # The tail spans the previous bot process as well; the loop belongs to the
    # process whose session-start record resets the decision sequence.
    session_start = max(
        index for index, row in enumerate(rows)
        if row.get("kind") == "session-start"
    )
    ordered = [
        row for row in rows[session_start + 1:] if "decision_sequence" in row
    ]

    frozen = set(INPUT_DECISIONS) | set(BLOCKED_WINDOW)
    by_sequence: dict[int, dict] = {}
    for record in ordered:
        sequence = record["decision_sequence"]
        if sequence in frozen:
            if sequence in by_sequence:
                raise AssertionError("frozen decision sequence is not unique")
            by_sequence[sequence] = record
    if set(by_sequence) != frozen:
        raise AssertionError("the recorded window is incomplete")

    def matches(board: dict, record: dict) -> bool:
        return (
            "knowledge" not in board
            and board["turn"] == record["turn"]
            and (board["player"]["y"], board["player"]["x"])
            == (record["position"]["y"], record["position"]["x"])
            and (board.get("store") or {}).get("store_type")
            == record["store_type"]
        )

    inputs: dict[int, int] = {}
    adjusted: list[tuple[int, int, int]] = []
    index = len(ring) - 1
    for position, record in enumerate(reversed(ordered)):
        if position:
            index -= int(record["timing"]["jsonl_drain_records"])
        # Knowledge rows and a periodic probe's own drain can shift the counted
        # boundary; it then moves back to the nearest row carrying the
        # decision's recorded turn, position and page (never forward).
        start = index
        while index >= 0 and not matches(boards[index], record):
            index -= 1
            if start - index > len(ordered):
                raise AssertionError(
                    f"decision {record['decision_sequence']} has no input row"
                )
        if index != start:
            adjusted.append((record["decision_sequence"], start, index))
        if record["decision_sequence"] in frozen:
            if index != start:
                raise AssertionError(
                    f"frozen decision {record['decision_sequence']} "
                    "boundary needed adjustment"
                )
            inputs[record["decision_sequence"]] = index
    print(f"boundary adjustments (sequence, counted, matched): {adjusted}")

    knowledge_rows = [
        index for index, board in enumerate(boards)
        if (board.get("knowledge") or {}).get("category") == "home"
        and board.get("turn") in HOME_KNOWLEDGE_TURNS
    ]
    if len(knowledge_rows) != 2:
        raise AssertionError("recorded Home catalogue rows changed")

    records = [
        {
            "role": "home-knowledge",
            "ring_index": index,
            "turn": boards[index]["turn"],
            "board": boards[index],
        }
        for index in knowledge_rows
    ]
    for sequence in INPUT_DECISIONS:
        records.append({
            "role": "decision-input",
            "ring_index": inputs[sequence],
            "decision": _decision_facts(by_sequence[sequence]),
            "board": boards[inputs[sequence]],
        })
    for sequence in BLOCKED_WINDOW:
        records.append({
            "role": "blocked-window",
            "ring_index": inputs[sequence],
            "decision": _decision_facts(by_sequence[sequence]),
            "board": boards[inputs[sequence]],
        })
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ).encode("utf-8", "surrogatepass")
    with OUTPUT.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(payload)
    print(f"wrote {len(records)} records to {OUTPUT}")
    print(f"sha256 {_sha256(OUTPUT)}")


if __name__ == "__main__":
    main()
