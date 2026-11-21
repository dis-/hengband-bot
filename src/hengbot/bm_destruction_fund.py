"""The Black Market's Staff of *Destruction*, funded by Home's spare gear.

Owner 2026-11-07: 「BMの買い物優先度について。*破壊*の杖の優先度を上げる。自宅にある
アーティファクトでない予備の武器と予備の胴防具を売って購入可能なら購入する。このとき
優先度2-10位の非アーティファクトにも例外で手を付ける。」  Asked when it buys: 「何本でも
買う」 -- whenever the Black Market shelves one, even with one carried, as the top of
the Black Market's optional picks (``_black_market_optional_purchase``).
Owner 2026-11-15, restating it: 「破壊の杖は最優先で購入、所持金が足りなければ自宅の予備の
装備をアーティファクト以外全て売ってでも購入する。以前決めた通りである。」, then
「念のため確認するが、すべて売るのは武器と胴防具だけ」 and 「闇市で破壊の杖を見て所持金が
足りない→予備装備売却処理→購入→出発　がただしい。その訪問中に購入まで遂行する必要がある。」

When the optional reserve (owner 2026-10-08 「必需品1回分の補充代を残す」) leaves the
staff out of reach, Home's spare melee weapons, launchers and body armour pay for it: the
existing junk sweep (item_fate.sweep_ware, the full-Home relief's take and sale)
takes them out and sells them one at a time, rank 21+ first, then 11-20, then
10..1, cheapest first within a rank.  Every rank is in (11-15 「アーティファクト以外
全て」); artifacts and unidentified pieces are unranked and stay, and the optimizer's
chosen pieces are not spare (spare_gear.released, asked by ``_home_full_sale_candidate``,
which also honours every retention, reservation and named keep).  If even every
eligible piece cannot cover the shortfall, nothing is sold and the visit's
decision log says so (``UNAFFORDABLE_WARNING`` among its drift warnings).  Once
the gold covers it, the finished Black Market stop reopens once for the purchase.

From the shelf to the purchase the staff comes first (``staff_pending``): the Black
Market page buys nothing else and no Magic-Eater staff-sequence buy is chosen
(``page_purchase``), the class sequences that leave town wait (``holds_town_for_staff``),
and the departure leaf ``destruction_staff_settled`` holds the departure until
the staff is bought or its fund is out of options.  The town end drops that
leaf (town_terminal.gather_town_end), so it never stops a visit.

The exception lives here and only here: ``releases`` is asked by
item_fate.gear_tier, so no other disposal path widens.

Owner 2026-11-15 (n1-a life-525, a warrior whose only ESP was a crown of eight race
ESPs in the Home, held at 49F by the 50F telepathy requirement), verbatim: 「完全な
テレパシーを闇市で最優先で買う」, to be bought like the staff: when the gold is short,
Home's spare weapons and body armour are sold in the same visit.  ``PRIORITY_WARES`` is
the one table of the wares this errand buys; the staff is its first row, full telepathy
(TR_TELEPATHY, never the race ESP_* flags) its second, wanted only while the character
owns none (worn, intrinsic, carried or in the Home: ``_owns_telepathy``) and read on
every shop's shelf (store.cpp gives a shop other than the Black Market an ego item
too).  One errand per stay: a shelf of a higher row on another shop is not replaced.

Owner 2026-11-16 (verbatim): 「破壊の杖の優先購入だが、魔道具術師で取り込み回数が50を超えたらやめる。」
The staff's row is wanted only while ``staff_wanted`` holds: a Magic-Eater whose absorbed
*Destruction* count (me_capability.count: the displayed list's ``max``, else the absorption
record, a lower bound) is above ``ME_STAFF_COUNT_LIMIT`` neither buys it as the Black Market's
top pick (any number) nor sells Home's spares for it.  Every other class keeps the rule.

Owner 2026-11-21 (verbatim): 「スピードの杖の一本目は最優先にする」.  The table's third row: a
Magic-Eater's first Staff of Speed, wanted while no Speed power is absorbed (me_capability.count)
and no Staff of Speed is carried or in the Home, read on every shop's shelf (the Magic shop and
the Black Market stock it).  Later copies stay the Magic-Eater device table's
(me_device_policy ``buy_more``, the "me-device:policy" rung).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hengbot import ability_sources
from hengbot import item_fate
from hengbot.item_reservation import decision_memo
from hengbot.model import STORE_BLACK, STORE_HOME, SV_STAFF_SPEED, TVAL_STAFF

# object-enchant/tr-types.h TR_TELEPATHY; the depth requirement's "telepathy"
# (DEPTH_ABILITY_REQUIREMENTS, 50F) is the board's ability of this flag only
# (bot-json-output.cpp ``sources(TR_TELEPATHY)``).
TR_TELEPATHY = 79


@dataclass(frozen=True)
class PriorityWare:
    """One row of the errand's table, in priority order."""

    label: str
    # The shops whose shelf is read; None: every shop but the Home.
    stores: frozenset | None
    # The shelf row (or a carried piece) is this ware: (policy, item).
    is_ware: Callable[[Any, Any], bool]
    # The character wants it now: (policy, snapshot).
    wanted: Callable[[Any, Any], bool]


