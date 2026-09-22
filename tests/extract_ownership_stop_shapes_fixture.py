"""Freeze the three recorded stops of 2026-09-23 as stop-shape classifier input.

Sources (automatic captures; backup copies under
C:/hengband-backups/incident-captures/).  Every source file is verified by
sha256 before anything is read; pass the directory holding the three captures
as the only argument when running from a worktree that has no
incident-captures/ of its own:

  20260923-014342-no-key-exhausted   01:43 town, store entry awaited forever
  20260923-034402-loop-detected      03:44 town, calibration block repeated
  20260923-060018-loop-detected      06:00 dungeon, seek-loot in turn with
                                     detected:prepare-choke

Frozen per capture (one JSON object per line, gzip, mtime 0):
  "meta": the capture's own meta.json - the stop kind, its time and turn, and
      ``last_reasons``, which is the driver's ``recent_reasons`` window
      (cli.py, deque(maxlen=20)) exactly as it stood at the stop.  This is the
      classifier's reason input in production, so the pins use the recorded
      window rather than one rebuilt from rows.
  "rows": the last 24 decision rows of the capture, projected onto the fields
      the classifier reads.  The driver's own stop report - the trailing row
      whose reason is the stop kind and whose decision_sequence repeats the
      previous row's - is not a policy decision and is dropped, so the last
      frozen row is the decision the policy actually produced before the stop
      (the row the live ledger holds when it classifies).

Nothing else of the captures is read: no policy state, no snapshot ring.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = ROOT / "incident-captures"
OUTPUT = ROOT / "tests" / "fixtures" / "ownership-stop-shapes-20260923.jsonl.gz"
PROVENANCE = ROOT / "tests" / "fixtures" / (
    "ownership-stop-shapes-20260923.provenance.txt"
)
ROWS_PER_CAPTURE = 24

# capture -> (meta.json sha256, decision-tail.jsonl sha256)
CAPTURES = {
    "20260923-014342-no-key-exhausted": (
        "9032d2621b5498ba4915f4629a1fd39fd6fe1745dc4d25baad5303e57f8e9667",
        "e23d0ef65bb6a1bbb71527575acf3433cbb1007e9a228f819272b98fb7bdd97d",
    ),
    "20260923-034402-loop-detected": (
        "4c3d2084e03f8089bf21b41bc0881422753a4f98b3a2a073af4a01f0ad0d89ef",
        "f28fb19eb82496ea326190ab310daf28bc15bbe56728e6fbcf2fced68cd787a5",
    ),
    "20260923-060018-loop-detected": (
        "e93f69d2ca74c7b68878ee954146ee1382c2f20942796da552b4657775a47916",
        "f58e4e2f93528ffd04549d070dd4448570616e1d256fb4e4c9204bf25d935413",
    ),
}
ROW_FIELDS = (
    "decision_sequence",
    "time",
    "turn",
    "reason",
    "key",
    "floor",
    "store_type",
    "requested_owner",
    "prompt_owner_handoff",
    "arbiter",
    "store_visit",
    "town_emit_ownership",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(tail: Path, kind: str) -> list[dict]:
    records: list[dict] = []
    for line in tail.read_bytes().splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue  # the capped tail starts mid-record
    if len(records) >= 2:
        last, previous = records[-1], records[-2]
        if (
            last.get("reason") == kind
            and last.get("decision_sequence") == previous.get("decision_sequence")
        ):
            records.pop()
    return [
        {field: record.get(field) for field in ROW_FIELDS}
        for record in records[-ROWS_PER_CAPTURE:]
    ]


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURE_ROOT
    records = []
    for name, (meta_sha, tail_sha) in CAPTURES.items():
        capture = root / name
        meta_path = capture / "meta.json"
        tail_path = capture / "decision-tail.jsonl"
        if _sha256(meta_path) != meta_sha:
            raise AssertionError(f"{name}: meta.json changed")
        if _sha256(tail_path) != tail_sha:
            raise AssertionError(f"{name}: decision-tail.jsonl changed")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        rows = _rows(tail_path, meta["kind"])
        if len(rows) != ROWS_PER_CAPTURE:
            raise AssertionError(f"{name}: {len(rows)} rows recovered")
        if len(meta["last_reasons"]) != 20:
            raise AssertionError(f"{name}: recorded reason window is not 20")
        records.append(
            {
                "role": "stop",
                "capture": name,
                "meta_sha256": meta_sha,
                "decision_tail_sha256": tail_sha,
                "meta": meta,
                "rows": rows,
            }
        )
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ).encode("utf-8", "surrogatepass")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(payload)
    PROVENANCE.write_text(
        "Source: incident-captures/{20260923-014342-no-key-exhausted,"
        "20260923-034402-loop-detected,20260923-060018-loop-detected}/\n"
        "Read: meta.json and decision-tail.jsonl only, each verified by the "
        "sha256 pinned in tests/extract_ownership_stop_shapes_fixture.py.\n"
        f"Selection: the whole recorded reason window (20) and the last "
        f"{ROWS_PER_CAPTURE} decision rows of each capture, projected onto "
        f"{', '.join(ROW_FIELDS)}; the driver's trailing stop-report row is "
        "dropped.\n"
        f"Decompressed sha256: {hashlib.sha256(payload).hexdigest()}\n"
        f"Fixture sha256: {_sha256(OUTPUT)}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(records)} records to {OUTPUT}")
    print(f"sha256 {_sha256(OUTPUT)}")


if __name__ == "__main__":
    main()
