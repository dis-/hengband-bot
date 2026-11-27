"""An equipment swap never takes out of Home what the kept pack cannot carry.

n1-c life-202 2026-11-12 17:18: the weight relief shelved the pack's light crossbow (110) at
the overweight Home (1735 / 1350, ``adj_str_wgt[17] * 50``, player-status.cpp
``calc_weight_limit``; weights in 0.1 lb), and the equipment transaction of the same visit took
it straight back out to wear it in place of the sling (+105), over a pack the retention keeps
(torches, potions, scrolls): the visit ended ``town:blocked:survival:inventory_weight_ready``.
Weight is no equipment comparison criterion (AGENTS.md), so the optimizer cannot see this;
the transaction asks before it begins.

``withdraw_overload``: the weight the swap leaves once every removable unit is shed.  The kept
weight now is the carried weight less the retention surplus of the pack; the session's remaining
actions add each withdrawal and drop each deposit of worn gear (a pack deposit is surplus
already, or kept weight leaving); a crossbow the swap puts on releases the reserved torches
(``torch_release``).  Whether that load may go is the overweight answer of the town
(``overweight_departure.swap_departs``, MAINTAINABILITY.md 3): within the weight that costs no
speed once the reserved quantities the relief may shed are shed.  The relief sheds them after
the swap and gives way at the same weight, so it never undoes the swap it admitted.

``close_unfit_swap``: the question is asked once, before the session's first action.  A swap
that would not depart is dropped for this town visit before anything is taken off (the current
gear stays, ``_equipment_transaction_visit_closure`` keeps the plan from being made again, and
the visit goes on: MAINTAINABILITY.md 2).  A session already under way is finished: its first
action has taken gear off, and the relief answers the load after it.  n1-a life-545 2026-11-27
16:59: the refusal was asked at the withdrawal, after the axe (25.0 lb) was deposited, for a
lance (30.0 lb) that left 168.1 lb of a 165.0 lb limit (no speed lost); the blocked session
re-entered Home for the same refusal until livelock:exhausted.
"""
from __future__ import annotations

from typing import Any

from hengbot import overweight_departure, torch_release

BOW_SLOT = "bow"
REFUSAL = "withdraw-overweight"


def _unit_weight(item: Any) -> int:
    return max(0, int(getattr(item, "weight", 0) or 0))


def withdraw_overload(policy: Any, snapshot: Any, session: Any) -> dict | None:
    """The weights of a refused swap (module docstring), or None when it may go on."""
    limit = policy._inventory_weight_limit(snapshot)
    if limit is None or session is None:
        return None
    weight = policy._inventory_weight(snapshot)
    chosen = []
    for item in snapshot.inventory:
        surplus = policy._retention_surplus(snapshot, item)
        if surplus > 0 and _unit_weight(item) > 0:
            chosen.append((0, policy._item_signature(item), item, surplus, ()))
    kept = weight - sum(_unit_weight(entry[2]) * entry[3] for entry in chosen)
    catalog = {owned.id: owned for owned in policy._equipment_catalog.items}
    bow = next((item for item in snapshot.equipment if item.slot == BOW_SLOT), None)
    delta = 0
    for action in session.plan.actions[session.index:]:
        owned = catalog.get(action.item_id)
        if owned is None:
            continue
        if action.kind == "withdraw":
            delta += _unit_weight(owned.item)
        elif action.kind == "deposit":
            if owned.origin == "equipped":
                delta -= _unit_weight(owned.item)
            elif owned.origin == "pack" and policy._retention_surplus(snapshot, owned.item) <= 0:
                delta -= _unit_weight(owned.item)
        elif action.kind == "equip" and action.target_slot == BOW_SLOT:
            bow = owned.item
    if torch_release.releases(bow) and not torch_release.released(policy, snapshot):
        delta -= sum(_unit_weight(item) * policy._retention_reservation(snapshot, item)
                     for item in snapshot.inventory if item.is_torch)
    after = kept + delta
    if after <= limit or after <= kept or overweight_departure.swap_departs(
            policy, snapshot, after, chosen):
        return None
    return {"limit": limit, "weight": weight, "kept": kept, "kept_after": after,
            "tolerated": overweight_departure.tolerated_weight(limit)}


def close_unfit_swap(policy: Any, snapshot: Any, session: Any) -> bool:
    """Drop a not yet begun swap whose load would not depart (module docstring); True if dropped."""
    if (session is None or session.index != 0 or session.pending_action is not None
            or not any(action.kind == "withdraw" for action in session.plan.actions)):
        return False
    overload = withdraw_overload(policy, snapshot, session)
    if overload is None:
        return False
    target = session.target_loadout_id
    policy._abandon_blocked_equipment_transaction(snapshot)
    policy._equipment_transaction_visit_closure = {
        "epoch": policy._town_visit_epoch,
        "reason": REFUSAL,
        "target_loadout_id": target,
        "turn": snapshot.turn,
        **overload,
    }
    policy.last_reason = f"equipment-transaction:{REFUSAL}"
    return True
