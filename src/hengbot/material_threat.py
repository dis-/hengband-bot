"""The landing's material threat after an emergency escape: a summoner or a breeder that can
summon or multiply before the player's next action.

Owner 2026-11-14 (recall-churn-1114 question 1, verbatim 「当てはめる」): the 10-03 rule
(USER DECISION 2026-10-03 06:1x, 「届かず、というのが「次のターン召喚を受ける可能性がない」という
意味であれば1」, ``policy_combat._summoner_may_summon_next_turn``) applies to the Recall after an
emergency escape (``_post_emergency_return_trigger``, trigger ``emergency-material-threat``) as
well.  n1-c life-207 (ガラスの城 60F, 2026-11-14 03:54-04:31) read Recall ten times after a single
escape because a summoner was merely visible: behind glass walls (no PROJECTION,
projection-path-calculator.cpp:94) or beyond get_max_range() (death knight and ニカデーモン at
cdis 20 at 04:23:22, アルベリヒ and 水の鬼 at cdis 15 behind glass at 04:29:05).

A summoner counts when ``_summoner_may_summon_next_turn`` holds (its line of fire, range, moves
and counter-attack target).  A breeder counts when the game would let it multiply on its next
move (``may_multiply_next_turn``).
"""

from __future__ import annotations

from hengbot.model import Position
from hengbot.policy_constants import NEIGHBOR_OFFSETS
from hengbot.search_coverage import MAX_PLAYER_SIGHT

# decide_monster_multiplication (monster-processor.cpp:498-527): the monsters in the breeder's
# 3x3, itself included; at this many or more it does not multiply.
CROWDED = 4


def present(policy, snapshot, hostiles) -> bool:
    """Some hostile of ``hostiles`` can summon or multiply before the player's next action."""
    return any(acts_before_next_turn(policy, snapshot, monster) for monster in hostiles)


def acts_before_next_turn(policy, snapshot, monster) -> bool:
    if monster.can_summon and policy._summoner_may_summon_next_turn(snapshot, monster):
        return True
    return monster.can_multiply and may_multiply_next_turn(policy, snapshot, monster)


def may_multiply_next_turn(policy, snapshot, monster) -> bool:
    """Whether the game may let ``monster`` (MULTIPLY) multiply on its next move, read with the
    player's information only (the floor's breeder count, num_repro, is not shown: not read).

    - it moves at all only when processed: within its ``vision`` (aaf), or within
      MAX_PLAYER_SIGHT with its grid in the player's view (decide_process_continue,
      monster-processor.cpp:701-716); asleep is no bar, as for the summoner (it may wake on the
      player's turn, monster-status.cpp:116-170);
    - fewer than ``CROWDED`` monsters in its 3x3, itself included
      (decide_monster_multiplication, monster-processor.cpp:507-523);
    - the clone needs an empty grid beside it that it can enter (multiply_monster ->
      mon_scatter(..., 1), monster-generator.cpp:42-119): not the player's grid, no monster,
      and floor, an unknown grid, or any grid for PASS_WALL / KILL_WALL."""
    here = snapshot.player.position
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    distance = policy._monster_cast_distance(monster.position, here)
    grid = snapshot.grid_at(monster.position)
    vision = knowledge.vision if knowledge is not None else 0
    if distance > vision and not (
            distance <= MAX_PLAYER_SIGHT and grid is not None and grid.in_view):
        return False
    occupied = {other.position for other in snapshot.visible_monsters}
    cells = [Position(monster.position.y + dy, monster.position.x + dx)
             for dy, dx in NEIGHBOR_OFFSETS]
    if 1 + sum(cell in occupied for cell in cells) >= CROWDED:
        return False
    through_walls = knowledge is not None and bool({"PASS_WALL", "KILL_WALL"} & knowledge.flags)
    return any(cell != here and cell not in occupied and _enterable(snapshot, cell, through_walls)
               for cell in cells)


def _enterable(snapshot, cell, through_walls: bool) -> bool:
    grid = snapshot.grid_at(cell)
    return through_walls or grid is None or not grid.known or grid.passable
