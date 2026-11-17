"""Loot the player detected on grids the map does not know: the loot memory keeps it too.

Owner 2026-11-13 (answer to 「感知だけで見えて既知のマスから行けない品」, verbatim): 「その品の方へ探索
を寄せる。」 (loot_frontier), and 「価値に関係なく溶かす」 for such loot walled in (sealed_loot).  Both
read the loot memory (policy ``_known_loot``), which the observation filled only from the board's
grids that carry an object count: a grid the map knows.  Object detection marks the objects, not
the floor under them (the game's ``found_items`` lists them; the grid runs leave the cell out or
unknown), so an item detected in an unmapped part of the floor was never loot at all: no walk,
no steering, no melt, and the floor was left with it.  n1-c life-216 (Castle 64F, 2026-11-16
23:00-23:05): an item detection at (18,125) showed nine items at (13,82)-(31,104) (a potion of
speed, a scroll of *Destruction*, an amulet and four rings among them) in an unmapped part of the
floor; the explore went elsewhere and the floor was left by its up stairs 25-46 cells from them.
Of the valuable-looking items life-216 left behind on 50F+ floors from 11-16 18:00 to 11-17 15:00,
521 of 621 lay on such grids.

``observe`` adds each found item's cell on a grid the map does not know (absent or not known)
whose classes are not junk (policy ``_floor_pile_is_junk``, as a known pile is judged), and drops
a remembered cell still unknown that the found items no longer list (the game forgot it, or the
item is gone).  A cell the map knows is the grid loop's, unchanged.  Town is left as it was.
"""

from __future__ import annotations

from types import SimpleNamespace

from hengbot.model import Position


def _unknown(snapshot, position: Position) -> bool:
    grid = snapshot.grids.get(position)
    return grid is None or not grid.known


def observe(policy, snapshot) -> None:
    """Keep the found items on unmapped grids in the loot memory (see the module)."""
    rows = getattr(snapshot, "found_items", None)
    if snapshot.in_town or rows is None:
        return
    found = {}
    for row in rows:
        position = Position(row[0], row[1])
        if row[2] > 0 and _unknown(snapshot, position):
            found[position] = tuple(row[3:])
    for position, tvals in found.items():
        pile = SimpleNamespace(position=position, object_tvals=tvals, object_count=len(tvals))
        if policy._floor_pile_is_junk(snapshot, pile):
            policy._known_loot.discard(position)
        else:
            policy._known_loot.add(position)
    for position in [position for position in policy._known_loot
                     if position not in found and _unknown(snapshot, position)]:
        policy._known_loot.discard(position)
        policy._deferred_loot.discard(position)
        policy._safety_deferred_loot.discard(position)
        policy._nav_ledger_deferred_loot.discard(position)
