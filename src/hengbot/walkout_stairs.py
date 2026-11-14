"""A declared walk-out the flee rung would turn away from: the step to its up-stair when it wins the race.

n1-c life-209 (zombie Magic-Eater Lv8, Yeek cave 1F, 2026-11-15 04:52) was walking out to the
up-stair (return:seek-upstairs, ``_returning_to_town``) past a growing giant white mouse swarm
and a jackal pack.  At turn 129065, two steps from the stair with HP 133/133 and the nearest
hostile five cells from it, the threat tiers decided the leave (``threat_tiers.leave_due``) and
the combat layer's flee rung took the decision: ``_flee_step`` maximises the distance to the
hostiles, so it walked '9', away from the stair, four times; the swarm closed in the open cave
and the character died there (no healing or escape item, the Word of Recall read at HP 85 too
late).

The flee rung already keeps a declared walk-out moving toward its exit when a weak blocker
stands in the way (``_blocking_escape_melee_key``, "A declared walk-out must keep moving toward
its known exit"), and the emergency and disengage rungs route to the nearest up-stair before
their flee step; only the open route was missing.  The step is taken only when the player
reaches the stair before any visible hostile can come beside the route: for each step ``i`` of
the route, each hostile that can approach has ``ceil(i * its energy / the player's)`` moves by
then (speed-table.cpp extract_energy; a monster that cannot approach has none), and it must stay
more than one cell beyond that reach of the route's ``i``-th cell.  Otherwise the flee step
answers as before.
"""
from __future__ import annotations

from math import ceil

from hengbot import goal_route
from hengbot.policy_constants import speed_energy
from hengbot.threat_projection import adjusted_speed


REASON = "flee:seek-upstairs"


def walkout_declared(policy, snapshot) -> bool:
    """The flee rung's own walk-out test (its ``_blocking_escape_melee_key`` branch)."""
    return (policy._fruitless_disengage_floor == snapshot.floor_key
            or policy._returning_to_town
            or policy._escape_state.owner in {"disengage", "return"})


def _intercepted(policy, snapshot, path, hostiles) -> bool:
    player_energy = speed_energy(snapshot.player.speed)
    for monster in hostiles:
        energy = speed_energy(adjusted_speed(monster))
        mobile = policy._monster_can_approach(snapshot, monster)
        for index, cell in enumerate(path, start=1):
            moves = ceil(index * energy / player_energy) if mobile else 0
            if monster.position.distance_to(cell) <= moves + 1:
                return True
    return False


def step(policy, snapshot):
    """(first step, up-stair) of the declared walk-out's route when it wins the race, else None."""
    if snapshot.in_town or not walkout_declared(policy, snapshot):
        return None
    if policy._quest_floor_exit_locked(snapshot):
        return None
    route = policy._nearest_goal_route(snapshot, policy._is_upstairs_target)
    if route is None:
        return None
    path = goal_route.committed_path(policy, policy._is_upstairs_target)
    if not path or path[0] != route.first_step or path[-1] != route.target:
        return None
    if _intercepted(policy, snapshot, path, policy._physical_hostiles(snapshot)):
        return None
    return route.first_step, route.target
