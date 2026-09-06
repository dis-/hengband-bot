"""Count town producers that leak state while being evaluated as candidates."""

import hashlib
import importlib.util
import json
from pathlib import Path
import pickle
from collections import Counter
from dataclasses import dataclass
from functools import cache

from hengbot.model import (
    parse_snapshot, STORE_ALCHEMIST, STORE_GENERAL, STORE_HOME, STORE_MAGIC,
)
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy, WAIT_KEY
from hengbot.policy_types import StoreVisit


ROOT = Path(__file__).resolve().parents[1]
CAPTURES = {
    "equip-swap": ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl",
    "no-actionable": ROOT / "jsonlog" / "incident-no-actionable-claim-20260827.snapshots.jsonl",
}
PROPERTY_BACKED_STATE = ("_store_visit",)

# No history-bearing field is exempt.  The ownership manifest makes widening
# this set a review-visible act, and the control below rejects every field not
# proved equal after X -> Y and fresh -> Y evaluation.
DERIVED_CACHE_EXEMPTIONS = {}
CACHE_FIELD_OWNERS = {
    "_town_fact_region": "producer B (formerly warmed through _home_available)",
    "_town_store_positions": "producer B (formerly warmed through _home_available)",
    "_town_emitted_entrances": "producer B (formerly warmed through _home_available)",
    "_town_fact_snapshot": "producer B (formerly warmed through _home_available)",
    "_town_entrance_cache": "producer A routing cache, not producer B",
    "_town_visit_entrances": "producer B routing history; cumulative by construction",
}

DIRECT_PRODUCERS = (
    "_boxed_town_breakout_key",
    "_town_procurement_progress_key",
    "departure_block_state",
)
PARTITION_COUNT = 6
PARTITION_MODULES = tuple(
    f"test_town_producer_purity_part{partition}"
    for partition in range(1, PARTITION_COUNT + 1)
)
FULL_CELL_COUNT = 1116
PARTITION_CELL_INDEXES = tuple(
    tuple(range(partition, FULL_CELL_COUNT, PARTITION_COUNT))
    for partition in range(PARTITION_COUNT)
)


@dataclass(frozen=True)
class PurityCell:
    kind: str
    capture: str
    row: int
    producer: str = ""
    pinned: bool = False


@cache
def _snapshots(name):
    path = CAPTURES[name]
    definitions = find_monrace_definitions(path, None)
    monraces = load_monrace_knowledge(definitions) if definitions else {}
    snapshots = []
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            snapshot = parse_snapshot(json.loads(line), monraces)
            if snapshot.in_town and snapshot.store is None:
                snapshots.append(snapshot)
    return snapshots, monraces


@cache
def _surface_snapshot_count(name):
    count = 0
    with CAPTURES[name].open(encoding="utf-8-sig") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("floor", {}).get("in_town") and row.get("store") is None:
                count += 1
    return count


def _surface_snapshot():
    snapshots, _ = _snapshots("equip-swap")
    return next(snapshot for snapshot in snapshots if snapshot.turn == 1172205)


def _digest(value):
    return hashlib.sha256(pickle.dumps(value, protocol=5)).hexdigest()


def observable_policy_fields(policy):
    fields = {
        f"policy.{name}": _digest(value)
        for name, value in policy.__dict__.items()
        if name != "_town_turn_arbiter" and name not in DERIVED_CACHE_EXEMPTIONS
    }
    fields.update(
        {f"arbiter.{name}": _digest(value)
         for name, value in policy._town_turn_arbiter.__dict__.items()}
    )
    fields.update(
        {f"property.{name}": _digest(getattr(policy, name))
         for name in PROPERTY_BACKED_STATE}
    )
    return fields


def observable_policy_state(policy):
    return _digest(observable_policy_fields(policy))


def _differ_detects_visit_mutation():
    policy = HengbotPolicy()
    before = observable_policy_state(policy)
    policy._town_turn_arbiter.store_visit = StoreVisit(
        "purity-control", "injected", STORE_MAGIC
    )
    return before != observable_policy_state(policy)


def _exemption_control():
    """Only X -> Y fields equal to a fresh town-fact refresh on Y may be exempted."""
    snapshots, monraces = _snapshots("equip-swap")
    x, y = snapshots[0], snapshots[-1]
    carried = HengbotPolicy(monrace_knowledge=monraces)
    fresh = HengbotPolicy(monrace_knowledge=monraces)
    carried._refresh_town_facts(x)
    carried._refresh_town_facts(y)
    fresh._refresh_town_facts(y)
    proven = {
        field for field in CACHE_FIELD_OWNERS
        if _digest(getattr(carried, field)) == _digest(getattr(fresh, field))
    }
    return set(DERIVED_CACHE_EXEMPTIONS) <= proven


