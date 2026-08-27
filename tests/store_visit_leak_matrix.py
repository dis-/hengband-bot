"""Measure both foreign-visit refusal leaks and unsafe visit transfers."""

from dataclasses import replace
import copy
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"
STORE_TYPES = tuple(range(8))
PHASES = tuple(StoreVisitPhase)[0:4]


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


def _fresh_approach(snapshot, wanted, *, owner, visit=None, prototype=None):
    # The approach unit only mutates the fields reset below.  A shallow clone
    # is therefore an independent policy for this cell without repeatedly
    # rebuilding the policy's large immutable knowledge tables.
    policy = copy.copy(prototype) if prototype is not None else HengbotPolicy()
    if prototype is not None:
        policy._town_turn_arbiter = copy.deepcopy(prototype._town_turn_arbiter)
    policy._town_turn_arbiter._owner = owner
    policy._store_visit = visit
    policy._store_visit_pending_goal = None
    policy._town_travel_state = None
    step = policy._shopping_approach_step(snapshot, wanted)
    return step, policy, visit


def measure():
    """Return two-directional failures over independently isolated cells.

    The real ``_shopping_approach_step`` is the honest unit: ``choose_key``
    derives unrelated needs before it reaches this producer.  Every subject
    has its own fresh policy and its own fresh no-visit control.
    """
    surface = _surface_snapshot()
    prototype = HengbotPolicy()
    owners = (None, *prototype._town_turn_arbiter.registry)
    entrance = next(
        grid for grid in surface.grids.values()
        if grid.position.distance_to(surface.player.position) == 1
        and grid.passable
    )
    snapshots = {
        wanted: replace(
            surface,
            grids={
                **surface.grids,
                entrance.position: replace(entrance, store_number=wanted),
            },
        )
        for wanted in STORE_TYPES
    }

    viable_wanted = {
        wanted
        for wanted in STORE_TYPES
        if _fresh_approach(
            snapshots[wanted], wanted, owner=None, prototype=prototype
        )[0] is not None
    }
    leaks = []
    transfer_violations = []
    total = live = candidates = protected_candidates = 0
    for open_store in (None, *STORE_TYPES):
        for wanted in STORE_TYPES:
            for owner in owners:
                for phase in PHASES:
                    for operation_posted in (False, True):
                        # Entry/leave posting is a separate command context;
                        # vary it independently from operation_posted where
                        # that context exists.
                        command_states = (
                            (False, True)
                            if phase in {
                                StoreVisitPhase.ENTERING,
                                StoreVisitPhase.LEAVING,
                            }
                            else (False,)
                        )
                        for command_posted in command_states:
                            total += 1
                            if wanted not in viable_wanted:
                                continue
                            control, _, _ = _fresh_approach(
                                snapshots[wanted], wanted, owner=owner,
                                prototype=prototype,
                            )
                            if control is None:
                                continue
                            live += 1
                            if open_store is None or open_store == wanted:
                                continue
                            candidates += 1
                            posted_sequence = 1 if command_posted else None
                            posted_turn = (
                                surface.turn
                                if command_posted
                                and phase == StoreVisitPhase.LEAVING
                                else None
                            )
                            visit = StoreVisit(
                                owner=owner or "unobserved-owner",
                                purpose="visit-leak-matrix",
                                store_type=open_store,
                                phase=phase,
                                operation_posted=operation_posted,
                                operation_released=False,
                                posted_sequence=posted_sequence,
                                posted_turn=posted_turn,
                            )
                            step, policy, original = _fresh_approach(
                                snapshots[wanted], wanted,
                                owner=owner, visit=visit, prototype=prototype,
                            )
                            protected = operation_posted or (
                                command_posted
                                and phase in {
                                    StoreVisitPhase.ENTERING,
                                    StoreVisitPhase.LEAVING,
                                }
                            )
                            cell = (
                                open_store, wanted, owner, phase.value,
                                operation_posted, command_posted,
                            )
                            if protected:
                                protected_candidates += 1
                                if (
                                    step is not None
                                    or policy._store_visit is not original
                                    or original.phase == StoreVisitPhase.CLOSED
                                ):
                                    transfer_violations.append(cell)
                            elif step is None:
                                leaks.append(cell)
    return {
        "leaks": leaks,
        "transfer_violations": transfer_violations,
        "total": total,
        "live": live,
        "candidates": candidates,
        "protected_candidates": protected_candidates,
    }


if __name__ == "__main__":
    result = measure()
    print(
        f"leaks={len(result['leaks'])} "
        f"transfer_violations={len(result['transfer_violations'])} "
        f"live={result['live']} candidates={result['candidates']} "
        f"protected_candidates={result['protected_candidates']} "
        f"total={result['total']}"
    )
    for name in ("leaks", "transfer_violations"):
        for failure in result[name][:20]:
            print(f"{name}: {failure!r}")
    raise SystemExit(bool(result["leaks"] or result["transfer_violations"]))
