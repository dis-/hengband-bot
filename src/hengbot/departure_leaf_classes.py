"""Which departure-minimum leaves may hold a departure (MAINTAINABILITY.md rule 2, 2026-11-27).

n1-a life-545 (2026-11-27 02:09, Amberite Rogue CL21): 18 of the 20 Identify staff charges
carried, the Magic shop's 21-charge staff and Home's 15-charge staff both refused because either
would put the pack (1432 of 1450) over the weight limit, and the town end stopped under
``town:blocked:survival:identify_staff_ready``.  Rule 2: a requirement this visit cannot meet does
not stop the bot; it leaves with what it has when that is adequate.

Every leaf of the forced departure's minimum (policy_town ``_departure_minimum``), each of which
the town end names as ``town:blocked:survival:<leaf>``, is in exactly one class:

``TOP_UP``     a target the visit keeps aiming for, adequate short of it.  When the town end
               would stop on such leaves alone and their rescues (departure_rescues) gave no
               key, the visit departs once they are adequate (``waivable``).
``MUST_HAVE``  leaving without it risks the life or cannot work; it holds the departure.  Each
               has its alternative action in departure_rescues.RESCUES (another supplier,
               another town, a 1F mining run on foot for a supply; sale and Home deposit for the
               weight; rest for HP, mana and status).
``MECHANISM``  a transfer or observation in flight; failing at the town end is a broken
               mechanism (rule 2 allows its named stop).
"""
from __future__ import annotations

from typing import Any, Callable

# leaf -> its adequacy short of the target: (policy, board) -> bool.
TOP_UP: dict[str, Callable[[Any, Any], bool]] = {
    # 20 charges is the top-up target (STAFF_IDENTIFY_MIN_CHARGES); IDENTIFY_CHARGE_FLOOR is the
    # least reserve (policy_supply ``_identify_staff_adequate``).
    "identify_staff_ready": lambda policy, board: policy._identify_staff_adequate(
        board, cache_fixed_quest_head=False),
}

# leaf -> why it holds the departure, and its alternative action.
MUST_HAVE: dict[str, str] = {
    "recall_departure_ready": "no way home; supplier, other town, 1F mining (0 needed while mining)",
    "food_ready": "starvation (n1-a 544); supplier, other town, 1F mining",
    "light_ready": "no light in the dungeon; supplier, other town, 1F mining",
    "teleport_ready": "the escape; supplier, other town, 1F mining",
    "cure_critical_ready": "the heal; supplier, other town, 1F mining",
    "remove_curse_ready": "a worn curse that needs removal; supplier, other town, 1F mining",
    "inventory_weight_ready": "slowed by the load; overweight sale, deposit of this visit's buys",
    "hp_full": "rest in town",
    "mp_full": "rest in town",
    "temporary_status_clear": "rest in town",
    "combat_weapon_ready": "the equipment transaction re-arms the hands",
    "teleport_items_safe": "the equipment transaction takes off the anti-teleport item",
    "depth_abilities": "the no-safe-destination fundraising (owner 2026-10-19)",
    "free_pack_slots_ready": "the Home deposit, sale and destroy owners",
}

MECHANISM: frozenset[str] = frozenset({
    "equipment_observed", "home_atomic_withdraw_clear", "store_transfer_clear",
    "equipment_transfer_clear",
})


def waivable(policy: Any, board: Any, leaves: tuple[str, ...]) -> tuple[str, ...]:
    """The top-up ``leaves`` that are adequate on ``board`` (an unknown reads as not adequate)."""
    adequate = []
    for leaf in leaves:
        check = TOP_UP.get(leaf)
        if check is None:
            continue
        try:
            if check(policy, board):
                adequate.append(leaf)
        except (AttributeError, TypeError, ValueError):
            continue
    return tuple(adequate)


def only_adequate_top_ups(policy: Any, board: Any, leaves: tuple[str, ...]) -> bool:
    """Whether every one of ``leaves`` is an adequate top-up (the town end may depart)."""
    return bool(leaves) and set(waivable(policy, board, leaves)) == set(leaves)