def _old_boxed_town_breakout_key(policy, snapshot):
    """Byte-for-byte producer body from e67b56f, kept as the comparison oracle."""
    here = snapshot.grid_at(snapshot.player.position)
    current_store = here.store_number if here is not None else -1
    for store_type in (STORE_HOME, STORE_MAGIC, STORE_ALCHEMIST, STORE_GENERAL):
        if store_type == current_store:
            continue
        step = policy._shopping_approach_step(snapshot, store_type)
        if step is None:
            continue
        key = policy._shopping_approach_key(
            snapshot, step, "town-progress-invariant:boxed-breakout-travel"
        )
        if key not in {"", WAIT_KEY}:
            return key
    return None


def _mutation_map(before, after):
    return {
        field: (before.get(field), after.get(field))
        for field in before.keys() | after.keys()
        if before.get(field) != after.get(field)
    }


def producer_equivalence():
    """Sweep old versus commit over both captures, including a posted General visit."""
    populations = {}
    missing_mutations = set()
    for capture in CAPTURES:
        snapshots, _ = _snapshots(capture)
        rows = {"unconstrained": 0, "posted_general": 0, "total": len(snapshots)}
        prototype = checkpoint(HengbotPolicy())
        old = restore_checkpoint(HengbotPolicy, prototype)
        new = restore_checkpoint(HengbotPolicy, prototype)
        for snapshot in snapshots:
            for pinned, label in ((False, "unconstrained"), (True, "posted_general")):
                if pinned:
                    visit = StoreVisit(
                        "town-errand", "shopping", STORE_GENERAL,
                        operation_posted=True, operation_key="5",
                    )
                    old._store_visit = visit
                    new._store_visit = pickle.loads(pickle.dumps(visit, protocol=5))
                old_before = observable_policy_fields(old)
                new_before = observable_policy_fields(new)
                old_key = _old_boxed_town_breakout_key(old, snapshot)
                new_key = new._commit_boxed_town_breakout_key(snapshot)
                old_changes = _mutation_map(old_before, observable_policy_fields(old))
                new_changes = _mutation_map(new_before, observable_policy_fields(new))
                rows[label] += old_key == new_key
                missing_mutations.update(old_changes.keys() - new_changes.keys())
                if old_changes or new_changes or pinned:
                    old = restore_checkpoint(HengbotPolicy, prototype)
                    new = restore_checkpoint(HengbotPolicy, prototype)
        populations[capture] = rows
    return populations, missing_mutations


def measure():
    snapshot = _surface_snapshot()
    impure = []
    results = {}
    prototype = checkpoint(HengbotPolicy())
    policy = restore_checkpoint(HengbotPolicy, prototype)
    for name in DIRECT_PRODUCERS:
        before = observable_policy_state(policy)
        results[name] = getattr(policy, name)(snapshot)
        if observable_policy_state(policy) != before:
            impure.append(name)
            policy = restore_checkpoint(HengbotPolicy, prototype)

    return {
        "impure": impure,
        "results": results,
        "exemption_control": _exemption_control(),
        "visit_injection_detected": _differ_detects_visit_mutation(),
    }


def probe_sweep():
    sweep = {}
    for capture in CAPTURES:
        snapshots, _ = _snapshots(capture)
        prototype = checkpoint(HengbotPolicy())
        policy = restore_checkpoint(HengbotPolicy, prototype)
        calls = impure_calls = 0
        for candidate in snapshots:
            before = observable_policy_state(policy)
            policy._boxed_town_breakout_key(candidate)
            calls += 1
            impure = observable_policy_state(policy) != before
            impure_calls += impure
            if impure:
                policy = restore_checkpoint(HengbotPolicy, prototype)
        sweep[capture] = {"calls": calls, "impure_calls": impure_calls}
    return sweep


def purity_cells():
    """Return the old test's complete producer/cell matrix in execution order."""
    cells = [
        PurityCell("direct", "equip-swap", 0, producer=name)
        for name in DIRECT_PRODUCERS
    ]
    for capture in CAPTURES:
        cells.extend(
            PurityCell("probe", capture, row, producer="_boxed_town_breakout_key")
            for row in range(_surface_snapshot_count(capture))
        )
    for capture in CAPTURES:
        for row in range(_surface_snapshot_count(capture)):
            cells.append(PurityCell("equivalence", capture, row, pinned=False))
            cells.append(PurityCell("equivalence", capture, row, pinned=True))
    return tuple(cells)


def partition_cells(partition):
    cells = purity_cells()
    return tuple(cells[index] for index in PARTITION_CELL_INDEXES[partition])


