"""Walled in on every side: Stone to Mud is the way out.

Owner 2026-11-05: 「*破壊*後全方位壁なら岩石溶解で脱出すれば良い」 (n1-c life-140:
*Destruction* left two floor cells in rock on random quest 40, Angband 50F; the
Teleportation that used to answer landed beside a biter and Recall left the quest).
The condition is the walls, not how they came: no floor, class or depth is named.
How they came sets only when: owner the same day, asked whether to melt before the
secret-door search, 「*破壊* の後はすぐ溶かす」.  A pocket in the circle of the player's own
*Destruction* on this floor visit is melted at once (``after_destruction_key``); any other
seal keeps the search first.

Sealed (``sealed_region``): what the player can walk to shows no way on.  Every
neighbour of it is known, and none is a stair, or a door or rubble not given up.

Game (C:/hengband/src).  wall_to_mud (spell-kind/spells-beam.cpp:14) is a PROJECT_BEAM
of KILL_WALL through project_hook, which aims one grid away with PROJECT_THRU, so the
beam runs the straight line.  project_path ends a line at the first grid without
PROJECTION (target/projection-path-calculator.cpp project_stop), so one use melts one
wall and open floor before that wall does not stop the beam (effect/effect-feature.cpp:232:
a STONE terrain turns to floor).  Every terrain with TUNNEL and not PERMANENT is STONE
(lib/edit/TerrainDefinitions.jsonc); a PERMANENT one has no STONE and ends the line
unmelted.  A failed use takes the turn and keeps the charge.

The direction (``_aim``) is read off the map: the line with the fewest grids to walkable
known floor that leads on (a magic mapping's blank grids are floor, mapped_area); with
none on any line, the line with the fewest walls to ground not yet known, which is a
frontier once melted, the nearest to such floor first.  Melting opens the grid, the board
shows what is behind it and exploration takes over; still sealed, the next ask chooses
again.  A wall that stayed after me_powers.FAILURES_PER_PLACE uses is left (the failures
of a low skill, or a terrain the board does not show) and its line is not asked again.

A wall melted out of the player's view leaves the board (``forget_melted_wall``):
cave_alter_feat makes it floor, which has no REMEMBER, and only a grid in view is noted
again, so the game forgets the grid while the bot's grid memory still holds the wall.  The
melt message names the use that took it (effect-feature.cpp:237, shown for a marked grid
only), so the first remembered wall of the aimed line that the board no longer shows is
dropped from the memory before the merge, as tunnel_feasibility.forget_dug_walls drops a
dug wall.  Without it the next ask aimed at the same remembered wall while each beam
melted the next one along the line, five uses a line, and the player never walked: n1-b
life-370 (Angband 80F, 2026-11-12 00:50, loop-detected) melted 33 walls along six lines of
its *Destruction* pocket from two cells.
With no line left the asker's next rung answers (Teleportation, Recall, the visible
stop), as it does blind, confused, with no charge or with only permanent walls.

Askers: the ladder above the searches for a destroyed pocket (``after_destruction_key``),
``_navigation_livelock_key`` before it would leave or read away,
``_stuck_escape_key`` where a stuck count would leave the floor first, and
``_town_idle_key`` in place of the first aimless step (exploration, the secret-door
search and the known stairs have all answered by then).  The map comes first
(area_mapping.sealed_key): it may show the way.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# me_absorbed_substitutes is read through the module at call time: importing
# hengbot.arena first loads me_absorbed_substitutes -> me_powers -> hunt_target
# -> retreat_enclosure -> this module while me_absorbed_substitutes is still
# initializing, so a from-import of its names fails (circular import).
from hengbot import area_mapping, me_absorbed_substitutes, me_powers
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position, Snapshot, game_distance
from hengbot.policy_constants import MONSTER_SPELL_MAX_RANGE, NEIGHBOR_OFFSETS


REASON = "livelock:stone-to-mud"
TELEPORT_REASON = "stuck:destroyed-circle-teleport"
RECALL_REASON = "stuck:destroyed-circle-recall"
MEMORY = "_sealed_pocket_memory"
TELEPORTED = "_destroyed_circle_teleport"  # ((floor, circles), turn) of the last read
# effect-feature.cpp:238 「{}が溶けて泥になった！」 / "The {} turns into mud!"
MELTED_MESSAGES = ("が溶けて泥になった", "turns into mud")


@dataclass
class Memory:
    floor: tuple
    uses: Counter = field(default_factory=Counter)  # wall (y, x) -> uses aimed at it
    aimed: tuple | None = None  # (game turn, origin, (dy, dx)) of the last use


def _neighbours(position: Position):
    return (Position(position.y + dy, position.x + dx) for dy, dx in NEIGHBOR_OFFSETS)


def _on_board(snapshot: Snapshot, position: Position) -> bool:
    return 0 <= position.y < snapshot.height and 0 <= position.x < snapshot.width


def _known(snapshot: Snapshot, position: Position):
    grid = snapshot.grid_at(position)
    return grid if grid is not None and grid.known else None


def _stairs(grid) -> bool:
    return grid.has_up_stairs or grid.has_down_stairs or grid.has_entrance or grid.has_quest_exit


def _leads_on(policy, position: Position, grid) -> bool:
    """A neighbour that is no wall to the player: unknown ground (an unknown grid
    probed to the limit is a wall), or a door or rubble not given up."""
    key = (position.y, position.x)
    if grid is None:
        return key not in policy._blocked_unknown
    if grid.is_closed_door:
        return key not in policy._blocked_doors
    return grid.is_rubble and key not in policy._blocked_rubble


def sealed_region(policy, snapshot: Snapshot) -> set[Position] | None:
    """The cells the player can walk to, when none of them leads anywhere.

    A magic mapping's blank grid is walkable floor (area_mapping.blank_floor, mapped_area's
    game facts), so it is part of the region, not unknown ground that leads on: n1-b life-367
    (Mountain 50F, 2026-11-10 20:54) stood in a 28-cell pocket of its own *Destruction* whose
    grass the map leaves blank, read it as open, searched its walls 60 times and recalled."""
    mapped = area_mapping.blank_floor(policy, snapshot)
    start = snapshot.player.position
    region, stack = {start}, [start]
    while stack:
        here = stack.pop()
        grid = snapshot.grid_at(here)
        if grid is not None and _stairs(grid):
            return None
        if grid is None and (here.y, here.x) not in mapped:
            return None
        for neighbour in _neighbours(here):
            if neighbour in region or not _on_board(snapshot, neighbour):
                continue
            seen = _known(snapshot, neighbour)
            if (seen is not None and seen.passable) or (
                    seen is None and (neighbour.y, neighbour.x) in mapped):
                region.add(neighbour)
                stack.append(neighbour)
            elif _leads_on(policy, neighbour, seen):
                return None
    return region


def _melts(grid) -> bool:
    """A grid the beam turns to floor (the module docstring)."""
    return grid.tunnel and not grid.permanent


def _floor_leading_on(policy, snapshot: Snapshot, region: set, mapped: set) -> set[Position]:
    """Walkable known floor outside ``region`` that reaches unknown ground or stairs."""
    def walkable(position) -> bool:
        seen = _known(snapshot, position)
        return seen.passable if seen is not None else (position.y, position.x) in mapped

    starts = [grid.position for grid in snapshot.grids.values() if grid.known and grid.passable]
    starts += [Position(*cell) for cell in mapped]
    done, leading = set(region), set()
    for start in starts:
        if start in done:
            continue
        done.add(start)
        group, stack, leads = [start], [start], False
        while stack:
            here = stack.pop()
            seen = _known(snapshot, here)
            leads = leads or (seen is not None and _stairs(seen))
            for neighbour in _neighbours(here):
                if not _on_board(snapshot, neighbour):
                    continue
                if walkable(neighbour):
                    if neighbour not in done:
                        done.add(neighbour)
                        group.append(neighbour)
                        stack.append(neighbour)
                elif _known(snapshot, neighbour) is None:
                    leads = leads or (neighbour.y, neighbour.x) not in policy._blocked_unknown
        if leads:
            leading.update(group)
    return leading


@dataclass(frozen=True)
class _Line:
    """One direction from the player, out to where its digging would end."""
    wall: Position          # the first wall: what one use melts
    to_floor: int | None    # grids between the pocket and floor that leads on
    to_unknown: int | None  # walls before ground not yet known


def _line(snapshot: Snapshot, region: set, leading: set, mapped: set, step: tuple) -> _Line | None:
    """The line in direction ``step``, else None when digging it leads nowhere."""
    here = snapshot.player.position
    wall, to_unknown = None, None
    walls = between = 0
    while True:
        here = Position(here.y + step[0], here.x + step[1])
        if not _on_board(snapshot, here):
            break
        if wall is None and here in region:
            continue
        if here in leading:
            return None if wall is None else _Line(wall, between, to_unknown)
        seen = _known(snapshot, here)
        if seen is None and (here.y, here.x) in mapped:
            continue  # mapped floor that leads nowhere: the beam crosses it
        if seen is not None and not _melts(seen):
            if seen.passable:
                continue  # enclosed floor: the beam crosses it
            break  # permanent rock: the line of digging ends here
        if wall is None:
            if seen is None:
                return None  # a wall the board does not show: nothing to aim at
            wall = here
        between += 1
        if seen is None:
            to_unknown = walls if to_unknown is None else to_unknown
        elif to_unknown is None:
            walls += 1
    return None if wall is None or to_unknown is None else _Line(wall, None, to_unknown)


def _aim(policy, snapshot: Snapshot, region: set, memory: Memory, mapped: set,
         leading: set) -> tuple[str, Position] | None:
    """(direction key, first wall) of the chosen line, else None."""
    origin = snapshot.player.position
    lines = []
    for step in NEIGHBOR_OFFSETS:
        line = _line(snapshot, region, leading, mapped, step)
        if line is None or memory.uses[(line.wall.y, line.wall.x)] >= me_powers.FAILURES_PER_PLACE:
            continue
        direction = me_powers.beam_direction(policy, snapshot, origin, line.wall)
        if direction is not None:
            lines.append((line, direction))
    if not lines:
        return None

    def nearest_floor(wall: Position) -> int:
        return min((game_distance(wall, cell) for cell in leading), default=0)

    to_floor = [each for each in lines if each[0].to_floor is not None]
    line, direction = (
        min(to_floor, key=lambda each: each[0].to_floor) if to_floor
        else min(lines, key=lambda each: (each[0].to_unknown, nearest_floor(each[0].wall))))
    return direction, line.wall


def _memory(policy, snapshot: Snapshot) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = Memory(snapshot.floor_key)
        setattr(policy, MEMORY, memory)
    return memory


def _melt_key(policy, snapshot: Snapshot, direction: str,
              reason: str = REASON) -> tuple[str, str] | None:
    """(key, reason) of the wand, else of the absorbed power, as the quest breach aims them."""
    wand = policy._stone_to_mud_wand(snapshot)
    if wand is not None:
        used = reserved_item_command(policy, snapshot, "wand", wand, suffix=direction)
        if used is not None:
            return used, reason
    cast = me_absorbed_substitutes.carry_cast_key(policy, snapshot, "utility_tools", "wall_breach", direction)
    return None if cast is None else (cast, reason + me_absorbed_substitutes.CAST_SUFFIX)


def can_melt(policy, snapshot: Snapshot) -> bool:
    """A charged Stone to Mud wand, or the absorbed power with a charge."""
    return (policy._stone_to_mud_wand(snapshot) is not None
            or me_absorbed_substitutes.carry_cast_key(
                policy, snapshot, "utility_tools", "wall_breach") is not None)


def worn_out(policy, snapshot: Snapshot, wall: Position) -> bool:
    """``wall`` stayed after me_powers.FAILURES_PER_PLACE uses on this floor visit."""
    return _memory(policy, snapshot).uses[(wall.y, wall.x)] >= me_powers.FAILURES_PER_PLACE


def _spend_melt(policy, snapshot: Snapshot, direction: str, wall: Position, reason: str) -> str | None:
    """One use along ``direction`` at ``wall``, counted against it, else None."""
    melt = _melt_key(policy, snapshot, direction, reason)
    if melt is None:
        return None
    memory = _memory(policy, snapshot)
    memory.uses[(wall.y, wall.x)] += 1
    origin = snapshot.player.position
    dy, dx = wall.y - origin.y, wall.x - origin.x
    memory.aimed = (snapshot.turn, origin, ((dy > 0) - (dy < 0), (dx > 0) - (dx < 0)))
    # As the Teleportation rung: the next decisions rebuild their progress budget.
    policy._nav_exhausted = False
    policy._nav_stall_count = 0
    policy.last_reason = melt[1]
    return melt[0]


def forget_melted_wall(policy, snapshot: Snapshot) -> None:
    """Drop the remembered wall the last use melted out of view (the module docstring).

    Called by the grid memory's owner (``_with_grid_memory``) before the merge.  Along the
    aimed line from where the player stood, floor the board shows is crossed; the first
    grid the board no longer shows whose remembered terrain is a wall the beam melts is the
    melted one.  A wall the board still shows ends the line: the beam stopped there."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.aimed is None or not snapshot.grids:
        return
    turn, origin, step = memory.aimed
    if memory.floor != snapshot.floor_key:
        memory.aimed = None
        return
    if snapshot.turn <= turn:
        return  # the use's own board, or one the executor refused it on
    memory.aimed = None
    if not any(text in message for message in snapshot.messages for text in MELTED_MESSAGES):
        return
    remembered = policy._remembered_grids
    here = origin
    for _ in range(MONSTER_SPELL_MAX_RANGE):
        here = Position(here.y + step[0], here.x + step[1])
        if not _on_board(snapshot, here):
            return
        live = snapshot.grids.get(here)
        if live is not None and live.known:
            if live.passable:
                continue
            return
        grid = remembered.get(here)
        if grid is not None and grid.known and not grid.passable and _melts(grid):
            del remembered[here]
            policy._remembered_grid_signatures.pop(here, None)
            policy._remembered_grid_sources.pop(here, None)
            return


