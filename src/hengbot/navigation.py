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
EXPIRED for the rest of the floor visit, for every mode at once. Legitimate
approaches keep improving their best distance (lateral detours merely plateau,
well inside the budget) so they never expire mid-route.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

# Decisions a committed target may go without improving its best achieved
# distance before it expires for the floor visit. The known-legitimate worst
# case is a static-map detour that held distance flat for ~12 turns (the town
# travel leash history); 48 leaves a 4x margin while still expiring the
# incident's doomed stair target hundreds of decisions before the old
# behaviour would have starved the character.
NAV_TARGET_STALL_LIMIT = 48


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
        self.improved_this_decision = False

    def begin_decision(self) -> None:
        self.improved_this_decision = False

    def observe(self, kind: str, target: Hashable, distance: int) -> bool:
        """Record the current distance to a committed target.

        Returns True when this decision improved the target's best distance
        (or committed to it for the first time). Crossing the stall budget
        expires the (kind, target) pair for the rest of the floor visit.
        """
        key = (kind, target)
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

    def reset(self) -> None:
        """Forget everything (called on every floor change)."""
        self._progress.clear()
        self._expired.clear()
        self.improved_this_decision = False
