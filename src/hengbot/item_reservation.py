"""Decision-local views of existing item reservations; no checkpoint state."""
from __future__ import annotations

from hengbot.model import TVAL_WAND

from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
import logging

from hengbot.equipment_optimizer import equipment_identity


# Exact item-intent source registry. The first value selects a component of
# the composed predicate below; the second records the reviewed state role.
# Queued candidates/selection observations retain their existing non-exclusive
# semantics. Ownership is acquired at the existing atomic/transaction seam.
ITEM_RESERVATION_SOURCES = {
    '_terminal_item_command': ('selection', 'Scoped item command admission inputs; existing reservation owners are unchanged'),
    '_terminal_equipment_command': ('selection', 'Scoped session command admission inputs; the existing session retains ownership'),
    '_terminal_home_take': ('selection', 'Scoped observed Home take target for admission; no additional exclusive owner'),
    '_terminal_store_sale': ('selection', 'Scoped exact sale target and refusal reason for admission; no additional exclusive owner'),
    '_overweight_surplus_disposal': ('selection', 'F3 shop-sell surplus transaction selection/observation; retained units acquire no new exclusive owner'),
    '_batch_sell_pending': ('selection', 'batch sell pending; selection/observation intent, no additional exclusive owner'),
    '_destroy_watch': ('selection', 'destroy watch; selection/observation intent, no additional exclusive owner'),
    '_device_identification_candidate': ('selection', 'device identification candidate; selection/observation intent, no additional exclusive owner'),
    '_device_identify_watch': ('selection', 'device identify watch; selection/observation intent, no additional exclusive owner'),
    '_emergency_consumable_issue_watch': ('selection', 'emergency consumable issue watch; selection/observation intent, no additional exclusive owner'),
    '_equipment_mutation': ('equipment-txn', 'equipment mutation; existing exclusive predicate'),
    '_equipment_transaction_owned_items': ('equipment-txn', 'equipment transaction owned items; existing exclusive predicate'),
    '_equipment_transaction_prepared_catalog_update': ('equipment-txn', 'equipment transaction prepared catalog update; existing exclusive predicate'),
    '_equipment_transaction_session': ('equipment-txn', 'equipment transaction session; existing exclusive predicate'),
    '_heavy_curse_inscription_pending': ('selection', 'heavy curse inscription pending; selection/observation intent, no additional exclusive owner'),
    '_home_atomic_deposit_pending': ('home-visit', 'home atomic deposit pending; existing exclusive predicate'),
    '_home_atomic_withdraw_move_identity': ('home-errand', 'home atomic withdraw move identity; existing exclusive predicate'),
    '_home_atomic_withdraw_pending': ('home-errand', 'home atomic withdraw pending; existing exclusive predicate'),
    '_home_digger_withdraw_pending': ('home-errand', 'home digger withdraw pending; existing exclusive predicate'),
    '_home_disposal_candidates': ('selection', 'home disposal candidates; selection/observation intent, no additional exclusive owner'),
    '_home_disposal_pending': ('selection', 'home disposal pending; selection/observation intent, no additional exclusive owner'),
    '_home_errand': ('home-errand', 'home errand; existing exclusive predicate'),
    '_home_full_retry_deposits': ('home-full-retry', 'home full retry deposits; existing exclusive predicate'),
    '_home_identify_staff_sale_pending': ('selection', 'home identify staff sale pending; selection/observation intent, no additional exclusive owner'),
    '_home_pending_batch': ('home-errand', 'home pending batch; existing exclusive predicate'),
    '_home_pending_item': ('home-errand', 'home pending item; existing exclusive predicate'),
    '_home_pending_quantities': ('home-errand', 'home pending quantities; existing exclusive predicate'),
    '_home_pending_quantity': ('home-errand', 'home pending quantity; existing exclusive predicate'),
    '_home_pending_slot': ('home-errand', 'home pending slot; existing exclusive predicate'),
    '_home_pending_take_confirmed': ('home-errand', 'home pending take confirmed; existing exclusive predicate'),
    '_home_procurement_probe': ('selection', 'home procurement probe; selection/observation intent, no additional exclusive owner'),
    '_home_visit': ('home-visit', 'home visit; existing exclusive predicate'),
    '_home_withdraw_page_probe': ('home-errand', 'Home target signature while probing catalogue pages; atomic withdrawal confers exclusivity'),
    '_identification_candidate': ('selection', 'identification candidate; selection/observation intent, no additional exclusive owner'),
    '_identification_source_reservation': ('selection', 'identification source reservation; selection/observation intent, no additional exclusive owner'),
    '_identify_watch': ('selection', 'identify watch; selection/observation intent, no additional exclusive owner'),
    '_launcher_enchant_watch': ('selection', 'launcher enchant watch; selection/observation intent, no additional exclusive owner'),
    '_look_floor_items': ('selection', 'look floor items; selection/observation intent, no additional exclusive owner'),
    '_morivant_full_identify': ('selection', 'morivant full identify; selection/observation intent, no additional exclusive owner'),
    '_no_teleport_rearm_pending': ('selection', 'no teleport rearm pending; selection/observation intent, no additional exclusive owner'),
    '_normal_sub_hand_identity': ('equipment-txn', 'normal sub hand identity; existing exclusive predicate'),
    '_normal_weapon_identity': ('equipment-txn', 'normal weapon identity; existing exclusive predicate'),
    '_pending_disposal_item': ('selection', 'pending disposal item; selection/observation intent, no additional exclusive owner'),
    '_pending_disposal_slot': ('selection', 'pending disposal slot; selection/observation intent, no additional exclusive owner'),
    '_ranged_target_macro_signature': ('selection', 'ranged target macro signature; selection/observation intent, no additional exclusive owner'),
    '_read_binding': ('selection', 'read binding; selection/observation intent, no additional exclusive owner'),
    '_remove_curse_watch': ('selection', 'remove curse watch; selection/observation intent, no additional exclusive owner'),
    '_staged_prompt_chain': ('selection', 'staged prompt chain; selection/observation intent, no additional exclusive owner'),
    '_star_remove_curse_reserve_buy_inflight': ('home-reserve', 'star remove curse reserve buy inflight; existing exclusive predicate'),
    '_star_remove_curse_reserve_deposit_inflight': ('home-reserve', 'star remove curse reserve deposit inflight; existing exclusive predicate'),
    '_star_remove_curse_reserve_deposit_pending': ('home-reserve', 'star remove curse reserve deposit pending; existing exclusive predicate'),
    '_star_remove_curse_reserve_withdraw_pending': ('home-reserve', 'star remove curse reserve withdraw pending; existing exclusive predicate'),
    '_store_buy_inflight': ('selection', 'store buy inflight; selection/observation intent, no additional exclusive owner'),
    '_store_sell_attempt': ('selection', 'store sell attempt; selection/observation intent, no additional exclusive owner'),
    '_town_visit_purchase_quantities': ('retention', 'Observed purchased quantities protect existing retention, without an exclusive owner'),
    '_town_visit_purchases': ('retention', 'Observed purchased signatures protect existing retention, without an exclusive owner'),
    '_town_visit_purchase_record': ('retention', 'The written copy of the observed visit purchases, restored after a restart, without an exclusive owner'),
}

