"""The dug cell the dark hides.

A fact of the game's tunnel command (src/action/tunnel-execution.cpp
``exe_tunnel``, src/cmd-action/cmd-tunnel.cpp ``do_cmd_tunnel``):

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

from hengbot.model import Position, Snapshot

# The board's message after a tunnel ends the wall or meets no wall.
TUNNEL_ENDED_MESSAGES = frozenset({
    "穴を掘り終えた。", "You have finished the tunnel.",  # tunnel-execution.cpp:91
    "そこは掘れない。", "You can't tunnel through that.",  # cmd-tunnel.cpp:58
})


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
