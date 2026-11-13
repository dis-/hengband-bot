"""An equipment swap never takes out of Home what the kept pack cannot carry.

n1-c life-202 2026-11-12 17:18: the weight relief shelved the pack's light crossbow (110) at
the overweight Home (1735 / 1350, ``adj_str_wgt[17] * 50``, player-status.cpp
``calc_weight_limit``; weights in 0.1 lb), and the equipment transaction of the same visit took
it straight back out to wear it in place of the sling (+105), over a pack the retention keeps
(torches, potions, scrolls): the visit ended ``town:blocked:survival:inventory_weight_ready``.
Weight is no equipment comparison criterion (AGENTS.md), so the optimizer cannot see this;
the transaction asks before its Home withdrawal.

``withdraw_overload``: the weight the swap leaves once every removable unit is shed, compared
with the limit.  The kept weight now is the carried weight less the retention surplus of the
pack; the session's remaining actions add each withdrawal and drop each deposit of worn gear
(a pack deposit is surplus already, or kept weight leaving); a crossbow the swap puts on
releases the reserved torches (``torch_release``).  A swap that ends over the limit and heavier
than now is refused (the session blocks; the abandonment keeps the item at Home this visit).
"""
from __future__ import annotations

from typing import Any

from hengbot import torch_release

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
    removable = sum(_unit_weight(item) * policy._retention_surplus(snapshot, item)
                    for item in snapshot.inventory)
    kept = weight - removable
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
    if after <= limit or after <= kept:
        return None
    return {"limit": limit, "weight": weight, "kept": kept, "kept_after": after}
