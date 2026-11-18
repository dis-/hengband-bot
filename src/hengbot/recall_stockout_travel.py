"""Word of Recall out of stock in this town: buy it in another town (owner 2026-11-17).

Owner 2026-11-17, verbatim: 「他の町に買いに行く。」 (n1-c life-216, 2,566,788 gold, went
mining at 15:04 with ``town:recall-stockout-mining`` because the Outpost's Temple and
Alchemist had no Word of Recall).  It replaces the decision of 2026-09-13
「帰還の巻物が品切れなら採掘して待つ。他の街までいかない。」: the one-run time-pass
(``_start_unobtainable_recall_stockout_mining``, ``_recall_restock_key``) is now the
fallback once no other town is left to try.  Owner 2026-11-17 「念のため。すべての町に
ズルは含まない。」: Zul is never a candidate (``CROSS_TOWN_TOWN_IDS``).

The circuit is the cross-town shopping expedition the other supplies already use
(``CrossTownShoppingExpedition`` in ``_cross_town_shopping``, travelled by
``_cross_town_shopping_key`` through the inn, ``_town_teleport_key``) with Word of
Recall as its blocking category.  ``start`` installs it, or continues it, where the
time-pass used to start:

* the towns are the visited inn towns other than this one, cheapest fare first
  (``_cross_town_candidate_order``; no town's shelf is known before it is visited);
* the funds are the ordinary expedition's: the scrolls short at the remembered price
  (``_observed_departure_prices``) and its reserve (``CROSS_TOWN_SHOPPING_RESERVE``),
  plus the next leg's inn fare;
* in each town the ordinary owners buy (the recall purchase rules, the departure
  reserve); the town's own stock-out, judged as the time-pass judges it
  (``_recall_stockout_persists``), sends the circuit on to the next town;
* with no town left (every town tried, none visited, or the fare not covered) the
  circuit ends and the time-pass runs as before.  ``_cross_town_shopping_funds`` keeps
  why (``fallback``) and the towns tried, for the decision log.

The character departs from the town it bought the scrolls in (the departure clears the
expedition, as for every other cross-town supply).
"""
from __future__ import annotations

from math import ceil
from typing import Any

from hengbot.model import SV_SCROLL_WORD_OF_RECALL, TVAL_SCROLL
from hengbot.policy_constants import CROSS_TOWN_SHOPPING_RESERVE, TOWN_TELEPORT_COST
from hengbot.policy_types import CrossTownShoppingExpedition

CATEGORY = "recall"
# The reason of the store page that leaves for the circuit (the time-pass's page reason
# was ``town:recall-stockout-mining``); the legs are ``town:cross-town-shopping:travel-N``.
LEAVE_REASON = "town:cross-town-recall-stockout"
FALLBACK = "recall-stockout-mining"


def fare(town_id: int) -> int:
    """The inn's fare to ``town_id`` (_town_teleport_dispatch_key)."""
    return TOWN_TELEPORT_COST if town_id == 0 else 2 * TOWN_TELEPORT_COST


def circuit(policy: Any) -> CrossTownShoppingExpedition | None:
    """The expedition when Word of Recall is what it travels for."""
    expedition = getattr(policy, "_cross_town_shopping", None)
    if expedition is None or CATEGORY not in expedition.blocking_categories:
        return None
    return expedition


def leg_chosen_here(policy: Any, snapshot: Any) -> bool:
    """This town's stock-out already sent the circuit on: its inn leg is chosen.

    The page that judged the stock-out left the store and the first board outside
    chose the leg (``target_town_id``, cleared on the arrival).  The town's other
    store pages until then are its own errands (the leg waits for the visit's
    errand holder, ``_cross_town_shopping_key``): judging the stock-out again
    there left every errand store unserved and walked back to the inn for ever
    (n1-b life-411, 2026-11-18 07:50, the Outpost's Weapon Smiths and Black Market).
    """
    expedition = circuit(policy)
    return (expedition is not None and expedition.target_town_id is not None
            and expedition.target_town_id != policy._effective_town_id(snapshot))


def _remaining(policy: Any, snapshot: Any,
               expedition: CrossTownShoppingExpedition) -> tuple[int, ...]:
    current = policy._effective_town_id(snapshot)
    return tuple(town for town in expedition.candidate_order
                 if town not in expedition.tried_towns and town != current)


def _shortage_cost(policy: Any, snapshot: Any) -> int:
    """The scrolls short for departure at the cheapest remembered price."""
    with policy._outside_fundraising():
        recall = policy._supply_ledger(snapshot, policy._planned_depth())[CATEGORY]
    missing = max(1, recall.required_departure - recall.count)
    observed = policy._observed_departure_prices.get(CATEGORY)
    if observed is None:
        base = policy._baseitem_costs.get((TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL), 0)
        observed = (base, 1) if base > 0 else None
    if observed is None:
        return 0
    price, units = observed
    return ceil(missing / units) * price


def start(policy: Any, snapshot: Any) -> bool:
    """Where the stock-out time-pass would start: True when a town is left to try.

    The circuit is installed (or continued, this town counted as tried); False ends it
    and records why the time-pass runs instead.
    """
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
    remaining = _remaining(policy, snapshot, expedition)
    why = None
    if not expedition.candidate_order:
        why = "no-candidate-town"
    elif not remaining:
        why = "all-towns-tried"
    elif snapshot.player.gold < expedition.required_gold + fare(remaining[0]):
        why = "funds"
    record = {
        "trigger_town_id": expedition.trigger_town_id,
        "blocking_categories": [CATEGORY],
        "shortage_costs": dict(expedition.shortage_costs),
        "reserve": expedition.reserve,
        "required_gold": expedition.required_gold,
        "gold": snapshot.player.gold,
        "candidate_order": list(expedition.candidate_order),
        "tried_towns": list(expedition.tried_towns),
    }
    if why is not None:
        policy._cross_town_shopping = None
        policy._cross_town_shopping_funds = {**record, "fallback": FALLBACK, "why": why}
        return False
    policy._cross_town_shopping = expedition
    policy._cross_town_shopping_funds = record
    return True
