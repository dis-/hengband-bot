"""Measure four emit-time store-visit invariants without changing policy.

The pre/post ordering is deliberate: copy the visit and targeting context
immediately before ``choose_key``; read attribution and reason immediately
after it returns, before any sender can post the key.  Acquisitions are only
observed.  Every form is evaluated by its own predicate on emitting decisions
whose copied visit satisfies the arbiter's four-clause in-flight definition.
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
QUOTED_B_SUBTRACTION = {
    "equip-swap (frozen)": 3,
    "no-actionable (frozen)": 22,
    "bot-state-fixed (unpinned live stream)": 132,
}

# These are the visit-owner codomain values actually produced by
# _store_visit_arbiter_owner for ordinary store visits.  Attribution families
# outside it have no coarse image and are reported, not silently discarded.
COARSE_ATTRIBUTION = {
    "equipment-txn": "equipment-txn",
    "town-plan": "town-plan",
    "store-router": "store-router",
    "shop-buy": "shop-buy",
    "home-visit": "home-visit",
}
FORMS = ("A", "B", "C", "D")


def _in_flight(visit: StoreVisit) -> bool:
    """Match town_arbiter.acquire_store_visit's four clauses exactly."""
    return bool(
        (visit.operation_posted and not visit.operation_released)
        or (visit.operation_released and not visit.operation_effect_observed)
        or (visit.phase == StoreVisitPhase.ENTERING and visit.posted_sequence is not None)
        or (
            visit.phase == StoreVisitPhase.LEAVING
            and (visit.posted_sequence is not None or visit.posted_turn is not None)
        )
    )


def _stepped_store(snapshot, key: str) -> int | None:
    if len(key) != 1:
        return None
    delta = HengbotPolicy._movement_delta_for_key(key)
    if delta is None:
        return None
    position = snapshot.player.position
    grid = snapshot.grid_at(type(position)(position.x + delta[0], position.y + delta[1]))
    return None if grid is None else grid.store_number


def _target_store(snapshot, key: str, approach_store: int | None) -> tuple[int | None, str]:
    """Derive the emitted key's target store from its pre-emission context."""
    if snapshot.store is not None:
        return snapshot.store.store_type, "snapshot.store.store_type"
    if approach_store is not None:
        return approach_store, "_shopping_approach_store_type"
    for store_type, symbol in enumerate(TOWN_TRAVEL_STORE_SYMBOLS):
        if key == f"\x1b`n{symbol}.":
            return store_type, "native-travel-key"
    stepped = _stepped_store(snapshot, key)
    if stepped is not None:
        return stepped, "stepped-onto-store-grid"
    return None, "undetermined"


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


def _predicates(
    *, attribution: str, owner: str, visit_store: int,
    target_store: int | None, acquire_calls: list[dict],
) -> dict[str, bool]:
    """Evaluate each candidate directly; none is subtraction-derived."""
    coarse = COARSE_ATTRIBUTION.get(attribution)
    return {
        "A": attribution != owner,
        "B": target_store is not None and target_store != visit_store,
        "C": coarse is not None and coarse != owner,
        "D": not any(call["granted"] for call in acquire_calls),
    }


def measure(path: Path) -> dict:
    definitions = find_monrace_definitions(path, None)
    if definitions is None:
        raise RuntimeError(f"MonraceDefinitions.jsonc was not found for {path}")
    knowledge = load_monrace_knowledge(definitions)
    policy = HengbotPolicy(monrace_knowledge=knowledge)
    acquire_calls: list[dict] = []
    _instrument_acquires(policy, acquire_calls)
    totals = Counter()
    rows = []

    with path.open(encoding="utf-8-sig") as stream:
        for row_index, line in enumerate(stream):
            if not line.strip():
                continue
            totals["snapshot_rows"] += 1
            snapshot = parse_snapshot(json.loads(line), knowledge)
            visit = copy.copy(policy._store_visit)
            approach_store = policy._shopping_approach_store_type
            acquire_calls.clear()
            key = policy.choose_key(snapshot)
            attribution = policy.decision_attribution
            reason = policy.last_reason

            if not (snapshot.in_town or snapshot.store is not None):
                continue
            totals["decisions"] += 1
            if key:
                totals["keys"] += 1
            if visit is not None and visit.phase != StoreVisitPhase.CLOSED:
                totals["open_visits"] += 1
            if visit is not None and _in_flight(visit):
                totals["in_flight_visits"] += 1
            if not key or visit is None or not _in_flight(visit):
                continue

            owner = policy._store_visit_arbiter_owner(visit)
            target_store, target_source = _target_store(snapshot, key, approach_store)
            forms = _predicates(
                attribution=attribution, owner=owner, visit_store=visit.store_type,
                target_store=target_store, acquire_calls=acquire_calls,
            )
            row = {
                "row": row_index, "attribution": attribution, "visit_owner": owner,
                "phase": visit.phase.value, "reason": reason,
                "visit_store": visit.store_type, "target_store": target_store,
                "target_source": target_source, "acquires": copy.deepcopy(acquire_calls),
                "forms": forms,
            }
            rows.append(row)
            for form, violated in forms.items():
                totals[f"{form}_violations"] += int(violated)
            totals["B_undetermined"] += int(target_store is None)
            totals["C_unmapped"] += int(attribution not in COARSE_ATTRIBUTION)

    totals["in_flight_emitting_decisions"] = len(rows)
    # Predicate-patch controls: collapse A/C comparison operands, force every
    # known B target across stores, and force D's acquisition fact true.
    totals["A_control"] = sum(owner != owner for owner in (r["visit_owner"] for r in rows))
    totals["B_control"] = sum(
        _predicates(
            attribution=r["attribution"], owner=r["visit_owner"],
            visit_store=r["visit_store"], target_store=(r["visit_store"] + 1) % 8,
            acquire_calls=r["acquires"],
        )["B"] for r in rows if r["target_store"] is not None
    )
    totals["C_control"] = sum(
        r["visit_owner"] != r["visit_owner"] for r in rows
        if r["attribution"] in COARSE_ATTRIBUTION
    )
    totals["D_control"] = sum(not [True] for _ in rows)
    return {"totals": dict(totals), "rows": rows}


