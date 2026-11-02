"""Freeze the n1-b life-294 blind mining boards (2026-11-02 13:14).

Source: C:/hengband-backups/pdca/captures/n1b-churn-1102/life-294-incidents/
(bot-e7f0e2ff6, warrior Lv8, Yeek cave 1F).  A gas trap blinded the mining
run at turn 144615.  20261102-131436-loop-detected: the last ring board of
turn 144790 (the dig into the vein it had already dug, 「そこは掘れない。」, the
stalled-command stop).  20261102-131452-loop-detected: the last ring board of
turn 145527 (the restarted process waiting '5' with
fundraise:upstairs-not-found, the cell-guard stop).  Each case keeps its
capture's remembered terrain and fundraising modes (policy-state.json), the
last skill row before the board and the recorded decision rows of the board.
Only this tool reads the captures.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


BASE = Path("C:/hengband-backups/pdca/captures/n1b-churn-1102/life-294-incidents")
CASES = {"dig": ("20261102-131436-loop-detected", 144790),
         "wait": ("20261102-131452-loop-detected", 145527)}
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-blind-mining-1102.json.gz"
MODE_FIELDS = ("_fundraising_mode", "_returning_to_town", "_crossarea_fundraising_enforced",
               "_emergency_return_active", "_last_return_trigger")
DECISION_FACTS = ("decision_sequence", "turn", "reason", "key", "position", "messages")


def decisions(path: Path, turn: int) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # the bounded tail starts inside a record
        if row.get("turn") == turn:
            rows.append({key: row.get(key) for key in DECISION_FACTS})
    return rows


def main() -> None:
    case = {"sources": {}}
    for name, (stamp, turn) in CASES.items():
        capture = BASE / stamp
        ring = capture / "snapshots" / "snapshots-current.jsonl.gz"
        rows = ring_rows(ring.read_bytes())
        board = [row for row in rows if row["type"] == "player_turn" and row["turn"] == turn][-1]
        skill = [row for row in rows if row["type"] == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp" and row["turn"] <= turn]
        state = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
        for source in (ring, capture / "policy-state.json", capture / "decision-tail.jsonl"):
            case["sources"][f"{stamp}/{source.name}"] = hashlib.sha256(
                source.read_bytes()).hexdigest()
        case[name] = dict(
            board=board, skill=skill[-1] if skill else None,
            terrain=state["terrain"],
            modes={field: state["modes_and_latches"].get(field) for field in MODE_FIELDS},
            decisions=decisions(capture / "decision-tail.jsonl", turn),
        )
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size,
          {name: [(d["reason"], d["key"]) for d in case[name]["decisions"]][-3:] for name in CASES})


if __name__ == "__main__":
    main()
