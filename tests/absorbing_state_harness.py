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

    def terminal_ends_drive(self, reason: str, key: str) -> bool: ...

    def deliver_events(self, policy: object) -> None: ...

    def unmodelled_release(self, reason: str) -> bool: ...


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
    progress_events: int
    longest_stall: int

    def report(self) -> str:
        return (
            f"{self.state}: {'PASS' if self.passed else 'FAIL'}: {self.outcome}; "
            f"decisions={self.decisions}; reasons={dict(self.reasons)}; "
            f"keys={dict(self.keys)}; entries={self.entries}; exits={self.exits}; "
            f"progress_events={self.progress_events}; longest_stall={self.longest_stall}"
        )


def drive(state: AbsorbingState) -> DriveResult:
    policy, world = state.build()
    reasons: Counter[str] = Counter()
    keys: Counter[str] = Counter()
    fingerprint = world.durable_fingerprint()
    last_progress = 0
    progress_events = 0
    longest_stall = 0
    final_reason = "<no decision>"
    repeated_visible_terminal: tuple[str, int] | None = None

    for decision in range(1, state.decisions + 1):
        world.deliver_events(policy)
        key = policy.choose_key(world.snapshot(decision))
        reason = policy.last_reason
        final_reason = reason
        reasons[reason] += 1
        keys[key] += 1

        terminal = world.visible_terminal(reason)
        if terminal is not None:
            if world.terminal_ends_drive(reason, key):
                return DriveResult(
                    state.name, True, f"drive-ending terminal {terminal}", decision,
                    reasons, keys, world.entries, world.exits,
                    progress_events, longest_stall,
                )
            count = (
                repeated_visible_terminal[1] + 1
                if repeated_visible_terminal is not None
                and repeated_visible_terminal[0] == terminal
                else 1
            )
            repeated_visible_terminal = (terminal, count)
            if count > 3:
                return DriveResult(
                    state.name, False,
                    f"visible terminal repeated without ending drive: {terminal}",
                    decision, reasons, keys, world.entries, world.exits,
                    progress_events, longest_stall,
                )
        else:
            repeated_visible_terminal = None

        confirm = getattr(policy, "confirm_key_posted", None)
        if confirm is not None:
            confirm(key)
        world.apply(key)
        current = world.durable_fingerprint()
        if current != fingerprint:
            fingerprint = current
            progress_events += 1
            longest_stall = max(longest_stall, decision - last_progress - 1)
            last_progress = decision

    longest_stall = max(longest_stall, state.decisions - last_progress)
    # Part 4 is parked. Principle: a cycling drive revisits an equivalent
    # workflow state without making irreversible progress toward a terminal;
    # progress needs a semantic well-founded measure, not merely changing
    # fingerprints. This bounded mutation heuristic cannot detect arbitrary
    # periods or slowly drifting cycles whose incidental fields stay unique.
    progress_stall_limit = max(3, state.decisions // 10)
    if progress_events >= 2 and longest_stall <= progress_stall_limit:
        return DriveResult(
            state.name, True, "durable progress within decision bound",
            state.decisions, reasons, keys, world.entries, world.exits,
            progress_events, longest_stall,
        )

    if world.unmodelled_release(final_reason):
        outcome = f"unmodelled release: {final_reason}"
    else:
        outcome = "decision bound exhausted without durable progress or named terminal"

    return DriveResult(
        state.name, False, outcome,
        state.decisions, reasons, keys, world.entries, world.exits,
        progress_events, longest_stall,
    )
