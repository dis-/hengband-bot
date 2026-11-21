"""Retreat vetoes that enclose the player or wall off known ground: one ladder out.

A retreat's veto stays for the floor visit, so in a corridor it can hold every
step out of a pocket after its threats have died (n1-a life-476 迷宮15階, n1-b
life-307 迷宮18階: '5' at one cell until the loop guard).  Every veto is kept.
Owner 2026-11-04: 「一旦テレポートで離脱を試みる。同じフロアで二度同じ形で動けなく
なったら帰還。」  Phase Door is no substitute (owner 2026-11-02 「ショートテレポートは
テレポートの代替にならない」).

``enclosed_key`` answers only from the idle fallback, after every survival rung has passed.

The same veto can wall a hunted target's ground off without holding the player's own steps:
n1-b life-317 (Angband 50F, RANDOM quest 40, 2026-11-05).  Five retreats from a half-giant
that later changed shape left a column of vetoes across a five-wide hall, and for 81,000
game turns the bot walked the 259 cells on its side while 83 detections showed the target
past the column.  A restart emptied the vetoes and it stood beside the target 486 game
turns later.  ``walled_off_key`` is that shape's read, for the hunt and the search of a
random quest (hunt_target, quest_target_search), where the idle fallback is never asked.

Both askers take one ladder (``_ladder``).  The walled-off hunt starts it with the floor's
first Teleportation and, walled off again after it, owner 2026-11-06: 「壁を掘る、罠を解除する、
弱い敵なら倒すことを試みる。ダメならテレポートを使用し、巻物が規定数以下になれば帰還。」, on a
random quest floor too (the Recall fails the quest, and the answer accepts that).  The enclosed
player starts at the openers (owner 2026-11-06: 「閉じ込められた時はどちらも、掘る（岩石溶解を含む）・
罠の解除・弱い敵を倒す を先に試し、駄目ならテレポート、巻物が規定数以下なら帰還。判定を1つにまとめる。」).
In order (``OPENERS``):

- dig: the dig route (policy_fundraising ``_dig_route_first_step``, the walk-out dig's)
  through walls that are no veto to the ground past the vetoes.  With a digging tool, its
  walls are bounded by the owner's dig cap (tunnel_feasibility ``not_dug``, applied by the
  route); else, or with no such route, Stone to Mud counts as digging (owner 2026-11-06
  「数える」): the wand or the absorbed power (sealed_pocket ``can_melt``, ``melt_at_key``,
  its uses counted against each wall) melts the route's next wall once beside it;
- disarm: a walk to the ground whose only way crosses a trap, onto which ``_step_toward``
  posts its existing disarm (CHEST_DISARM_BUDGET tries a trap, as every walk); the quest
  search asks it alone (``cross_toward_key``) toward ground only a known trap walls off;
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

from hengbot import return_start
from hengbot import engagement_avoid_seal, random_quest_reserve, sealed_pocket, walkout_dig
from hengbot.model import Position
from hengbot.policy_constants import CHEST_DISARM_BUDGET, TELEPORT_RETURN_THRESHOLD

_READ = "_enclosure_teleport_read"  # (floor, turn) of this floor's latest Teleportation here
TELEPORT_REASON = "stuck:enclosed-teleport"
DIG_REASON = "stuck:walled-off-dig"
DIG_WIELD_REASON = "stuck:walled-off-wield-digger"
# The secret-door search before the dig (``_reveal_key``): the corridor dead-end search's reason.
REVEAL_REASON = "search"
REVEAL_DEVICE_REASON = "stuck:walled-off-door-beam"
MELT_REASON = "stuck:walled-off-stone-to-mud"
DISARM_REASON = "stuck:walled-off-disarm"
STRIKE_REASON = "stuck:walled-off-strike"
RECALL_REASON = "stuck:walled-off-recall"


class WalledOff(NamedTuple):
    """The player's side of the vetoes, and the known ground they wall off.  ``kept_off``: the
    vetoes the sides were drawn by when they are not the retreats' own cells (the openers' walks
    keep off them too)."""
    reach: frozenset
    ground: frozenset
    kept_off: frozenset = frozenset()


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


def _sides(policy, snapshot, owned=None) -> WalledOff | None:
    """The player's side of the vetoes and the known ground past them (maybe none).

    ``owned``: the vetoes the sides are drawn by, the retreats' own cells unless given (the
    routes' engagement veto for ``route_veto_sealed_key``); a cell of them is kept off as the
    retreats' cells are."""
    kept_off = frozenset() if owned is None else owned
    owned = policy._engagement_owned_avoid_cells if owned is None else owned
    if not owned:
        return None
    avoid = policy._engagement_avoid_cells
    start = snapshot.player.position
    reach, stack, gates = {start}, [start], set()
    while stack:
        for neighbour in policy._walkable_neighbors(snapshot, stack.pop(), allow_damaging=False):
            if neighbour in owned:
                gates.add(neighbour)
            elif neighbour not in avoid and neighbour not in reach:
                reach.add(neighbour)
                stack.append(neighbour)
    past, stack, ground = set(gates), list(gates), set()
    while stack:
        for neighbour in policy._walkable_neighbors(snapshot, stack.pop(), allow_damaging=False):
            if neighbour in owned:
                if neighbour not in past:
                    past.add(neighbour)
                    stack.append(neighbour)
            elif neighbour not in avoid and neighbour not in reach:
                ground.add(neighbour)
    stack = list(ground)
    while stack:
        for neighbour in _steps(policy, snapshot, stack.pop()):
            if neighbour not in reach and neighbour not in ground and neighbour not in kept_off:
                ground.add(neighbour)
                stack.append(neighbour)
    return WalledOff(frozenset(reach), frozenset(ground), kept_off)


