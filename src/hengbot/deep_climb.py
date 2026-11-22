"""The Castle's 50F recall landing, taken only to climb at once to the 38-42F band.

Owner 2026-11-22 (verbatim choice), n1-a life-531 (Lv50 Warrior, device skill 42: its thirteen
Home staves of *Destruction* at about 3% against the 80% of owner 2026-11-04, no MAGIC_MASTERY
piece owned): 「城の50Fに帰還してすぐ38〜42Fへ登る」.  Angband's 50F landing was refused for the
*Destruction* means and telepathy; the one exception of angband_hold (owner 2026-11-19
「この場合だけ城40F付近を許す」, dive_floor.pick_refused) found the Castle's and the Mountain's
recall landings both at 50 (the Mountain entered at 50 on 2026-11-19 19:59), refused by the same
gate, so the visit fundraised at the Yeek cave 1F for 58 hours and, the Alchemist out of
Treasure Detection, stood in town (loop-detected 2026-11-22 06:12).

This one case is the exception to owner 2026-11-18 「破壊を持っていないのに50F以降にいるのが
不具合」:

- ``admits``: a Castle (else Mountain) recall landing of exactly 50F (``LANDING``) whose only
  gaps are the 50F row of the depth table (``ROW_GAPS``: the *Destruction* means and telepathy).
  dive_floor.reaches_band asks it (``_fallback_landing_allowed``'s ``climb_landing``), so
  ``pick_refused`` takes the Castle and ``refused_dive_held`` keeps it.
- ``departure_admits``: in town, with that switch held and the target its dungeon, the recall
  to its 50F landing passes the town's destination gates (``_recall_destination_safe``,
  ``_destination_depth_allowed``, destruction_means.departure_carried) under the named reason
  ``REASON``.
- ``on_floor``: a floor of that dungeon at 50F or deeper while the switch is held.  There the
  row's gaps start no return (the resist-gap return, destruction_use.means_spent) and ``key``
  (the objectives layer's first rung) climbs: the up stairs underfoot, else the nearest known
  one, else a carried 周辺感知 (area_mapping), else the exploration step toward the stairs --
  never the loot.  Every rung above (the emergency ladder, combat) is kept.  Once on 49F or
  above, the ordinary rules (dive_floor's climb to the band) play.

The net under the rule (the same owner words): a floor of 50F or deeper entered from a
shallower floor of the same dungeon without the means, outside a quest floor, stops the bot
under ``STOP_REASON`` (``observe`` / ``stop_key``).  The 2026-11-19 Mountain 49F -> 50F arrival
is not in the kept decision log; every stair the policy takes into 50F+ is refused by the depth
gate (``_is_descent_target`` / ``_destination_depth_allowed``), so what is left is the game's
(a trap door, a Scroll of Teleport Level read as an escape).
"""
from __future__ import annotations

from hengbot.policy_constants import (
    DEEP_FLOOR_DEPTH, DESCEND_MIN_HP_RATIO, UP_STAIRS_KEY, WAIT_KEY, required_depth_gates,
)

LANDING = DEEP_FLOOR_DEPTH
ROW_GAPS = required_depth_gates(DEEP_FLOOR_DEPTH) - required_depth_gates(DEEP_FLOOR_DEPTH - 1)
REASON = "castle-climb-landing-50"
STOP_REASON = "dungeon:blocked:deep-arrival-without-destruction"
STOP_MESSAGE = ("a floor of 50F or deeper was entered from a shallower floor of the same "
                "dungeon without the *Destruction* means")
MEMORY = "_deep_climb_arrival"


def admits(missing, dungeon_id: int, landing: int) -> bool:
    """The Castle's (or the Mountain's) 50F landing whose only gaps are the 50F row."""
    from hengbot import dive_floor  # import cycle (dive_floor reads the policy's gates)

    missing = frozenset(missing)
    return (dungeon_id in dive_floor.DIVE_FLOOR_DUNGEONS and landing == LANDING
            and bool(missing) and missing <= ROW_GAPS)


def _held_dungeon(policy, snapshot) -> int | None:
    from hengbot import dive_floor

    dungeon = dive_floor.climb_dungeon(policy)
    if dungeon is None or not dive_floor.refused_dive_held(policy, snapshot):
        return None
    return dungeon


def departure_admits(policy, snapshot, depth: int, *, dungeon_id: int | None = None,
                     missing=None) -> bool:
    """In town: the recall to the held Castle's 50F landing, its only gaps the 50F row."""
    if not getattr(snapshot, "in_town", False) or depth != LANDING:
        return False
    dungeon = _held_dungeon(policy, snapshot)
    if dungeon is None or dungeon != (policy._target_dungeon_id if dungeon_id is None
                                      else dungeon_id):
        return False
    if policy._dungeon_entry_depth(snapshot, dungeon, via_recall=True) != depth:
        return False
    if missing is None:
        missing = policy._missing_required_abilities(snapshot, depth, owned=True)
    return admits(missing, dungeon, depth)


