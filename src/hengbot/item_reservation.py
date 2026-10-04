"""Decision-local views of existing item reservations; no checkpoint state."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import logging

from hengbot.equipment_optimizer import equipment_identity


@dataclass(frozen=True)
class ReservationVerdict:
    sink: str
    owner: str | None = None
    quantity: int | None = None
    ambiguous: bool = False

    @property
    def reason(self):
        return f"ownership:item-reserved:{self.sink}:{self.owner}"


_decision = ContextVar("item_reservation_decision", default=None)


def reservation_decision(function):
    @wraps(function)
    def run(policy, snapshot):
        token = _decision.set({"policy": policy, "view": None, "shadow": []})
        try:
            return function(policy, snapshot)
        finally:
            _decision.reset(token)
    return run


def reservation_shadow(policy):
    state = _decision.get()
    return list(state["shadow"]) if state and state["policy"] is policy else []


def _row_key(snapshot, item):
    carried = any(item is candidate for candidate in (*snapshot.inventory, *snapshot.equipment))
    return equipment_identity(item), carried


def _reservation_row(policy, snapshot, item, view):
    signature = policy._item_signature(item)
    owners = []
    if (policy._equipment_transaction_deposit_owns_item(item)
            or policy._equipment_transaction_owns_item(item)):
        owners.append("equipment-txn")
    if signature in view["retry"]:
        owners.append("home-full-retry")
    if signature in view["deposit"]:
        owners.append("home-visit")
    if signature in view["withdraw"]:
        owners.append("home-errand")
    if policy._home_reserve_deposit_item(item):
        owners.append("home-reserve")
    # Retention has a quantity, never an invented owner.
    retained = (not _row_key(snapshot, item)[1]
                and policy._equipment_disposal_reserved(snapshot, item))
    return tuple(owners), retained


def _view(policy, snapshot):
    """Materialize identity sets once; equivalent synthetic items share rows."""
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
    view = {"retry": retry, "deposit": deposit_signatures,
            "withdraw": withdraw_signatures, "rows": {}}
    items = (*snapshot.inventory, *snapshot.equipment, *policy._home_knowledge_items)
    for item in items:
        key = _row_key(snapshot, item)
        if key not in view["rows"]:
            view["rows"][key] = _reservation_row(policy, snapshot, item, view)
    return view


def item_reserved_by_other(policy, snapshot, item, work) -> ReservationVerdict | None:
    """Pure ownership predicate. work is (owner, sink); None means unreserved."""
    owner, sink = work
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
        if sink == "deposit" and reserved_owner in {"home-full-retry", "home-reserve"}:
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
    """OFF exceptions preserve historical behavior; conflicts skip in both modes."""
    try:
        denied = item_reserved_by_other(policy, snapshot, item, (owner, sink))
        if denied is not None and denied.owner is not None:
            _shadow(policy, {"would_stop": denied.reason, "ambiguous": denied.ambiguous})
            if getattr(policy, "_town_claim_bar_enforced", False):
                policy.last_reason = denied.reason
            return denied
        if denied is not None:
            return denied
        quantity = (policy._retention_surplus(snapshot, item)
                    if sink in {"sell", "deposit", "destroy", "weight-deposit", "home-full-sale"}
                    else None)
        return ReservationVerdict(sink, quantity=quantity)
    except Exception as error:
        if getattr(policy, "_town_claim_bar_enforced", False):
            policy.last_reason = f"ownership:item-reserved:{sink}:predicate-error"
            _shadow(policy, {"would_stop": policy.last_reason, "error": type(error).__name__})
            return ReservationVerdict(sink, "predicate-error")
        _shadow(policy, {"error": type(error).__name__, "sink": sink})
        return ReservationVerdict(sink)


def item_available(policy, snapshot, item, owner, sink):
    return reservation_verdict(policy, snapshot, item, owner, sink).owner is None
