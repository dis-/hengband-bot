"""Pure policy state types shared across policy domains."""

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal

from hengbot.model import Position, Snapshot
from hengbot.policy_constants import (
    TOWN_STOP_PASS_LIMIT,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
)

# This is a game-mirror-free safety bound: a mistaken expectation declaration
# may delay an owner, but must never deadlock it forever.
OWNER_EXPECTATION_MAX_TURNS = 10

@dataclass
class TownTravelProgress:
    goal: Position
    best_distance: int
    stalls: int
    turn_stalls: int
    last_turn: int

    def __getitem__(self, index: int) -> Position | int:
        """Retain the read-only tuple-style probes used by policy tests."""
        return (
            self.goal,
            self.best_distance,
            self.stalls,
            self.turn_stalls,
            self.last_turn,
        )[index]

    def record(self, distance: int, turn: int) -> Literal["reissue", "fallback"]:
        """Record one repeated travel decision using the current turn domain."""
        if distance < self.best_distance:
            self.best_distance = distance
            self.stalls = 0
            self.turn_stalls = 0
            self.last_turn = turn
        elif turn != self.last_turn:
            self.turn_stalls += 1
            self.stalls = 0
            self.last_turn = turn
            if self.turn_stalls >= TOWN_TRAVEL_TURN_STALL_LIMIT:
                return "fallback"
        else:
            self.stalls += 1
            if self.stalls >= TOWN_TRAVEL_STALL_LIMIT:
                return "fallback"
        return "reissue"


class StoreVisitPhase(str, Enum):
    APPROACHING = "approaching"
    ENTERING = "entering"
    OPERATING = "operating"
    LEAVING = "leaving"
    CLOSED = "closed"


@dataclass
class StoreVisit:
    """The sole authority for one deliberate trip to one store."""

    owner: str
    purpose: str
    store_type: int
    phase: StoreVisitPhase = StoreVisitPhase.APPROACHING
    composed_key: str | None = None
    goal: Position | None = None
    opened_sequence: int = 0
    armed_sequence: int | None = None
    posted_sequence: int | None = None
    posted_turn: int | None = None
    operation_posted: bool = False
    operation_key: str | None = None
    operation_released: bool = False
    operation_effect_observed: bool = False
    outcome: str | None = None

    def transition(self, phase: StoreVisitPhase, key: str | None = None) -> None:
        if self.phase == StoreVisitPhase.CLOSED:
            raise RuntimeError("closed store visit cannot transition")
        self.phase = phase
        if key is not None:
            self.composed_key = key

    def close(self, outcome: str) -> None:
        self.operation_posted = False
        self.operation_key = None
        self.operation_released = False
        self.phase = StoreVisitPhase.CLOSED
        self.outcome = outcome


@dataclass(frozen=True)
class EmissionState:
    """Observable state whose recurrence proves an emitted cycle made no progress."""

    floor: tuple[int, int, int] | None
    position: Position
    store_type: int | None
    inventory: tuple[tuple[object, ...], ...]
    equipment: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class OwnerProgressCore:
    """Durable progress facts an issued owner is allowed to wait for."""

    floor: tuple[int, int, int] | None
    position: Position
    store_type: int | None
    turn: int
    hp: int
    recalling: bool
    gold: int
    experience: int
    inventory: tuple[tuple[object, ...], ...]
    equipment: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class OwnerExpectation:
    progress_core: OwnerProgressCore
    expected_changes: frozenset[str]


class OwnerExpectationRegistry:
    """Yield result-waiting owners until their issuing progress core changes."""

    def __init__(self) -> None:
        self._pending: dict[str, OwnerExpectation] = {}

    def post(
        self,
        owner: str,
        progress_core: OwnerProgressCore,
        *expected_changes: str,
    ) -> None:
        if not expected_changes:
            raise ValueError("an owner expectation must name an observable change")
        valid_changes = frozenset(OwnerProgressCore.__dataclass_fields__)
        unknown = frozenset(expected_changes) - valid_changes
        if unknown:
            raise ValueError(
                "unknown owner expectation progress field(s): "
                + ", ".join(sorted(unknown))
            )
        self._pending[owner] = OwnerExpectation(
            progress_core, frozenset(expected_changes)
        )

    def may_select(self, owner: str, progress_core: OwnerProgressCore) -> bool:
        pending = self._pending.get(owner)
        if pending is None:
            return True
        if pending.progress_core.floor != progress_core.floor:
            self._pending.pop(owner, None)
            return True
        if (
            progress_core.turn - pending.progress_core.turn
            >= OWNER_EXPECTATION_MAX_TURNS
        ):
            self._pending.pop(owner, None)
            return True
        if any(
            getattr(pending.progress_core, component)
            != getattr(progress_core, component)
            for component in pending.expected_changes
        ):
            self._pending.pop(owner, None)
            return True
        return False

    def yield_owner(self, owner: str) -> None:
        """Keep an already-posted owner yielded after sender refusal."""
        # The pending expectation already contains the issuing observation.
        # This named operation makes refusal migration explicit without a
        # second owner-specific latch.
        if owner not in self._pending:
            return

    def is_pending(self, owner: str) -> bool:
        return owner in self._pending

    def release(self, owner: str) -> None:
        self._pending.pop(owner, None)

@dataclass(frozen=True)
class TownNeed:
    store_type: int
    category: str
    ordering_class: str


