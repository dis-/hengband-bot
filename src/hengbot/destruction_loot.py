"""The floor items a non-urgent *Destruction* would delete: a clean place first, else the valuables.

Owner 2026-11-17 (the 50F+ efficiency study's 第2位, answer 「価値の高い品は先に拾ってから撃つ」):
the uses that wait for no blow -- the approach to a T1 known only by detection and the use on a
sleeping or out-of-radius T1 (threat_tiers), the sealers of a route veto (retreat_enclosure) --
are made from a cell none of the remembered floor items lies within the circle of; where there
is none, the potions, scrolls, magic devices, rings and amulets inside it are picked up first
while no hostile is in view, then the use is made.  The instant-death and emergency uses are
unchanged (they never ask this).

The study (C:/hengband-backups/pdca/deep-efficiency-1117/REPORT.md 4.3): n1-c life-216's 1,645
uses at 50F+ deleted 2,771 remembered floor items, 652 of them worth taking (Healing, Speed,
Resistance potions, Stone to Mud wands).

Game (C:/hengband/src): spell-kind/spells-floor.cpp destroy_area deletes every item in its
circle, of radius 13 + randint0(5) for the staff and the absorbed power (cmd-usestaff.cpp:282),
so an item 17 or nearer may go (destruction_use ``in_worst_radius``); 22 or nearer where the use
goes through Powerful Activation, 18 + randint0(5) (destruction_use ``worst_radius``: the given-up
quest target beyond the sure radius, owner 2026-11-22; until 2026-11-23 this read 17 there too).  The remembered items are the loot memory and the
game's found items (``remembered_piles``: the detected piles too, n1-b life-411's 64F use at
turn 5161935 had sixteen of them within 17 and no known grid under any); a pile's classes are
the found items' (grid_map ``found_items``: y, x, count, tval...).

The order, asked where the use is due (``key``, before destruction_use ``key``):

1. A committed place (``MEMORY``) is walked to while it still has a monster the use leaves within
   the sure radius and no remembered item within the worst one; on it, None: the use is made.
2. Else the nearest such place within ``PLACE_MAX_DISTANCE`` of the player, with no awake hostile
   in view: committed and walked to.
3. Else, with no hostile in view, the nearest valuable pile (``VALUABLE_TVALS``) inside the worst
   radius: walked to and picked up, the cell committed (``MEMORY`` "fetch").  A pile no known way
   leads to (shown by detection on a floor the map does not hold) is walked toward by the
   reachable remembered frontier nearest it (``_frontier_step``, 2026-11-23; until then the use
   was made at once, and such piles were most of the valuables the non-urgent uses deleted).
4. Else None: the use is made as before.

The fetch goes on where the use is not due as well (``_committed``): the piles a use at the
committed cell may delete are fetched one after another while a hostile the use leaves is still
shown, the approach's gates hold and no hostile is in view.  n1-c life-216 (Glass castle 59F,
2026-11-17 18:40-18:41, loop-detected): at (37,37) the sensed ブルー・デイドラゴン (35,49) was 13
off, the use due, and the fetch stepped west toward the potions at (42,24); at (37,36) it was 14
off, the use not due, and the approach stepped back east: 40 alternations until the loop detector.
A target the remembered approach still goes to while detection has lost it (threat_tiers
``remembered_approach_key``, n1-b life-377) held the commitment as a shown one does (since Q3,
below, every begun fetch holds without either).  n1-b life-411 (Angband 80F, 2026-11-18
01:51-01:52, loop-detected): the fetch began at (8,102), the use due on the sleeping T1 (race 1306) at (12,90), and walked
east toward the staff, potion and ring at (8,110)-(10,111); at (8,109) the T1 was 21 off
(monster-update.cpp: telepathy within MAX_PLAYER_SIGHT 20), no longer shown, the commitment was
not asked and the remembered approach stepped back west, until the loop detector (40 decisions).

A hostile in view the walk does not survive (``survivable``; until 2026-11-28 any hostile in
view) ends the fetch for the scene (``MEMORY`` "withheld", until the flash): the owner's words
pick up first only 「見える敵がいなければ」, so once one is seen the use goes first and a later
board out of its sight does not start the fetch again.  n1-c life-216 (Angband 80F,
2026-11-18 03:11-03:12, loop-detected): at (26,74) the use was due and the fetch walked toward
the potion at (39,80) by (27,75), (26,76), (25,77); at (25,77) a sleeping hostile (race 423) at
(5,76) came into view, the fetch dropped, and the approach stepped back out of its sight to
(26,76), (27,75), (26,74), where the use was due again and the fetch began afresh, until the
loop detector.

Every scene is bounded: ``DECISIONS_MAX`` decisions of this module per floor between two flashes
(a flash resets it), and a pile the pickup did not take is not gone to again on the floor; past
the bound the use is made as before, so no walk here can hold a use back for good.

Owner 2026-11-18 (maintainability Q3 「命の危険が無ければ取り終える」): a begun fetch is walked to its
end whoever asks (loot_walk, the one loot walk commitment): it no longer needs a hostile the use
leaves to be shown or remembered, only no life danger (loot_walk ``life_danger``), the approach's
gates and the bound above; the ordinary loot walk asked meanwhile continues it
(loot_walk ``normal_yield_key``).  The one entry of the non-urgent uses is
destruction_use ``loot_then_use`` (the maintainability review 1118 (a)-6).

Supervisor 2026-11-28 (the hunt items, hunt_items ``hunt_pile``; its numbers are there): of the
356 uses n1-b life-419 made on Angband 80F in the decision log's window (42 floors, 2026-11-28
01:29-05:11), 201 had no hostile in view: 194 were the sensed T1 rule's (threat_tiers
``sensed_t1_destruction_key`` 144, ``remembered_approach_key`` 50: a T1 asleep or out of the
player's sight, known by telepathy or detection, owner 2026-11-10 「積極的に*破壊*で消しにいく」),
no emergency.  The uses that deleted what the bot knew of had declined the fetch for the scene's
bound (``DECISIONS_MAX``: the 02:17:48 use deleted a 破壊のアミュレット 13 off), for a hostile in
view (``withheld``: on 02:18:35 a sleeping ドラウグル・ウォーカー 16 off withheld the fetch, and the
use deleted a Ring of Speed 13 off with 21 other items) or were asked with ``loot`` False (the
11-08 leave).  So, unless the board is 即死 (threat_tiers ``instant_death``, ``urgent``):

* the hunt piles in the circle are fetched first, nearest first, under their own bound
  (``HUNT_DECISIONS_MAX``, which the ordinary fetch's walks do not spend), for the 11-08 leave's
  use too (``key``'s ``hunt_only``);
* a hostile in view withholds a fetch only when the walk is not survivable (``survivable``: the
  awake shown hostiles' predicted damage over the steps to the pile, plus the plan's reserve,
  threat_projection ``plan_reserve``, reaches the HP); this replaces the 2026-11-18 reading that
  any hostile in view withholds it (n1-c life-216), the ``withheld`` latch kept;
* a hunt pile no way reaches holds the use (``holds``): the caller's answers that erase nothing
  (the stairs, a teleport, the walk; threat_tiers) come first, the use only past the hunt bound.
"""

