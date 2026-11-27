"""Which departure leaves may hold a departure (MAINTAINABILITY.md rules 2 and 3, 2026-11-27).

The one classification table of the departure gates' leaves.  Every leaf the gates can return
(``_town_departure_conjuncts``, ``_recall_town_departure_conjuncts``, ``_departure_minimum``,
``town_terminal.gather_blocked_recall``: read from the source by scripts/departure_rescue_lint.py,
which fails on a leaf in no class or in two) is in exactly one class:

``TOP_UP``     a target the visit keeps aiming for, adequate short of it (n1-a life-545 02:09: 18
               of 20 Identify staff charges, every staff refused as overweight; 2026-11-28 04:01:
               food 8 of 9 Rations' worth, one trip eats 8).  Since 2026-11-28 every supply leaf
               (Recall, Teleportation, Cure Critical Wounds, light, Remove Curse), the rest leaves
               (HP, mana, a temporary status) and the minimum's one free pack slot are TOP_UP: each
               adequacy line is the dive's own line (its return or rest rule), named in ``TOP_UP``.
``OPTIONAL``   work worth finishing this visit that leaving without loses nothing but time: a Home
               candidate to identify or compare, the identification backlog, Home's queued takes
               and its batch review, the Home list, the pack's tidy-up, spare gear, the equipment
               optimiser's better loadout (n1-a life-545 04:39: a Home candidate doable with four
               Identify scrolls but Home's passes used up,
               town:blocked:unmet:home_candidate_resolved).  The item stays where it is for a
               later visit.
``MUST_HAVE``  a floor of the planned dive with no line short of it: the weight that slows, the
               hands, an anti-teleport item, the depth's abilities, 50F+ *Destruction*.  It holds
               the departure, and its rescue in departure_rescues.RESCUES answers first (a sale or
               deposit for the weight, the equipment transaction, the no-safe-destination
               fundraising, the walk back to Home).
``MECHANISM``  a transfer or an observation in flight; still failing at the town end is a broken
               mechanism (rule 2 allows its named stop).

The town end (town_terminal.town_end_key) waives the ordinary gate's TOP_UP leaves that are
adequate and its OPTIONAL leaves once the rescues gave no key, departs, and records them in the
decision row (``departure_block.town_end_waived``).  The forced departure's minimum
(``_departure_minimum``) is never waived; it reads a TOP_UP leaf to its adequacy
(``adequate_top_ups``), so a leaf of both gates (``free_pack_slots_ready``: the minimum's one slot,
the ordinary gate's four or five) holds where both gates are below the adequacy line.

When a leaf's rescues are spent (MAINTAINABILITY.md rule 2, coordinator 2026-11-28): a TOP_UP leaf
at its adequacy line departs with the waiver recorded; a TOP_UP leaf below its line and every
MUST_HAVE leaf go to the town end's 1F mining cycle (``SAFER_FALLBACK``, town_end_mining: the Yeek
cave 1F asks no Word of Recall, escape, cure, weapon or depth ability, and earns the gold the next
retry buys with); only a MECHANISM leaf names its stop.  The weight (``inventory_weight_ready``)
is settled by its last rescue, overweight_departure ``relief_spent_key``.  n1-a life-545
2026-11-28 05:06 stopped town:blocked:survival:inventory_weight_ready at 181.4 of 160.0 lb with
no speed lost, after the food (04:01) and the pack slots (03:01) of the same visit.
"""
from __future__ import annotations

from typing import Any, Callable

# The adequacy lines below cite these (MAINTAINABILITY.md rule 4).
# temporary_status_clear: the statuses that refuse a read, a cast or a step (blind and confused
# refuse the read, cmd-read.cpp; paralysis every command; hallucination misreads every monster;
# a stun lowers every skill, player-status.cpp).  Poison, a cut and fear do not: the dungeon cures
# a heavy poison and moves on with a light one (coordinator 2026-11-26), and fear only refuses the
# melee the dive's own Heroism and escapes answer.
IMPAIRING_STATUSES = ("blind", "confused", "paralyzed", "hallucinated", "stunned")


def _supply(policy: Any, board: Any, kind: str):
    return policy._supply_ledger(board, policy._planned_depth())[kind]


def _status_adequate(policy: Any, board: Any) -> bool:
    return not any(getattr(board.player, name) for name in IMPAIRING_STATUSES)


def _mana_adequate(policy: Any, board: Any) -> bool:
    from hengbot import realm_spells
    player = board.player
    return (not realm_spells.applies(policy, board)
            or player.mp >= min(realm_spells.escape_reserve(policy, board), player.max_mp))


def _light_adequate(policy: Any, board: Any) -> bool:
    judgment = policy._light_judgment(board)
    return judgment.owns_fuelless_light or (judgment.worn is not None and not judgment.faint)


def _slots_adequate(policy: Any, board: Any) -> bool:
    from hengbot.policy_constants import PACK_CAPACITY
    return (PACK_CAPACITY - len(board.inventory) >= 1
            or policy._overflow_disposal_item(board) is None)


def _hp_adequate(policy: Any, board: Any) -> bool:
    from hengbot.policy_constants import REST_TARGET_HP_RATIO
    player = board.player
    return player.max_hp > 0 and player.hp >= player.max_hp * REST_TARGET_HP_RATIO


def _teleport_adequate(policy: Any, board: Any) -> bool:
    status = _supply(policy, board, "teleport")
    return status.count >= max(1, status.required_return)


