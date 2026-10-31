"""Whether a town owner may take the board: its terminal's admission (ROOT-FIX S1).

Design: plans/DESIGN-town-claim-rootfix-1023.md.  A town rung declares the
last action it intends on a board (``intended_terminal``).  Each terminal kind
splits into a material read (``gather_*``), a pure verdict that returns the
admission *and* its refusal codes from the same branch (``verdict_*``), and
the commit that only the terminal's own call site performs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Callable, NamedTuple

from hengbot.policy_constants import (
    EQUIPMENT_SLOT_KEY,
    LEAVE_STORE_KEY,
    SELL_KEY,
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
from hengbot.town_pack_budget import permits
from hengbot.item_reservation import decision_memo, item_available, reservation_verdict, reserved_item_command
from hengbot.model import STORE_ALCHEMIST, STORE_HOME
from hengbot.policy_types import TownNeed
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
    key = (
        policy._decision_sequence, need, policy._town_need_supplier_reachable,
        id(policy._town_map), policy._town_map_active,
        tuple((town, id(layout)) for town, layout in policy._town_maps.items()),
        tuple(page.items) if page is not None else None,
        store in policy._town_store_attempted,
        frozenset(policy._town_visit_sale_signatures),
        frozenset(getattr(policy._town_visit_ledger,
                          "purchase_churn_class_exclusions", ())),
        policy._town_visit_sale_identify_charges, policy._fundraising_mode,
    )
    return decision_memo(
        policy, "gather_store_buy", board, key,
        lambda: _compute_store_buy_material(policy, board, need))


def _compute_store_buy_material(
    policy: Any, board: Any, need: Any
) -> StoreBuyMaterial:
    """Compute a supplier material on a decision-memo miss."""
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


def home_full_identification_target(policy: Any, board: Any) -> Any:
    """The already withdrawn Home-relief item, not the free pack target."""
    if not board.in_town or board.store is not None:
        return None
    relief = policy._home_full_relief
    sale = relief.get("sale") if relief is not None else None
    if sale is None:
        return None
    # The relief body follows its sale identity across inscription changes.
    name, tval, sval = sale[0]
    identity = (re.sub(r"\s+\{[^{}]*\}\s*$", "", name), tval, sval)
    return next((item for item in board.inventory
                 if policy._sale_item_identity(item) == identity), None)


def gather_home_full_identify(policy: Any, board: Any) -> IdentifyMaterial:
    """Read the same source tier as _carried_identify_command, no watch writes."""
    target = home_full_identification_target(policy, board)
    return IdentifyMaterial(source_held=target is not None and (
        policy._find_identification_source(
            board, full=target.known, reliable_only=(
                policy._identify_staff_success_rate(board) < STAFF_IDENTIFY_MIN_SUCCESS
            )) is not None))


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


@dataclass(frozen=True)
class HomeAtomicWithdrawMaterial:
    surface_ready: bool
    at_entrance: bool


def gather_home_atomic_withdraw(policy: Any, board: Any) -> HomeAtomicWithdrawMaterial:
    visit = policy._store_visit
    step_off = getattr(policy, "_store_entrance_step_off", None)
    surface_ready = bool(
        board.store is None
        and policy._shopping_approach_store_type == STORE_HOME
        and policy._home_atomic_withdraw_pending is None
        and (visit is None or visit.store_type == STORE_HOME)
        and (step_off is None or step_off[0] == policy._decision_sequence))
    entrance = board.grid_at(board.player.position)
    return HomeAtomicWithdrawMaterial(
        surface_ready, entrance is not None and entrance.store_number == STORE_HOME)


def verdict_home_atomic_withdraw(material: HomeAtomicWithdrawMaterial) -> Admission:
    if not material.surface_ready:
        return refused(("wrong-surface-or-pending",))
    if not material.at_entrance:
        return refused(("not-at-home-entrance",))
    return ADMIT


def gather_home_take(policy: Any, board: Any) -> HomeWithdrawMaterial:
    target, owner, _quantity, _letter = policy._terminal_home_take
    return HomeWithdrawMaterial(True, any(item is target for item in policy._home_knowledge_items)
                                and item_available(policy, board, target, owner, "withdraw"))


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
NO_REFUSAL = "no-refusal"
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
    no_refusal_reason: str = ""


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
    # The existing session.prepare refusal, before its caller's failure commit.
    "equipment-dispatch-rejected",
    "item-command-reserved", "disposal-quantity-invalid",
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
STORE_BUY_CODES = frozenset({"supplier-unreachable", "no-matching-offer", "page-not-composable", "store-page-not-fresh", "sale-item-unavailable", "sale-retains-digging-tool", "sale-not-accepted", "store-observation-current"})
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
HOME_WITHDRAW_CODES = frozenset({
    "reservation-unavailable", "wrong-surface-or-pending", "not-at-home-entrance", "home-recovery-no-work",
})
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
    "home_atomic_withdraw_clear": (Server("home-errand"), Server("home-visit")),
    "digger_withdrawal_resolved": (Server("home-errand"),),
    "identification_need_clear": (Server("identification"),),
    # Always ready (the quest-entry contract owns quest carry).
    "quest_carry_ready": (),
    "combat_weapon_ready": _TRANSACTION_SERVERS,
    # The forced-visit departure's existing HARD-only gate.
    "depth_abilities": _TRANSACTION_SERVERS,
    "equipment_observed": (),
    "store_transfer_clear": (
        Server("store-router"), Server("shop-buy"), Server("shop-sell"), Server("home-visit")),
    "equipment_transfer_clear": _TRANSACTION_SERVERS,
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
    "home-recovery-no-work": (),
    "store-observation-current": (),
    "item-command-reserved": (),
    "disposal-quantity-invalid": (),
    "equipment-dispatch-rejected": (),
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
    "wrong-surface-or-pending": (),
    "not-at-home-entrance": (),
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
        "supplier-unreachable", "no-matching-offer", "page-not-composable",
        "store-page-not-fresh", "sale-item-unavailable", "sale-retains-digging-tool", "sale-not-accepted",
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
    from hengbot.town_pack_headroom import organizing
    if not (organizing(policy, board) or policy._town_space_deposit_actionable(board)):
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


def home_disposal_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """Only the sale pipeline's actual identify branch owns identification.

    Destruction delegates to verified-disposal; absent/completed targets and
    leaving that pipeline are its settlements, never identification refusals.
    """
    pending = policy._home_disposal_pending
    if pending is None or not board.in_town or board.store is not None:
        return None
    target = policy._home_disposal_inventory_item(board)
    if pending[1] != "destroy" and target is not None and not target.known:
        return TerminalRef("home-disposal-identify", (policy._item_signature(target),))
    return TerminalRef(NO_REFUSAL, ("home-disposal-settle-or-delegate",))


def gather_home_disposal_identify(policy: Any, board: Any) -> IdentifyMaterial:
    return IdentifyMaterial(source_held=policy._find_identification_source(
        board, full=False, reliable_only=True) is not None)


def home_full_identify_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    target = home_full_identification_target(policy, board)
    if target is None:
        return None
    return TerminalRef("home-full-identify", (policy._item_signature(target),))


def home_withdraw_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    """The approach rungs: walk to Home for the filed withdrawal.  Other
    stores (store-buy) and other Home requests have no terminal here yet."""
    target = home_withdraw_target(policy, board)
    if target is None:
        return None
    request = policy._home_visit.request
    return TerminalRef("home-withdraw", (target, tuple(request.batch)))


def home_atomic_withdraw_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    if board is None:
        return None
    context = getattr(policy, "_terminal_home_take", None)
    if context is not None:
        target, owner, quantity, letter = context
        return TerminalRef("home-take", (
            policy._item_signature(target), getattr(target, "slot", ""), owner, quantity, letter))
    material = gather_home_atomic_withdraw(policy, board)
    return TerminalRef("home-atomic-withdraw", (material.surface_ready, material.at_entrance))


def home_relief_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    # Like town-special, this dispatcher must retain its effect confirmations,
    # candidate misses and scan requests. Its child entries admit actual work.
    return TerminalRef(NO_REFUSAL, ("home-relief-dispatch",))


def home_rearm_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    # This selector only files a request or advances/exits a Home page. The
    # physical take belongs to home-atomic-withdraw, after address observation.
    return TerminalRef(NO_REFUSAL, ("home-rearm-file-or-scan",))


@dataclass(frozen=True)
class EquipmentCommandMaterial:
    executable: bool
    current_action: bool
    right_surface: bool
    prepared_matches: bool


def gather_equipment_command(policy: Any, board: Any) -> EquipmentCommandMaterial:
    session, action, observation, key, context_identity = policy._terminal_equipment_command
    from hengbot.equipment_transaction_planner import PHASE_EQUIP
    needs_home = session.physical_context == "home" or action.phase != PHASE_EQUIP
    candidate = (action, observation, key, context_identity)
    return EquipmentCommandMaterial(
        session.executable, action == session.current_action,
        observation.in_home == needs_home,
        session._prepared is None or session._prepared == candidate)


def verdict_equipment_command(material: EquipmentCommandMaterial) -> Admission:
    if not (material.executable and material.current_action
            and material.right_surface and material.prepared_matches):
        return refused(("equipment-dispatch-rejected",))
    return ADMIT


def equipment_transaction_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    context = getattr(policy, "_terminal_equipment_command", None)
    if context is None:
        # Replanning, restoration, observation barriers and named failures must
        # run even when the selected command cannot be prepared.
        return TerminalRef(NO_REFUSAL, ("equipment-transaction-dispatch",))
    session, action, _observation, key, context_identity = context
    material = gather_equipment_command(policy, board)
    return TerminalRef("equipment-command", (
        session.target_loadout_id, session.index, action.kind,
        action.item_identity, key, context_identity,
        (material.executable, material.current_action,
         material.right_surface, material.prepared_matches)))


@dataclass(frozen=True)
class ItemCommandMaterial:
    available: bool
    partial: bool
    quantity: int | None
    count: int


def gather_item_command(policy: Any, board: Any) -> ItemCommandMaterial:
    kind, target, owner, _address = policy._terminal_item_command
    sink = kind if kind == "overweight-surplus" else kind.split("-")[0]
    verdict = reservation_verdict(policy, board, target, owner, sink)
    return ItemCommandMaterial(verdict.owner is None, kind == "overweight-surplus",
                               verdict.quantity, target.count)


def verdict_item_command(material: ItemCommandMaterial) -> Admission:
    if not material.available:
        return refused(("item-command-reserved",))
    if material.partial and (material.quantity is None
                             or not 0 < material.quantity <= material.count):
        return refused(("disposal-quantity-invalid",))
    return ADMIT


def item_command_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    context = getattr(policy, "_terminal_item_command", None)
    if context is None:
        # Keep candidate selection, effect settlement, alternative buyers and
        # named failures; their actual serializer is admitted at its own seam.
        return TerminalRef(NO_REFUSAL, ("item-command-dispatch",))
    kind, target, owner, address = context
    material = gather_item_command(policy, board)
    return TerminalRef("item-command", (
        kind, policy._item_signature(target), getattr(target, "slot", ""), owner, address,
        material.available, material.partial, material.quantity, material.count))


def _commit_item_command(policy: Any, board: Any, terminal: TerminalRef,
                          admission: Admission) -> None:
    # Retain the denied serializer's ownership/invalid-quantity diagnostic.
    # The caller still owns its no-step, failed-attempt or alternative choice.
    kind, target, owner, address = policy._terminal_item_command
    if kind in {"wield", "takeoff"}:
        item_available(policy, board, target, owner, kind)
        return
    reserved_item_command(policy, board, kind, target, owner, address=address)


def gather_blocked_recall(policy: Any, board: Any) -> DepartureMaterial:
    dungeon_id, minimum, strict = policy._terminal_blocked_recall
    if strict and not minimum:
        return gather_recall_departure(policy, board)
    depth = policy._dungeon_entry_depth(board, dungeon_id, via_recall=True)
    if minimum:
        values = policy._departure_minimum(board, depth)["values"]
    else:
        # The repetition remedy's ordinary branch checks food/two scrolls
        # and _dungeon_entry_allowed, not the optional supply/loadout leaves
        # of the normal town-recall dispatcher. Preserve that exact boundary.
        expedition = policy._morivant_full_identify
        recall = policy._supply_ledger(board, depth)["recall"]
        values = {
            "food_ready": policy._food_ready(board),
            "recall_departure_ready": policy._count_recall_scrolls(board) >= 2
                and recall.count >= max(1, recall.required_return),
            "equipment_transfer_clear": not (expedition is not None and expedition.temporary_deposits),
            "digger_withdrawal_resolved": not policy._home_digger_withdraw_pending
                or policy._digger_fallback_bought_this_visit,
            "depth_abilities": policy._destination_depth_allowed(board, depth),
            "equipment_departure_ready": policy._equipment_departure_ready(
                board, destination_depth=depth, commit=False),
        }
    return DepartureMaterial(tuple(name for name, value in values.items() if value is not True))


def blocked_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    context = getattr(policy, "_terminal_blocked_recall", None)
    if context is not None:
        return TerminalRef("blocked-recall", context)
    return TerminalRef(NO_REFUSAL, ("town-blocked-dispatch",))


def floor_exit_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    # Loot/triage and floor-exit dispatchers must retain their reactions.
    # Their read seams ask the existing recall terminal on the acting board;
    # Home/disposal children retain their own selected-operation admissions.
    return TerminalRef(NO_REFUSAL, ("floor-exit-dispatch",))


def opening_town_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    # Q34's readiness/blocked states must still select their suppliers. Gear,
    # shopping and fixed-quest actions keep their own operation verdicts.
    return TerminalRef(NO_REFUSAL, ("opening-q34-dispatch",))


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


def stockout_mining_intended_terminal(
    policy: Any, board: Any, *, failed: tuple[str, ...] | None = None,
) -> TerminalRef | None:
    if (not board.in_town or board.store is not None
            or policy._fundraising_mode is not None or board.player.recalling):
        return None
    return stockout_mining_supply_terminal(policy, board, failed=failed)


def stockout_mining_supply_terminal(
    policy: Any, board: Any, *, failed: tuple[str, ...] | None = None,
) -> TerminalRef | None:
    """Share supply eligibility with preparation, including on an open page.

    The dispatcher consumes the departure's failed leaves; terminal admission
    separately checks the physical surface before starting a mining run.
    """
    labels = {
        "recall_departure_ready": {"Word of Recall scrolls"},
        "food_ready": {"Food rations", "Device charges for food"},
        "light_ready": {"Flasks of oil"},
        "teleport_ready": {"Teleport scrolls"},
        "cure_critical_ready": {"Cure Critical Wounds potions"},
        "remove_curse_ready": {"Remove Curse scrolls", "*Remove Curse* scrolls"},
    }
    # Installing a one-run procurement plan is not ordinary dungeon entry.
    # Optional catalogue/identification work can remain pending; physical
    # transfers must settle before another expedition can own the board.
    if (policy._equipment_transaction_session is not None
            or policy._home_atomic_withdraw_pending is not None
            or policy._home_atomic_deposit_pending is not None
            or policy._home_pending_item is not None
            or policy._home_pending_batch):
        return None
    if failed is None:
        failed = gather_recall_departure(policy, board).failed
    failed = tuple(name for name in failed
                   if name not in {"equipment_departure_ready", "home_candidate_resolved",
                                   "identification_need_clear", "departure_identification_need_clear"})
    blocked = {row["item"] for row in policy.procurement_requirements(board)
               if row.get("blocked_reason") == "no-actionable-supplier"}
    if not failed or any(not (labels.get(name, set()) & blocked) for name in failed):
        return None
    return TerminalRef("fundraising", ("supply-stockout",))


def departure_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    if not board.in_town or board.store is not None or board.player.class_id < 0:
        return None
    # Only the scroll-read branch owns departure. The dispatcher also selects
    # remedies and named closes, whose child entries own their own terminals.
    if getattr(policy, "_terminal_town_recall_read", False):
        return TerminalRef("departure-recall", ())
    return TerminalRef(NO_REFUSAL, ("town-special-dispatch",))


def recall_read_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    # Dungeon return reads pass through; town reads own the full recall gate.
    return TerminalRef("departure-recall", ()) if board.in_town else None


@dataclass(frozen=True)
class ShopPageMaterial:
    composable: bool


def gather_shop_page(policy: Any, board: Any) -> ShopPageMaterial:
    return ShopPageMaterial(policy._can_compose_shop_observation(board))


def verdict_shop_page(material: ShopPageMaterial) -> Admission:
    if not material.composable:
        return refused(("page-not-composable",))
    return ADMIT


def shop_page_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    observation = policy._shop_observation
    if observation is None:
        return None
    if not policy._can_compose_shop_observation(board) and policy._can_resume_magic_shelf(board):
        return TerminalRef(NO_REFUSAL, ("shop-resume-delegated-route",))
    return TerminalRef("shop-page", (observation[0].store_type, observation[1]))


def _commit_shop_page(policy: Any, board: Any, terminal: TerminalRef,
                      admission: Admission) -> None:
    observation = policy._shop_observation
    if (observation is not None and board.store is None
            and observation[0].store_type != STORE_HOME
            and board.grid_at(board.player.position) is not None
            and board.grid_at(board.player.position).store_number == observation[0].store_type
            and observation[0].page_top not in (None, 0)):
        policy._shop_observation = None
        policy.last_reason = "shop:one-shot-page-not-zero"
    family = policy._claim_family_of(policy.last_reason)
    if family not in {"shop-buy", "shop-sell", "store-router"}:
        family = "store-router"
    policy._offer_execution_no_step(
        producer=family,
        work_id=f"shop-page:{terminal.args[0]}:{policy._decision_sequence}",
        cause="page-not-composable")


@dataclass(frozen=True)
class StagedStoreMaterial:
    fresh: bool


def gather_staged_store(policy: Any, board: Any) -> StagedStoreMaterial:
    visit = policy._store_visit
    return StagedStoreMaterial(bool(
        board.store is not None and visit is not None
        and visit.operation_posted and not visit.operation_released
        and visit.operation_key is not None
        and board.store.store_type == visit.store_type
        and visit.posted_turn is not None and board.turn >= visit.posted_turn))


def verdict_staged_store(material: StagedStoreMaterial) -> Admission:
    if not material.fresh:
        return refused(("store-page-not-fresh",))
    return ADMIT


def staged_store_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    visit = policy._store_visit
    if visit is None or not visit.operation_posted or visit.operation_released or visit.operation_key is None:
        return None
    if (gather_staged_store(policy, board).fresh and visit.store_type == STORE_HOME
            and policy._inventory_overweight(board) and policy._home_is_full(board)
            and visit.operation_key.startswith(SELL_KEY)
            and policy._home_atomic_deposit_pending is not None):
        return TerminalRef(NO_REFUSAL, ("full-page-supersedes-weight-deposit",))
    return TerminalRef("staged-store-operation", (visit.store_type, visit.operation_key))


@dataclass(frozen=True)
class StoreSaleMaterial:
    target_present: bool
    available: bool = True
    retained: bool = False
    accepted: bool = True
    refused_before: bool = False


def store_sale_target(policy: Any, board: Any) -> Any:
    context = getattr(policy, "_terminal_store_sale", None)
    if context is not None:
        return next((item for item in board.inventory
                     if item.slot == context[0] and policy._item_signature(item) == context[1]), None)
    state = policy._overweight_surplus_disposal
    pending = state.get("pending") if state is not None else None
    if pending is None:
        return None
    return next((item for item in board.inventory
                 if policy._sale_item_identity(item) == pending["identity"]), None)


def gather_store_sale(policy: Any, board: Any) -> StoreSaleMaterial:
    item = store_sale_target(policy, board)
    if item is None:
        return StoreSaleMaterial(False)
    store = board.store
    return StoreSaleMaterial(
        True, available=item_available(policy, board, item, "shop-sell", "sell"),
        retained=policy._sale_retains_digging_tool(board, item),
        accepted=store is not None and policy._store_accepts_sale(store.store_type, item),
        refused_before=(policy._item_signature(item) in policy._unsellable_items
                        or (store is not None and store.store_type in policy._store_sale_refused)))


def verdict_store_sale(material: StoreSaleMaterial) -> Admission:
    if not material.target_present or not material.available:
        return refused(("sale-item-unavailable",))
    if material.retained:
        return refused(("sale-retains-digging-tool",))
    if not material.accepted or material.refused_before:
        return refused(("sale-not-accepted",))
    return ADMIT


def store_sale_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    context = getattr(policy, "_terminal_store_sale", None)
    if context is not None:
        return TerminalRef("store-sell", (context[1], context[0], context[2]))
    state = policy._overweight_surplus_disposal
    pending = state.get("pending") if state is not None else None
    if pending is None:
        return None
    return TerminalRef("store-sell", (pending["signature"],))


def _commit_store_sale(policy: Any, board: Any, terminal: TerminalRef,
                        admission: Admission) -> str:
    item = store_sale_target(policy, board)
    material = gather_store_sale(policy, board)
    if not material.target_present:
        policy._last_sell_sig = None
        policy._store_sell_stuck_count = 0
    elif material.available and material.retained:
        policy._batch_sell_pending = None
    elif material.available and not material.accepted:
        policy._unsellable_items.add(policy._item_signature(item))
        if board.store is not None:
            policy._set_town_store_attempted(board.store.store_type, board.turn, "sell-no-item")
        policy._batch_sell_pending = None
        policy._last_sell_sig = None
        policy._store_sell_stuck_count = 0
    policy.last_reason = ("shop:retain-standing-digging-tool"
                          if material.target_present and material.available and material.retained
                          else terminal.args[2] if len(terminal.args) > 2
                          else "shop:unsellable-leave")
    policy._offer_store_sale_leave(board)
    return LEAVE_STORE_KEY


def gather_store_route(policy: Any, board: Any) -> tuple[StoreBuyMaterial, ...]:
    store = policy._shopping_approach_store_type
    plan = policy._town_errand_plan
    categories = plan.need_categories.get(store, ()) if plan is not None else ()
    return tuple(gather_store_buy(policy, board, TownNeed(store, category, "normal"))
                 for category in categories)


def verdict_store_route(materials: tuple[StoreBuyMaterial, ...]) -> Admission:
    admissions = tuple(verdict_store_buy(material) for material in materials)
    if not admissions or any(admission.admitted for admission in admissions):
        return ADMIT
    return refused(code for admission in admissions for code in admission.codes)


def shopping_intended_terminal(policy: Any, board: Any) -> TerminalRef | None:
    withdrawal = home_withdraw_intended_terminal(policy, board)
    if withdrawal is not None:
        return withdrawal
    store = policy._shopping_approach_store_type
    if not board.in_town or board.store is not None or store is None or store == STORE_HOME:
        return None
    plan = policy._town_errand_plan
    categories = plan.need_categories.get(store, ()) if plan is not None else ()
    return TerminalRef("store-route", (store, tuple(categories))) if categories else None


def visit_intended_terminal(policy: Any, board: Any, store: int) -> TerminalRef | None:
    """A detector borrows the concrete errand before acquiring a real visit."""
    if store == STORE_HOME:
        request = policy._home_visit.request
        if request is None:
            return None
        if request.kind == HomeVisitKind.WITHDRAW:
            target = request.address if request.address is not None else request.item_identity
            return TerminalRef("home-withdraw", (target, tuple(request.batch)))
        if request.kind == HomeVisitKind.RECOVERY:
            return TerminalRef("home-recovery", (request.requester,))
        if request.kind == HomeVisitKind.DEPOSIT:
            return TerminalRef("home-deposit", (request.item_identity,))
        if request.kind == HomeVisitKind.EQUIPMENT_MUTATION:
            return equipment_transaction_intended_terminal(policy, board)
        return TerminalRef(NO_REFUSAL, ("home-scan", request.requester))
    plan = policy._town_errand_plan
    categories = tuple(plan.need_categories.get(store, ())) if plan is not None else ()
    return TerminalRef("store-route", (store, categories))


def verdict_visit(policy: Any, board: Any, terminal: TerminalRef) -> Admission:
    """Use the borrowed operation, or the information a visit can still read."""
    if terminal.terminal_id == "home-recovery":
        return (ADMIT if not policy._home_knowledge_current
                else refused(("home-recovery-no-work",)))
    store, categories = terminal.args
    if not categories:
        return (refused(("store-observation-current",))
                if store in policy._town_store_attempted else ADMIT)
    materials = tuple(gather_store_buy(policy, board, TownNeed(store, category, "normal"))
                      for category in categories)
    return verdict_store_route(materials)


def rung_terminal(policy: Any, rung_name: str, board: Any) -> TerminalRef | None:
    """The rung's declared terminal on ``board``: a TerminalRef, NOT_APPLICABLE,
    a reason-bearing NO_REFUSAL marker, or None (no board or terminal)."""
    decl = TERMINALS.get(rung_name)
    if board is None or decl is None:
        return None
    if decl.mode == NO_REFUSAL:
        return TerminalRef(NO_REFUSAL, (rung_name, decl.no_refusal_reason))
    if decl.intended_terminal is None:
        return None
    return decl.intended_terminal(policy, board)


def delegated_command_intended_terminal(policy: Any, board: Any) -> TerminalRef:
    """Admit selection/settlement; the selected command owns its admission.

    Like item-command-dispatch, this is an enforced dispatcher, not another
    permanently non-refusable leaf. Batch sales validate their observed item
    and inscription; shopping admits teleport travel; dungeon selectors hand
    movement and attacks to their existing command producers.
    """
    return TerminalRef(NO_REFUSAL, ("delegated-command-dispatch",))


# S2 exit: every production rung has an explicit final mode.
SHADOW_RUNGS: frozenset[str] = frozenset()
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

# Non-refusable selectors and named closes (round-10 classification b).
NO_REFUSAL_REASONS = {
    '_chest_processing_key#1': 'not a town errand: drop, approach, search, disarm, open and collect a chest; src/hengbot/policy_identification.py:82',
    '_chest_processing_key#2': 'not a town errand: drop, approach, search, disarm, open and collect a chest; src/hengbot/policy_identification.py:82',
    '_normal_loot_key#1': 'not a town errand: defend, pick up or walk to visible floor loot; src/hengbot/policy_identification.py:1322',
    '_normal_loot_key#2': 'not a town errand: defend, pick up or walk to visible floor loot; src/hengbot/policy_identification.py:1322',
    '_kill_quest_floor_recovery_key': 'not a town errand: recover quest depth by walking, waiting or ordinary stairs; src/hengbot/policy_quest.py:5899',
    '_start_kill_quest_regeneration': 'not a town errand: walk to upstairs, ascend or name an exhausted-floor wait; src/hengbot/policy.py:19380',
    "_town_order_step4_key#1": "Walk to the bounty office and answer its cash-out prompt for observed wanted remains; unavailable routes are named closes; src/hengbot/policy_town.py:2354",
    "_town_order_step4_key#2": "Walk to the bounty office and answer its cash-out prompt for observed wanted remains; unavailable routes are named closes; src/hengbot/policy_town.py:2354",
    "town-progress-committed-loot": "not a town errand: continue pickup or walking to committed floor loot; src/hengbot/policy_town.py:1668",
    "_home_catalogue_work_key": "Request or observe a read-only Home catalogue, adopt its observed rows, or exit; src/hengbot/policy.py:6945",
    "_home_full_knowledge_key": "Request or await a read-only Home census, or exit an incompatible store; src/hengbot/policy_home.py:1390",
    "home-errand-knowledge": "Request or await a filed take's read-only census, or exit before requesting; src/hengbot/policy_home.py:1416",
    "home-full-knowledge": "Request or await a read-only Home census, or exit before requesting; src/hengbot/policy_home.py:1390",
    "home-knowledge-after-exit": "Request or await a read-only Home census after the observed exit; src/hengbot/policy_home.py:1390",
    "_released_restock_store_key": "Delegate each supplier walk to the shopping terminal; unreachable suppliers produce a visible named close; src/hengbot/policy_shop.py:1015",
    "_recall_restock_key": "Observe stock turnover or queue mining preparation; supplier walking delegates to the shopping terminal; src/hengbot/policy.py:15758",
    '_blocking_escape_melee_key': 'tactical survival/combat: not a town errand; src/hengbot/policy.py:19599',
    '_breeder_breakthrough_escape_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:3710',
    '_breeder_breakthrough_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:3647',
    '_choke_engagement_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:3503',
    '_detected_threat_preparation_key': 'tactical survival/combat: not a town errand; src/hengbot/policy.py:19011',
    '_emergency_item': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:1692',
    '_esp_threat_rest_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:1078',
    '_fruitless_disengage_key': 'tactical survival/combat: not a town errand; src/hengbot/policy.py:18237',
    '_immobile_breeder_giveup_key': 'tactical survival/combat: not a town errand; src/hengbot/policy.py:18916',
    '_item_destroying_breeder_leave_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:257',
    '_melee_swarm_combat_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:3276',
    '_paralyzer_prevention_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:2406',
    '_ranged_attack_key#1': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:1231',
    '_ranged_attack_key#2': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:1231',
    '_summoner_ranged_kill_key': 'tactical survival/combat: not a town errand; src/hengbot/policy.py:12686',
    '_town_random_teleport_suppression_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_town.py:5442',
    '_unseen_retreat_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_supply.py:1777',

    "_wield_digging_tool_key": "dungeon-only: not a town errand; src/hengbot/policy.py:12259 caller requires not snapshot.in_town",
    '_dig_to_known_downstairs_key': "delegated: caller's terminal governs; src/hengbot/policy_fundraising.py:829",
    '_entrance_travel_key': "delegated: caller's terminal governs; src/hengbot/policy.py:16497",
    '_step_toward': "delegated: caller's terminal governs; src/hengbot/policy_navigation.py:1828",
    '_step_toward:departure': "delegated: caller's terminal governs; src/hengbot/policy_navigation.py:1828",
    '_step_toward:escape': "delegated: caller's terminal governs; src/hengbot/policy_navigation.py:1828",
    '_step_toward:hunt': "delegated: caller's terminal governs; src/hengbot/policy_navigation.py:1828",
    '_step_toward:positioning': "delegated: caller's terminal governs; src/hengbot/policy_navigation.py:1828",
    'idle-fallback': "delegated: caller's terminal governs; src/hengbot/policy.py:12465",
    'navigator.decide': "delegated: caller's terminal governs; src/hengbot/policy.py:10944",

    '_conquest_loot_key': 'dungeon-only: not a town errand; src/hengbot/policy_quest.py:1578',
    '_esp_threat_hunt_key': 'dungeon-only: not a town errand; src/hengbot/policy_combat.py:942',
    '_fundraising_combat_equipment_key': 'dungeon-only: not a town errand; src/hengbot/policy_fundraising.py:496',
    '_mining_unbeatable_unique_abort_key': 'dungeon-only: not a town errand; src/hengbot/policy_fundraising.py:536',
    '_mining_loadout_rollback_key': 'dungeon-only: not a town errand; src/hengbot/mining_loadout.py rollback_key returns None in town',
    '_pack_pressure_identify_key': 'dungeon-only: not a town errand; src/hengbot/policy_identification.py:378',
    '_return_to_town_key#1': 'dungeon-only: not a town errand; src/hengbot/policy_town.py:7451',
    '_return_to_town_key#2': 'dungeon-only: not a town errand; src/hengbot/policy_combat.py:3702',
    '_return_to_town_key#3': 'dungeon-only: not a town errand; src/hengbot/policy_town.py:7451',
    '_unprofitable_unique_disengage_key': 'dungeon-only: not a town errand; src/hengbot/policy.py:18414',

    "_direction_key#1": "Convert adjacent coordinates to a direction key; no transaction, resource use or entry is selected.",
    "_direction_key#2": "Convert adjacent coordinates to a direction key; no transaction, resource use or entry is selected.",
    "_explore_step#2": "Select a destination coordinate; the separate movement entry owns the game command.",
    "_flee_step#2": "Select a retreat coordinate; the separate movement entry owns the game command.",
    "_flee_step#3": "Select a retreat coordinate; the separate movement entry owns the game command.",
    "_flee_step#4": "Select a retreat coordinate; the separate movement entry owns the game command.",
    "_home_full_skip_key": "Retain the unresolved item and clear its selection; the emitted wait only observes that named close.",
    "_hunt_step#1": "Select a pursuit coordinate; the separate movement entry owns the game command.",
    "_hunt_step#2": "Select a pursuit coordinate; the separate movement entry owns the game command.",
    "_hunt_step#3": "Select a pursuit coordinate; the separate movement entry owns the game command.",
    "_unseen_retreat_intercept_key": "Hold an established choke with a direction key or wait; no travel, entry or resource use is selected.",
    "frontier-probe": "Select a probe coordinate; the separate movement entry owns the game command.",
    "oscillating-probe": "Select a probe coordinate; the separate movement entry owns the game command.",
}


# Every ``_town_producer_entry`` rung (checked against the source by AST).
TERMINALS: dict[str, TerminalDecl] = {
    **{name: TerminalDecl(delegated_command_intended_terminal, ENFORCE) for name in (
        "_cross_town_shopping_key", "_batch_sell_key", "_immobile_summoner_key",
        "_ranged_attack_key", "_normal_loot_key", "_explore_step")},
    "_finish_mining_floor": TerminalDecl(floor_exit_intended_terminal, ENFORCE),
    "_victory_loot_key": TerminalDecl(floor_exit_intended_terminal, ENFORCE),
    "_town_blocked_key": TerminalDecl(blocked_intended_terminal, ENFORCE),
    "_opening_q34_town_key": TerminalDecl(opening_town_intended_terminal, ENFORCE),
    "_town_restore_weapon_key": TerminalDecl(item_command_intended_terminal, ENFORCE),
    "_heavy_curse_inscription_key": TerminalDecl(item_command_intended_terminal, ENFORCE),
    **{name: TerminalDecl(item_command_intended_terminal, ENFORCE) for name in (
        "_overweight_surplus_sale_key", "_town_overflow_destroy_key", "_worthless_junk_destroy_key",
        "_full_pack_destroy_key", "_town_destroy_key", "verified-disposal")},
    **{name: TerminalDecl(equipment_transaction_intended_terminal, ENFORCE) for name in (
        "_equipment_transaction_home_key", "_equipment_transaction_town_key",
        "_equipment_transaction_town_key#1", "_equipment_transaction_town_key#2",
        "_equipment_transaction_town_owner_key")},
    "home-atomic-withdraw": TerminalDecl(home_atomic_withdraw_intended_terminal, ENFORCE),
    "_home_full_relief_key": TerminalDecl(home_relief_intended_terminal, ENFORCE),
    "_home_rearm_key": TerminalDecl(home_rearm_intended_terminal, ENFORCE),
    "_store_sell_key": TerminalDecl(store_sale_intended_terminal, ENFORCE),
    "_release_staged_store_operation": TerminalDecl(staged_store_intended_terminal, ENFORCE),
    "_atomic_shop_transaction_key": TerminalDecl(shop_page_intended_terminal, ENFORCE),
    "_fixed_quest_key#1": TerminalDecl(fixed_quest_return_intended_terminal, ENFORCE),
    "_fixed_quest_key#2": TerminalDecl(fixed_quest_intended_terminal, ENFORCE),
    **{name: TerminalDecl(None, NO_REFUSAL, reason)
       for name, reason in NO_REFUSAL_REASONS.items()},
    **{name: TerminalDecl(None, EXEMPT_SURVIVAL) for name in EXEMPT_RUNGS},
    # S2-d terminals: declared and recorded; ENFORCE with the S2 flip.
    "_town_space_deposit_key": TerminalDecl(space_deposit_intended_terminal, ENFORCE),
    "_town_remove_curse_key": TerminalDecl(curse_remove_intended_terminal, ENFORCE),
    "_town_enchant_launcher_key": TerminalDecl(enchant_launcher_intended_terminal, ENFORCE),
    "_town_equipped_identification_key": TerminalDecl(
        identify_equipped_intended_terminal, ENFORCE),
    "_town_device_processing_key": TerminalDecl(
        device_identification_intended_terminal, ENFORCE),
    "town-item-processing": TerminalDecl(carried_identification_intended_terminal, ENFORCE),
    "_home_disposal_processing_key": TerminalDecl(home_disposal_intended_terminal, ENFORCE),
    "home-full-identification": TerminalDecl(home_full_identify_intended_terminal, ENFORCE),
    **{name: TerminalDecl(shopping_intended_terminal, ENFORCE) for name in (
        "_shopping_approach_key", "_shopping_approach_key#1",
        "_shopping_approach_key#2")},
    "home-atomic-deposit": TerminalDecl(home_atomic_deposit_intended_terminal, ENFORCE),
    "_open_home_deposit_key": TerminalDecl(open_home_deposit_intended_terminal, ENFORCE),
    "_defer_home_full_deposit": TerminalDecl(home_full_defer_intended_terminal, ENFORCE),
    "_descent_step": TerminalDecl(descent_route_intended_terminal, ENFORCE),
    "direct-descent": TerminalDecl(direct_descent_intended_terminal, ENFORCE),
    "town-teleport": TerminalDecl(cross_town_intended_terminal, ENFORCE),
    **{name: TerminalDecl(fundraising_intended_terminal, ENFORCE) for name in (
        "_fundraising_key#1", "_fundraising_key#2")},
    "supply-stockout-mining": TerminalDecl(stockout_mining_intended_terminal, ENFORCE),
    "supply-stockout-prepare": TerminalDecl(
        lambda policy, board: TerminalRef(NO_REFUSAL, ("supply-stockout-prepare",)), ENFORCE),
    "_town_special_key": TerminalDecl(departure_intended_terminal, ENFORCE),
    "_read_dungeon_recall_scroll_key": TerminalDecl(recall_read_intended_terminal, ENFORCE),
}

# The verdict of each non-quest terminal kind (gather, then the pure verdict).
_TERMINAL_VERDICTS: dict[str, Callable[[Any, Any], Admission]] = {
    "blocked-recall": lambda policy, board: verdict_departure(gather_blocked_recall(policy, board)),
    "item-command": lambda policy, board: verdict_item_command(gather_item_command(policy, board)),
    "equipment-command": lambda policy, board: verdict_equipment_command(
        gather_equipment_command(policy, board)),
    "home-atomic-withdraw": lambda policy, board: verdict_home_atomic_withdraw(
        gather_home_atomic_withdraw(policy, board)),
    "home-take": lambda policy, board: verdict_home_withdraw(gather_home_take(policy, board)),
    "store-route": lambda policy, board: verdict_store_route(gather_store_route(policy, board)),
    "staged-store-operation": lambda policy, board: verdict_staged_store(gather_staged_store(policy, board)),
    "store-sell": lambda policy, board: verdict_store_sale(gather_store_sale(policy, board)),
    "shop-page": lambda policy, board: verdict_shop_page(gather_shop_page(policy, board)),
    NO_REFUSAL: lambda policy, board: ADMIT,
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
    "home-disposal-identify": lambda policy, board: verdict_identify_equipped(
        gather_home_disposal_identify(policy, board)),
    "home-full-identify": lambda policy, board: verdict_identify_equipped(
        gather_home_full_identify(policy, board)),
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


def _commit_home_disposal_identify(policy: Any, board: Any, terminal: TerminalRef,
                                   admission: Admission) -> None:
    policy._request_identification("normal")


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
    # The refusal, legacy hold and executor refer to the same immutable item.
    # Yielding leaves it held; a named close settles only that work identity.
    if (terminal in policy._town_visit_ledger.closed_terminals
            and policy._home_atomic_withdraw_pending is None):
        target = terminal.args[0]
        batch = terminal.args[1] if len(terminal.args) > 1 else ()
        held = (policy._home_pending_item, *policy._home_pending_batch)
        stored = {policy._item_signature(item) for item in policy._home_knowledge_items}
        for signature in dict.fromkeys((target, *batch)):
            if signature in held and signature not in stored:
                policy._defer_unobserved_home_withdrawal(signature)
        if (target in held and policy._home_pending_item is None
                and not policy._home_pending_batch):
            policy._home_withdrawal_queued = False
            policy._home_active_from_batch = False
        errand = policy._home_errand
        if errand.request is not None and errand.request.signature == target:
            errand.state = type(errand.state).FAILED
            errand.finish()
    home = policy._home_visit
    if home.report_unoperated("reservation-unavailable"):
        report = home.consume_report()
        policy._pending_home_visit_report = (
            f"home-visit:{report.request.requester}:{report.outcome}")


def _commit_visit_route(policy: Any, board: Any, terminal: TerminalRef,
                        admission: Admission) -> None:
    cause = policy._town_visit_ledger.closed_terminals.get(terminal)
    if cause is None:
        return
    policy._offer_execution_no_step(
        producer="store-router", work_id=repr(terminal), cause=cause)
    if terminal.terminal_id == "home-recovery":
        home = policy._home_visit
        if home.report_unoperated(admission.codes[0]):
            report = home.consume_report()
            policy._pending_home_visit_report = (
                f"home-visit:{report.request.requester}:{report.outcome}")



def _commit_home_atomic_withdraw(policy: Any, board: Any, terminal: TerminalRef,
                                 admission: Admission) -> None:
    if terminal.terminal_id == "home-atomic-withdraw":
        policy._offer_home_atomic_no_step("withdraw", admission.codes[0])


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


def _commit_fundraising_run(policy: Any, board: Any, terminal: TerminalRef,
                            admission: Admission) -> None:
    # These town rungs run the dungeon driver, not the departure dispatcher.
    # Keep its no-step confirmation and detection observation on a refused run.
    if policy._fundraising_mode not in {"mine", "scavenge"}:
        cause = "fundraising-mode-inactive"
    elif (policy._fundraising_mode == "scavenge"
          and not policy._detectionless_scavenge_allowed(board)):
        policy._settle_fundraising_detection(board)
        return
    else:
        cause = "outside-mining-floor"
    policy._offer_execution_no_step(
        producer="fundraising", work_id="fundraise:run", cause=cause)


# Rung-specific confirmation takes precedence when a terminal is shared by
# different producers; the other entries apply to the terminal kind.
REFUSAL_COMMITS: dict[str, Callable[[Any, Any, TerminalRef, Admission], str | None]] = {
    "item-command": _commit_item_command,
    "home-atomic-withdraw": _commit_home_atomic_withdraw,
    "shop-page": _commit_shop_page,
    "store-sell": _commit_store_sale,
    # The initiator only installs preparation. Missing mining supplies are
    # precisely the work that preparation must make visible to its suppliers.
    "supply-stockout-mining": lambda policy, board, terminal, admission:
        policy._town_producer_entry(
            "supply-stockout-prepare",
            lambda: policy._supply_stockout_mining_dispatch_key(board),
            family="fundraising", board=board),
    "_fundraising_key#1": _commit_fundraising_run,
    "_fundraising_key#2": _commit_fundraising_run,
    "identify-equipped": _commit_identify_equipped,
    "identify-device": _commit_identify_device,
    "identify-carried": _commit_identify_carried,
    "home-disposal-identify": _commit_home_disposal_identify,
    "home-withdraw": _commit_home_withdraw,
    "home-recovery": _commit_visit_route,
    "store-route": _commit_visit_route,
    "home-atomic-deposit": _commit_home_atomic_deposit,
    "cross-town": _commit_cross_town,
    "curse-remove": _commit_curse_remove,
    "enchant-launcher": _commit_enchant_launcher,
}


def commit_refusal(policy: Any, board: Any, terminal: TerminalRef | None, *,
                   rung_name: str | None = None) -> str | None:
    """Called by the entry when ``may_take_board`` refused (ENFORCE only)."""
    commit = (REFUSAL_COMMITS.get(rung_name or "")
              or REFUSAL_COMMITS.get(terminal.terminal_id)) if terminal is not None else None
    if commit is not None:
        return commit(policy, board, terminal, terminal_admission(policy, board, terminal))


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
                 else verdict_home_withdraw(gather_home_withdraw(
                     policy, board, target=terminal.args[0]))
                 if terminal.terminal_id == "home-withdraw"
                 else verdict_visit(policy, board, terminal)
                 if terminal.terminal_id in {"store-route", "home-recovery"}
                 else verdict(policy, board) if verdict is not None else ADMIT)
    if terminal.terminal_id == "quest-reward":
        here = board.grid_at(board.player.position)
        slots = max(1, here.object_count) if here is not None else 1
        if not permits(board, slots):
            admission = refused(("free_pack_slots_ready",))
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
    if ((family in EXEMPT_FAMILIES and family != "detectors")
            or board is None or terminal is None):
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
