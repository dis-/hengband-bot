"""The Black Market's Staff of *Destruction*, funded by Home's spare gear.

Owner 2026-11-07: 「BMの買い物優先度について。*破壊*の杖の優先度を上げる。自宅にある
アーティファクトでない予備の武器と予備の胴防具を売って購入可能なら購入する。このとき
優先度2-10位の非アーティファクトにも例外で手を付ける。」  Asked when it buys: 「何本でも
買う」 -- whenever the Black Market shelves one, even with one carried, as the top of
the Black Market's optional picks (``_black_market_optional_purchase``).

When the optional reserve (owner 2026-10-08 「必需品1回分の補充代を残す」) leaves the
staff out of reach, Home's spare melee weapons, launchers and body armour pay for it: the
existing junk sweep (item_fate.sweep_ware, the full-Home relief's take and sale)
takes them out and sells them one at a time, rank 21+ first, then 11-20, then
10..2, cheapest first within a rank.  Rank 1 of each slot stays, artifacts and
unidentified pieces are unranked and stay, and the optimizer's chosen pieces are
not spare (spare_gear.released, asked by ``_home_full_sale_candidate``).  If
even every eligible piece cannot cover the shortfall, nothing is sold.  Once the
gold covers it, the finished Black Market stop reopens once for the purchase.

The exception lives here and only here: ``releases`` is asked by
item_fate.gear_tier, so no other disposal path widens.
"""
from __future__ import annotations

from typing import Any

from hengbot import item_fate
from hengbot.item_reservation import decision_memo
from hengbot.model import STORE_BLACK

# 「予備の武器と予備の胴防具」: item_fate's melee and body slots; 2026-11-07
# 「射撃武器も入れる」: and launchers (bows, crossbows, slings).  Diggers stay.
FUND_SLOTS = frozenset({"melee", "launcher", "body"})
# store/store-owners.cpp: every non-Black-Market owner's purse limit (max_cost).
STORE_PURSE_LIMIT = 30000
# store/pricing.cpp calc_store_price (PLAYER_SELLS): value * min(400 - markup,
# 100)% then -10%.  The markup (owner greed + race pairing + CHR) is not
# observable before the sale; 50% stays under the usual 60-90% so the plan
# never counts gold a sale will not bring.  Each sale's real gold re-plans.
SALE_ESTIMATE_PERCENT = 50


def _shelf(policy: Any, snapshot: Any) -> dict | None:
    shelf = getattr(policy, "_bm_destruction_shelf", None)
    if (shelf is None or not snapshot.in_town
            or shelf["town"] != policy._effective_town_id(snapshot)
            or shelf["epoch"] != policy._town_visit_epoch):
        return None
    return shelf


def shortfall(policy: Any, snapshot: Any) -> int | None:
    """Gold still missing for the observed staff under the optional reserve.

    None without an observed staff this town stay, while a required
    remove-curse purchase holds the optional picks, or with an unknown reserve.
    """
    shelf = _shelf(policy, snapshot)
    if shelf is None or policy._required_remove_curse_kind(snapshot) is not None:
        return None
    reserve = policy._full_departure_resupply_reserve(snapshot)
    if reserve is None:
        return None
    fare = policy._outpost_return_fare(snapshot) or 0
    return shelf["price"] + max(reserve, fare) - snapshot.player.gold


