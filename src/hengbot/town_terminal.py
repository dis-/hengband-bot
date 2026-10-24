"""Whether a town owner may take the board: its terminal's admission (ROOT-FIX S1).

Design: plans/DESIGN-town-claim-rootfix-1023.md.  A town rung declares the
last action it intends on a board (``intended_terminal``).  Each terminal kind
splits into a material read (``gather_*``), a pure verdict that returns the
admission *and* its refusal codes from the same branch (``verdict_*``), and
the commit that only the terminal's own call site performs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, NamedTuple

from hengbot.policy_constants import (
    EQUIPMENT_SLOT_KEY,
    FIXED_QUEST_REWARD_POSITIONS,
    FIXED_QUEST_TOWNS,
    MORIVANT_TOWN_ID,
    PACK_CAPACITY,
    QUEST_STATUS_COMPLETED,
    QUEST_STATUS_FINISHED,
    QUEST_STATUS_REWARDED,
    QUEST_STATUS_TAKEN,
    QUEST_STATUS_UNTAKEN,
    STAFF_IDENTIFY_MIN_SUCCESS,
    TOWN_TELEPORT_COST,
    TOWN_TRAVEL_STALL_LIMIT,
)
from hengbot.home_visit import HomeVisitKind
from hengbot.model import STORE_ALCHEMIST, STORE_HOME
from hengbot.quest_knowledge import QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER


@dataclass(frozen=True)
class Admission:
    """ADMIT, or REFUSED with the declared codes that refused the terminal."""

    admitted: bool
    codes: tuple[str, ...] = ()


ADMIT = Admission(True)


def refused(codes) -> Admission:
    return Admission(False, tuple(dict.fromkeys(codes)))


@dataclass(frozen=True)
class QuestEntryMaterial:
    """Frozen inputs of the fixed-quest entry verdict."""

    quest_id: int
    morivant_deposits: bool = False
    q34: bool = False
    readiness_reason: str | None = None
    kill_descent_allowed: bool = True
    equipment_ready: bool = True
    equipment_codes: tuple[str, ...] = ()


def gather_quest_entry(policy: Any, board: Any, quest_id: int, *,
                       kill_descent: bool = False) -> QuestEntryMaterial:
    """Read the entry material without the entry's commit writes.

    The same conditions, in the same order, as ``_quest_equipment_entry_allowed``
    (and ``_kill_quest_descent_allowed`` before it on the ``_fixed_quest_enter_key``
    path); that call site keeps its commit (``_departure_block``,
    ``_town_blocked_reason``, the Q34 ``quest:readiness`` reason).
    """
    expedition = policy._morivant_full_identify
    if expedition is not None and expedition.temporary_deposits:
        return QuestEntryMaterial(quest_id, morivant_deposits=True)
    kill_ok = (policy._kill_quest_descent_allowed(board)
               if kill_descent else True)
    if policy._opening_q34_active(board) and quest_id == 34:
        sink: list[dict] = []
        ready = policy._evaluate_fixed_quest_readiness(
            board, quest_id, require_target_town=True,
            commit=False, telemetry_sink=sink)
        return QuestEntryMaterial(
            quest_id, q34=True, kill_descent_allowed=kill_ok,
            readiness_reason=(
                None if ready else sink[0].get("reason", "unready")))
    info = policy._quest_knowledge.get(quest_id)
    quest = board.quests.get(quest_id)
    depth = max(1, info.level if info is not None else quest.level if quest is not None else 1)
    codes: list[str] = []
    ready = policy._equipment_departure_ready(
        board, destination_depth=depth, commit=False, codes=codes)
    return QuestEntryMaterial(
        quest_id, kill_descent_allowed=kill_ok,
        equipment_ready=ready, equipment_codes=tuple(codes))


@dataclass(frozen=True)
class QuestWorkMaterial:
    """Frozen inputs every fixed-quest terminal shares (travel, claim,
    request, entry): the admitted cross-town shopping trip still holds."""

    shopping_hold: bool = False


# The fixed-quest terminals the shopping hold refuses (not the floor reward).
QUEST_WORK_TERMINALS = frozenset({
    "quest-prepare-return", "quest-travel", "quest-claim",
    "quest-request-building", "quest-entry", "quest-descent",
})


def gather_quest_work(policy: Any, board: Any) -> QuestWorkMaterial:
    """The hold without the arrival observation (``choose_key`` observes it)."""
    return QuestWorkMaterial(shopping_hold=policy._cross_town_shopping_hold(board))


def verdict_quest_work(material: QuestWorkMaterial) -> Admission:
    """Pure: the shopping trip's hold is a refusal code (design 3.3 M5)."""
    if material.shopping_hold:
        return refused(("cross-town-shopping-in-progress",))
    return ADMIT


# Need categories whose wares the supply ledger names (``_store_item_is_supply``
# kinds); the same map as ``_departure_supplier_core``'s ledger shortages.
SUPPLY_KIND_BY_CATEGORY = {
    "recall": "recall", "food": "food", "oil": "oil", "teleport": "teleport",
    "cure-critical": "cure", "remove-curse": "remove-curse",
    "required-star-remove-curse": "star-remove-curse",
}


@dataclass(frozen=True)
class StoreBuyMaterial:
    """Frozen inputs of a supplier's store-buy verdict for one town need."""

    store: int
    reachable: bool
    home: bool
    attempted: bool
    page_offers: bool


def gather_store_buy(policy: Any, board: Any, need: Any) -> StoreBuyMaterial:
    """Read whether ``need``'s supplier can serve it, without any write.

    A remembered page offers the need when a ware of the need's supply kind
    passes the ledger's predicate (``_supply_page_offers``: within gold or on
    an unattempted store, and not refused by the churn guard, #68).  A
    category without a supply kind keeps the earlier evidence (any ware within
    the carried gold).
    """
    store = need.store_type
    page = policy._town_supplier_stock.get(store)
    kind = SUPPLY_KIND_BY_CATEGORY.get(need.category)
    if page is None:
        offers = False
    elif kind is not None:
        offers = policy._supply_page_offers(board, kind, store, page)
    else:
        offers = any(item.price <= board.player.gold for item in page.items)
    return StoreBuyMaterial(
        store=store,
        reachable=policy._town_need_supplier_reachable(board, need),
        home=store == STORE_HOME,
        attempted=store in policy._town_store_attempted,
        page_offers=offers,
    )


def verdict_store_buy(material: StoreBuyMaterial) -> Admission:
    """Pure: the supplier serves the need, or the branch's code."""
    if not material.reachable:
        return refused(("supplier-unreachable",))
    if material.home or not material.attempted or material.page_offers:
        return ADMIT
    return refused(("no-matching-offer",))


@dataclass(frozen=True)
class HomeDepositMaterial:
    """Frozen inputs of the space-reserve Home deposit verdict."""

    order_step4_pending: bool


def gather_home_deposit(policy: Any, board: Any) -> HomeDepositMaterial:
    """The town order's reward work, as ``_town_space_deposit_key`` reads it:
    a merely tight pack (not full) with recorded bounty work yields."""
    return HomeDepositMaterial(order_step4_pending=(
        len(board.inventory) < PACK_CAPACITY
        and policy._town_order_step4_pending(board)))


def verdict_home_deposit(material: HomeDepositMaterial) -> Admission:
    """Pure: the deposit, or the order's reward work it yields to."""
    if material.order_step4_pending:
        return refused(("town-order-step4-pending",))
    return ADMIT


@dataclass(frozen=True)
class CurseRemoveMaterial:
    """Frozen inputs of the worn-curse removal verdict."""

    cannot_read: bool
    scroll_held: bool
    target_available: bool


def gather_curse_remove(policy: Any, board: Any) -> CurseRemoveMaterial:
    """What ``_town_remove_curse_key`` reads before its read key, no write."""
    player = board.player
    return CurseRemoveMaterial(
        cannot_read=bool(player.blind or player.confused),
        scroll_held=policy._usable_remove_curse_scroll(board) is not None,
        target_available=policy._required_remove_curse_kind(board) is not None,
    )


