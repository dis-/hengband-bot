"""Gear the next departure does not use waits at Home (one owning rule).

Owner 2026-11-04: 「使わない装備をキープしたままダンジョンに出発している。自宅に
仕舞うようにしたい。」 and 「採掘に行かない時はシャベルも仕舞う」.  n1-c life-130:
with the character sheet rejected no optimizer target ever released the pack's
armour, and a good weapon was released by nothing but pack pressure, so
identified gear left town on four departures.

Three questions, asked by Home's deposit finder, by the transaction plans and
by their Home executors:

* ``released``: may this pack item be shelved as spare gear?  The optimizer's
  choice stays; so does a good weapon while no real weapon is wielded (mining
  displaced it, and the re-arm needs it).  With a target known the rest is
  spare; with the character sheet rejected no target is coming.  A launcher that
  only waits for its ammunition stays (launcher_upgrade).
* ``digger_stays_carried``: a digging tool is carried only for mining.
* ``stow_pending``: the departure leaf.  True only while Home can still take
  the gear this visit, so it can delay a departure but never stop one.

Gear picked up during a dive is not touched: it comes home on the next visit.
"""
from __future__ import annotations

from typing import Any

from hengbot import launcher_upgrade
from hengbot.model import STORE_HOME
from hengbot.policy_constants import FUNDRAISING_START_GOLD

MINING_MODES = frozenset({"prepare", "mine", "scavenge"})


def mining_planned(policy: Any, snapshot: Any) -> bool:
    """A mining set is open, or this town's poverty is about to open one."""
    return policy._fundraising_mode in MINING_MODES or bool(
        snapshot.in_town
        and snapshot.player.class_id >= 0
        and snapshot.player.gold < FUNDRAISING_START_GOLD)


def _breach_required(policy: Any, snapshot: Any) -> int:
    """The next quest's wall_breach carry (Q2's corridor), 0 without one."""
    if not snapshot.in_town:
        return 0
    strategy = policy._carry_procurement_strategy(snapshot, cache_fixed_quest_head=False)
    tools = getattr(strategy, "required_force", {}).get("utility_tools", {}) if strategy else {}
    return int(tools.get("wall_breach", 0)) if isinstance(tools, dict) else 0


def digger_needed(policy: Any, snapshot: Any, item: Any) -> bool:
    """A retained tool of a planned mining run, or the next quest's breach tool.

    The carry's retention counts a spent Stone to Mud wand as its one item, so
    it alone would let the tool go to Home and quest_digger_at_home take it back.
    """
    if not item.is_digging_tool:
        return False
    if mining_planned(policy, snapshot) and not policy._is_surplus_digging_tool(snapshot, item):
        return True
    return bool(policy._is_quest_wall_breach_item(item) and _breach_required(policy, snapshot) > 0)


def digger_stays_carried(policy: Any, snapshot: Any, item: Any) -> bool:
    """A digger no Home deposit may take: the plans ask what Home refuses."""
    return bool(item.is_digging_tool and (
        policy._fundraising_mode in MINING_MODES
        or digger_needed(policy, snapshot, item)))


def home_breach_digger(policy: Any) -> Any:
    """A Home tool strong enough for a quest's wall_breach carry, else None."""
    return next((item for item in policy._home_knowledge_items
                 if item.is_digging_tool and policy._is_quest_wall_breach_item(item)
                 and not policy._equip_blocked_by_identification(item)
                 and policy._item_signature(item) not in policy._deferred_home_items), None)


def quest_digger_at_home(policy: Any, snapshot: Any) -> Any:
    """The Home tool the next quest's unmet wall_breach carry takes back.

    The carry counts only what is carried (the quest walks the corridor with
    it).  Once carried, digger_needed keeps it from Home again.
    """
    required = _breach_required(policy, snapshot)
    if required <= 0 or policy._quest_carry_count(
            snapshot, "utility_tools", "wall_breach", required) >= required:
        return None
    return home_breach_digger(policy)


def _chosen_by_optimizer(policy: Any, item: Any) -> bool:
    from hengbot.equipment_optimizer import equipment_identity
    preparation = policy._equipment_optimization_preparation
    best = getattr(getattr(preparation, "result", None), "best", None)
    loadout = getattr(best, "loadout", None)
    if loadout is None:
        return False
    identity = equipment_identity(item)
    return any(equipment_identity(owned.item) == identity for _, owned in getattr(loadout, "slots", ()))


def _rearm_needed(snapshot: Any, item: Any) -> bool:
    """A good weapon while the hand holds no real weapon (a digger or nothing)."""
    good = item.is_melee_weapon and item.known and (
        item.is_ego or item.is_artifact or item.to_h > 0 or item.to_d > 0 or item.pval > 0)
    if not good:
        return False
    if snapshot is None:
        return True
    main_hand = next((worn for worn in snapshot.equipment if worn.slot == "main_hand"), None)
    return main_hand is None or main_hand.is_digging_tool


def released(policy: Any, snapshot: Any, item: Any) -> bool:
    """Whether this pack item is spare gear Home may take."""
    if (not policy._spare_equipment_deposit_shape(item)
            or item.is_digging_tool or item.is_ammo):
        return False
    if _rearm_needed(snapshot, item) or _chosen_by_optimizer(policy, item):
        return False
    if snapshot is not None and launcher_upgrade.is_waiting(policy, snapshot, item):
        return False
    return policy._target_loadout_known() or policy._calibration_rejection is not None


def stow_pending(policy: Any, snapshot: Any) -> bool:
    """Spare gear in the pack that a Home visit can still shelve this visit."""
    if (not snapshot.in_town
            or policy._fundraising_mode in MINING_MODES
            or policy._identification_need is not None
            or not policy._home_available(snapshot)
            or STORE_HOME in policy._town_store_attempted
            or policy._town_store_blocked_under_applicable_bound(STORE_HOME)
            or policy._home_is_full(snapshot)):
        return False
    deposit = policy._find_home_deposit(snapshot)
    return deposit is not None and (
        released(policy, snapshot, deposit) or deposit.is_digging_tool)


def carried_names(policy: Any, snapshot: Any) -> list[str]:
    """The decision log's view: spare gear still in the pack in town."""
    if not snapshot.in_town:
        return []
    return [item.name for item in snapshot.inventory
            if released(policy, snapshot, item)
            or (item.is_digging_tool and not digger_stays_carried(policy, snapshot, item))]
