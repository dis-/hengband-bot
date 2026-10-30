"""Morivant's Tower of Sorcery: the steps every Tower trip shares.

Shared by every Tower trip (first the Magic-Eater staff sequence,
``me_staff_sequence``):

 rumor    -- the inn rumor flow until Morivant (town 2) is listed in the
             exported ``visited_town_ids`` (what the inn teleport lists).
 travel   -- the inn teleport (``_town_teleport_key``).
 recharge -- lib/edit/towns/03_Morivant.jsonc building 8, action 'a'
             (BACT_RECHARGE_ALL): market/building-recharger.cpp
             building_recharge_all totals the price over the whole pack, asks
             input_check once and fills every staff and wand to its base pval
             (rod timeouts reset).  observed_input answers 'y' only at that
             observed question and leaves with ESC.
 fund     -- one explicit-target run of the existing fundraising owners.
"""

from __future__ import annotations

from functools import lru_cache
import json

from hengbot.baseitem_knowledge import find_baseitem_definitions
from hengbot.model import TVAL_ROD, TVAL_STAFF, TVAL_WAND
from hengbot.monrace_knowledge import _strip_jsonc
from hengbot.policy_constants import (
    LEAVE_STORE_KEY, MORIVANT_TOWN_ID, RUMOR_COST, RUMOR_GOLD_RESERVE,
    RUMOR_READS_PER_VISIT, TOWN_TELEPORT_COST,
)

# ItemEntity::can_recharge (baseitem-key.cpp): what 'a' recharges.
RECHARGEABLE_TVALS = (TVAL_STAFF, TVAL_WAND, TVAL_ROD)
UNKNOWN_ITEM_RECHARGE_FEE = 50  # building_recharge_all: +50 per unknown item
TOWER_OF_SORCERY = 8  # 03_Morivant.jsonc building 8: 'a' Recharge all items
RECHARGE_ALL_ACTION_KEY = "a"
RECHARGE_ALL_TAIL = RECHARGE_ALL_ACTION_KEY + "y" + LEAVE_STORE_KEY
# The owners' reasons of a posted 'a' + 'y' + ESC (observed_input composes it).
RECHARGE_ALL_REASONS = frozenset({"me-staff:recharge-all"})


@lru_cache(maxsize=1)
def device_definitions() -> dict:
    """(tval, sval) -> (base pval, level, cost) of every rechargeable kind."""
    path = find_baseitem_definitions()
    found = {}
    if path is not None:
        try:
            data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
            for entry in data.get("baseitems", data.get("items", [])):
                kind = entry.get("itemkind", entry)
                if int(kind["type_value"]) in RECHARGEABLE_TVALS:
                    found[(int(kind["type_value"]), int(kind["subtype_value"]))] = (
                        int(entry["parameter_value"]), int(entry["level"]), int(entry["cost"]))
        except (OSError, ValueError, KeyError, TypeError):
            found = {}
    return found