def verdict_curse_remove(material: CurseRemoveMaterial) -> Admission:
    """Pure: the body's branches in its order."""
    if material.cannot_read:
        return refused(("cannot-read-scroll",))
    if not material.scroll_held:
        return refused(("no-remove-curse-scroll",))
    if not material.target_available:
        return refused(("cursed-item-unavailable",))
    return ADMIT


@dataclass(frozen=True)
class EnchantLauncherMaterial:
    """Frozen inputs of the launcher enchanting verdict."""

    cannot_read: bool


def gather_enchant_launcher(policy: Any, board: Any) -> EnchantLauncherMaterial:
    """What ``_town_enchant_launcher_key`` reads before its read key."""
    player = board.player
    return EnchantLauncherMaterial(cannot_read=bool(player.blind or player.confused))


def verdict_enchant_launcher(material: EnchantLauncherMaterial) -> Admission:
    """Pure: a carried scroll is read unless the player cannot read."""
    if material.cannot_read:
        return refused(("cannot-read-scroll",))
    return ADMIT


def launcher_enchant_scroll_held(policy: Any, board: Any) -> bool:
    """A carried enchant scroll of a sval the worn launcher still needs."""
    needed = set(policy._launcher_enchant_needed_svals(board))
    return any(item.is_scroll and item.aware and item.sval in needed
               for item in board.inventory)


def equipped_identification_target(policy: Any, board: Any) -> Any:
    """The worn item ``_town_equipped_identification_key`` identifies, or None."""
    return next(
        (item for item in board.equipment
         if item.slot in EQUIPMENT_SLOT_KEY
         and policy._item_signature(item) not in policy._deferred_home_items
         and policy._identification_flow_candidate(item)),
        None)


@dataclass(frozen=True)
class IdentifyMaterial:
    """Frozen inputs of the worn-item identification verdict."""

    source_held: bool


def gather_identify_equipped(policy: Any, board: Any) -> IdentifyMaterial:
    """Whether a reliable source of the needed kind is carried.

    The source lookup binds an awaiting identification-source reservation to
    a newly carried source (``_bind_identification_source_reservation``), the
    same observation the body makes on this board; a second call changes
    nothing.
    """
    target = equipped_identification_target(policy, board)
    return IdentifyMaterial(source_held=target is not None and (
        policy._find_identification_source(
            board, full=target.known, reliable_only=True) is not None))


def verdict_identify_equipped(material: IdentifyMaterial) -> Admission:
    """Pure: identify with the carried source, or acquire one first."""
    if not material.source_held:
        return refused(("no-identification-source",))
    return ADMIT


def device_identification_target(policy: Any, board: Any) -> Any:
    """The carried device ``_town_device_processing_key`` identifies, or None."""
    return next(
        (item for item in board.inventory
         if policy._normal_identification_flow_candidate(item)
         and not item.is_equipment
         and policy._item_signature(item) not in policy._deferred_device_items),
        None)


def gather_identify_device(policy: Any, board: Any) -> IdentifyMaterial:
    """Whether the body's reliable normal source is carried (the same lookup)."""
    return IdentifyMaterial(source_held=policy._find_identification_source(
        board, full=False, reliable_only=True) is not None)


def carried_identification_target(policy: Any, board: Any) -> Any:
    """The free carried target; an existing Home batch owns its own flow."""
    if (not board.in_town or policy._home_pending_item is not None
            or policy._home_pending_batch):
        return None
    return next((item for item in board.inventory
                 if item.is_equipment
                 and policy._item_signature(item) not in policy._deferred_home_items
                 and policy._item_signature(item) not in policy._unidentifiable_sigs
                 and policy._item_signature(item) not in policy._town_unidentifiable_carried_sigs
                 and policy._identification_flow_candidate(item)), None)


@dataclass(frozen=True)
class CarriedIdentifyMaterial:
    source_held: bool
    full_exhausted: bool


def gather_identify_carried(policy: Any, board: Any) -> CarriedIdentifyMaterial:
    """Use the carried-command source rules without staging a command or
    advancing its device failure watch. A held device still runs that watch
    in the body; only absence of a source refuses here."""
    target = carried_identification_target(policy, board)
    full = bool(target is not None and target.known)
    return CarriedIdentifyMaterial(
        source_held=policy._find_identification_source(
            board, full=full, reliable_only=(
                policy._identify_staff_success_rate(board) < STAFF_IDENTIFY_MIN_SUCCESS
            )) is not None,
        full_exhausted=full and STORE_ALCHEMIST in policy._town_store_attempted,
    )


def verdict_identify_carried(material: CarriedIdentifyMaterial) -> Admission:
    if material.source_held:
        return ADMIT
    if material.full_exhausted:
        return refused(("full-identification-exhausted",))
    return refused(("no-identification-source",))


def home_withdraw_target(policy: Any, board: Any) -> Any:
    """The Home item the filed visit request walks to withdraw, or None.

    The walking deciders are the approach rungs: ``_shopping_approach_step``
    files the Home visit request (a legacy withdrawal, a home-errand take,
    survival's device) before the approach key steps toward Home.
    """
    if (not board.in_town or board.store is not None
            or policy._shopping_approach_store_type != STORE_HOME):
        return None
    request = getattr(getattr(policy, "_home_visit", None), "request", None)
    if request is None or request.kind != HomeVisitKind.WITHDRAW:
        return None
    return request.address if request.address is not None else request.item_identity


@dataclass(frozen=True)
class HomeWithdrawMaterial:
    """Frozen inputs of the Home withdrawal verdict."""

    knowledge_current: bool
    target_stored: bool


def gather_home_withdraw(policy: Any, board: Any, *, target: Any = None) -> HomeWithdrawMaterial:
    """Whether the current Home catalogue still holds the requested item."""
    if target is None:
        target = home_withdraw_target(policy, board)
    return HomeWithdrawMaterial(
        knowledge_current=bool(policy._home_knowledge_current),
        target_stored=any(policy._item_signature(item) == target
                          for item in policy._home_knowledge_items),
    )


def verdict_home_withdraw(material: HomeWithdrawMaterial) -> Admission:
    """Pure: a current catalogue without the item refuses before the walk
    (the in-Home ``identify-staff-reserve-unavailable`` / ``route-claim-
    unfulfilled`` exits learned it only after entering)."""
    if material.knowledge_current and not material.target_stored:
        return refused(("reservation-unavailable",))
    return ADMIT


def plan_stop_admission(policy: Any, board: Any, need: Any) -> Admission:
    """Judge the same supplier before putting it in the town route.

    Home's derived request is read without filing it or acquiring a visit;
    a scan/deposit/recovery does not require a withdrawal reservation.
    """
    material = gather_store_buy(policy, board, need)
    # The router supports native travel before a town map has been adopted.
    # Its next stop may also rearm a newly produced category, as the router
    # historically does after rebuilding the projection.  An observed shelf
    # still has to offer this need; a new category cannot erase that evidence.
    plan = policy._town_errand_plan
    prior_categories = plan.need_categories.get(need.store_type, ()) if plan is not None else ()
    material = replace(
        material,
        reachable=material.reachable or not policy._town_map_active(board),
        attempted=(material.attempted and not (
            need.category not in prior_categories
            and need.store_type not in policy._town_supplier_stock)),
    )
    supplier = verdict_store_buy(material)
    if not supplier.admitted or need.store_type != STORE_HOME:
        return supplier
    request = policy._derived_home_visit_request(board)
    if request is not None and request.kind == HomeVisitKind.WITHDRAW:
        target = request.address if request.address is not None else request.item_identity
        return verdict_home_withdraw(gather_home_withdraw(policy, board, target=target))
    return ADMIT


@dataclass(frozen=True)
class DepartureMaterial:
    """The failing leaves of the ordinary town departure gate, in its order."""

    failed: tuple[str, ...]


