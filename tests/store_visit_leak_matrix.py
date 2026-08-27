"""Measure foreign store visits that wrongly refuse a wanted approach."""

from dataclasses import replace
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"
STORE_TYPES = tuple(range(8))
PHASES = (
    StoreVisitPhase.APPROACHING,
    StoreVisitPhase.ENTERING,
    StoreVisitPhase.OPERATING,
    StoreVisitPhase.LEAVING,
)


def _surface_snapshot():
    with SNAPSHOTS.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") != 1172205 or row.get("store") is not None:
                continue
            snapshot = parse_snapshot(row, {})
            if snapshot.store is None:
                return snapshot
    raise RuntimeError("capture entry snapshot is missing")


def _approach(policy, snapshot, wanted):
    return policy._shopping_approach_step(snapshot, wanted)


def measure():
    """Return (leaks, cells, descriptions) using the real approach producer.

    ``choose_key`` derives many unrelated needs before reaching this producer;
    the honest unit is the real ``_shopping_approach_step`` where the defect's
    early refusal lived.  A paired no-visit control proves that every counted
    refusal is caused solely by the injected foreign visit.
    """
    snapshot = _surface_snapshot()
    policy = HengbotPolicy()
    owners = tuple(policy._town_turn_arbiter.registry)
    entrance = next(
        grid for grid in snapshot.grids.values()
        if grid.position.distance_to(snapshot.player.position) == 1
        and grid.passable
    )
    snapshots = {
        wanted: replace(
            snapshot,
            grids={
                **snapshot.grids,
                entrance.position: replace(entrance, store_number=wanted),
            },
        )
        for wanted in STORE_TYPES
    }
    controls = {}
    for wanted in STORE_TYPES:
        policy._store_visit = None
        policy._store_visit_pending_goal = None
        policy._town_travel_state = None
        controls[wanted] = _approach(policy, snapshots[wanted], wanted)
    leaks = []
    cells = 0
    for open_store in (None, *STORE_TYPES):
        for wanted in STORE_TYPES:
            for owner in owners:
                for phase in PHASES:
                    for operation_posted in (False, True):
                        cells += 1
                        policy._store_visit = None
                        policy._store_visit_pending_goal = None
                        policy._town_travel_state = None
                        policy._town_turn_arbiter._owner = owner
                        if open_store is not None:
                            policy._store_visit = StoreVisit(
                                owner=owner,
                                purpose="visit-leak-matrix",
                                store_type=open_store,
                                phase=phase,
                                operation_posted=operation_posted,
                                operation_released=False,
                                posted_sequence=(1 if operation_posted else None),
                            )
                        step = _approach(policy, snapshots[wanted], wanted)
                        if (
                            open_store is not None
                            and open_store != wanted
                            and not operation_posted
                            and controls[wanted] is not None
                            and step is None
                        ):
                            leaks.append(
                                (open_store, wanted, owner, phase.value, operation_posted)
                            )
    return len(leaks), cells, leaks


if __name__ == "__main__":
    leak_count, total, leaks = measure()
    print(f"{leak_count}/{total} leaks")
    for leak in leaks[:20]:
        print(repr(leak))
    raise SystemExit(bool(leak_count))