def melt_at_key(policy, snapshot: Snapshot, wall: Position, reason: str) -> str | None:
    """One use aimed at ``wall`` on a straight line from the player, else None.

    For an asker that chose the wall itself (retreat_enclosure's way to walled-off ground)."""
    player = snapshot.player
    if player.blind or player.confused or player.recalling:
        return None
    direction = me_powers.beam_direction(policy, snapshot, player.position, wall)
    return None if direction is None else _spend_melt(policy, snapshot, direction, wall, reason)


def after_destruction_key(policy, snapshot: Snapshot) -> str | None:
    """For a sealed region inside the player's *Destruction*, at once: ``key``, else the
    Teleportation of ``destroyed_leave_key``, else Recall as the last means; else None.

    Owner 2026-11-05 「*破壊*後全方位壁なら岩石溶解で脱出すれば良い」 (melt first, Teleportation
    when it cannot), and 2026-11-04 on what follows a *Destruction*: 「治して階の探索を続ける。
    破壊の回数だけでは帰還しない」.  The pocket's walls hide no secret door (area_mapping.wrecked),
    so it is not searched first."""
    if not area_mapping.destroyed_since_arrival(policy, snapshot):
        return None
    player = snapshot.player
    if snapshot.in_town or player.blind or player.confused or player.recalling:
        return None
    region = sealed_region(policy, snapshot)
    if region is None or not area_mapping.in_destroyed_circle(policy, snapshot, region):
        return None
    return (key(policy, snapshot) or destroyed_leave_key(policy, snapshot)
            or _last_recall_key(policy, snapshot))