def _is_telepathy_ware(_policy: Any, item: Any) -> bool:
    return (TR_TELEPATHY in item.known_flags and getattr(item, "is_equipment", True)
            and not item.is_cursed and not item.is_broken)


def _owns_telepathy(policy: Any, snapshot: Any) -> bool:
    """Full telepathy worn or intrinsic, or a known piece carried or in the Home."""
    if ability_sources.has_ability(snapshot.player, "telepathy"):
        return True
    catalog = getattr(policy, "_equipment_catalog", None)
    owned = (*snapshot.equipment, *snapshot.inventory,
             *getattr(policy, "_home_knowledge_items", ()),
             *(owned.item for owned in (catalog.items if catalog is not None else ())))
    return any(TR_TELEPATHY in item.known_flags for item in owned)


def _is_speed_staff(_policy: Any, item: Any) -> bool:
    return (item.tval == TVAL_STAFF and item.sval == SV_STAFF_SPEED and item.aware
            and max(item.charges, item.pval) > 0)


def first_speed_staff_wanted(policy: Any, snapshot: Any) -> bool:
    """A Magic-Eater with no Speed power absorbed and no Staff of Speed carried or in the Home."""
    from hengbot import me_capability
    from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER

    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        return False
    if me_capability.count(policy, snapshot, "staff", SV_STAFF_SPEED) > 0:
        return False
    home = getattr(policy, "_home_knowledge_items", ()) or ()
    return not any(item.tval == TVAL_STAFF and item.sval == SV_STAFF_SPEED and item.aware
                   for item in (*snapshot.inventory, *home))


# Owner 2026-11-16 「魔道具術師で取り込み回数が50を超えたらやめる」.
ME_STAFF_COUNT_LIMIT = 50


def staff_wanted(policy: Any, snapshot: Any) -> bool:
    """The staff's priority purchase applies: not a Magic-Eater past ``ME_STAFF_COUNT_LIMIT``
    (me_capability.count is 0 for every other class)."""
    from hengbot import destruction_means, me_capability

    return (me_capability.count(policy, snapshot, *destruction_means.POWER)
            <= ME_STAFF_COUNT_LIMIT)


PRIORITY_WARES = (
    # Owner 2026-11-07 「何本でも買う」: whenever the Black Market shelves one (owner
    # 2026-11-16: a Magic-Eater only up to its count limit, ``staff_wanted``).
    PriorityWare("destruction-staff", frozenset({STORE_BLACK}),
                 lambda policy, item: policy._is_destruction_staff(item),
                 staff_wanted),
    # Owner 2026-11-15 「完全なテレパシーを闇市で最優先で買う」; its purchase rung is
    # policy_shop's "priority-ware:telepathy" (``rung_matches``).
    PriorityWare("telepathy", None, _is_telepathy_ware,
                 lambda policy, snapshot: not _owns_telepathy(policy, snapshot)),
    # Owner 2026-11-21 「スピードの杖の一本目は最優先にする」; its purchase rung is policy_shop's
    # "priority-ware:speed-staff".
    PriorityWare("speed-staff", None, _is_speed_staff, first_speed_staff_wanted),
)
_BY_LABEL = {entry.label: entry for entry in PRIORITY_WARES}
_RANK = {entry.label: rank for rank, entry in enumerate(PRIORITY_WARES)}