def sale_estimate(policy: Any, item: Any) -> int:
    per_item = min(STORE_PURSE_LIMIT,
                   item_fate.sale_value(policy, item) * SALE_ESTIMATE_PERCENT // 100)
    return per_item * max(1, item.count)


def plan(policy: Any, snapshot: Any) -> tuple:
    """Signatures of the Home spares to sell, in sale order; () for none.

    Empty when the gold already covers the staff, without a current Home
    census, or when every eligible piece together cannot cover the shortfall.
    """
    if (getattr(policy, "_bm_fund_planning", False)
            or getattr(policy, "_bm_destruction_shelf", None) is None):
        return ()
    # Whatever the reserve and the candidates ask of the ranking meanwhile
    # sees no exception but the probed piece (``releases``).
    policy._bm_fund_planning = True
    try:
        short = shortfall(policy, snapshot)
    finally:
        policy._bm_fund_planning = False
    if short is None or short <= 0 or not policy._home_knowledge_current:
        return ()
    return decision_memo(policy, "bm-destruction-fund", snapshot, short,
                         lambda: _plan(policy, snapshot, short))


def _plan(policy: Any, snapshot: Any, short: int) -> tuple:
    rows = []
    policy._bm_fund_planning = True
    try:
        for item in policy._home_knowledge_items:
            if (item_fate.SLOT_BY_TVAL.get(item.tval) not in FUND_SLOTS
                    or item.is_artifact or not item.known):
                continue
            rank = item_fate.gear_rank(policy, snapshot, item)
            if rank is None or rank < 2:
                continue
            signature = policy._item_signature(item)
            policy._bm_fund_probe = signature
            result = policy._home_full_sale_candidate(snapshot, item)
            if result is None:
                continue
            rows.append((-rank, item_fate.sale_value(policy, result[0]), signature,
                         sale_estimate(policy, result[0])))
    finally:
        policy._bm_fund_probe = None
        policy._bm_fund_planning = False
    chosen, total = [], 0
    for _rank, _value, signature, estimate in sorted(rows):
        if total >= short:
            break
        chosen.append(signature)
        total += estimate
    return tuple(chosen) if total >= short else ()


def releases(policy: Any, snapshot: Any, item: Any) -> bool:
    """The owner's exception to the ranking: this piece may be sold (rank 2+)."""
    if getattr(policy, "_bm_destruction_shelf", None) is None:
        return False
    signature = policy._item_signature(item)
    if getattr(policy, "_bm_fund_planning", False):
        return getattr(policy, "_bm_fund_probe", None) == signature
    relief = getattr(policy, "_home_full_relief", None)
    if relief is not None and relief.get("fund") == signature:
        return True
    return signature in plan(policy, snapshot)


def funding(policy: Any, snapshot: Any) -> bool:
    """A fund sale is due: the sweep runs past its per-stay bound for it."""
    return (getattr(policy, "_bm_fund_sweep_ended", None) != policy._town_visit_epoch
            and bool(plan(policy, snapshot)))


def census_wanted(policy: Any, snapshot: Any) -> bool:
    """The staff is short and the fund has no current Home census to read.

    Asked outside; one request per stay and gold amount (a sale changes it).
    """
    if (snapshot.store is not None or policy._home_knowledge_current
            or getattr(policy, "_bm_fund_sweep_ended", None) == policy._town_visit_epoch
            or getattr(policy, "_bm_fund_census", None) == _census_mark(policy, snapshot)
            or not policy._home_available(snapshot)):
        return False
    short = shortfall(policy, snapshot)
    return short is not None and short > 0


def _census_mark(policy: Any, snapshot: Any) -> tuple:
    return (policy._town_visit_epoch, snapshot.player.gold)


def census_requested(policy: Any, snapshot: Any) -> None:
    policy._bm_fund_census = _census_mark(policy, snapshot)


def _black_market_finished(policy: Any) -> bool:
    plan = getattr(policy, "_town_errand_plan", None)
    return (STORE_BLACK in policy._town_store_attempted
            or (plan is not None and STORE_BLACK in plan.completed_this_visit))


def observe(policy: Any, snapshot: Any) -> None:
    """Remember the shelved staff; reopen the finished Black Market stop once
    the sales have covered it."""
    store = snapshot.store
    shelf = getattr(policy, "_bm_destruction_shelf", None)
    if store is not None and store.store_type == STORE_BLACK:
        staffs = [item for item in store.items
                  if policy._is_destruction_staff(item) and item.count > 0 and item.price > 0]
        if not staffs:
            if shelf is not None and (shelf.get("page_top") == store.page_top
                                      or store.stock_num == len(store.items)):
                policy._bm_destruction_shelf = None
            return
        ware = min(staffs, key=lambda item: item.price)
        mark = (policy._effective_town_id(snapshot), policy._town_visit_epoch,
                ware.price, sum(item.count for item in staffs))
        same = shelf is not None and shelf.get("mark") == mark
        policy._bm_destruction_shelf = {
            "town": mark[0], "epoch": mark[1], "price": ware.price,
            "page_top": store.page_top, "mark": mark,
            "rearmed": bool(shelf.get("rearmed")) if same else False,
        }
        short = shortfall(policy, snapshot)
        if short is not None and short <= 0:
            # This visit is the chance to buy: no reopening for it.
            policy._bm_destruction_shelf["rearmed"] = True
        return
    if (store is None and shelf is not None and not shelf.get("rearmed")
            and _black_market_finished(policy)):
        short = shortfall(policy, snapshot)
        if short is not None and short <= 0:
            shelf["rearmed"] = True
            policy._rearm_town_store_for_new_work(STORE_BLACK)
