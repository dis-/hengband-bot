"""The Home's cap of 200 stacks and the tidy that keeps it (Home root fix stage 2).

Owner 2026-11-19 「自宅の満杯問題で問題を起こしすぎなので根本解決すること」, on the
PROPOSAL (C:\\hengband-backups\\pdca\\home-full-root-1119, 3-2 and 3-6 stage 2):

1. 「200件（空き40）」: the Home keeps at most ``home_ledger.HOME_KEEP_CAP`` stacks; the 40
   above it (powerup_home's 240, store.cpp store_get_stock_capacity) stay free for deposits.
2. 「安い順に売ってよい」: past the sellable stock, ranks 11-20 go, cheapest first; the top ten
   always stay.
3. 「一気に片づける」: one town visit clears the Home down to the cap (no per-visit bound).
4. 「上限を置かない」: supplies' spares are not sold to meet the cap.

What leaves is what ``item_fate.fate`` moves (``sheds``: destroy, sell, room-sale); everything
the fate keeps stays, and a Home of only kept stock stays over the cap without a stop.  The tidy
is the full-Home relief (policy_home ``_home_full_relief_key``) with ``cap`` set: it takes no
deposits, frees ``remaining`` stacks (the count over the cap), and takes its wares in batches:
each observed take outside the Home is put on ``carried`` and the next ware is taken while the
pack keeps its reserve (``batch_grows``), then the batch is sold store by store (``drain``)
before the next take.  The tidy ends (``end``) when the Home is at the cap and the batch is
sold, when nothing more is to shed, or when its store cannot be reached; it does not begin
again in the same town visit (``STATE``).  A Home seen over the cap on an earlier visit asks
for one census per visit (``census_wanted``) so the tidy can begin.
"""
from __future__ import annotations

from typing import Any

from hengbot import item_fate, town_pack_budget
from hengbot.home_full_relief import SALE_DESTROY_FIELDS, HomeFullRelief
from hengbot.home_ledger import HOME_DEPOSIT_ROOM, HOME_KEEP_CAP, SHED_ORDER
from hengbot.item_identity import same_memory
from hengbot.model import STORE_HOME

# powerup_home's Home (store.cpp store_get_stock_capacity, STORE_INVEN_MAX * 10).
HOME_CAPACITY = HOME_KEEP_CAP + HOME_DEPOSIT_ROOM
# The policy attribute: {"ended": the town visit epoch whose tidy ended, "count": the Home's
# stack count last seen (it outlives a stale census), "census": the visit a census was asked in}.
STATE = "_home_cap_tidy"
# Owner 2026-11-19 「12件を超えたら先に鑑定」: past this many unidentified Home stacks the tidy
# identifies what a carried means identifies now before it sells.
IDENTIFY_FIRST = 12
# The Home errand purposes of the relief's takes (policy_home ``_home_full_relief_key``).
RELIEF_PURPOSES = frozenset({"full-home-sale", "full-home-discard"})
SHED_FATES = frozenset(SHED_ORDER)


def _state(policy: Any) -> dict:
    state = getattr(policy, STATE, None)
    if state is None:
        state = {"ended": None, "count": None, "census": None}
        setattr(policy, STATE, state)
    return state


def stock_count(policy: Any, snapshot: Any) -> int | None:
    """The Home's stack count: the open Home page, the current census, the last page seen."""
    store = snapshot.store
    if store is not None and store.store_type == STORE_HOME and isinstance(store.stock_num, int):
        return store.stock_num
    if policy._home_knowledge_current:
        return len(policy._home_knowledge_items)
    fact = getattr(policy, "_home_capacity_observation", None)
    if fact and fact[2] == policy._effective_town_id(snapshot):
        return fact[0]
    return None


def at_cap(policy: Any, snapshot: Any) -> bool:
    """The Home holds the cap or more, short of full: a deposit would leave it over the cap.

    A full Home (``HOME_CAPACITY``) is the full-Home relief's, which sells ranks 11-20 for room
    on its own order (item_fate.relief_order); the cap reads the stacks below it.
    """
    count = stock_count(policy, snapshot)
    return count is not None and HOME_KEEP_CAP <= count < HOME_CAPACITY


def sheds(policy: Any, snapshot: Any, item: Any) -> bool:
    """A Home stack the cap tidy moves out (its fate is destroy, sell or room-sale)."""
    return item_fate.fate(policy, snapshot, item, item_fate.SHELF) in SHED_FATES


def shed_rank(policy: Any, snapshot: Any, item: Any) -> int:
    """The cap's order of fates: destroy, sell, then ranks 11-20 (owner 2026-11-19 「安い順に
    売ってよい」: ranks 11-20 only once the sellable stock is gone)."""
    fate = item_fate.fate(policy, snapshot, item, item_fate.SHELF)
    return SHED_ORDER.index(fate) if fate in SHED_ORDER else len(SHED_ORDER)


