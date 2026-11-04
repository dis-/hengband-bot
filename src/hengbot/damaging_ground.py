"""Leave damaging ground before standing still on it.

Owner 2026-11-04 「先に出る」: on damaging ground, a rest, search, wait, shot or
device use becomes a step to the nearest safe cell; a quaff does so only when a
safe cell is adjacent.  Reads, stairs and melee stay, and every other answer keeps
its order.

Recorded n1-a life-478 (Angband 19F, 2026-11-04 10:45): the player rested and drank
its two Healing potions on deep acid, then shot energy hounds from (8,166) with
floor beside it, HP 427 -> 292 -> 71 -> dead (hp-mp-processor.cpp deals the terrain's
damage every 10 game turns to whoever stands there).

An immune player takes no such damage, and a levitating one does not stand in it.
Deep water is not in the table: it only drowns an overloaded player.  Town decisions
stay with the town arbiter.
"""

from __future__ import annotations

from functools import wraps

from hengbot.policy_constants import SEARCH_KEY, WAIT_KEY

STEP_REASON = "hazard:step-off"
LEADING_ESCAPE = "\x1b"
REST, FIRE, THROW, AIM, USE, ZAP, ACTIVATE, ABSORBED_POWER, QUAFF = "RfvauzAmq"
STANDSTILLS = frozenset({REST, SEARCH_KEY, WAIT_KEY, FIRE, THROW, AIM, USE, ZAP,
                         ACTIVATE, ABSORBED_POWER})


def hurts_here(policy, snapshot) -> bool:
    """The player's own cell damages this player now."""
    player = snapshot.player
    grid = snapshot.grid_at(player.position)
    if grid is None or "levitation" in player.abilities:
        return False
    elements = getattr(policy, "_damaging_terrain_elements", {})
    return (grid.terrain_id in elements
            and elements[grid.terrain_id] not in player.immunities)


def _safe(policy, grid) -> bool:
    return (grid.passable and not grid.has_monster
            and not policy._is_avoidable_hazard_grid(grid))


def _step_off(policy, snapshot, *, adjacent_only: bool):
    """The least visited safe cell beside the player (a walk across goes on rather
    than back onto ground it must cross again), else the nearest safe cell's step."""
    beside = [cell for cell in policy._walkable_neighbors(
                  snapshot, snapshot.player.position, allow_damaging=False)
              if (grid := snapshot.grids.get(cell)) is not None and _safe(policy, grid)]
    if beside:
        return min(beside, key=lambda cell: policy._visit_counts[cell])
    if adjacent_only:
        return None
    return policy._nearest_goal_step(snapshot, lambda grid: _safe(policy, grid))


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
        key = decide(policy, snapshot)
        return step_off_key(policy, snapshot, key) or key
    return wrapped
