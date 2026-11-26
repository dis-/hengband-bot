"""The 99F/100F Teleportation scrolls bought in the other towns (owner 2026-11-20).

Owner 2026-11-20, verbatim: 「4つの街を回ってテレポートの巻物を買い足す処理をつけて」.  n1-c
life-217 (Magic-Eater, preparing the 99F/100F battle, angband_finale) owned 24 of the 40
Teleportation scrolls (none at Home) and its town's shops did not stock the rest.  The four towns
are the inn towns but Zul (owner 2026-11-17 「すべての町にズルは含まない」, CROSS_TOWN_TOWN_IDS).

The circuit is the cross-town shopping expedition the Word of Recall stock-out already takes
(recall_stockout_travel; ``CrossTownShoppingExpedition``, travelled by
``_cross_town_shopping_key`` through the inn), with Teleportation as its category and nothing of
its own rules changed:

* ``due``: the supply plan is short (angband_finale ``shortage``: 40 less the pack's and the Home's)
  and this town's suppliers of the plan (the Alchemist and the General Store, angband_finale's
  errand) were visited this visit, and no circuit of this kind ended on this trip;
* ``start`` (asked where the town's Word of Recall would be read): installs or continues the
  expedition as recall_stockout_travel does: the towns are the visited inn towns other than this
  one, cheapest fare first; the funds are the scrolls short at the remembered price, the
  expedition's reserve and the next leg's fare; with no town left (or the funds short) the
  circuit ends, this trip tries no more, and the town departs as before;
* while it runs, the expedition's Teleportation shortage is the plan's (``shortage``): the
  ordinary circuit holds a town while its suppliers are not yet seen empty and travels on once
  they are (policy_town ``_cross_town_shopping_hold`` / ``_cross_town_quest_hold``); the town's
  own purchase rung (``tail:angband-finale``) buys there;
* the character departs from the town where the plan's 40 are owned.

Owner 2026-11-20 (verbatim) 「一周する毎に宿屋で一泊する」: a loop that tried every town with the
scrolls still short is followed by a night at the inn of the town it ended in (``night_key``,
me_inn_refill's walk and stay: cmd-inn.cpp stay_inn, world.cpp pass_game_turn_by_stay moves the
game to the next half day, and each store restocks by the time passed when it is next entered,
store.cpp store_maintenance); then this town's suppliers are shopped again and the next loop
starts, until the 40 are owned.  Only the funds stop it (the expedition's rule), or an inn the
walk cannot reach.

Owner 2026-11-26 (verbatim) 「そろうまで出発しない（他の町も回る）」: the ten Scrolls of Recharging of a
race that eats device charges (angband_finale ``RECHARGING``, a readiness row) are the circuit's
too.  Only the Alchemist sells them (store/articles-on-sale.cpp, its regular stock of a few a
restock), so the circuit carries a second category, ``RECHARGING_CATEGORY``, supplied by the
Alchemist alone (policy_town ``_cross_town_supplier_types``): ``due`` when either supply is short
after its own suppliers were tried, the expedition blocks on the short ones, and each town's own
rungs (``tail:angband-finale``, ``tail:angband-finale-recharging``) buy there.
"""
from __future__ import annotations

from math import ceil
from typing import Any

from dataclasses import dataclass, field

from hengbot import angband_finale
from hengbot.me_inn_refill import InnRefillStay
from hengbot.model import STORE_ALCHEMIST, STORE_GENERAL
from hengbot.policy_constants import CROSS_TOWN_SHOPPING_RESERVE
from hengbot.policy_types import CrossTownShoppingExpedition
from hengbot.recall_stockout_travel import fare

CATEGORY = "teleport"  # the expedition's category (policy_town _cross_town_shortages)
RECHARGING_CATEGORY = "recharging"  # the Scrolls of Recharging's (owner 2026-11-26)
CATEGORIES = (CATEGORY, RECHARGING_CATEGORY)
RECHARGING_SUPPLIERS = (STORE_ALCHEMIST,)  # store/articles-on-sale.cpp: the Alchemist alone
STATE = "_finale_teleport_tour"  # True while the expedition is this circuit's
FALLBACK = "depart"
SUPPLIERS = (STORE_ALCHEMIST, STORE_GENERAL)  # angband_finale's errand stores
NIGHT = "_finale_teleport_tour_night"


