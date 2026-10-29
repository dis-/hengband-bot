"""The Magic-Eater (class 16) staff sequence after quest 1.

Owner instructions 2026-10-30 (in order):
 1. 「魔道具術師でQ1クリア後の最初の採掘の目標を明示する。
     ・資金を貯めて鑑定の杖と財宝感知の杖を1本ずつ買う」
 2. 「その後、噂でモリバントへの移動を解禁、鑑定と財宝感知をチャージマックスにして取り込む」
 3. 「2本目は買わない。以降、鑑定と財宝感知は取り込みで賄う」

Steps (each observed on the board, never assumed):
 fund     -- the first mining run's explicit gold target is the observed
             Magic-shop (or Black-market) price of one Staff of Identify plus
             one Staff of Detect Treasure.
 buy      -- exactly one of each, through the shop's purchase hooks.
 rumor    -- the existing inn rumor flow until Morivant (town 2) is listed in
             the exported ``visited_town_ids`` (what the inn teleport lists).
 travel   -- the inn teleport to Morivant.
 recharge -- Morivant's Tower of Sorcery (lib/edit/towns/03_Morivant.jsonc
             building 8, action 'r' = BACT_RECHARGE) up to the base pval,
             which market/building-recharger.cpp treats as the maximum.
 absorb   -- 'G' (mind-magic-eater.cpp import_magic_device); a staff's first
             absorption sets the power's count to its charges.
 return   -- the inn teleport back to the Outpost.
Afterwards both powers replace the two staffs: no further purchase, the
identify-staff readiness and treasure-detection stock count them, and the
identify / detect commands use ``m`` ``A`` and the power (cmd-magiceat.cpp
letters are I2A(sval)).  Any step that cannot proceed starts one bounded
fundraising run or ends with a named ``quest:blocked:me-staff:`` stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
import json

from hengbot.baseitem_knowledge import find_baseitem_definitions
from hengbot.magic_eater import ABSORB_REASON
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import (
    STORE_BLACK, STORE_MAGIC, SV_STAFF_IDENTIFY, TVAL_STAFF,
)
from hengbot.monrace_knowledge import _strip_jsonc
from hengbot.policy_constants import (
    LEAVE_STORE_KEY, MORIVANT_TOWN_ID, OUTPOST_TOWN_ID, QUEST_STATUS_FINISHED,
    QUEST_STATUS_REWARDED, REST_MACRO, RUMOR_COST, RUMOR_GOLD_RESERVE,
    RUMOR_READS_PER_VISIT, STORE_STUCK_LIMIT, TOWN_TELEPORT_COST, WAIT_KEY,
)
from hengbot.protocol import PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY


SV_STAFF_DETECT_GOLD = 10  # sv-definition/sv-staff-types.h
SEQUENCE_SVALS = (SV_STAFF_IDENTIFY, SV_STAFF_DETECT_GOLD)
# cmd-magiceat.cpp prints and accepts I2A(sval) for every power.
POWER_LETTER = {SV_STAFF_IDENTIFY: "f", SV_STAFF_DETECT_GOLD: "k"}
# The power list prints the baseitem name (BaseitemDefinitions ids 326, 301).
POWER_NAMES = {SV_STAFF_IDENTIFY: ("鑑定", "Perception"),
               SV_STAFF_DETECT_GOLD: ("財宝感知", "Treasure Location")}
# Base pval and cost when the definitions cannot be read (ids 326 and 301).
_FALLBACK_BASE = {SV_STAFF_IDENTIFY: (21, 400), SV_STAFF_DETECT_GOLD: (19, 200)}
TOWER_OF_SORCERY = 8  # 03_Morivant.jsonc building 8: 'r' Recharge item
RECHARGE_ACTION_KEY = "r"
RUMOR_BATCH_LIMIT = 10  # 400 rumors: a visible stop instead of an endless inn
FUNDRAISE_RUN_LIMIT = 6
ATTEMPT_LIMIT = 3

REASON = "me-staff:"
STOP_REASON = "quest:blocked:me-staff"
IDENTIFY_POWER_KEY = "mA" + POWER_LETTER[SV_STAFF_IDENTIFY]
DETECT_POWER_KEY = "mA" + POWER_LETTER[SV_STAFF_DETECT_GOLD]
DETECT_REASON = "fundraise:me-detect-treasure"
BUY_RUNG = "me-staff:buy"


@dataclass
class MeStaffSequence:
    """The sequence's own facts; the board supplies everything else."""
    absorbed: dict = field(default_factory=dict)   # sval -> absorbed count
    bought: frozenset = frozenset()
    fundraise_runs: int = 0
    fundraise_target: int | None = None
    shelf_after_turn: int = -1
    rumor_batches: int = 0
    attempts: dict = field(default_factory=dict)   # (step, sval) -> count
    pending: tuple | None = None                   # (step, sval, charges)
    empty_turn: dict = field(default_factory=dict)  # sval -> turn seen empty
    progress: tuple | None = None
    positions: dict = field(default_factory=dict)
    failure: str | None = None