from __future__ import annotations

from hengbot import destruction_use, full_pack_exchange, hunt_items, loot_frontier
from hengbot.unwanted_kinds import UNWANTED_TVALS
from hengbot.model import (
    Position, TVAL_AMULET, TVAL_POTION, TVAL_RING, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND,
    game_distance,
)

PLACE_REASON = "destruction-loot:place"
FETCH_REASON = "destruction-loot:fetch"
FRONTIER_REASON = "destruction-loot:fetch-frontier"
PICKUP_REASON = "destruction-loot:pickup"
TRIGGER_REASON = "destruction-loot:trigger-autodestroy"
# Owner 2026-11-17 「薬・巻物・魔法道具・指輪・首飾り」.
VALUABLE_TVALS = frozenset({TVAL_POTION, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND, TVAL_ROD,
                            TVAL_RING, TVAL_AMULET})
# The classes no pile is kept for (policy_helpers ``_floor_pile_is_junk``: skeletons, bottles,
# junk, statues, figurines, capture balls).
JUNK_TVALS = UNWANTED_TVALS | {1, 3, 10}
# The farthest (in game distance) a clean place is looked for: a short move beside the T1, not a
# second approach.
PLACE_MAX_DISTANCE = 8
# This module's decisions on a floor between two flashes before the use goes ahead regardless.
DECISIONS_MAX = 40
# The hunt piles' own decisions between two flashes (their fetches and the holds of the use): the
# scene's 40, counted apart so the ordinary fetch's walks do not spend them (supervisor
# 2026-11-28: the 02:17:48 use deleted a 破壊のアミュレット past the spent scene bound).
HUNT_DECISIONS_MAX = DECISIONS_MAX
HELD_CAUSE = "hunt-held"
# {"floor": floor_key, "place": Position | None, "fetch": Position | None (the cell the fetch
#  began on, where the use was due), "withheld": bool (a hostile was in view: no fetch until the
#  flash), "decisions": int, "tried": set of Position, "radius": int (the worst radius of the use
#  due, destruction_use ``worst_radius``), "frontier": Position | None (the frontier the fetch walks
#  to, ``_frontier_step``), "frontiers": set of Position (the ones reached or given up),
#  "declined": (game turn, cause) record only (``declined``), "hunt_decisions": int (the hunt
#  piles' decisions, ``HUNT_DECISIONS_MAX``), "held": the game turn the use was held for a hunt
#  pile no way reaches (``holds``), or None}
MEMORY = "_destruction_loot_memory"


