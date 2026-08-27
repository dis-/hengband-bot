"""Verify completed town-decision attribution against a frozen reason map.

The fixture is a regression pin: a known reason whose attribution changes is a
failure.  A reason absent from the fixture is new coverage, is reported, and is
not a failure.  Empty reasons are defective records, counted separately from
the non-empty decision-reason owner histogram.
"""

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
EXPECTED_PATH = ROOT / "tests" / "fixtures" / "t1-reason-attribution.json"


def _arbiter() -> TownTurnArbiter:
    return HengbotPolicy()._town_turn_arbiter


def capture_attributions(path: Path) -> list[tuple[str, str]]:
    definitions = find_monrace_definitions(path, None)
    if definitions is None:
        raise RuntimeError("MonraceDefinitions.jsonc was not found")
    knowledge = load_monrace_knowledge(definitions)
    policy = HengbotPolicy(monrace_knowledge=knowledge)
    attributions: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            snapshot = parse_snapshot(json.loads(line), knowledge)
            policy.choose_key(snapshot)
            if snapshot.in_town or snapshot.store is not None:
                attributions.append((policy.last_reason, policy.decision_attribution))
    return attributions


def live_tail_attributions(limit: int) -> list[tuple[str, str]]:
    rows = []
    with (ROOT / "jsonlog" / "bot-decisions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    arbiter = _arbiter()
    selected = rows[-limit:] if limit else rows
    return [
        (row.get("reason", ""), arbiter.decision_owner_for_reason(row.get("reason", "")))
        for row in selected
        if row.get("floor", {}).get("dungeon_id") == 0
        or row.get("store_type") is not None
    ]


def all_attributions() -> list[tuple[str, str]]:
    attributions = live_tail_attributions(0)
    for path in CAPTURES.values():
        attributions.extend(capture_attributions(path))
    return attributions


def generated_fixture() -> dict[str, str]:
    mappings: dict[str, str] = {}
    for reason, owner in all_attributions():
        if not reason:
            continue
        previous = mappings.setdefault(reason, owner)
        if previous != owner:
            raise RuntimeError(
                f"inconsistent attribution for {reason!r}: {previous!r} != {owner!r}"
            )
    return dict(sorted(mappings.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", choices=(*CAPTURES, "live-tail"))
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--write-fixture", action="store_true")
    args = parser.parse_args()
    if args.write_fixture:
        EXPECTED_PATH.write_text(
            json.dumps(generated_fixture(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    attributions = (
        live_tail_attributions(args.limit)
        if args.capture == "live-tail"
        else capture_attributions(CAPTURES[args.capture])
    )
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    non_empty = [(reason, owner) for reason, owner in attributions if reason]
    empty_reason_rows = len(attributions) - len(non_empty)
    mismatches = [
        (reason, expected[reason], attribution)
        for reason, attribution in non_empty
        if reason in expected and expected[reason] != attribution
    ]
    unseen_reasons = sorted({reason for reason, _ in non_empty if reason not in expected})
    owners = Counter(attribution for _, attribution in non_empty)
    print(" ".join(f"{owner}={owners[owner]}" for owner in sorted(owners)))
    uncovered = owners["unregistered"] + owners["misc"]
    print(
        f"unregistered+misc={uncovered} mismatches={len(mismatches)} "
        f"unseen_reasons={len(unseen_reasons)} empty_reason_rows={empty_reason_rows} "
        f"total={sum(owners.values())}"
    )
    for reason, wanted, got in mismatches[:10]:
        print(f"attribution mismatch: {reason!r}: expected={wanted!r} actual={got!r}")
    for reason in unseen_reasons:
        print(f"unseen reason: {reason!r}")
    expected_empty_rows = 4 if args.capture == "live-tail" and args.limit == 0 else 0
    return 1 if (
        uncovered or mismatches or empty_reason_rows != expected_empty_rows
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
