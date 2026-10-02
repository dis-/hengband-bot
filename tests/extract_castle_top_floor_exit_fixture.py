"""Freeze the Castle 20F boards before the '<' that left the dungeon (2026-10-02 11:50).

Source (read-only): ``jsonlog/autorecover-20261002-115120-loop-detected.*`` of
the live checkout (commit 9cf0af6f).  That process started before the
capture's window (its first recorded decision is 911), so it cannot be
replayed from its attach row.  Instead a fresh policy is started on the board
of decision 1063 (state row 45): from there it reproduces every live key
through 1076 (``status-threat:stairs`` '<' on Castle 20F, the dungeon's top
floor, minDepth 20).  State row 59 is the arrival: floor (0, 0, 0), the
surface wilderness at the Castle entrance.

Each of these decisions drained exactly one state row
(``timing.jsonl_drain_records`` == 1), so row 45 + n is the input of decision
1063 + n; the extraction checks the turn and position of every pair.

A fresh process asks for the ~f skill list before its first decision.  The
capture holds no reply for this process, so the frozen file carries the
``skill_exp`` knowledge row of the next process (11:51:24, capture
``autorecover-20261002-115150-loop-detected``, state row 42; same character,
level 31); the test feeds it to ``consume_skill_knowledge`` before the first
board (declared wall).

Only this tool reads the capture; the committed test reads the frozen files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path("C:/hengband/bot-client/jsonlog")
CAPTURE = "autorecover-20261002-115120-loop-detected"
NEXT = "autorecover-20261002-115150-loop-detected"
DECISIONS = LIVE / f"{CAPTURE}.bot-decisions.jsonl.gz"
STATE = LIVE / f"{CAPTURE}.bot-state-fixed.jsonl.gz"
NEXT_STATE = LIVE / f"{NEXT}.bot-state-fixed.jsonl.gz"
OUTPUT = ROOT / "tests" / "fixtures" / "castle-top-floor-exit-20261002.jsonl.gz"
BOUNDARIES = ROOT / "tests" / "fixtures" / "castle-top-floor-exit-20261002.boundaries.json"
FIRST_ROW, FIRST_DECISION = 45, 1063
LAST_DECISION = 1077  # the first wilderness decision (arrival board)
KNOWLEDGE_ROW = 42


def _lines(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return stream.read().splitlines(keepends=True)


def main() -> None:
    decisions = {
        row["decision_sequence"]: row
        for row in map(json.loads, _lines(DECISIONS))
        if row.get("decision_sequence") is not None
    }
    lines = _lines(STATE)
    kept = []
    recorded = []
    for sequence in range(FIRST_DECISION, LAST_DECISION + 1):
        decision = decisions[sequence]
        line = lines[FIRST_ROW + sequence - FIRST_DECISION]
        row = json.loads(line)
        assert row["turn"] == decision["turn"], sequence
        assert (row["player"]["y"], row["player"]["x"]) == (
            decision["position"]["y"], decision["position"]["x"]
        ), sequence
        if sequence < LAST_DECISION:
            assert int(decision["timing"]["jsonl_drain_records"]) == 1, sequence
        kept.append(line.replace("\r\n", "\n"))
        floor = decision["floor"]
        recorded.append([
            sequence, decision["turn"], decision["key"], decision["reason"],
            [decision["position"]["y"], decision["position"]["x"]],
            [floor["dungeon_id"], floor["level"], floor["quest_id"]],
        ])
    knowledge = _lines(NEXT_STATE)[KNOWLEDGE_ROW]
    assert json.loads(knowledge)["type"] == "knowledge"
    assert json.loads(knowledge)["knowledge"]["category"] == "skill_exp"
    payload = knowledge.replace("\r\n", "\n") + "".join(kept)
    OUTPUT.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    boundaries = {
        "source": {
            str(path.name): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (DECISIONS, STATE, NEXT_STATE)
        },
        "state_rows": [FIRST_ROW, FIRST_ROW + LAST_DECISION - FIRST_DECISION],
        "knowledge_row": [NEXT, KNOWLEDGE_ROW],
        "recorded_fields": [
            "decision_sequence", "turn", "key", "reason", "position", "floor",
        ],
        "recorded": recorded,
    }
    BOUNDARIES.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    for path in (OUTPUT, BOUNDARIES):
        print(path.name, hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