def _memory(policy, snapshot) -> dict:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        memory = {"floor": snapshot.floor_key, "place": None, "fetch": None, "withheld": False,
                  "decisions": 0, "tried": set(), "radius": destruction_use.WORST_RADIUS,
                  "frontier": None, "frontiers": set(), "declined": (None, None),
                  "hunt_decisions": 0, "held": None}
        setattr(policy, MEMORY, memory)
    return memory


def observe(policy, snapshot) -> None:
    """A flash ends the scene: the next use starts with a fresh bound."""
    memory = getattr(policy, MEMORY, None)
    if memory is not None and any(message in destruction_use.FLASH for message in snapshot.messages):
        memory["place"] = None
        memory["fetch"] = None
        memory["withheld"] = False
        memory["decisions"] = 0
        memory["hunt_decisions"] = 0
        memory["frontier"] = None


def remembered_piles(policy, snapshot) -> set:
    """The remembered floor piles: the loot memory (``_known_loot``, the non-junk piles of known
    grids) and the game's found items (grid_map ``found_items``: the detected ones too, whose
    grids the map may not show) that are not junk only (``JUNK_TVALS``)."""
    piles = set(getattr(policy, "_known_loot", ()))
    piles.update(Position(row[0], row[1]) for row in snapshot.found_items or ()
                 if any(tval not in JUNK_TVALS for tval in row[3:]))
    return piles


def exposed(policy, snapshot, centre=None, radius=None) -> list:
    """The remembered floor piles a use made at ``centre`` (the player's cell) may delete:
    within ``radius`` (by default the worst radius of the use due, ``MEMORY`` "radius", 17 or the
    powered 22)."""
    if radius is None:
        memory = getattr(policy, MEMORY, None)
        radius = (memory.get("radius", destruction_use.WORST_RADIUS)
                  if memory is not None and memory.get("floor") == snapshot.floor_key
                  else destruction_use.WORST_RADIUS)
    return [position for position in remembered_piles(policy, snapshot)
            if destruction_use.in_worst_radius(snapshot, position, centre=centre, radius=radius)]