def gather_departure(policy: Any, board: Any) -> DepartureMaterial:
    """``_town_departure_conjuncts`` without the equipment leaf's commit."""
    return DepartureMaterial(failed=tuple(
        name for name, ready
        in policy._town_departure_conjuncts(board, commit=False).items()
        if not ready))


def verdict_departure(material: DepartureMaterial) -> Admission:
    """Pure: each failing leaf is its own ``departure:<leaf>`` code."""
    if material.failed:
        return refused(tuple(f"departure:{name}" for name in material.failed))
    return ADMIT


def gather_recall_departure(policy: Any, board: Any) -> DepartureMaterial:
    return DepartureMaterial(tuple(
        name for name, ready
        in policy._recall_town_departure_conjuncts(board, commit=False).items()
        if not ready))


def expedition_destination(policy: Any, board: Any) -> int | None:
    """The destination already selected by the expedition that calls teleport."""
    context = getattr(policy, "_terminal_town_travel", None)
    if context is not None:
        producer, destination = context
        return destination if producer == "cross-town" else None
    current = policy._effective_town_id(board)
    expedition = policy._morivant_full_identify
    if expedition is not None and expedition.phase not in {
            "prepare-home", "return-home", "restore-home"}:
        destination = expedition.origin_town_id if expedition.returning else MORIVANT_TOWN_ID
        if destination != current:
            return destination
    shopping = policy._cross_town_shopping
    return None if shopping is None else shopping.target_town_id


@dataclass(frozen=True)
class CrossTownMaterial:
    affordable: bool
    reachable: bool


def gather_cross_town(policy: Any, board: Any) -> CrossTownMaterial:
    destination = expedition_destination(policy, board)
    required = TOWN_TELEPORT_COST if destination == 0 else 2 * TOWN_TELEPORT_COST
    positions = policy._town_teleport_building_positions(board)
    reachable = bool(positions) and (
        bool(policy._walkable_neighbors(board, board.player.position))
        if board.player.position in positions
        else policy._town_teleport_building_route(board, positions) is not None)
    return CrossTownMaterial(board.player.gold >= required, bool(reachable))


def verdict_cross_town(material: CrossTownMaterial) -> Admission:
    if not material.affordable:
        return refused(("cross-town-fare-unaffordable",))
    if not material.reachable:
        return refused(("cross-town-route-unavailable",))
    return ADMIT


@dataclass(frozen=True)
class FundraisingMaterial:
    missing_digger: bool
    missing_detection: bool
    missing_food: bool
    missing_light: bool
    departure_ready: bool


def gather_fundraising(policy: Any, board: Any) -> FundraisingMaterial:
    preparing = policy._fundraising_mode in {None, "prepare"}
    detection = policy._count_treasure_detection_scrolls(board)
    # Before the stock-out initiator installs its plan, its terminal is
    # already the declared single run, not the ordinary multi-run set.
    detection_missing = (not detection if policy._fundraising_mode is None else
                         preparing and detection < policy._mining_detection_scroll_target(board))
    return FundraisingMaterial(
        missing_digger=preparing and not policy._has_digging_tool(board),
        missing_detection=detection_missing,
        missing_food=not policy._fundraising_food_ready(board),
        missing_light=not policy._fundraising_light_ready(board),
        departure_ready=policy._fundraising_departure_ready(board),
    )


def verdict_fundraising(material: FundraisingMaterial) -> Admission:
    codes = []
    if material.missing_digger:
        codes.append("fundraising-no-digging-tool")
    if material.missing_detection:
        codes.append("fundraising-no-detection")
    if material.missing_food:
        codes.append("fundraising-no-food")
    if material.missing_light:
        codes.append("fundraising-no-light")
    if not codes and not material.departure_ready:
        codes.append("fundraising-departure-unready")
    return refused(tuple(codes)) if codes else ADMIT


@dataclass(frozen=True)
class DescentMaterial:
    """Whether the descent's destination asks the quest-entry question."""

    quest_entrance: bool


def gather_descent(policy: Any, board: Any, target: Any) -> DescentMaterial:
    return DescentMaterial(
        quest_entrance=policy._step_raises_unintended_confirm(board, target))


def verdict_descent(material: DescentMaterial) -> Admission:
    """Pure: a descent never ends on a quest entrance (#102: QUEST_ENTER also
    carries DOWN_STAIRS; only the quest-entry owner answers its question)."""
    if material.quest_entrance:
        return refused(("quest-entrance-target",))
    return ADMIT


@dataclass(frozen=True)
class HomeAtomicDepositMaterial:
    """Frozen inputs of the entrance deposit verdict."""

    relief_pending: bool


def gather_home_atomic_deposit(policy: Any, board: Any) -> HomeAtomicDepositMaterial:
    return HomeAtomicDepositMaterial(relief_pending=policy._home_full_relief is not None)


def verdict_home_atomic_deposit(material: HomeAtomicDepositMaterial) -> Admission:
    """Pure: the body's ``home-full-sale-pending`` branch."""
    if material.relief_pending:
        return refused(("home-full-relief-pending",))
    return ADMIT


def verdict_quest_entry(material: QuestEntryMaterial) -> Admission:
    """Pure: each refusing branch returns its own codes."""
    if material.morivant_deposits:
        return refused(("morivant-temporary-deposits",))
    if not material.kill_descent_allowed:
        return refused(("kill-descent",))
    if material.q34:
        if material.readiness_reason is None:
            return ADMIT
        return refused((material.readiness_reason,))
    if material.equipment_ready:
        return ADMIT
    return refused(material.equipment_codes)


# --- Declarations (design 3.3 / 3.4) -------------------------------------

ENFORCE = "enforce"
SHADOW = "shadow"
EXEMPT_SURVIVAL = "exempt-survival"
EXEMPT_FAMILIES = frozenset({"survival", "detectors", "bookkeeping"})


class TerminalRef(NamedTuple):
    terminal_id: str
    args: tuple


class Server(NamedTuple):
    """The town work that serves a refusal code: arbiter family, need category."""

    family: str
    category: str | None = None


class TerminalDecl(NamedTuple):
    intended_terminal: Callable[[Any, Any], TerminalRef | None] | None
    mode: str


# Codes the quest-entry verdict can return.  Each is an existing blocker or
# reject name, or names a branch that had no string (the ``*`` entries are
# prefixes followed by a detail).
QUEST_ENTRY_CODES = frozenset({
    # Equipment preparation blockers (warrior_optimization,
    # equipment_transaction_planner, policy_equipment).
    "unsupported-class", "missing-natural-stats", "skill-exp-unknown",
    "missing-monrace-knowledge", "home-scan-incomplete", "calibration-required",
    "calibration-stale:*", "illegal-target:*", "cursed-equipped:*",
    "pack-space-required:*", "missing-item:*", "empty-encounter-set",
    "optimization-timeout", "incomplete-equipment-catalog", "no-valid-loadout",
    "pending-random-teleport-suppression", "equipment-transaction-failed",
    "home-route-unavailable", "town-owner-retired",
    # The incomplete item owned by the identification flow (policy_equipment).
    "identification-flow",
    # _equipment_departure_ready branches that had no string.
    "preparation-unavailable", "transaction-actions-remaining", "session-active",
    "missing-ability:*", "loadout-unconfirmed",
    # Q34 readiness rejects (_evaluate_fixed_quest_readiness).
    "not-in-town", "unknown-quest", "strategy-force", "not-full-hp",
    "temporary-status", "combat-weapon", "pack-space", "overweight",
    "random-teleport", "departure", "empty-roster", "unknown-monster",
    "three-turn-threat", "toughest-kill-time", "unready",
    # The entry's own conditions.
    "morivant-temporary-deposits", "kill-descent",
    # The fixed-quest terminals' shared verdict (verdict_quest_work).
    "cross-town-shopping-in-progress",
})

