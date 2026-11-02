"""Freeze the 2026-11-02 15:49 n1-c life-106 shop-required-operation-uncomposable stop.

Sources, copied under C:/hengband-backups/pdca/captures/hourly-1600-1102/:

  incident-life-106-20261102-154929-town-blocked-shop-required-operation-uncomposable/
      snapshots/snapshots-current.jsonl.gz  the ring of the stopped session
          (bot-9afd9203e); rows 3662 (the Home page, one item), 3663 (outside,
          before the travel to the Magic shop), 3666 and 3667 (the Magic shop
          before the first two buys) and 3674 (the page after the eighth
          operation, the stop board).
      policy-state.json  ``_me_staff_sequence`` at the stop.
      skill-row-first.jsonl  the earliest skill_exp row left in the life's
          state.jsonl (turn 1310445; the earlier rows were rotated away).
  n1-c-life-106-20261102-154931-town-blocked-shop-required-operation-uncomposable/
      bot-decisions.jsonl.gz  decisions 3529-3538 (the entry and the stop).

Only this extraction tool reads the captures; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-1600-1102")
NAME = "20261102-154929-town-blocked-shop-required-operation-uncomposable"
INCIDENT = ROOT / f"incident-life-106-{NAME}"
CAPTURE = ROOT / "n1-c-life-106-20261102-154931-town-blocked-shop-required-operation-uncomposable"
OUTPUT = Path(__file__).with_name("fixtures") / "me-second-identify-staff-1102.json.gz"
BOARDS = {"home": 3662, "outside": 3663, "shop-first": 3666, "shop-second": 3667,
          "shop-stop": 3674}


def _decisions() -> list[dict]:
    rows = []
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["decision_sequence"] < 3529:
                continue
            rows.append({
                "decision_sequence": row["decision_sequence"], "turn": row["turn"],
                "reason": row["reason"], "key": row["key"],
                "ops": ((row.get("in_store") or {}).get("operation") or {}).get("ops"),
                "required": (row.get("shop_selector") or {}).get("required-page-continuation"),
                "optimization_depth": row["equipment_optimization"].get("optimization_depth"),
            })
    return rows


def main() -> None:
    ring_path = INCIDENT / "snapshots" / "snapshots-current.jsonl.gz"
    ring = ring_rows(ring_path.read_bytes())
    state_path = INCIDENT / "policy-state.json"
    skill_path = INCIDENT / "skill-row-first.jsonl"
    data = {
        "sources": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (ring_path, state_path, skill_path)},
        "boards": {name: ring[index] for name, index in BOARDS.items()},
        "staff_sequence": json.loads(state_path.read_text(encoding="utf-8"))
        ["state"]["_me_staff_sequence"],
        "skill_exp": json.loads(skill_path.read_text(encoding="utf-8")),
        "decisions": _decisions(),
    }
    payload = gzip.compress(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0)
    OUTPUT.write_bytes(payload)
    print(OUTPUT, len(payload), hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    main()