def _entry(shelf: dict | None) -> PriorityWare:
    # A checkpoint older than the table shelved the staff.
    return _BY_LABEL[(shelf or {}).get("ware", PRIORITY_WARES[0].label)]


def _shelf_store(shelf: dict) -> int:
    return shelf.get("store", STORE_BLACK)

# 「予備の武器と予備の胴防具」: item_fate's melee and body slots; 2026-11-07
# 「射撃武器も入れる」: and launchers (bows, crossbows, slings).  Diggers stay, and so
# does every other slot (2026-11-15 「すべて売るのは武器と胴防具だけ」).
FUND_SLOTS = frozenset({"melee", "launcher", "body"})
# store/store-owners.cpp: every non-Black-Market owner's purse limit (max_cost).
STORE_PURSE_LIMIT = 30000
# store/pricing.cpp calc_store_price (PLAYER_SELLS): value * min(400 - markup,
# 100)% then -10%.  The markup (owner greed + race pairing + CHR) is not
# observable before the sale; 50% stays under the usual 60-90% so the plan
# never counts gold a sale will not bring.  Each sale's real gold re-plans.
SALE_ESTIMATE_PERCENT = 50
# The decision log's drift warning of a staff Home's spares cannot pay for.
UNAFFORDABLE_WARNING = "bm-destruction-fund:unaffordable"


def _shelf(policy: Any, snapshot: Any) -> dict | None:
    """This town stay's shelved staff; None once its errand closed (``observe``):
    a staff bought by a one-shot purchase that left the page is not seen gone,
    and its fund must not go on selling for it."""
    shelf = _open_shelf(policy, snapshot)
    return None if shelf is None or shelf.get("closed") else shelf


def _open_shelf(policy: Any, snapshot: Any) -> dict | None:
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
    if getattr(policy, "_bm_fund_planning", False) or _shelf(policy, snapshot) is None:
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
            if rank is None:
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
    """The owner's exception to the ranking: this piece may be sold (any rank)."""
    if _shelf(policy, snapshot) is None:
        return False
    signature = policy._item_signature(item)
    if getattr(policy, "_bm_fund_planning", False):
        return getattr(policy, "_bm_fund_probe", None) == signature
    relief = getattr(policy, "_home_full_relief", None)
    if relief is not None and relief.fund == signature:
        return True
    return signature in plan(policy, snapshot)


def funding(policy: Any, snapshot: Any) -> bool:
    """A fund sale is due: the sweep runs past its per-stay bound for it."""
    return (getattr(policy, "_bm_fund_sweep_ended", None) != policy._town_visit_epoch
            and bool(plan(policy, snapshot)))


def census_wanted(policy: Any, snapshot: Any) -> bool:
    """The staff is short and the fund has no current Home census to read.

    Asked outside; one request per stay, gold and pack (a sale or a Home
    operation changes them).
    """
    return snapshot.store is None and _census_due(policy, snapshot)


def _census_due(policy: Any, snapshot: Any) -> bool:
    if (policy._home_knowledge_current
            or getattr(policy, "_bm_fund_sweep_ended", None) == policy._town_visit_epoch
            or _census_posted(policy) == _census_mark(policy, snapshot)
            or not policy._home_available(snapshot)):
        return False
    short = shortfall(policy, snapshot)
    return short is not None and short > 0


def _census_mark(policy: Any, snapshot: Any) -> tuple:
    # A sale changes the gold, a Home take or deposit the pack.
    return (policy._town_visit_epoch, snapshot.player.gold,
            tuple(sorted((item.tval, item.sval, item.count) for item in snapshot.inventory)))


