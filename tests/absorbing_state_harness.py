"""Physics-driven liveness harness for public ``choose_key`` decisions.

The policy is deliberately a black box here.  A catalogue entry owns a small
world model which emits the next Snapshot and applies every posted key before
that next observation.  This keeps game physics explicit and makes adding a
new incident a builder plus a few model methods, rather than another bespoke
decision-counting loop.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Protocol

from hengbot.model import Snapshot


class Physics(Protocol):
    """The game-side half of one JSONL request/reply cycle."""

    entries: int
    exits: int

    def snapshot(self, decision: int) -> Snapshot: ...

    def apply(self, key: str) -> None: ...

    def durable_fingerprint(self) -> object: ...

    def visible_terminal(self, reason: str) -> str | None: ...

    def deliver_events(self, policy: object) -> None: ...

    def release_modelled(self, reason: str) -> bool: ...


@dataclass(frozen=True)
class AbsorbingState:
    name: str
    decisions: int
    build: Callable[[], tuple[object, Physics]]


@dataclass(frozen=True)
class DriveResult:
    state: str
    passed: bool
    outcome: str
    decisions: int
    reasons: Counter[str]
    keys: Counter[str]
    entries: int
    exits: int
    first_stopped: int

    def report(self) -> str:
        return (
            f"{self.state}: {'PASS' if self.passed else 'FAIL'}: {self.outcome}; "
            f"decisions={self.decisions}; reasons={dict(self.reasons)}; "
            f"keys={dict(self.keys)}; entries={self.entries}; exits={self.exits}; "
            f"first_progress_stopped={self.first_stopped}"
        )


def drive(state: AbsorbingState) -> DriveResult:
    policy, world = state.build()
    reasons: Counter[str] = Counter()
    keys: Counter[str] = Counter()
    fingerprint = world.durable_fingerprint()
    first_stopped = 1
    last_progress = 0
    progress_events = 0
    longest_stall = 0
    final_reason = "<no decision>"

    for decision in range(1, state.decisions + 1):
        world.deliver_events(policy)
        key = policy.choose_key(world.snapshot(decision))
        reason = policy.last_reason
        final_reason = reason
        reasons[reason] += 1
        keys[key] += 1

        terminal = world.visible_terminal(reason)
        if terminal is not None:
            return DriveResult(
                state.name, True, f"visible terminal {terminal}", decision,
                reasons, keys, world.entries, world.exits, first_stopped,
            )

        confirm = getattr(policy, "confirm_key_posted", None)
        if confirm is not None:
            confirm(key)
        world.apply(key)
        current = world.durable_fingerprint()
        if current != fingerprint:
            fingerprint = current
            first_stopped = decision + 1
            progress_events += 1
            longest_stall = max(longest_stall, decision - last_progress - 1)
            last_progress = decision

    longest_stall = max(longest_stall, state.decisions - last_progress)
    # Workflow progress may pass a bounded drive when it stays live throughout
    # the drive. Repeated mutations and a bounded quiet window prevent a lone
    # final-decision twitch from passing.
    progress_stall_limit = max(3, state.decisions // 10)
    if progress_events >= 2 and longest_stall <= progress_stall_limit:
        return DriveResult(
            state.name, True, "durable progress within decision bound",
            state.decisions, reasons, keys, world.entries, world.exits, first_stopped,
        )

    if not world.release_modelled(final_reason):
        outcome = f"unmodelled release: {final_reason}"
    else:
        outcome = "decision bound exhausted without durable progress or named terminal"

    return DriveResult(
        state.name, False, outcome,
        state.decisions, reasons, keys, world.entries, world.exits, first_stopped,
    )
