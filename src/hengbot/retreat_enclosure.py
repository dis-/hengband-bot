"""Retreat vetoes that enclose the player: Teleportation, then Recall.

A retreat's veto stays for the floor visit, so in a corridor it can hold every
step out of a pocket after its threats have died (n1-a life-476 迷宮15階, n1-b
life-307 迷宮18階: '5' at one cell until the loop guard).  Every veto is kept.
Owner 2026-11-04: 「一旦テレポートで離脱を試みる。同じフロアで二度同じ形で動けなく
なったら帰還。」  Phase Door is no substitute (owner 2026-11-02 「ショートテレポートは
テレポートの代替にならない」); with no Teleportation the Recall is read at once.

``teleport_key`` answers only from the idle fallback, after every survival rung has passed.

The same veto can wall a hunted target's ground off without holding the player's own steps:
n1-b life-317 (Angband 50F, RANDOM quest 40, 2026-11-05).  Five retreats from a half-giant
that later changed shape left a column of vetoes across a five-wide hall, and for 81,000
game turns the bot walked the 259 cells on its side while 83 detections showed the target
past the column.  A restart emptied the vetoes and it stood beside the target 486 game
turns later.  ``walled_off_key`` is that shape's read, for the hunt and the search of a
random quest (hunt_target, quest_target_search), where the idle fallback is never asked.
The first time, the floor's one Teleportation.

Walled off again after it, owner 2026-11-06: 「壁を掘る、罠を解除する、弱い敵なら倒すことを試みる。
ダメならテレポートを使用し、巻物が規定数以下になれば帰還。」, on a random quest floor too (the
Recall fails the quest, and the answer accepts that).  In order (``OPENERS``):

- dig: with a digging tool, the dig route (policy_fundraising ``_dig_route_first_step``,
  the walk-out dig's) through walls that are no veto to the walled-off ground, bounded by
  the owner's dig cap (tunnel_feasibility ``not_dug``, applied by the route);
- disarm: a walk to the ground whose only way crosses a trap, onto which ``_step_toward``
  posts its existing disarm (CHEST_DISARM_BUDGET tries a trap, as every walk);
- strike: a visible enemy standing on the ground or on the vetoes beside the player's side
  that the walk-out's blocker reading calls weak (``_weak_blocker``: no ranged attack, and
  ``_escape_blocker_is_easy_kill``'s melee projection kills it before its blows take the
  player's HP), bumped from the player's side;
- else Teleportation again, or Recall once the Teleportation scrolls are at or below the
  reserve: on a covered kill quest's floor the 11-01 reserve
  (random_quest_reserve.RANDOM_QUEST_TELEPORT_RESERVE, 5), elsewhere the ordinary low
  reserve the supply ledger returns on (TELEPORT_RETURN_THRESHOLD, 3).  With no Recall
  scroll the Teleportation is read; with neither, nothing answers.
"""

from __future__ import annotations

from collections import deque
from typing import NamedTuple

from hengbot import random_quest_reserve, walkout_dig
from hengbot.model import Position
from hengbot.policy_constants import CHEST_DISARM_BUDGET, TELEPORT_RETURN_THRESHOLD

_READ = "_enclosure_teleport_read"  # (floor, turn) of this floor's latest Teleportation here
TELEPORT_REASON = "stuck:enclosed-teleport"
DIG_REASON = "stuck:walled-off-dig"
DIG_WIELD_REASON = "stuck:walled-off-wield-digger"
DISARM_REASON = "stuck:walled-off-disarm"
STRIKE_REASON = "stuck:walled-off-strike"
RECALL_REASON = "stuck:walled-off-recall"


class WalledOff(NamedTuple):
    """The player's side of the vetoes, and the known ground they wall off."""
    reach: frozenset
    ground: frozenset