@lru_cache(maxsize=1)
def _base_definitions() -> dict:
    path = find_baseitem_definitions()
    found = {}
    if path is not None:
        try:
            data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
            for entry in data.get("baseitems", data.get("items", [])):
                kind = entry.get("itemkind", entry)
                if (int(kind["type_value"]) == TVAL_STAFF
                        and int(kind["subtype_value"]) in SEQUENCE_SVALS):
                    found[int(kind["subtype_value"])] = (
                        int(entry["parameter_value"]), int(entry["cost"]))
        except (OSError, ValueError, KeyError, TypeError):
            found = {}
    return {sval: found.get(sval, _FALLBACK_BASE[sval]) for sval in SEQUENCE_SVALS}


def max_charges(sval: int) -> int:
    """building-recharger.cpp: a staff is full at its base pval."""
    return _base_definitions()[sval][0]


def recharge_price_per_charge(item) -> int:
    """building-recharger.cpp: max(10, base cost / 10 * number) per charge."""
    return max(10, _base_definitions()[item.sval][1] // 10 * max(1, item.count))


def recharge_cost(snapshot) -> int:
    return sum(max(0, max_charges(item.sval) - item.charges) * recharge_price_per_charge(item)
               for item in carried_staffs(snapshot).values())


def state(policy) -> MeStaffSequence:
    record = getattr(policy, "_me_staff_sequence", None)
    if record is None:
        record = policy._me_staff_sequence = MeStaffSequence()
    return record


def applies(policy, snapshot) -> bool:
    """Class 16 after Q1 was rewarded, on protocol-3 boards."""
    if (snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER
            or getattr(snapshot, "protocol_version", PROTOCOL_LEGACY) < PROTOCOL_SCREEN_PARITY
            or not getattr(snapshot, "quests", None)):
        return False
    q1 = policy._known_fixed_quests(snapshot).get(1)
    return q1 is not None and q1.status in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}


def is_sequence_staff(item) -> bool:
    return item.tval == TVAL_STAFF and item.sval in SEQUENCE_SVALS and item.aware


def carried_staffs(snapshot) -> dict:
    staffs = {}
    for item in snapshot.inventory:
        if is_sequence_staff(item) and item.known and item.sval not in staffs:
            staffs[item.sval] = item
    return staffs


def absorbed(policy, sval: int) -> bool:
    record = getattr(policy, "_me_staff_sequence", None)
    return record is not None and sval in record.absorbed


def complete(policy) -> bool:
    return all(absorbed(policy, sval) for sval in SEQUENCE_SVALS)


def absorbed_charges(policy, snapshot, sval: int) -> int:
    """Charges the absorbed power serves, as last read from its own list.

    The power list is observed only when it is cast (executor answers). A
    power seen empty on this board serves nothing until game time passes
    (it regenerates, and an inn rest refills it); otherwise its count does.
    """
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER or not absorbed(policy, sval):
        return 0
    record = state(policy)
    listed = getattr(snapshot, "magic_eater_power_list", None)
    if isinstance(listed, dict) and listed.get("kind") == "staff":
        for row in listed.get("rows", ()):
            if row.get("name") in POWER_NAMES[sval] and row.get("current") == 0:
                record.empty_turn[sval] = snapshot.turn
    if record.empty_turn.get(sval) == snapshot.turn:
        return 0
    return record.absorbed[sval]