def walled_off(policy, snapshot) -> WalledOff | None:
    """The ground a retreat veto stands between the player and, else None."""
    sides = _sides(policy, snapshot)
    return sides if sides is not None and sides.ground else None


def _traced(policy, snapshot, asker: str, walled, answer):
    """``answer(walled)`` (None while ``walled`` is None), with the asker that took the ladder or
    an opener noted for the decision record (``trace``): which of the askers drew the sides, how
    large they were, and the vetoes they were drawn by, so that a stop shows why the ladder dug.
    n1-b life-413 (Angband 12F, 2026-11-21 19:02 and 20:11) dug from a corridor whose exits were
    open, and neither capture told the cut-off floor's opener from the vetoes' ladder."""
    if walled is None:
        return None
    key = answer(walled)
    if key is not None:
        policy._enclosure_trace = {
            "turn": snapshot.turn, "asker": asker, "reason": policy.last_reason,
            "reach": len(walled.reach), "ground": len(walled.ground),
            "ground_nearest": _nearest(snapshot, walled.ground),
            "kept_off": len(walled.kept_off),
        }
    return key


def _nearest(snapshot, cells, limit: int = 8) -> list:
    here = snapshot.player.position
    return [[cell.y, cell.x] for cell in sorted(
        cells, key=lambda cell: (max(abs(cell.y - here.y), abs(cell.x - here.x)), cell.y, cell.x))[:limit]]


def trace(policy) -> dict | None:
    """The last ladder or opener answer (``_traced``), for the decision record."""
    return getattr(policy, "_enclosure_trace", None)


def holds_ground(policy, snapshot) -> bool:
    """Whether a retreat veto stands between the player and known walkable ground."""
    return walled_off(policy, snapshot) is not None