def _valuable(snapshot, position) -> bool:
    row = next((row for row in snapshot.found_items or ()
                if row[0] == position.y and row[1] == position.x), None)
    return row is not None and any(tval in VALUABLE_TVALS for tval in row[3:])


def _shown_leaving(snapshot, leaving) -> list:
    shown = {monster.index for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
             if monster.hostile}
    return [monster for monster in leaving if monster.index in shown]


def _place(policy, snapshot, centre, shown) -> bool:
    return (any(destruction_use.in_sure_radius(snapshot, monster, centre=centre) for monster in shown)
            and not exposed(policy, snapshot, centre))


def _in_view(snapshot, *, awake_only: bool) -> bool:
    return any(monster.hostile and not (awake_only and monster.asleep)
               for monster in snapshot.visible_monsters)


def urgent(policy, snapshot) -> bool:
    """The board is 即死 (threat_tiers ``instant_death``: the one-action projection reaches the
    HP): no hunt pile holds or delays a use."""
    from hengbot import threat_tiers  # import cycle
    return threat_tiers.instant_death(policy, snapshot).holds


def survivable(policy, snapshot, pile) -> bool:
    """The walk to ``pile`` survives the awake hostiles shown (seen or sensed): their predicted
    damage over the steps to it (game distance, at least one; policy ``_predicted_damage``) and
    the plan's reserve (threat_projection ``plan_reserve``: a tenth of the maximum HP or the next
    action's damage) stay below the HP.  No awake hostile shown: survivable."""
    from hengbot.threat_projection import plan_reserve  # import cycle
    awake = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
             if monster.hostile and not monster.asleep]
    if not awake:
        return True
    steps = max(1, game_distance(snapshot.player.position, pile))
    player = snapshot.player
    reserve = plan_reserve(player.max_hp, policy._predicted_damage(snapshot, awake, turns=1))
    return policy._predicted_damage(snapshot, awake, turns=steps) + reserve < player.hp


def holds(policy, snapshot) -> bool:
    """``key`` held the use on this board for a hunt pile no way reaches: the caller answers
    without it (destruction_use ``loot_then_use``)."""
    memory = getattr(policy, MEMORY, None)
    return (memory is not None and memory.get("floor") == snapshot.floor_key
            and memory.get("held") == snapshot.turn)


def _hunt_exposed(policy, snapshot, memory) -> set:
    """The untried hunt piles (hunt_items ``hunt_piles``) the use due may delete."""
    hunted = hunt_items.hunt_piles(policy, snapshot)
    return {position for position in exposed(policy, snapshot)
            if position in hunted and position not in memory["tried"]}


def _hunt_key(policy, snapshot, memory, leaving, *, hunt_only) -> str | None:
    """The hunt piles first (supervisor 2026-11-28, the module docstring): their fetch, else --
    none reachable -- a clean place (``_new_place``, not for ``hunt_only``), else the use held
    (``holds``); within ``HUNT_DECISIONS_MAX``.  None: no hunt pile asks (the 即死 board, none
    exposed, the bound spent, or the walk not survivable: the use or the ordinary fetch as
    before)."""
    if urgent(policy, snapshot) or memory["hunt_decisions"] >= HUNT_DECISIONS_MAX:
        return None
    if not _hunt_exposed(policy, snapshot, memory):
        return None
    answer = _fetch(policy, snapshot, begin=True, hunt_only=True)
    if answer is None and memory["withheld"]:
        # A hostile in view the walk does not survive: the use as before (``survivable``).
        return None
    if answer is None and not hunt_only:
        answer = _new_place(policy, snapshot, leaving)
    memory["hunt_decisions"] += 1
    if answer is None:
        memory["held"] = snapshot.turn
        _decline(memory, snapshot, HELD_CAUSE)
    return answer


