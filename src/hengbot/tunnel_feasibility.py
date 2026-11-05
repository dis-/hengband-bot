"""Which walls the player can tunnel through at all, and the dug cell the dark hides.

Two facts of the game's tunnel command (src/action/tunnel-execution.cpp
``exe_tunnel``, src/cmd-action/cmd-tunnel.cpp ``do_cmd_tunnel``):

* A wall without CAN_DIG (granite, magma and quartz veins, glass, trees) is
  dug through only when ``skill_dig > power + randint0(40 * power)``; with
  ``skill_dig <= power`` it never is.  n1-b life-315 (2026-11-05, Lv7
  Magic-Eater, one shovel, digging 18 shown in town) tunnelled one granite wall
  (power 40) with ``T9`` 577 times over 550,000 game turns until its lantern
  ran dry.  The mining tunnel key (policy_fundraising ``_mining_tunnel_key``,
  which the treasure dig and the walk-out dig both post through) refuses such a
  wall, so the target is released instead of dug forever.  The check reads the
  board's ``digging_skill`` only while a digging tool is worn: the skill before
  the digger is wielded does not tell what the digger adds.
* A finished tunnel turns the wall into floor (``cave_alter_feat``), and
  floor does not REMEMBER: grid.cpp ``set_terrain_id_to_grid`` clears its
  CAVE_MARK, and ``note_spot`` marks it again only when the player sees it.
  With no light (n1-b life-321 wore ★火消しライター, radius 0) the dug
  cell leaves the board, while the policy's grid memory still held the wall:
  ``T`` was asked again on floor, refused with 「そこは掘れない。」 and no turn
  passing, twelve times until the loop detector stopped it (02:05 and 02:06).
  When the board reports the tunnel finished or refused, the remembered walls
  next to the player that the board no longer shows are forgotten.
"""

from __future__ import annotations

from hengbot.model import GridState, Position, Snapshot

# tunnel.power of every TUNNEL terrain without CAN_DIG
# (lib/edit/TerrainDefinitions.jsonc, by terrain id).
TUNNEL_POWER_BY_TERRAIN_ID = {
    50: 10, 51: 20, 52: 10, 53: 20, 54: 20, 55: 20,  # magma / quartz veins
    56: 40, 57: 40, 58: 40, 59: 40,  # granite
    96: 10,  # tree
    218: 40,  # glass wall
    223: 10, 224: 20, 225: 40, 226: 40,  # on shallow water
    236: 10, 237: 20, 238: 40, 239: 40,  # on deep water
    240: 30, 241: 30, 242: 30, 243: 30,  # quartz with treasure / hidden
}

# The board's message after a tunnel ends the wall or meets no wall.
TUNNEL_ENDED_MESSAGES = frozenset({
    "穴を掘り終えた。", "You have finished the tunnel.",  # tunnel-execution.cpp:91
    "そこは掘れない。", "You can't tunnel through that.",  # cmd-tunnel.cpp:58
})


def never_dug(snapshot: Snapshot, grid: GridState) -> bool:
    """The worn digger can never tunnel through ``grid`` (skill_dig <= power)."""
    skill = snapshot.player.digging_skill
    power = TUNNEL_POWER_BY_TERRAIN_ID.get(grid.terrain_id)
    return (
        skill is not None
        and power is not None
        and any(item.is_digging_tool for item in snapshot.equipment)
        and skill <= power
    )


def _tunnel_ended(messages) -> bool:
    return any(
        message.split(" <x", 1)[0] in TUNNEL_ENDED_MESSAGES for message in messages
    )


def forget_dug_walls(policy, snapshot: Snapshot) -> None:
    """Drop remembered walls next to the player that a finished tunnel removed.

    Called by the grid memory's owner (``_with_grid_memory``) before the merge.
    """
    if not snapshot.grids or not _tunnel_ended(snapshot.messages):
        return
    remembered = policy._remembered_grids
    here = snapshot.player.position
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            position = Position(here.y + dy, here.x + dx)
            grid = remembered.get(position)
            if (
                grid is not None
                and grid.tunnel
                and not grid.passable
                and position not in snapshot.grids
            ):
                del remembered[position]
                policy._remembered_grid_signatures.pop(position, None)
                policy._remembered_grid_sources.pop(position, None)