@dataclass
class Night:
    """The night between two loops (owner 2026-11-20 「一周する毎に宿屋で一泊する」)."""
    due: bool = False
    stay: InnRefillStay = field(default_factory=InnRefillStay)
    nights: int = 0


def night(policy: Any) -> Night:
    held = getattr(policy, NIGHT, None)
    if held is None:
        held = Night()
        setattr(policy, NIGHT, held)
    return held


def forget_trip(policy: Any) -> None:
    """A dungeon board: the next town starts afresh."""
    # The circuit's expedition goes with it: left behind, it was an ordinary Teleportation
    # expedition the next visit, under way, so the circuit was never due again (n1-c
    # life-217 2026-11-21 03:49, a circuit started at 03:3x's recall read).
    if circuit(policy) is not None:
        policy._cross_town_shopping = None
    setattr(policy, STATE, False)
    setattr(policy, NIGHT, Night())


def circuit(policy: Any) -> CrossTownShoppingExpedition | None:
    """The expedition when it travels for the finale's Teleportation."""
    expedition = getattr(policy, "_cross_town_shopping", None)
    if (expedition is None or not getattr(policy, STATE, False)
            or not set(CATEGORIES) & set(expedition.blocking_categories)):
        return None
    return expedition


def shortage(policy: Any, snapshot: Any) -> int:
    """The plan's Teleportation still to buy (40 less the pack's and the Home's)."""
    return angband_finale.shortage(policy, snapshot, angband_finale.TELEPORT)


def recharging_shortage(policy: Any, snapshot: Any) -> int:
    """The Scrolls of Recharging still to buy (ten less the pack's and the Home's; 0 for a race
    that eats no device charges)."""
    return angband_finale.shortage(policy, snapshot, angband_finale.RECHARGING)


def shortages(policy: Any, snapshot: Any) -> dict:
    """{category: still to buy} of the circuit's short supplies."""
    found = {CATEGORY: shortage(policy, snapshot),
             RECHARGING_CATEGORY: recharging_shortage(policy, snapshot)}
    return {category: missing for category, missing in found.items() if missing > 0}


def _suppliers(category: str) -> tuple:
    return RECHARGING_SUPPLIERS if category == RECHARGING_CATEGORY else SUPPLIERS


def due(policy: Any, snapshot: Any) -> bool:
    """Short after this town's suppliers, no other expedition under way, not ended this trip."""
    short = shortages(policy, snapshot) if snapshot.in_town else {}
    if not short:
        return False
    if angband_finale.memory(policy).teleport_tour_done:
        return False
    if getattr(policy, "_cross_town_shopping", None) is not None and circuit(policy) is None:
        return False
    # Tried: entered, or its shelf seen without them since the last restock (the need
    # registry skips that stop, so it is never entered: policy_instore._shelf_stop_tried).
    return all(policy._shelf_stop_tried(snapshot, store, angband_finale.CATEGORY)
               for category in short for store in _suppliers(category))


def _category_cost(policy: Any, category: str, missing: int) -> int:
    """``missing`` of a category at the cheapest remembered price, else its base price."""
    observed = policy._observed_departure_prices.get(category)
    if observed is None:
        kind = angband_finale.RECHARGING if category == RECHARGING_CATEGORY else angband_finale.TELEPORT
        base = policy._baseitem_costs.get(kind, 0)
        if not base and category == RECHARGING_CATEGORY:
            base = angband_finale.RECHARGING_BASE_COST
        observed = (base, 1) if base > 0 else None
    if observed is None:
        return 0
    price, units = observed
    return ceil(missing / units) * price