# Codes the store-buy verdict can return (verdict_store_buy).
STORE_BUY_CODES = frozenset({"supplier-unreachable", "no-matching-offer"})
# Codes the Home deposit verdict can return (verdict_home_deposit).
HOME_DEPOSIT_CODES = frozenset({"town-order-step4-pending"})
# Codes the worn-curse removal verdict can return (verdict_curse_remove).
CURSE_REMOVE_CODES = frozenset({
    "cannot-read-scroll", "no-remove-curse-scroll", "cursed-item-unavailable",
})
# Codes the launcher enchanting verdict can return (shared with curse-remove).
ENCHANT_LAUNCHER_CODES = frozenset({"cannot-read-scroll"})
# Codes the worn-item identification verdict can return.
IDENTIFY_CODES = frozenset({"no-identification-source"})
IDENTIFY_CARRIED_CODES = IDENTIFY_CODES | {"full-identification-exhausted"}
# Codes the Home withdrawal verdict can return (verdict_home_withdraw).
HOME_WITHDRAW_CODES = frozenset({"reservation-unavailable"})
# Codes the entrance deposit verdict can return.
HOME_ATOMIC_DEPOSIT_CODES = frozenset({"home-full-relief-pending"})
# Categories are ``_town_need_registry`` names (design 3.4, S2 (c)).
_IDENTIFICATION_SERVERS = (
    Server("identification"), Server("cross-town"),
    Server("home-errand", "identification-withdrawal"),
    Server("shop-buy", "identification-source"),
)
_SPACE_SERVERS = (
    Server("home-visit", "space-deposit"),
    Server("shop-sell", "organization-sale"),
    Server("town-plan"),
)
_TRANSACTION_SERVERS = (Server("equipment-txn"),)

# Codes the descent verdict can return (verdict_descent).
DESCENT_CODES = frozenset({"quest-entrance-target"})
# Who serves each failing leaf of the ordinary departure gate
# (``_town_departure_conjuncts``; design 3.4 S2 rows ``departure:<leaf>``).
_DEPARTURE_LEAF_SERVERS: dict[str, tuple[Server, ...]] = {
    # Owner decision 2026-10-23 (c4-a life-016, recall unaffordable): first
    # sell the sellable surplus for the scroll's price, then scavenge dungeon
    # 1F with the held Treasure Detection, back by the stairs within 10,000
    # game turns (2026-10-15 rule); both run as fundraising.
    "recall_departure_ready": (
        Server("shop-buy", "recall"),
        Server("shop-sell", "organization-sale"),
        Server("fundraising"),
    ),
    "remove_curse_ready": (
        Server("curse-enchant", "remove-curse"),
        Server("curse-enchant", "required-star-remove-curse"),
    ),
    "food_ready": (Server("shop-buy", "food"),),
    "light_ready": (Server("shop-buy", "light"),),
    "teleport_ready": (Server("shop-buy", "teleport"),),
    "cure_critical_ready": (Server("shop-buy", "cure-critical"),),
    # #76: the staff is bought, or the stock-out mining run (fundraising).
    "identify_staff_ready": (Server("shop-buy", "identify-staff"), Server("fundraising")),
    "teleport_items_safe": _TRANSACTION_SERVERS,
    "free_pack_slots_ready": _SPACE_SERVERS,
    "inventory_weight_ready": (
        Server("shop-sell", "overweight-surplus"),
        Server("home-visit", "weight-overload"),
    ),
    "hp_full": (Server("survival"),),
    "mp_full": (Server("survival"),),
    "temporary_status_clear": (Server("survival"),),
    "organization_complete": (
        Server("shop-sell", "organization-sale"), Server("town-plan"),
    ),
    "equipment_departure_ready": (*_TRANSACTION_SERVERS, *_IDENTIFICATION_SERVERS),
    "home_candidate_resolved": (Server("home-visit"),),
    "home_catalog_ready": (Server("home-scan"),),
    "home_pending_item_clear": (Server("home-errand"),),
    "home_pending_batch_clear": (Server("home-errand"),),
    "home_batch_review_clear": (Server("home-errand"),),
    "home_atomic_withdraw_clear": (Server("home-errand"),),
    "digger_withdrawal_resolved": (Server("home-errand"),),
    "identification_need_clear": (Server("identification"),),
    # Always ready (the quest-entry contract owns quest carry).
    "quest_carry_ready": (),
    "combat_weapon_ready": _TRANSACTION_SERVERS,
    "departure_home_pending_item_clear": (Server("home-errand"),),
    "departure_home_pending_batch_clear": (Server("home-errand"),),
    "departure_home_batch_review_clear": (Server("home-errand"),),
    "departure_home_atomic_withdraw_clear": (Server("home-errand"),),
    "departure_identification_need_clear": (Server("identification"),),
}
# Codes the departure verdict can return: one per leaf, and the prefix for a
# leaf added later (no server until it is named here).
DEPARTURE_CODES = frozenset(
    {"departure:*", *(f"departure:{leaf}" for leaf in _DEPARTURE_LEAF_SERVERS)})
CROSS_TOWN_CODES = frozenset({"cross-town-fare-unaffordable", "cross-town-route-unavailable"})
FUNDRAISING_CODES = frozenset({
    "fundraising-no-digging-tool", "fundraising-no-detection", "fundraising-no-food",
    "fundraising-no-light", "fundraising-departure-unready",
})
# Every declared code: the keys of REFUSAL_SERVERS (design 3.3 (1)).
TERMINAL_CODES = (QUEST_ENTRY_CODES | STORE_BUY_CODES | HOME_DEPOSIT_CODES
                  | CURSE_REMOVE_CODES | ENCHANT_LAUNCHER_CODES | IDENTIFY_CODES
                  | IDENTIFY_CARRIED_CODES
                  | HOME_WITHDRAW_CODES
                  | HOME_ATOMIC_DEPOSIT_CODES | DESCENT_CODES | DEPARTURE_CODES)
TERMINAL_CODES |= CROSS_TOWN_CODES | FUNDRAISING_CODES

# Who serves each refusal code.  An empty right side is explicit: no town
# owner can satisfy it, so the terminal closes for the visit.
REFUSAL_SERVERS: dict[str, tuple[Server, ...]] = {
    "identification-flow": _IDENTIFICATION_SERVERS,
    "incomplete-equipment-catalog": (
        *_IDENTIFICATION_SERVERS, Server("home-scan", "equipment-catalog")),
    "home-scan-incomplete": (Server("home-scan"),),
    "pack-space-required:*": _SPACE_SERVERS,
    "pack-space": _SPACE_SERVERS,
    "cursed-equipped:*": (
        Server("curse-enchant", "remove-curse"),
        Server("curse-enchant", "required-star-remove-curse"),
    ),
    "transaction-actions-remaining": _TRANSACTION_SERVERS,
    "session-active": _TRANSACTION_SERVERS,
    "combat-weapon": _TRANSACTION_SERVERS,
    "random-teleport": _TRANSACTION_SERVERS,
    "pending-random-teleport-suppression": _TRANSACTION_SERVERS,
    "overweight": (
        Server("shop-sell", "overweight-surplus"),
        Server("home-visit", "weight-overload"),
    ),
    "not-full-hp": (Server("survival"),),
    "temporary-status": (Server("survival"),),
    "morivant-temporary-deposits": (Server("cross-town"), Server("home-visit")),
    "cross-town-shopping-in-progress": (Server("cross-town"),),
    # The town order's reward/bounty work (``_town_order_step4_key``).
    "town-order-step4-pending": (Server("quest-request"),),
    # A reliable source: bought, withdrawn from Home, or the Morivant trip.
    "no-identification-source": (
        Server("shop-buy", "identification-source"),
        Server("home-errand", "identification-withdrawal"),
        Server("cross-town"),
    ),
    "full-identification-exhausted": (Server("cross-town"),),
    # Blindness or confusion: rest it off.
    "cannot-read-scroll": (Server("survival"),),
    # The needed scroll: bought, or the Home *Remove Curse* stock fetched.
    "no-remove-curse-scroll": (
        Server("shop-buy", "remove-curse"),
        Server("shop-buy", "required-star-remove-curse"),
        Server("home-visit", "home-star-remove-curse-use"),
    ),
    # The Home catalogue lacks the reserved item (design 3.4 S2 row): a
    # source is bought instead (the staff itself, or a scroll), or fetched on
    # the Morivant trip.
    "reservation-unavailable": (
        Server("shop-buy", "identify-staff"),
        Server("shop-buy", "identification-source"),
        Server("cross-town"),
    ),
    # A Home-full relief owns the page first (``_home_full_relief_key``).
    "home-full-relief-pending": (Server("home-visit"),),
    "cross-town-fare-unaffordable": (
        Server("shop-sell", "organization-sale"), Server("fundraising")),
    "cross-town-route-unavailable": (),
    "fundraising-no-digging-tool": (
        Server("home-errand", "stored-digger"),
        Server("shop-buy", "fundraising-digger")),
    "fundraising-no-detection": (
        Server("home-errand", "stored-detection"),
        Server("shop-buy", "fundraising-detection")),
    "fundraising-no-food": (Server("shop-buy", "fundraising-food"),),
    "fundraising-no-light": (Server("shop-buy", "fundraising-light"),),
    "fundraising-departure-unready": (
        Server("survival"), Server("curse-enchant", "remove-curse")),
    **{f"departure:{leaf}": servers
       for leaf, servers in _DEPARTURE_LEAF_SERVERS.items()},
    **{code: () for code in (
        # The descent never ends on a quest entrance; no town owner moves it.
        "quest-entrance-target",
        # A departure leaf not named above has no server yet.
        "departure:*",
        # Every worn curse is proven permanent.
        "cursed-item-unavailable",
        "unsupported-class", "missing-natural-stats", "skill-exp-unknown",
        "missing-monrace-knowledge", "calibration-required", "calibration-stale:*",
        "illegal-target:*", "missing-item:*", "empty-encounter-set",
        "optimization-timeout", "no-valid-loadout", "equipment-transaction-failed",
        "home-route-unavailable", "town-owner-retired", "preparation-unavailable",
        "missing-ability:*", "loadout-unconfirmed", "not-in-town", "unknown-quest",
        "strategy-force", "departure", "empty-roster", "unknown-monster",
        "three-turn-threat", "toughest-kill-time", "unready", "kill-descent",
        # A supplier that cannot serve the need: no town owner serves it.
        "supplier-unreachable", "no-matching-offer",
    )},
}