def encloses(policy, snapshot) -> bool:
    """Whether a retreat veto holds a step the player could otherwise take."""
    return any(
        cell in policy._engagement_owned_avoid_cells
        for cell in policy._walkable_neighbors(snapshot, snapshot.player.position)
    )


def _steps(policy, snapshot, position):
    """Walkable steps on safe ground that no veto holds."""
    return [
        neighbour
        for neighbour in policy._walkable_neighbors(snapshot, position, allow_damaging=False)
        if neighbour not in policy._engagement_avoid_cells
    ]


def walled_off(policy, snapshot) -> WalledOff | None:
    """The ground a retreat veto stands between the player and, else None."""
    owned = policy._engagement_owned_avoid_cells
    if not owned:
        return None
    start = snapshot.player.position
    reach, stack, gates = {start}, [start], set()
    while stack:
        for neighbour in policy._walkable_neighbors(snapshot, stack.pop(), allow_damaging=False):
            if neighbour in owned:
                gates.add(neighbour)
            elif neighbour not in policy._engagement_avoid_cells and neighbour not in reach:
                reach.add(neighbour)
                stack.append(neighbour)
    past, stack, ground = set(gates), list(gates), set()
    while stack:
        for neighbour in policy._walkable_neighbors(snapshot, stack.pop(), allow_damaging=False):
            if neighbour in owned:
                if neighbour not in past:
                    past.add(neighbour)
                    stack.append(neighbour)
            elif neighbour not in policy._engagement_avoid_cells and neighbour not in reach:
                ground.add(neighbour)
    stack = list(ground)
    while stack:
        for neighbour in _steps(policy, snapshot, stack.pop()):
            if neighbour not in reach and neighbour not in ground:
                ground.add(neighbour)
                stack.append(neighbour)
    return WalledOff(frozenset(reach), frozenset(ground)) if ground else None


def holds_ground(policy, snapshot) -> bool:
    """Whether a retreat veto stands between the player and known walkable ground."""
    return walled_off(policy, snapshot) is not None


def teleport_key(policy, snapshot) -> str | None:
    """The first enclosure of the floor's read, else None (Recall owns it)."""
    if not encloses(policy, snapshot) or _first_read_spent(policy, snapshot):
        return None
    return _read_teleport(policy, snapshot)


def walled_off_key(policy, snapshot) -> str | None:
    """While vetoes hold known ground from a hunt or search: the floor's first
    Teleportation, then the owner's openers, then Teleportation again or Recall."""
    if snapshot.player.recalling:
        return None
    walled = walled_off(policy, snapshot)
    if walled is None:
        return None
    if not _first_read_spent(policy, snapshot):
        key = _read_teleport(policy, snapshot)
        if key is not None:
            return key
    for opener in OPENERS:
        key = opener(policy, snapshot, walled)
        if key is not None:
            return key
    return _leave_key(policy, snapshot)


def _first_read_spent(policy, snapshot) -> bool:
    """This floor's Teleportation was read on an earlier turn.  A later decision on
    the read's own game turn is the same enclosure: the executor refused the key and
    the board was decided again."""
    read = getattr(policy, _READ, None)
    return read is not None and read[0] == snapshot.floor_key and snapshot.turn > read[1]


def _read_teleport(policy, snapshot) -> str | None:
    scroll = policy._escape_scroll(snapshot, teleport_only=True)
    key = policy._read_key(snapshot, scroll) if scroll is not None else None
    if key is not None:
        setattr(policy, _READ, (snapshot.floor_key, snapshot.turn))
        policy.last_reason = TELEPORT_REASON
    return key


def _dig_route(policy, snapshot, walled) -> Position | None:
    """The first step of the digger's route toward the ground (the route applies
    tunnel_feasibility.not_dug), else None."""
    player = snapshot.player
    if player.blind or player.confused or not policy._has_digging_tool(snapshot):
        return None
    return policy._dig_route_first_step(snapshot, set(walled.ground), walkout_dig.diggable)