@dataclass(frozen=True)
class ReservationVerdict:
    sink: str
    owner: str | None = None
    quantity: int | None = None
    ambiguous: bool = False
    item_id: int | None = None

    @property
    def reason(self):
        return f"ownership:item-reserved:{self.sink}:{self.owner}"


# Only the fare-recovery caller grants a quantity for this exact live stack.
# The token ends before any other town producer can run; retention itself is
# never lowered for deposits, destruction, or ordinary shop sales.
_fare_sale = ContextVar("outpost_fare_sale", default=None)


@contextmanager
def outpost_fare_sale(policy, snapshot, item, quantity):
    token = _fare_sale.set((policy, snapshot, item, quantity))
    try:
        yield
    finally:
        _fare_sale.reset(token)


def outpost_fare_sale_quantity(policy, snapshot, item):
    grant = _fare_sale.get()
    if (grant is not None and grant[0] is policy and grant[1] is snapshot
            and grant[2] is item):
        return grant[3]
    return None


_decision = ContextVar("item_reservation_decision", default=None)
_query = ContextVar("item_reservation_query", default=False)
_query_memo = ContextVar("item_reservation_query_memo", default=None)
_caches_enabled = ContextVar("item_reservation_caches_enabled", default=True)
_claim_candidate_memo = ContextVar("town_claim_candidate_memo", default=None)