def enclosed_key(policy, snapshot) -> str | None:
    """While a veto holds the player's own steps (the idle fallback): ``_ladder`` from
    the openers (owner 2026-11-06: 「閉じ込められた時はどちらも、掘る（岩石溶解を含む）・罠の解除・
    弱い敵を倒す を先に試し、駄目ならテレポート、巻物が規定数以下なら帰還。」)."""
    if not encloses(policy, snapshot):
        return None
    return _traced(policy, snapshot, "enclosed", _sides(policy, snapshot),
                   lambda walled: _ladder(policy, snapshot, walled, teleport_first=False))


def sealed_in_key(policy, snapshot) -> str | None:
    """The idle fallback before its wander: while the vetoes wall the player's side off
    from known ground, ``_ladder`` from the openers, as for the enclosed player.  The
    wander only walked the sealed pocket: n1-c life-153 (Labyrinth 13F, 2026-11-06 20:50)
    stood between (2,35) and (2,36), one cell past the vetoes, until the loop guard."""
    walled = walled_off(policy, snapshot)
    return _traced(policy, snapshot, "sealed-in", walled,
                   lambda walled: _ladder(policy, snapshot, walled, teleport_first=False))


ROUTE_VETO_DESTRUCTION_SUFFIX = ":route-veto-seal"  # the reason suffix of the sealers' *Destruction*


def route_veto_sealed_key(policy, snapshot) -> str | None:
    """Where the explore found no way on and the routes' engagement veto (a sleeper's reach
    among it) is what holds every way on from the player (engagement_avoid_seal
    ``route_veto_encloses``).  Owner 2026-11-17 (the n1-c life-216 question 「眠った強敵を避ける
    マスで出口がすべてふさがれた時はどうしますか？」, answer 「半径13以内なら *破壊*、無理なら溶かして
    抜ける」), in order:

    - *Destruction* leaving the sealing monsters (``sealers``) alone -- destruction_use ``key``
      with them as ``leaving``: its gates (clear-headed, a floor the game destroys, no damaged
      quest target or guardian in its worst radius, a reliable means with a charge, the most
      dangerous of them within GUARANTEED_RADIUS); no other monster is asked about;
    - the openers toward the known ground past the veto (owner 2026-11-06: the dig, Stone to Mud
      among it; the disarm walk; the weak blocker), the sides drawn by that veto;
    - the floor's stuck escape (policy ``_stuck_escape_key``: 50F+ deep_teleport ``stuck_key``,
      owner 2026-11-15 「岩石溶解で掘る・だめなら帰還」; shallower the Recall).

    Before, the secret-wall search ran the stuck count first and the wander walked the pocket:
    n1-c life-216 (Angband 62F, 2026-11-17 04:19) until the livelock guard read Recall at full HP
    beside a sleeping 百足龍虫 whose reach held both doors of the room.  None while recalling, or
    where the stuck escape may not leave (``_stuck_escape_permitted``)."""
    if snapshot.player.recalling or not engagement_avoid_seal.route_veto_encloses(policy, snapshot):
        return None
    if not policy._stuck_escape_permitted(snapshot, policy._is_forgetting_maze(snapshot),
                                          policy._is_completed_forgetting_maze(snapshot)):
        return None
    walled = _sides(policy, snapshot, frozenset(policy._engagement_route_veto(snapshot)))
    if walled is not None:
        sealing = sealers(policy, snapshot, walled)
        if sealing:
            from hengbot import destruction_use  # import cycle

            # No blow waits on it: the remembered floor items out of its circle first
            # (destruction_loot, owner 2026-11-17 「価値の高い品は先に拾ってから撃つ」).
            answer = destruction_use.loot_then_use(policy, snapshot, sealing,
                                                   suffix=ROUTE_VETO_DESTRUCTION_SUFFIX)
            if answer.key is not None:
                return answer.key
        key = _traced(policy, snapshot, "route-veto-sealed", walled, lambda walled: next(
            (key for opener in OPENERS if (key := opener(policy, snapshot, walled)) is not None),
            None))
        if key is not None:
            return key
    return policy._stuck_escape_key(snapshot)


