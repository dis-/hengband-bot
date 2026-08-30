"""Measure emit-time store-visit ownership violations without changing policy.

Ordering is deliberate: immediately before ``choose_key`` we copy the open
visit (the state that exists before this decision's key can be posted).  After
``choose_key`` returns, but before any sender sees the key, we read that same
decision's ``decision_attribution`` and ``last_reason`` and evaluate the copied
visit.  Calls to ``acquire_store_visit`` are observed, not replaced semantically.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
from types import MethodType

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy, TOWN_TRAVEL_STORE_SYMBOLS
from hengbot.policy_types import StoreVisit, StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
POPULATIONS = {
    "equip-swap (frozen)": ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl",
    "no-actionable (frozen)": ROOT / "jsonlog" / "incident-no-actionable-claim-20260827.snapshots.jsonl",
    "bot-state-fixed (unpinned live stream)": ROOT / "jsonlog" / "bot-state-fixed.jsonl",
}


def _in_flight(visit: StoreVisit) -> bool:
    """Match town_arbiter.acquire_store_visit's four clauses exactly."""
    return bool(
        (visit.operation_posted and not visit.operation_released)
        or (visit.operation_released and not visit.operation_effect_observed)
        or (
            visit.phase == StoreVisitPhase.ENTERING
            and visit.posted_sequence is not None
        )
        or (
            visit.phase == StoreVisitPhase.LEAVING
            and (visit.posted_sequence is not None or visit.posted_turn is not None)
        )
    )


def _target_store(snapshot, key: str, acquisitions: list[dict]) -> int | None:
    """Identify the store context targeted by the emitted key when observable."""
    if acquisitions:
        return acquisitions[-1]["store_type"]
    if snapshot.store is not None:
        return snapshot.store.store_type
    for store_type, symbol in enumerate(TOWN_TRAVEL_STORE_SYMBOLS):
        if key == f"\x1b`n{symbol}.":
            return store_type
    return None


def _instrument_acquires(policy: HengbotPolicy, calls: list[dict]) -> None:
    arbiter = policy._town_turn_arbiter
    original = arbiter.acquire_store_visit

    def observed(_arbiter, **kwargs):
        result = original(**kwargs)
        calls.append({
            "store_type": kwargs["store_type"],
            "owner": kwargs["owner"],
            "granted": result is not None,
        })
        return result

    arbiter.acquire_store_visit = MethodType(observed, arbiter)


def measure(path: Path) -> dict:
    definitions = find_monrace_definitions(path, None)
    if definitions is None:
        raise RuntimeError(f"MonraceDefinitions.jsonc was not found for {path}")
    knowledge = load_monrace_knowledge(definitions)
    policy = HengbotPolicy(monrace_knowledge=knowledge)
    acquire_calls: list[dict] = []
    _instrument_acquires(policy, acquire_calls)

    totals = Counter()
    violations = []
    with path.open(encoding="utf-8-sig") as stream:
        for row_index, line in enumerate(stream):
            if not line.strip():
                continue
            totals["snapshot_rows"] += 1
            snapshot = parse_snapshot(json.loads(line), knowledge)

            # PRE-EMIT SAMPLE: copied before choose_key can return a postable key.
            visit = copy.copy(policy._store_visit)
            acquire_calls.clear()
            key = policy.choose_key(snapshot)
            # POST-DECISION SAMPLE: attribution/reason belong to the returned key.
            attribution = policy.decision_attribution
            reason = policy.last_reason

            if not (snapshot.in_town or snapshot.store is not None):
                continue
            totals["decisions"] += 1
            if key:
                totals["keys"] += 1
            if visit is not None and visit.phase != StoreVisitPhase.CLOSED:
                totals["open_visits"] += 1
            inflight = visit is not None and _in_flight(visit)
            if inflight:
                totals["in_flight_visits"] += 1
            if not key or visit is None:
                continue
            owner = policy._store_visit_arbiter_owner(visit)
            mismatch = attribution != owner
            if mismatch:
                totals["wide_violations"] += 1
            if not inflight or not mismatch:
                continue
            target_store = _target_store(snapshot, key, acquire_calls)
            violations.append({
                "row": row_index,
                "attribution": attribution,
                "visit_owner": owner,
                "phase": visit.phase.value,
                "reason": reason,
                "visit_store": visit.store_type,
                "target_store": target_store,
                "same_store": target_store == visit.store_type,
                "no_acquire": not acquire_calls,
            })
    totals["violations"] = len(violations)
    totals["collapse_violations"] = 0
    return {"totals": dict(totals), "violations": violations}


def _print_report(label: str, result: dict) -> None:
    totals = result["totals"]
    print(f"population={label}")
    print(
        " ".join(
            f"{name}={totals.get(name, 0)}"
            for name in (
                "snapshot_rows", "decisions", "keys", "open_visits",
                "in_flight_visits", "violations",
            )
        )
    )
    print(
        f"controls exact={totals.get('violations', 0)} "
        f"widen_open={totals.get('wide_violations', 0)} "
        f"collapse_owner={totals.get('collapse_violations', 0)}"
    )
    violations = result["violations"]
    print(
        f"same_target_store={sum(v['same_store'] for v in violations)} "
        f"no_acquire_this_turn={sum(v['no_acquire'] for v in violations)}"
    )
    grouped = defaultdict(list)
    for violation in violations:
        triple = (
            violation["attribution"], violation["visit_owner"],
            violation["phase"],
        )
        grouped[triple].append(violation)
    for triple, rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        examples = [row["row"] for row in rows[:5]]
        reasons = sorted({row["reason"] for row in rows})
        print(
            f"triple={triple!r} count={len(rows)} examples={examples!r} "
            f"reasons={reasons!r}"
        )
    stores = Counter(row["visit_store"] for row in violations)
    phases = Counter(row["phase"] for row in violations)
    print(f"visit_store_types={dict(stores.most_common())}")
    print(f"visit_phases={dict(phases.most_common())}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("population", choices=(*POPULATIONS, "all"), default="all", nargs="?")
    args = parser.parse_args()
    selected = POPULATIONS if args.population == "all" else {
        args.population: POPULATIONS[args.population]
    }
    failed_control = False
    for label, path in selected.items():
        result = measure(path)
        _print_report(label, result)
        totals = result["totals"]
        failed_control |= totals.get("collapse_violations", 0) != 0
        if totals.get("violations", 0) and (
            totals.get("wide_violations", 0) <= totals.get("violations", 0)
        ):
            failed_control = True
            print("CONTROL FAILURE: widening open visits did not raise violations")
    return int(failed_control)


if __name__ == "__main__":
    raise SystemExit(main())