def power_key(policy, snapshot, sval: int) -> str | None:
    """``m A <letter>`` for an absorbed power that may serve this board."""
    player = snapshot.player
    if (absorbed_charges(policy, snapshot, sval) <= 0 or snapshot.store is not None
            or player.blind or player.confused or player.hallucinated or player.paralyzed):
        return None
    return "mA" + POWER_LETTER[sval]


def identify_power_available(policy, snapshot) -> bool:
    return power_key(policy, snapshot, SV_STAFF_IDENTIFY) is not None


def identify_power_command(policy, snapshot, target, *, full: bool) -> str | None:
    """The absorbed Identify power instead of a staff (never *Identify*)."""
    if full or getattr(target, "slot", None) not in "abcdefghijklmnopqrstuvw":
        return None
    key = power_key(policy, snapshot, SV_STAFF_IDENTIFY)
    return key + target.slot if key is not None else None


def purchase_excluded(policy, snapshot, item) -> bool:
    """「2本目は買わない」: class 16 never buys these staffs after Q1 itself."""
    return is_sequence_staff(item) and applies(policy, snapshot)


def retains(policy, snapshot, item) -> bool:
    """A bought staff stays carried until it is recharged and absorbed."""
    return (is_sequence_staff(item) and applies(policy, snapshot)
            and not absorbed(policy, item.sval))


# -- the shop: same hook points as the opening route's purchase ------------

def _fresh_pages(policy, snapshot) -> dict:
    record = state(policy)
    town = policy._effective_town_id(snapshot)
    pages = {}
    for store in (STORE_MAGIC, STORE_BLACK):
        page = policy._town_supplier_stock.get(store)
        observed = policy._town_supplier_stock_observations.get(store)
        if (page is not None and observed is not None and observed[0] == town
                and observed[1] >= record.shelf_after_turn):
            pages[store] = page
    if snapshot.store is not None and snapshot.store.store_type in (STORE_MAGIC, STORE_BLACK):
        pages[snapshot.store.store_type] = snapshot.store
    return pages


def offers(policy, snapshot) -> dict:
    """sval -> (store, cheapest observed offer) for each staff still needed."""
    needed = [sval for sval in SEQUENCE_SVALS
              if not absorbed(policy, sval) and sval not in carried_staffs(snapshot)]
    found = {}
    for store, page in _fresh_pages(policy, snapshot).items():
        for item in page.items:
            if (item.count > 0 and item.tval == TVAL_STAFF and item.sval in needed
                    and (item.sval not in found or item.price < found[item.sval][1].price)):
                found[item.sval] = (store, item)
    return found


def buy_target(policy, snapshot) -> int | None:
    """The explicit gold target: one of each still-needed staff, as priced."""
    needed = [sval for sval in SEQUENCE_SVALS
              if not absorbed(policy, sval) and sval not in carried_staffs(snapshot)]
    found = offers(policy, snapshot)
    if not needed or any(sval not in found for sval in needed):
        return None
    return sum(found[sval][1].price for sval in needed)


def shopping(policy, snapshot) -> bool:
    return (snapshot.store is not None and applies(policy, snapshot)
            and _phase(policy, snapshot) == "buy")


def purchase(policy, snapshot):
    """The shelf row to buy on this page (quantity one), or None."""
    if not shopping(policy, snapshot):
        return None
    target = buy_target(policy, snapshot)
    if target is None or snapshot.player.gold < target:
        return None
    for sval in SEQUENCE_SVALS:
        offer = offers(policy, snapshot).get(sval)
        if offer is not None and offer[0] == snapshot.store.store_type:
            return next((item for item in snapshot.store.items if item == offer[1]), None)
    return None


# -- the town owner --------------------------------------------------------

def _phase(policy, snapshot) -> str:
    if complete(policy):
        return "return" if policy._effective_town_id(snapshot) != OUTPOST_TOWN_ID else "done"
    carried = carried_staffs(snapshot)
    missing = [sval for sval in SEQUENCE_SVALS
               if not absorbed(policy, sval) and sval not in carried]
    if missing:
        return "buy"
    visited = snapshot.visited_town_ids
    if visited is None or MORIVANT_TOWN_ID not in visited:
        return "rumor"
    if policy._effective_town_id(snapshot) != MORIVANT_TOWN_ID:
        return "travel"
    if any(item.charges < max_charges(sval) for sval, item in carried.items()):
        return "recharge"
    return "absorb"