def key(policy, snapshot, leaving, *, hunt_only=False) -> str | None:
    """A step or a pickup before the use that leaves ``leaving``, else None (the use is made, or
    -- ``holds`` -- held for an unreachable hunt pile).  Asked through destruction_use
    ``loot_then_use``.  ``hunt_only``: the hunt piles alone (the use the 11-08 leave makes, whose
    ordinary items stay as they were).  None on the finale expedition's way down (owner
    2026-11-24 「寄り道は不要。」, finale_descent): the use is made."""
    from hengbot import finale_descent  # import cycle
    if finale_descent.applies(policy, snapshot):
        return None
    leaving = list(leaving or ())
    if not leaving or not destruction_use.usable(policy, snapshot, leaving=leaving):
        return None if hunt_only else _committed(policy, snapshot, leaving)
    # The real circle of the use due (the powered one reaches 22, owner 2026-11-23 loot yield).
    memory = _memory(policy, snapshot)
    memory["radius"] = destruction_use.worst_radius(policy, snapshot, leaving)
    memory["declined"] = (snapshot.turn, None)
    if not exposed(policy, snapshot):
        memory["place"] = None
        _decline(memory, snapshot, "nothing-exposed")
        return None
    hunted = _hunt_key(policy, snapshot, memory, leaving, hunt_only=hunt_only)
    if hunted is not None or holds(policy, snapshot) or hunt_only:
        return hunted
    if memory["decisions"] >= DECISIONS_MAX:
        _decline(memory, snapshot, "bound")
        return None
    # A committed fetch's step counts itself (``continue_fetch``, which the ordinary walk asks
    # too): counted once here it went to the bound at half its decisions.  The committed place's
    # walk is counted as before.
    fetching = memory.get("place") is None
    answer = _committed(policy, snapshot, leaving)
    if answer is not None and fetching:
        return answer
    if answer is None:
        answer = _new_place(policy, snapshot, leaving)
    if answer is None:
        answer = _fetch(policy, snapshot, begin=True)
    if answer is not None:
        memory["decisions"] += 1
    return answer


def _decline(memory, snapshot, cause) -> None:
    """Record only: why no step or pickup came before the use on this board (``declined``)."""
    turn, earlier = memory.get("declined") or (None, None)
    if turn != snapshot.turn or earlier is None:
        memory["declined"] = (snapshot.turn, cause)


def declined(policy, snapshot) -> str | None:
    """Record only (destruction_use ``use_report``): why ``key`` answered None on this board --
    "nothing-exposed", "bound" (``DECISIONS_MAX``), "withheld" (a hostile in view), "no-valuable"
    (no untried valuable pile in the circle), "no-way" (none reachable, no frontier toward them)
    -- else None."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        return None
    turn, cause = memory.get("declined") or (None, None)
    return cause if turn == snapshot.turn else None


def _committed(policy, snapshot, leaving) -> str | None:
    """The walk to the committed place, while it still serves (``MEMORY``); else the walk to the
    committed pile and its pickup (``continue_fetch``)."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        return None
    if memory.get("place") is None:
        return continue_fetch(policy, snapshot)
    place = memory["place"]
    shown = _shown_leaving(snapshot, leaving)
    if (memory["decisions"] >= DECISIONS_MAX or not shown or not _place(policy, snapshot, place, shown)
            or not destruction_use.approach_gates(policy, snapshot)
            or snapshot.player.position == place):
        memory["place"] = None
        return None
    found = policy._nearest_goal_and_step(snapshot, lambda grid: grid.position == place)
    if found is None:
        memory["place"] = None
        return None
    step = found[1]
    memory["decisions"] += 1
    policy.last_reason = PLACE_REASON
    return policy._step_toward(snapshot, step)


