from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from hengbot.latch_onset_capture import assignment_provenance
from hengbot.model import Position, Snapshot, STORE_HOME
from hengbot.policy_constants import LEAVE_STORE_KEY
from hengbot.policy_types import (
    EmissionState,
    OwnerProgressCore,
    StoreVisit,
    StoreVisitPhase,
)


@dataclass(frozen=True)
class TownOwnerRegistration:
    """Advisory registration for one family of town turn producers."""

    name: str
    reason_prefixes: tuple[str, ...]
    progress_metric: str
    budget_references: tuple[str, ...]
    budget: int


class TownTurnArbiter:
    """Observe the legacy town ladder and preview bounded owner retirement.

    ARB-1 deliberately has no selector or retirement side effects.  The policy
    supplies the existing budget constants and the already-selected reason;
    this object only attributes and records the decision.
    """

    def __init__(self, budgets: Mapping[str, tuple[tuple[str, ...], int]]) -> None:
        def registration(
            name: str,
            prefixes: tuple[str, ...],
            metric: str,
        ) -> TownOwnerRegistration:
            references, budget = budgets[name]
            return TownOwnerRegistration(
                name, prefixes, metric, references, max(1, budget)
            )

        # Ordered from narrow families to explicitly registered compatibility
        # families. Unknown reasons remain falsifiable as ``unregistered``.
        registrations = (
            registration("home-errand", ("home-errand:",), "executor state advance"),
            registration("home-scan", ("home:request-knowledge", "home:scan", "home:seek-"), "home scan completion"),
            registration("home-visit", ("home:", "home-visit:", "home-disposal:"), "addressed Home state delta"),
            registration("shop-sell", ("shop:sale", "shop:sell-", "shop:batch-sale", "shop:batch-sell", "shop:batch-inscribe", "shop:one-shot-sale", "shop:one-shot-sell", "shop:unsellable-", "shop:defective-target-leave", "shop:leave", "shop:stuck-leave", "shop:invalid", "shop:retain-standing-digging-tool", "town:destroy-overflow", "equipment:sale"), "gold up and inventory delta"),
            registration("shop-buy", ("shop:one-shot-buy", "shop:one-shot-in-flight", "shop:one-shot-page-not-zero", "shop:buy", "shop:await-", "shop:observe", "shop:home-first-before-purchase", "shop:store-context-exit", "town:wait-restock"), "gold down and inventory delta"),
            registration("store-router", ("shop:approach", "shop:travel", "store:", "town:travel", "town-travel:", "town:teleport", "wilderness:enter-town", "wilderness:global-travel", "wilderness:enter-global", "bounty:approach"), "distance to store goal"),
            registration("equipment-opt", ("equipment-optimization:", "equipment:opt", "optimizer:"), "optimization signature delta"),
            registration("equipment-txn", ("equipment-transaction:", "equipment-mutation:", "equipment:", "town:restore-combat-weapon", "town:remove-no-teleport-weapon", "wield-light"), "equipment session or slot delta"),
            registration("calibration", ("calibration:",), "calibration phase advance"),
            registration("identification", ("identify:", "identification:", "item-processing:", "inventory:"), "known item or failure-set delta"),
            registration("fundraising", ("fundraise:", "fundraising:", "mining:"), "gold or vein delta"),
            registration("curse-enchant", ("town:remove-curse", "town:enchant-launcher-", "curse:", "remove-curse:", "enchant:"), "curse or enchantment delta"),
            registration("cross-town", ("town:cross-town", "town:morivant"), "expedition state advance"),
            registration("survival", ("survival:", "weak-fainting", "status-threat:", "town:kill-mob", "town:eat-before-travel", "town:recover", "town:seek-shelter", "confused:", "item:", "mana-food:", "stat-gain:", "wilderness:escape-scroll", "wilderness:flee", "refill-light", "restore-lantern", "eat", "rest"), "survival supply or status delta"),
            registration("departure", ("depart", "descend", "recall", "return:", "stair:", "postlevel:", "repetition-depart", "town:repetition-depart", "town:entrance", "town:wait-recall", "town:await-recall-confirmation", "town:recall-to-", "town:cancel-", "town:unsafe-recall-fallback", "wilderness:no-safe-route"), "stairs, recall, or floor delta"),
            registration("town-plan", ("town:blocked", "town:procurement", "procurement:", "town-plan:", "quest:readiness", "town:repetition-required-shopping"), "completed plan or claim delta"),
            registration("rumor", ("town:rumor",), "departure-ready gate delta"),
            registration("quest-request", ("fixedquest:", "quest:", "opening-q34:", "bounty:cashout", "bounty:step-off"), "quest request or phase advance"),
            registration("detectors", ("livelock:", "town-progress-invariant:", "town-liveness-invariant:", "town:cycle-break", "posting-contract:", "stuck:", "novel:", "breakout", "no-wait:", "nav:", "warning:"), "block release or visible stop"),
            registration("misc", ("policy:", "town:misc:", "town:character-dump", "periodic:", "explore", "melee", "hunt", "seek-loot", "wait"), "town progress vector delta"),
        )
        self.registry = {entry.name: entry for entry in registrations}
        self._ordered = registrations
        self._owner: str | None = None
        self._tenure = 0
        self._no_progress_by_owner: dict[str, int] = {}
        self._vector_by_owner: dict[str, object] = {}
        self.telemetry: dict[str, object] | None = None

    def owner_for_reason(self, reason: str) -> str:
        normalized = reason or "policy:none"
        for entry in self._ordered:
            if entry.reason_prefixes and normalized.startswith(entry.reason_prefixes):
                return entry.name
        return "unregistered"

    def observe(
        self,
        *,
        in_town: bool,
        reason: str,
        progress_vector: object,
    ) -> dict[str, object] | None:
        if not in_town:
            self._owner = None
            self._tenure = 0
            self._no_progress_by_owner.clear()
            self._vector_by_owner.clear()
            self.telemetry = None
            return None
        owner = self.owner_for_reason(reason)
        same_owner = owner == self._owner
        previous_vector = self._vector_by_owner.get(owner)
        progress = previous_vector is None or previous_vector != progress_vector
        self._tenure = self._tenure + 1 if same_owner else 1
        no_progress = 0 if progress else self._no_progress_by_owner.get(owner, 0) + 1
        self._no_progress_by_owner[owner] = no_progress
        self._vector_by_owner[owner] = progress_vector
        registration = self.registry.get(owner)
        remaining = (
            max(0, registration.budget - no_progress)
            if registration is not None else None
        )
        self.telemetry = {
            "owner": owner,
            "tenure": self._tenure,
            "progress": progress,
            "budget_remaining_estimate": remaining,
            "would_retire": registration is not None and not progress and remaining == 0,
        }
        self._owner = owner
        return dict(self.telemetry)


