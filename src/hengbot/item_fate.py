"""What may leave the character's hands: the one disposal answer (owner 2026-11-04).

Owner, on the ranking: per slot, by sale value, rank 21+ may be sold any time,
ranks 11-20 when room is needed, the top 10 are kept, artifacts are not sold.
When only the top 10 are left: 「消耗品や不用品などを整理。装備は売らない。」
When selling cannot get under the weight limit: 「基本的には上限を超えない設定なので、
停止して調査」, so the named weight stop stays.

Every sale, Home take and destroy path asks here: ``gear_tier`` for the ranking,
``held`` and ``stock_reserved`` for the gates all of them share, and the order
functions for what goes first.  The consumable and Magic-Eater device tables
keep their own modules.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from hengbot import spare_gear, town_pack_budget
from hengbot.baseitem_knowledge import item_base_cost
from hengbot.item_reservation import decision_memo, item_available
from hengbot.model import SV_STAFF_IDENTIFY, TVAL_STAFF
from hengbot.store_sale import known_sale_value

KEEP, ROOM, ANY = "keep", "room", "any"
KEPT_RANKS = 10
ROOM_RANKS = 20

SLOT_BY_TVAL = {
    19: "launcher", 20: "digger", 21: "melee", 22: "melee", 23: "melee",
    30: "feet", 31: "arms", 32: "head", 33: "head", 34: "shield", 35: "cloak",
    36: "body", 37: "body", 38: "body", 40: "neck", 45: "ring",
}


def sale_value(policy: Any, item: Any) -> int:
    """The known per-item value every ranking and order compares."""
    return max(0, known_sale_value(item, item_base_cost(item, policy._baseitem_costs)) or 0)


def _ranks(policy: Any, snapshot: Any) -> dict:
    """Signature -> best rank in its slot, over worn, pack and Home rows."""
    rows: dict[str, list] = {}
    for item in (*snapshot.equipment, *snapshot.inventory, *policy._home_knowledge_items):
        slot = SLOT_BY_TVAL.get(item.tval)
        if slot is not None and item.known and not item.is_artifact and getattr(item, "slot", None) != "home-surplus":
            rows.setdefault(slot, []).append(
                (-sale_value(policy, item), policy._item_signature(item)))
    ranks: dict = {}
    for row in rows.values():
        for position, (_, signature) in enumerate(sorted(row), 1):
            ranks.setdefault(signature, position)
    return ranks


def gear_tier(policy: Any, snapshot: Any, item: Any) -> str:
    """KEEP, ROOM (11-20) or ANY (21+); anything unranked is kept.

    Without a current Home census the rank is unknown, so nothing is released,
    except the ware the relief already chose from a census and has taken out.
    """
    if item.is_artifact or not item.known or SLOT_BY_TVAL.get(item.tval) is None:
        return KEEP
    if not policy._home_knowledge_current:
        relief = policy._home_full_relief or {}
        return ROOM if relief.get("rank_released") == policy._item_signature(item) else KEEP
    ranks = decision_memo(policy, "gear-ranks", snapshot, None, lambda: _ranks(policy, snapshot))
    rank = ranks.get(policy._item_signature(item))
    if rank is None:
        return KEEP
    return KEEP if rank <= KEPT_RANKS else ROOM if rank <= ROOM_RANKS else ANY


def gear_surplus(policy: Any, snapshot: Any, item: Any) -> bool:
    """May this piece go when room or weight relief is needed?  All classes."""
    if not item.is_equipment or item.is_ammo:
        # Ammunition has its own quantity/launcher reservation, applied by callers.
        return True
    if policy._sale_retains_digging_tool(snapshot, item):
        return False
    if (item.is_torch and item.known and item.fuel <= 0) or policy._is_spare_lantern(snapshot, item):
        return True
    if gear_tier(policy, snapshot, item) == KEEP:
        return False
    return item.is_digging_tool or spare_gear.released(policy, snapshot, item)


def held(policy: Any, snapshot: Any, item: Any, owner: str, sink: str, *, known: bool = True) -> bool:
    """The gate every disposal path shares; ``known`` also asks for identification."""
    return bool(
        not item_available(policy, snapshot, item, owner, sink)
        or item.is_bounty
        or policy._home_disposal.decision(policy._item_signature(item)) == "keep"
        or (known and (not item.known or policy._disposal_protected_by_identification(item))))


def empty_identify_staff(item: Any) -> bool:
    return (item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
            and max(item.charges, item.pval) == 0)


def stock_reserved(policy: Any, snapshot: Any, probe: Any, item: Any) -> bool:
    """Retention, ownership and the purchase ladder claim this stock."""
    return bool(
        policy._retention_reservation(probe, item) > 0
        or policy._home_full_equipment_reserved(snapshot, item)
        or (policy._item_matches_purchase_rung(probe, item) and not empty_identify_staff(item)))


def relief_order(policy: Any, snapshot: Any, item: Any) -> tuple:
    """Rank 21+, then 11-20, then surplus consumables; cheapest first in each."""
    if not item.is_equipment or item.is_ammo:
        group = 2
    else:
        group = 0 if gear_tier(policy, snapshot, item) == ANY else 1
    return (group, sale_value(policy, item), policy._item_signature(item))


def weight_relief_order(policy: Any, snapshot: Any, candidates: list) -> list:
    """The overweight rows: gear first when it alone clears the excess.

    ``candidates`` are the relief's cheapest-first (value, signature, item,
    count, stores) rows; each group keeps that order.
    """
    limit = policy._inventory_weight_limit(snapshot)
    gear = [entry for entry in candidates
            if entry[2].is_equipment and not entry[2].is_ammo]
    if limit is None or sum(entry[2].weight * entry[3] for entry in gear) < (
            policy._inventory_weight(snapshot) - limit):
        return candidates
    return [*gear, *(entry for entry in candidates if entry not in gear)]


def home_take_blocked(snapshot: Any) -> bool:
    """No one-slot Home take is admitted: the pack must shrink first."""
    return not town_pack_budget.permits(snapshot, 1)


def can_identify_now(policy: Any, snapshot: Any, item: Any) -> bool:
    """10-31 「鑑定待ちの装備は預ける」: a take for identification needs a source now."""
    from hengbot.me_staff_sequence import identify_power_command
    full = bool(item.known)
    return (identify_power_command(policy, snapshot, replace(item, slot="a"), full=full) is not None
            or policy._carried_identification_source(snapshot, full=full) is not None)
