"""Freeze the 2026-09-23 01:43 interrupted Alchemist travel (no-key stop).

Source: the automatic capture incident-captures/20260923-014342-no-key-exhausted/
(backup copy under C:/hengband-backups/incident-captures/).  Both source files
are verified by sha256 before anything is read.  Pass the capture directory as
the only argument when running from a worktree without that directory.

Boundary rule (snapshot rows are not one per decision): walking back from the
final ring row, which is the input of the final decision, each earlier
decision's input ends ``timing.jsonl_drain_records`` of that earlier decision
rows before the later decision's input.  Every derived input row must carry
its decision's recorded turn, player position and store page type; the script
fails otherwise.

Frozen records (one JSON object per line, gzip, mtime 0):
  role "skill-knowledge": the latest ``~f`` skill list before each frozen
      travel post (turns 4730301 and 4733303);
  role "decision-input": the boards of decisions 1719, 1720, 1905, 1906 with
      that decision's recorded facts;
  role "lagged-duplicate": the second, byte-identical JSONL row of turn
      4734443 (the board a lagged observation would repeat after the post).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "incident-captures" / "20260923-014342-no-key-exhausted"
RING_NAME = "snapshots/snapshots-current.jsonl.gz"
RING_SHA256 = "8ce0e682abac3feddfe58bd991c843802bf570c90ad6c533394ef1a04db4141e"
TAIL_NAME = "decision-tail.jsonl"
TAIL_SHA256 = "e23d0ef65bb6a1bbb71527575acf3433cbb1007e9a228f819272b98fb7bdd97d"
OUTPUT = (
    ROOT / "tests" / "fixtures" /
    "store-entry-travel-interrupted-20260923.jsonl.gz"
)
DECISIONS = (1719, 1720, 1905, 1906)
# The latest ``~f`` skill list preceding each frozen travel post.
SKILL_KNOWLEDGE_TURNS = (4_730_301, 4_733_303)
LAGGED_TURN = 4_734_443


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decision_facts(record: dict) -> dict:
    threat = record.get("threat_prediction") or {}
    return {
        "decision_sequence": record["decision_sequence"],
        "turn": record["turn"],
        "position": record["position"],
        "store_type": record["store_type"],
        "key": record["key"],
        "reason": record["reason"],
        "store_visit": record["store_visit"],
        "town_emit_ownership": record["town_emit_ownership"],
        "visible_hostiles": record["visible_hostiles"],
        "loot_blocker": (record.get("loot") or {}).get("blocker"),
        "threat_monsters": [
            {
                "race_id": monster["race_id"],
                "position": monster["position"],
                "distance": monster["distance"],
                "asleep": monster["asleep"],
            }
            for monster in threat.get("monsters", ())
        ],
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

    decisions: list[dict] = []
    for line in tail_path.read_bytes().splitlines():
        try:
            decisions.append(json.loads(line))
        except ValueError:
            continue  # the capped tail starts mid-record
    ordered = [
        record for record in decisions
        if DECISIONS[0] <= record["decision_sequence"] <= DECISIONS[-1]
    ]
    # A periodic ``~f`` probe reuses its neighbour's sequence; it is still a
    # separate emitted decision with its own drain, so keep file order.
    if sorted(set(r["decision_sequence"] for r in ordered)) != list(
        range(DECISIONS[0], DECISIONS[-1] + 1)
    ):
        raise AssertionError("decision window is not contiguous")
    by_sequence: dict[int, dict] = {}
    for record in ordered:
        if record["decision_sequence"] in DECISIONS:
            if record["decision_sequence"] in by_sequence:
                raise AssertionError("frozen decision sequence is not unique")
            by_sequence[record["decision_sequence"]] = record

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
        # Knowledge rows and the probe's own drain can shift the counted
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
        if record["decision_sequence"] in DECISIONS:
            if index != start:
                raise AssertionError(
                    f"frozen decision {record['decision_sequence']} "
                    "boundary needed adjustment"
                )
            inputs[record["decision_sequence"]] = index
    print(f"boundary adjustments (sequence, counted, matched): {adjusted}")

    skill_rows = [
        index for index, board in enumerate(boards)
        if board.get("turn") in SKILL_KNOWLEDGE_TURNS
        and (board.get("knowledge") or {}).get("category") == "skill_exp"
    ]
    lagged_rows = [
        index for index, board in enumerate(boards)
        if board.get("turn") == LAGGED_TURN and index != inputs[1905]
    ]
    if len(skill_rows) != 2 or len(lagged_rows) != 1:
        raise AssertionError("recorded auxiliary rows changed")
    if ring[lagged_rows[0]] != ring[inputs[1905]]:
        raise AssertionError("lagged duplicate is not byte-identical")

    records = [
        {
            "role": "skill-knowledge",
            "ring_index": index,
            "board": boards[index],
        }
        for index in skill_rows
    ]
    for sequence in DECISIONS:
        records.append({
            "role": "decision-input",
            "ring_index": inputs[sequence],
            "decision": _decision_facts(by_sequence[sequence]),
            "board": boards[inputs[sequence]],
        })
    records.append({
        "role": "lagged-duplicate",
        "ring_index": lagged_rows[0],
        "board": boards[lagged_rows[0]],
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
