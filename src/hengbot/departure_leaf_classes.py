"""Which departure leaves may hold a departure (MAINTAINABILITY.md rules 2 and 3, 2026-11-27).

The one classification table of the departure gates' leaves.  Every leaf the gates can return
(``_town_departure_conjuncts``, ``_recall_town_departure_conjuncts``, ``_departure_minimum``,
``town_terminal.gather_blocked_recall``: read from the source by scripts/departure_rescue_lint.py,
which fails on a leaf in no class or in two) is in exactly one class:

``TOP_UP``     a target the visit keeps aiming for, adequate short of it (n1-a life-545 02:09: 18
               of 20 Identify staff charges, every staff refused as overweight; 2026-11-28 04:01:
               food 8 of 9 Rations' worth, one trip eats 8).
``OPTIONAL``   work worth finishing this visit that leaving without loses nothing but time: a Home
               candidate to identify or compare, the identification backlog, Home's queued takes
               and its batch review, the Home list, the pack's tidy-up and free slots beyond the
               minimum's one, spare gear, the equipment optimiser's better loadout (n1-a life-545
               04:39: a Home candidate doable with four Identify scrolls but Home's passes used up,
               town:blocked:unmet:home_candidate_resolved).  The item stays where it is for a
               later visit.
``MUST_HAVE``  leaving without it risks the life or cannot work.  It holds the departure, and its
               rescue in departure_rescues.RESCUES answers first (another supplier, another town,
               a 1F mining run on foot, a sale or deposit for the weight, rest, the equipment
               transaction, the no-safe-destination fundraising).
``MECHANISM``  a transfer or an observation in flight; still failing at the town end is a broken
               mechanism (rule 2 allows its named stop).

The town end (town_terminal.town_end_key) waives the ordinary gate's TOP_UP leaves that are
adequate and its OPTIONAL leaves once the rescues gave no key, departs, and records them in the
decision row (``departure_block.town_end_waived``).  The forced departure's minimum
(``_departure_minimum``) is never waived; it reads a TOP_UP leaf to its adequacy
(``adequate_top_ups``), so a leaf of both gates (``free_pack_slots_ready``: the minimum's one slot,
the ordinary gate's four or five) keeps the minimum's hold.
"""
from __future__ import annotations

from typing import Any, Callable

# leaf -> its adequacy short of the target: (policy, board) -> bool.
TOP_UP: dict[str, Callable[[Any, Any], bool]] = {
    # 20 charges is the top-up target (STAFF_IDENTIFY_MIN_CHARGES); IDENTIFY_CHARGE_FLOOR is the
    # least reserve (policy_supply ``_identify_staff_adequate``).
    "identify_staff_ready": lambda policy, board: policy._identify_staff_adequate(
        board, cache_fixed_quest_head=False),
    # The departure target (food_supply.departure_rations) is one planned trip at the character's
    # digestion plus MARGIN_RATIONS, at least FOOD_STOCK_TARGET; one trip's worth is adequate
    # (policy ``_food_adequate``).  Below it the leaf holds like a MUST_HAVE: its rescues (another
    # supplier, another town, a 1F mining run) answer, and the food purchase may use the pack's
    # reserve (town_pack_budget ``purchase_reserve_use``).  n1-a life-545 2026-11-28 04:01: 8 of
    # 9 Rations' worth (a trip eats 8) stopped town:blocked:survival:food_ready.
    "food_ready": lambda policy, board: policy._food_adequate(board),
}

# leaf -> what stays for a later visit when it is waived.
OPTIONAL: dict[str, str] = {
    "home_candidate_resolved": "the Home candidate waits for its identification (identification_wait)",
    "identification_need_clear": "the identification backlog waits (identification_wait)",
    "departure_identification_need_clear": "the identification backlog waits (identification_wait)",
    "home_pending_item_clear": "the queued Home take stays queued",
    "departure_home_pending_item_clear": "the queued Home take stays queued",
    "home_pending_batch_clear": "the queued Home batch stays queued",
    "departure_home_pending_batch_clear": "the queued Home batch stays queued",
    "home_batch_review_clear": "the Home batch review waits",
    "departure_home_batch_review_clear": "the Home batch review waits",
    "home_catalog_ready": "the Home list is read on a later visit",
    "organization_complete": "the pack's tidy-up sale waits",
    "free_pack_slots_ready": "fewer than the four or five free slots (the minimum's one holds)",
    "spare_gear_stowed": "spare gear stays carried",
    "destruction_staff_settled": "the Black Market *Destruction* staff waits",
    "digger_withdrawal_resolved": "the digger take waits (a mining run without it digs less)",
    "quest_carry_ready": "always ready (the quest-entry contract owns quest carry)",
    "equipment_departure_ready": "the worn loadout departs; the better one waits "
                                 "(depth_abilities and combat_weapon_ready still hold)",
}

# leaf -> why it holds the departure, and its alternative action.
MUST_HAVE: dict[str, str] = {
    "recall_departure_ready": "no way home; supplier, other town, 1F mining (0 needed while mining)",
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
    "destruction_carried": "50F+ without *Destruction* (owner 2026-11-18); walk back to Home",
}

MECHANISM: frozenset[str] = frozenset({
    "equipment_observed", "home_atomic_withdraw_clear", "departure_home_atomic_withdraw_clear",
    "store_transfer_clear", "equipment_transfer_clear",
})

CLASSES = {"top-up": frozenset(TOP_UP), "optional": frozenset(OPTIONAL),
           "must-have": frozenset(MUST_HAVE), "mechanism": MECHANISM}


def class_of(leaf: str) -> str | None:
    """The leaf's class name, or None for a leaf no class names."""
    return next((name for name, leaves in CLASSES.items() if leaf in leaves), None)


def adequate_top_ups(policy: Any, board: Any, leaves: tuple[str, ...]) -> tuple[str, ...]:
    """The TOP_UP ``leaves`` adequate on ``board`` (an unknown reads as not adequate)."""
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


def town_end_waivable(policy: Any, board: Any, leaves: tuple[str, ...]) -> tuple[str, ...]:
    """The ``leaves`` the town end may depart without: adequate TOP_UP and every OPTIONAL."""
    adequate = set(adequate_top_ups(policy, board, leaves))
    return tuple(leaf for leaf in leaves if leaf in adequate or leaf in OPTIONAL)


def only_waivable(policy: Any, board: Any, leaves: tuple[str, ...],
                  survival: tuple[str, ...] = ()) -> bool:
    """Whether the town end may depart: every one of ``leaves`` is waivable and none is a leaf of
    the forced departure's minimum (``survival``), which is never waived."""
    return (bool(leaves) and not set(leaves) & set(survival)
            and set(town_end_waivable(policy, board, leaves)) == set(leaves))