@contextmanager
def decision_caches_disabled():
    """Provide a cache-free decision oracle without adding policy state."""
    token = _caches_enabled.set(False)
    try:
        yield
    finally:
        _caches_enabled.reset(token)


def decision_caches_enabled():
    """Whether decision-local performance caches are enabled in this context."""
    return _caches_enabled.get()


@contextmanager
def claim_candidate_cache(policy, snapshot):
    """Memoize town candidates only during one claims evaluation."""
    if not _caches_enabled.get():
        yield
        return
    token = _claim_candidate_memo.set(
        {"policy": policy, "snapshot": snapshot, "candidates": None}
    )
    try:
        yield
    finally:
        _claim_candidate_memo.reset(token)


def claim_candidate_memo(policy, snapshot, compute):
    state = _claim_candidate_memo.get()
    if (
        not _caches_enabled.get()
        or state is None
        or state["policy"] is not policy
        or state["snapshot"] is not snapshot
    ):
        return compute()
    if state["candidates"] is None:
        state["candidates"] = compute()
    return state["candidates"]


def reservation_query(function):
    """Need enumeration filters candidates without issuing an item operation."""
    @wraps(function)
    def run(*args, **kwargs):
        policy = args[0] if args else None
        token_memo = _query_memo.set({"policy": policy, "values": {}})
        token = _query.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _query.reset(token)
            _query_memo.reset(token_memo)
    return run


def reservation_query_memo(policy, name, snapshot, key, compute):
    """Reuse a query result only while one read-only need enumeration is live."""
    if not _caches_enabled.get():
        return compute()
    state = _query_memo.get()
    if state is None or state["policy"] is not policy:
        return compute()
    cache = state["values"].setdefault(name, {})
    cache_key = (id(snapshot), key)
    hit = cache.get(cache_key)
    if hit is not None and hit[0] is snapshot:
        return hit[1]
    value = compute()
    cache[cache_key] = (snapshot, value)
    return value


def decision_memo(policy, name, snapshot, key, compute):
    """Memoize an immutable snapshot-derived value for the current decision."""
    if not _caches_enabled.get():
        return compute()
    state = _decision.get()
    if state is None or state["policy"] is not policy:
        return compute()
    cache = state.setdefault("memo", {}).setdefault(name, {})
    cache_key = (id(snapshot), key)
    hit = cache.get(cache_key)
    if hit is not None and hit[0] is snapshot:
        return hit[1]
    value = compute()
    cache[cache_key] = (snapshot, value)
    return value


def reservation_decision(function):
    @wraps(function)
    def run(policy, snapshot):
        token = _decision.set({
            "policy": policy, "view": None, "shadow": [], "skips": {}, "memo": {},
        })
        try:
            return function(policy, snapshot)
        finally:
            _decision.reset(token)
    return run


def reservation_shadow(policy):
    state = _decision.get()
    return list(state["shadow"]) if state and state["policy"] is policy else []


def _selector_skip(policy, verdict):
    """Count filtered candidates without changing the acting producer's reason."""
    state = _decision.get()
    if state is not None and state["policy"] is policy:
        key = ("query_skip" if _query.get() else "selector_skip", verdict.reason)
        row = state["skips"].get(key)
        if row is None:
            row = {key[0]: verdict.reason, "count": 0, "ambiguous": verdict.ambiguous}
            state["skips"][key] = row
            state["shadow"].append(row)
        row["count"] += 1
        row["ambiguous"] |= verdict.ambiguous


def _emission_denied(policy, verdict):
    """A foreign verdict is terminal only at the command serialization seam."""
    _shadow(policy, {"would_stop": verdict.reason, "ambiguous": verdict.ambiguous})
    if getattr(policy, "_town_claim_bar_enforced", False):
        policy.last_reason = verdict.reason


