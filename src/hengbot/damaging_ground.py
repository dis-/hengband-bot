"""Leave damaging ground before standing still on it.

Owner 2026-11-04 「先に出る」: on damaging ground, a rest, search, wait, shot or
device use becomes a step to the nearest safe cell; a quaff does so only when a
safe cell is adjacent.  Reads, stairs and melee stay, and every other answer keeps
its order.

Recorded n1-a life-478 (Angband 19F, 2026-11-04 10:45): the player rested and drank
its two Healing potions on deep acid, then shot energy hounds from (8,166) with
floor beside it, HP 427 -> 292 -> 71 -> dead (hp-mp-processor.cpp deals the terrain's
damage every 10 game turns to whoever stands there).

A wall search is never chosen on such ground, and a cell of it is no secret-wall stop
(``hurts_at``): the step that replaced the search walked back off it, the walk out
stepped onto it again, and each replaced search was counted as made (n1-a life-492,
Orc cave 23F, 2026-11-06 23:55, HEAVY_ELECTRICAL_ZONE around a pocket).

A step off while crossing (owner 2026-11-09 「渡った先へ出る」) goes to the safe ground
across, not back to the ground the crossing left: n1-c life-174 (Orc cave 23F, 11-09
00:31 and 00:36) walked from a notch into a poison-puddle room, saw an orc crossbowman
only from the puddle, had each shot replaced by the step back to the notch, and walked
in again until the loop guard stopped it.  The ground left is the safe region of the
last safe cell the player stood on this floor (``_hazard_entry``); the far side is the
nearest safe cell outside it, reached over the hazard only.

A cell a monster stands on is no safe cell and no way through, whether the monster is in view
or only sensed (``detected_monsters``: telepathy shows it, the grid's own monster mark is for
monsters in view only).  n1-b life-362 (Orc cave 23F, 2026-11-10 09:32) stood in a cold-zone
corridor (COLD_ZONE, hp-mp-processor.cpp COLD_PUDDLE) whose only near safe cells were two open
doors, each held by a black ogre.  From (39,43) the ogre on the door (42,41) was in view and the
step off went east; from (38,44) the wall hid it, telepathy still showed it, the door looked free
and the step off went back: '1' and '9' until the loop guard stopped the bot.

A step off that cannot cross goes back to the ground the walk came from: no safe cell
outside it is reached over the hazard.  The crossing is then given up for the floor visit:
the hazard ground it stood on (every cell that hurts, connected to the player's) is claimed
as the engagement retreats claim the cells they leave (policy ``_claim_engagement_avoid_cells``),
and every walker keeps off it (``_walk_veto``).  n1-b life-367 (Orc cave 23F, 2026-11-10
20:11): the exploration stepped '1' from (45,61) onto a shallow acid puddle (terrain 232,
ACID_PUDDLE) toward a frontier past the door a black ogre held; on the puddle the ogre came
into view, each shot at it was a step back to (45,61), whose dry ground reached every safe cell
around the puddle, and the exploration walked in again, until the loop guard.  The way back is
walked over the hazard alone (``_far_side_step`` with nothing left behind), so the claim does
not stop it.

An immune or invulnerable player takes no such damage.  A levitating one takes none
from shallow ground but a fifth of deep ground's (hp-mp-processor.cpp
deal_damege_by_feat: DEEP terrain hurts whoever is over it, other damaging terrain only
whoever stands in it), and at least 1 point, since no rate short of immunity is below
12%.  Deep water is not in the table: it only drowns an overloaded player.  Town decisions
stay with the town arbiter.
"""

from __future__ import annotations

from collections import deque
from functools import wraps

from hengbot.policy_constants import SEARCH_KEY, WAIT_KEY

STEP_REASON = "hazard:step-off"
# The status bar's BAR_INVULN key, set exactly when is_invuln() holds
# (main-window-stat-poster.cpp), which hp-mp-processor.cpp exempts from every puddle.
INVULNERABILITY = "invulnerability"
LEADING_ESCAPE = "\x1b"
REST, FIRE, THROW, AIM, USE, ZAP, ACTIVATE, ABSORBED_POWER, QUAFF = "RfvauzAmq"
STANDSTILLS = frozenset({REST, SEARCH_KEY, WAIT_KEY, FIRE, THROW, AIM, USE, ZAP,
                         ACTIVATE, ABSORBED_POWER})


def hurts_here(policy, snapshot) -> bool:
    """The player's own cell damages this player now."""
    return hurts_at(policy, snapshot, snapshot.player.position)


def hurts_at(policy, snapshot, position) -> bool:
    """Standing on ``position`` would damage this player now.

    This is the player's question (invulnerability, levitation over shallow ground,
    the ground element's immunity), unlike policy ``_is_damaging_grid``, the map's
    question of which terrain can damage anyone, which the walkers and this module's
    safe cells (``_safe``) use: a step off lands on ground that would not hurt even
    without a protection.  Deep water, which only drowns an overloaded player, is in the
    map's set but not here (see ``_is_damaging_grid``)."""
    player = snapshot.player
    grid = snapshot.grid_at(position)
    elements = getattr(policy, "_damaging_terrain_elements", {})
    if grid is None or grid.terrain_id not in elements:
        return False
    if INVULNERABILITY in (player.status_bar or ()):
        return False
    if ("levitation" in player.abilities
            and grid.terrain_id not in getattr(policy, "_deep_damaging_terrain_ids", ())):
        return False
    return elements[grid.terrain_id] not in player.immunities