def destroyed_leave_key(policy, snapshot: Snapshot) -> str | None:
    """After the player's own *Destruction* on this floor visit: one Teleportation per
    circle while the scrolls are above the leave reserve (retreat_enclosure's), else None.

    The stuck and livelock escapes ask it before their Recall: Recall only after it (owner
    2026-11-04 「治して階の探索を続ける」).  A second stuck on the same circle after the read is the
    floor's own, and keeps the old order."""
    from hengbot import retreat_enclosure

    if not area_mapping.destroyed_since_arrival(policy, snapshot):
        return None
    if snapshot.player.recalling or snapshot.floor_key[2] != 0 and not policy._on_random_quest_floor(snapshot):
        return None
    mark = (snapshot.floor_key, area_mapping.circle_count(policy, snapshot))
    read = getattr(policy, TELEPORTED, None)
    # A later decision on the read's own game turn is the same leave (the executor refused it).
    if read is not None and read[0] == mark and snapshot.turn > read[1]:
        return None
    if policy._count_teleport_scrolls(snapshot) <= retreat_enclosure.teleport_reserve(policy, snapshot):
        return None
    scroll = policy._escape_scroll(snapshot, teleport_only=True)
    if scroll is None:
        return None
    setattr(policy, TELEPORTED, (mark, snapshot.turn))
    policy._stuck_escape_streak = 0
    policy._nav_exhausted = False
    policy._nav_stall_count = 0
    policy.last_reason = TELEPORT_REASON
    return policy._read_key(snapshot, scroll)