def _stop(policy, detail: str) -> str:
    state(policy).failure = detail
    policy.last_reason = STOP_REASON
    return ""


def _fundraise(policy, snapshot, target: int, why: str) -> str:
    """One existing fundraising run whose objective is ``target`` gold."""
    record = state(policy)
    if record.fundraise_runs >= FUNDRAISE_RUN_LIMIT:
        return _stop(policy, f"fundraise-limit:{why}:{target}")
    record.fundraise_runs += 1
    record.fundraise_target = target
    record.shelf_after_turn = snapshot.turn
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
    policy.last_reason = f"{REASON}fundraise:{why}:{target}"
    return WAIT_KEY


def _fundraising_owns(policy) -> bool:
    record = state(policy)
    return (policy._fundraising_mode in {"prepare", "mine", "scavenge"}
            and record.fundraise_target is not None
            and getattr(policy, "_supply_stockout_gold_target", None) == record.fundraise_target)


def _attempt(policy, step: str, sval: int) -> bool:
    record = state(policy)
    count = record.attempts.get((step, sval), 0) + 1
    record.attempts[(step, sval)] = count
    return count <= ATTEMPT_LIMIT


def _settle_pending(policy, snapshot) -> None:
    """Read the previous recharge/absorb from this board."""
    record = state(policy)
    if record.pending is None:
        return
    step, sval, charges = record.pending
    record.pending = None
    item = carried_staffs(snapshot).get(sval)
    if step == "absorb" and item is None:
        record.absorbed = {**record.absorbed, sval: charges}
    if step == "recharge" and item is not None and item.charges > charges:
        record.attempts.pop(("recharge", sval), None)


def _travel(policy, snapshot, destination: int, step: str) -> str:
    key = policy._town_teleport_key(
        snapshot, destination, producer="quest-request", reason=f"{REASON}{step}")
    if key is None:
        return _stop(policy, f"{step}-unavailable:{policy.last_reason}")
    return key


def _building_step(policy, snapshot, building: int):
    """(first step, whether that step enters the building)."""
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


def _recharge_key(policy, snapshot) -> str:
    """Recharge one staff per Tower visit; the next board reads its charges."""
    for sval, item in sorted(carried_staffs(snapshot).items()):
        missing = max_charges(sval) - item.charges
        if missing <= 0:
            continue
        if snapshot.player.gold < missing * recharge_price_per_charge(item) + TOWN_TELEPORT_COST:
            # Return with the reserved fare; the Outpost travel gate funds
            # the recharge with one explicit-target run.
            return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-for-funds")
        step, enters = _building_step(policy, snapshot, TOWER_OF_SORCERY)
        if step is None:
            return _stop(policy, "tower-of-sorcery-route-unavailable")
        if not enters:
            policy.last_reason = f"{REASON}approach-tower"
            return policy._step_toward(snapshot, step)
        if not _attempt(policy, "recharge", sval):
            return _stop(policy, f"recharge-no-progress:{sval}")
        state(policy).pending = ("recharge", sval, item.charges)
        policy.last_reason = f"{REASON}recharge:{sval}"
        # 'r' item, the charge count (input_quantity), then leave the Tower.
        return policy._step_toward(
            snapshot, step,
            tail=RECHARGE_ACTION_KEY + item.slot + f"{missing}\r" + LEAVE_STORE_KEY)
    return _stop(policy, "recharge-nothing-to-do")


def _absorb_key(policy, snapshot) -> str:
    player = snapshot.player
    if (player.hp < player.max_hp or player.blind or player.confused
            or player.poisoned or player.cut or player.stunned or player.hallucinated):
        policy.last_reason = f"{REASON}recover"
        return REST_MACRO
    sval, item = sorted(carried_staffs(snapshot).items())[0]
    if not _attempt(policy, "absorb", sval):
        return _stop(policy, f"absorb-no-progress:{sval}")
    state(policy).pending = ("absorb", sval, item.charges)
    policy.last_reason = ABSORB_REASON
    return "G" + item.slot


