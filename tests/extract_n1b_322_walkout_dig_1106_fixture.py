"""Freeze the n1-b life-322 mining walk-out boards (2026-11-06 02:37-02:43).

Source: C:/hengband-backups/pdca/captures/n1b-322-1f-1106/life-322/ (bot-f67755a8f,
Magic-Eater Lv14, Yeek cave 1F).  A floating eye woke at (5,60) beside the digging
player (turn 959971), a Teleportation landed in the walled western rooms, and the one
corridor back ran past the eye: its ring held the walk, exploration had nothing left,
and the mining run wandered until the loop guard at 02:43:45.
Frozen: the eye's board (cap-0243/eye-boards), the ring boards of a recorded wander and
of a recorded wait beside the trap, the stop capture's remembered terrain and modes,
the exploration ledger, the last skill row and the recorded decision rows of the boards.
Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


LIFE = Path("C:/hengband-backups/pdca/captures/n1b-322-1f-1106/life-322")
CAPTURE = LIFE / "cap-0243"
RING = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
EYE_BOARDS = CAPTURE / "eye-boards.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-322-walkout-dig-1106.json.gz"
EYE_TURN = 959971
WANDER_TURN = 969503
BESIDE_TRAP_TURN = 973095
MODE_FIELDS = ("_returning_to_town", "_fundraising_mode", "_crossarea_fundraising_enforced",
               "_fundraising_runs_started")
DECISION_FACTS = ("decision_sequence", "turn", "reason", "key", "position", "rung")


def _lines(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # the bounded tail starts inside a record


def main() -> None:
    rows = ring_rows(RING.read_bytes())
    board = {row["turn"]: row for row in rows if row["turn"] in (WANDER_TURN, BESIDE_TRAP_TURN)}
    eye = next(row for row in _lines(EYE_BOARDS) if row["turn"] == EYE_TURN)
    state = json.loads((CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    decisions = [
        {key: row.get(key) for key in DECISION_FACTS}
        for row in _lines(LIFE / "decisions-tail.jsonl.gz")
        if row.get("turn") in (EYE_TURN, WANDER_TURN, BESIDE_TRAP_TURN)
    ]
    skill = next(_lines(LIFE / "skill.json.gz"))
    case = dict(
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (RING, EYE_BOARDS, CAPTURE / "policy-state.json",
                              LIFE / "exploration-ledger.json", LIFE / "skill.json.gz")},
        eye_board=eye, wander_board=board[WANDER_TURN], beside_trap_board=board[BESIDE_TRAP_TURN],
        skill=skill, terrain=state["terrain"],
        modes={field: state["modes_and_latches"].get(field) for field in MODE_FIELDS},
        paralyzer_avoid_cells=state["state"]["_paralyzer_avoid_cells"],
        ledger=json.loads((LIFE / "exploration-ledger.json").read_text(encoding="utf-8")),
        decisions=decisions,
    )
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size, [(d["turn"], d["reason"], d["key"]) for d in decisions])


if __name__ == "__main__":
    main()
