"""Paths and readers for the frozen pre-2026-09-01 emit-ownership window."""

from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "historical-emit-ownership"
DECISIONS = FIXTURE_DIR / "decisions.jsonl.gz"
LEDGER = FIXTURE_DIR / "read-batches.jsonl.gz"
POSTED = FIXTURE_DIR / "posted-characters.jsonl.gz"
EQUIP_DECISIONS = FIXTURE_DIR / "equip-swap-decisions.jsonl.gz"
EQUIP_SNAPSHOTS = FIXTURE_DIR / "equip-swap-snapshots.jsonl.gz"
NO_ACTION_DECISIONS = FIXTURE_DIR / "no-actionable-decisions.jsonl.gz"
NO_ACTION_SNAPSHOTS = FIXTURE_DIR / "no-actionable-snapshots.jsonl.gz"
E6_PRELANDING_DECISIONS = FIXTURE_DIR / "e6-prelanding-decisions.jsonl.gz"
CAL3_VISIT_BUDGET_DECISIONS = FIXTURE_DIR / "cal3-visit-budget-decisions.jsonl.gz"
IDW_BLOCK_DECISIONS = FIXTURE_DIR / "idw-block-decisions.jsonl.gz"
RESTORE_STALL_DECISIONS = FIXTURE_DIR / "restore-stall-decisions.jsonl.gz"


def rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, mode="rt", encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)