def _row_key(snapshot, item):
    carried = any(item is candidate for candidate in (*snapshot.inventory, *snapshot.equipment))
    return equipment_identity(item), carried


def _reservation_row(policy, snapshot, item, view):
    signature = policy._item_signature(item)
    owners = []
    retained = False
    for source in _SOURCE_PREDICATES:
        active = source in view["sources"] and _SOURCE_PREDICATES[source](policy, snapshot, item, signature, view)
        if source == "retention":
            retained = bool(active)
        elif active:
            owners.append(source)
    return tuple(owners), retained


def _transaction_source(policy, snapshot, item, signature, view):
    return (policy._equipment_transaction_deposit_owns_item(item)
            or policy._equipment_transaction_owns_item(item))


def _retry_source(policy, snapshot, item, signature, view):
    return signature in view["retry"]


def _deposit_source(policy, snapshot, item, signature, view):
    return signature in view["deposit"]


def _withdraw_source(policy, snapshot, item, signature, view):
    return signature in view["withdraw"]


def _reserve_source(policy, snapshot, item, signature, view):
    return policy._home_reserve_deposit_item(item)


def _selection_source(policy, snapshot, item, signature, view):
    # A candidate, prompt binding or completed-use observer is an intent source
    # but did not historically confer exclusive item ownership. Keep that
    # behavior: its active atomic/session state is evaluated above.
    return False


def _retention_source(policy, snapshot, item, signature, view):
    # Retention has a quantity, never an invented exclusive owner.
    return (not _row_key(snapshot, item)[1]
            and policy._equipment_disposal_reserved(snapshot, item))


_SOURCE_PREDICATES = {
    "equipment-txn": _transaction_source,
    "home-full-retry": _retry_source,
    "home-visit": _deposit_source,
    "home-errand": _withdraw_source,
    "home-reserve": _reserve_source,
    "selection": _selection_source,
    "retention": _retention_source,
}


def _view(policy, snapshot):
    """Materialize identity sets once; compute candidate rows on first use."""
    retry = frozenset(entry[0] for entry in (policy._home_full_retry_deposits or ()))
    deposit = policy._home_atomic_deposit_pending
    deposit_signatures = frozenset(entry[0] for entry in deposit[0]) if deposit else frozenset()
    withdraw = policy._home_atomic_withdraw_pending
    withdraw_signatures = frozenset()
    if withdraw:
        signature, before_count, _withdrawn, quantity = withdraw[:4]
        move_identity = getattr(policy, '_home_atomic_withdraw_move_identity', None)
        after_count = (policy._inventory_move_identity_count(snapshot, move_identity)
                       if move_identity is not None else
                       policy._inventory_signature_count(snapshot, signature))
        # An observed take can be wielded by its next owner. The observer
        # retires the persisted pending tuple at its usual seam.
        if after_count < before_count + quantity:
            withdraw_signatures = frozenset((signature,))
    sources = {}
    for attribute, (component, _reason) in ITEM_RESERVATION_SOURCES.items():
        sources.setdefault(component, {})[attribute] = getattr(policy, attribute, None)
    view = {"retry": retry, "deposit": deposit_signatures,
            "withdraw": withdraw_signatures, "rows": {}, "sources": sources}
    return view


def item_reserved_by_other(policy, snapshot, item, work) -> ReservationVerdict | None:
    """Pure ownership predicate. work is (owner, sink); None means unreserved."""
    owner, sink = work
    if sink == 'buy':
        # Merchant stock is external to the bot's reservations. Home stock
        # is selected with the withdraw sink and retains the ownership check.
        return None
    if isinstance(item, str) and sink == 'takeoff':
        from hengbot.equipment_mutation import _SLOT_BY_KEY
        slot = _SLOT_BY_KEY.get(item)
        worn = next((candidate for candidate in snapshot.equipment if candidate.slot == slot), None)
        if worn is None:
            return None
        item = worn
    state = _decision.get()
    if state is not None and state["policy"] is policy:
        if state["view"] is None:
            state["view"] = _view(policy, snapshot)
        view = state["view"]
    else:
        view = _view(policy, snapshot)
    key = _row_key(snapshot, item)
    row = view["rows"].get(key)
    if row is None:
        # New synthetic candidates evaluate only their row, never rebuild
        # the decision's identity sets or rescan the full Home catalogue.
        row = _reservation_row(policy, snapshot, item, view)
        view["rows"][key] = row
    owners, retained = row
    for reserved_owner in owners:
        if reserved_owner == owner:
            continue
        if sink in {"deposit", "weight-deposit", "overweight-surplus"} and reserved_owner in {"home-full-retry", "home-reserve"}:
            continue
        matches = sum(policy._item_signature(candidate) == policy._item_signature(item)
                      for candidate in snapshot.inventory)
        return ReservationVerdict(sink, reserved_owner, ambiguous=matches > 1)
    if retained and sink in {"sell", "destroy", "home-full-sale"}:
        return ReservationVerdict(sink, quantity=0)
    return None