def departure_gaps(policy, snapshot, depth: int) -> frozenset:
    """The worn kit's gaps at the departure's landing ``depth``, none for the held Castle's 50F
    landing whose only gaps are the 50F row (``departure_admits``).  The town's readers of the
    worn kit at the landing ask it: the departure minimum's ``depth_abilities`` leaf (n1-a
    life-531 2026-11-22 08:25: the Mountain's 50F switch, every other gate admitting it, stopped
    the town end as town:blocked:survival:depth_abilities) and the equipment departure's
    worn-loadout checks."""
    missing = frozenset(policy._missing_required_abilities(snapshot, depth))
    if missing and departure_admits(policy, snapshot, depth, missing=missing):
        return frozenset()
    return missing


def on_floor(policy, snapshot) -> bool:
    """A floor of the held Castle at 50F or deeper (no quest floor)."""
    from hengbot import dive_floor

    floor_key = getattr(snapshot, "floor_key", None)
    if getattr(snapshot, "in_town", False) or not floor_key or floor_key[2] != 0:
        return False
    return (floor_key[1] >= LANDING and dive_floor.climb_dungeon(policy) == floor_key[0])


def floor_gaps(policy, snapshot, gaps) -> frozenset:
    """``gaps`` of the floor stood on, the 50F row taken out on a climb floor."""
    gaps = frozenset(gaps)
    return gaps - ROW_GAPS if on_floor(policy, snapshot) else gaps


def key(policy, snapshot):
    """The climb off a 50F+ floor of the held Castle, before any loot or objective."""
    from hengbot import area_mapping

    if not on_floor(policy, snapshot) or policy._floor_navigation_exit_locked(snapshot):
        return None
    here = snapshot.grid_at(snapshot.player.position)
    if here is not None and policy._is_upstairs_target(here):
        if snapshot.player.hp_ratio < DESCEND_MIN_HP_RATIO:
            return None
        policy.last_reason = f"{REASON}:ascend"
        return UP_STAIRS_KEY
    step = policy._nearest_goal_step(snapshot, policy._is_upstairs_target)
    if step is not None:
        move = policy._step_toward(snapshot, step)
        if move is not None:
            policy.last_reason = f"{REASON}:seek-upstairs"
            return move
    mapped = area_mapping.deep_climb_key(policy, snapshot)
    if mapped is not None:
        return mapped
    goal = policy._town_producer_entry("_explore_step", lambda: policy._explore_step(snapshot))
    if goal is None:
        return None
    move = policy._step_toward(snapshot, goal)
    if move is not None:
        policy.last_reason = f"{REASON}:search-upstairs"
    return move


# --- the net: an arrival at 50F+ by a descent without the means ------------------------------

def observe(policy, snapshot) -> None:
    """Every board: a new floor of 50F or deeper entered from a shallower floor of the same
    dungeon, with no *Destruction* means and no quest, is remembered for ``stop_key``.  A
    shallower 50F+ floor counts too: n1-a life-531 2026-11-22 08:04, on the Castle's 50F climb,
    fell through two trap doors (50F -> 52F -> 54F); the Castle's recall depth became 54 and
    the climb's landing was lost.  A floor deeper than the last one is a new descent too."""
    from hengbot import deep_fall_guard, destruction_use

    floor_key = tuple(getattr(snapshot, "floor_key", ()) or ())
    record = getattr(policy, MEMORY, None)
    previous = record[0] if record else None
    stopped = record[1] if record else None
    if previous == floor_key:
        return
    if (previous is not None and floor_key and not snapshot.in_town
            and previous[0] == floor_key[0] and 0 < previous[1] < floor_key[1]
            and floor_key[1] >= LANDING
            and floor_key[2] == 0 and previous[2] == 0
            and not deep_fall_guard.sanctioned(policy, floor_key[0], floor_key[1])
            and not destruction_use.holds_means(policy, snapshot)):
        stopped = floor_key
    elif not (stopped is not None and stopped == floor_key):
        stopped = None
    setattr(policy, MEMORY, (floor_key, stopped))


def stop_key(policy, snapshot):
    """The named stop of an unadmitted 50F+ arrival (``observe``)."""
    record = getattr(policy, MEMORY, None)
    if not record or record[1] is None or record[1] != tuple(snapshot.floor_key):
        return None
    policy.last_reason = STOP_REASON
    return WAIT_KEY
