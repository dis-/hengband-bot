"""Sell one Treasure Detection scroll to buy oil for a mining set.

Owner 2026-11-06: 「それでもお金がなければ、財宝感知の巻物を1本売って油を買います」.
n1-b life-315 came back from a mining run with 1 gold, no oil, an empty lantern and
7 scrolls; oil was 5 gold, so the visit could only wait until the stop
town:blocked:survival:recall_departure_ready.

The sale serves only an identified lantern that needs oil.  A torch takes no oil
(src/cmd-item/cmd-refill.cpp), a fuel-less light needs none, a working light has no
need yet, and an unidentified lantern shows no fuel to say it needs any.  One scroll
per town visit; the set keeps the scrolls its remaining runs read.  No sale price is
exported for pack items, so the sale is not predicted: if the proceeds still do not
buy oil the visit goes on as it would have without this module.
"""
from hengbot.model import STORE_ALCHEMIST, STORE_GENERAL, SV_LITE_LANTERN, lights_nothing
from hengbot.policy_constants import LANTERN_DIM_WARNING_FUEL

_MINING_MODES = frozenset({"prepare", "mine", "scavenge"})


def _light_needs_oil(policy, snapshot):
    # A dark light (★火消しライター) lights nothing: it neither needs oil nor lights the way.
    lights = [item for item in (*snapshot.inventory, *snapshot.equipment)
              if item.is_light and not lights_nothing(item)]
    return (
        any(item.is_lantern for item in lights)
        and all(item.sval <= SV_LITE_LANTERN and item.known
                and item.fuel < LANTERN_DIM_WARNING_FUEL for item in lights)
        and policy._count_oil(snapshot) == 0
    )


def _oil_unaffordable(policy, snapshot):
    """The General Store's shelf, seen in this town, sells oil above the purse."""
    page = policy._town_supplier_stock.get(STORE_GENERAL)
    seen = policy._town_supplier_stock_observations.get(STORE_GENERAL)
    if page is None or seen is None or seen[0] != policy._effective_town_id(snapshot):
        return False
    prices = [item.price for item in page.items if item.is_oil]
    return bool(prices) and min(prices) > snapshot.player.gold


def _sold_this_visit(policy):
    record = policy.__dict__.get("_mining_oil_sale")
    return (record is not None and record["sold"]
            and record["epoch"] == policy._town_visit_epoch)


def scroll_to_sell(policy, snapshot):
    """The scroll stack to sell one of, while the owner's condition holds."""
    if (policy._fundraising_mode not in _MINING_MODES
            or _sold_this_visit(policy)
            or STORE_ALCHEMIST in policy._store_sale_refused
            or not _light_needs_oil(policy, snapshot)
            or not _oil_unaffordable(policy, snapshot)
            or any(item.is_oil for item in policy._home_knowledge_items)):
        return None
    scroll = next((item for item in snapshot.inventory
                   if item.is_treasure_detection_scroll and item.known), None)
    if (scroll is None
            or policy._item_signature(scroll) in policy._unsellable_items
            or policy._count_treasure_detection_scrolls(snapshot) - 1
            < policy._mining_detection_scroll_target(snapshot)):
        return None
    return scroll


def sale_candidates(policy, snapshot):
    """The Alchemist's page offers the scroll to the ordinary sale path."""
    if snapshot.store is None or snapshot.store.store_type != STORE_ALCHEMIST:
        return []
    scroll = scroll_to_sell(policy, snapshot)
    return [] if scroll is None else [scroll]


def kept_scrolls(policy, snapshot, item, target):
    """The retention of ``item``: one scroll is released on the Alchemist's page only."""
    if sale_candidates(policy, snapshot):
        return item.count - 1
    return target


def observe_shop_page(policy, snapshot):
    """Open the sale on a shop page, and hand a finished sale to the General Store."""
    record = policy.__dict__.get("_mining_oil_sale")
    if record is None or record["epoch"] != policy._town_visit_epoch:
        if scroll_to_sell(policy, snapshot) is None:
            return
        policy._mining_oil_sale = {
            "epoch": policy._town_visit_epoch,
            "scrolls": policy._count_treasure_detection_scrolls(snapshot),
            "sold": False,
        }
        policy._rearm_town_store_for_new_work(STORE_ALCHEMIST, release_visit_bound=True)
    elif (not record["sold"]
          and policy._count_treasure_detection_scrolls(snapshot) < record["scrolls"]):
        record["sold"] = True
        policy._rearm_town_store_for_new_work(STORE_GENERAL, release_visit_bound=True)
