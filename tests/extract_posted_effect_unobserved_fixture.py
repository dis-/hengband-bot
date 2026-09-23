"""Freeze the three 2026-09-23 posted-effect-unobserved stops.

Sources (automatic captures; read from the preserved copies under
C:/hengband-backups/incident-captures/, which are byte-identical to the live
directories).  Both files of every capture are verified by sha256 before
anything is read.  Pass a directory holding the three captures as the only
argument when running from a checkout without them.

  20260923-181527-town-blocked-owner-retired  (enter/leave Home cycle)
  20260923-201024-stuck-prompt                (leave confirmation repeat)
  20260923-202618-no-key-exhausted            (one-shot in flight, no key)

Reading the snapshot ring: it is a fixed-size byte ring of concatenated gzip
members that is overwritten in place, so it usually begins inside a member and
its first row is a partial line.  ``_ring_rows`` starts at the first member
that decompresses whole and then chains members by their compressed length
(``unused_data``), which never mistakes a magic sequence inside compressed
bytes for a member start.  Rows that do not parse as JSON are dropped; only the
ring's own first fragment is ever affected.  The 18:15 and 20:26 rings begin
mid-member; the 20:10 ring does not.  The decision tail is a byte ring too, so
lines that do not parse are dropped there as well.

Boundary rule (snapshot rows are not one per decision): walking back from the
final ring row, which is the input of the final decision, each earlier
decision's input ends ``timing.jsonl_drain_records`` of that earlier decision
rows before the later decision's input.  Every frozen input row must carry its
decision's recorded turn, player position and store page type; the script fails
otherwise.  None of the frozen decisions needed an adjustment.

Frozen records (one JSON object per line, gzip, mtime 0):
  role "skill-knowledge": the latest ``~f`` skill list of each capture, so a
      replayed policy does not spend its first decision on the periodic probe;
  role "decision-input": the board of each frozen decision plus that
      decision's recorded facts;
  role "policy-state": the named policy-state.json fields the 18:15 pins
      restore (the captured Home queue and its stale catalogue flag).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAPTURES = Path("C:/hengband-backups/incident-captures")
OUTPUT = (
    ROOT / "tests" / "fixtures" / "posted-effect-unobserved-20260923.jsonl.gz"
)
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
RING_NAME = "snapshots/snapshots-current.jsonl.gz"
TAIL_NAME = "decision-tail.jsonl"
STATE_NAME = "policy-state.json"
MAGIC = b"\x1f\x8b\x08"

# capture -> (ring sha256, tail sha256, skill-knowledge turn, decisions)
CAPTURES = {
    "20260923-181527-town-blocked-owner-retired": (
        "0406919b6af619987f073f26d5ac04549148638b0877356d1f4d36cb3e5659ff",
        "a30c9d6d5e31ae0803eddb5b746d49b98d07b1a830738cedd352f28eda525386",
        5_044_439,
        (1567, 1568, 1569, 1570),
    ),
    "20260923-201024-stuck-prompt": (
        "4f42c3b8c6612469b656b82b19bff9a76960cdc02ecb4bd99580e6d0689907f1",
        "2cd233ba1365d78076131f67c36ff307d4dff3656526dcd00266682350b2ca86",
        5_172_091,
        (5428, 5429),
    ),
    "20260923-202618-no-key-exhausted": (
        "13e8e929b25dbbdccb0153ed7734c571c9f48dfb6ddba8436ce554738871678e",
        "6defc5c519d71ed996bad658de35d2dc28c69f418b0c5cbb655a50d2dc34275c",
        5_212_073,
        (628, 629, 630),
    ),
}
# The 18:15 pins restore the queued Home take and the catalogue flag that
# refuses to compose it; both are named fields of that capture's state dump.
STATE_FIELDS = (
    "_home_pending_item",
    "_home_pending_quantity",
    "_home_knowledge_current",
    "_home_knowledge_valid_before",
    "_home_scan_source",
    "_home_scan_item_count",
)
STATE_CAPTURE = "20260923-181527-town-blocked-owner-retired"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ring_rows(raw: bytes) -> list[dict]:
    offset = raw.find(MAGIC)
    rows: list[dict] = []
    while 0 <= offset < len(raw):
        engine = zlib.decompressobj(31)
        try:
            decoded = engine.decompress(raw[offset:])
        except zlib.error:
            decoded = b""
        if not decoded or not engine.eof:
            offset = raw.find(MAGIC, offset + 1)
            continue
        offset = len(raw) - len(engine.unused_data)
        for line in decoded.splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _decision_rows(raw: bytes) -> list[dict]:
    """Emitted decisions of a decision tail, newest last.

    The tail also carries session-header rows (a ``kind``/``argv`` record
    written when the bot starts); they are not decisions and carry no drain
    count, so the boundary walk skips them.
    """
    rows: list[dict] = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if "decision_sequence" in row:
            rows.append(row)
    return rows


def _facts(record: dict) -> dict:
    return {
        "decision_sequence": record["decision_sequence"],
        "turn": record["turn"],
        "position": record["position"],
        "store_type": record["store_type"],
        "key": record["key"],
        "reason": record["reason"],
        "store_visit": record["store_visit"],
        "town_emit_ownership": record.get("town_emit_ownership"),
        "arbiter": record["arbiter"],
        "shopping_approach_store_type": record["shopping_approach_store_type"],
        "messages": record["messages"],
        "visible_hostiles": record["visible_hostiles"],
        "jsonl_drain_records": (record.get("timing") or {}).get(
            "jsonl_drain_records"
        ),
    }


def _matches(board: dict, record: dict) -> bool:
    return (
        "knowledge" not in board
        and board["turn"] == record["turn"]
        and (board["player"]["y"], board["player"]["x"])
        == (record["position"]["y"], record["position"]["x"])
        and (board.get("store") or {}).get("store_type") == record["store_type"]
    )


def _inputs(boards: list[dict], decisions: list[dict], wanted) -> dict[int, int]:
    found: dict[int, int] = {}
    index = len(boards) - 1
    for position, record in enumerate(reversed(decisions)):
        if position:
            index -= int(record["timing"]["jsonl_drain_records"])
        start = index
        while index >= 0 and not _matches(boards[index], record):
            index -= 1
            if start - index > len(decisions):
                raise AssertionError(
                    f"decision {record['decision_sequence']} has no input row"
                )
        sequence = record["decision_sequence"]
        if sequence in wanted:
            if index != start:
                raise AssertionError(
                    f"frozen decision {sequence} boundary needed adjustment"
                )
            if sequence in found:
                raise AssertionError(f"decision {sequence} is not unique")
            found[sequence] = index
        if len(found) == len(wanted):
            return found
    raise AssertionError(f"decisions {sorted(set(wanted) - set(found))} not found")


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CAPTURES
    records: list[dict] = []
    provenance: list[str] = []
    for name, (ring_sha, tail_sha, skill_turn, wanted) in CAPTURES.items():
        capture = root / name
        ring_path = capture / RING_NAME
        tail_path = capture / TAIL_NAME
        if _sha256(ring_path) != ring_sha:
            raise AssertionError(f"{name}: snapshot ring changed")
        if _sha256(tail_path) != tail_sha:
            raise AssertionError(f"{name}: decision tail changed")
        boards = _ring_rows(ring_path.read_bytes())
        decisions = _decision_rows(tail_path.read_bytes())
        inputs = _inputs(boards, decisions, set(wanted))
        by_sequence = {
            record["decision_sequence"]: record
            for record in decisions
            if record["decision_sequence"] in wanted
        }
        skill_rows = [
            index for index, board in enumerate(boards)
            if board.get("turn") == skill_turn
            and (board.get("knowledge") or {}).get("category") == "skill_exp"
        ]
        if len(skill_rows) != 1:
            raise AssertionError(f"{name}: recorded skill row changed")
        records.append({
            "capture": name,
            "role": "skill-knowledge",
            "ring_index": skill_rows[0],
            "board": boards[skill_rows[0]],
        })
        for sequence in wanted:
            records.append({
                "capture": name,
                "role": "decision-input",
                "ring_index": inputs[sequence],
                "decision": _facts(by_sequence[sequence]),
                "board": boards[inputs[sequence]],
            })
        provenance.append(
            f"{name}: ring sha256 {ring_sha}; tail sha256 {tail_sha}; "
            f"ring rows {len(boards)}; skill row {skill_rows[0]}; "
            f"decision->row {[(s, inputs[s]) for s in wanted]}"
        )

    state = json.loads(
        (root / STATE_CAPTURE / STATE_NAME).read_text(encoding="utf-8")
    )["state"]
    records.append({
        "capture": STATE_CAPTURE,
        "role": "policy-state",
        "fields": {field: state[field] for field in STATE_FIELDS},
    })
    provenance.append(
        f"{STATE_CAPTURE}: policy-state.json sha256 "
        f"{_sha256(root / STATE_CAPTURE / STATE_NAME)}; "
        f"fields {list(STATE_FIELDS)}"
    )

    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ).encode("utf-8", "surrogatepass")
    with OUTPUT.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(payload)
    PROVENANCE.write_text(
        "Source: incident-captures/ (read from the backup copies under "
        "C:/hengband-backups/).\n"
        + "\n".join(provenance)
        + f"\nRecords: {len(records)}; decompressed sha256: "
        f"{hashlib.sha256(payload).hexdigest()}\n"
        f"Compressed sha256: {_sha256(OUTPUT)}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(records)} records to {OUTPUT}")
    print(f"sha256 {_sha256(OUTPUT)}")


if __name__ == "__main__":
    main()