def declared_code(code: str) -> str | None:
    """The declaration a returned code belongs to, or None when undeclared."""
    if code in TERMINAL_CODES:
        return code
    head, sep, _detail = code.partition(":")
    if sep and f"{head}:*" in TERMINAL_CODES:
        return f"{head}:*"
    return None


def refusal_servers(codes) -> tuple[Server, ...]:
    return tuple(dict.fromkeys(
        server
        for code in codes
        for server in REFUSAL_SERVERS.get(declared_code(code) or code, ())
    ))


# --- intended_terminal (design 3.1) --------------------------------------

def fixed_quest_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """Pure: the last action ``_fixed_quest_key`` intends on this board.

    It follows the body's order (policy_quest.py ``_fixed_quest_key``): a
    pending floor reward, the overweight release, the targeted quest's town,
    then its status.  Reward, claim, request and entry stay distinct so a
    refused entry never stops another quest's reward or request.
    """
    if not board.in_town:
        return None
    pending = policy._fixed_quest_reward_pending
    if pending is None:
        for quest_id in FIXED_QUEST_REWARD_POSITIONS:
            quest = board.quests.get(quest_id)
            if quest is None or quest.status not in {
                    QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}:
                continue
            if any((grid := board.grid_at(position)) is not None
                   and grid.object_count > 0
                   for position in policy._fixed_quest_reward_positions(
                       board, quest_id)):
                pending = quest_id
                break
    if pending is not None:
        return TerminalRef("quest-reward", (pending,))
    if policy._inventory_overweight(board):
        return None
    quest_id = policy._fixed_quest_target(board)
    quest = (None if quest_id is None
             else policy._known_fixed_quests(board).get(quest_id))
    if quest is None:
        if policy._fixed_quest_prepare_return_required(board):
            # No fixed quest is ready for travel: the body returns by inn to
            # the base town (or prepares the town-1 request) instead.
            return TerminalRef("quest-prepare-return",
                               (policy._effective_town_id(board),))
        # The body still travels toward its travel quest (the head, when
        # approved and, untaken, ready for travel) in another town.
        travel = policy._fixed_quest_head(board)
        if travel is None or policy.approved_quest_strategy(travel.id) is None or (
                travel.status == QUEST_STATUS_UNTAKEN
                and not policy._fixed_quest_ready_for_travel(board, travel.id)):
            return None
        travel_town = FIXED_QUEST_TOWNS.get(travel.id, 0)
        if policy._effective_town_id(board) == travel_town:
            return None
        return TerminalRef("quest-travel", (travel_town,))
    target_town = FIXED_QUEST_TOWNS.get(quest_id, 0)
    if policy._effective_town_id(board) != target_town:
        return TerminalRef("quest-travel", (target_town,))
    if quest.status == QUEST_STATUS_COMPLETED:
        return TerminalRef("quest-claim", (quest_id,))
    if quest.status == QUEST_STATUS_UNTAKEN:
        return TerminalRef("quest-request-building", (quest_id,))
    if quest.status != QUEST_STATUS_TAKEN:
        return None
    info = policy._quest_knowledge.get(quest_id)
    if info is not None and info.type in {QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER}:
        # A taken kill quest descends by ordinary stairs from the town.
        return TerminalRef("quest-descent", (quest_id,))
    return TerminalRef("quest-entry", (quest_id,))


# The rung does not apply on this board: the entry skips its producer (on
# and off town).  Distinct from None, which means "no terminal, not judged".
NOT_APPLICABLE = TerminalRef("not-applicable", ())


def fixed_quest_return_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    """Rung #1 (design 3.1 M5): it opens only while the quest-request owner is
    not retired and stage-2 quest travel owns the town now
    (``_fixed_quest_prepare_return_required``); then the body's terminal."""
    if ("quest-request" in policy._town_turn_arbiter._retired
            or not policy._fixed_quest_prepare_return_required(board)):
        return NOT_APPLICABLE
    return fixed_quest_intended_terminal(policy, board)