def begin(policy: Any, snapshot: Any) -> bool:
    """Begin the cap tidy when the Home stands over its cap; True when it began."""
    count = stock_count(policy, snapshot)
    if (count is None or count <= HOME_KEEP_CAP
            or _state(policy)["ended"] == policy._town_visit_epoch
            or not snapshot.in_town or snapshot.player.recalling
            or not policy._home_knowledge_current
            or not policy._home_available(snapshot)
            or policy._home_full_relief is not None
            or getattr(policy, "_home_full_retry_deposits", None) is not None
            or policy._home_errand.active
            or policy._home_pending_item is not None
            or policy._home_pending_batch
            or policy._equipment_transaction_session is not None
            or policy._physical_hostiles(snapshot)
            or policy._inventory_overweight(snapshot)
            or item_fate.home_take_blocked(snapshot)
            or policy._town_store_blocked_under_applicable_bound(STORE_HOME)):
        return False
    policy._home_full_relief = HomeFullRelief(
        remaining=count - HOME_KEEP_CAP, town=policy._effective_town_id(snapshot), cap=True)
    return True


def batch_grows(policy: Any, snapshot: Any, relief: Any) -> bool:
    """Another ware may be taken before the batch is sold."""
    return bool(relief.remaining > 0 and not item_fate.home_take_blocked(snapshot)
                and not policy._inventory_overweight(snapshot))


def take_done(policy: Any, relief: Any, signature: Any, store_type: int) -> None:
    """An observed take outside the Home joins the batch: its shelf slot is freed."""
    relief.carried = (*relief.carried, (signature, store_type, relief.useless == signature))
    relief.remaining -= 1
    taken = relief.consume("taken")
    if taken is not None and taken[0] == signature and relief.stock_count is not None:
        # As after a sale: a later census tells a put-back from the take.
        relief.settled_home_counts[signature] = max(0, relief.stock_count - taken[1])
    relief.end_sale(*SALE_DESTROY_FIELDS)
    relief.reset("stock_count", "pack_only")
    policy._home_errand.finish()


def drain(policy: Any, snapshot: Any, relief: Any) -> bool:
    """Make the next carried ware of the batch the relief's sale; False when none is left.

    A ware no longer carried (another owner sold or used it) is dropped.  The sale is a pack
    sale (``pack_only``): its shelf slot was counted at the take.
    """
    relief.draining = True
    while relief.carried:
        (signature, store_type, useless), relief.carried = relief.carried[0], relief.carried[1:]
        identity = policy._sale_signature_identity(signature)
        stacks = [item for item in snapshot.inventory
                  if policy._sale_item_identity(item) == identity]
        if not stacks:
            continue
        count = sum(item.count for item in stacks)
        relief.sale = (signature, store_type, count - stacks[0].count)
        relief.withdrawn = True
        relief.pack_only = True
        relief.mode = "sale"
        relief.rank_released = signature
        relief.useless = signature if useless else None
        return True
    relief.draining = False
    return False


def end(policy: Any) -> None:
    """End the cap tidy for this town visit."""
    relief = policy._home_full_relief
    if (relief is not None and relief.sale is not None
            and same_memory(policy._home_pending_item, relief.sale[0])):
        policy._home_pending_item = None
        policy._home_pending_quantity = None
    policy._home_full_relief = None
    request = policy._home_errand.request
    if (policy._home_errand.active and request is not None
            and request.purpose in RELIEF_PURPOSES):
        # Only the tidy's own take: another owner's errand is not this tidy's to end.
        policy._home_errand.finish()
    _state(policy)["ended"] = policy._town_visit_epoch


def observe(policy: Any, snapshot: Any) -> None:
    """Remember the Home's stack count whenever a page or a current census shows it."""
    if snapshot.in_town:
        count = stock_count(policy, snapshot)
        if count is not None:
            _state(policy)["count"] = count


def census_wanted(policy: Any, snapshot: Any) -> bool:
    """The Home stood over its cap when last seen and no current census shows it now: one
    census per town visit lets the tidy begin."""
    state = _state(policy)
    epoch = policy._town_visit_epoch
    return bool(snapshot.store is None and snapshot.in_town and epoch is not None
                and not policy._home_knowledge_current
                and not getattr(policy, "_home_knowledge_scan_inflight", False)
                and (state["count"] or 0) > HOME_KEEP_CAP
                and state["ended"] != epoch and state["census"] != epoch
                and policy._home_available(snapshot)
                and not policy._town_store_blocked_under_applicable_bound(STORE_HOME)
                # Only when the tidy could begin on it: the census never goes before a
                # weight deposit or another owner's Home work.
                and not policy._inventory_overweight(snapshot)
                and not item_fate.home_take_blocked(snapshot)
                and not policy._home_errand.active
                and policy._home_pending_item is None
                and not policy._home_pending_batch
                and policy._equipment_transaction_session is None
                and getattr(policy, "_home_full_retry_deposits", None) is None
                and policy._find_home_deposit(snapshot) is None)


def census_requested(policy: Any) -> None:
    _state(policy)["census"] = policy._town_visit_epoch