def sealers(policy, snapshot, walled) -> list:
    """The monsters whose danger areas (policy ``_engagement_danger_areas``) hold a cell the
    player's side steps onto: the ones that seal it in."""
    gates = {
        neighbour
        for cell in walled.reach
        for neighbour in policy._walkable_neighbors(snapshot, cell, allow_damaging=False)
        if neighbour in walled.kept_off
    }
    areas = policy._engagement_danger_areas(snapshot) or ()
    return [monster for monster, area in areas if area & gates]


def walled_off_key(policy, snapshot) -> str | None:
    """While vetoes hold known ground from a hunt or search: ``_ladder`` from the floor's
    first Teleportation (owner 2026-11-04; the openers once walled off again, 2026-11-06)."""
    walled = walled_off(policy, snapshot)
    return _traced(policy, snapshot, "walled-off", walled,
                   lambda walled: _ladder(policy, snapshot, walled, teleport_first=True))


def open_toward_key(policy, snapshot, reach, ground) -> str | None:
    """The openers' dig (the digger's route, else Stone to Mud) toward known ``ground`` the walk
    from ``reach`` does not reach, for an asker with no veto of its own: the quest search's cut-off
    floor (owner 2026-11-08 21:5x 「掘るか岩石溶解で通す」, quest_target_search)."""
    if snapshot.player.recalling:
        return None
    return _traced(policy, snapshot, "cut-off", WalledOff(frozenset(reach), frozenset(ground)),
                   lambda walled: _dig_key(policy, snapshot, walled))


def ring_ladder_key(policy, snapshot, walled: WalledOff) -> str | None:
    """A never-moving monster's ring that blocks the way in a maze and cannot be shot
    away (immobile_ranged_kill ``blocking_key``, owner 2026-11-06 「倒せない時だけ 11-04 の
    決まりに進む」): ``_ladder`` from the openers, as for the enclosed player."""
    return _traced(policy, snapshot, "immobile-ring", walled,
                   lambda walled: _ladder(policy, snapshot, walled, teleport_first=False))


def _ladder(policy, snapshot, walled, *, teleport_first: bool) -> str | None:
    """With ``teleport_first``, the floor's first Teleportation; then the owner's
    openers, then Teleportation (again) or Recall at or below the reserve."""
    if snapshot.player.recalling:
        return None
    if teleport_first and not _first_read_spent(policy, snapshot):
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
    # The 50F+ rule (deep_teleport): no monster prompts this teleport, so off the 即死 board it
    # is not read; the openers and the leave answer (``_leave_key``).
    from hengbot import deep_teleport

    if deep_teleport.movement_refused(policy, snapshot):
        return None
    scroll = policy._escape_scroll(snapshot, teleport_only=True)
    # The 50F+ rule's substitute (deep_teleport) keeps its own reason; no teleport is read.
    if (instead := deep_teleport.scroll_substitute(policy, snapshot, scroll)) is not None:
        return instead
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