def _cure_adequate(policy: Any, board: Any) -> bool:
    status = _supply(policy, board, "cure")
    return status.count >= status.required_return


# leaf -> its adequacy short of the target: (policy, board) -> bool.  At the line the town end
# departs without the leaf once its rescues gave no key and records it (``town_end_waived``);
# below it the leaf holds like a MUST_HAVE and, its rescues spent, goes to ``SAFER_FALLBACK``.
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
    # The target is the recall band plus the one read at departure (policy ``_recall_target``);
    # adequate is the repetition departure's own line: two reads the dungeon can go home with and
    # the ledger at its return line (policy ``_recall_adequate``, read by gather_blocked_recall).
    "recall_departure_ready": lambda policy, board: policy._recall_adequate(board),
    # The target is the departure band (SUPPLY_THRESHOLDS["teleport"]["departure"]); adequate is
    # the dive's own return line (["return"]: the floor returns below it,
    # ``_ledger_return_shortages``), at least one escape.
    "teleport_ready": _teleport_adequate,
    # The same for Cure Critical Wounds (SUPPLY_THRESHOLDS["cure"]): its return line is 0 short of
    # CURE_CRITICAL_REQUIRED_DEPTH, so a shallow dive leaves without one.
    "cure_critical_ready": _cure_adequate,
    # The target is a lantern and OIL_TARGET flasks (or FOOD_STOCK_TARGET torches); adequate is a
    # worn light that lights and is not yet faint (LANTERN_DIM_WARNING_FUEL, lite-processor.cpp:71),
    # or a fuelless light: the dungeon's light-low return answers the rest (``_light_judgment``).
    "light_ready": _light_adequate,
    # A worn curse the bot already wore into town: the cure is bought on a later visit; leaving
    # with it changes nothing the last dive did not have.
    "remove_curse_ready": lambda policy, board: True,
    # Rest answers first (departure_rescues ``rest``); adequate is the dungeon's rest line
    # (REST_TARGET_HP_RATIO): the dive rests below it on its first quiet board.
    "hp_full": _hp_adequate,
    # Adequate is the dungeon's mana rest line (realm_spells ``mana_rest_due``: the escape spell's
    # mana, at most the maximum); a class without realm spells holds no mana for an escape.
    "mp_full": _mana_adequate,
    # Adequate is none of IMPAIRING_STATUSES.
    "temporary_status_clear": _status_adequate,
    # The ordinary gate asks MIN_TERMINAL_FREE_PACK_SLOTS, the minimum one.  Adequate is one free
    # slot, or none and no legal disposal left (``_overflow_disposal_item``, coordinator
    # 2026-11-28 03:01: every stack is a reservation's kit).  Gold takes no slot, and the floor's
    # full-pack exchange (full_pack_exchange) judges a pickup on a full pack.
    "free_pack_slots_ready": _slots_adequate,
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
    "spare_gear_stowed": "spare gear stays carried",
    "destruction_staff_settled": "the Black Market *Destruction* staff waits",
    "digger_withdrawal_resolved": "the digger take waits (a mining run without it digs less)",
    "quest_carry_ready": "always ready (the quest-entry contract owns quest carry)",
    "equipment_departure_ready": "the worn loadout departs; the better one waits "
                                 "(depth_abilities and combat_weapon_ready still hold)",
}

# leaf -> why it holds the departure, and its answer once its rescues are spent.  None departs
# without it: each is a floor of the planned dive, which the 1F mining cycle (``SAFER_FALLBACK``)
# does not need.
MUST_HAVE: dict[str, str] = {
    "inventory_weight_ready": "slowed by the load; overweight sale, deposit of this visit's buys, "
                              "then overweight_departure (no speed lost departs, else shed)",
    "combat_weapon_ready": "the equipment transaction re-arms the hands; spent: 1F mining",
    "teleport_items_safe": "the equipment transaction takes off the anti-teleport item; "
                           "spent: 1F mining",
    "depth_abilities": "the no-safe-destination fundraising (owner 2026-10-19); spent: 1F mining",
    "destruction_carried": "50F+ without *Destruction* (owner 2026-11-18); walk back to Home; "
                           "spent: 1F mining",
}

# The town end's answer for a requirement (TOP_UP below its line, MUST_HAVE) whose rescues are
# spent: one mining cycle at the Yeek cave 1F (town_end_mining.start, the owner's 2026-11-02 cycle
# for purchase gaps), retried on the run's return.  The mining departure keeps its own gates
# (policy_fundraising ``_fundraising_departure_ready``: food, light, health, the kit).
SAFER_FALLBACK = "town-end-mining-cycle"

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


def safer_fallback(leaves: tuple[str, ...]) -> bool:
    """Whether the 1F mining cycle answers ``leaves`` once their rescues are spent: every one is a
    requirement or optional work (no MECHANISM leaf, no unclassified one)."""
    return bool(leaves) and all(class_of(leaf) in {"top-up", "optional", "must-have"}
                                for leaf in leaves)


def only_waivable(policy: Any, board: Any, leaves: tuple[str, ...],
                  survival: tuple[str, ...] = ()) -> bool:
    """Whether the town end may depart: every one of ``leaves`` is waivable and none is a leaf of
    the forced departure's minimum (``survival``), which is never waived."""
    return (bool(leaves) and not set(leaves) & set(survival)
            and set(town_end_waivable(policy, board, leaves)) == set(leaves))
