"""Pure emit-time ownership checks for in-flight store visits."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from hengbot.policy_types import StoreVisit, StoreVisitPhase


TOWN_TRAVEL_STORE_SYMBOLS = ("!", '"', "#", "$", "%", "&", "'", "(")
_MOVEMENT_DELTAS = {
    "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
    "4": (0, -1), "6": (0, 1),
    "1": (1, -1), "2": (1, 0), "3": (1, 1),
}


@dataclass(frozen=True)
class EmitOwnershipVerdict:
    """The form-B verdict and the evidence used to reach it."""

    blocked: bool
    target_store: int | None
    visit_store: int | None
    phase: str | None
    in_flight_clause: str | None
    target_source: str

    def as_dict(self) -> dict:
        return asdict(self)


def in_flight_clause(visit: StoreVisit | None) -> str | None:
    """Name the first clause that makes a store visit in flight."""
    if visit is None:
        return None
    if visit.operation_posted and not visit.operation_released:
        return "operation-posted-not-released"
    if visit.operation_released and not visit.operation_effect_observed:
        return "operation-released-effect-not-observed"
    if visit.phase == StoreVisitPhase.ENTERING and visit.posted_sequence is not None:
        return "entering-with-posted-sequence"
    if (
        visit.phase == StoreVisitPhase.LEAVING
        and (visit.posted_sequence is not None or visit.posted_turn is not None)
    ):
        return "leaving-with-posted-sequence"
    return None


def derive_target_store(snapshot, key: str, approach_store: int | None) -> tuple[int | None, str]:
    """Derive a key's store target from its pre-emission town context."""
    if snapshot.store is not None:
        return snapshot.store.store_type, "snapshot.store.store_type"
    if approach_store is not None:
        return approach_store, "_shopping_approach_store_type"
    for store_type, symbol in enumerate(TOWN_TRAVEL_STORE_SYMBOLS):
        if key == f"\x1b`n{symbol}.":
            return store_type, "native-travel-key"
    delta = _MOVEMENT_DELTAS.get(key)
    if delta is not None:
        position = snapshot.player.position
        grid = snapshot.grid_at(type(position)(position.x + delta[0], position.y + delta[1]))
        if grid is not None and grid.store_number is not None:
            return grid.store_number, "stepped-onto-store-grid"
    return None, "undetermined"


def emit_ownership_verdict(
    visit: StoreVisit | None, snapshot, key: str, approach_store: int | None,
) -> EmitOwnershipVerdict:
    """Evaluate form B without mutating the visit, snapshot, or decision."""
    clause = in_flight_clause(visit)
    target_store, target_source = derive_target_store(snapshot, key, approach_store)
    visit_store = None if visit is None else visit.store_type
    return EmitOwnershipVerdict(
        blocked=bool(
            clause is not None
            and target_store is not None
            and target_store != visit_store
        ),
        target_store=target_store,
        visit_store=visit_store,
        phase=None if visit is None else visit.phase.value,
        in_flight_clause=clause,
        target_source=target_source,
    )
