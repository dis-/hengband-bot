"""Walking out of a floor with a digger: dig toward the way up.

Owner 2026-11-02 (n1-b life-293, Yeek cave 1F, walking out to claim quest
14 searched walls for a secret door until the cell guard stopped it):
「1Fから歩いて出るときは概ね採掘中なので、困ったら壁を掘れば上り階段に辿り
着くと思うのだが壁を調べ続ける理由は？」 -> 「掘って進む」: with a digging
tool, dig toward a remembered up staircase; without one known, dig toward the
nearest unexplored area; only without a digging tool search the walls as
before.

The return owner (policy_town ``_return_to_town_key``) asks ``key`` where it
would otherwise search walls for a hidden up staircase (no walking route to
one).  The route itself is the one dig-route helper (policy_fundraising
``_dig_route_first_step``, shared with the dig-to-stairs breakout).
The digger is wielded and the combat weapon restored afterwards through the
dig-to-stairs breakout's own keys (``_wield_digging_tool_key`` with
``_breakout_dig_floor``, ``_breakout_restore_weapon_key``); the restore rung
asks ``has_route`` whether this dig still has work.  Repeated digging that
makes no progress ends under the existing navigation ledger
(``_nav_exhausted``, ``_navigation_livelock_key`` above the return owner).

Diggable terrain is the game's (src/action/tunnel-execution.cpp,
do_cmd_tunnel_aux): a grid without TUNNEL has nothing to tunnel (line 34),
PERMANENT rock refuses (71-76), CAN_DIG rubble and every other TUNNEL wall --
granite, magma and quartz veins -- is dug (77-112).
"""

from __future__ import annotations

from hengbot import survival_preemption
from hengbot.model import GridState, Position, Snapshot
from hengbot.policy_constants import (
    RETURN_DIG_FRONTIER_REASON as FRONTIER_REASON,
    RETURN_DIG_UPSTAIRS_REASON as UPSTAIRS_REASON,
)

WIELD_REASON = "return:wield-digging-tool"
# The ladder rung whose producer asks ``key`` (survival_preemption).
RETURN_RUNG = "_return_to_town_key#3"


def diggable(grid: GridState) -> bool:
    """Terrain ``do_cmd_tunnel`` removes: TUNNEL and not PERMANENT."""
    return grid.known and grid.tunnel and not grid.permanent


def _frontier(policy, snapshot: Snapshot) -> set[Position]:
    """The exploration's frontier plus diggable walls bordering unexplored ground.

    Floor cells use the explore owner's own test (``_is_frontier``, which
    drops frontiers it gave up on), walls the same unexplored-neighbour test
    (``_borders_unexplored``: not in the remembered ``_marked_t``).
    """
    return {
        grid.position for grid in snapshot.grids.values()
        if policy._is_frontier(snapshot, grid)
        or (diggable(grid) and policy._borders_unexplored(snapshot, grid.position))
    }


def _plan(policy, snapshot: Snapshot) -> tuple[Position, str] | None:
    """The first dig-route step and reason of a walk-out dig, else None.

    A remembered up staircase is dug to only when no walking route reaches
    it; without one, the route goes to the nearest unexplored area through
    floor and diggable cells, walking where the floor reaches.
    """
    player = snapshot.player
    if (
        snapshot.in_town
        or not policy._returning_to_town
        or player.blind
        or player.confused
        or policy._nav_exhausted
        or policy._is_forgetting_maze(snapshot)
        or not policy._has_digging_tool(snapshot)
    ):
        return None
    upstairs = {
        grid.position for grid in snapshot.grids.values()
        if policy._is_upstairs_target(grid)
    }
    if upstairs:
        first = policy._dig_route_first_step(snapshot, upstairs, diggable)
        reason = UPSTAIRS_REASON
    else:
        first = policy._dig_route_first_step(
            snapshot, _frontier(policy, snapshot), diggable, walking_wins=False)
        reason = FRONTIER_REASON
    return None if first is None else (first, reason)


def has_route(policy, snapshot: Snapshot) -> bool:
    """Whether the walk-out dig still has work (keeps the digger wielded)."""
    if survival_preemption.preempts(policy, RETURN_RUNG, snapshot):
        return False
    return _plan(policy, snapshot) is not None


def key(policy, snapshot: Snapshot) -> str | None:
    """Wield the digger before a tunnel step, else take the step, else None."""
    plan = _plan(policy, snapshot)
    if plan is None:
        return None
    first, reason = plan
    first_grid = snapshot.grids.get(first)
    if (
        first_grid is not None
        and diggable(first_grid)
        and policy._equipped_digging_tool(snapshot) is None
    ):
        wield = policy._wield_digging_tool_key(snapshot, WIELD_REASON)
        if wield is not None:
            policy._breakout_dig_floor = snapshot.floor_key
            return wield
    step = policy._dig_step_key(snapshot, first, diggable)
    if step is not None:
        policy.last_reason = reason
    return step
