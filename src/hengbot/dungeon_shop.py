"""Shop entrances on a dungeon floor: not entered (one owning predicate).

Owner 2026-11-04 「入らない」.  An underground city (src/room/rooms-city.cpp) and
the Black market vaults put real store entrances on dungeon floors, and walking
onto one opens its page (n1-c life-139, Angband 5F: the ammo re-entry alternated
8 rounds).  Town is untouched.

* ``entrance``: the walk does not step here: no route, frontier or flight.
* ``only_way``: a dead end whose only step is an entrance takes it as the last
  resort of the idle wander; ``page_open`` then leaves, and the walk goes on
  from the entrance cell.
* ``page_open`` / ``leave_key``: a page open anyway (teleport-in, an accidental
  step) is left at once, with no shop owner, sale, buy or re-entry.
"""
from __future__ import annotations

from typing import Any

from hengbot.model import Position
from hengbot.policy_constants import LEAVE_STORE_KEY, NEIGHBOR_OFFSETS

LEAVE_REASON = "shop:store-context-exit"


def _on_dungeon_floor(snapshot: Any) -> bool:
    return not snapshot.in_town and snapshot.dungeon_level > 0


def entrance(snapshot: Any, grid: Any) -> bool:
    """A store entrance on a dungeon floor."""
    return grid is not None and grid.is_store and _on_dungeon_floor(snapshot)


def only_way(policy: Any, snapshot: Any) -> Position | None:
    """An entrance beside a player with no other step, else None."""
    here = snapshot.player.position
    cells = (Position(here.y + dy, here.x + dx) for dy, dx in NEIGHBOR_OFFSETS)
    return next((cell for cell in cells
                 if entrance(snapshot, grid := snapshot.grids.get(cell))
                 and not grid.has_monster
                 and cell not in policy._engagement_avoid_cells), None)


def page_open(snapshot: Any) -> bool:
    """A store page on a dungeon floor."""
    return snapshot.store is not None and _on_dungeon_floor(snapshot)


def leave_key(policy: Any, snapshot: Any) -> str:
    """Leave the page; nothing of the visit survives for a re-entry."""
    policy._close_store_visit("dungeon-shop")
    policy._shop_observation = None
    policy._staged_shop_approach = None
    policy._pending_shop_approach = None
    policy.last_reason = LEAVE_REASON
    policy._offer_execution(
        LEAVE_STORE_KEY, producer="shop-buy", work_id="shop:dungeon-shop-leave",
        next_step="store.leave.send", arguments=(snapshot.store.store_type,),
        expected_effect="outside-store",
    )
    return LEAVE_STORE_KEY
