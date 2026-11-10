"""A mining set's survival shortfall, bought from the gold its kit leaves.

Owner 2026-11-03 「道具の後に足りない分を買う」: in a mining set the kit
comes first (11-02 「採掘の要求品が優先」); the remaining gold then buys the
departure-survival shortfall, as much as it pays for, and the set still
leaves.  The town planner filed that shortfall
(``policy_town.add_ledger_shortages``) but the store's fundraising order
bought only the kit, the recall and a restore potion:

* n1-a life-507 (2026-11-10 08:40): the Alchemist sold テレポートの巻物 x66 at
  61 gold, 3,827 gold carried, teleport 12/15.  The order bought the
  detection and one recall; the in-store dry run then judged the shelf
  without a teleport, the planner dropped the stop and the visit stopped on
  town:blocked:survival:teleport_ready.
* n1-b life-364 (2026-11-10 10:21, Lv7 Magic-Eater): one food charge short
  (14/15, with a carried edible staff), the order's food rung came before
  every survival item and bought a 1,177-gold スリープ・モンスターの魔法棒,
  leaving 78 gold and no teleport, Cure Critical Wounds or recall; the visit
  stopped on town:blocked:survival:recall_departure_ready.

The order of the shortfall is recall, teleport, Cure Critical Wounds, then
the food above the set's departure food (the set leaves on any edible food,
``_departure_food_ready``).  Each item is bought only from the gold left after
the kit's reserve (``_fundraising_kit_reserve``) and the price of every
earlier item still short, so a cheaper item never spends the money an
earlier one needs at another store.
"""
from __future__ import annotations

from math import ceil

from hengbot.model import (
    SV_POTION_CURE_CRITICAL,
    SV_SCROLL_TELEPORT,
    SV_SCROLL_WORD_OF_RECALL,
    TVAL_POTION,
    TVAL_SCROLL,
)

MINING_MODES = frozenset({"prepare", "mine", "scavenge"})
# The survival shortfall of a mining set, first to last.
ORDER = ("recall", "teleport", "cure", "food")
_PRICE_CATEGORY = {"cure": "cure-critical"}
_BASE_KINDS = {
    "recall": ((TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),),
    "teleport": ((TVAL_SCROLL, SV_SCROLL_TELEPORT),),
    "cure": ((TVAL_POTION, SV_POTION_CURE_CRITICAL),),
}


def active(policy) -> bool:
    """Whether the store order is a mining set's."""
    return policy._fundraising_mode in MINING_MODES


def _unit_price(policy, kind: str) -> int | None:
    """One unit's price: the shelf price seen in town, else the base cost."""
    known = getattr(policy, "_observed_departure_prices", {}).get(
        _PRICE_CATEGORY.get(kind, kind))
    if known is not None:
        price, units = known
        return ceil(price / max(1, units))
    costs = getattr(policy, "_baseitem_costs", {})
    prices = [costs[base] for base in _BASE_KINDS.get(kind, ()) if costs.get(base, 0) > 0]
    return min(prices) if prices else None


def _missing(policy, snapshot, kind: str, *, for_kind: str) -> int:
    status = policy._supply_ledger(snapshot, policy._planned_depth())[kind]
    required = status.required_departure
    if (kind == "recall" and for_kind == "food"
            and policy._fundraising_mode in {"mine", "scavenge"}):
        # A mine or scavenge set needs no recall to leave
        # (``_recall_required_target``), but the visit that ends the set
        # departs under the ordinary recall gate.  n1-b life-364: the set
        # spent its gold on food in scavenge mode and the next departure
        # stopped on recall_departure_ready (0/3).  Only the optional food
        # holds this money back; teleport and Cure are bought before it.
        required = max(required, policy._recall_target(policy._planned_depth()))
    return max(0, required - status.count)


def budget(policy, snapshot, kind: str) -> int:
    """The gold ``kind`` may spend: carried gold less the kit's reserve and
    the price of every earlier survival item still short.

    An earlier item of unknown price holds back all the gold (nothing of a
    later kind is bought before the earlier one's price is known)."""
    reserve = policy._fundraising_kit_reserve(snapshot)
    for earlier in ORDER[:ORDER.index(kind)]:
        missing = _missing(policy, snapshot, earlier, for_kind=kind)
        if not missing:
            continue
        price = _unit_price(policy, earlier)
        if price is None:
            return 0
        reserve += missing * price
    return snapshot.player.gold - reserve


def affordable(policy, snapshot, kind: str, item) -> bool:
    """Whether buying ``item`` for ``kind`` (the selector's whole quantity)
    stays within ``kind``'s budget."""
    quantity = max(1, policy._purchase_quantity(snapshot, item))
    return item.price * quantity <= budget(policy, snapshot, kind)