def space_deposit_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``_town_space_deposit_key``: the Home deposit that restores the pack
    reserve.  While stage-2 quest travel owns the town (rung #1) the rung does
    not apply; the check moved here from the key's body."""
    if not policy._town_space_deposit_actionable(board):
        return None
    if policy._fixed_quest_prepare_return_required(board):
        return NOT_APPLICABLE
    return TerminalRef("home-deposit", ("space-reserve",))


def curse_remove_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``_town_remove_curse_key``: read a Remove Curse scroll on worn gear."""
    if not board.in_town or not policy._has_cursed_equipment(board):
        return None
    return TerminalRef("curse-remove", (policy._required_remove_curse_kind(board),))


def enchant_launcher_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``_town_enchant_launcher_key``: read a carried enchant scroll on the
    worn launcher.  Enchanting is optional (buying the scroll is the
    launcher-enchant need's own work), so without a carried scroll the rung
    intends nothing."""
    if not board.in_town or board.store is not None:
        return None
    launcher = policy._equipped_launcher(board)
    if (launcher is None or EQUIPMENT_SLOT_KEY.get(launcher.slot) is None
            or not launcher_enchant_scroll_held(policy, board)):
        return None
    return TerminalRef("enchant-launcher", (policy._item_signature(launcher),))


def identify_equipped_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``_town_equipped_identification_key``: identify a worn item."""
    if not board.in_town or board.store is not None:
        return None
    target = equipped_identification_target(policy, board)
    if target is None:
        return None
    return TerminalRef("identify-equipped", (policy._item_signature(target),))


def device_identification_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``_town_device_processing_key``: identify a carried device."""
    if not board.in_town:
        return None
    target = device_identification_target(policy, board)
    if target is None:
        return None
    return TerminalRef("identify-device", (policy._item_signature(target),))


def carried_identification_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``town-item-processing``: identify the free carried equipment target."""
    target = carried_identification_target(policy, board)
    if target is None:
        return None
    return TerminalRef("identify-carried", (policy._item_signature(target),))


def home_withdraw_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """The approach rungs: walk to Home for the filed withdrawal.  Other
    stores (store-buy) and other Home requests have no terminal here yet."""
    target = home_withdraw_target(policy, board)
    if target is None:
        return None
    return TerminalRef("home-withdraw", (target,))


def home_atomic_deposit_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``home-atomic-deposit``: the entrance deposit bound to its stay."""
    if (board.store is not None or policy._shopping_approach_store_type != STORE_HOME
            or policy._home_atomic_deposit_pending is not None
            or (policy._store_visit is not None
                and policy._store_visit.store_type != STORE_HOME)):
        return None
    return TerminalRef("home-atomic-deposit", ())


def open_home_deposit_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``_open_home_deposit_key`` on the open Home page: the Home-full relief
    while Home is full (or a relief runs), else the page's deposit.  Neither
    is refused on the board; the body's own exits stay."""
    store = board.store
    if store is None or store.store_type != STORE_HOME:
        return None
    if policy._home_is_full(board) or policy._home_full_relief is not None:
        return TerminalRef("home-full-relief", ())
    return TerminalRef("home-open-deposit", ())


def home_full_defer_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``_defer_home_full_deposit``: carry the unserviceable deposit past the
    visit.  It is the Home-full refusal's own close, never refused itself."""
    if policy._home_full_relief is None:
        return None
    return TerminalRef("home-full-defer", ())


def descent_route_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``_descent_step`` in town: the committed stair or entrance it walks to."""
    if not board.in_town:
        return None
    target = policy._nav_ledger.descent_target
    if target is None:
        return None
    return TerminalRef("descent", (target,))


def direct_descent_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """``direct-descent`` in town: descend from the grid the player stands on."""
    if not board.in_town or board.store is not None:
        return None
    return TerminalRef("descent-here", (board.player.position,))


def cross_town_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    if not board.in_town or board.store is not None:
        return None
    destination = expedition_destination(policy, board)
    return None if destination is None else TerminalRef("cross-town", (destination,))


def fundraising_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    if (not board.in_town or board.store is not None
            or policy._fundraising_mode not in {"prepare", "mine", "scavenge"}):
        return None
    return TerminalRef("fundraising", (policy._fundraising_mode,))


def stockout_mining_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    if (not board.in_town or board.store is not None
            or policy._fundraising_mode is not None or board.player.recalling):
        return None
    labels = {
        "recall_departure_ready": {"Word of Recall scrolls"},
        "food_ready": {"Food rations", "Device charges for food"},
        "light_ready": {"Flasks of oil"},
        "teleport_ready": {"Teleport scrolls"},
        "cure_critical_ready": {"Cure Critical Wounds potions"},
        "remove_curse_ready": {"Remove Curse scrolls", "*Remove Curse* scrolls"},
    }
    failed = gather_recall_departure(policy, board).failed
    blocked = {row["item"] for row in policy.procurement_requirements(board)
               if row.get("blocked_reason") == "no-actionable-supplier"}
    if not failed or any(not (labels.get(name, set()) & blocked) for name in failed):
        return None
    return TerminalRef("fundraising", ("supply-stockout",))


def departure_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    if not board.in_town or board.store is not None or board.player.class_id < 0:
        return None
    funding = fundraising_intended_terminal(policy, board)
    if funding is not None:
        return funding
    # The special dispatcher also serves the expedition before departure.
    if policy._morivant_full_identify is not None:
        return None
    return TerminalRef("departure-recall", ())


def recall_read_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    # Dungeon return reads pass through; town reads own the full recall gate.
    return TerminalRef("departure-recall", ()) if board.in_town else None


def rung_terminal(policy: Any, rung_name: str, board: Any) -> TerminalRef | None:
    """The rung's declared terminal on ``board``: a TerminalRef, NOT_APPLICABLE,
    or None (no declaration, no board, or no terminal on this board)."""
    decl = TERMINALS.get(rung_name)
    if board is None or decl is None or decl.intended_terminal is None:
        return None
    return decl.intended_terminal(policy, board)


def _shadow_rungs() -> frozenset[str]:
    # The fixed S1->S2 list: these rungs only record (design 3.7 item 2).
    return frozenset({
        "_atomic_shop_transaction_key", "_blocking_escape_melee_key",
        "_breeder_breakthrough_escape_key", "_breeder_breakthrough_key",
        "_chest_processing_key#1", "_chest_processing_key#2",
        "_choke_engagement_key", "_conquest_loot_key",
        "_defer_home_full_deposit", "_descent_step",
        "_detected_threat_preparation_key", "_direction_key#1", "_direction_key#2",
        "_emergency_item", "_equipment_transaction_home_key",
        "_equipment_transaction_town_key", "_equipment_transaction_town_key#1",
        "_equipment_transaction_town_key#2", "_equipment_transaction_town_owner_key",
        "_esp_threat_hunt_key", "_esp_threat_rest_key", "_explore_step#2",
        "_flee_step#2", "_flee_step#3", "_flee_step#4", "_fruitless_disengage_key",
        "_fundraising_key#1", "_fundraising_key#2", "_heavy_curse_inscription_key",
        "_home_catalogue_work_key", "_home_disposal_processing_key",
        "_home_full_knowledge_key", "_home_full_relief_key", "_home_full_skip_key",
        "_home_rearm_key", "_hunt_step#1", "_hunt_step#2", "_hunt_step#3",
        "_immobile_breeder_giveup_key", "_item_destroying_breeder_leave_key",
        "_kill_quest_floor_recovery_key", "_melee_swarm_combat_key",
        "_normal_loot_key#1", "_normal_loot_key#2", "_open_home_deposit_key",
        "_overweight_surplus_sale_key", "_paralyzer_prevention_key",
        "_ranged_attack_key#1", "_ranged_attack_key#2",
        "_release_staged_store_operation", "_released_restock_store_key",
        "_return_to_town_key#1", "_return_to_town_key#2", "_return_to_town_key#3",
        "_shopping_approach_key", "_shopping_approach_key#1",
        "_shopping_approach_key#2", "_start_kill_quest_regeneration",
        "_store_sell_key", "_summoner_ranged_kill_key", "_town_device_processing_key",
        "_town_enchant_launcher_key", "_town_equipped_identification_key",
        "_town_order_step4_key#1", "_town_order_step4_key#2",
        "_town_overflow_destroy_key", "_town_random_teleport_suppression_key",
        "_town_remove_curse_key", "_town_restore_weapon_key",
        "_town_space_deposit_key", "_unseen_retreat_intercept_key",
        "_unseen_retreat_key", "_victory_loot_key", "_worthless_junk_destroy_key",
        "direct-descent", "frontier-probe", "home-atomic-deposit",
        "home-atomic-withdraw", "home-errand-knowledge", "home-full-identification",
        "home-full-knowledge", "home-knowledge-after-exit", "idle-fallback",
        "navigator.decide", "oscillating-probe", "supply-stockout-mining",
        "town-item-processing", "town-progress-committed-loot", "town-teleport",
        "_town_special_key", "_read_dungeon_recall_scroll_key",
        "verified-disposal",
        "_dig_to_known_downstairs_key",
        "_entrance_travel_key",
        "_finish_mining_floor",
        "_full_pack_destroy_key",
        "_fundraising_combat_equipment_key",
        "_opening_q34_town_key",
        "_pack_pressure_identify_key",
        "_recall_restock_key",
        "_step_toward",
        "_step_toward:escape",
        "_step_toward:positioning",
        "_step_toward:hunt",
        "_step_toward:departure",
        "_town_blocked_key",
        "_town_destroy_key",
        "_unprofitable_unique_disengage_key",
        "_wield_digging_tool_key",
    })


SHADOW_RUNGS = _shadow_rungs()
# Producers ``_decide`` still calls outside the entry (S1->S2 list, design
# 3.6 item 3 / 3.7 item 3); S2 moves them behind named entries.
DIRECT_PRODUCERS_S1: frozenset[str] = frozenset()
# Parallel predicates still deciding beside the quest rung's terminal (S2).
PARALLEL_PREDICATES_S1: frozenset[str] = frozenset()
EXEMPT_RUNGS = frozenset({
    "_step_toward:survival", "_step_toward:detectors",
    "_darkness_recovery_key",
    "_escape_by_stairs",
    "_town_cancel_unsafe_recall_key",
    "_warning_prompt_response_key",
    "_wilderness_survival_key",
    "_breakout_restore_weapon_key#1", "_breakout_restore_weapon_key#2",
    "_dark_locomotion_key", "_experience_potion_quaff_key", "_explore_step#1",
    "_flee_step#1", "_mana_food_loot_key", "_mana_food_survival_override_key",
    "_navigation_livelock_key", "_stat_gain_quaff_key", "_stat_restore_quaff_key",
    "_survival_gate_key#1", "_survival_gate_key#2", "_town_kill_mob_key",
})

# Every ``_town_producer_entry`` rung (checked against the source by AST).
TERMINALS: dict[str, TerminalDecl] = {
    "_fixed_quest_key#1": TerminalDecl(fixed_quest_return_intended_terminal, ENFORCE),
    "_fixed_quest_key#2": TerminalDecl(fixed_quest_intended_terminal, ENFORCE),
    **{name: TerminalDecl(None, SHADOW) for name in SHADOW_RUNGS},
    **{name: TerminalDecl(None, EXEMPT_SURVIVAL) for name in EXEMPT_RUNGS},
    # S2-d terminals: declared and recorded; ENFORCE with the S2 flip.
    "_town_space_deposit_key": TerminalDecl(space_deposit_intended_terminal, SHADOW),
    "_town_remove_curse_key": TerminalDecl(curse_remove_intended_terminal, SHADOW),
    "_town_enchant_launcher_key": TerminalDecl(enchant_launcher_intended_terminal, SHADOW),
    "_town_equipped_identification_key": TerminalDecl(
        identify_equipped_intended_terminal, SHADOW),
    "_town_device_processing_key": TerminalDecl(
        device_identification_intended_terminal, SHADOW),
    "town-item-processing": TerminalDecl(carried_identification_intended_terminal, SHADOW),
    **{name: TerminalDecl(home_withdraw_intended_terminal, SHADOW) for name in (
        "_shopping_approach_key", "_shopping_approach_key#1",
        "_shopping_approach_key#2")},
    "home-atomic-deposit": TerminalDecl(home_atomic_deposit_intended_terminal, SHADOW),
    "_open_home_deposit_key": TerminalDecl(open_home_deposit_intended_terminal, SHADOW),
    "_defer_home_full_deposit": TerminalDecl(home_full_defer_intended_terminal, SHADOW),
    "_descent_step": TerminalDecl(descent_route_intended_terminal, SHADOW),
    "direct-descent": TerminalDecl(direct_descent_intended_terminal, SHADOW),
    "town-teleport": TerminalDecl(cross_town_intended_terminal, SHADOW),
    **{name: TerminalDecl(fundraising_intended_terminal, SHADOW) for name in (
        "_fundraising_key#1", "_fundraising_key#2")},
    "supply-stockout-mining": TerminalDecl(stockout_mining_intended_terminal, SHADOW),
    "_town_special_key": TerminalDecl(departure_intended_terminal, SHADOW),
    "_read_dungeon_recall_scroll_key": TerminalDecl(recall_read_intended_terminal, SHADOW),
}

# The verdict of each non-quest terminal kind (gather, then the pure verdict).
_TERMINAL_VERDICTS: dict[str, Callable[[Any, Any], Admission]] = {
    "home-deposit": lambda policy, board: verdict_home_deposit(
        gather_home_deposit(policy, board)),
    "curse-remove": lambda policy, board: verdict_curse_remove(
        gather_curse_remove(policy, board)),
    "enchant-launcher": lambda policy, board: verdict_enchant_launcher(
        gather_enchant_launcher(policy, board)),
    "identify-equipped": lambda policy, board: verdict_identify_equipped(
        gather_identify_equipped(policy, board)),
    "identify-device": lambda policy, board: verdict_identify_equipped(
        gather_identify_device(policy, board)),
    "identify-carried": lambda policy, board: verdict_identify_carried(
        gather_identify_carried(policy, board)),
    "home-withdraw": lambda policy, board: verdict_home_withdraw(
        gather_home_withdraw(policy, board)),
    "home-atomic-deposit": lambda policy, board: verdict_home_atomic_deposit(
        gather_home_atomic_deposit(policy, board)),
    "descent": lambda policy, board: verdict_descent(
        gather_descent(policy, board, policy._nav_ledger.descent_target)),
    "descent-here": lambda policy, board: verdict_descent(
        gather_descent(policy, board, board.player.position)),
    "departure-recall": lambda policy, board: verdict_departure(
        gather_recall_departure(policy, board)),
    "cross-town": lambda policy, board: verdict_cross_town(gather_cross_town(policy, board)),
    "fundraising": lambda policy, board: verdict_fundraising(gather_fundraising(policy, board)),
}


# --- The refusal path's commit (design 3.2 item 3) -----------------------
# A refused ENFORCE terminal skips its producer, so the confirmation its body
# makes on the same refusal moves here: the entry performs it instead of the
# skipped body (same writes, same execution offer).  SHADOW rungs still run
# the body, which commits itself.

def _commit_identify_equipped(policy: Any, board: Any, terminal: TerminalRef,
                              admission: Admission) -> None:
    target = equipped_identification_target(policy, board)
    signature = terminal.args[0]
    full = bool(target is not None and target.known)
    if full and STORE_ALCHEMIST in policy._town_store_attempted:
        policy._defer_full_identification(signature)
    else:
        policy._identification_candidate = signature
        policy._request_identification("full" if full else "normal")
    policy._offer_execution(
        None, producer="identification",
        work_id=f"identify:equipped:{signature}",
        next_step="identification.acquire-source",
        arguments=("full" if full else "normal", signature),
        expected_effect="reliable-identification-source-ready",
    )


def _commit_identify_device(policy: Any, board: Any, terminal: TerminalRef,
                            admission: Admission) -> None:
    policy._request_identification("normal")
    policy._device_identification_candidate = terminal.args[0]
    policy._offer_execution(
        None, producer="identification", work_id="identify:device",
        next_step="identification.acquire-source",
        arguments=("normal", terminal.args[0]),
        expected_effect="reliable-identification-source-ready",
    )


def _commit_identify_carried(policy: Any, board: Any, terminal: TerminalRef,
                             admission: Admission) -> None:
    policy._activate_home_batch_item()
    target = carried_identification_target(policy, board)
    signature = terminal.args[0]
    full = bool(target is not None and target.known)
    if full and STORE_ALCHEMIST in policy._town_store_attempted:
        policy._defer_full_identification(signature)
        policy._offer_execution_no_step(
            producer="identification", work_id=f"identify:town-item:{signature}",
            cause="full-identification-deferred")
    else:
        policy._identification_candidate = signature
        policy._request_identification("full" if full else "normal")
        policy._offer_execution(
            None, producer="identification", work_id=f"identify:town-item:{signature}",
            next_step="identification.acquire-source",
            arguments=("full" if full else "normal", signature),
            expected_effect="identification-source-ready")


def _commit_home_withdraw(policy: Any, board: Any, terminal: TerminalRef,
                          admission: Admission) -> None:
    # The approach step acquired this visit and filed its trip before the
    # walking rung asked admission. A refused walk must not retain that visit.
    visit = policy._store_visit
    if visit is not None and visit.store_type == STORE_HOME:
        policy._close_store_visit("reservation-unavailable")


def _commit_curse_remove(policy: Any, board: Any, terminal: TerminalRef,
                         admission: Admission) -> None:
    # The body's no-step causes are the verdict's codes.
    policy._offer_execution_no_step(
        producer="curse-enchant", work_id="remove-curse", cause=admission.codes[0])


def _commit_enchant_launcher(policy: Any, board: Any, terminal: TerminalRef,
                             admission: Admission) -> None:
    policy._offer_execution_no_step(
        producer="curse-enchant", work_id="enchant-launcher",
        cause="enchant-context-unavailable")


def _commit_home_atomic_deposit(policy: Any, board: Any, terminal: TerminalRef,
                                 admission: Admission) -> None:
    policy._offer_home_atomic_no_step("deposit", "home-full-sale-pending")


def _commit_cross_town(policy: Any, board: Any, terminal: TerminalRef,
                       admission: Admission) -> None:
    if "cross-town-fare-unaffordable" in admission.codes:
        destination = terminal.args[0]
        policy.town_teleport_refusal = {
            "current_town_id": policy._effective_town_id(board),
            "destination_town_id": destination,
            "gold": board.player.gold,
            "required_gold": (TOWN_TELEPORT_COST if destination == 0
                              else 2 * TOWN_TELEPORT_COST),
        }
        policy.last_reason = "town:teleport-refused-fare"


REFUSAL_COMMITS: dict[str, Callable[[Any, Any, TerminalRef, Admission], None]] = {
    "identify-equipped": _commit_identify_equipped,
    "identify-device": _commit_identify_device,
    "identify-carried": _commit_identify_carried,
    "home-withdraw": _commit_home_withdraw,
    "home-atomic-deposit": _commit_home_atomic_deposit,
    "cross-town": _commit_cross_town,
    "curse-remove": _commit_curse_remove,
    "enchant-launcher": _commit_enchant_launcher,
}


def commit_refusal(policy: Any, board: Any, terminal: TerminalRef | None) -> None:
    """Called by the entry when ``may_take_board`` refused (ENFORCE only)."""
    commit = REFUSAL_COMMITS.get(terminal.terminal_id) if terminal is not None else None
    if commit is not None:
        commit(policy, board, terminal, terminal_admission(policy, board, terminal))


# --- The board verdict (design 3.5) --------------------------------------

def terminal_admission(policy: Any, board: Any, terminal: TerminalRef) -> Admission:
    """The terminal's verdict, gathered once per decision and terminal."""
    memo_key = (policy._decision_sequence, terminal)
    memo = getattr(policy, "_terminal_admission_memo", None)
    if memo is not None and memo_key in memo:
        return memo[memo_key]
    verdict = _TERMINAL_VERDICTS.get(terminal.terminal_id)
    admission = (verdict_quest_work(gather_quest_work(policy, board))
                 if terminal.terminal_id in QUEST_WORK_TERMINALS
                 else verdict(policy, board) if verdict is not None else ADMIT)
    if admission.admitted and terminal.terminal_id == "quest-entry":
        quest_id = terminal.args[0]
        info = policy._quest_knowledge.get(quest_id)
        navigator = bool(policy.approved_quest_strategy(quest_id) is not None
                         and info is not None and info.battlefield is not None)
        admission = verdict_quest_entry(gather_quest_entry(
            policy, board, quest_id, kill_descent=not navigator))
    policy._terminal_admission_memo = {memo_key: admission}
    return admission


def _expedition_route_edges(policy: Any, board: Any) -> int | None:
    """Edges left on the held cross-town expedition's next inn route."""
    current = policy._effective_town_id(board)
    destination = None
    morivant = policy._morivant_full_identify
    if morivant is not None:
        destination = (morivant.origin_town_id if morivant.returning
                       else MORIVANT_TOWN_ID)
    shopping = getattr(policy, "_cross_town_shopping", None)
    if (destination is None or destination == current) and shopping is not None:
        destination = shopping.target_town_id
    if destination is None or destination == current:
        return None
    result = policy._town_teleport_route(board, destination)
    if result.key is None or result.failure is not None:
        return None
    return 0 if result.route is None else result.route.remaining_edges


def _need_served_now(policy: Any, board: Any, server: Server) -> bool:
    """Design 3.5 (ii): the server's need is on this decision's need list and
    its supplier's store-buy verdict admits (a route, and an offer or an
    unattempted store).  The list is the claims evaluation's own read; a
    decision without one shows no such evidence (no second read here)."""
    stamp = getattr(policy, "_decision_claim_needs", None)
    if (stamp is None or stamp[0] != policy._decision_sequence
            or stamp[1] is not board):
        return False
    return any(
        need.category == server.category
        and verdict_store_buy(gather_store_buy(policy, board, need)).admitted
        for need in stamp[2])


def _live_servers(policy: Any, board: Any, terminal: TerminalRef,
                  servers: tuple[Server, ...]) -> tuple[tuple[Server, ...], bool]:
    """Servers progressing now, and whether one showed progress on this board.

    Never a claim's existence (design 3.5 M4): an expedition whose next inn
    step composes, or a family whose arbiter progress vector is within the
    stall limit.  Progress is a shorter route or a changed vector.
    """
    ledger = policy._town_visit_ledger
    arbiter = policy._town_turn_arbiter
    vectors = getattr(arbiter, "_vector_by_owner", {})
    no_progress = getattr(arbiter, "_no_progress_by_owner", {})
    live: list[Server] = []
    progressed = False
    for server in servers:
        if server.category is not None and _need_served_now(policy, board, server):
            live.append(server)
            continue
        key = (terminal, server.family)
        if server.family == "cross-town":
            edges = _expedition_route_edges(policy, board)
            if edges is not None:
                live.append(server)
                best = ledger.terminal_route_edges.get(key)
                if best is None or edges < best:
                    ledger.terminal_route_edges[key] = edges
                    progressed = progressed or best is not None
                continue
        if (server.family in vectors
                and no_progress.get(server.family, 0) < TOWN_TRAVEL_STALL_LIMIT):
            live.append(server)
            vector = vectors[server.family]
            if (key in ledger.terminal_server_vectors
                    and ledger.terminal_server_vectors[key] != vector):
                progressed = True
            ledger.terminal_server_vectors[key] = vector
    return tuple(dict.fromkeys(live)), progressed


def may_take_board(policy: Any, rung_name: str, family: str, board: Any,
                   terminal: TerminalRef | None) -> bool:
    """Whether this town rung may take the board (design 3.5).

    ``terminal`` is ``rung_terminal`` of this board (the entry reads it once,
    before its off-town pass-through, and skips NOT_APPLICABLE rungs).  A
    refused terminal yields while a server progresses, and closes for the
    visit after TOWN_TRAVEL_STALL_LIMIT yields without progress, or at once
    when no server is live.  Closing never stops the bot.  SHADOW rungs only
    record.  Independent of --enforce-town-claims.
    """
    if family in EXEMPT_FAMILIES or board is None or terminal is None:
        return True
    decl = TERMINALS[rung_name]
    admission = terminal_admission(policy, board, terminal)
    if admission.admitted:
        return True
    records = getattr(policy, "_decision_terminal_admissions", None)
    if records is None:
        records = policy._decision_terminal_admissions = []
    row_terminal = [terminal.terminal_id, list(terminal.args)]
    if not any(row["terminal"] == row_terminal for row in records):
        ledger = policy._town_visit_ledger
        closed = ledger.closed_terminals
        live: tuple[Server, ...] = ()
        if terminal not in closed:
            live, progressed = _live_servers(
                policy, board, terminal, refusal_servers(admission.codes))
            if not live:
                closed[terminal] = f"terminal-refused-unserved:{admission.codes[0]}"
            else:
                yields = 0 if progressed else ledger.terminal_yields[terminal] + 1
                ledger.terminal_yields[terminal] = yields
                if yields >= TOWN_TRAVEL_STALL_LIMIT:
                    closed[terminal] = "yield-without-server-progress"
        records.append({
            "rung": rung_name, "terminal": row_terminal,
            "mode": decl.mode, "verdict": "refused", "codes": list(admission.codes),
            "live": [list(server) for server in live],
            "yields": ledger.terminal_yields[terminal],
            "closed": closed.get(terminal),
        })
    return decl.mode != ENFORCE
