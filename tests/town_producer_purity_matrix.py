"""Count town producers that leak state while being evaluated as candidates."""

import hashlib
import gzip
import importlib.util
import json
from pathlib import Path
import pickle
from collections import Counter
from dataclasses import dataclass
from functools import cache

from hengbot.model import (
    parse_snapshot, STORE_MAGIC,
)
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = ROOT / "tests" / "fixtures"
CAPTURES = {
    "equip-swap": CAPTURE_DIR / "equip-swap-20260826.snapshots.jsonl.gz",
    "no-actionable": CAPTURE_DIR / "no-actionable-claim-20260827.snapshots.jsonl.gz",
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
    "_town_procurement_progress_key",
    "departure_block_state",
)
PARTITION_COUNT = 6
PARTITION_MODULES = tuple(
    f"test_town_producer_purity_part{partition}"
    for partition in range(1, PARTITION_COUNT + 1)
)
# The boxed town breakout producer and its probe/equivalence cells were
# deleted with it (owner 2026-11-02 town defined end): two direct cells remain.
FULL_CELL_COUNT = 2
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
def _monraces(name):
    path = CAPTURES[name]
    definitions = find_monrace_definitions(path, None)
    return load_monrace_knowledge(definitions) if definitions else {}


def _open_capture(name, mode="rt"):
    path = CAPTURES[name]
    return gzip.open(path, mode, encoding="utf-8-sig") if "b" not in mode else gzip.open(path, mode)


@cache
def _surface_snapshot_offsets(name):
    offsets = []
    with _open_capture(name, "rb") as stream:
        while True:
            offset = stream.tell()
            line = stream.readline()
            if not line:
                break
            row = json.loads(line.decode("utf-8-sig"))
            if row.get("floor", {}).get("in_town") and row.get("store") is None:
                offsets.append(offset)
    return tuple(offsets)


def _snapshot_at_surface_row(name, row):
    offset = _surface_snapshot_offsets(name)[row]
    with _open_capture(name, "rb") as stream:
        stream.seek(offset)
        raw = json.loads(stream.readline().decode("utf-8-sig"))
        return parse_snapshot(raw, _monraces(name))


@cache
def _snapshots(name):
    monraces = _monraces(name)
    snapshots = []
    with _open_capture(name) as stream:
        for line in stream:
            snapshot = parse_snapshot(json.loads(line), monraces)
            if snapshot.in_town and snapshot.store is None:
                snapshots.append(snapshot)
    return snapshots, monraces


@cache
def _surface_snapshot_count(name):
    return len(_surface_snapshot_offsets(name))


def _parsed_surface_snapshot_count(name):
    monraces = _monraces(name)
    count = 0
    with _open_capture(name) as stream:
        for line in stream:
            snapshot = parse_snapshot(json.loads(line), monraces)
            if snapshot.in_town and snapshot.store is None:
                count += 1
    return count


def _surface_snapshot():
    name = "equip-swap"
    with _open_capture(name) as stream:
        for line in stream:
            row = json.loads(line)
            if (
                row.get("floor", {}).get("in_town")
                and row.get("store") is None
                and row.get("turn") == 1172205
            ):
                return parse_snapshot(row, _monraces(name))
    raise LookupError("surface snapshot at turn 1172205 is absent")


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
    name = "equip-swap"
    monraces = _monraces(name)
    x = _snapshot_at_surface_row(name, 0)
    y = _snapshot_at_surface_row(name, _surface_snapshot_count(name) - 1)
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


def purity_cells():
    """Return the producer/cell matrix in execution order."""
    return tuple(
        PurityCell("direct", "equip-swap", 0, producer=name)
        for name in DIRECT_PRODUCERS
    )


def partition_cells(partition):
    cells = purity_cells()
    return tuple(cells[index] for index in PARTITION_CELL_INDEXES[partition])


def assert_partition_is_pure(testcase, partition, *, indexes=None):
    """Run one order-preserving slice of the former monolithic purity test."""
    # Partition membership/coverage remains full in assert_partitions_complete.
    selected = set(PARTITION_CELL_INDEXES[partition] if indexes is None else indexes)
    cells = purity_cells()
    whole_capture_cache_before = _snapshots.cache_info()

    if partition == 0:
        testcase.assertTrue(_differ_detects_visit_mutation())
        testcase.assertTrue(_exemption_control())

    direct_policy = HengbotPolicy()
    for index, cell in enumerate(cells):
        if index not in selected:
            continue
        before = observable_policy_state(direct_policy)
        getattr(direct_policy, cell.producer)(_surface_snapshot())
        testcase.assertEqual(observable_policy_state(direct_policy), before)

    testcase.assertEqual(
        _snapshots.cache_info(),
        whole_capture_cache_before,
        "a partition must not populate the whole-capture snapshot cache",
    )


def assert_partitions_complete(testcase):
    for module in PARTITION_MODULES:
        testcase.assertIsNotNone(
            importlib.util.find_spec(module),
            f"purity partition module is not discoverable: {module}",
        )
    for capture in CAPTURES:
        testcase.assertEqual(
            _parsed_surface_snapshot_count(capture),
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
        Counter({("direct", "equip-swap"): 2}),
    )


if __name__ == "__main__":
    result = measure()
    print(f"impure_producers={len(result['impure'])}")
    for producer in result["impure"]:
        print(f"impure: {producer}")
    print(f"visit_injection_detected={result['visit_injection_detected']}")
    print(f"exemption_control={result['exemption_control']}")
    raise SystemExit(bool(
        result["impure"]
        or not result["visit_injection_detected"]
        or not result["exemption_control"]
    ))
