"""Bounded, decision-pure capture of town-blocked latch onset."""

from __future__ import annotations

import base64
from collections import deque
import inspect
import json
import pickle
from pathlib import Path
from typing import Any

from hengbot.flight_recorder import jsonable


CAPTURE_DECISIONS_AFTER_ONSET = 2
CALLER_CHAIN_LIMIT = 24
_CAPTURE_STATE_NAMES = frozenset(
    {
        "_latch_capture_path",
        "_latch_capture_previous",
        "_latch_capture_assignment",
        "_latch_capture_remaining",
        # Derived registry contains local predicate lambdas. It is rebuilt on
        # first use from the authoritative policy state.
        "_town_need_specs",
    }
)


def checkpoint(policy: Any) -> str:
    """Return an exact, restorable pre-decision policy checkpoint."""
    state = {
        name: value
        for name, value in vars(policy).items()
        if name not in _CAPTURE_STATE_NAMES
    }
    return base64.b64encode(pickle.dumps(state, protocol=5)).decode("ascii")


def restore_checkpoint(policy_type: type, encoded: str) -> Any:
    """Restore a capture checkpoint without running policy initialization."""
    restored = policy_type.__new__(policy_type)
    restored.__dict__.update(pickle.loads(base64.b64decode(encoded)))
    restored._latch_capture_path = None
    restored._latch_capture_previous = None
    restored._latch_capture_predecision = None
    restored._latch_capture_assignment = None
    restored._latch_capture_remaining = 0
    return restored


def assignment_provenance() -> dict[str, Any]:
    """Capture the assigning source and bounded Python caller chain."""
    frames = inspect.stack(context=0)[2 : 2 + CALLER_CHAIN_LIMIT]
    chain = [
        {"file": frame.filename, "line": frame.lineno, "function": frame.function}
        for frame in frames
    ]
    return {
        "assigning_file": chain[0]["file"] if chain else None,
        "assigning_line": chain[0]["line"] if chain else None,
        "caller_chain": chain,
    }


def _recall_candidates(policy: Any, snapshot: Any) -> list[dict[str, Any]]:
    """Evaluate the exact destination branch predicates on a disposable clone."""
    angband = 1
    yeek = 2
    target = policy._target_dungeon_id

    def safety(dungeon_id: int) -> dict[str, Any]:
        if dungeon_id == snapshot.recall_dungeon_id:
            depth = snapshot.recall_depth
            depth_source = "snapshot.recall_depth"
        else:
            info = policy._dungeon_knowledge.get(dungeon_id)
            depth = info.min_depth if info is not None else 1
            depth_source = "dungeon.min_depth-or-1"
        missing = sorted(policy._missing_required_abilities(snapshot, depth))
        return {
            "landing_depth": depth,
            "landing_depth_source": depth_source,
            "predicate": "not _missing_required_abilities(snapshot, landing_depth)",
            "missing_required_abilities": missing,
            "value": not missing,
        }

    candidates = [
        {
            "name": "angband",
            "dungeon_id": angband,
            "predicates": {
                "target_is_angband": target == angband,
                "angband_recall_unlocked": snapshot.angband_recall_unlocked,
                "recall_destination_safe": safety(angband),
            },
        },
        {
            "name": "target-alt-dungeon",
            "dungeon_id": target,
            "predicates": {
                "target_is_not_angband_or_yeek": target not in (angband, yeek),
                "target_was_entered": target in snapshot.entered_dungeon_ids,
                "recall_destination_safe": safety(target),
            },
        },
        {
            "name": "yeek-cave",
            "dungeon_id": yeek,
            "predicates": {
                "target_is_yeek_cave": target == yeek,
                "fundraising_allows_recall": policy._fundraising_mode not in {"mine", "scavenge"},
                "taken_kill_quest_requires_walk_in": policy._taken_kill_quest_requires_walk_in(snapshot),
                "deepest_level_at_least_recall_min_depth": policy._deepest_level >= 5,
                "recall_destination_safe": safety(yeek),
            },
        },
    ]
    for candidate in candidates:
        candidate["accepted"] = all(
            (not value if name == "taken_kill_quest_requires_walk_in" else value)
            if isinstance(value, bool)
            else value["value"]
            for name, value in candidate["predicates"].items()
        )
    return candidates


def _session_state(session: Any) -> Any:
    if session is None:
        return None
    action = (
        session.pending_action
        or session.prepared_action
        or session.current_action
    )
    return {
        "phase": getattr(action, "phase", None),
        "required_context": getattr(session, "required_context", None),
        "pending_action": jsonable(getattr(session, "pending_action", None)),
        "executable": getattr(session, "executable", None),
    }


def decision_record(
    policy: Any,
    snapshot: Any,
    key: str,
    reason: str,
    before: Any,
    predecision: str,
    assignment: dict[str, Any] | None,
    relative_decision: int,
) -> dict[str, Any]:
    # All method calls are made on this disposable pre-decision clone.
    clone = restore_checkpoint(type(policy), predecision)
    ledger = clone._town_visit_ledger
    plan = clone._town_errand_plan
    calibration = clone.calibration_entry_state(snapshot)
    claims_active = clone._town_claims_active(snapshot)
    claim_categories = list(getattr(clone, "_town_claim_categories", ()))
    store = snapshot.store
    return {
        "format": 1,
        "relative_decision": relative_decision,
        "turn": snapshot.turn,
        "snapshot": {
            "type": type(snapshot).__name__,
            "store_context": None if store is None else jsonable(store),
            "floor_key": jsonable(snapshot.floor_key),
            "town_id": getattr(snapshot, "town_id", None),
            "position": jsonable(snapshot.player.position),
        },
        "emitted_key": key,
        "last_reason": reason,
        "town_blocked_reason": {"before": before, "after": policy._town_blocked_reason},
        "assignment": assignment,
        "calibration": calibration,
        "town_claims": {"active": claims_active, "categories": claim_categories},
        "town_store_attempted": jsonable(clone._town_store_attempted),
        "visit_ledger": {
            "blocked_stores": sorted(ledger.blocked_stores),
            "approach_failures": jsonable(ledger.approach_fails),
        },
        "errand_current_stop": (
            None if plan is None or plan.index >= len(plan.stops) else plan.stops[plan.index]
        ),
        "fundraising_mode": clone._fundraising_mode,
        "equipment_transaction_session": _session_state(clone._equipment_transaction_session),
        "home_pending_item": jsonable(clone._home_pending_item),
        "recall_destination_candidates": _recall_candidates(clone, snapshot),
        # Pickle preserves Python container/key/dataclass types that a generic JSON
        # projection loses. Replay each decision from its own checkpoint; never chain
        # decisions from an earlier record because the live loop mutates between them.
        "predecision_policy_checkpoint_pickle_b64": predecision,
        "snapshot_pickle_b64": base64.b64encode(pickle.dumps(snapshot, protocol=5)).decode("ascii"),
    }


def write_window(path: Path, records: list[dict[str, Any]], *, replace: bool) -> None:
    """Write one bounded four-decision window; a new onset replaces the old one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if replace else "a"
    with path.open(mode, encoding="utf-8") as file:
        for record in records:
            json.dump(record, file, ensure_ascii=False, separators=(",", ":"))
            file.write("\n")
