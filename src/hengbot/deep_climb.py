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
  never the loot.  Every rung above (the emergency ladder, combat) is kept.  ``key`` climbs the
  same way on every floor of that dungeon below the band (``climb_floor``: 49F up to the band's
  deepest floor + 1, owner 2026-11-22 「すぐ38〜42Fへ登る」); the row's gaps are the 50F+
  floors' only.

A floor of 50F or deeper entered from a shallower floor of the same dungeon without the means,
outside a quest floor (``observe``), is climbed from the same way: owner 2026-11-23 (n1-a
life-535, the Castle's 48F trap door onto 50F, the answer 「登りと同じにすぐ45F以浅へ登る」) -- by
any path the arrival holds the climb switch on its dungeon (``_hold_climb``: the unsafe-recall
fallback's Castle climb, dive_floor ``bind_refused``), so ``key`` climbs to the band (at most
45F), the climb reads the teleport as above 50F (deep_teleport.applies) and the Recall read on a
band floor answers the reset-recall question y (dive_floor.reset_recall_depth).  Every stair the
policy takes into 50F+ is refused by the depth gate (``_is_descent_target`` /
``_destination_depth_allowed``), so what is left is the game's (a trap door, which drops one
floor or two, deep_fall_guard; a Scroll of Teleport Level read as an escape).

Standing on such a floor is enough (``_standing_without_means``): the first board after a
restart has no previous floor, and n1-a life-535 is resumed on the Castle's 50F.  Only where no
climb can be held (a dungeon other than the Castle and the Mountain, or a band the kit cannot
reach, dive_floor.reaches_band) does an arrival from a shallower floor stop the bot under
``STOP_REASON`` (``stop_key``).
"""
from __future__ import annotations

from hengbot import deep_admission
from hengbot.policy_constants import (
    DESCEND_MIN_HP_RATIO, UP_STAIRS_KEY, WAIT_KEY, required_depth_gates,
)

LANDING = deep_admission.LANDING
ROW_GAPS = (required_depth_gates(LANDING)
            - required_depth_gates(deep_admission.DEEPEST_WITHOUT_MEANS))
REASON = "castle-climb-landing-50"
# The climb floors below 50F: ladder_descent's climb rung's reasons (``key``).
CLIMB_REASON = "castle-climb"
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
    # The worn kit's gaps already read the means: the climb alone is asked (deep_admission).
    if missing and deep_admission.verdict(
            policy._target_dungeon_id, depth, "recall",
            climbing=lambda: departure_admits(policy, snapshot, depth, missing=missing)).climb:
        return frozenset()
    return missing


def on_floor(policy, snapshot) -> bool:
    """A floor of the held Castle at 50F or deeper (no quest floor)."""
    from hengbot import dive_floor

    floor_key = getattr(snapshot, "floor_key", None)
    if getattr(snapshot, "in_town", False) or not floor_key or floor_key[2] != 0:
        return False
    return deep_admission.verdict(
        floor_key[0], floor_key[1], "stand",
        climbing=lambda: dive_floor.climb_dungeon(policy) == floor_key[0]).climb


def floor_gaps(policy, snapshot, gaps) -> frozenset:
    """``gaps`` of the floor stood on, the 50F row taken out on a climb floor."""
    gaps = frozenset(gaps)
    return gaps - ROW_GAPS if on_floor(policy, snapshot) else gaps


def climb_floor(policy, snapshot) -> bool:
    """A floor ``key`` climbs from at once: a 50F+ floor of the held Castle (``on_floor``), or
    one of its floors below the band (dive_floor.climb_switch_floor), no quest floor."""
    from hengbot import dive_floor

    floor_key = getattr(snapshot, "floor_key", None)
    if getattr(snapshot, "in_town", False) or not floor_key or floor_key[2] != 0:
        return False
    return on_floor(policy, snapshot) or dive_floor.climb_switch_floor(policy, snapshot, floor_key)


def key(policy, snapshot):
    """The climb off a climb floor of the held Castle (``climb_floor``), before any loot or
    objective.

    Owner 2026-11-22 「城の50Fに帰還してすぐ38〜42Fへ登る」: every floor below the band, not the 50F+
    ones only.  n1-a life-531 (13:38-13:40) walked Mountain 47F and 49F after loot and the
    exploration's frontier (ladder_descent's climb rung, below the loot, acts only once an up
    staircase is known).  Below 50F the reasons are the climb rung's ``castle-climb:*``; a fled
    breeder floor's walk-out keeps its place there as it had over that rung."""
    from hengbot import area_mapping

    if not climb_floor(policy, snapshot) or policy._floor_navigation_exit_locked(snapshot):
        return None
    landing = on_floor(policy, snapshot)
    if not landing and policy._breeder_walkout_active(snapshot):
        return None
    family = REASON if landing else CLIMB_REASON
    here = snapshot.grid_at(snapshot.player.position)
    if here is not None and policy._is_upstairs_target(here):
        if snapshot.player.hp_ratio < DESCEND_MIN_HP_RATIO:
            return None
        policy.last_reason = f"{family}:ascend"
        return UP_STAIRS_KEY
    step = policy._nearest_goal_step(snapshot, policy._is_upstairs_target)
    if step is not None:
        move = policy._step_toward(snapshot, step)
        if move is not None:
            policy.last_reason = f"{family}:seek-upstairs"
            return move
    mapped = area_mapping.deep_climb_key(policy, snapshot)
    if mapped is not None:
        return mapped
    goal = policy._town_producer_entry("_explore_step", lambda: policy._explore_step(snapshot))
    if goal is None:
        return None
    move = policy._step_toward(snapshot, goal)
    if move is not None:
        policy.last_reason = f"{family}:search-upstairs"
    return move