def recharge_all_price(item, definitions: dict, fallback: dict | None = None) -> int:
    """building_recharge_all's price of one pack item (an upper bound).

    An unaware kind is priced as the dearest kind of its tval and an unknown
    staff/wand as empty; a charging rod as fully charging (timeout is not
    exported, and a stack's timeout never exceeds number * base pval).
    ``fallback`` maps (tval, sval) to (base pval, level, cost) for kinds the
    definitions cannot supply.
    """
    kinds = ([definitions[(item.tval, item.sval)]] if item.aware and (item.tval, item.sval) in definitions
             else [value for (tval, _sval), value in definitions.items() if tval == item.tval])
    if not kinds and fallback and (item.tval, item.sval) in fallback:
        kinds = [fallback[(item.tval, item.sval)]]
    number = max(1, item.count)
    charges = item.charges if item.known else 0
    prices = []
    for base_pval, level, base_cost in kinds:
        if item.tval == TVAL_ROD:
            prices.append(level * 50 * number if item.charging else 0)
        elif item.tval == TVAL_STAFF:
            prices.append((base_pval - charges) * max(10, base_cost // 10 * number))
        else:
            prices.append((number * base_pval - charges) * max(10, base_cost // 10))
    price = max([0, *prices])
    return price + (0 if item.known else UNKNOWN_ITEM_RECHARGE_FEE)


def recharge_cost(snapshot, fallback: dict | None = None) -> int:
    """The Tower's 'a' total over every rechargeable pack item."""
    definitions = device_definitions()
    return sum(recharge_all_price(item, definitions, fallback) for item in snapshot.inventory
               if item.tval in RECHARGEABLE_TVALS and not item.is_equipment)


def wand_charges_after_recharge(item) -> int:
    """building-recharger.cpp: a wand stack is filled to number * base pval."""
    kind = device_definitions().get((item.tval, item.sval))
    if kind is None:
        return item.charges
    return max(item.charges, max(1, item.count) * kind[0])


def morivant_unlocked(snapshot) -> bool:
    visited = snapshot.visited_town_ids
    return visited is not None and MORIVANT_TOWN_ID in visited


def expedition_cost(snapshot, supplies: int, fallback: dict | None = None) -> int:
    """Fares to Morivant and back, the Tower's recharge and the supplies."""
    return 2 * TOWN_TELEPORT_COST + recharge_cost(snapshot, fallback) + supplies


def rumor_expedition_cost(snapshot, supplies: int, fallback: dict | None = None) -> int:
    """The rumor phase's total: the expedition plus the inn's reads."""
    return (expedition_cost(snapshot, supplies, fallback)
            + RUMOR_GOLD_RESERVE + RUMOR_COST * RUMOR_READS_PER_VISIT)


def rumor_key(policy, snapshot):
    """(key, whether a rumor batch was posted) of the inn rumor flow."""
    policy._town_travel_rumor_pending = MORIVANT_TOWN_ID
    key = policy._town_special_key(snapshot)
    return key, policy.last_reason == "town:rumor-batch"


def building_step(policy, snapshot, building: int):
    """(first step, whether that step enters the building)."""
    here = snapshot.grid_at(snapshot.player.position)
    if here is not None and here.building_type == building:
        # player-move.cpp enters a building only by moving onto it: step off
        # onto a plain grid, and the next board walks back in (D24).
        off = next((cell for cell in policy._walkable_neighbors(snapshot, snapshot.player.position)
                    if (grid := snapshot.grid_at(cell)) is not None and grid.building_type < 0
                    and grid.store_number < 0 and grid.building_special < 0
                    and not grid.has_entrance and not grid.has_quest_enter), None)
        return off, False
    position = (policy._town_map.building_position(building)
                if policy._town_map_active(snapshot) else None)
    policy._claim_target_capture = []
    try:
        step = policy._nearest_goal_step(
            snapshot, lambda grid: grid.building_type == building)
    finally:
        target = policy._take_claim_target()
    if step is None and position is not None:
        step = policy._town_map_goal_step(snapshot, position)
    if step is None:
        return None, False
    policy._declare_reach(position if position is not None else target)
    enters = step == position or (
        snapshot.grid_at(step) is not None
        and snapshot.grid_at(step).building_type == building)
    return step, enters


def start_fundraising_run(policy, snapshot, target: int) -> None:
    """Hand one explicit ``target``-gold run to the existing fundraising owners."""
    policy._supply_stockout_gold_target = target
    policy._planned_mining_runs = 1
    policy._mining_runs_completed = 0
    policy._identify_staff_mining_plan = False
    policy._recall_stockout_mining_plan = False
    policy._fundraising_mode = "prepare"
    policy._town_restock_suppressed = False
    policy._town_restock_waiting_for = ()
    policy._town_restock_wait_until = None
    policy._town_store_attempted.clear()
    policy._cross_town_shopping = None
    policy._retire_town_errand_plan_for_rebuild()
