"""Measure town decision-owner coverage on captures or the frozen live tail."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.town_arbiter import TownTurnArbiter

from replay_key_equality import CAPTURES


ROOT = Path(__file__).resolve().parents[1]


def _arbiter() -> TownTurnArbiter:
    return HengbotPolicy()._town_turn_arbiter


def capture_owners(path: Path) -> Counter[str]:
    definitions = find_monrace_definitions(path, None)
    if definitions is None:
        raise RuntimeError("MonraceDefinitions.jsonc was not found")
    knowledge = load_monrace_knowledge(definitions)
    policy = HengbotPolicy(monrace_knowledge=knowledge)
    owners: Counter[str] = Counter()
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            snapshot = parse_snapshot(json.loads(line), knowledge)
            policy.choose_key(snapshot)
            if snapshot.in_town or snapshot.store is not None:
                owners[policy.decision_owner] += 1
    return owners


def live_tail_owners(limit: int) -> Counter[str]:
    rows = []
    with (ROOT / "jsonlog" / "bot-decisions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    arbiter = _arbiter()
    return Counter(
        arbiter.decision_owner_for_reason(row.get("reason", ""))
        for row in rows[-limit:]
        if row.get("floor", {}).get("dungeon_id") == 0
        or row.get("store_type") is not None
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", choices=(*CAPTURES, "live-tail"))
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()
    owners = (
        live_tail_owners(args.limit)
        if args.capture == "live-tail"
        else capture_owners(CAPTURES[args.capture])
    )
    print(" ".join(f"{owner}={owners[owner]}" for owner in sorted(owners)))
    uncovered = owners["unregistered"] + owners["misc"]
    print(f"unregistered+misc={uncovered} total={sum(owners.values())}")
    return 1 if uncovered else 0


if __name__ == "__main__":
    raise SystemExit(main())