# --- an arrival at 50F+ by a descent without the means: the climb, else the named stop -------

def _hold_climb(policy, snapshot, dungeon_id: int) -> bool:
    """Hold the climb switch on ``dungeon_id`` (the Castle or the Mountain) whose band the kit
    reaches, as the unsafe-recall fallback's Castle climb holds it (policy
    ._activate_safe_recall_fallback with dive_floor.pick_refused); False where none can be held."""
    from hengbot import dive_floor

    if dive_floor.climb_dungeon(policy) == dungeon_id:
        return True
    if (dungeon_id not in dive_floor.DIVE_FLOOR_DUNGEONS
            or not dive_floor.reaches_band(policy, snapshot, dungeon_id)):
        return False
    policy._alternate_dungeon = dungeon_id
    policy._alternate_dungeon_reason = dive_floor.SAFE_FALLBACK_REASON
    dive_floor.bind_refused(policy, snapshot, dungeon_id)
    policy._target_dungeon_id = dungeon_id
    policy._target_dungeon_reason = dive_floor.SAFE_FALLBACK_REASON
    policy._conquest_committed = None
    return dive_floor.climb_dungeon(policy) == dungeon_id


def _standing_without_means(policy, snapshot, floor_key) -> bool:
    """A 50F+ floor, no quest floor, without the *Destruction* means and no climb held there:
    the climb is held where it can be (``_hold_climb``: the Castle or the Mountain; Angband has
    none and its means-spent return leaves the floor, destruction_use.means_spent)."""
    from hengbot import destruction_use, dive_floor

    return (len(floor_key) == 3 and not snapshot.in_town
            and not deep_admission.verdict(
                floor_key[0], floor_key[1], "quest" if floor_key[2] != 0 else "stand",
                lambda: destruction_use.holds_means(policy, snapshot),
                lambda: dive_floor.climb_dungeon(policy) == floor_key[0]).admitted)


def observe(policy, snapshot) -> None:
    """Every board: a new floor of 50F or deeper entered from a shallower floor of the same
    dungeon, with no *Destruction* means and no quest, holds the climb (``_hold_climb``, owner
    2026-11-23 「登りと同じにすぐ45F以浅へ登る」), else is remembered for ``stop_key``.  A
    shallower 50F+ floor counts too: n1-a life-531 2026-11-22 08:04, on the Castle's 50F climb,
    fell through two trap doors (50F -> 52F -> 54F); the Castle's recall depth became 54 and
    the climb's landing was lost.  A floor deeper than the last one is a new descent too."""
    from hengbot import deep_fall_guard, destruction_use

    floor_key = tuple(getattr(snapshot, "floor_key", ()) or ())
    record = getattr(policy, MEMORY, None)
    previous = record[0] if record else None
    stopped = record[1] if record else None
    if _standing_without_means(policy, snapshot, floor_key):
        # Standing there is enough, whatever the board before (the first board after a restart
        # has no previous floor: n1-a life-535 is resumed on the Castle's 50F).
        _hold_climb(policy, snapshot, floor_key[0])
    if previous == floor_key:
        return
    if (previous is not None and floor_key and not snapshot.in_town
            and previous[0] == floor_key[0] and 0 < previous[1] < floor_key[1]
            and not deep_admission.verdict(
                floor_key[0], floor_key[1],
                "quest" if floor_key[2] != 0 or previous[2] != 0 else "trapdoor",
                lambda: destruction_use.holds_means(policy, snapshot),
                lambda: deep_fall_guard.climbing(policy, floor_key[0])).admitted):
        stopped = None if _hold_climb(policy, snapshot, floor_key[0]) else floor_key
    elif not (stopped is not None and stopped == floor_key):
        stopped = None
    setattr(policy, MEMORY, (floor_key, stopped))


def stop_key(policy, snapshot):
    """The named stop of an unadmitted 50F+ arrival no climb can be held for (``observe``)."""
    record = getattr(policy, MEMORY, None)
    if not record or record[1] is None or record[1] != tuple(snapshot.floor_key):
        return None
    policy.last_reason = STOP_REASON
    return WAIT_KEY
