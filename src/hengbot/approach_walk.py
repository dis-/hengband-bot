"""The walking fallback of a store approach (#47, 2026-10-31 鍵3).

``_shopping_approach_step`` may return the store's remembered landmark itself
when neither the visible floor nor the town map gives a first step; that goal
is meant for native town travel.  When travel is refused (the town pack
budget refuses it while loot lies on the town floor), turning that distant
goal into one direction key walks toward it blindly: n1-a life-447 walked into
the Alchemist's permanent wall from its entrance, the bump cost no game time,
no new board came and the arrival wait stopped the bot (no-key-exhausted).
A distant goal is walked one cell toward it, never into a cell observed to be
impassable (an unobserved cell remains the old probing step).
"""

from __future__ import annotations

from hengbot.model import Position


def walk_key(policy, snapshot, step) -> str | None:
    """The direction key toward ``step``, never into an observed wall."""
    here = snapshot.player.position
    if here.distance_to(step) <= 1:
        return policy._step_toward(snapshot, step)
    toward = Position(here.y + (step.y > here.y) - (step.y < here.y),
                      here.x + (step.x > here.x) - (step.x < here.x))
    grid = snapshot.grid_at(toward)
    if grid is not None and not grid.passable:
        return None
    return policy._step_toward(snapshot, toward)