def _print_form_rows(form: str, rows: list[dict]) -> None:
    grouped = defaultdict(list)
    for row in rows:
        if row["forms"][form]:
            grouped[(row["attribution"], row["visit_owner"], row["phase"])].append(row)
    for triple, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        print(
            f"form={form} triple={triple!r} count={len(members)} "
            f"examples={[r['row'] for r in members[:5]]!r} "
            f"reasons={sorted({r['reason'] for r in members})!r}"
        )


def _print_report(label: str, result: dict) -> None:
    totals, rows = result["totals"], result["rows"]
    print(f"population={label}")
    print(
        " ".join(f"{name}={totals.get(name, 0)}" for name in (
            "snapshot_rows", "decisions", "keys", "open_visits",
            "in_flight_visits", "in_flight_emitting_decisions",
            "A_violations", "B_violations", "C_violations", "D_violations",
        ))
    )
    pairs = ("AB", "AC", "AD", "BC", "BD", "CD")
    overlaps = {
        pair: sum(r["forms"][pair[0]] and r["forms"][pair[1]] for r in rows)
        for pair in pairs
    }
    overlaps["ABCD"] = sum(all(r["forms"].values()) for r in rows)
    exactly_one = {
        form: sum(r["forms"][form] and sum(r["forms"].values()) == 1 for r in rows)
        for form in FORMS
    }
    print("overlap " + " ".join(f"{name}={value}" for name, value in overlaps.items()))
    print("exactly_one " + " ".join(f"{form}={exactly_one[form]}" for form in FORMS))
    print(
        f"B_undetermined={totals.get('B_undetermined', 0)} "
        f"B_target_sources={dict(Counter(r['target_source'] for r in rows))!r}"
    )
    quoted = QUOTED_B_SUBTRACTION[label]
    direct = totals.get("B_violations", 0)
    print(
        f"B_quoted_subtraction={quoted} B_direct={direct} "
        f"B_reproduces_subtraction={direct == quoted} "
        "B_subtraction_status='direct predicate is authoritative; E1 subtraction "
        "counted every A row not proved same-store, which is not the different-store predicate'"
    )
    unmapped = sorted({r["attribution"] for r in rows if r["attribution"] not in COARSE_ATTRIBUTION})
    print(f"C_unmapped={totals.get('C_unmapped', 0)} C_unmapped_values={unmapped!r}")
    d_targeted = [r for r in rows if r["forms"]["D"] and r["target_store"] is not None]
    print(
        f"D_targeted_store={len(d_targeted)} "
        f"D_targeted_reasons={dict(Counter(r['reason'] for r in d_targeted).most_common())!r}"
    )
    print(
        "controls " + " ".join(
            f"{form}={totals.get(form + '_violations', 0)}->{totals.get(form + '_control', 0)}"
            for form in FORMS
        )
    )
    for form in FORMS:
        _print_form_rows(form, rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("population", choices=(*POPULATIONS, "all"), default="all", nargs="?")
    args = parser.parse_args()
    selected = POPULATIONS if args.population == "all" else {args.population: POPULATIONS[args.population]}
    failed = False
    for label, path in selected.items():
        result = measure(path)
        _print_report(label, result)
        totals = result["totals"]
        failed |= totals.get("A_control", -1) != 0
        failed |= totals.get("C_control", -1) != 0
        failed |= totals.get("D_control", -1) != 0
        determinate = totals.get("in_flight_emitting_decisions", 0) - totals.get("B_undetermined", 0)
        failed |= totals.get("B_control", -1) != determinate
        for form in FORMS:
            if totals.get(f"{form}_violations", 0) == totals.get(f"{form}_control", 0):
                print(f"CONTROL FAILURE: {form} count did not move")
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
