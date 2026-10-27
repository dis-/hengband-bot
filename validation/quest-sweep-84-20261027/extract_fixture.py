"""Rebuild the recorded boards and measured prior sweep certificates."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.quest_strategies import load_quest_strategies


ROOT = Path(__file__).resolve().parents[2]
EDIT = Path("C:/hengband/lib/edit")
SOURCES = (
    ("20261027-072914-loop-detected", 31, (26621, 26622, 26623, 26624)),
    ("20261027-083813-loop-detected", 22,
     (15411, 15412, 15413, 15414, 15415, 15416)),
)


def main():
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "C:/hengband-backups/viewing-captures-1027"
    )
    monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    quests = load_quest_knowledge(EDIT / "quests")
    profiles = load_quest_strategies(ROOT / "strategy/quests")
    cases = []
    for source, qid, sequences in SOURCES:
        directory = base / source
        with gzip.open(directory / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
            boards = {board["turn"]: board for board in map(json.loads, stream)}
        with gzip.open(directory / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
            decisions = list(map(json.loads, stream))
        rows = []
        for decision in decisions:
            if decision["decision_sequence"] not in sequences or decision["reason"] == "loop-detected":
                continue
            rows.append({
                "board": boards[decision["turn"]],
                "decision": {key: decision[key] for key in (
                    "decision_sequence", "turn", "position", "key", "reason", "threat_prediction"
                )},
                "goal": decision["claim"]["goal"],
            })
        battlefield = quests[qid].battlefield
        navigator = QuestFloorNavigator(qid, battlefield)
        targets = (
            {Position(y, x) for y, x in battlefield.terrain
             if navigator._static_walkable(Position(y, x))}
            if profiles[qid].engagement_plan.get("placement_sweep_scope") == "battlefield"
            else {Position(*position) for position, _race in battlefield.monster_placements}
        )
        policy = HengbotPolicy(monrace_knowledge=monraces)
        surveyed = set()
        for decision in decisions:
            if decision["decision_sequence"] >= sequences[0]:
                break
            if decision["reason"] != "quest-strategy:placement-sweep" or decision["turn"] not in boards:
                continue
            board = parse_snapshot(boards[decision["turn"]], monraces)
            if board.visible_monsters:
                continue
            surveyed.update(
                position for position in targets
                if (grid := board.grid_at(position)) is not None
                and grid.known and not grid.has_monster
                and policy._quest_cell_confirmed_empty(board, position)
            )
        cases.append({
            "source": source, "quest_id": qid,
            "sha256": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                       for name in ("state.jsonl.gz", "bot-decisions.jsonl.gz")},
            "rows": rows,
            "surveyed_before_rows": [[position.y, position.x] for position in sorted(surveyed)],
        })
    payload = gzip.compress(json.dumps(cases, ensure_ascii=False).encode("utf-8"), mtime=0)
    target = ROOT / "tests/fixtures/quest-sweep-hold-20261027.json.gz"
    if "--check" in sys.argv:
        if target.read_bytes() != payload:
            raise SystemExit("recorded fixture differs")
        print("recorded fixture matches source captures byte for byte")
    else:
        target.write_bytes(payload)


if __name__ == "__main__":
    main()
