"""Freeze the n1-c life-111 Weapon Smith page of 2026-11-02 23:39 (turn 945241).

Source: C:/hengband-backups/pdca/captures/q2-ammo-1102/life-111/ (bot-9548e37f4).
The Lv21 Magic-Eater wielded a light crossbow (x3) (+6,+3) and carried 95
plain bolts; Q2's force asked an average shot of 25 (measured 18).  The shelf
held bolts (1d5) (+5,+3) (27/shot), and decision 10638 left the page
(shop:observe-and-leave, observed-page-nothing-wanted).  Frozen: the store
board of turn 945241 (state.jsonl row 311) and decisions 10637-10638 facts.
Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/q2-ammo-1102/life-111")
OUTPUT = Path(__file__).with_name("fixtures") / "q2-damage-ammo-1102.json.gz"
FACTS = ("decision_sequence", "turn", "reason", "key", "store_visit", "shop_selector")


def main() -> None:
    board = None
    with (CAPTURE / "state.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") == 945241 and (row.get("store") or {}).get("store_type") == 2:
                board = row
    assert board is not None
    decisions = []
    with (CAPTURE / "jsonlog" / "bot-decisions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("decision_sequence") in (10637, 10638):
                fact = {key: row.get(key) for key in FACTS}
                fact["carries"] = row["fixedquest_readiness"]["strategy_force"]["carries"]
                decisions.append(fact)
    case = dict(
        sources={name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
                 for name in ("state.jsonl", "jsonlog/bot-decisions.jsonl")},
        board=board, decisions=decisions)
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, [d["reason"] for d in decisions])


if __name__ == "__main__":
    main()
