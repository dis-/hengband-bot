"""Freeze the n1-b life-295 19:49:09 town:blocked:survival:remove_curse_ready board.

Source: C:/hengband-backups/pdca/captures/hourly-2000-1102/
n1-b-20261102-194909-town-blocked-survival-remove-curse-ready (bot-ec1f68398).
Decision 27248 withdrew 財宝感知の巻物 (the Home list of turn 1231601 no
longer holds it, its take was confirmed) while the shovel stayed queued
behind it; 27251 stopped with the Home leg's terminal refused as
reservation-unavailable.  Frozen: the board of turn 1231613, the Home list
of 1231601, the skill row of 1228051 (incident snapshot tail), and decisions
27248-27251 facts.  Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-2000-1102/"
               "n1-b-20261102-194909-town-blocked-survival-remove-curse-ready")
SKILL_SOURCE = "incident/snapshots-current.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "confirmed-home-take-1102.json.gz"
FACTS = ("decision_sequence", "turn", "reason", "key", "messages", "procurement_requirements")


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
    board = [r for r in state if r["type"] == "player_turn" and r["turn"] == 1231613][-1]
    home = [r for r in state if r["type"] == "knowledge"
            and r["knowledge"]["category"] == "home"][-1]
    assert home["turn"] == 1231601, home["turn"]
    skill = [r for r in _rows(SKILL_SOURCE) if r.get("type") == "knowledge"
             and r["knowledge"]["category"] == "skill_exp"][-1]
    decisions = []
    for row in _rows("bot-decisions.jsonl.gz"):
        if row.get("decision_sequence") in (27248, 27249, 27250, 27251):
            fact = {key: row.get(key) for key in FACTS}
            fact["departure_failed"] = (row.get("departure_block") or {}).get("failed")
            fact["terminal_admission"] = row["claim"]["terminal_admission"]
            decisions.append(fact)
    case = dict(
        sources={name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
                 for name in ("state.jsonl.gz", "bot-decisions.jsonl.gz", SKILL_SOURCE)},
        board=board, home=home, skill=skill, decisions=decisions)
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, [d["reason"] for d in decisions])


if __name__ == "__main__":
    main()