def assert_partition_is_pure(testcase, partition):
    """Run one order-preserving slice of the former monolithic purity test."""
    selected = set(PARTITION_CELL_INDEXES[partition])
    cells = purity_cells()
    snapshots_by_capture = {
        capture: _snapshots(capture)[0] for capture in CAPTURES
    }

    if partition == 0:
        testcase.assertTrue(_differ_detects_visit_mutation())
        testcase.assertTrue(_exemption_control())

    direct_policy = HengbotPolicy()
    direct_snapshot = _surface_snapshot()
    probe_state = {}
    equivalence_prototype = checkpoint(HengbotPolicy())
    for index, cell in enumerate(cells):
        if index not in selected:
            continue
        if cell.kind == "direct":
            before = observable_policy_state(direct_policy)
            result = getattr(direct_policy, cell.producer)(direct_snapshot)
            testcase.assertEqual(observable_policy_state(direct_policy), before)
            if cell.producer == "_boxed_town_breakout_key":
                testcase.assertEqual(result, "\x1b`n&.")
            continue

        snapshots = snapshots_by_capture[cell.capture]
        snapshot = snapshots[cell.row]
        if cell.kind == "probe":
            policy, prototype = probe_state.get(cell.capture, (None, None))
            if policy is None:
                prototype = checkpoint(HengbotPolicy())
                policy = restore_checkpoint(HengbotPolicy, prototype)
            before = observable_policy_state(policy)
            policy._boxed_town_breakout_key(snapshot)
            testcase.assertEqual(observable_policy_state(policy), before)
            probe_state[cell.capture] = (policy, prototype)
            continue

        old = restore_checkpoint(HengbotPolicy, equivalence_prototype)
        new = restore_checkpoint(HengbotPolicy, equivalence_prototype)
        if cell.pinned:
            visit = StoreVisit(
                "town-errand", "shopping", STORE_GENERAL,
                operation_posted=True, operation_key="5",
            )
            old._store_visit = visit
            new._store_visit = pickle.loads(pickle.dumps(visit, protocol=5))
        old_before = observable_policy_fields(old)
        new_before = observable_policy_fields(new)
        old_key = _old_boxed_town_breakout_key(old, snapshot)
        new_key = new._commit_boxed_town_breakout_key(snapshot)
        old_changes = _mutation_map(old_before, observable_policy_fields(old))
        new_changes = _mutation_map(new_before, observable_policy_fields(new))
        testcase.assertEqual(new_key, old_key)
        testcase.assertEqual(old_changes.keys() - new_changes.keys(), set())


def assert_partitions_complete(testcase):
    for module in PARTITION_MODULES:
        testcase.assertIsNotNone(
            importlib.util.find_spec(module),
            f"purity partition module is not discoverable: {module}",
        )
    for capture in CAPTURES:
        testcase.assertEqual(
            len(_snapshots(capture)[0]),
            _surface_snapshot_count(capture),
            f"parsed surface population drifted for {capture}",
        )
    cells = purity_cells()
    flattened = tuple(
        index for partition in PARTITION_CELL_INDEXES for index in partition
    )
    testcase.assertEqual(len(cells), FULL_CELL_COUNT)
    testcase.assertEqual(len(flattened), len(set(flattened)), "partition overlap")
    testcase.assertEqual(set(flattened), set(range(len(cells))))
    testcase.assertEqual(
        Counter((cell.kind, cell.capture) for cell in cells),
        Counter({
            ("direct", "equip-swap"): 3,
            ("probe", "equip-swap"): 145,
            ("probe", "no-actionable"): 226,
            ("equivalence", "equip-swap"): 290,
            ("equivalence", "no-actionable"): 452,
        }),
    )


if __name__ == "__main__":
    result = measure()
    sweep = probe_sweep()
    equivalence, missing_mutations = producer_equivalence()
    print(f"impure_producers={len(result['impure'])}")
    for producer in result["impure"]:
        print(f"impure: {producer}")
    print(f"visit_injection_detected={result['visit_injection_detected']}")
    print(f"exemption_control={result['exemption_control']}")
    print(f"probe_sweep={sweep}")
    print(f"producer_equivalence={equivalence}")
    print(f"mutations OLD made that NEW does not = {missing_mutations}")
    raise SystemExit(bool(
        result["impure"]
        or not result["visit_injection_detected"]
        or not result["exemption_control"]
        or any(row["impure_calls"] for row in sweep.values())
        or missing_mutations
        or any(
            row[label] != row["total"]
            for row in equivalence.values()
            for label in ("unconstrained", "posted_general")
        )
    ))