def _reveal_key(policy, snapshot, wall: Position) -> str | None:
    """Before any digging, the secret door the wall may be.

    Owner 2026-11-08 (verbatim) 「閉じた区画では感知手段を使う・無ければ扉になりうる壁沿いも探す
    （諦めない）」 and 2026-11-21 「どうみても隠し扉なのに罠破壊を試みない理由は？隠し扉って分からん？」
    (n1-b life-413, Angband 12F: the dig's first wall was the dead end of a corridor beside a
    room; the bot wielded the digger at once).  A secret door is a closed door under a granite
    mimic (Grid::is_hidden_door): the absorbed Detect Doors discloses it (detect_doors,
    me_powers SECRET_SEARCH, its own spacing), and a search ('s', do_cmd_search ->
    player-move.cpp search) finds a hidden door beside the player with the search skill's chance
    a turn.  The wall the dig would open next, beside the player, is searched SEARCH_LIMIT rounds
    (policy ``_undersearched_walls``) before the digger is wielded or Stone to Mud is spent.
    A MAZE dungeon's floor (cave-generator.cpp switch_making_floor -> build_maze_vault) is walls
    and floor only, so there no wall is a door."""
    from hengbot import immobile_ranged_kill, me_powers
    from hengbot.policy_constants import SEARCH_KEY

    if immobile_ranged_kill._in_maze(policy, snapshot):
        return None   # build_maze_vault lays walls and floor only: a maze floor has no door
    power = me_powers.power_key(policy, snapshot, me_powers.SECRET_SEARCH)
    if power is not None:
        return power
    here = snapshot.player.position
    grid = snapshot.grids.get(wall)
    if grid is None or grid.passable or max(abs(wall.y - here.y), abs(wall.x - here.x)) != 1:
        return None
    beam = _door_beam_key(policy, snapshot, wall)
    if beam is not None:
        return beam
    if (wall.y, wall.x) not in policy._undersearched_walls(here):
        return None
    policy._record_wall_search(here)
    policy.last_reason = REVEAL_REASON
    return SEARCH_KEY



def _door_beam_key(policy, snapshot, wall: Position) -> str | None:
    """A trap beam at ``wall``, once: KILL_TRAP discloses a hidden door on its line and KILL_DOOR
    destroys it (effect/effect-feature.cpp; a hidden door's own terrain is the door under the
    mimic).  The absorbed Disarming or Trap/Door Destruction (me_powers ``TRAP``, once a target),
    then a carried rod or wand of either (sealed_loot ``TRAP_DEVICES``, Disarming first), one use
    a wall a floor visit."""
    from hengbot import me_powers, sealed_loot
    from hengbot.item_reservation import reserved_item_command
    from hengbot.model import TVAL_ROD

    power = me_powers.power_key(policy, snapshot, me_powers.TRAP, wall)
    if power is not None:
        return power
    uses = sealed_loot._device_uses(policy, snapshot)
    if uses.get((wall.y, wall.x), 0):
        return None
    device = sealed_loot._trap_device(policy, snapshot, wall)
    direction = me_powers.beam_direction(policy, snapshot, snapshot.player.position, wall)
    if device is None or direction is None:
        return None
    kind = "rod" if device.tval == TVAL_ROD else "wand"
    used = reserved_item_command(policy, snapshot, kind, device, suffix=direction)
    if used is None:
        return None
    uses[(wall.y, wall.x)] = 1
    policy.last_reason = REVEAL_DEVICE_REASON
    return used


def _dig_key(policy, snapshot, walled) -> str | None:
    """The secret door first (``_reveal_key``), then the digger's route, else the Stone to Mud
    route."""
    first = _dig_route(policy, snapshot, walled)
    if first is not None:
        reveal = _reveal_key(policy, snapshot, first)
        if reveal is not None:
            return reveal
        return walkout_dig.dig_step_key(
            policy, snapshot, first, walkout_dig.diggable, DIG_REASON, DIG_WIELD_REASON)
    player = snapshot.player
    if not (player.blind or player.confused) and sealed_pocket.can_melt(policy, snapshot):
        route = melt_route(policy, snapshot, walled.ground)
        if route is not None:
            reveal = _reveal_key(policy, snapshot, route[0])
            if reveal is not None:
                return reveal
    return _melt_key(policy, snapshot, walled)


def melt_toward_key(policy, snapshot, reach, ground, reason: str,
                    *, power_first: bool = False) -> str | None:
    """The Stone to Mud route (``_melt_key``) from ``reach`` toward known ``ground``, under
    ``reason``: a sealed pocket whose straight lines all end at permanent rock
    (sealed_pocket ``key``), the walls around sensed loot (sealed_loot)."""
    if snapshot.player.recalling:
        return None
    return _melt_key(policy, snapshot, WalledOff(frozenset(reach), frozenset(ground)), reason,
                     power_first=power_first)