def _no_progress(policy, snapshot, phase) -> bool:
    record = state(policy)
    progress = (phase, snapshot.player.gold,
                tuple((it.slot, it.name, it.count, it.charges) for it in snapshot.inventory))
    if record.progress != progress:
        record.progress = progress
        record.positions = {}
    position = snapshot.player.position
    record.positions[position] = record.positions.get(position, 0) + 1
    return record.positions[position] >= STORE_STUCK_LIMIT


def town_key(policy, snapshot, hostiles) -> str | None:
    """Sole non-emergency town owner while the sequence is unfinished."""
    if not snapshot.in_town or snapshot.store is not None or not applies(policy, snapshot):
        return None
    record = state(policy)
    _settle_pending(policy, snapshot)
    if record.failure:
        return _stop(policy, record.failure)
    phase = _phase(policy, snapshot)
    if phase == "done":
        return None
    if _fundraising_owns(policy):
        # The existing fundraising owners carry out the run.
        return None
    if record.fundraise_target is not None:
        record.fundraise_target = None
    if policy._physical_adjacent_hostiles(snapshot):
        return None
    if _no_progress(policy, snapshot, phase):
        return _stop(policy, f"no-progress:{phase}")
    gold = snapshot.player.gold
    if phase == "buy":
        if policy._effective_town_id(snapshot) != OUTPOST_TOWN_ID:
            return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-to-shop")
        target = buy_target(policy, snapshot)
        if target is None:
            if STORE_MAGIC not in _fresh_pages(policy, snapshot):
                step = policy._shopping_approach_step(
                    snapshot, store_type=STORE_MAGIC, requester="quest-request")
                if step is None:
                    return _stop(policy, "magic-shop-route-unavailable")
                policy.last_reason = "shop:approach"
                key = policy._shopping_approach_key(snapshot, step, "shop:travel")
                return key if key is not None else _stop(policy, "magic-shop-operation-unavailable")
            # Observed shelf without one of the staffs: one run passes the
            # restock time; its gold target is the staffs' base estimate.
            estimate = sum(_base_definitions()[sval][1] * 2 for sval in SEQUENCE_SVALS
                           if sval not in carried_staffs(snapshot))
            return _fundraise(policy, snapshot, max(gold + 1, estimate), "staff-stockout")
        if gold < target:
            return _fundraise(policy, snapshot, target, "staffs")
        offer = next(offer for sval, offer in sorted(offers(policy, snapshot).items()))
        step = policy._shopping_approach_step(snapshot, store_type=offer[0], requester="quest-request")
        if step is None:
            return _stop(policy, f"store-{offer[0]}-route-unavailable")
        policy.last_reason = "shop:approach"
        key = policy._shopping_approach_key(snapshot, step, "shop:travel")
        return key if key is not None else _stop(policy, "shop-operation-unavailable")
    record.bought = record.bought | frozenset(carried_staffs(snapshot))
    expedition = 2 * TOWN_TELEPORT_COST + recharge_cost(snapshot)
    if phase == "rumor":
        needed = expedition + RUMOR_GOLD_RESERVE + RUMOR_COST * RUMOR_READS_PER_VISIT
        if gold < needed:
            return _fundraise(policy, snapshot, needed, "rumor-travel-recharge")
        if record.rumor_batches >= RUMOR_BATCH_LIMIT:
            return _stop(policy, "morivant-rumor-exhausted")
        policy._town_travel_rumor_pending = MORIVANT_TOWN_ID
        key = policy._town_special_key(snapshot)
        if policy.last_reason == "town:rumor-batch":
            record.rumor_batches += 1
        return key
    if phase == "travel":
        if policy._effective_town_id(snapshot) == OUTPOST_TOWN_ID and gold < expedition:
            return _fundraise(policy, snapshot, expedition, "travel-recharge")
        return _travel(policy, snapshot, MORIVANT_TOWN_ID, "travel-morivant")
    if phase == "recharge":
        return _recharge_key(policy, snapshot)
    if phase == "absorb":
        return _absorb_key(policy, snapshot)
    return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-outpost")
