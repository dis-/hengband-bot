"""Whether a retreat's veto would seal the player in a dead end.

``_avoid_engagement_key`` vetoes the cell it retreats from (``_claim_engagement_avoid_cells``)
so a committed route does not walk straight back.  In a one-wide corridor that cell can be
the only way out of the pocket the step enters: n1-c life-153 (Labyrinth 13F, a forgetting
maze, 2026-11-06 20:50) retreated two steps from a sleeping giant spider into a three-cell
dead end, the two vetoed cells were the pocket's only exit, the explore, descent and stair
routes refused them, and the idle fallback walked (2,35)<->(2,36) until the loop guard.  The
vetoes were in the checkpoint, so the restarted process stood in the same pocket.

A veto seals when, from the cell the retreat steps onto, a walk over the routes that avoids
every veto reaches no remembered frontier and no stair the stuck walk would take, while the
same walk over the retreats' vetoes would.  Such a claim is not made: the retreat itself is
still taken.  A pocket the retreat could not see the end of when it claimed (its far cell was
still a frontier) is sealed only afterwards; the idle fallback answers that one with the
enclosure ladder (retreat_enclosure ``sealed_in_key``).
"""

from __future__ import annotations

from collections import deque

from hengbot.model import Position


def _way_on(policy, snapshot, start: Position, closed: frozenset, *,
            retreat_vetoes: bool = True) -> bool:
    """Whether a walk from ``start`` avoiding the vetoes and ``closed`` reaches a remembered
    frontier or a stair the stuck walk would take (immobile_ranged_kill's way-on reading).
    Without ``retreat_vetoes`` the retreats' own vetoes are walked over."""
    stairs = policy._remembered_stair_goals(snapshot, not policy._descent_is_blocked(snapshot))
    avoid = policy._engagement_avoid_cells
    if not retreat_vetoes:
        avoid = avoid - policy._engagement_owned_avoid_cells
    seen = {start}
    queue = deque([start])
    while queue:
        position = queue.popleft()
        if position in stairs or policy._is_remembered_frontier(snapshot, position):
            return True
        for neighbor in policy._walkable_neighbors(snapshot, position):
            if neighbor not in seen and neighbor not in avoid and neighbor not in closed:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


def encloses(policy, snapshot) -> bool:
    """Whether the vetoes leave the player, where it stands, no way on: no remembered frontier
    and no stair the stuck walk would take is reached by a walk that avoids every veto -- the
    retreats' own cells and every walker's veto (policy ``_walk_veto``: a sleeper's reach,
    n1-b life-341)."""
    closed = frozenset(policy._walk_veto(snapshot)) - {snapshot.player.position}
    return not _way_on(policy, snapshot, snapshot.player.position, closed)


def seals(policy, snapshot, cell: Position, step: Position) -> bool:
    """Whether vetoing ``cell`` leaves the player, stepping onto ``step``, no way on that
    the retreats' vetoes (this one with them) would otherwise leave open."""
    if cell in policy._engagement_avoid_cells:
        return False
    return (not _way_on(policy, snapshot, step, frozenset({cell}))
            and _way_on(policy, snapshot, step, frozenset(), retreat_vetoes=False))
