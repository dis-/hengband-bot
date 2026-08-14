"""Replay the frozen Q34 navigation snapshots through the public policy boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies


def replay(args: argparse.Namespace) -> list[dict[str, object]]:
    monraces = load_monrace_knowledge(args.monraces)
    policy = HengbotPolicy(
        monrace_knowledge=monraces,
        quest_knowledge=load_quest_knowledge(args.quests),
        quest_strategies=load_quest_strategies(args.strategies),
    )
    decisions: list[dict[str, object]] = []
    with args.snapshots.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            snapshot = parse_snapshot(json.loads(line), monraces)
            key = policy.choose_key(snapshot)
            decisions.append(
                {
                    "line": line_number,
                    "turn": snapshot.turn,
                    "position": [
                        snapshot.player.position.y,
                        snapshot.player.position.x,
                    ],
                    "key": key,
                    "reason": policy.last_reason,
                }
            )
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshots", type=Path)
    parser.add_argument("--strategies", type=Path, required=True)
    parser.add_argument("--quests", type=Path, required=True)
    parser.add_argument("--monraces", type=Path, required=True)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    decisions = replay(args)
    after_lantern = [
        decision
        for decision in decisions
        if decision["position"] == [10, 20] and decision["line"] >= 18
    ]
    result = {
        "decisions": decisions,
        "post_lantern_keys": [decision["key"] for decision in after_lantern[:8]],
        "post_lantern_reasons": [
            decision["reason"] for decision in after_lantern[:8]
        ],
        "opening_door_unreachable": sum(
            decision["reason"] == "quest-strategy:opening-door-unreachable"
            for decision in decisions
        ),
    }
    expected_post_lantern_keys = ["8"] * 8
    result["expected_post_lantern_keys"] = expected_post_lantern_keys
    result["progresses"] = (
        result["post_lantern_keys"] == expected_post_lantern_keys
        and result["opening_door_unreachable"] == 0
    )
    if args.summary_only:
        result.pop("decisions")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["progresses"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
