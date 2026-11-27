"""The Ring of Speed hunt: a floor whose level feeling rules the ring out is done with.

Supervisor 2026-11-28 (under the owner's 2026-11-26 permission to change in-game choices from
measured numbers; the owner 「マジックイーターが進展しない」): n1-b life-419 (Magic-Eater CL50,
permanent speed +17) sat under the speed ceiling (angband_cap) for 14 hours hunting a second Ring
of Speed.  Of the 58 Angband 80F floors of its last 4.4 h (none held a ring), the final feeling was
8-10 on 32; they took 44,442 of the 62,232 decisions (71%), 35,863 of them (58% of all) after the
feeling was already known.

The game (C:/hengband/src, floor/floor-events.cpp ``get_dungeon_feeling``):

- Every object of the floor's list adds ``floor_rating_boost(delta)`` (line 159; the list holds the
  items monsters carry too, monster-floor/monster-object.cpp:156 ``held_m_idx``); only an item
  the player has carried and knows (TOUCHED, inventory-object.cpp:327) or has sensed is left out
  (line 161), and every term is >= 0 (``floor_rating_boost`` clamps ``delta`` to 0..1001 and
  returns ``d*d + 50*d``, line 115; no term of ``delta`` is negative).
- An uncursed Ring of Speed adds ``25 * base`` (base 10, line 210) and, only while its level
  (80, BaseitemDefinitions.jsonc id 136) is deeper than the floor, ``(80 - depth) * base``
  (line 223): never less than 250 at any depth, exactly 250 from 80F down.
- The feeling is the band of the summed rating (lines 230-262): 10 for rating <= boost(0),
  9 for <= boost(100), 8 for <= boost(200), 7 for <= boost(300) ... (``FEELING_CEILING_DELTA``).
  A ring alone puts the rating at boost(250) or more, so a feeling whose band ends below that
  (``no_ring_feelings``: 8, 9 and 10 at 80-90F) cannot be read while one lies on the floor or in
  a monster's pack.  Feeling 1 is the special one of an artifact outside preserve mode (line 186), 0 is not known yet
  (the floor change sets it, floor-changer.cpp:488; it is read after
  ``max(10, 150 - skill_fos) * (150 - depth) * TURNS_PER_TICK / 100`` game turns, line 280).
- Not covered: an item made at a monster's death (monster-floor/monster-death.cpp drop_near) is
  in no list before it; the feeling says nothing of the drops of the fights to come.

The rule (``finished``): on a hunt floor (angband_cap ``ring_hunt_floor``: Angband, 80F down to
the speed ceiling, held there because the permanent +25 row is unmet), once the feeling the
player knows (the board's ``floor.feeling``) has been in the no-ring band on this floor visit,
the floor is done with for the hunt.  The memory (``MEMORY``) keeps it for the visit: the game
reads the feeling again every delay and a monster coming later may raise the rating (n1-b
2026-11-28 04:01, 80F: 9 -> 10 -> 7), which brings no ring.  What it changes:

- the loot owner fetches no ordinary loot there (``loot_filter``): only a pile holding a ring
  (an unidentified ring may be one the feeling did not count, a carried-and-dropped one) and the
  pile on the cell stood on (one action, no walk; as owner 2026-11-23's climb pickup);
- the floor counts as explored (explored_floor ``explored``; ``leave_key`` asks its way out in the
  idle layer before the searches and the explore), so on the dead-end ceiling floor
  the explored floor's way out answers at once: deep_stairs (the up stair, a new level of the
  floor above, the dive's descent back to a new level of this depth; EXTRA_FLOORS a trip),
  else Word of Recall.  Above the ceiling (80F to the ceiling - 1) the floor is no dead end and
  the dive's own descent (ladder_descent) takes its known stair down, the explore finding one.

Everything above them is as before: the emergency ladder, combat, the rest layer, *Destruction*,
the haste upkeep, the town returns.  A feeling not known yet (0) changes nothing; floors of
feeling 7 and below are explored as before.
"""
from __future__ import annotations

from hengbot.model import TVAL_RING

