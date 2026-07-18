"""Shared navigation progress accounting (the R1 exploration redesign).

Every navigation goal the policy commits to (a remembered downstairs, a
frontier sweep, ...) historically kept its own private notion of progress and
its own bespoke give-up counter. Goals that gave up privately could be
re-selected by another mode that knew nothing about the failure, which is how
the seek-downstairs -> approach-descent -> breakout:descent triad walked a
character to the edge of starvation (2026-07-17, Yeek Cave 6F): the remembered
stair target itself never expired, so the three modes handed the same doomed
goal to each other forever while every aggregate metric looked like progress.

The ledger replaces that with ONE rule: a (kind, target) pair whose best
achieved distance stops improving for ``stall_limit`` consecutive decisions is
EXPIRED from routing selection until the target is reached. Legitimate
approaches keep improving their best distance (lateral detours merely plateau,
well inside the budget) so they never expire mid-route.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Sequence

# Decisions a committed target may go without improving its best achieved
# distance before it expires for the floor visit. The known-legitimate worst
# case is a static-map detour that held distance flat for ~12 turns (the town
# travel leash history).  The target must expire before the CLI's 40-decision
# confined-cell loop guard, or that outer fail-safe stops the bot before the
# ledger can abandon a two-cell stair oscillation.  32 still leaves more than
# a 2x margin for the observed legitimate detour.
NAV_TARGET_STALL_LIMIT = 32


@dataclass
class _TargetProgress:
    best_distance: int
    stall: int = 0


class NavigationLedger:
    """Per-floor-visit progress ledger shared by every navigation mode."""

    def __init__(self, stall_limit: int = NAV_TARGET_STALL_LIMIT) -> None:
        self._stall_limit = stall_limit
        self._progress: dict[tuple[str, Hashable], _TargetProgress] = {}
        self._expired: set[tuple[str, Hashable]] = set()
        self._descent_target: Hashable | None = None
        self._descent_path: list[Hashable] = []
        self.improved_this_decision = False

    def begin_decision(self) -> None:
        self.improved_this_decision = False

    def observe(self, kind: str, target: Hashable, distance: int) -> bool:
        """Record the current distance to a committed target.

        Returns True when this decision improved the target's best distance
        (or committed to it for the first time). Crossing the stall budget
        expires the (kind, target) pair from routing selection. Reaching a
        descent target clears that routing expiry.
        """
        key = (kind, target)
        if kind == "descend" and distance == 0:
            self._expired.discard(key)
        entry = self._progress.get(key)
        if entry is None:
            self._progress[key] = _TargetProgress(distance)
            self.improved_this_decision = True
            return True
        if distance < entry.best_distance:
            entry.best_distance = distance
            entry.stall = 0
            self.improved_this_decision = True
            return True
        entry.stall += 1
        if entry.stall >= self._stall_limit:
            self._expired.add(key)
        return False

    def is_expired(self, kind: str, target: Hashable) -> bool:
        return (kind, target) in self._expired

    def expired_targets(self, kind: str) -> set[Hashable]:
        return {target for k, target in self._expired if k == kind}

    def expire(self, kind: str, target: Hashable) -> None:
        """Expire a target immediately from external rejection evidence."""
        self._expired.add((kind, target))
        if kind == "descend" and target == self._descent_target:
            self.clear_descent_route()

    @property
    def descent_target(self) -> Hashable | None:
        return self._descent_target

    @property
    def descent_path(self) -> tuple[Hashable, ...]:
        return tuple(self._descent_path)

    def commit_descent_route(
        self, target: Hashable, path: Sequence[Hashable]
    ) -> None:
        """Own the selected stair and the remaining step-by-step route to it."""
        self._descent_target = target
        self._descent_path = list(path)

    def replace_descent_path(self, path: Sequence[Hashable]) -> None:
        """Re-path to the committed stair after a block or interruption."""
        if self._descent_target is not None:
            self._descent_path = list(path)

    def advance_descent_route(self, position: Hashable) -> None:
        """Discard route steps already reached by the player."""
        while self._descent_path and self._descent_path[0] == position:
            self._descent_path.pop(0)

    def clear_descent_route(self) -> None:
        self._descent_target = None
        self._descent_path.clear()

    def reset(self) -> None:
        """Forget everything (called on every floor change)."""
        self._progress.clear()
        self._expired.clear()
        self.clear_descent_route()
        self.improved_this_decision = False