def _last_recall_key(policy, snapshot: Snapshot) -> str | None:
    """Recall out of a sealed circle nothing else leaves (a random quest floor is not left)."""
    if snapshot.floor_key[2] != 0 or not policy._can_read_scrolls(snapshot):
        return None
    recall = policy._find_recall_scroll(snapshot)
    if recall is None:
        return None
    policy._stuck_escape_streak = 0
    policy._note_return_start(None)
    policy._returning_to_town = True
    policy.last_reason = RECALL_REASON
    return policy._read_dungeon_recall_scroll_key(snapshot, recall)


def key(policy, snapshot: Snapshot) -> str | None:
    """The next use on the way out of a sealed region, else None."""
    player = snapshot.player
    if snapshot.in_town or player.blind or player.confused or player.recalling:
        return None
    region = sealed_region(policy, snapshot)
    if region is None:
        return None
    mapping = area_mapping.sealed_key(policy, snapshot)
    if mapping is not None:
        return mapping
    memory = _memory(policy, snapshot)
    mapped = area_mapping.blank_floor(policy, snapshot)
    leading = _floor_leading_on(policy, snapshot, region, mapped)
    aim = _aim(policy, snapshot, region, memory, mapped, leading)
    if aim is None:
        # Every straight line ends at permanent rock first (the Mountain's peaks around
        # a *Destruction*: n1-b life-367, 50F, 2026-11-10): melt along the route that
        # melts fewest walls to the floor that leads on, walking its floor between
        # (retreat_enclosure's Stone to Mud route).
        if not leading:
            return None
        from hengbot import retreat_enclosure

        return retreat_enclosure.melt_toward_key(policy, snapshot, region, leading, REASON)
    direction, wall = aim
    return _spend_melt(policy, snapshot, direction, wall, REASON)