def _shadow(policy, row):
    state = _decision.get()
    if state is not None and state["policy"] is policy:
        state["shadow"].append(row)
    logging.getLogger(__name__).info("item-reservation-shadow: %s", row)


def reservation_verdict(policy, snapshot, item, owner, sink):
    """Select a permitted item; foreign candidates are filtered in both modes."""
    try:
        denied = item_reserved_by_other(policy, snapshot, item, (owner, sink))
        if denied is not None and denied.owner is not None:
            _selector_skip(policy, denied)
            return denied
        if denied is not None:
            return ReservationVerdict(sink, quantity=denied.quantity, item_id=id(item))
        quantity = (policy._retention_surplus(snapshot, item)
                    if sink in {"sell", "deposit", "destroy", "weight-deposit", "home-full-sale", "overweight-surplus"}
                    else None)
        return ReservationVerdict(sink, quantity=quantity, item_id=id(item))
    except Exception as error:
        if getattr(policy, "_town_claim_bar_enforced", False):
            denied = ReservationVerdict(sink, "predicate-error")
            _selector_skip(policy, denied)
            return denied
        _shadow(policy, {"error": type(error).__name__, "sink": sink})
        return ReservationVerdict(sink, item_id=id(item))


def item_available(policy, snapshot, item, owner, sink):
    return reservation_verdict(policy, snapshot, item, owner, sink).owner is None


def standalone_verdict(kind, item):
    """Compatibility for pinned low-level APIs without a policy decision.

    Production callers must supply the snapshot/verdict; lint checks those
    adapter calls. Standalone equipment-mutation tests retain their old API.
    """
    actual = item[0] if isinstance(item, tuple) else item
    return ReservationVerdict(kind.split('-')[0], item_id=id(actual))


def item_command(kind, item, verdict: ReservationVerdict):
    """The only serializer of item-command prefixes and selectors.

    A (physical item, observed letter/tag) pair binds an alternative address
    to the same item for sales and catalogued Home withdrawals.
    """
    actual, address = item if isinstance(item, tuple) else (item, None)
    if not isinstance(verdict, ReservationVerdict):
        raise TypeError('item command requires ReservationVerdict')
    if verdict.owner is not None:
        state = _decision.get()
        if state is not None:
            _emission_denied(state["policy"], verdict)
        raise ValueError('item command has a denied verdict')
    if verdict.item_id != id(actual):
        raise ValueError('item command has a denied or different-item verdict')
    if verdict.sink != (kind if kind == "overweight-surplus" else kind.split('-')[0]):
        raise ValueError('item command has a different-sink verdict')
    letter = address if address is not None else (
        actual if isinstance(actual, str) else getattr(actual, 'slot', None)
        or getattr(actual, 'letter', None))
    if not isinstance(letter, str) or len(letter) != 1:
        raise ValueError('item command requires one observed item selector')
    prefixes = {'deposit': 'd', 'sell': 'd', 'withdraw': 'p', 'buy': 'p',
                'wield': 'w', 'takeoff': 't', 'inscribe': '{',
                'inscribe-equipped': '{/', 'uninscribe-equipped': '}/',
                'read': 'r', 'quaff': 'q', 'eat': 'E', 'staff': 'u',
                'wand': 'a', 'rod': 'z', 'fire': 'f', 'throw': 'v',
                'refill': '\\F'}
    if kind == "overweight-surplus":
        if verdict.quantity is None or not 0 < verdict.quantity <= actual.count:
            raise ValueError("surplus destroy requires a positive retained quantity")
        return f'0{verdict.quantity}k{letter}'
    if kind == 'destroy':
        return f'0{actual.count}k{letter}'
    return prefixes[kind] + letter