@dataclass(frozen=True)
class NeedSpec:
    category: str
    store_type: int | Callable[[Snapshot], int]
    ordering_class: str
    produces: Callable[[Snapshot], bool]
    satisfied: Callable[[Snapshot], bool]
    departure_blocking: bool
    budget: int = TOWN_STOP_PASS_LIMIT

    def resolve_store_type(self, snapshot: Snapshot) -> int:
        return self.store_type(snapshot) if callable(self.store_type) else self.store_type


@dataclass
class TownVisitLedger:
    store_visits: Counter[int] = field(default_factory=Counter)
    need_attempts: dict[str, int] = field(default_factory=dict)
    approach_fails: Counter[int] = field(default_factory=Counter)
    unsatisfied_passes: Counter[int] = field(default_factory=Counter)
    blocked_stores: set[int] = field(default_factory=set)
    blocked_store_limits: dict[int, int] = field(default_factory=dict)
    passes_since_progress: int = 0
    drift_warnings: list[str] = field(default_factory=list)
    satisfied_needs: set[tuple[int, str]] = field(default_factory=set)
    shelf_observations: dict[
        tuple[int, str], tuple[tuple[int, int], ...]
    ] = field(default_factory=dict)
    pending_store_transaction: tuple[int, int] | None = None
    pending_store_context_waits: int = 0
    nonhome_attempted_without_effect: dict[int, tuple[object, ...]] = field(
        default_factory=dict
    )
    pending_nonhome_effect_observation: set[int] = field(default_factory=set)


@dataclass
class CrossTownShoppingExpedition:
    trigger_town_id: int
    blocking_categories: tuple[str, ...]
    shortage_costs: dict[str, int]
    reserve: int
    required_gold: int
    candidate_order: tuple[int, ...]
    tried_towns: list[int] = field(default_factory=list)
    target_town_id: int | None = None


@dataclass
class MorivantFullIdentifyExpedition:
    origin_town_id: int
    target_signatures: tuple[tuple[str, int, int], ...]
    home_target_signatures: tuple[tuple[str, int, int], ...] = ()
    temporary_deposits: list[tuple[tuple[str, int, int], int]] = field(
        default_factory=list
    )
    phase: str = "travel"
    home_inflight: tuple[str, tuple[str, int, int], int, int] | None = None
    home_failures: Counter[tuple[str, tuple[str, int, int]]] = field(
        default_factory=Counter
    )
    seen_home_pages: set[tuple[tuple[str, int, int], ...]] = field(
        default_factory=set
    )
    returning: bool = False


@dataclass
class EscapeState:
    """Single owner and decision ledger for escape-family policy."""

    floor: tuple[int, int, int] | None = None
    owner: str | None = None
    rung: str | None = None
    stable_decisions: int = 0
    budgets: Counter[str] = field(default_factory=Counter)
    decision_token: int | None = None
    ledger: dict[str, object] = field(default_factory=dict)

    def begin_decision(self, snapshot: Snapshot, decision_token: int) -> None:
        floor_key = getattr(snapshot, "floor_key", None)
        if floor_key is not None and self.floor != floor_key:
            self.floor = floor_key
            self.owner = None
            self.rung = None
            self.stable_decisions = 0
            self.budgets.clear()
        if decision_token != self.decision_token:
            self.decision_token = decision_token
            self.ledger.clear()

    def read_once(
        self, snapshot: Snapshot, key: str, producer: Callable[[], object]
    ) -> object:
        if key not in self.ledger:
            self.ledger[key] = producer()
        return self.ledger[key]

    def enter(self, owner: str, rung: str) -> None:
        self.owner = owner
        self.rung = rung
        self.stable_decisions = 0

    def release(self) -> None:
        self.owner = None
        self.rung = None
        self.stable_decisions = 0


@dataclass
class ChokeEngagementPlan:
    """Persistent owner for one validated melee-swarm engagement."""

    floor: tuple[int, int, int]
    phase: str
    destination: Position
    covered_retreat_direction: tuple[int, int]
    trigger_last_seen: dict[int, Position]
    start_exp: int
    start_gold: int
    start_breeder_count: int
    last_player_hp: int
    closest_destination_distance: int = 0
    decisions_consumed: int = 1
    last_movement: tuple[Position, Position] | None = None
    sight_loss_decisions: int = 0
    no_progress_decisions: int = 0
    release_cause: str | None = None


@dataclass(frozen=True)
class CrossDecisionLatch:
    """Declared owner and per-decision release evaluator for a policy latch."""

    owner: str
    release_evaluator: str
    permanent_values: tuple[str, ...] = ()
    retained_values: tuple[str, ...] = ()
    retained_prefixes: tuple[str, ...] = ()
    release_sites: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupplyStatus:
    kind: str
    count: int
    required_return: int
    required_departure: int
    obtainable: bool
    stores: tuple[int, ...]


@dataclass
class TownErrandPlan:
    stops: list[int]
    need_categories: dict[int, tuple[str, ...]] = field(default_factory=dict)
    index: int = 0
    inserted_this_visit: list[int] | None = None
    skipped_latched: list[int] | None = None
    completed_this_visit: list[int] | None = None
    blocked_this_visit: list[int] | None = None
    current_stop_passes: int = 0

    def __post_init__(self) -> None:
        if self.inserted_this_visit is None:
            self.inserted_this_visit = []
        if self.skipped_latched is None:
            self.skipped_latched = []
        if self.completed_this_visit is None:
            self.completed_this_visit = []
        if self.blocked_this_visit is None:
            self.blocked_this_visit = []
