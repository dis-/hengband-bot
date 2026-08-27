"""Count town producers that leak state while being evaluated as candidates."""

import hashlib
import json
from pathlib import Path
import pickle

from hengbot.model import parse_snapshot, STORE_MAGIC
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"
PROPERTY_BACKED_STATE = ("_store_visit",)
DERIVED_CACHE_EXEMPTIONS = {
    "_town_fact_region": "floor/town region key derived by _grid_region(snapshot)",
    "_town_store_positions": "store positions derived from grids emitted by the snapshot",
    "_town_emitted_entrances": "entrance membership derived from emitted snapshot grids",
    "_town_fact_snapshot": "identity key for the last snapshot; a new Snapshot invalidates it",
    "_town_entrance_cache": "entrance set derived from town facts and the static town map",
    "_town_visit_entrances": "observed modal cells derived from snapshots in this town visit",
}


def _surface_snapshot():
    with CAPTURE.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") == 1172205 and row.get("store") is None:
                return parse_snapshot(row, {})
    raise RuntimeError("frozen armour-swap surface snapshot is missing")


def _digest(value):
    return hashlib.sha256(pickle.dumps(value, protocol=5)).hexdigest()


def observable_policy_state(policy):
    """Enumerate policy, arbiter, and compatibility-property state explicitly."""
    policy_fields = {
        name: value
        for name, value in policy.__dict__.items()
        if name != "_town_turn_arbiter" and name not in DERIVED_CACHE_EXEMPTIONS
    }
    arbiter = policy._town_turn_arbiter
    properties = {
        name: getattr(policy, name)
        for name in PROPERTY_BACKED_STATE
    }
    return (
        _digest(policy_fields),
        _digest(arbiter.__dict__),
        _digest(properties),
    )


def _differ_detects_visit_mutation():
    policy = HengbotPolicy()
    before = observable_policy_state(policy)
    policy._town_turn_arbiter.store_visit = StoreVisit(
        "purity-control", "injected", STORE_MAGIC
    )
    return before != observable_policy_state(policy)


def measure():
    snapshot = _surface_snapshot()
    producers = (
        "_boxed_town_breakout_key",
        "_town_procurement_progress_key",
    )
    impure = []
    results = {}
    cache_idempotence = {}
    for name in producers:
        policy = HengbotPolicy()
        before = observable_policy_state(policy)
        results[name] = getattr(policy, name)(snapshot)
        if observable_policy_state(policy) != before:
            impure.append(name)
        if name == "_town_procurement_progress_key":
            first = {
                field: _digest(getattr(policy, field))
                for field in DERIVED_CACHE_EXEMPTIONS
            }
            first_result = results[name]
            second_result = getattr(policy, name)(snapshot)
            second = {
                field: _digest(getattr(policy, field))
                for field in DERIVED_CACHE_EXEMPTIONS
            }
            cache_idempotence[name] = {
                "result": first_result == second_result,
                **{field: first[field] == second[field] for field in first},
            }
    return {
        "impure": impure,
        "results": results,
        "cache_idempotence": cache_idempotence,
        "visit_injection_detected": _differ_detects_visit_mutation(),
    }


if __name__ == "__main__":
    result = measure()
    print(f"impure_producers={len(result['impure'])}")
    for producer in result["impure"]:
        print(f"impure: {producer}")
    print(f"visit_injection_detected={result['visit_injection_detected']}")
    print(f"cache_idempotence={result['cache_idempotence']}")
    raise SystemExit(bool(
        result["impure"]
        or not result["visit_injection_detected"]
        or not all(
            all(checks.values())
            for checks in result["cache_idempotence"].values()
        )
    ))