def _new_place(policy, snapshot, leaving) -> str | None:
    if _in_view(snapshot, awake_only=True):
        return None
    shown = _shown_leaving(snapshot, leaving)
    here = snapshot.player.position
    found = policy._nearest_goal_and_step(snapshot, lambda grid: (
        game_distance(here, grid.position) <= PLACE_MAX_DISTANCE
        and _place(policy, snapshot, grid.position, shown)))
    if found is None:
        return None
    held = _yield_to_walk(policy, snapshot)
    if held is not None:
        return held
    place, step = found
    _memory(policy, snapshot)["place"] = place
    policy.last_reason = PLACE_REASON
    return policy._step_toward(snapshot, step)


def fetch_committed(policy, snapshot) -> bool:
    """A fetch is committed on this floor (``MEMORY`` "fetch")."""
    memory = getattr(policy, MEMORY, None)
    return (memory is not None and memory.get("floor") == snapshot.floor_key
            and memory.get("fetch") is not None)


def continue_fetch(policy, snapshot) -> str | None:
    """The committed fetch on a board where no use asks (``key``'s first test) or where another
    loot walk asks (loot_walk ``normal_yield_key``): the piles a use at the committed cell
    (``MEMORY`` "fetch", where the use was due when the fetch began) may delete are walked to and
    picked up one after another, until none is left, ``DECISIONS_MAX``, the approach's gates
    failing or life danger (owner 2026-11-18 Q3 「命の危険が無ければ取り終える」, loot_walk); then
    the commitment is dropped and None.  Before Q3 it also ended once no hostile the use leaves
    was shown (n1-c life-216 1117) or remembered by the approach (n1-b life-411 1118), and the
    ordinary loot walk took the board over (n1-b life-411 1119, loot_walk)."""
    from hengbot import loot_walk  # import cycle

    if not fetch_committed(policy, snapshot):
        return None
    memory = getattr(policy, MEMORY)
    if (memory["decisions"] >= DECISIONS_MAX
            or not destruction_use.approach_gates(policy, snapshot)
            or loot_walk.life_danger(policy, snapshot)):
        memory["fetch"] = None
        return None
    answer = _fetch(policy, snapshot, memory["fetch"])
    if answer is not None:
        memory["decisions"] += 1
    return answer


def walk_held(policy, snapshot) -> str | None:
    """The ordinary loot walk in progress, continued in place of the approach's own step
    (loot_walk ``approach_yield_key``) within this module's bound: counted as a decision of the
    scene, so past ``DECISIONS_MAX`` the approach walks on (owner 2026-11-18 Q3 「上限40回は残す」)."""
    memory = _memory(policy, snapshot)
    if memory["decisions"] >= DECISIONS_MAX:
        return None
    held = _yield_to_walk(policy, snapshot)
    if held is not None:
        memory["decisions"] += 1
    return held


def _yield_to_walk(policy, snapshot) -> str | None:
    """Owner 2026-11-18 Q3: a place or a fetch about to begin leaves the board to the ordinary
    loot walk in progress (loot_walk ``fetch_yield_key``); asked only once one would begin, so a
    use with nothing to begin is made as before."""
    from hengbot import loot_walk  # import cycle

    return loot_walk.fetch_yield_key(policy, snapshot)


