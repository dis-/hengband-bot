"""Single authority for every physical visit to the Home."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Hashable


class HomeVisitKind(str, Enum):
    SCAN = "scan"
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    EQUIPMENT_MUTATION = "equipment-mutation"
    CALIBRATION_RESTORE = "calibration-restore"
    RECOVERY = "recovery"


class HomeVisitState(str, Enum):
    IDLE = "idle"
    FILED = "filed"
    APPROACHING = "approaching"
    ENTRY_PENDING = "entry-pending"
    OBSERVING = "observing"
    OPERATING = "operating"
    EXIT_PENDING = "exit-pending"
    REPORTED = "reported"
    DEFECT = "defect"


@dataclass(frozen=True)
class HomeVisitRequest:
    """Immutable work filed before Home routing is allowed to begin."""

    kind: HomeVisitKind
    requester: str
    item_identity: Hashable | None = None
    address: Hashable | None = None
    quantity: int = 1
    keep_set: frozenset[Hashable] = frozenset()
    shelving_plan: tuple[Hashable, ...] = ()
    batch: tuple[Hashable, ...] = ()

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError("Home visit quantity must be positive")
        if self.kind in {HomeVisitKind.DEPOSIT, HomeVisitKind.WITHDRAW}:
            if self.item_identity is None:
                raise ValueError("item visit requires an identity")
        if (
            self.kind == HomeVisitKind.DEPOSIT
            and self.item_identity in self.keep_set
        ):
            raise ValueError("retention-wins")


@dataclass(frozen=True)
class HomeVisitReport:
    request: HomeVisitRequest
    outcome: str
    visit_id: int
    attempts_used: int
    defect: str | None = None


@dataclass
class HomeVisitExecutor:
    """Own approach, context, one operation, exit, and explicit reporting.

    ``attempt_limit`` is installed once for the town epoch. Filing another
    optimizer request never replenishes it.  Call ``reset_epoch`` only after an
    observed town/dungeon epoch change, not after replanning.
    """

    attempt_limit: int
    state: HomeVisitState = HomeVisitState.IDLE
    request: HomeVisitRequest | None = None
    queued: list[HomeVisitRequest] = field(default_factory=list)
    report: HomeVisitReport | None = None
    visit_id: int = 0
    attempts_used: int = 0
    fresh_evidence: Hashable | None = None
    operation: tuple[str, Hashable | None] | None = None
    operation_history: list[tuple[str, Hashable | None]] = field(default_factory=list)
    # The immediately preceding completed inventory mutation survives report
    # consumption.  It is effect evidence, not an authorization blacklist.
    # The requester/direction scope catches the captured standing-digger take
    # followed by transaction put without classifying normal deposit/withdraw
    # composition as churn.
    previous_completed_delta: tuple[
        int, Hashable | None, HomeVisitKind, str
    ] | None = None
    semantic_churn_cooldown: bool = False
    context_token: tuple[str, int] | None = None

    @property
    def active(self) -> bool:
        return self.state not in {
            HomeVisitState.IDLE, HomeVisitState.REPORTED, HomeVisitState.DEFECT
        }

    @property
    def entry_pending(self) -> bool:
        return self.state == HomeVisitState.ENTRY_PENDING

    def file(self, request: HomeVisitRequest) -> str:
        if self.request == request and self.active:
            return "active"
        if request in self.queued:
            return "queued"
        if self.active:
            self.queued.append(request)
            return "queued"
        if self.semantic_churn_cooldown:
            self._report(request, "semantic-churn-cooldown")
            return "rejected"
        if (
            self.attempts_used >= self.attempt_limit
            and not self._composes_equipment_withdrawal(request)
        ):
            self._report(request, "attempt-budget-exhausted")
            return "rejected"
        self.request = request
        self.report = None
        self.fresh_evidence = None
        self.operation = None
        self.context_token = None
        self.state = HomeVisitState.FILED
        return "filed"

    def begin_approach(self, outside_generation: int) -> bool:
        if self.state not in {HomeVisitState.FILED, HomeVisitState.APPROACHING}:
            return False
        if (
            self.attempts_used >= self.attempt_limit
            and not (
                self.request is not None
                and self._composes_equipment_withdrawal(self.request)
            )
        ):
            assert self.request is not None
            self._report(self.request, "attempt-budget-exhausted")
            return False
        if self.state == HomeVisitState.FILED:
            self.visit_id += 1
            self.attempts_used += 1
        self.context_token = ("outside", outside_generation)
        self.state = HomeVisitState.APPROACHING
        return True

    def _composes_equipment_withdrawal(self, request: HomeVisitRequest) -> bool:
        """Let an already-started equipment swap shelve its displaced item."""
        previous = self.previous_completed_delta
        return (
            previous is not None
            and previous[0] > 0
            and previous[2] == HomeVisitKind.EQUIPMENT_MUTATION
            and previous[3] == "equipment-transaction"
            and request.kind == HomeVisitKind.EQUIPMENT_MUTATION
            and request.requester == "equipment-transaction"
            and request.address is None
            and bool(request.shelving_plan)
        )

    def post_entry(self, outside_generation: int) -> bool:
        if self.state != HomeVisitState.APPROACHING:
            return False
        if self.context_token != ("outside", outside_generation):
            return False
        self.state = HomeVisitState.ENTRY_PENDING
        self.context_token = None
        return True

    def observe_inside(self, evidence: Hashable, generation: int) -> None:
        if self.state not in {
            HomeVisitState.ENTRY_PENDING, HomeVisitState.OBSERVING
        }:
            return
        self.fresh_evidence = evidence
        self.context_token = ("inside", generation)
        self.state = HomeVisitState.OBSERVING

    def observe_outside_ready(self, evidence: Hashable, generation: int) -> None:
        """Bind fresh ``~9`` address evidence at the Home entrance.

        Hengband flushes characters after the entry key, so the established
        atomic composer posts entry + one operation + exit from this outside
        command-loop generation.  It is still a Home operation, never an
        outside-only command.
        """
        if self.state not in {
            HomeVisitState.FILED, HomeVisitState.APPROACHING,
            HomeVisitState.OBSERVING,
        }:
            return
        self.fresh_evidence = evidence
        self.context_token = ("outside-ready", generation)
        self.state = HomeVisitState.OBSERVING

    def may_post_inside(self, generation: int) -> bool:
        return (
            self.state == HomeVisitState.OBSERVING
            and self.fresh_evidence is not None
            and self.context_token in {
                ("inside", generation), ("outside-ready", generation)
            }
            and self.operation is None
        )

    def record_operation(
        self, action: str, identity: Hashable | None, generation: int
    ) -> bool:
        if not self.may_post_inside(generation):
            return False
        self.operation = (action, identity)
        self.operation_history.append(self.operation)
        self.state = HomeVisitState.OPERATING
        return True

    def post_exit(self) -> bool:
        if self.state not in {HomeVisitState.OBSERVING, HomeVisitState.OPERATING}:
            return False
        self.state = HomeVisitState.EXIT_PENDING
        self.context_token = None
        return True

    def observe_outside(self, *, effect_observed: bool) -> None:
        if self.state != HomeVisitState.EXIT_PENDING or self.request is None:
            return
        empty_ok = self.request.kind in {
            HomeVisitKind.SCAN, HomeVisitKind.RECOVERY
        }
        outcome = "completed" if (
            effect_observed or (self.operation is None and empty_ok)
        ) else "unfulfilled"
        if effect_observed and self.operation is not None:
            action, identity = self.operation
            delta = self.request.quantity * (1 if action == "take" else -1)
            previous = self.previous_completed_delta
            calibration_restore = (
                self.request.kind == HomeVisitKind.CALIBRATION_RESTORE
                or (previous is not None
                    and previous[2] == HomeVisitKind.CALIBRATION_RESTORE)
            )
            captured_takeput_pair = (
                previous is not None
                and previous[2] == HomeVisitKind.WITHDRAW
                and previous[3] == "standing-digger"
                and self.request.kind == HomeVisitKind.DEPOSIT
                and self.request.requester == "equipment-transaction"
            )
            if (
                previous is not None
                and previous[0] + delta == 0
                and not calibration_restore
                and captured_takeput_pair
            ):
                self.semantic_churn_cooldown = True
                self._defect(
                    "zero-net-inventory-delta:"
                    f"{previous[1]!r}:{identity!r}"
                )
                return
            self.previous_completed_delta = (
                delta, identity, self.request.kind, self.request.requester
            )
        self._report(self.request, outcome)

    def consume_report(self) -> HomeVisitReport | None:
        report = self.report
        if report is None:
            return None
        self.report = None
        self.request = None
        self.fresh_evidence = None
        self.operation = None
        self.operation_history.clear()
        self.context_token = None
        self.state = HomeVisitState.IDLE
        if self.queued:
            next_request = self.queued.pop(0)
            self.file(next_request)
        return report

    def report_unoperated(self, outcome: str) -> bool:
        """Terminally report a scan/recovery visit before filing later work."""
        if (
            self.request is None
            or self.operation is not None
        ):
            return False
        self._report(self.request, outcome)
        return True

    def reset_epoch(self) -> None:
        if self.active:
            raise RuntimeError("cannot reset an active Home visit")
        self.attempts_used = 0
        self.operation_history.clear()
        self.previous_completed_delta = None

    def _report(self, request: HomeVisitRequest, outcome: str) -> None:
        self.report = HomeVisitReport(
            request, outcome, self.visit_id, self.attempts_used
        )
        self.state = HomeVisitState.REPORTED

    def _defect(self, defect: str) -> None:
        assert self.request is not None
        self.report = HomeVisitReport(
            self.request, "defect", self.visit_id, self.attempts_used, defect
        )
        self.state = HomeVisitState.DEFECT
