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
    arrived: Callable[[object, Physics], str | None]


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

    for decision in range(1, state.decisions + 1):
        deliver = getattr(world, "deliver_events", None)
        if deliver is not None:
            deliver(policy)
        key = policy.choose_key(world.snapshot(decision))
        reason = policy.last_reason
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
        arrived = state.arrived(policy, world)
        if arrived is not None:
            return DriveResult(
                state.name, True, f"arrived at {arrived}", decision,
                reasons, keys, world.entries, world.exits, first_stopped,
            )

        current = world.durable_fingerprint()
        if current != fingerprint:
            fingerprint = current
            first_stopped = decision + 1

    # Progress is a pass only while it remains live at the bound.  A single
    # early mutation followed by hundreds of identical decisions is a freeze.
    if first_stopped > state.decisions:
        return DriveResult(
            state.name, True, "durable progress within decision bound",
            state.decisions, reasons, keys, world.entries, world.exits, first_stopped,
        )

    final_reason = reasons.most_common(1)[0][0] if reasons else "<no decision>"
    release_modelled = getattr(world, "release_modelled", None)
    if release_modelled is not None and not release_modelled(final_reason):
        outcome = f"unmodelled release: {final_reason}"
    else:
        outcome = "decision bound exhausted without durable progress or named terminal"

    return DriveResult(
        state.name, False, outcome,
        state.decisions, reasons, keys, world.entries, world.exits, first_stopped,
    )
