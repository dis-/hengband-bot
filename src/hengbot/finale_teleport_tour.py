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
* the character departs from the town where the plan's 40 are owned, or from the last town tried.
"""
from __future__ import annotations

from math import ceil
from typing import Any

from hengbot import angband_finale
from hengbot.model import STORE_ALCHEMIST, STORE_GENERAL
from hengbot.policy_constants import CROSS_TOWN_SHOPPING_RESERVE
from hengbot.policy_types import CrossTownShoppingExpedition
from hengbot.recall_stockout_travel import fare

CATEGORY = "teleport"  # the expedition's category (policy_town _cross_town_shortages)
STATE = "_finale_teleport_tour"  # True while the expedition is this circuit's
FALLBACK = "depart"
SUPPLIERS = (STORE_ALCHEMIST, STORE_GENERAL)  # angband_finale's errand stores


def circuit(policy: Any) -> CrossTownShoppingExpedition | None:
    """The expedition when it travels for the finale's Teleportation."""
    expedition = getattr(policy, "_cross_town_shopping", None)
    if (expedition is None or not getattr(policy, STATE, False)
            or CATEGORY not in expedition.blocking_categories):
        return None
    return expedition


def shortage(policy: Any, snapshot: Any) -> int:
    """The plan's Teleportation still to buy (40 less the pack's and the Home's)."""
    return angband_finale.shortage(policy, snapshot, angband_finale.TELEPORT)


def due(policy: Any, snapshot: Any) -> bool:
    """Short after this town's suppliers, no other expedition under way, not ended this trip."""
    if not snapshot.in_town or shortage(policy, snapshot) <= 0:
        return False
    if angband_finale.memory(policy).teleport_tour_done:
        return False
    if getattr(policy, "_cross_town_shopping", None) is not None and circuit(policy) is None:
        return False
    attempted = getattr(policy, "_town_store_attempted", {})
    return all(store in attempted for store in SUPPLIERS)


def _shortage_cost(policy: Any, snapshot: Any) -> int:
    """The scrolls short at the cheapest remembered price (the expedition's funds rule)."""
    observed = policy._observed_departure_prices.get(CATEGORY)
    if observed is None:
        base = policy._baseitem_costs.get(angband_finale.TELEPORT, 0)
        observed = (base, 1) if base > 0 else None
    if observed is None:
        return 0
    price, units = observed
    return ceil(shortage(policy, snapshot) / units) * price


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
        cost = _shortage_cost(policy, snapshot)
        expedition = CrossTownShoppingExpedition(
            trigger_town_id=current,
            blocking_categories=(CATEGORY,),
            shortage_costs={CATEGORY: cost},
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
        "blocking_categories": [CATEGORY],
        "shortage": shortage(policy, snapshot),
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
        return _end(policy, record, "all-towns-tried")
    if snapshot.player.gold < expedition.required_gold + fare(remaining[0]):
        return _end(policy, record, "funds")
    policy._cross_town_shopping = expedition
    setattr(policy, STATE, True)
    policy._cross_town_shopping_funds = record
    return True
