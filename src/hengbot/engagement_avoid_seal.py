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

While a Word of Recall counts down in the dungeon nothing seals: the Recall is the way on
(``_way_on``, n1-b life-411).
"""

from __future__ import annotations

from collections import deque

from hengbot.model import Position


def _way_on(policy, snapshot, start: Position, closed: frozenset, *,
            retreat_vetoes: bool = True) -> bool:
    """Whether a walk from ``start`` avoiding the vetoes and ``closed`` reaches a remembered
    frontier or a stair the stuck walk would take (immobile_ranged_kill's way-on reading).
    Without ``retreat_vetoes`` the retreats' own vetoes are walked over.

    A Word of Recall counting down in the dungeon is the way on wherever the player stands: no
    veto seals it in (retreat_enclosure's ``sealed_in_key`` reads the same, None while
    recalling), so a cell an owner left stays refused even where it is a pocket's only exit.
    n1-b life-411 (Magic-Eater Lv50, Angband 99F, 2026-11-19 00:55): during the Recall wait the
    sensed T1 leave (threat_tiers ``sensed_t1_leave_key``, owner 2026-11-08) stepped from the
    item cell (15,17) into the dead end (14,16) away from アンバーの王『オベロン』 (awake, known by
    telepathy only, vision 100); its left cell was the pocket's only exit, so the record was not
    made (``seals``) or not read (left_cells ``_encloses``), and the wait's pickup (owner
    2026-11-18 「見える敵がいなければ拾う」, which left every other reader of a sensed monster as
    it was) walked straight back onto it: 15 leaves and 14 pickups until the loop detector."""
    if snapshot.player.recalling and not snapshot.in_town:
        return True
    stairs =policy._remembered_stair_goals(snapshot, not policy._descent_is_blocked(snapshot))
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


def route_veto_encloses(policy, snapshot) -> bool:
    """Whether the routes' engagement veto (policy ``_engagement_route_veto``: a sleeper's reach
    among it) is what leaves the player no way on: no remembered frontier or stair is reached
    avoiding every veto, and one is with that veto lifted (every other veto kept).

    n1-c life-216 (Angband 62F, 2026-11-17 04:19): Recall landed the player in a dark room five
    cells from a sleeping 百足龍虫 (race 1257) out of sight in the corridor below it.  Its reach
    (the cells nearer it than the player) held both of the room's doors, so the explore had no
    frontier; the secret-wall search and the wander walked the room's top row for 280 game turns
    until the livelock guard read Recall at full HP.  The retreats' own vetoes were empty, so
    neither enclosure read (``encloses`` here asked only under them, retreat_enclosure's sides
    are drawn by them) saw it."""
    route = frozenset(policy._engagement_route_veto(snapshot))
    if not route:
        return False
    here = snapshot.player.position
    closed = frozenset(policy._walk_veto(snapshot)) - {here}
    return (not _way_on(policy, snapshot, here, closed)
            and _way_on(policy, snapshot, here, closed - route))


def seals(policy, snapshot, cell: Position, step: Position) -> bool:
    """Whether vetoing ``cell`` leaves the player, stepping onto ``step``, no way on that
    the retreats' vetoes (this one with them) would otherwise leave open."""
    if cell in policy._engagement_avoid_cells:
        return False
    return (not _way_on(policy, snapshot, step, frozenset({cell}))
            and _way_on(policy, snapshot, step, frozenset(), retreat_vetoes=False))