def _shortage_costs(policy: Any, snapshot: Any) -> dict:
    """{category: the scrolls short at the cheapest remembered price} (the expedition's funds rule)."""
    return {category: _category_cost(policy, category, missing)
            for category, missing in shortages(policy, snapshot).items()}


def _end(policy: Any, record: dict, why: str) -> bool:
    policy._cross_town_shopping = None
    setattr(policy, STATE, False)
    angband_finale.memory(policy).teleport_tour_done = True
    policy._cross_town_shopping_funds = {**record, "fallback": FALLBACK, "why": why}
    return False


def start(policy: Any, snapshot: Any) -> bool:
    """Where the town's Word of Recall would be read: True when a town is left to try (the
    circuit installed or continued, this town counted as tried); False ends it."""
    current = policy._effective_town_id(snapshot)
    expedition = circuit(policy)
    if expedition is None:
        costs = _shortage_costs(policy, snapshot)
        cost = sum(costs.values())
        expedition = CrossTownShoppingExpedition(
            trigger_town_id=current,
            blocking_categories=tuple(costs) or (CATEGORY,),
            shortage_costs=costs or {CATEGORY: 0},
            reserve=CROSS_TOWN_SHOPPING_RESERVE,
            required_gold=cost + CROSS_TOWN_SHOPPING_RESERVE,
            candidate_order=policy._cross_town_candidate_order(snapshot),
        )
    if current not in expedition.tried_towns:
        expedition.tried_towns.append(current)
    expedition.target_town_id = None
    remaining = tuple(town for town in expedition.candidate_order
                      if town not in expedition.tried_towns and town != current)
    record = {
        "circuit": "angband-finale-teleport",
        "trigger_town_id": expedition.trigger_town_id,
        "blocking_categories": list(expedition.blocking_categories),
        "shortage": shortage(policy, snapshot),
        "recharging_shortage": recharging_shortage(policy, snapshot),
        "shortage_costs": dict(expedition.shortage_costs),
        "reserve": expedition.reserve,
        "required_gold": expedition.required_gold,
        "gold": snapshot.player.gold,
        "candidate_order": list(expedition.candidate_order),
        "tried_towns": list(expedition.tried_towns),
    }
    if not expedition.candidate_order:
        return _end(policy, record, "no-candidate-town")
    if not remaining:
        # Owner 2026-11-20 「一周する毎に宿屋で一泊する」: the loop is done, the night comes
        # before the next one (``night_key``).
        policy._cross_town_shopping = None
        setattr(policy, STATE, False)
        held = night(policy)
        held.due, held.stay = True, InnRefillStay()
        policy._cross_town_shopping_funds = {**record, "fallback": "inn-night", "why": "all-towns-tried"}
        return False
    if snapshot.player.gold < expedition.required_gold + fare(remaining[0]):
        return _end(policy, record, "funds")
    policy._cross_town_shopping = expedition
    setattr(policy, STATE, True)
    policy._cross_town_shopping_funds = record
    return True


def night_key(policy: Any, snapshot: Any) -> str | None:
    """The walk to this town's inn and its night after a loop, else None.  The board after the
    night clears this town's suppliers' visited marks, so they are shopped again (restocked) and
    the next loop can start; an inn the walk cannot reach ends the trip's tour."""
    from hengbot import me_inn_refill
    held = night(policy)
    if not held.due:
        return None
    if held.stay.posted_turn is not None:
        if snapshot.turn == held.stay.posted_turn:
            return None
        held.due, held.nights = False, held.nights + 1
        attempted = getattr(policy, "_town_store_attempted", {})
        for store in SUPPLIERS:
            attempted.pop(store, None)
        return None
    key = me_inn_refill._stay_key(
        policy, snapshot, me_inn_refill.DESTRUCTION_PRODUCER,
        me_inn_refill.FINALE_TELEPORT_APPROACH_REASON, me_inn_refill.FINALE_TELEPORT_REST_REASON,
        record=held.stay)
    if key is None:
        held.due = False
        angband_finale.memory(policy).teleport_tour_done = True
    return key
