"""Freeze the 2026-11-02 15:35-15:38 n1-c life-105 weapon swap loop (hourly-1600-1102).

Sources, copied under C:/hengband-backups/pdca/captures/hourly-1600-1102/:

  incident-life-105-20261102-153812-loop-detected/
      snapshots/snapshots-current.jsonl.gz  the ring of the looping session
          (bot-9afd9203e); rows 265 (War Hammer worn, Pike in Home, after
          the deposit), 266 (the same, outside), 278 (Pike worn, War Hammer
          in Home, after the deposit) and 279 (the same, outside).
      character-calibration.json  the session's equipped-C-screen calibration.
      knowledge-rows.jsonl  line 1: the skill_exp row (~f) the restarted
          process read at turn 1485835 (the stop turn, same character).
  n1-c-life-105-20261102-153817-loop-detected/bot-decisions.jsonl.gz
      decisions 1411 and 1419 (the atomic withdrawals of each weapon, with
      their band descents).

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
INCIDENT = ROOT / "incident-life-105-20261102-153812-loop-detected"
CAPTURE = ROOT / "n1-c-life-105-20261102-153817-loop-detected"
OUTPUT = Path(__file__).with_name("fixtures") / "pike-hammer-swap-1102.json.gz"
BOARDS = {
    "hammer-worn-in-home": 265,
    "hammer-worn-outside": 266,
    "pike-worn-in-home": 278,
    "pike-worn-outside": 279,
}


def _withdraw_decisions() -> dict:
    rows = {}
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("reason") != "equipment-transaction:atomic-withdraw":
                continue
            facts = {key: row[key] for key in ("decision_sequence", "turn", "reason", "key")}
            optimization = row["equipment_optimization"]
            facts["band_descent"] = optimization["band_descent"][-2:]
            facts["transaction_next"] = optimization["transaction_next"]
            rows[str(row["decision_sequence"])] = facts
            if len(rows) == 2:
                break
    return rows


def main() -> None:
    ring_path = INCIDENT / "snapshots" / "snapshots-current.jsonl.gz"
    ring = ring_rows(ring_path.read_bytes())
    knowledge = INCIDENT / "knowledge-rows.jsonl"
    skill = json.loads(knowledge.read_text(encoding="utf-8").splitlines()[0])
    assert skill["knowledge"]["category"] == "skill_exp"
    calibration = INCIDENT / "character-calibration.json"
    data = {
        "sources": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ring_path, knowledge, calibration)
        },
        "boards": {name: ring[index] for name, index in BOARDS.items()},
        "calibration": json.loads(calibration.read_text(encoding="utf-8")),
        "skill_exp": skill,
        "decisions": _withdraw_decisions(),
    }
    payload = gzip.compress(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0)
    OUTPUT.write_bytes(payload)
    print(OUTPUT, len(payload), hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    main()
