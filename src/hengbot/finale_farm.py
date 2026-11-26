"""The finale's Black Market supplies farmed over several floors a trip, not one (owner 2026-11-26).

Owner 2026-11-26 (verbatim): 「n1-cはこのままゾンビ魔道具術師で勝率と時間効率改善を進める。…いずれも、
ゲーム内選択に関して私の以前の指示を破ることを許可する。」.  The rule this changes: owner 2026-11-17
(the 50F+ efficiency study's 第1位) 「適当な閾値を決めて、探索が済んだら帰還する。」 -- an explored
floor the dive goes no deeper from is left by Word of Recall (explored_floor ``recall_key``).

n1-c life-222 (Magic-Eater Lv50, the 95F exploration, 2026-11-26 10:05-12:58): after its third 100F
attempt the Restore Mana owned was 21-23 of the carry 46 (then 40 and 38 as more rockets were
absorbed: restore_mana_target), a supply only the Black Market sells (store/articles-on-sale.cpp
stocks none; BaseitemDefinitions id 266, cost 3,000, shelved at 34,697-37,332 gold).  Each town
visit sold the trip's loot and bought one or two (purchase-source.jsonl: 19 bought in those three
hours), so the gold of the trips was the bound, and the trips were one 95F floor each: 50 trips in
2 h 53 min (3.4 min a trip, about a minute of it in town), 17 of them ended by
``explored-dead-end-floor`` with 6 to 12 of the 23 pack slots still free, 6 by ``pack-full``.
The town's half of each trip bought nothing the next floor would not have paid for as well.

While the finale is prepared at the 95F cap (angband_finale ``preparing``, the cap not lifted) and a
supply only the Black Market sells is still short (finale_bm_tour ``shortage``: the gold or the
potions themselves are what the trip brings back), an explored dead-end floor of Angband is left by
its stairs instead (``key``): the up stairs of 95F (its stair down is refused at the cap) to a new
94F and the dive's stairs down to a new 95F, ``FARM_STAIR_FLOORS`` times a trip.  The trip's other
returns are untouched (``pack-full``, the supplies, every survival and escape rule come before the
explore this replaces), and the Word of Recall comes back as before once the trip has left that
many explored floors by the stairs, or when no stair is known (``key`` None: explored_floor reads
the Recall).

``FARM_STAIR_FLOORS`` = 2 (three explored dead-end floors a trip at most): the explored-floor
returns of the record above left 6-12 slots free after one floor whose loot had taken about as
many, so a second floor fills most packs and the ``pack-full`` return ends the trip; a third is the
bound for a pack the loot does not fill (the gold is sold only in town, so an unbounded trip would
bring none back).

State: ``FLOORS`` (``_finale_farm_floors``, the explored floors this trip left by the stairs; a
town board clears it, angband_finale ``observe``) and ``COUNTED`` (``_finale_farm_floor``, this floor
visit is counted; floor_visit_memory forgets it on the floor change).  A restart loses both: the
new process counts the trip's floors again from none (at most ``FARM_STAIR_FLOORS`` more).
"""
from __future__ import annotations

from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy_constants import UP_STAIRS_KEY

FARM_STAIR_FLOORS = 2
FLOORS = "_finale_farm_floors"
COUNTED = "_finale_farm_floor"
REASON = "finale-farm:seek-stairs"
ASCEND_REASON = "finale-farm:ascend"


def farming(policy, snapshot) -> bool:
    """An Angband floor of the 95F exploration while a finale supply only the Black Market sells is
    short (angband_finale ``preparing``, not ``lifted``; finale_bm_tour ``shortage``)."""
    from hengbot import angband_finale, finale_bm_tour  # import cycle
    return bool(not snapshot.in_town and snapshot.floor_key[0] == DUNGEON_ANGBAND
                and angband_finale.preparing(snapshot) and not angband_finale.lifted(policy)
                and finale_bm_tour.shortage(policy, snapshot) > 0)


def floors(policy) -> int:
    return int(getattr(policy, FLOORS, 0) or 0)


def forget_trip(policy) -> None:
    """A town board: the next trip counts its floors from none."""
    setattr(policy, FLOORS, 0)


def due(policy, snapshot) -> bool:
    """This explored dead-end floor is left by its stairs: farming, and this floor is counted or
    the trip has left fewer than FARM_STAIR_FLOORS so."""
    if not farming(policy, snapshot):
        return False
    return bool(getattr(policy, COUNTED, None)) or floors(policy) < FARM_STAIR_FLOORS


def key(policy, snapshot) -> str | None:
    """explored_floor ``recall_key``'s replacement on a farming floor (``due``): the stair underfoot,
    else the walk to the nearest stair the ladder would take (an up stair, or a stair down the
    descent admits); None when no stair is known (the Recall is read as before)."""
    if not due(policy, snapshot) or policy._floor_navigation_exit_locked(snapshot):
        return None
    here = snapshot.grid_at(snapshot.player.position)
    allow_descent = not policy._descent_is_blocked(snapshot)

    def stair(grid) -> bool:
        return (policy._is_upstairs_target(grid)
                or (allow_descent and policy._is_descent_target(snapshot, grid)))

    if here is not None and policy._is_upstairs_target(here):
        _count(policy)
        policy._defer_descent(snapshot)
        policy.last_reason = ASCEND_REASON
        return UP_STAIRS_KEY
    policy._claim_target_capture = []
    try:
        step = policy._nearest_goal_step(snapshot, stair)
    finally:
        step_target = policy._take_claim_target()
    if step is None:
        return None
    _count(policy)
    policy.last_reason = REASON
    policy._declare_reach(step_target)
    return policy._town_producer_entry(
        "_step_toward:finale-farm", lambda: policy._step_toward(snapshot, step), family="explore")


def _count(policy) -> None:
    if not getattr(policy, COUNTED, None):
        setattr(policy, COUNTED, True)
        setattr(policy, FLOORS, floors(policy) + 1)
