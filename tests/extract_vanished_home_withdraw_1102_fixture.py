"""Freeze the n1-a life-464 07:12:40 town:blocked:survival:cure_critical_ready board.

Source: C:/hengband-backups/pdca/captures/hourly-0800-1102/
20261102-071240-town-blocked-survival-cure-critical-ready (bot-e8f860713).
Decision 2293 withdrew ドラゴン・グローブ [4,+8] {r呪} for the full-Home
discard and 2294-2295 destroyed it; the Home list of turn 3311414 no longer
holds it.  Decision 2301 opened the town end's mining cycle and 2302 stopped:
the fundraising departure was refused (no Treasure Detection) and the Home
leg's only terminal was a withdrawal of the destroyed gloves, refused as
reservation-unavailable.  Frozen: the board of turn 3311423, the Home list of
3311414, the last skill row, and decisions 2293-2295 / 2301-2302 facts.
Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-0800-1102/"
               "20261102-071240-town-blocked-survival-cure-critical-ready")
OUTPUT = Path(__file__).with_name("fixtures") / "vanished-home-withdraw-1102.json.gz"
FACTS = ("decision_sequence", "turn", "reason", "key", "messages")


def _rows(name: str) -> list[dict]:
    rows = []
    with gzip.open(CAPTURE / name, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def main() -> None:
    state = _rows("state.jsonl.gz")
    board = [r for r in state if r["type"] == "player_turn" and r["turn"] == 3311423][-1]
    knowledge = [r for r in state if r["type"] == "knowledge"]
    home = [r for r in knowledge if r["knowledge"]["category"] == "home"][-1]
    assert home["turn"] == 3311414, home["turn"]
    skill = [r for r in knowledge if r["knowledge"]["category"] == "skill_exp"][-1]
    decisions = []
    for row in _rows("bot-decisions.jsonl.gz"):
        if row.get("decision_sequence") in (2293, 2294, 2295, 2301, 2302):
            fact = {key: row.get(key) for key in FACTS}
            if row["decision_sequence"] == 2302:
                # Rows before structure stage 2 B slice 4 carry it in the claim row.
                fact["terminal_admission"] = (row.get("terminal_admission")
                                              or row["claim"]["terminal_admission"])
            decisions.append(fact)
    case = dict(
        sources={name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
                 for name in ("state.jsonl.gz", "bot-decisions.jsonl.gz")},
        board=board, home=home, skill=skill, decisions=decisions)
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, [d["reason"] for d in decisions])


if __name__ == "__main__":
    main()