_historical_item_command = item_command


def checked_item_command(policy, kind, item, verdict: ReservationVerdict):
    if isinstance(verdict, ReservationVerdict) and verdict.owner is not None:
        _emission_denied(policy, verdict)
        return None
    try:
        return item_command(kind, item, verdict)
    except Exception as error:
        sink = kind if kind == "overweight-surplus" else kind.split('-')[0]
        if sink == 'overweight-surplus' or getattr(policy, '_town_claim_bar_enforced', False):
            reason = f'ownership:item-reserved:{sink}:serializer-error'
            policy.last_reason = reason
            _shadow(policy, {'would_stop': reason, 'error': type(error).__name__})
            return None
        _shadow(policy, {'sink': sink, 'error': type(error).__name__})
        # The saved serializer preserves the historical spelling even if the
        # new checking entry raises. Rebind solely within this exception seam.
        historical_verdict = standalone_verdict(kind, item)
        return _historical_item_command(kind, item, historical_verdict)


def reserved_item_command(policy, snapshot, kind, item, owner=None, *, address=None, suffix=""):
    # Identification selects a source using the game's observed command key.
    # Normalize it here so all item commands share the same checked serializer.
    kind = {'r': 'read', 'u': 'staff', 'z': 'rod', 'a': 'wand'}.get(kind, kind)
    if owner is None:
        # Consumption has no outstanding transfer claim of its own. A stale
        # last_reason must not borrow the owner of an item's pending deposit.
        owner = "consumption"
    verdict = reservation_verdict(policy, snapshot, item, owner, kind if kind == "overweight-surplus" else kind.split('-')[0])
    selected = (item, address) if address is not None else item
    key = checked_item_command(policy, kind, selected, verdict)
    return key + suffix if key is not None else None


def store_item_key(policy, snapshot, kind, item, owner, *, quantity, address=None):
    """The only composer of a store or Home item operation key.

    ``kind`` is ``sell``/``buy`` (a store) or ``deposit``/``withdraw`` (the
    Home); ``item`` is the stack the game offers (the pack stack for a sale or
    deposit, the shelf row for a purchase or withdrawal).  After the item
    selector the game asks, in this order (store/sell-order.cpp store_sell,
    store/purchase-order.cpp store_purchase):

    * the quantity, only when that stack holds more than one
      (``input_quantity``: the first digit replaces the default "1", Return
      accepts; asking-player.cpp input_quantity);
    * a store sale: prompt_to_sell's ``[Y/n]`` (answered ``y``); a store
      purchase: prompt_to_buy's ``[Y/n]`` (Return takes DEFAULT_Y); the Home
      asks nothing more.
    """
    if kind == "buy":
        fare = policy._outpost_return_fare(snapshot)
        # A split wand stack rounds charges in purchase-order.cpp; its actual
        # price may exceed the exported full-stack unit price. Without an
        # exact price, that partial purchase cannot spend a reserved fare.
        if (quantity <= 0 or item.price * quantity > snapshot.player.gold - fare
                or (fare and item.tval == TVAL_WAND and quantity < item.count)):
            return None
    if kind == "sell":
        allowed = outpost_fare_sale_quantity(policy, snapshot, item)
        if allowed is None:
            # Ordinary sale selection historically offers the whole pile when
            # its surplus is nonpositive. Preserve that for unreserved items;
            # only a scoped fare grant may release an actual reservation.
            allowed = max(0, item.count - policy._retention_reservation(snapshot, item))
        if not 0 < quantity <= allowed:
            return None
    confirmation = {"sell": "y", "buy": "\r", "deposit": "", "withdraw": ""}[kind]
    prefix = reserved_item_command(policy, snapshot, kind, item, owner, address=address)
    if prefix is None:
        return None
    return prefix + (f"{quantity}\r" if item.count > 1 else "") + confirmation
