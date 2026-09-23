"""Freeze the two 2026-09-23 town-plan-exhausted-wander stops.

Sources (automatic captures; read from the preserved copies under
C:/hengband-backups/incident-captures/, which are byte-identical to the live
directories).  All three files of both captures are verified by sha256 before
anything is read.  Pass a directory holding the captures as the only argument
when running from a checkout without them.

  20260923-224927-town-blocked-owner-retired  (22:49, procurement *Destruction*)
  20260923-235359-town-blocked-owner-retired  (23:53, empty procurement list)

Both captures are a whole bot process: a session-start marker, decision 0
(``periodic:skill-exp-knowledge``) and 63 further decisions ending in the stop.
Only the closing window is frozen (decisions 59..63: the emptied Alchemist
page, the three ``stuck:wander`` steps and ``town:blocked:owner-retired``),
plus the ~f skill list the process read at decision 0, plus the named
policy-state fields the pins re-attach.

Reading the snapshot ring: it is a fixed-size byte ring of concatenated gzip
members that is overwritten in place, so it usually begins inside a member and
its first bytes are an unreadable fragment.  ``_ring_rows`` starts at the first
member that decompresses whole and then chains members by their compressed
length (``unused_data``), which never mistakes a magic sequence inside
compressed bytes for a member start.  Both rings here begin mid-member (the
first whole member starts at byte 663738 and 4916).  Rows that do not parse as
JSON are dropped; in these two rings the only such rows are the four empty
lines of four zero-payload flush members, and the script asserts that count.
The decision tail is a plain file, not a ring.

Boundary rule (snapshot rows are not one per decision): walking back from the
final ring row, which is the input of the final decision, each earlier
decision's input ends ``timing.jsonl_drain_records`` of that earlier decision
rows before the later decision's input.  Every frozen input row must carry its
decision's turn, player position and store page type; the script fails
otherwise.  Neither capture needed an adjustment.

Frozen records (one JSON object per line, gzip, mtime 0):
  role "skill-knowledge": the ``~f`` skill list of each capture, so a replayed
      policy does not spend its first decision on the periodic probe;
  role "decision-input": the board of each frozen decision plus that
      decision's recorded facts;
  role "policy-state": the named policy-state.json fields the pins restore
      (the errand plan, the Home catalogue bookkeeping, the fundraising mode
      and the town-visit purchase/attempt ledgers).
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
    ROOT / "tests" / "fixtures" / "town-plan-exhausted-wander-20260923.jsonl.gz"
)
PROVENANCE = OUTPUT.with_suffix(".provenance.txt")
RING_NAME = "snapshots/snapshots-current.jsonl.gz"
TAIL_NAME = "decision-tail.jsonl"
STATE_NAME = "policy-state.json"
MAGIC = b"\x1f\x8b\x08"
WANTED = (59, 60, 61, 62, 63)
EMPTY_RING_LINES = 4

# capture -> (ring sha256, tail sha256, state sha256)
CAPTURES = {
    "20260923-224927-town-blocked-owner-retired": (
        "7f32016260019956ef4b649df0541a8e2cf5389b5d1dbab86fcbcf028d4d7da1",
        "c123e90fd0f50ef9a4d448145b196f9d680c8304882606550b91fc3b1b67d44e",
    ),
    "20260923-235359-town-blocked-owner-retired": (
        "10003da388179f8f78ad6b245be2d80791cd27876a0a0d6c88cdc2f8a4c20230",
        "777edcac84c28b5cf3bba3730f4cdbc38d2221a406e93e12ca80c5cecb22e7e1",
    ),
}
# Named fields of the capture's own state dump.  "state" holds the errand plan
# and the Home catalogue bookkeeping; "modes_and_latches" holds the fundraising
# mode and this visit's purchase/attempt ledgers.
STATE_FIELDS = (
    "_town_errand_plan",
    "_home_knowledge_current",
    "_home_knowledge_valid_before",
    "_home_page_size",
    "_home_scan_source",
    "_home_scan_item_count",
)
MODE_FIELDS = (
    "_fundraising_mode",
    "_observed_town_id",
    "_town_was_in_town",
    "_town_store_attempted",
    "_town_visit_purchases",
    "_town_visit_purchase_quantities",
    "_town_no_progress_count",
    "_town_wander_streak",
    "_yeek_conquest_processed",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ring_rows(raw: bytes) -> tuple[list[dict], int]:
    offset = raw.find(MAGIC)
    rows: list[dict] = []
    dropped = 0
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
                if line.strip():
                    raise AssertionError("ring holds a non-empty unreadable row")
                dropped += 1
    return rows, dropped


def _session(raw: bytes) -> list[dict]:
    """The decisions of the last process in the tail, oldest first."""
    rows: list[dict] = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if "decision_sequence" in row:
            rows.append(row)
    start = len(rows) - 1
    while start > 0 and (
        rows[start - 1]["decision_sequence"] == rows[start]["decision_sequence"] - 1
    ):
        start -= 1
    session = rows[start:]
    if session[0]["decision_sequence"] != 0:
        raise AssertionError("the capture does not hold a whole bot process")
    if session[-1]["reason"] != "town:blocked:owner-retired":
        raise AssertionError("the final decision is not the recorded stop")
    return session


def _matches(board: dict, record: dict) -> bool:
    return (
        "knowledge" not in board
        and board.get("turn") == record["turn"]
        and (board["player"]["y"], board["player"]["x"])
        == (record["position"]["y"], record["position"]["x"])
        and (board.get("store") or {}).get("store_type") == record["store_type"]
    )


def _input_ends(decisions: list[dict], boards: list[dict]) -> list[int]:
    ends = [len(boards) - 1]
    for index in range(len(decisions) - 1, 0, -1):
        drain = int(
            (decisions[index - 1].get("timing") or {}).get("jsonl_drain_records") or 0
        )
        end = ends[-1] - drain
        if end < 0 or not _matches(boards[end], decisions[index - 1]):
            raise AssertionError(
                f"decision {decisions[index - 1]['decision_sequence']} "
                "boundary needed adjustment"
            )
        ends.append(end)
    ends.reverse()
    return ends


def _facts(record: dict) -> dict:
    return {
        "decision_sequence": record["decision_sequence"],
        "turn": record["turn"],
        "position": record["position"],
        "store_type": record["store_type"],
        "key": record["key"],
        "reason": record["reason"],
        "store_visit": record["store_visit"],
        "arbiter": record["arbiter"],
        "fundraising": record["fundraising"],
        "home_candidate_waiting": record["home_candidate_waiting"],
        "objective": record["objective"],
        "procurement_requirements": record["procurement_requirements"],
        "shop_selector": record["shop_selector"],
        "town_plan": record["town_plan"],
        "messages": record["messages"],
        "jsonl_drain_records": (record.get("timing") or {}).get(
            "jsonl_drain_records"
        ),
    }


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CAPTURES
    records: list[dict] = []
    provenance: list[str] = []
    for name, (ring_sha, tail_sha) in CAPTURES.items():
        capture = root / name
        ring_path = capture / RING_NAME
        tail_path = capture / TAIL_NAME
        state_path = capture / STATE_NAME
        if _sha256(ring_path) != ring_sha:
            raise AssertionError(f"{name}: snapshot ring changed")
        if _sha256(tail_path) != tail_sha:
            raise AssertionError(f"{name}: decision tail changed")
        boards, dropped = _ring_rows(ring_path.read_bytes())
        if dropped != EMPTY_RING_LINES:
            raise AssertionError(f"{name}: unreadable ring rows changed")
        decisions = _session(tail_path.read_bytes())
        ends = _input_ends(decisions, boards)
        by_sequence = {row["decision_sequence"]: row for row in decisions}
        skill_rows = [
            index for index, board in enumerate(boards[: ends[WANTED[0]]])
            if (board.get("knowledge") or {}).get("category") == "skill_exp"
        ]
        if not skill_rows:
            raise AssertionError(f"{name}: no skill list before the window")
        records.append({
            "capture": name,
            "role": "skill-knowledge",
            "ring_index": skill_rows[-1],
            "board": boards[skill_rows[-1]],
        })
        for sequence in WANTED:
            index = ends[sequence]
            records.append({
                "capture": name,
                "role": "decision-input",
                "ring_index": index,
                "decision": _facts(by_sequence[sequence]),
                "board": boards[index],
            })
        dump = json.loads(state_path.read_text(encoding="utf-8"))
        records.append({
            "capture": name,
            "role": "policy-state",
            "fields": {
                field: dump["state"][field] for field in STATE_FIELDS
            } | {
                field: dump["modes_and_latches"][field] for field in MODE_FIELDS
            },
        })
        provenance.append(
            f"{name}: ring sha256 {ring_sha}; tail sha256 {tail_sha}; "
            f"state sha256 {_sha256(state_path)}; ring rows {len(boards)} "
            f"({dropped} empty flush rows dropped); process decisions "
            f"{len(decisions)}; skill row {skill_rows[-1]}; decision->row "
            f"{[(s, ends[s]) for s in WANTED]}"
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