class TownArbiterMixin:
    @property
    def _town_blocked_reason(self) -> str | None:
        return getattr(self, "_town_blocked_reason_value", None)

    @_town_blocked_reason.setter
    def _town_blocked_reason(self, value: str | None) -> None:
        previous = getattr(self, "_town_blocked_reason_value", None)
        self._town_blocked_reason_value = value
        if (
            previous is None
            and value is not None
            and getattr(self, "_latch_capture_path", None) is not None
        ):
            try:
                self._latch_capture_assignment = assignment_provenance()
            except Exception:
                # Diagnostics must never change a decision or prevent a latch.
                self._latch_capture_assignment = {
                    "assigning_file": None,
                    "assigning_line": None,
                    "caller_chain": [],
                    "capture_error": "assignment-provenance-failed",
                }

    @property
    def _shopping_approach_store_type(self) -> int | None:
        visit = self._store_visit
        return visit.store_type if visit is not None else None

    @_shopping_approach_store_type.setter
    def _shopping_approach_store_type(self, value: int | None) -> None:
        if value is None:
            return
        if self._store_visit is None:
            self._store_visit = StoreVisit(
                owner="store-router", purpose="town-need", store_type=value,
                goal=self._store_visit_pending_goal,
                opened_sequence=self._decision_sequence,
            )
            self._store_visit_pending_goal = None

    @property
    def _shopping_approach_goal(self) -> Position | None:
        visit = self._store_visit
        return visit.goal if visit is not None else None

    @_shopping_approach_goal.setter
    def _shopping_approach_goal(self, value: Position | None) -> None:
        if self._store_visit is not None:
            self._store_visit.goal = value
        else:
            self._store_visit_pending_goal = value

    @property
    def _store_entry_wait_owner(self) -> int | None:
        visit = self._store_visit
        if visit is None or visit.phase != StoreVisitPhase.ENTERING:
            return None
        return visit.store_type

    @_store_entry_wait_owner.setter
    def _store_entry_wait_owner(self, value: int | None) -> None:
        if value is None:
            return
        visit = self._store_visit
        if visit is None:
            self._store_visit = StoreVisit(
                owner="store-router", purpose="store-entry", store_type=value,
                opened_sequence=self._decision_sequence,
            )
            visit = self._store_visit
        if visit.store_type == value:
            visit.transition(StoreVisitPhase.ENTERING)
            visit.armed_sequence = self._decision_sequence

    @property
    def _store_entry_wait_key(self) -> str | None:
        visit = self._store_visit
        return visit.composed_key if visit is not None else None

    @_store_entry_wait_key.setter
    def _store_entry_wait_key(self, value: str | None) -> None:
        if self._store_visit is not None and value is not None:
            self._store_visit.composed_key = value

    @property
    def _store_entry_posted_owner(self) -> int | None:
        visit = self._store_visit
        if visit is None or visit.phase != StoreVisitPhase.ENTERING:
            return None
        return visit.store_type if visit.posted_sequence is not None else None

    @_store_entry_posted_owner.setter
    def _store_entry_posted_owner(self, value: int | None) -> None:
        visit = self._store_visit
        if value is None:
            if visit is not None:
                visit.posted_sequence = None
            return
        self._store_entry_wait_owner = value
        assert self._store_visit is not None
        self._store_visit.posted_sequence = self._decision_sequence

    @property
    def _home_entry_operation_posted(self) -> bool:
        visit = self._store_visit
        return bool(
            visit is not None
            and visit.store_type == STORE_HOME
            and visit.operation_posted
        )

    @_home_entry_operation_posted.setter
    def _home_entry_operation_posted(self, value: bool) -> None:
        visit = self._store_visit
        if value and visit is None:
            visit = StoreVisit(
                owner="home-one-shot", purpose="bound-operation",
                store_type=STORE_HOME, phase=StoreVisitPhase.OPERATING,
                opened_sequence=self._decision_sequence,
            )
            self._store_visit = visit
        if visit is not None and visit.store_type == STORE_HOME:
            visit.operation_posted = value

    @property
    def _store_leave_inflight(self) -> tuple[int, int, int] | None:
        visit = self._store_visit
        if (
            visit is None
            or visit.phase != StoreVisitPhase.LEAVING
            or visit.posted_sequence is None
            or visit.posted_turn is None
        ):
            return None
        return visit.posted_sequence, visit.posted_turn, visit.store_type

    @_store_leave_inflight.setter
    def _store_leave_inflight(self, value: tuple[int, int, int] | None) -> None:
        visit = self._store_visit
        if value is None:
            if visit is not None and visit.phase == StoreVisitPhase.LEAVING:
                self._close_store_visit(visit.outcome or "completed")
            return
        sequence, turn, store_type = value
        if visit is None:
            visit = StoreVisit(
                owner="recovered-store-context", purpose="leave",
                store_type=store_type, opened_sequence=sequence,
            )
            self._store_visit = visit
        visit.transition(StoreVisitPhase.LEAVING, LEAVE_STORE_KEY)
        visit.posted_sequence = sequence
        visit.posted_turn = turn

    def _close_store_visit(self, outcome: str) -> None:
        visit = self._store_visit
        if visit is None:
            return
        if visit.operation_posted:
            if (
                self._store_buy_inflight is not None
                and self._store_buy_inflight[0] == visit.store_type
            ):
                self._store_buy_inflight = None
            if (
                self._batch_sell_pending is not None
                and self._batch_sell_pending.get("store_type") == visit.store_type
            ):
                self._batch_sell_pending = None
        visit.close(outcome)
        self._store_visit_last_closed = visit
        self._store_visit = None

    @staticmethod
    def _emission_item_state(item: object) -> tuple[object, ...]:
        return tuple(
            getattr(item, name, None)
            for name in (
                "slot", "tval", "sval", "name", "count", "charges",
                "inscription", "known", "fully_known", "is_equipment",
            )
        )

    @staticmethod
    def _town_progress_item_state(item: object) -> tuple[object, ...]:
        """Return stable item facts for town-cycle progress detection.

        Display names may contain live counters such as lantern fuel.  Those
        counters are useful to emission/owner observers, but they cannot prove
        that a blocked town decision made progress.
        """
        return tuple(
            getattr(item, name, None)
            for name in (
                "tval", "sval", "count", "charges", "inscription",
                "known", "fully_known", "pseudo_feeling",
            )
        )

    def _emission_state(self, snapshot: Snapshot) -> EmissionState:
        return EmissionState(
            floor=getattr(snapshot, "floor_key", None),
            position=snapshot.player.position,
            store_type=(
                snapshot.store.store_type if snapshot.store is not None else None
            ),
            inventory=tuple(sorted(
                (self._emission_item_state(item) for item in snapshot.inventory),
                key=repr,
            )),
            equipment=tuple(sorted(
                (self._emission_item_state(item) for item in snapshot.equipment),
                key=repr,
            )),
        )

    def _owner_progress_core(self, snapshot: Snapshot) -> OwnerProgressCore:
        return OwnerProgressCore(
            floor=getattr(snapshot, "floor_key", None),
            position=snapshot.player.position,
            gold=getattr(snapshot.player, "gold", 0),
            experience=getattr(snapshot.player, "exp", 0),
            inventory=tuple(sorted(
                (self._emission_item_state(item) for item in snapshot.inventory),
                key=repr,
            )),
            equipment=tuple(sorted(
                (self._emission_item_state(item) for item in snapshot.equipment),
                key=repr,
            )),
        )

    def _post_owner_expectation(
        self, snapshot: Snapshot, owner: str, *expected_changes: str
    ) -> None:
        self._owner_expectations.post(
            owner, self._owner_progress_core(snapshot), *expected_changes
        )

    def _owner_may_select(self, snapshot: Snapshot, owner: str) -> bool:
        return self._owner_expectations.may_select(
            owner, self._owner_progress_core(snapshot)
        )