def census_requested(policy: Any, snapshot: Any) -> None:
    """The census key was chosen; it counts once it was posted (``observe``):
    a later rewrite of the board's key (a periodic character dump) asks again."""
    policy._bm_fund_census = (_census_mark(policy, snapshot), False)


def _census_posted(policy: Any) -> tuple | None:
    census = getattr(policy, "_bm_fund_census", None)
    return census[0] if census is not None and census[1] else None


def _note_census_posted(policy: Any) -> None:
    census = getattr(policy, "_bm_fund_census", None)
    if (census is not None and not census[1]
            and (policy._home_knowledge_scan_inflight or policy._home_knowledge_current)):
        policy._bm_fund_census = (census[0], True)


def _store_finished(policy: Any, store: int) -> bool:
    plan = getattr(policy, "_town_errand_plan", None)
    return (store in policy._town_store_attempted
            or (plan is not None and store in plan.completed_this_visit))


def _fundable(policy: Any, snapshot: Any) -> bool:
    """Home's spares may still cover the shortfall this stay."""
    if getattr(policy, "_bm_fund_sweep_ended", None) == policy._town_visit_epoch:
        return False
    if policy._home_knowledge_current:
        return bool(plan(policy, snapshot))
    relief = getattr(policy, "_home_full_relief", None)
    if relief is not None and relief.fund is not None:
        # A fund piece is out of Home on its way to its buyer.
        return True
    return _census_due(policy, snapshot) or bool(
        getattr(policy, "_home_knowledge_scan_inflight", False))


def staff_pending(policy: Any, snapshot: Any) -> bool:
    """This stay's shelved staff still waits for its purchase or for its fund.

    False once the staff is bought (the shelf is seen without it), once the
    reopened Black Market stop has been left again, or once Home's spares can
    no longer cover it (the shelf's ``closed`` outcome, ``observe``).
    """
    if _shelf(policy, snapshot) is None:
        return False
    short = shortfall(policy, snapshot)
    if short is None:
        return False
    return short <= 0 or _fundable(policy, snapshot)


def holds_town_for_staff(policy: Any, snapshot: Any) -> bool:
    """The class sequences that leave town wait for the staff (「その訪問中に購入まで」)."""
    return bool(snapshot.in_town and staff_pending(policy, snapshot))


def settled(policy: Any, snapshot: Any) -> bool:
    """The departure leaf ``destruction_staff_settled``: nothing left to do for the staff."""
    return not staff_pending(policy, snapshot)


def _carried(policy: Any, snapshot: Any, entry: PriorityWare | None = None) -> int:
    entry = entry or _entry(getattr(policy, "_bm_destruction_shelf", None))
    return sum(item.count for item in snapshot.inventory if entry.is_ware(policy, item))


def _rows(policy: Any, store: Any, entry: PriorityWare) -> list:
    return [item for item in store.items
            if entry.is_ware(policy, item) and item.count > 0 and item.price > 0]


def _wares(policy: Any, snapshot: Any, store: Any) -> tuple:
    """(row of the table, its wares on this page) of the first wanted row shelved here."""
    for entry in PRIORITY_WARES:
        if entry.stores is not None and store.store_type not in entry.stores:
            continue
        rows = _rows(policy, store, entry)
        if rows and entry.wanted(policy, snapshot):
            return entry, rows
    return None, []


def rung_matches(policy: Any, snapshot: Any, label: str, item: Any) -> bool:
    """The purchase rung of the table's row ``label``: this stay's shelved ware."""
    shelf = _shelf(policy, snapshot)
    return (shelf is not None and _entry(shelf).label == label
            and _BY_LABEL[label].is_ware(policy, item))


def page_purchase(policy: Any, snapshot: Any) -> tuple | None:
    """``(ware or None,)`` when the staff owns this page's purchase; None otherwise.

    While the staff is pending (「最優先」), the Black Market page buys the staff
    alone, and only once the gold covers it; a Magic-Eater staff-sequence buy on
    any page waits for it as well.  Every other page keeps its ordinary order.
    """
    store = snapshot.store
    if store is None or not staff_pending(policy, snapshot):
        return None
    shelf = _shelf(policy, snapshot)
    if store.store_type == _shelf_store(shelf):
        staffs = _rows(policy, store, _entry(shelf))
        if not staffs:
            return None
        short = shortfall(policy, snapshot)
        return (min(staffs, key=lambda item: item.price)
                if short is not None and short <= 0 else None,)
    from hengbot import me_staff_sequence
    if me_staff_sequence.shopping(policy, snapshot):
        return (None,)
    return None


