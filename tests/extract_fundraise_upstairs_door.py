"""Extract the n1-c Yeek cave 1F fundraising-return wander boards (D19).

Source: the 2026-10-30 07:26 viewing capture of n1-c (zombie Magic-Eater,
Lv8), which wandered with fundraise:seek-upstairs-wander for 3000+ decisions
while its map memory held the up staircase [18,144].

The fixture keeps two recorded boards with their following boards, the
recorded decision rows of those boards, and the remembered terrain of the
policy checkpoint written at 07:26:48 (the flight recorder's terrain view and
the exploration state fields that decide frontiers), and the fundraising
purpose ledger entry the recorded decision rows report.
"""
import gzip
import hashlib
import json
from pathlib import Path

CAPTURE = Path(r"C:\hengband-backups\viewing-captures-1030\n1c-yeek-wander")
STATES = CAPTURE / "n1c-state.jsonl"
DECISIONS = CAPTURE / "n1c-dec.jsonl"
CHECKPOINT = CAPTURE / "jsonlog" / "checkpoints" / "policy-state.json"
# 9220: beside the closed door [11,161]; 9409: the last recorded decision.
SEQUENCES = (9220, 9409)
STATE_FIELDS = ("_probed_frontiers", "_visit_counts", "_engagement_avoid_cells",
                "_unenterable_explore_goals")
MODE_FIELDS = ("_fundraising_mode", "_returning_to_town", "_emergency_return_active",
               "_crossarea_fundraising_enforced", "_last_return_trigger",
               "_fundraising_runs_started")
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position",
                   "map_memory", "fundraising")


def rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    states = {row["turn"]: row for row in rows(STATES)}
    decisions = rows(DECISIONS)
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    boards = {}
    for sequence in SEQUENCES:
        index = next(i for i, row in enumerate(decisions)
                     if row["decision_sequence"] == sequence)
        decision = decisions[index]
        following_turn = (decisions[index + 1]["turn"] if index + 1 < len(decisions)
                          else max(states))
        boards[str(sequence)] = {
            "board": states[decision["turn"]],
            "following": states[following_turn],
            "decision": {field: decision[field] for field in DECISION_FIELDS},
        }
    case = {
        "sources": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (STATES, DECISIONS, CHECKPOINT)},
        "checkpoint_created_at": checkpoint["created_at"],
        "terrain": checkpoint["terrain"],
        "state": {field: checkpoint["state"][field] for field in STATE_FIELDS},
        "modes": {field: checkpoint["modes_and_latches"][field] for field in MODE_FIELDS},
        "boards": boards,
        "purpose": decisions[-1]["claim"]["fundraising_purpose"],
    }
    target = Path(__file__).with_name("fixtures") / "fundraise-upstairs-door-20261030.json.gz"
    with gzip.open(target, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(target, target.stat().st_size)


if __name__ == "__main__":
    main()
