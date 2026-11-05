"""Which of a plan's firing cells a shot at a breeder can really be taken from.

The approved formation shoots from a distance and never melees what does not move (QUEST_2 P7,
P8: 「近接せず」「被弾ゼロ」).  n1-b life-316 at [1,3] held for a sleeping rat at [3,1] on the
diagonal through a puddle at [2,2]: no shot could fly, the puddle touched the player, and the rung
that forbids a damaged WAIT (policy_combat._forbid_wait_while_damaged) read Teleport at HP 252/257.
"""

from __future__ import annotations

from hengbot import immobile_threat_memory
from hengbot.model import Position


def touching_cells(policy, snapshot, cells) -> set[Position]:
    """``cells`` beside a visible hostile that never moves."""
    fixed = [monster.position for monster in snapshot.visible_monsters
             if monster.hostile and immobile_threat_memory.never_moves(policy, monster)]
    return {cell for cell in cells if any(cell.distance_to(position) <= 1 for position in fixed)}


def _lane_is_clear(snapshot, cell: Position, target: Position) -> bool:
    """No visible monster stands on the straight ray from ``cell`` to ``target``."""
    occupied = {monster.position for monster in snapshot.visible_monsters}
    step_y = (target.y > cell.y) - (target.y < cell.y)
    step_x = (target.x > cell.x) - (target.x < cell.x)
    return not any(
        Position(cell.y + step_y * step, cell.x + step_x * step) in occupied
        for step in range(1, cell.distance_to(target))
    )


def usable(policy, snapshot, target: Position, vantages: set[Position]) -> set[Position]:
    """``vantages`` with a clear lane to ``target`` and out of reach of what does not move."""
    return {cell for cell in vantages - touching_cells(policy, snapshot, vantages)
            if _lane_is_clear(snapshot, cell, target)}