def _close_shelf(policy: Any, shelf: dict, outcome: str, snapshot: Any) -> None:
    short = shortfall(policy, snapshot)
    shelf["closed"] = outcome
    if outcome != "unaffordable":
        return
    warning = f"{UNAFFORDABLE_WARNING}:price={shelf['price']}:short={short}"
    warnings = policy._town_visit_ledger.drift_warnings
    if warning not in warnings:
        warnings.append(warning)
    if shelf.get("withheld") and not shelf.get("rearmed"):
        # The page's other wares waited for the staff: they may be bought now.
        shelf["rearmed"] = True
        policy._rearm_town_store_for_new_work(_shelf_store(shelf))


def observe(policy: Any, snapshot: Any) -> None:
    """Remember the shelved staff; reopen the finished Black Market stop once
    the sales have covered it, and close the errand once it cannot finish."""
    _note_census_posted(policy)
    store = snapshot.store
    shelf = getattr(policy, "_bm_destruction_shelf", None)
    if store is not None and store.store_type != STORE_HOME:
        entry, staffs = _wares(policy, snapshot, store)
        here = shelf is not None and _shelf_store(shelf) == store.store_type
        if not staffs:
            if here and (shelf.get("page_top") == store.page_top
                         or store.stock_num == len(store.items)):
                policy._bm_destruction_shelf = None
            return
        open_shelf = _shelf(policy, snapshot)
        if (open_shelf is not None and not here
                and _RANK[_entry(open_shelf).label] < _RANK[entry.label]):
            # A higher row shelved on another shop keeps this stay's errand.
            return
        ware = min(staffs, key=lambda item: item.price)
        mark = (policy._effective_town_id(snapshot), policy._town_visit_epoch,
                ware.price, sum(item.count for item in staffs), store.store_type, entry.label)
        kept = ({name: shelf[name]
                 for name in ("rearmed", "withheld", "revisited", "closed", "carried")
                 if name in shelf}
                if shelf is not None and shelf.get("mark") == mark else {})
        shelf = policy._bm_destruction_shelf = {
            "town": mark[0], "epoch": mark[1], "price": ware.price,
            "page_top": store.page_top, "mark": mark, "rearmed": False,
            "store": store.store_type, "ware": entry.label,
            "carried": _carried(policy, snapshot, entry), **kept,
        }
        if shelf["rearmed"]:
            # The reopened stop's page: its purchase has its chance now.
            shelf["revisited"] = True
        short = shortfall(policy, snapshot)
        if short is not None and short <= 0:
            # This visit is the chance to buy: no reopening for it.
            shelf["rearmed"] = True
        elif short is not None:
            # 「最優先」: the page's other wares wait for the staff (page_purchase).
            shelf["withheld"] = True
        return
    if store is not None or _shelf(policy, snapshot) is None:
        return
    if _carried(policy, snapshot) > shelf.get("carried", 0):
        # A one-shot purchase left the page with the staff: it is bought.
        _close_shelf(policy, shelf, "bought", snapshot)
        return
    short = shortfall(policy, snapshot)
    if short is None:
        return
    if short > 0 and not _fundable(policy, snapshot):
        # Every eligible spare together cannot cover it: nothing is sold.
        _close_shelf(policy, shelf, "unaffordable", snapshot)
        return
    if not _store_finished(policy, _shelf_store(shelf)):
        return
    if shelf.get("revisited"):
        # The reopened stop was left again: the purchase had its chance.
        _close_shelf(policy, shelf, "revisited", snapshot)
    elif short <= 0 and not shelf.get("rearmed"):
        shelf["rearmed"] = True
        policy._rearm_town_store_for_new_work(_shelf_store(shelf))
