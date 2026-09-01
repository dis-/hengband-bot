"""Extract the compact, immutable emit-ownership measurement fixture.

Run from the repository root:
  PYTHONPATH=src;tests python tests/extract_historical_emit_fixture.py
"""

from __future__ import annotations

import gzip
import io
import json
from datetime import datetime
from pathlib import Path

from historical_emit_fixture import (
    DECISIONS, EQUIP_DECISIONS, EQUIP_SNAPSHOTS, FIXTURE_DIR, LEDGER,
    CAL3_VISIT_BUDGET_DECISIONS, E6_PRELANDING_DECISIONS, NO_ACTION_DECISIONS,
    NO_ACTION_SNAPSHOTS, POSTED, ROOT,
)


CUTOFF = datetime.fromisoformat("2026-09-01T17:30")
E6_PRELANDING_END = datetime.fromisoformat("2026-09-01T17:47:46.999999")
CAL3_VISIT_BUDGET_START = datetime.fromisoformat("2026-09-02T04:15")
CAL3_VISIT_BUDGET_END = datetime.fromisoformat("2026-09-02T04:20:36.999999")
DECISION_FIELDS = (
    "time", "decision_sequence", "turn", "reason", "key", "store_visit",
    "store_type", "position", "shopping_approach_store_type", "floor",
)
LEDGER_FIELDS = ("time", "posted_key", "line_turns", "line_types")
POSTED_FIELDS = ("time", "character_index", "composed_key", "decision")
SNAPSHOT_FIELDS = ("type", "turn", "player", "store", "grid_map")


def _read(path: Path):
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _before_cutoff(rows: list[dict]) -> list[dict]:
    """Select by time, retaining a malformed row bracketed by selected times."""
    timed = [
        datetime.fromisoformat(row["time"]).replace(tzinfo=None) if row.get("time") else None
        for row in rows
    ]
    selected = []
    for index, row in enumerate(rows):
        if timed[index] is not None:
            include = timed[index] < CUTOFF
        else:
            previous = next((value for value in reversed(timed[:index]) if value is not None), None)
            following = next((value for value in timed[index + 1:] if value is not None), None)
            include = previous is not None and following is not None and previous < CUTOFF and following < CUTOFF
        if include:
            selected.append(row)
    return selected


def _project(row: dict, fields: tuple[str, ...]) -> dict:
    return {field: row[field] for field in fields if field in row}


def _write(path: Path, rows: list[dict], fields: tuple[str, ...]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(json.dumps(_project(row, fields), ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    rotated = _read(ROOT / "jsonlog" / "bot-decisions.jsonl.1")
    current = _read(ROOT / "jsonlog" / "bot-decisions.jsonl")
    all_decisions = rotated + current
    decisions = _before_cutoff(all_decisions)
    e6_prelanding = [
        row for row in all_decisions
        if row.get("time") and CUTOFF <= datetime.fromisoformat(row["time"]).replace(tzinfo=None) <= E6_PRELANDING_END
    ]
    cal3_visit_budget = [
        row for row in all_decisions
        if row.get("time")
        and CAL3_VISIT_BUDGET_START
        <= datetime.fromisoformat(row["time"]).replace(tzinfo=None)
        <= CAL3_VISIT_BUDGET_END
    ]
    first = min(datetime.fromisoformat(row["time"]).replace(tzinfo=None) for row in decisions if row.get("time"))
    last = max(datetime.fromisoformat(row["time"]).replace(tzinfo=None) for row in decisions if row.get("time"))
    ledger = _before_cutoff(_read(ROOT / "capture-ledger" / "read-batches.jsonl"))
    posted = [
        row for row in _read(ROOT / "jsonlog" / "bot-posted-characters.jsonl")
        if row.get("time") and first <= datetime.fromisoformat(row["time"]).replace(tzinfo=None) <= last
    ]
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _write(DECISIONS, decisions, DECISION_FIELDS)
    _write(LEDGER, ledger, LEDGER_FIELDS)
    _write(POSTED, posted, POSTED_FIELDS)
    _write(EQUIP_DECISIONS, _read(ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.jsonl"), DECISION_FIELDS)
    _write(EQUIP_SNAPSHOTS, _read(ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"), SNAPSHOT_FIELDS)
    _write(NO_ACTION_DECISIONS, _read(ROOT / "jsonlog" / "incident-no-actionable-claim-20260827.jsonl"), DECISION_FIELDS)
    _write(NO_ACTION_SNAPSHOTS, _read(ROOT / "jsonlog" / "incident-no-actionable-claim-20260827.snapshots.jsonl"), SNAPSHOT_FIELDS)
    _write(E6_PRELANDING_DECISIONS, e6_prelanding, DECISION_FIELDS + (
        "acquire_store_visit_called", "requested_owner", "requested_store",
        "acquire_result",
    ))
    _write(CAL3_VISIT_BUDGET_DECISIONS, cal3_visit_budget, DECISION_FIELDS + (
        "acquire_store_visit_called", "requested_owner", "requested_store",
        "acquire_result", "inventory", "equipment_optimization",
        "departure_block", "shop_selector", "town_stall_report",
    ))
    print(f"decisions={len(decisions)} first={first.isoformat()} last={last.isoformat()}")
    fixture_paths = tuple(FIXTURE_DIR.iterdir())
    print(f"ledger={len(ledger)} posted={len(posted)} bytes={sum(p.stat().st_size for p in fixture_paths)}")
    print(f"e6_prelanding={len(e6_prelanding)} first={e6_prelanding[0]['time']} last={e6_prelanding[-1]['time']}")
    print(f"cal3_visit_budget={len(cal3_visit_budget)} first={cal3_visit_budget[0]['time']} last={cal3_visit_budget[-1]['time']} bytes={CAL3_VISIT_BUDGET_DECISIONS.stat().st_size}")


if __name__ == "__main__":
    main()
