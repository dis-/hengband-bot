"""Observation-driven owner for one addressable Home withdrawal errand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HomeErrandState(str, Enum):
    IDLE = "idle"
    PENDING = "pending"
    NEED_KNOWLEDGE = "need-knowledge"
    COMPOSABLE = "composable"
    POSTED = "posted"
    DONE = "done"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class HomeErrandRequest:
    signature: tuple[str, int, int]
    quantity: int
    origin: str
    purpose: str


@dataclass
class HomeErrandExecutor:
    """Own the complete lifecycle of a migrated Home withdrawal.

    Policy supplies observations and retains command composition.  Keeping the
    executor free of policy callbacks prevents another owner from advancing it
    through a side effect or a guessed command result.
    """

    state: HomeErrandState = HomeErrandState.IDLE
    request: HomeErrandRequest | None = None
    before_count: int | None = None
    entries_without_address_progress: int = 0
    addressed_entries: int = 0
    stopped_fact: str | None = None

    @property
    def active(self) -> bool:
        return self.state not in {
            HomeErrandState.IDLE,
            HomeErrandState.DONE,
            HomeErrandState.FAILED,
            HomeErrandState.STOPPED,
        }

    @property
    def needs_knowledge(self) -> bool:
        return self.state == HomeErrandState.NEED_KNOWLEDGE

    def file(self, request: HomeErrandRequest, *, knowledge_current: bool) -> bool:
        if self.active:
            return self.request == request
        self.request = request
        self.before_count = None
        self.entries_without_address_progress = 0
        self.addressed_entries = 0
        self.stopped_fact = None
        self.state = HomeErrandState.PENDING
        self.observe_knowledge(knowledge_current)
        return True

    def observe_knowledge(self, current: bool) -> None:
        if self.state not in {
            HomeErrandState.PENDING,
            HomeErrandState.NEED_KNOWLEDGE,
            HomeErrandState.COMPOSABLE,
        }:
            return
        self.state = (
            HomeErrandState.COMPOSABLE if current
            else HomeErrandState.NEED_KNOWLEDGE
        )

    def observe_scan_refused(self, fact: str) -> None:
        if self.state == HomeErrandState.NEED_KNOWLEDGE:
            self.state = HomeErrandState.STOPPED
            self.stopped_fact = fact

    def observe_unaddressed_entry(self, visit_limit: int, fact: str) -> None:
        if self.state not in {
            HomeErrandState.NEED_KNOWLEDGE,
            HomeErrandState.COMPOSABLE,
        }:
            return
        self.entries_without_address_progress += 1
        if self.entries_without_address_progress >= visit_limit:
            self.state = HomeErrandState.STOPPED
            self.stopped_fact = fact

    def post(self, before_count: int) -> None:
        if self.state != HomeErrandState.COMPOSABLE:
            raise ValueError("Home errand is not composable")
        self.before_count = before_count
        self.addressed_entries += 1
        self.state = HomeErrandState.POSTED

    def observe_outside(self, count: int) -> None:
        if self.state != HomeErrandState.POSTED or self.before_count is None:
            return
        self.state = (
            HomeErrandState.DONE if count > self.before_count
            else HomeErrandState.FAILED
        )

    def finish(self) -> None:
        if self.state in {HomeErrandState.DONE, HomeErrandState.FAILED}:
            self.state = HomeErrandState.IDLE
            self.request = None
            self.before_count = None

    def reason(self, action: str) -> str:
        if self.state == HomeErrandState.STOPPED and self.stopped_fact:
            return f"home-errand:stopped:{self.stopped_fact}"
        purpose = self.request.purpose if self.request is not None else "none"
        return f"home-errand:{action}:{purpose}"