def meltable(policy, snapshot, grid) -> bool:
    """A wall the Stone to Mud route may melt: diggable, and not worn out on this floor."""
    return walkout_dig.diggable(grid) and not sealed_pocket.worn_out(policy, snapshot, grid.position)


def melt_route(policy, snapshot, ground) -> tuple[Position, int] | None:
    """(first step, walls melted) of the Stone to Mud route toward ``ground``, else None."""
    return policy._dig_route(snapshot, set(ground), lambda grid: meltable(policy, snapshot, grid),
                             tunnelled=False)


def _melt_key(policy, snapshot, walled, reason: str = MELT_REASON,
              *, power_first: bool = False) -> str | None:
    """Melt the route's next wall when beside it, else walk toward it."""
    player = snapshot.player
    if player.blind or player.confused or not sealed_pocket.can_melt(policy, snapshot):
        return None
    route = melt_route(policy, snapshot, walled.ground)
    if route is None:
        return None
    first = route[0]
    grid = snapshot.grids.get(first)
    if grid is not None and meltable(policy, snapshot, grid):
        return sealed_pocket.melt_at_key(policy, snapshot, first, reason, power_first=power_first)
    policy.last_reason = reason
    return policy._step_toward(snapshot, first)


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


def crossable(policy, snapshot, position) -> bool:
    """A cell the disarm opener's walk enters: no hazard, or a trap on ground that does no damage
    whose disarm the walk still tries (CHEST_DISARM_BUDGET)."""
    grid = snapshot.grids.get(position)
    if not policy._is_avoidable_hazard_grid(grid):
        return True
    return (grid.trap and not policy._is_damaging_grid(grid)
            and policy._floor_trap_disarm_attempts[(position.y, position.x)] < CHEST_DISARM_BUDGET)


def cross_toward_key(policy, snapshot, ground, avoid=frozenset()) -> str | None:
    """The disarm opener's walk across a trap toward known ``ground`` that the asker's own
    walk, which keeps off traps, does not reach, keeping off ``avoid`` too: the quest search's
    ground past a known trap (quest_target_search, n1-a life-522)."""
    if snapshot.player.recalling:
        return None
    return _traced(policy, snapshot, "past-traps", WalledOff(frozenset(), frozenset(ground)),
                   lambda walled: _disarm_key(policy, snapshot, walled, avoid))


def _disarm_key(policy, snapshot, walled, avoid=frozenset()) -> str | None:
    """A walk to the ground across a trap the walk's disarm still tries."""
    def admit(position) -> bool:
        return (position not in policy._engagement_avoid_cells and position not in avoid
                and position not in walled.kept_off and crossable(policy, snapshot, position))

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


def teleport_reserve(policy, snapshot) -> int:
    reserve = random_quest_reserve.floor_reserve(policy, snapshot)
    return TELEPORT_RETURN_THRESHOLD if reserve is None else reserve


def _leave_key(policy, snapshot) -> str | None:
    """Teleportation again, or Recall at or below the reserve.  50F+ off the 即死 board, no
    teleport: deep_teleport ``stuck_key`` (Stone to Mud toward a goal, else Recall; owner
    2026-11-15 「岩石溶解で掘る・だめなら帰還」)."""
    from hengbot import deep_teleport

    if deep_teleport.movement_refused(policy, snapshot):
        return deep_teleport.stuck_key(policy, snapshot)
    if policy._count_teleport_scrolls(snapshot) <= teleport_reserve(policy, snapshot):
        recall = policy._find_recall_scroll(snapshot)
        player = snapshot.player
        if (recall is not None and not player.blind and not player.confused
                and policy._can_read_scrolls(snapshot)):
            return_start.start(policy)
            policy.last_reason = RECALL_REASON
            return policy._read_dungeon_recall_scroll_key(snapshot, recall)
    return _read_teleport(policy, snapshot)


def forget_floor_visit(policy) -> None:
    setattr(policy, _READ, None)