# floor/floor-events.cpp:124 get_dungeon_feeling: ``base`` and the Ring of Speed's rating
# (line 210: ``delta += 25 * base`` for an uncursed one; line 223: ``(level - depth) * base``
# while the item's level is deeper than the floor).
FEELING_BASE = 10
RING_OF_SPEED_RATING = 25 * FEELING_BASE
# lib/edit/BaseitemDefinitions.jsonc id 136 "level": 80 (angband_cap.RING_OF_SPEED_DEPTH).
RING_OF_SPEED_LEVEL = 80
# floor-events.cpp:230-262: the feeling of a summed rating; each feeling's band ends at
# floor_rating_boost(this delta) (``rating > boost(d)`` picks the feeling above it).  Feeling 2
# (rating > boost(1000)) has no end.
FEELING_CEILING_DELTA = {10: 0, 9: 100, 8: 200, 7: 300, 6: 400, 5: 600, 4: 800, 3: 1000}
# The board's ``floor.feeling`` before the game has told it (floor-changer.cpp:488).
UNKNOWN_FEELING = 0
# {"feeling": the no-ring feeling read on this floor visit}; floor_visit_memory forgets it.
MEMORY = "_ring_hunt_floor_done"


def floor_rating_boost(delta: int) -> int:
    """floor-events.cpp:111-117: the rating a ``delta`` adds."""
    delta = min(max(delta, 0), 1001)
    return delta * delta + 50 * delta


def ring_rating(depth: int) -> int:
    """The least ``delta`` an uncursed Ring of Speed adds on ``depth`` (lines 210 and 223)."""
    return RING_OF_SPEED_RATING + max(0, RING_OF_SPEED_LEVEL - depth) * FEELING_BASE


def no_ring_feelings(depth: int) -> frozenset:
    """The feelings no floor of ``depth`` holding an uncursed Ring of Speed can have: those whose
    band ends below the ring's own rating (the other terms only add)."""
    least = floor_rating_boost(ring_rating(depth))
    return frozenset(feeling for feeling, end in FEELING_CEILING_DELTA.items()
                     if floor_rating_boost(end) < least)


def observe(policy, snapshot) -> None:
    """Every board: a no-ring feeling read on a hunt floor is kept for the floor visit."""
    from hengbot import angband_cap  # import cycle (policy modules)

    feeling = getattr(snapshot, "feeling", None)
    if (not feeling or getattr(policy, MEMORY, None) is not None
            or not angband_cap.ring_hunt_floor(policy, snapshot)):
        return
    if feeling in no_ring_feelings(snapshot.dungeon_level):
        setattr(policy, MEMORY, {"feeling": feeling})


def finished(policy, snapshot) -> bool:
    """This hunt floor's feeling has ruled the Ring of Speed out on this visit."""
    from hengbot import angband_cap  # import cycle (policy modules)

    return (getattr(policy, MEMORY, None) is not None
            and angband_cap.ring_hunt_floor(policy, snapshot))


def floor_may_hold_ring(policy, snapshot) -> bool | None:
    """The public answer for other modules: None off a hunt floor (angband_cap
    ``ring_hunt_floor``), False on a hunt floor whose known feeling ruled an uncursed Ring of Speed
    out on this visit (``finished``; drops of monsters killed later are not covered), True on a
    hunt floor not ruled out yet (feeling unknown, or 7 and below)."""
    from hengbot import angband_cap  # import cycle (policy modules)

    if not angband_cap.ring_hunt_floor(policy, snapshot):
        return None
    return not finished(policy, snapshot)


def leave_key(policy, snapshot) -> str | None:
    """The explored floor's way out (explored_floor ``recall_key``: deep_stairs, else Word of
    Recall) on a finished hunt floor the dive goes no deeper from, asked by the idle layer before
    its searches, probes and explore (the stair underfoot is not searched around first)."""
    from hengbot import explored_floor  # import cycle (explored_floor reads this module)

    if not finished(policy, snapshot):
        return None
    return explored_floor.recall_key(policy, snapshot, exhausted=True)


def loot_filter(policy, snapshot, candidates: set) -> set:
    """The loot owner's ``candidates`` on a finished hunt floor: the pile stood on, the piles
    holding a ring and the hunt piles (hunt_items ``hunt_piles``: known rings and amulets, which
    the feeling does not rule out; supervisor 2026-11-28, fetched before the floor is left);
    every candidate elsewhere."""
    from hengbot import hunt_items  # import cycle (hunt_items -> angband_cap)

    if not candidates or not finished(policy, snapshot):
        return candidates
    here = snapshot.player.position
    hunted = hunt_items.hunt_piles(policy, snapshot)
    kept = set()
    for position in candidates:
        grid = snapshot.grid_at(position)
        if (position == here or position in hunted
                or (grid is not None and TVAL_RING in grid.object_tvals)):
            kept.add(position)
    return kept
