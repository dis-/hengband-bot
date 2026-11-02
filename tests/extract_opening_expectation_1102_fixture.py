"""Freeze the n1-c life-104 13:49 opening-route board (quest:blocked:opening-route).

Source: C:/hengband-backups/pdca/captures/hourly-1400-1102/life-104/captures/
20261102-134929-quest-blocked-opening-route (bot-59230b90d).  The third
session after the Q1 purchases: skill-exp knowledge, periodic:game-save,
periodic:character-dump, then quest:blocked:opening-route
(quest-request-unavailable) on the unchanged board at turn 84217.  Frozen:
the last player-turn board, the last skill_exp knowledge row and the recorded
facts of that session's decisions.  Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


CAPTURE = Path("C:/hengband-backups/pdca/captures/hourly-1400-1102/life-104/captures/"
               "20261102-134929-quest-blocked-opening-route")
OUTPUT = Path(__file__).with_name("fixtures") / "opening-expectation-1102.json.gz"
TURN = 84217
DECISION_FACTS = ("decision_sequence", "turn", "reason", "key")


def main() -> None:
    with gzip.open(CAPTURE / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream.read().splitlines()]
    board = [row for row in rows if row.get("type") == "player_turn" and row.get("turn") == TURN][-1]
    skill = [row for row in rows if row.get("type") == "knowledge"
             and row["knowledge"].get("category") == "skill_exp"][-1]
    with gzip.open(CAPTURE / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        decisions = [json.loads(line) for line in stream]
    # The last session: from its session-start row to the stop.
    start = max(index for index, row in enumerate(decisions) if row.get("kind") == "session-start")
    session = [{key: row[key] for key in DECISION_FACTS} for row in decisions[start + 1:]]
    case = dict(
        sources={name: hashlib.sha256((CAPTURE / name).read_bytes()).hexdigest()
                 for name in ("state.jsonl.gz", "bot-decisions.jsonl.gz")},
        board=board, skill=skill, decisions=session,
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
