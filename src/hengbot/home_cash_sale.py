"""Home's cash wares sold before a poverty mining set (owner 2026-11-18).

n1-a life-530 2026-11-18 06:36:52: an Alchemist *Identify* purchase left 1,160 gold, under
FUNDRAISING_START_GOLD, and ``_start_fundraising`` sent the Lv49 warrior to mine the Yeek cave's
first floor while its Home held seven realm books worth some 160,000 gold to a store.  Owner,
verbatim: 「必要なものは買う。本当に資金枯渇したら採掘で良いが、自宅に大量の換金用アイテムがあるので
先に売る。」, and on what to sell: 「魔法書と明確に不要な指輪アミュレットを売る」.

The cash wares (``ware``), Home stock only:

* a high-value realm book (``_is_high_value_book``, the third and fourth books, the policy's own
  "valuable town-sale loot");
* clearly unneeded jewelry (``unneeded_jewelry``): a known non-artifact ring or amulet the owner's
  ranking does not keep (item_fate.gear_tier: outside its slot's top ten), carrying none of the
  abilities a loadout may need (``KEPT_FLAGS``).  Anything in doubt stays on the shelf.

Each ware still passes every gate of the Home sale (``_home_full_sale_candidate``: retention,
reservations, named keeps, identification) and leaves through the existing Home junk sweep
(item_fate.sweep_ware, policy_home ``_begin_home_junk_sweep``), most valuable first, past the
sweep's per-stay bound.  While one is left (``pending``) ``_start_fundraising`` waits; once the gold
is back over the line, or no ware is left, or the sweep ended without a take this stay
(``end``), the mining set opens as before.  Nothing else is sold for it: weapons, armour,
artifacts, survival supplies and *Destruction* staves keep their rules.
"""
from __future__ import annotations

from typing import Any

from hengbot import item_fate
from hengbot.item_reservation import decision_memo
from hengbot.policy_constants import FUNDRAISING_START_GOLD

TVAL_AMULET = 40
TVAL_RING = 45
JEWELRY_TVALS = frozenset({TVAL_AMULET, TVAL_RING})
MINING_MODES = frozenset({"prepare", "mine", "scavenge"})

# object-enchant/tr-types.h: what a ring or amulet may give a loadout beyond its sale value.
TR_MAGIC_MASTERY = 6   # the device skill of the *Destruction* staff gate (owner 2026-11-15)
TR_SPEED = 12
TR_BLOWS = 13
TR_REFLECT = 45
TR_HOLD_EXP = 47
TR_SEE_INVIS = 78
TR_XTRA_SHOTS = 83


def _kept_flags() -> frozenset:
    """The depth table's abilities (equipment_optimizer.ABILITY_FLAG) and the rest above."""
    from hengbot.equipment_optimizer import ABILITY_FLAG
    return frozenset(ABILITY_FLAG.values()) | {
        TR_MAGIC_MASTERY, TR_SPEED, TR_BLOWS, TR_REFLECT, TR_HOLD_EXP, TR_SEE_INVIS, TR_XTRA_SHOTS}


# The policy attribute: {"seen": the last current census held a ware, "census": the
# (epoch, gold, pack) mark of the census asked for, "ended": the stay whose sweep ended}.
STATE = "_home_cash_sale"


def _state(policy: Any) -> dict:
    state = getattr(policy, STATE, None)
    if state is None:
        state = {"seen": False, "census": None, "ended": None}
        setattr(policy, STATE, state)
    return state


def unneeded_jewelry(policy: Any, snapshot: Any, item: Any) -> bool:
    """A ring or amulet nothing keeps: outside the ranking's keep, giving no kept ability."""
    return bool(item.tval in JEWELRY_TVALS and item.known and not item.is_artifact
                and not (set(item.known_flags) & _kept_flags())
                and item_fate.gear_tier(policy, snapshot, item) != item_fate.KEEP)


def ware(policy: Any, snapshot: Any, item: Any) -> bool:
    """A Home stack kept only for its sale value."""
    return bool(policy._is_high_value_book(item) or unneeded_jewelry(policy, snapshot, item))


def due(policy: Any, snapshot: Any) -> bool:
    """Poverty in town with no mining set open, the sale not ended this stay."""
    return bool(snapshot.in_town and snapshot.player.class_id >= 0
                and snapshot.player.gold < FUNDRAISING_START_GOLD
                and policy._fundraising_mode not in MINING_MODES
                and _state(policy)["ended"] != policy._town_visit_epoch)


def wares(policy: Any, snapshot: Any, stock: Any) -> list:
    """``(sale candidate, item)`` of the cash wares in ``stock``, most valuable first."""
    rows = [(result, item) for item in stock
            if ware(policy, snapshot, item)
            and (result := policy._home_full_sale_candidate(snapshot, item)) is not None
            and policy._can_add_item_without_overweight(snapshot, item)]
    return sorted(rows, key=lambda entry: (-item_fate.sale_value(policy, entry[0][0]),
                                           policy._item_signature(entry[0][0])))


def _shelf_has_ware(policy: Any, snapshot: Any) -> bool:
    stock = policy._home_knowledge_items
    return decision_memo(
        policy, "home-cash-sale", snapshot,
        (id(stock), len(stock), policy._home_pending_item, snapshot.player.gold),
        lambda: bool(wares(policy, snapshot, stock)))


def sweep_ware(policy: Any, snapshot: Any, stock: Any) -> Any:
    """The sweep's next cash ware while the sale is due, else None."""
    if not due(policy, snapshot):
        return None
    rows = wares(policy, snapshot, stock)
    return rows[0] if rows else None


def _census_mark(policy: Any, snapshot: Any) -> tuple:
    # A sale changes the gold, a Home take or deposit the pack.
    return (policy._town_visit_epoch, snapshot.player.gold,
            tuple(sorted((item.tval, item.sval, item.count) for item in snapshot.inventory)))


def pending(policy: Any, snapshot: Any) -> bool:
    """A cash ware is still on the Home shelf: the poverty mining set waits.

    With a stale census (each sale invalidates it), the last current census decides until the
    census this gold and pack ask for has been requested and is no longer in flight.
    """
    if (not due(policy, snapshot) or not policy._home_available(snapshot)
            or not policy._home_junk_sweep_capacity(snapshot)):
        return False
    if policy._home_knowledge_current:
        return _shelf_has_ware(policy, snapshot)
    state = _state(policy)
    return bool(state["seen"] and (
        state["census"] != _census_mark(policy, snapshot)
        or getattr(policy, "_home_knowledge_scan_inflight", False)))


def census_wanted(policy: Any, snapshot: Any) -> bool:
    """The sale waits on a Home census that has not been asked for at this gold and pack."""
    return bool(snapshot.store is None and not policy._home_knowledge_current
                and not getattr(policy, "_home_knowledge_scan_inflight", False)
                and pending(policy, snapshot))


def census_requested(policy: Any, snapshot: Any) -> None:
    _state(policy)["census"] = _census_mark(policy, snapshot)


def end(policy: Any) -> None:
    """A sweep for a cash ware ended without its sale: no more cash sales this stay."""
    _state(policy)["ended"] = policy._town_visit_epoch


def observe(policy: Any, snapshot: Any) -> None:
    """Remember whether the current census holds a cash ware (read while it is stale)."""
    if (snapshot.in_town and policy._home_knowledge_current
            and snapshot.player.gold < FUNDRAISING_START_GOLD):
        _state(policy)["seen"] = _shelf_has_ware(policy, snapshot)