def _occupied(snapshot) -> frozenset:
    """The cells a monster is known to stand on: in view or sensed."""
    return frozenset(monster.position for monster in snapshot.detected_monsters)


def _held(grid, occupied) -> bool:
    return grid.has_monster or grid.position in occupied


def _safe(policy, grid, occupied=frozenset()) -> bool:
    return (grid.passable and not _held(grid, occupied)
            and not policy._is_avoidable_hazard_grid(grid))


def _entry(policy, snapshot):
    """The last safe cell the player stood on this floor, else None."""
    entry = policy.__dict__.get("_hazard_entry")
    if entry is None or entry[0] != snapshot.floor_key:
        return None
    return entry[1]


def _left_ground(policy, snapshot, entry, occupied) -> set:
    """The safe cells connected to ``entry`` without crossing a hazard."""
    region = {entry}
    queue = deque([entry])
    while queue:
        for cell in policy._walkable_neighbors(snapshot, queue.popleft(), allow_damaging=False):
            grid = snapshot.grids.get(cell)
            if cell not in region and grid is not None and _safe(policy, grid, occupied):
                region.add(cell)
                queue.append(cell)
    return region


def _far_side_step(policy, snapshot, left, occupied, *, adjacent_only: bool):
    """The first step to the nearest safe cell outside ``left``, walking only hazard
    cells on the way (never back through the ground the crossing left)."""
    start = snapshot.player.position
    parent = {start: None}
    queue = deque([start])
    while queue:
        position = queue.popleft()
        for cell in policy._walkable_neighbors(snapshot, position, allow_damaging=True):
            if cell in parent or cell in left:
                continue
            grid = snapshot.grids.get(cell)
            if grid is None or _held(grid, occupied):
                continue
            parent[cell] = position
            if _safe(policy, grid, occupied):
                while parent[cell] != start:
                    cell = parent[cell]
                return cell
            if not adjacent_only and hurts_at(policy, snapshot, cell):
                queue.append(cell)
    return None


def _step_off(policy, snapshot, *, adjacent_only: bool):
    """The safe ground across a crossing (owner 2026-11-09 「渡った先へ出る」), else the
    step back (``_back_step``), which gives the crossing up for the floor visit."""
    occupied = _occupied(snapshot)
    entry = _entry(policy, snapshot)
    if entry is not None:
        across = _far_side_step(policy, snapshot, _left_ground(policy, snapshot, entry, occupied),
                                occupied, adjacent_only=adjacent_only)
        if across is not None:
            return across
    step = _back_step(policy, snapshot, occupied, adjacent_only=adjacent_only)
    if step is not None and entry is not None:
        # No crossing: the walk is given up here for the floor visit.
        policy._claim_engagement_avoid_cells(_hazard_ground(policy, snapshot))
    return step


def _back_step(policy, snapshot, occupied, *, adjacent_only: bool):
    """The least visited safe cell beside the player, else the first step to the nearest safe
    cell over the hazard alone, else the nearest safe cell's step."""
    beside = [cell for cell in policy._walkable_neighbors(
                  snapshot, snapshot.player.position, allow_damaging=False)
              if (grid := snapshot.grids.get(cell)) is not None and _safe(policy, grid, occupied)]
    if beside:
        return min(beside, key=lambda cell: policy._visit_counts[cell])
    if adjacent_only:
        return None
    return (_far_side_step(policy, snapshot, frozenset(), occupied, adjacent_only=False)
            or policy._nearest_goal_step(snapshot, lambda grid: _safe(policy, grid, occupied)))


def _hazard_ground(policy, snapshot) -> set:
    """The cells that hurt, connected to the player's own cell."""
    start = snapshot.player.position
    region = {start}
    queue = deque([start])
    while queue:
        position = queue.popleft()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cell = type(position)(position.y + dy, position.x + dx)
                if cell not in region and hurts_at(policy, snapshot, cell):
                    region.add(cell)
                    queue.append(cell)
    return region


def _replaces(key: str | None) -> tuple[bool, bool]:
    """(whether ``key`` stands still in the owner's list, whether it is a quaff)."""
    command = (key or "").lstrip(LEADING_ESCAPE)[:1]
    return command in STANDSTILLS, command == QUAFF


def step_off_key(policy, snapshot, key: str | None) -> str | None:
    """The step that replaces ``key`` on damaging ground, else None."""
    standstill, quaff = _replaces(key)
    if not (standstill or quaff) or snapshot.in_town or not hurts_here(policy, snapshot):
        return None
    step = _step_off(policy, snapshot, adjacent_only=quaff)
    if step is None:
        return None
    policy.last_reason = STEP_REASON
    policy._declare_reach(step)
    return policy._step_toward(snapshot, step)


def leave_first(decide):
    """Answer a decision's standstill with the step off damaging ground."""
    @wraps(decide)
    def wrapped(policy, snapshot):
        if not snapshot.in_town and not hurts_here(policy, snapshot):
            policy._hazard_entry = (snapshot.floor_key, snapshot.player.position)
        key = decide(policy, snapshot)
        return step_off_key(policy, snapshot, key) or key
    return wrapped