def dig_has_route(policy, snapshot) -> bool:
    """Whether the dig toward walled-off ground still has work (keeps the digger wielded)."""
    if not _first_read_spent(policy, snapshot):
        return False
    walled = walled_off(policy, snapshot)
    return walled is not None and _dig_route(policy, snapshot, walled) is not None


def _dig_key(policy, snapshot, walled) -> str | None:
    first = _dig_route(policy, snapshot, walled)
    if first is None:
        return None
    return walkout_dig.dig_step_key(
        policy, snapshot, first, walkout_dig.diggable, DIG_REASON, DIG_WIELD_REASON)


def _first_step(policy, snapshot, goals, admit) -> Position | None:
    """The first step of the shortest walk to ``goals`` over cells ``admit`` accepts."""
    start = snapshot.player.position
    seen, queue = {start}, deque([(start, None)])
    while queue:
        position, first = queue.popleft()
        if position in goals and first is not None:
            return first
        for neighbour in policy._walkable_neighbors(snapshot, position, allow_damaging=True):
            if neighbour not in seen and admit(neighbour):
                seen.add(neighbour)
                queue.append((neighbour, neighbour if first is None else first))
    return None


def _disarm_key(policy, snapshot, walled) -> str | None:
    """A walk to the ground across a trap the walk's disarm still tries."""
    def admit(position) -> bool:
        if position in policy._engagement_avoid_cells:
            return False
        grid = snapshot.grids.get(position)
        if not policy._is_avoidable_hazard_grid(grid):
            return True
        return (grid.trap and not policy._is_damaging_grid(grid)
                and policy._floor_trap_disarm_attempts[(position.y, position.x)] < CHEST_DISARM_BUDGET)

    first = _first_step(policy, snapshot, walled.ground, admit)
    if first is None:
        return None
    policy.last_reason = DISARM_REASON
    return policy._step_toward(snapshot, first)


def _strike_key(policy, snapshot, walled) -> str | None:
    """Bump a weak enemy standing in the wall or on the ground, from the player's side."""
    if not policy._can_fight_in_dungeon(snapshot.floor_key[0]):
        return None
    hostiles = policy._physical_hostiles(snapshot)
    wall = walled.ground | policy._engagement_owned_avoid_cells
    here = snapshot.player.position
    targets = sorted(
        (monster for monster in hostiles
         if monster.position in wall and policy._weak_blocker(snapshot, hostiles, monster)),
        key=lambda monster: here.distance_to(monster.position))
    for monster in targets:
        stands = {cell for cell in walled.reach if cell.distance_to(monster.position) <= 1}
        if not stands:
            continue
        policy.last_reason = STRIKE_REASON
        if here in stands:
            return policy._direction_key(here, monster.position)
        first = _first_step(policy, snapshot, stands, lambda cell: cell in walled.reach)
        if first is not None:
            return policy._step_toward(snapshot, first)
    return None


OPENERS = (_dig_key, _disarm_key, _strike_key)


def _teleport_reserve(policy, snapshot) -> int:
    reserve = random_quest_reserve.floor_reserve(policy, snapshot)
    return TELEPORT_RETURN_THRESHOLD if reserve is None else reserve


def _leave_key(policy, snapshot) -> str | None:
    """Teleportation again, or Recall at or below the reserve."""
    if policy._count_teleport_scrolls(snapshot) <= _teleport_reserve(policy, snapshot):
        recall = policy._find_recall_scroll(snapshot)
        player = snapshot.player
        if (recall is not None and not player.blind and not player.confused
                and policy._can_read_scrolls(snapshot)):
            policy._note_return_start(None)
            policy._returning_to_town = True
            policy.last_reason = RECALL_REASON
            return policy._read_dungeon_recall_scroll_key(snapshot, recall)
    return _read_teleport(policy, snapshot)


def forget_floor_visit(policy) -> None:
    setattr(policy, _READ, None)
