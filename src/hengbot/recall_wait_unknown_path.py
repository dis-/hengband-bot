"""The 50F+ recall wait walks to an item over cells the map does not hold.

Owner 2026-11-23, asked whether the 50F+ recall wait, with no known way to a nearby item (the
absorbed area mapping remembers the walls and not the floor, so after a *Destruction* or in a
cave the way is often missing), walks to it over cells it has not seen; verbatim choice: 「見て
いないマスも通って向かう — 帰還の発動までに歩いて届く距離なら、地図に無いマスも床として通る前提で
品へ向かう。壁に当たったら別の道を探す。見える敵がいれば今までどおり拾いをやめる。」  This widens the
2026-11-17 「待ちの残りで届く所まで」 (recall_wait_reach, which measured the reach over the known
floor) for the 50F+ wait only.

Game (C:/hengband/src): map_area (spell-kind/spells-floor.cpp) marks the walls it shows
(``REMEMBER`` terrain) and not the floor; *Destruction* (destroy_area) forgets the circle it
reshapes.  A step into an unseen wall takes the turn, says 「…が行く手をはばんでいるようだ」 and marks
the wall (action/movement-execution.cpp), so the next board shows it; a step into the unseen
outer boundary (「それ以上先には進めない」) marks nothing.

n1-c life-221 (Magic-Eater, the Mountain 50F, 2026-11-23 18:43, turns 4695002-4695070): the
Recall read under deep-teleport:recall at (23,153), the wait stood there (``return:wait-recall``)
with an item 16 cells off at (25,168) and only the walls of the area mapping between; over the
unknown cells the walk is 15-16 steps within a reach of 51.  Not every such wait has a way: n1-b
life-416 (Angband 95F, 17:35, turns 4236440-4236690) stood at (10,72) inside the circle its
*Destruction* had made granite, the walls known all around, and is left waiting as before.

``key`` (asked by policy ``_recall_wait_collect_key`` when the ordinary walk, over the known
floor within the reach, answered nothing): on a floor of ``DEEP_FLOOR_DEPTH`` or deeper, with
every gate of that wait already passed (the calm test: no hostile in view, the HP not low, a
zero prediction) and the loot owner's block reason clear, the shortest walk within the same
reach (recall_wait_reach) to a loot candidate where a cell the map does not know (not shown,
not remembered, not found blocked) counts as floor; the walks' vetoes and the unseen attack's
area are kept as in ``_loot_step``.  The step taken into an unknown cell is remembered
(``MEMORY``); when the next board finds the player where it stood and the cell still unknown
(the outer boundary, which the game does not mark), the cell joins the floor's
``_blocked_unknown`` (the explore's record of unknown cells found to be walls).  A marked wall
needs nothing: it is known on the next board and the walk is planned again around it.
"""

from __future__ import annotations

from collections import deque

from hengbot import recall_wait_reach, walk_vetoes
from hengbot.model import Position
from hengbot.policy_constants import DEEP_FLOOR_DEPTH, NEIGHBOR_OFFSETS

REASON = "return:seek-loot-unknown"
# (floor_key, game turn, the cell stood on, the unknown cell stepped into) of the last step
# into a cell the map did not know, or None.
MEMORY = "_recall_wait_unknown_step"


def _unknown(policy, snapshot, key) -> bool:
    """A cell the map does not hold: not shown, not remembered, not found blocked, in bounds."""
    return (key not in policy._remembered_known_t and key not in policy._blocked_unknown
            and snapshot.in_bounds(Position(*key))
            and (snapshot.grids.get(Position(*key)) is None
                 or not snapshot.grids[Position(*key)].known))


def _note_bump(policy, snapshot) -> None:
    """The last unknown step left the player where it stood and the cell unknown: blocked."""
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        return
    setattr(policy, MEMORY, None)
    floor_key, turn, origin, cell = memory
    if (floor_key == tuple(snapshot.floor_key) and snapshot.turn > turn
            and snapshot.player.position == origin and _unknown(policy, snapshot, cell)):
        policy._blocked_unknown.add(cell)


def path(policy, snapshot, hostiles, max_path_distance, candidates=None, *,
         unknown=True) -> list[Position]:
    """[first step, ..., the item]: the shortest walk within ``max_path_distance`` (None: no
    bound) to a loot candidate (``candidates``: those alone; hunt_items' walk) with the unknown
    cells as floor (``unknown`` False: the known floor alone), or []."""
    if candidates is None:
        candidates = policy._loot_candidates(snapshot)
    if not candidates or (max_path_distance is not None and max_path_distance <= 0):
        return []
    veto = walk_vetoes.route_left(policy, snapshot)
    through = policy._loot_route_hostile_cells(hostiles)
    avoid = policy._engagement_avoid_cells
    start = snapshot.player.position
    parent = {start: None}
    queue = deque([(start, 0)])
    while queue:
        position, distance = queue.popleft()
        if position != start and position in candidates:
            route = []
            cell = position
            while cell != start:
                route.append(cell)
                cell = parent[cell]
            return list(reversed(route))
        if max_path_distance is not None and distance >= max_path_distance:
            continue
        neighbors = list(policy._walkable_neighbors(snapshot, position, through=through))
        for dy, dx in NEIGHBOR_OFFSETS if unknown else ():
            key = (position.y + dy, position.x + dx)
            if _unknown(policy, snapshot, key):
                neighbors.append(Position(*key))
        for neighbor in neighbors:
            if (neighbor in parent or neighbor in avoid or neighbor in veto
                    or policy._in_unseen_attack_area(snapshot, neighbor)):
                continue
            parent[neighbor] = position
            queue.append((neighbor, distance + 1))
    return []


def key(policy, snapshot, hostiles) -> str | None:
    """The step toward the nearest item over unknown cells in the 50F+ recall wait, else None."""
    _note_bump(policy, snapshot)
    if snapshot.in_town or snapshot.dungeon_level < DEEP_FLOOR_DEPTH:
        return None
    if policy._loot_block_reason(snapshot, hostiles) is not None:
        return None
    return walk(policy, snapshot, hostiles, recall_wait_reach.max_path_distance(policy, snapshot),
                REASON)


def walk(policy, snapshot, hostiles, max_path_distance, reason, *, candidates=None,
         unknown=True) -> str | None:
    """The first step of the walk ``path`` plans (its arguments) under ``reason``, its unknown
    cell remembered for the bump (``MEMORY``); None for no walk.  hunt_items' walk takes its
    steps here too."""
    _note_bump(policy, snapshot)
    route = path(policy, snapshot, hostiles, max_path_distance, candidates, unknown=unknown)
    if not route:
        return None
    step = route[0]
    target = route[-1]
    if _unknown(policy, snapshot, (step.y, step.x)):
        setattr(policy, MEMORY, (tuple(snapshot.floor_key), snapshot.turn,
                                 snapshot.player.position, (step.y, step.x)))
    policy._loot_target = target
    policy._loot_walked_target = target
    policy.last_reason = reason
    policy._declare_reach(target)
    return policy._step_toward(snapshot, step)