def _fetch(policy, snapshot, centre=None, *, begin=False, hunt_only=False) -> str | None:
    """The step toward (or the pickup of) the nearest untried valuable pile a use at ``centre``
    (the player's cell by default, where the use is due) may delete, the hunt piles (hunt_items
    ``hunt_piles``) before the others and, with ``hunt_only``, alone (supervisor 2026-11-28; not
    on the 即死 board, ``urgent``); ``centre`` is committed (``MEMORY`` "fetch") while such a
    pile is left, else dropped and None.  A hostile in view the walk does not survive
    (``survivable``) withholds the fetch until the flash (``MEMORY`` "withheld", n1-c life-216
    1118).  A fetch to ``begin`` continues the ordinary loot walk in progress instead (loot_walk
    ``fetch_yield_key``, owner 2026-11-18 Q3)."""
    memory = _memory(policy, snapshot)
    here = snapshot.player.position
    centre = here if centre is None else centre
    memory["fetch"] = None
    if memory.get("withheld"):
        _decline(memory, snapshot, "withheld")
        return None
    untried = {position for position in exposed(policy, snapshot, centre)
               if position not in memory["tried"]}
    hunted = frozenset() if urgent(policy, snapshot) else hunt_items.hunt_piles(policy, snapshot)
    piles = untried & hunted
    if not piles and not hunt_only:
        piles = {position for position in untried if _valuable(snapshot, position)}
    if piles and _in_view(snapshot, awake_only=False) and not survivable(
            policy, snapshot, min(piles, key=lambda position: game_distance(here, position))):
        memory["withheld"] = True
        _decline(memory, snapshot, "withheld")
        return None
    if not piles:
        _decline(memory, snapshot, "no-valuable")
        return None
    if here in piles:
        if begin:
            held = _yield_to_walk(policy, snapshot)
            if held is not None:
                return held
        # A full pack makes room for a hunt pile by its cheapest spare (full_pack_exchange,
        # supervisor 2026-11-28 rule 4); the pickup follows on the next board.
        pickup = (full_pack_exchange.key(policy, snapshot, policy._strategic_hostiles(snapshot),
                                         only=frozenset({here}))
                  if here in hunted else None)
        if pickup is not None:
            memory["fetch"] = centre
            return pickup
        pickup = policy._current_floor_item_key(
            snapshot, pickup_reason=PICKUP_REASON, trigger_reason=TRIGGER_REASON)
        if pickup is None or policy.last_reason == PICKUP_REASON:
            # Taken now, or refused (a full pack, a pile the budget refuses): not gone to again.
            memory["tried"].add(here)
        if pickup is not None:
            memory["fetch"] = centre
            return pickup
        piles.discard(here)
        if not piles:
            _decline(memory, snapshot, "no-valuable")
            return None
    found = policy._nearest_goal_and_step(snapshot, lambda grid: grid.position in piles)
    reason = FETCH_REASON
    if found is not None:
        step = found[1]
        memory["frontier"] = None
    else:
        step = _frontier_step(policy, snapshot, piles, memory)
        reason = FRONTIER_REASON
        if step is None:
            _decline(memory, snapshot, "no-way")
            return None
    if begin:
        held = _yield_to_walk(policy, snapshot)
        if held is not None:
            return held
    memory["fetch"] = centre
    policy.last_reason = reason
    return policy._step_toward(snapshot, step)


def _frontier_step(policy, snapshot, piles, memory):
    """No known way leads to the ``piles``: the step toward the reachable remembered frontier
    nearest them (loot_frontier ``frontier_path``, owner 2026-11-13 「その品の方へ探索を寄せる」),
    kept as ``MEMORY`` "frontier" until it is stood on (then spent, ``MEMORY`` "frontiers") or
    no longer reachable; None with none.  Within the scene's bound (``DECISIONS_MAX``).

    The 2026-11-23 loot yield study (C:/hengband-backups/pdca/loot-yield-1123): of the uses with no
    hostile in view in the scene that deleted valuables known to the bot, every one replayed had
    refused the fetch here for want of a known way (the piles the absorbed detection showed in a
    room whose floor the map did not hold): n1-c life-221 (Angband 80F, turn 4392698) at (49,88),
    the potions and scrolls six cells west on unknown floor; n1-b life-416 (Angband 95F, turn
    4038441) at (20,11), two Speed rings and a potion in a walled room five cells off."""
    here = snapshot.player.position
    spent = memory["frontiers"]
    goal = memory.get("frontier")
    if goal == here:
        spent.add(goal)
        goal = None
    path = []
    if goal is not None and goal not in spent:
        path = loot_frontier.frontier_path(policy, snapshot, [goal], spent=spent)
        if not path or path[-1] != goal:
            spent.add(goal)
            path = []
    if not path:
        path = loot_frontier.frontier_path(policy, snapshot, piles, spent=spent)
    if not path:
        memory["frontier"] = None
        return None
    memory["frontier"] = path[-1]
    return path[0]
