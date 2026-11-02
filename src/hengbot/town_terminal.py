"""Whether a town owner may take the board: its terminal's admission (ROOT-FIX S1).

Design: plans/DESIGN-town-claim-rootfix-1023.md.  A town rung declares the
last action it intends on a board (``intended_terminal``).  Each terminal kind
splits into a material read (``gather_*``), a pure verdict that returns the
admission *and* its refusal codes from the same branch (``verdict_*``), and
the commit that only the terminal's own call site performs.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field, replace
from enum import Enum
import re
from typing import Any, Callable, NamedTuple

from hengbot.policy_constants import (
    DETECTED_THREAT_HOLD_MAX_GAME_TURNS,
    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
    STORE_STUCK_LIMIT,
    EQUIPMENT_SLOT_KEY,
    HOME_KNOWLEDGE_MACRO,
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
    SUPPLY_LABEL_KINDS,
    TOWN_TELEPORT_COST,
    TOWN_TRAVEL_STALL_LIMIT,
)
from hengbot.home_visit import HomeVisitKind
from hengbot.retired_values import retired_module
from hengbot.town_pack_budget import permits
from hengbot.town_quest_reward import holds_town, report_waits_for_room
from hengbot import town_end_mining
from hengbot.item_reservation import decision_memo, item_available, reservation_verdict, reserved_item_command
from hengbot.model import STORE_ALCHEMIST, STORE_HOME, Position
from hengbot.policy_types import (
    EXPECTATION_POP_SATISFIED,
    OWNER_EXPECTATION_MAX_TURNS,
    OwnerProgressCore,
    StoreVisitPhase,
    TownNeed,
)
from hengbot.quest_knowledge import QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER
from hengbot.town_arbiter import (
    RECALL_ACTIVATION_MAX_GAME_TURNS,
    UNREGISTERED_FAMILY,
    ClaimOwner,
    owner_families,
    owner_of,
    reason_owner_family,
)


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
    # The owner family the rung's entry admits under when its call site
    # names none (``RUNG_FAMILIES``); "" for a rung whose every call site
    # passes ``family=``.
    family: str = ""


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
# The terminals that leave the town level: refused while the report or the
# pickup of a town-map quest reward holds the town (town_quest_reward.holds_town,
# owner 2026-11-02 「空きを作って報告し、報酬を回収するまでを優先したい」).
TOWN_LEAVING_TERMINALS = frozenset({
    "inn-travel", "cross-town", "departure-recall", "descent", "descent-here", "fundraising",
})
QUEST_REWARD_FIRST = "quest-reward-first"
# The room makers, then the report and the pickup themselves.
_QUEST_REWARD_FIRST_SERVERS = (*_SPACE_SERVERS, Server("quest-request"))

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
TERMINAL_CODES |= CROSS_TOWN_CODES | FUNDRAISING_CODES | {QUEST_REWARD_FIRST}

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
    QUEST_REWARD_FIRST: _QUEST_REWARD_FIRST_SERVERS,
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
    """The expedition's inn trip; another producer's inn trip only while the
    town-map quest reward holds the town (town_quest_reward.holds_town)."""
    if not board.in_town or board.store is not None:
        return None
    destination = expedition_destination(policy, board)
    if destination is not None:
        return TerminalRef("cross-town", (destination,))
    travel = getattr(policy, "_terminal_town_travel", None)
    if travel is not None and holds_town(policy, board):
        return TerminalRef("inn-travel", travel)
    return None


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


# The procurement requirement labels (policy_supply.procurement_requirements)
# that supply each departure leaf.
LEAF_SUPPLY_LABELS: dict[str, frozenset[str]] = {
    "recall_departure_ready": frozenset({"Word of Recall scrolls"}),
    "food_ready": frozenset({"Food rations", "Device charges for food"}),
    "light_ready": frozenset({"Flasks of oil"}),
    "teleport_ready": frozenset({"Teleport scrolls"}),
    "cure_critical_ready": frozenset({"Cure Critical Wounds potions"}),
    "remove_curse_ready": frozenset({"Remove Curse scrolls", "*Remove Curse* scrolls"}),
}


def stockout_mining_supply_terminal(
    policy: Any, board: Any, *, failed: tuple[str, ...] | None = None,
) -> TerminalRef | None:
    """Share supply eligibility with preparation, including on an open page.

    The dispatcher consumes the departure's failed leaves; terminal admission
    separately checks the physical surface before starting a mining run.
    """
    labels = LEAF_SUPPLY_LABELS
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
    family = claim_family_of(policy, policy.last_reason)
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
    '_immobile_summoner_exit_key': 'tactical survival/combat: not a town errand; src/hengbot/policy_combat.py:471',
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


# --- Town ownership (structure stage 2 B, step 1) ---------------------------
# Owner 2026-10-28 「B: 場面の終点に一本化」: town_terminal is the one "who
# acts" authority.  The three claim parts that still steer live keys moved
# here: the rung -> family table, the census family of a reason, and the
# town errand / cross-area Home hold.  Slice 3 moved the state the hold reads
# here as well (``TownHold`` below).


# --- The town hold's records (structure stage 2 B, slice 4) ---------------
# The claim types the hold keeps (formerly claim_register): a claim names its
# owner family (``town_arbiter.ClaimOwner``), its goal (Reach / Observe /
# Terminal) and its state; the register keeps the standing claim, the
# suspended stack and the bars.  Plain data only: a goal holds a ``(y, x)``
# tuple, never a ``Position``, so the hold pickles into every checkpoint.

# A closing call that names no cell closes any Reach goal of its owners.
CLAIM_ANY_CELL = object()

ClaimState = Enum(
    "ClaimState",
    [
        ("ACTIVE", "active"),
        ("AWAITING", "awaiting"),
        ("SUSPENDED", "suspended"),
        ("COMPLETE", "complete"),
        ("RETIRED", "retired"),
    ],
    module=__name__,
    qualname="ClaimState",
    type=str,
)
ClaimState.__doc__ = "The five claim states of design section 3.1."

CLOSED_BY_RELEASE = "release"
CLOSED_BY_COMPLETE = "complete"
CLOSED_BY_RETIRED = "retired"
# Rev 9.2: an Observe claim older than its ``within`` closes as ``expired`` --
# neither a completion nor an abandonment.
CLOSED_BY_EXPIRED = "expired"
CLOSING_EVENTS = frozenset(
    {CLOSED_BY_RELEASE, CLOSED_BY_COMPLETE, CLOSED_BY_RETIRED, CLOSED_BY_EXPIRED}
)
# The release label of a suspended claim a floor change ended (design rev 10.1
# item 6, rule i); written by ``claim_suspended_exit``.
SUSPENDED_EXPIRED = "suspended-expired"

GOAL_REACH = "Reach"
GOAL_OBSERVE = "Observe"
GOAL_TERMINAL = "Terminal"


@dataclass(frozen=True)
class Goal:
    """One of the three declared goal kinds, as plain data.

    ``source`` (S2a.1) names where an ``Observe`` goal came from: the owner
    expectation a producer posted on this decision (its registry name), or
    the content label of the goal-typing row that declared it
    (the goal typing below).  The floor-change and expectation completions
    read it.  A goal pickled before S2a.1 has no ``source`` in its state and
    reads the class default ``None``.

    Rev 9.2 adds two Reach forms beside the cell:

    ``monster``  a moving target -- hunt, ``clear-descent``,
                 ``town:kill-mob-approach`` -- named by ``(index, race_id)``,
                 never by the cell it stood on; the claim continues while the
                 identity is unchanged.
    ``place``    a named place with no local-map cell (the wilderness walk to a
                 town), completed by its producer's own arrival test only.

    Both default to ``None``, so an older pickle reads them from the class.
    """

    kind: str
    cell: tuple[int, int] | None = None
    expectation: tuple[str, ...] = ()
    within: int | None = None
    effect: str | None = None
    source: str | None = None
    monster: tuple[int, int] | None = None
    place: str | None = None


def reach_goal(cell: tuple[int, int]) -> Goal:
    """Arrive at one cell, named as ``(y, x)`` rather than as a ``Position``."""
    return Goal(GOAL_REACH, cell=(int(cell[0]), int(cell[1])))


def reach_monster_goal(index: int, race_id: int) -> Goal:
    """Close with one monster, named by identity (rev 9.2, moving targets)."""
    return Goal(GOAL_REACH, monster=(int(index), int(race_id)))


def reach_place_goal(place: str) -> Goal:
    """Arrive at a named place that has no local-map cell (rev 9.2)."""
    return Goal(GOAL_REACH, place=str(place))


def observe_goal(
    expectation, within: int | None, source: str | None = None
) -> Goal:
    """See one of the named observable changes within a bound."""
    return Goal(
        GOAL_OBSERVE,
        expectation=tuple(sorted(str(name) for name in expectation)),
        within=None if within is None else int(within),
        source=None if source is None else str(source),
    )


def terminal_goal(effect: str) -> Goal:
    """Produce one effect; the decision ends with it."""
    return Goal(GOAL_TERMINAL, effect=str(effect))


@dataclass(frozen=True)
class ExecutionDeclaration:
    """Checkpoint-safe, producer-written work state, independent of lifecycle."""

    claim_id: int
    work_id: str
    revision: int
    producer: str
    state: str
    next_step: str | None = None
    arguments: tuple = ()
    operation_ref: str | None = None
    expected_effect: str | None = None
    continuation: str | None = None
    budget_ref: str | None = None
    evidence: str | None = None
    cause: str | None = None
    producer_entry: str | None = None


@dataclass(frozen=True)
class Claim:
    """One declared claim.  Frozen: a transition replaces it.

    S2a.1 adds three recorded facts, all defaulted so that a claim pickled
    before them (a restored checkpoint's register) unpickles with the class
    defaults -- a frozen dataclass restores its ``__dict__`` and reads a
    missing field from the class:

    ``floor``          ``snapshot.floor_key`` when the claim was opened; the
                       floor-change ``Observe`` goal completes when the board's
                       floor differs from it, and a ``Reach`` cell is only
                       compared on this floor.
    ``closed_reason``  the label the closing call gave (``release(label)``,
                       ``complete(label)``, ``suspend(label)``).
    ``survival``       the latest decision that owned the claim was survival
                       (``is_survival``); S2b.1 round 2
                       updates it on a continuing declaration.
    ``opened_turn``    (rev 9.2) the game turn the claim was opened on; the
                       floor-change ``Observe`` expires on it.

    S2b.1 (design rev 10.1) adds, with the same defaults-from-the-class cover:

    ``rank`` / ``rung``        the ladder rank and rung of the decision that
                               opened (or resumed) the claim
                               (``rung_of``); ``None`` on a claim
                               pickled before the ladder.
    ``suspended_sequence`` /   the decision sequence and game turn at which the
    ``suspended_turn``         claim was suspended; ``None`` while it is not.
    ``suspended_decisions`` /  (item 6) the decisions and game turns it spent
    ``suspended_turns``        suspended, summed over its suspensions; a resumed
                               ``Observe`` claim's ``within`` does not count
                               them.
    ``trigger_monsters``       (item 9) the ``(index, race_id)`` pairs of the
                               hostiles perceived when the claim opened, for a
                               Reach/Observe claim of a trigger family.
    ``last_perceived_turn``    (item 9) the game turn of the latest decision the
                               claim owned on which one of them was perceived.
    """

    claim_id: int
    owner: ClaimOwner
    goal: Goal
    state: ClaimState = ClaimState.ACTIVE
    non_discardable: bool = False
    closed: str | None = None
    opened_sequence: int | None = None
    floor: tuple[int, ...] | None = None
    closed_reason: str | None = None
    survival: bool = False
    opened_turn: int | None = None
    rank: int | None = None
    rung: str | None = None
    suspended_sequence: int | None = None
    suspended_turn: int | None = None
    suspended_decisions: int = 0
    suspended_turns: int = 0
    trigger_monsters: tuple[tuple[int, int], ...] = ()
    last_perceived_turn: int | None = None
    # A pre-declaration checkpoint reads this class default after unpickling.
    execution: ExecutionDeclaration | None = None

    @property
    def is_open(self) -> bool:
        """Not ended by an event and not suspended: it still owns its goal."""
        return self.closed is None and self.state not in (
            ClaimState.SUSPENDED,
            ClaimState.COMPLETE,
            ClaimState.RETIRED,
        )


# -- S2b.2: the bar table (design 3.2, 3.3, 5.4.1) ---------------------------

# A preemptor barred by the 50-turn safety rule (design 3.2): the owner is one
# of the threat-triggered families (``TRIGGER_FAMILIES``).
BAR_THREAT = "threat"
# An errand owner barred by retirement (design 3.3): it lifts when the durable
# part of the existing retirement clearance key changes (user decision
# 2026-09-26), never by the player's own movement and never by a clock.
BAR_ERRAND = "errand"


@dataclass(frozen=True)
class Bar:
    """One bar: ``(owner, goal, trigger monsters)`` and when it was set.

    Plain data, like a claim.  ``triggers`` are ``(index, race_id)`` pairs,
    never an index alone: Hengband reuses a dead monster's index for a new
    one.  ``last_perceived_turn`` is the game turn of the latest board on
    which one of them was perceived (the bar's own start when none was).

    ``rung`` (round 2) is the ladder rung of the claim that earned the bar
    (``rung_of_claim``).  ``clearance`` and ``reason`` are, for an errand bar, the durable
    part of the retirement clearance key when the bar was set and the reason
    it was computed for (``claim_errand_clearance``).
    """

    owner: ClaimOwner
    goal: Goal
    kind: str
    triggers: tuple[tuple[int, int], ...] = ()
    since_turn: int | None = None
    since_sequence: int | None = None
    last_perceived_turn: int | None = None
    claim_id: int | None = None
    ending: str | None = None
    clearance: object = None
    rung: str | None = None
    reason: str | None = None


_UNREAD = object()


def bar_after_board(
    bar: Bar,
    *,
    turn: int | None,
    perceived: frozenset,
    hold: int,
    clearance_of=None,
) -> Bar | None:
    """The bar as this board leaves it, or ``None`` when the board lifts it.

    A pure function of the bar and the board (design 5.4.1: the bar match is
    a pure function of the current snapshot and the key):

    * ``threat``: a trigger ``(index, race_id)`` in ``perceived`` moves
      ``last_perceived_turn`` to ``turn``; the bar lifts once more than
      ``hold`` game turns have passed since then with none of them perceived
      (the comparison of the detected-threat choke release it shares its
      clock with).
    * ``errand``: ``clearance_of(bar)`` is the durable part of the owner's
      retirement clearance key on this board; the bar stands while it equals
      the one recorded when the bar was set and lifts when it changes.  No
      clock: an errand bar never lifts by waiting or by walking.

    Nothing else lifts a bar: not the player's movement, not a changed target,
    not the trigger set growing or shrinking, not the floor.
    """
    if bar.kind == BAR_ERRAND:
        now = clearance_of(bar) if clearance_of is not None else _UNREAD
        if now is _UNREAD or now == bar.clearance:
            return bar
        return None
    if turn is None:
        return bar
    if any(tuple(pair) in perceived for pair in bar.triggers):
        if bar.last_perceived_turn == turn:
            return bar
        return replace(bar, last_perceived_turn=int(turn))
    last = bar.last_perceived_turn
    if last is None:
        last = bar.since_turn
    if last is not None and turn - last > hold:
        return None
    return bar


class ClaimRegister:
    """The town hold's claim register: one current claim and one counter.

    A register pickled before a field below existed has no attribute for
    it; every reader goes through ``getattr``.
    """

    def __init__(self) -> None:
        self._next_id = 1
        self._claim: Claim | None = None
        # S2b.1 (design rev 10.1 item 5): the claims a preemption suspended,
        # the most recent last.
        self._suspended: list[Claim] = []
        # S2b.2: the bar table, and the claims that ended since the last
        # declaration (``claim_set_bars`` bars them).  Readers use
        # ``getattr``.  Both lists are rebound, never mutated in place, so the
        # telemetry observer's shallow copy of the register stays isolated.
        self._bars: list[Bar] = []
        self._ended: list[Claim] = []

    # -- allocation ------------------------------------------------------

    def allocate(self) -> int:
        """The next id from this register's one monotonic source."""
        claim_id = self._next_id
        self._next_id += 1
        return claim_id

    @property
    def current(self) -> Claim | None:
        return self._claim

    def declare_execution(self, claim_id: int, *, work_id: str,
                          producer: str, state: str, next_step: str | None = None,
                          arguments: tuple = (), operation_ref: str | None = None,
                          expected_effect: str | None = None,
                          continuation: str | None = None,
                          budget_ref: str | None = None,
                          evidence: str | None = None,
                          cause: str | None = None,
                          producer_entry: str | None = None) -> ExecutionDeclaration | None:
        """Replace the named current/child declaration without altering the claim."""
        if state not in {"acting", "awaiting", "done", "releasing"}:
            raise ValueError(state)
        claim = self._claim
        if claim is None or claim.claim_id != claim_id:
            return None
        old = claim.execution
        revision = old.revision + 1 if old is not None else 1
        declaration = ExecutionDeclaration(
            claim_id, str(work_id), revision, str(producer), state,
            next_step, tuple(arguments), operation_ref, expected_effect,
            continuation, budget_ref, evidence, cause, producer_entry,
        )
        self._claim = replace(claim, execution=declaration)
        return declaration

    @staticmethod
    def _execution_ending(claim: Claim, closed: str | None,
                          label: str | None) -> Claim:
        declaration = claim.execution
        if declaration is None or closed is None:
            return claim
        state = "done" if closed == CLOSED_BY_COMPLETE else "releasing"
        ending = replace(
            declaration, revision=declaration.revision + 1, state=state,
            next_step=None, arguments=(), operation_ref=None,
            evidence=label if state == "done" else None,
            cause=label if state == "releasing" else None,
        )
        return replace(claim, execution=ending)

    # -- declaration -----------------------------------------------------

    def continues(
        self, owner: str | ClaimOwner, goal: Goal, non_discardable: bool = False
    ) -> bool:
        """Whether ``declare`` would keep the current claim's id."""
        claim = self._claim
        return (
            claim is not None
            and claim.closed is None
            and claim.state != ClaimState.SUSPENDED
            and claim.owner == owner_of(owner)
            and claim.goal == goal
        )

    def declare(
        self,
        owner: str | ClaimOwner,
        goal: Goal,
        *,
        non_discardable: bool = False,
        opened_sequence: int | None = None,
        floor: tuple[int, ...] | None = None,
        survival: bool = False,
        opened_turn: int | None = None,
        rank: int | None = None,
        rung: str | None = None,
        trigger_monsters: tuple[tuple[int, int], ...] = (),
        perceived_turn: int | None = None,
    ) -> Claim:
        """Declare (or continue) the claim that owns the decision being made.

        Rev 9.2's "a suspended claim does not continue" stands for the current
        claim: a declaration after its suspension does not continue it.  From
        S2b.1 a suspended claim comes back only through ``resume`` (design rev
        10.1 item 5), under its own id.

        S2b.1 facts: ``rank`` / ``rung`` and ``trigger_monsters``
        of a newly opened claim; ``survival`` follows the latest decision;
        ``perceived_turn`` -- the game turn, when one of the claim's trigger
        monsters is perceived on this board -- moves ``last_perceived_turn``
        forward.
        """
        declared_owner = owner_of(owner)
        claim = self._claim
        if self.continues(declared_owner, goal, non_discardable):
            # The same owner pursuing the same goal keeps its id, so a reader
            # can see one claim spanning the boards it took to reach the goal.
            changes: dict = {}
            if claim.state != ClaimState.ACTIVE:
                changes["state"] = ClaimState.ACTIVE
            # Round 2 (F2): a continuing claim records whether the decision
            # that continues it is survival.  Its rank and rung stay the ones
            # it was opened or resumed at: every push is then by a strictly
            # higher rank than the claim it suspends, which bounds the stack.
            if claim.survival != bool(survival):
                changes["survival"] = bool(survival)
            if non_discardable and not claim.non_discardable:
                if rank is None or rung is None:
                    promoted_rung = rung_of(
                        declared_owner, None, non_discardable=True
                    )
                    rank = promoted_rung.rank if rank is None else rank
                    rung = promoted_rung.name if rung is None else rung
                changes["non_discardable"] = True
                changes["rank"] = rank
                changes["rung"] = rung
            if perceived_turn is not None:
                changes["last_perceived_turn"] = int(perceived_turn)
            if changes:
                claim = replace(claim, **changes)
                self._claim = claim
            return claim
        self._claim = Claim(
            claim_id=self.allocate(),
            owner=declared_owner,
            goal=goal,
            state=ClaimState.ACTIVE,
            non_discardable=non_discardable,
            opened_sequence=opened_sequence,
            floor=None if floor is None else tuple(floor),
            survival=bool(survival),
            opened_turn=None if opened_turn is None else int(opened_turn),
            rank=rank,
            rung=rung,
            trigger_monsters=tuple(
                (int(index), int(race)) for index, race in trigger_monsters
            ),
            last_perceived_turn=(
                None if perceived_turn is None else int(perceived_turn)
            ),
        )
        return self._claim

    # -- the suspended stack (design rev 10.1 items 5-6) -----------------

    @property
    def suspended(self) -> tuple[Claim, ...]:
        """The suspended claims, the most recently suspended last."""
        return tuple(getattr(self, "_suspended", None) or ())

    def resume(
        self,
        claim_id: int,
        *,
        sequence: int | None = None,
        turn: int | None = None,
        rank: int | None = None,
        rung: str | None = None,
        perceived_turn: int | None = None,
    ) -> Claim | None:
        """The owner came back to a suspended claim: it continues, same id.

        The decisions and game turns it spent suspended are added to its
        ``suspended_decisions`` / ``suspended_turns``, so that its ``within``
        does not count them (item 6).
        """
        stack = list(self.suspended)
        for position in range(len(stack) - 1, -1, -1):
            claim = stack[position]
            if claim.claim_id != claim_id:
                continue
            del stack[position]
            self._suspended = stack
            decisions = claim.suspended_decisions or 0
            turns = claim.suspended_turns or 0
            if sequence is not None and claim.suspended_sequence is not None:
                decisions += max(0, int(sequence) - int(claim.suspended_sequence))
            if turn is not None and claim.suspended_turn is not None:
                turns += max(0, int(turn) - int(claim.suspended_turn))
            changes: dict = {
                "state": ClaimState.ACTIVE,
                "closed": None,
                "closed_reason": None,
                "suspended_sequence": None,
                "suspended_turn": None,
                "suspended_decisions": decisions,
                "suspended_turns": turns,
            }
            if rank is not None:
                changes["rank"] = rank
            if rung is not None:
                changes["rung"] = rung
            if perceived_turn is not None:
                changes["last_perceived_turn"] = int(perceived_turn)
            self._claim = replace(claim, **changes)
            return self._claim
        return None

    def close_suspended(self, claim_id: int, closed: str, label: str | None = None) -> None:
        """A suspended claim ends while suspended (item 6, rules i-iii).

        ``closed`` is ``complete`` or ``release``.
        """
        stack = list(self.suspended)
        for position, claim in enumerate(stack):
            if claim.claim_id != claim_id:
                continue
            del stack[position]
            self._suspended = stack
            ended = self._execution_ending(
                replace(claim, closed=closed, closed_reason=label), closed, label
            )
            self._note_ended(ended)
            return

    def stamp_suspended_floor(
        self, claim_id: int, floor: tuple[int, ...]
    ) -> None:
        """Give a suspended claim with no recorded floor the board's floor.

        Round 3: a claim restored from a checkpoint pickled before ``floor``
        existed reads ``None``; stamped with the first board that sees it
        suspended, it expires on the first floor change after that.
        """
        stack = list(self.suspended)
        for position, claim in enumerate(stack):
            if claim.claim_id == claim_id and claim.floor is None:
                stack[position] = replace(claim, floor=tuple(floor))
                self._suspended = stack
                return

    # -- transitions -----------------------------------------------------

    def _transition(self, state: ClaimState, closed: str | None) -> Claim | None:
        claim = self._claim
        if claim is None:
            return None
        self._claim = replace(claim, state=state, closed=closed)
        return self._claim

    def await_observation(self) -> Claim | None:
        """The claim emitted no command and is waiting for its observation."""
        return self._transition(ClaimState.AWAITING, self._closed())

    def keep_active(self) -> Claim | None:
        return self._transition(ClaimState.ACTIVE, self._closed())

    def _close(
        self, state: ClaimState, closed: str | None, label: str | None
    ) -> Claim | None:
        claim = self._claim
        if claim is None:
            return None
        self._claim = self._execution_ending(
            replace(claim, state=state, closed=closed, closed_reason=label),
            closed, label,
        )
        return self._claim

    def suspend(
        self,
        label: str | None = None,
        *,
        sequence: int | None = None,
        turn: int | None = None,
    ) -> Claim | None:
        """Preempted with its goal intact (design 3.2).

        ``closed`` stays ``None``: a suspension is not an end.  From S2b.1
        (design rev 10.1 item 5) the suspended claim is also pushed onto the
        suspended stack with the decision sequence and game turn it was
        suspended at, so that ``resume`` can bring it back under its id.
        """
        claim = self._claim
        if claim is None:
            return None
        self._claim = replace(
            claim,
            suspended_sequence=None if sequence is None else int(sequence),
            suspended_turn=None if turn is None else int(turn),
        )
        suspended = self._close(ClaimState.SUSPENDED, self._closed(), label)
        stack = list(self.suspended)
        stack.append(suspended)
        self._suspended = stack
        return suspended

    def complete(self, label: str | None = None) -> Claim | None:
        """The declared goal was observed reached."""
        return self._note_ended(
            self._close(ClaimState.COMPLETE, CLOSED_BY_COMPLETE, label)
        )

    def retire(self) -> Claim | None:
        """Out of budget: the claim emits nothing further (design 3.3)."""
        claim = self._transition(ClaimState.RETIRED, CLOSED_BY_RETIRED)
        if claim is not None:
            self._claim = self._execution_ending(
                claim, CLOSED_BY_RETIRED, "retired"
            )
        return self._note_ended(
            self._claim
        )

    def release(self, label: str | None = None) -> Claim | None:
        """The holder handed the decision back of its own accord."""
        claim = self._claim
        if claim is None:
            return None
        return self._note_ended(
            self._close(claim.state, CLOSED_BY_RELEASE, label)
        )

    def expire(self, label: str | None = None) -> Claim | None:
        """An Observe claim outlived its ``within`` (rev 9.2)."""
        claim = self._claim
        if claim is None:
            return None
        return self._note_ended(
            self._close(claim.state, CLOSED_BY_EXPIRED, label)
        )

    # -- S2b.2: endings and the bar table ----------------------------------

    def _note_ended(self, claim: Claim | None) -> Claim | None:
        """Keep a claim a closing call ended for ``take_ended``; pass it on."""
        if claim is not None and claim.closed in CLOSING_EVENTS:
            self._ended = [*(getattr(self, "_ended", None) or ()), claim]
        return claim

    def take_ended(self) -> list[Claim]:
        """Every claim a closing call ended since the last call, once."""
        ended = list(getattr(self, "_ended", None) or ())
        self._ended = []
        return ended

    @property
    def bars(self) -> tuple[Bar, ...]:
        """The bar table (design 3.2 / 3.3), oldest first."""
        return tuple(getattr(self, "_bars", None) or ())

    def set_bar(self, bar: Bar) -> Bar:
        """Record a bar; a bar already standing on its owner and goal keeps
        its start and takes the union of the two trigger sets and the later
        perception."""
        bars = list(self.bars)
        for position, standing in enumerate(bars):
            if standing.owner == bar.owner and standing.goal == bar.goal:
                perceived = [
                    turn
                    for turn in (standing.last_perceived_turn, bar.last_perceived_turn)
                    if turn is not None
                ]
                merged = replace(
                    standing,
                    triggers=tuple(sorted({*standing.triggers, *bar.triggers})),
                    last_perceived_turn=max(perceived) if perceived else None,
                )
                bars[position] = merged
                self._bars = bars
                return merged
        bars.append(bar)
        self._bars = bars
        return bar

    def replace_bars(self, bars) -> None:
        """The table after a board's lift pass (rebound, never mutated)."""
        self._bars = list(bars)

    def _closed(self) -> str | None:
        claim = self._claim
        return None if claim is None else claim.closed


# --- Goal typing (formerly claim_goal_typing) -------------------------------
# One owner family can hold several kinds of work, so the unit of the table is
# the reason prefix of the family: ``goal_typing`` resolves a reason to the
# longest matching prefix of its own family.  ``claim_goal`` reads it:
# ``Reach`` needs the producer's target in the decision's goal slot,
# ``Observe`` the expectation it posted (or the row's own content),
# ``Terminal`` owns exactly the decision that emits it.

WALK_TARGET = "walk-target"        # Reach: the cell the producer walks to
ENTRANCE = "entrance"              # Reach: the entrance cell of a building
TRANSACTION = "transaction"        # Observe: a transaction's expected change
STORE_OPERATION = "store-operation"  # Observe: a posted store/Home effect
STORE_ENTRY = "store-entry"          # Observe: an entrance command awaiting a page
KNOWLEDGE = "knowledge"              # Observe: Home catalogue becomes current
FLOOR_CHANGE = "floor-change"      # Observe: the floor key changes
EFFECT = "effect"                  # Terminal: the effect label

OBSERVE_WITHIN = {
    TRANSACTION: OWNER_EXPECTATION_MAX_TURNS,
    STORE_OPERATION: STORE_STUCK_LIMIT,
    STORE_ENTRY: STORE_STUCK_LIMIT,
    KNOWLEDGE: STORE_STUCK_LIMIT,
    FLOOR_CHANGE: RECALL_ACTIVATION_MAX_GAME_TURNS,
}
# The observable a floor-change goal names (an ``OwnerProgressCore`` field).
FLOOR_EXPECTATION = ("floor",)


@dataclass(frozen=True)
class GoalTypingRow:
    family: str
    prefix: str
    kind: str
    content: str


def _rows(family: str, *entries: tuple[str, str, str]) -> tuple[GoalTypingRow, ...]:
    return tuple(
        GoalTypingRow(family, prefix, kind, content)
        for prefix, kind, content in entries
    )


R, O, T = GOAL_REACH, GOAL_OBSERVE, GOAL_TERMINAL

GOAL_TYPING: tuple[GoalTypingRow, ...] = (
    *_rows(
        "home-errand",
        ("home-errand:", O, STORE_OPERATION),
        ("home-errand:request-knowledge:", O, KNOWLEDGE),
        ("home-errand:await-fresh-knowledge:", O, KNOWLEDGE),
        ("home-errand:stopped:", T, EFFECT),
        ("home-errand:filed:", T, EFFECT),
    ),
    *_rows(
        "home-scan",
        ("home:request-knowledge", O, KNOWLEDGE),
        ("home:scan", O, KNOWLEDGE),
        ("home:scan-complete-from-open-page", T, EFFECT),
        ("home:scan-incomplete-open-page", T, EFFECT),
        ("home:seek-", T, EFFECT),
        ("home:scan-step-off", R, ENTRANCE),
        ("home:seek-quest-launcher-page", T, EFFECT),
    ),
    *_rows(
        "home-visit",
        ("home:", T, EFFECT),
        ("home:atomic-withdraw", O, STORE_OPERATION),
        ("home:atomic-withdraw-await-confirmation", O, STORE_OPERATION),
        ("home:atomic-withdraw-pending-hold", O, STORE_OPERATION),
        ("home:atomic-withdraw-page-probe", T, EFFECT),
        ("home:atomic-deposit", O, STORE_OPERATION),
        ("home:weight-overload-deposit", O, STORE_OPERATION),
        ("home:deposit", O, STORE_OPERATION),
        ("home:morivant-temporary-deposit", O, STORE_OPERATION),
        ("home:morivant-retry-temporary-deposit", O, STORE_OPERATION),
        ("home:morivant-restore-temporary-deposit", O, STORE_OPERATION),
        ("home:morivant-", T, EFFECT),
        ("home:withdraw-identify-staff-reserve", O, STORE_OPERATION),
        ("home:withdraw-surplus-identify-staff", O, STORE_OPERATION),
        ("home:defer-capacity", T, EFFECT),
        ("home:process-next-batch-item", T, EFFECT),
        ("home:route-claim-unfulfilled", T, EFFECT),
        ("home:withdraw-failed-deferred", T, EFFECT),
        ("home:atomic-withdraw-complete", T, EFFECT),
        ("home:atomic-withdraw-failed", T, EFFECT),
        ("home:atomic-withdraw-target-unobserved", T, EFFECT),
        ("home:atomic-withdraw-slot-unobserved", T, EFFECT),
        ("home:atomic-withdraw-address-invalid", T, EFFECT),
        ("home:deposit-rejected", T, EFFECT),
        ("home:deposit-unobserved-rescan", T, EFFECT),
        ("home:queue-", T, EFFECT),
        ("home:await-fresh-knowledge", T, EFFECT),
        ("home:await-page-size", T, EFFECT),
        ("home:leave-", T, EFFECT),
        ("home:store-context-exit", T, EFFECT),
        ("home:identify-staff-reserve-", T, EFFECT),
        ("home:no-", T, EFFECT),
        ("home:need-", T, EFFECT),
        ("home:processing-complete", T, EFFECT),
        ("home:full-space-ready", T, EFFECT),
        ("home:full-leave-with-surplus", T, EFFECT),
        ("home:full-leave-for-identification-effect", T, EFFECT),
        ("home:full-queue-surplus-withdraw", T, EFFECT),
        ("home:full-deposit-deferred-no-legal-relief", T, EFFECT),
        ("home:full-destroy-", O, EFFECT),
        ("home:junk-sweep:", O, EFFECT),
        ("home:junk-sweep-withdraw", T, EFFECT),
        ("home-visit:", T, EFFECT),
        ("home-disposal:", O, STORE_OPERATION),
        ("home-disposal:destroy-refused", T, EFFECT),
    ),
    *_rows(
        "shop-sell",
        ("shop:outpost-fare-earned-leave", T, EFFECT),
        ("shop:outpost-fare-seek-sale-leave", T, EFFECT),
        ("shop:outpost-fare-sale-approach", R, ENTRANCE),
        ("shop:outpost-fare-sale-approach:await-entry", O, STORE_ENTRY),
        ("shop:sale", T, EFFECT),
        ("shop:sell-", T, EFFECT),
        ("shop:batch-sale", T, EFFECT),
        ("shop:batch-sell", O, STORE_OPERATION),
        ("shop:batch-inscribe", T, EFFECT),
        ("shop:one-shot-sale", O, STORE_OPERATION),
        ("shop:one-shot-sell", O, STORE_OPERATION),
        # SOL-DESIGN-store-reentry-20261003 3.2: one Observe goal per
        # in-store operation, as the one-shot it replaces.
        ("shop:in-store-sell", O, STORE_OPERATION),
        ("shop:in-store-inscribe", O, STORE_OPERATION),
        ("shop:unsellable-", T, EFFECT),
        ("shop:defective-target-leave", T, EFFECT),
        ("shop:leave", O, STORE_OPERATION),
        ("shop:stuck-leave", T, EFFECT),
        ("shop:invalid", T, EFFECT),
        ("shop:retain-standing-digging-tool", T, EFFECT),
        ("town:overweight-surplus-", O, EFFECT),
        ("town:overweight-surplus-sold:", O, STORE_OPERATION),
        ("town:overweight-surplus-destroyed:", O, EFFECT),
        ("town:overweight-surplus-await-effect", O, EFFECT),
        ("town:destroy-overflow", T, EFFECT),
        ("equipment:sale", T, EFFECT),
    ),
    *_rows(
        "shop-buy",
        ("shop:one-shot-buy", O, STORE_OPERATION),
        ("shop:in-store-buy", O, STORE_OPERATION),
        # The in-store entry's own exit: emits the leave key inside the store.
        ("shop:in-store-done", T, EFFECT),
        ("shop:one-shot-in-flight", O, STORE_OPERATION),
        ("shop:one-shot-page-not-zero", T, EFFECT),
        ("shop:opening-route-page", T, EFFECT),
        ("shop:buy", O, STORE_OPERATION),
        ("shop:purchase-deferred", T, EFFECT),
        ("shop:await-", O, STORE_OPERATION),
        ("shop:observe", T, EFFECT),
        # Rev 9.2 (T2): ``shop:observe-and-leave`` emits the leave key inside
        # the store and never walks; rev 9 had listed it with the travel rows.
        ("shop:observe-and-leave", T, EFFECT),
        ("shop:home-first-before-purchase", T, EFFECT),
        ("shop:store-context-exit", O, STORE_OPERATION),
        ("town:wait-restock", T, EFFECT),
    ),
    *_rows(
        "store-router",
        ("shop:approach", R, ENTRANCE),
        ("shop:approach:await-entry", O, STORE_ENTRY),
        ("shop:travel", R, ENTRANCE),
        ("shop:travel:await-entry", O, STORE_ENTRY),
        ("store:", T, EFFECT),
        ("store:entry-await-observation", O, STORE_ENTRY),
        ("store:entry-failed-step-off", R, ENTRANCE),
        ("store:entry-interrupted-replan", R, ENTRANCE),
        ("town:travel", R, ENTRANCE),
        ("town-travel:", R, ENTRANCE),
        # The walk to the teleport building (its route's goal cell).
        ("town:teleport", R, ENTRANCE),
        ("town:teleport-refused-fare", T, EFFECT),
        # One step off the teleport building; the step is computed inside the
        # route helper, which no producer can name without recomputing it.
        ("town:teleport-step-off", T, EFFECT),
        ("store:entry-interrupted-replan:await-entry", O, STORE_ENTRY),
        ("wilderness:enter-town", T, EFFECT),
        ("wilderness:global-travel", R, WALK_TARGET),
        ("wilderness:enter-global", T, EFFECT),
    ),
    *_rows(
        "equipment-opt",
        ("equipment-optimization:", O, TRANSACTION),
        ("equipment:opt", O, TRANSACTION),
        ("optimizer:", O, TRANSACTION),
    ),
    *_rows(
        "equipment-txn",
        ("home:atomic-withdraw", O, STORE_OPERATION),
        ("home:atomic-deposit", O, STORE_OPERATION),
        ("home:leave-after-one-operation", O, STORE_OPERATION),
        ("home:atomic-withdraw-target-unobserved", T, EFFECT),
        ("equipment-transaction:", O, TRANSACTION),
        ("equipment-transaction:approach-home", R, ENTRANCE),
        ("equipment-transaction:travel-home", R, ENTRANCE),
        ("equipment-transaction:travel-home:await-entry", O, STORE_ENTRY),
        # Rev 9.2 (T2): it walks to the Home through the store router.
        ("equipment-transaction:acquire-home-catalog", R, ENTRANCE),
        ("equipment-transaction:home-route-unavailable", T, EFFECT),
        ("equipment-transaction:abandon", T, EFFECT),
        ("equipment-transaction:confirmation-stall-bound", T, EFFECT),
        ("equipment-transaction:retain-", T, EFFECT),
        ("equipment-transaction:defer-identification", T, EFFECT),
        ("equipment-transaction:stale-identity-invalidated:", T, EFFECT),
        ("equipment-transaction:deposit-missing", T, EFFECT),
        ("equipment-transaction:withdraw-missing", T, EFFECT),
        ("equipment-mutation:", T, EFFECT),
        ("equipment:", O, TRANSACTION),
        ("equipment:destroy-", T, EFFECT),
        ("town:restore-combat-weapon", O, TRANSACTION),
        ("town:remove-no-teleport-weapon", O, TRANSACTION),
        ("wield-light", T, EFFECT),
        ("opening-q1:equip-light", O, TRANSACTION),
        ("town:replace-no-teleport-weapon", O, TRANSACTION),
    ),
    *_rows(
        "identification",
        ("identify:", T, EFFECT),
        ("identification:", O, STORE_OPERATION),
        ("item-processing:", T, EFFECT),
        ("inventory:", T, EFFECT),
    ),
    *_rows(
        "fundraising",
        ("fundraise:", T, EFFECT),
        ("fundraise:dig-to-treasure", R, WALK_TARGET),
        ("fundraise:seek-treasure", R, WALK_TARGET),
        ("fundraise:seek-loot", R, WALK_TARGET),
        ("fundraise:seek-upstairs", R, WALK_TARGET),
        ("fundraise:sweep-explore", R, WALK_TARGET),
        ("fundraise:recall", O, FLOOR_CHANGE),
        ("fundraise:recall-stuck", T, EFFECT),
        ("fundraise:wait-recall", O, FLOOR_CHANGE),
        ("fundraise:ascend", O, FLOOR_CHANGE),
        ("fundraising:", T, EFFECT),
        ("mining:", T, EFFECT),
        ("town:recall-stockout-mining", T, EFFECT),
        ("town:identify-staff-stockout-mining", T, EFFECT),
    ),
    *_rows(
        "curse-enchant",
        ("town:remove-curse", T, EFFECT),
        ("town:enchant-launcher-", T, EFFECT),
        ("curse:", O, STORE_OPERATION),
        ("remove-curse:", O, STORE_OPERATION),
        ("enchant:", O, STORE_OPERATION),
    ),
    *_rows(
        "cross-town",
        ("town:cross-town", R, ENTRANCE),
        ("town:cross-town-shopping-needs-funds", T, EFFECT),
        ("town:morivant", R, ENTRANCE),
    ),
    *_rows(
        "survival",
        ("survival:", T, EFFECT),
        ("survival:mana-home-scan", O, KNOWLEDGE),
        ("survival:mana-home-await-operation", O, STORE_OPERATION),
        ("survival:mana-home-withdraw", O, STORE_OPERATION),
        ("survival:mana-home-approach", R, ENTRANCE),
        ("survival:mana-sale-approach", R, ENTRANCE),
        ("survival:mana-shop-approach", R, ENTRANCE),
        ("survival:shop-approach", R, ENTRANCE),
        # Rev 9.2 (T2): the survival errands' native-travel legs.
        ("survival:shop-travel", R, ENTRANCE),
        ("survival:mana-home-travel", R, ENTRANCE),
        ("survival:mana-sale-travel", R, ENTRANCE),
        ("survival:mana-shop-travel", R, ENTRANCE),
        ("survival:shop-travel:await-entry", O, STORE_ENTRY),
        ("survival:mana-home-travel:await-entry", O, STORE_ENTRY),
        ("survival:mana-sale-travel:await-entry", O, STORE_ENTRY),
        ("survival:mana-shop-travel:await-entry", O, STORE_ENTRY),
        ("survival:seek-exit", R, WALK_TARGET),
        ("weak-fainting", T, EFFECT),
        ("status-threat:", T, EFFECT),
        ("status-threat:retreat", R, WALK_TARGET),
        ("status-threat:stairs", O, FLOOR_CHANGE),
        ("town:kill-mob", R, WALK_TARGET),
        ("town:kill-mob-friendly", T, EFFECT),
        ("town:eat-before-travel", T, EFFECT),
        ("town:recover", T, EFFECT),
        ("town:seek-shelter", R, WALK_TARGET),
        ("confused:", T, EFFECT),
        ("item:", T, EFFECT),
        ("mana-food:", T, EFFECT),
        ("mana-food:seek-", R, WALK_TARGET),
        ("stat-gain:", T, EFFECT),
        ("experience:", T, EFFECT),
        ("wilderness:escape-scroll", T, EFFECT),
        ("wilderness:flee", T, EFFECT),
        # Loop 6 (owner 2026-10-31): a refused global map reads Recall and waits.
        ("wilderness:recall", O, FLOOR_CHANGE),
        ("wilderness:wait-recall", O, FLOOR_CHANGE),
        # Slice 1 (2026-10-06): the no-wait escapes are survival interrupts.
        ("no-wait:escape-scroll", T, EFFECT),
        ("no-wait:flee", T, EFFECT),
        ("refill-light", T, EFFECT),
        ("restore-lantern", T, EFFECT),
        ("eat", T, EFFECT),
        ("rest", T, EFFECT),
    ),
    *_rows(
        "departure",
        ("depart", T, EFFECT),
        ("descend", O, FLOOR_CHANGE),
        ("town:ascend", O, FLOOR_CHANGE),
        ("town:descend", O, FLOOR_CHANGE),
        ("recall", O, FLOOR_CHANGE),
        ("return:", T, EFFECT),
        ("return:recall", O, FLOOR_CHANGE),
        ("return:wait-recall", O, FLOOR_CHANGE),
        ("return:await-recall-confirmation", O, FLOOR_CHANGE),
        ("return:ascend", O, FLOOR_CHANGE),
        ("return:seek-upstairs", R, WALK_TARGET),
        # every producer of it emits the search key in place
        ("return:search-upstairs", T, EFFECT),
        ("return:seek-secret-wall", R, WALK_TARGET),
        ("return:explore", R, WALK_TARGET),
        ("return:seek-loot", R, WALK_TARGET),
        ("stair:", O, FLOOR_CHANGE),
        ("stair:observation-timeout-probe", T, EFFECT),
        ("postlevel:", T, EFFECT),
        ("repetition-depart", T, EFFECT),
        ("town:repetition-depart", T, EFFECT),
        ("town:repetition-depart:enter", O, FLOOR_CHANGE),
        ("town:repetition-depart:recall", O, FLOOR_CHANGE),
        ("town:entrance", T, EFFECT),
        ("town:entrance-step-off:", R, WALK_TARGET),
        ("town:wait-recall", O, FLOOR_CHANGE),
        ("town:wait-recall-step-off", R, WALK_TARGET),
        ("town:await-recall-confirmation", O, FLOOR_CHANGE),
        ("town:recall-to-", O, FLOOR_CHANGE),
        ("town:cancel-", T, EFFECT),
        ("town:unsafe-recall-fallback", T, EFFECT),
        ("wilderness:no-safe-route", T, EFFECT),
        ("esp-threat:leave-", O, FLOOR_CHANGE),
        ("seek-downstairs", R, WALK_TARGET),
        ("approach-descent", R, WALK_TARGET),
        ("clear-descent", R, WALK_TARGET),
    ),
    *_rows(
        "town-plan",
        ("town:blocked", T, EFFECT),
        ("town:procurement", T, EFFECT),
        ("procurement:", T, EFFECT),
        ("town-plan:", T, EFFECT),
        ("quest:readiness", T, EFFECT),
        ("town:repetition-required-shopping", T, EFFECT),
    ),
    *_rows(
        "rumor",
        ("town:rumor", R, ENTRANCE),
        ("town:rumor-batch", T, EFFECT),
        ("town:rumor-needs-funds", T, EFFECT),
        ("town:rumor-wait-supplies", T, EFFECT),
    ),
    *_rows(
        "quest-request",
        ("fixedquest:", T, EFFECT),
        ("fixedquest:q2-teleport", R, ENTRANCE),
        ("fixedquest:q2-teleport-step-off", T, EFFECT),
        ("fixedquest:q2-travel", R, ENTRANCE),
        ("fixedquest:q2-travel-needs-funds", T, EFFECT),
        ("fixedquest:approach", R, ENTRANCE),
        ("fixedquest:reward-approach", R, ENTRANCE),
        ("fixedquest:reward-approach:route-unavailable", T, EFFECT),
        ("fixedquest:claim:approach", R, ENTRANCE),
        ("fixedquest:claim:approach:route-unavailable", T, EFFECT),
        ("fixedquest:claim:approach:unsatisfiable", T, EFFECT),
        ("fixedquest:request:approach", R, ENTRANCE),
        ("fixedquest:request:approach:route-unavailable", T, EFFECT),
        ("fixedquest:request:approach:unsatisfiable", T, EFFECT),
        ("fixedquest:q22-travel", R, ENTRANCE),
        ("fixedquest:q22-travel:route-unavailable", T, EFFECT),
        ("fixedquest:q22-travel:unsatisfiable", T, EFFECT),
        ("fixedquest:prepare-return", R, WALK_TARGET),
        ("fixedquest:prepare-return:route-unavailable", T, EFFECT),
        ("fixedquest:prepare-return:unsatisfiable", T, EFFECT),
        ("fixedquest:seek-exit", R, WALK_TARGET),
        ("fixedquest:enter", O, FLOOR_CHANGE),
        ("fixedquest:exit", O, FLOOR_CHANGE),
        ("quest:", T, EFFECT),
        ("quest:enter:approach", R, ENTRANCE),
        ("quest:enter:approach:route-unavailable", T, EFFECT),
        ("quest:enter:approach:unsatisfiable", T, EFFECT),
        ("quest:regen:ascend", O, FLOOR_CHANGE),
        ("quest:regen:descend", O, FLOOR_CHANGE),
        ("opening-q34:", T, EFFECT),
        ("me-staff:", T, EFFECT),
        # The Tower trips' walks (me_staff_sequence / q2_tower_recharge
        # ``_travel`` through _town_teleport_key, and the Tower approach
        # through morivant_tower.building_step) declare their cell like
        # ``fixedquest:q2-teleport``; Terminal left every step uncounted as
        # progress (D49 n1-c life-067/068: owner-retired-burst two steps into
        # the walk to the inn, loop-detected 15 steps into the Tower walk).
        ("me-staff:travel-morivant", R, ENTRANCE),
        ("me-staff:travel-morivant-step-off", T, EFFECT),
        ("me-staff:return-to-shop", R, ENTRANCE),
        ("me-staff:return-to-shop-step-off", T, EFFECT),
        ("me-staff:search-staff", R, ENTRANCE),
        ("me-staff:search-staff-step-off", T, EFFECT),
        ("me-staff:return-for-funds", R, ENTRANCE),
        ("me-staff:return-for-funds-step-off", T, EFFECT),
        ("me-staff:return-outpost", R, ENTRANCE),
        ("me-staff:return-outpost-step-off", T, EFFECT),
        ("me-staff:approach-tower", R, ENTRANCE),
        ("fixedquest:q2-recharge:travel-morivant", R, ENTRANCE),
        ("fixedquest:q2-recharge:travel-morivant-step-off", T, EFFECT),
        ("fixedquest:q2-recharge:travel-telmora", R, ENTRANCE),
        ("fixedquest:q2-recharge:travel-telmora-step-off", T, EFFECT),
        ("fixedquest:q2-recharge:return-for-funds", R, ENTRANCE),
        ("fixedquest:q2-recharge:return-for-funds-step-off", T, EFFECT),
        ("fixedquest:q2-recharge:approach-tower", R, ENTRANCE),
        ("magic-eater:absorb", O, EFFECT),
        ("bounty:", T, EFFECT),
        ("bounty:cashout", T, EFFECT),
        ("bounty:approach", R, ENTRANCE),
        ("bounty:step-off", R, WALK_TARGET),
        ("bounty:leave", T, EFFECT),
    ),
    *_rows(
        "detectors",
        ("ownership:", T, EFFECT),
        ("livelock:", T, EFFECT),
        ("livelock:ascend", O, FLOOR_CHANGE),
        ("livelock:recall-escape", O, FLOOR_CHANGE),
        ("livelock:seek-", R, WALK_TARGET),
        # S2b.1b: a one-shot rewrite, not a walk.  It rebuilds the explore
        # path toward a window edge, records it as the *explore* goal and
        # clears ``_nav_exhausted``, so the next decision is ordinary
        # ``explore`` on that goal; typed Reach, its one-row claim was
        # dropped by explore on every firing (never two rows in a row in
        # any recorded ledger).
        ("livelock:seek-window-edge", T, EFFECT),
        ("town-progress-invariant:", T, EFFECT),
        ("town-liveness-invariant:", T, EFFECT),
        ("town:cycle-break", T, EFFECT),
        ("posting-contract:", T, EFFECT),
        ("stuck:", T, EFFECT),
        ("stuck:ascend", O, FLOOR_CHANGE),
        ("stuck:recall-escape", O, FLOOR_CHANGE),
        ("stuck:seek-stairs", R, WALK_TARGET),
        ("novel:", T, EFFECT),
        ("breakout", T, EFFECT),
        # S2b.1b: a one-shot rewrite, not a walk.  The oscillation branch of
        # ``_decide`` resumes the committed explore planner for one step and
        # clears ``_recent``, so the next decision is ordinary ``explore`` on
        # the same goal; typed Reach, its one-row claim was dropped by explore
        # on every firing (77 rows in the recorded ledgers, never two in a
        # row).
        ("breakout:seek-frontier", T, EFFECT),
        # a tunnel command toward a stair the reason site cannot name
        ("breakout:dig-to-stairs", T, EFFECT),
        ("no-wait:", T, EFFECT),
        ("nav:", T, EFFECT),
        ("warning:", T, EFFECT),
        ("dark:", R, WALK_TARGET),
        ("dark:locomotion-exhausted", T, EFFECT),
        ("dark:no-recovery:", T, EFFECT),
        ("dark:probe", T, EFFECT),
    ),
    *_rows(
        "positioning",
        ("detected:", R, WALK_TARGET),
        ("detected:hold-choke", T, EFFECT),
        ("melee:choke", T, EFFECT),
        ("melee:choke-reposition", R, WALK_TARGET),
        ("summoner:hold-choke", T, EFFECT),
        ("summoner:hold-reposition", R, WALK_TARGET),
        ("threat:reposition", R, WALK_TARGET),
        ("threat:avoid-engagement", R, WALK_TARGET),
        ("threat:paralyzer-avoid", R, WALK_TARGET),
        ("threat:paralyzer-avoid:blocked-step", T, EFFECT),
        ("paralyzer-guard:", R, WALK_TARGET),
    ),
    *_rows(
        "esp-threat",
        ("esp-threat:hunt-", R, WALK_TARGET),
        ("esp-threat:hunt-heal", T, EFFECT),
        ("esp-threat:hunt-speed", T, EFFECT),
        ("melee:esp-threat-hunt", T, EFFECT),
    ),
    *_rows(
        "escape",
        ("emergency:", T, EFFECT),
        ("emergency:recall", O, FLOOR_CHANGE),
        ("emergency:stairs", O, FLOOR_CHANGE),
        ("emergency:seek-upstairs", R, WALK_TARGET),
        ("flee", T, EFFECT),
        ("flee:stairs", O, FLOOR_CHANGE),
        ("combat:disengage", T, EFFECT),
        ("combat:disengage-recall", O, FLOOR_CHANGE),
        ("combat:disengage-stairs", O, FLOOR_CHANGE),
        ("combat:disengage-seek-upstairs", R, WALK_TARGET),
        ("combat:fruitless", T, EFFECT),
        ("unseen:", T, EFFECT),
        ("unseen-recall:", T, EFFECT),
        ("breeder-breakthrough:", T, EFFECT),
        ("breeder-breakthrough:ascend", O, FLOOR_CHANGE),
        ("breeder-breakthrough:recall", O, FLOOR_CHANGE),
        ("breeder-breakthrough:wait-recall", O, FLOOR_CHANGE),
        ("breeder-breakthrough:seek-", R, WALK_TARGET),
        ("breeder-item-damage:", T, EFFECT),
        ("breeder-item-damage:stairs", O, FLOOR_CHANGE),
        ("breeder-item-damage:teleport-level", O, FLOOR_CHANGE),
        ("breeder-item-damage:recall", O, FLOOR_CHANGE),
        ("breeder-item-damage:seek-stairs", R, WALK_TARGET),
        ("guardian:teleport-to-cover", T, EFFECT),
        ("summoner:retreat", T, EFFECT),
        ("summoner:stairs", O, FLOOR_CHANGE),
        ("summoner:hold-teleport", T, EFFECT),
        ("threat:scroll", T, EFFECT),
        ("threat:wait", T, EFFECT),
    ),
    *_rows(
        "combat",
        ("melee", T, EFFECT),
        ("ranged:", T, EFFECT),
        ("summoner:ranged-kill", T, EFFECT),
        ("summoner:cornered-approach", R, WALK_TARGET),
        ("summoner:seek-upstairs", R, WALK_TARGET),
        ("summoner:seek-downstairs", R, WALK_TARGET),
        ("summoner:teleport-level", O, FLOOR_CHANGE),
        ("summoner:recall", O, FLOOR_CHANGE),
        ("summoner:wait-recall", O, FLOOR_CHANGE),
        ("unique:quaff-", T, EFFECT),
    ),
    *_rows("hunt", ("hunt", R, WALK_TARGET)),
    *_rows(
        "explore",
        ("explore", R, WALK_TARGET),
        ("explore:", T, EFFECT),
        ("search", T, EFFECT),
        ("seek-secret-wall", R, WALK_TARGET),
        ("probe", T, EFFECT),
    ),
    *_rows(
        "floor-loot",
        ("seek-loot", R, WALK_TARGET),
        ("loot:", T, EFFECT),
        ("loot:seek-", R, WALK_TARGET),
        ("chest:", T, EFFECT),
        ("chest:approach", R, WALK_TARGET),
        ("chest:return-reserved-position", R, WALK_TARGET),
        ("chest:step-off", R, WALK_TARGET),
        ("victory:", R, WALK_TARGET),
        ("conquest:", R, WALK_TARGET),
        # S2b.1 round 2 (F5): picking up underfoot and the auto-destroy
        # trigger each own exactly the decision that emits them.
        ("pickup", T, EFFECT),
        ("trigger-autodestroy", T, EFFECT),
    ),
    *_rows(
        "quest-sweep",
        ("quest-strategy:", T, EFFECT),
        ("quest-strategy:approach-", R, WALK_TARGET),
        ("quest-strategy:placement-sweep", R, WALK_TARGET),
        ("quest-strategy:placement-sweep-repeat", T, EFFECT),
        # a route to the nearest of a set of vantages the navigator does not
        # name (rev 9.3: the target is not obtainable without a second route)
        ("quest-strategy:q2-approach-", T, EFFECT),
        ("quest-strategy:q2-blue-confirm-approach", R, WALK_TARGET),
        ("quest-strategy:q2-breach-approach", R, WALK_TARGET),
        ("quest-strategy:q2-final-patrol", R, WALK_TARGET),
        ("quest-strategy:q2-final-patrol-round-complete", T, EFFECT),
    ),
    *_rows(
        "bookkeeping",
        ("periodic:", T, EFFECT),
        ("town:character-dump", T, EFFECT),
    ),
    *_rows(
        "idle",
        ("policy:", T, EFFECT),
        ("wait", T, EFFECT),
    ),
    # ``misc`` keeps its registration (design 6/S2a) but the census answers
    # an earlier family for every prefix except ``town:misc:``; each still
    # needs its row so the table cannot silently lose one.
    *_rows(
        "misc",
        ("policy:", T, EFFECT),
        ("town:misc:", T, EFFECT),
        ("town:character-dump", T, EFFECT),
        ("periodic:", T, EFFECT),
        ("explore", R, WALK_TARGET),
        ("melee", T, EFFECT),
        ("hunt", R, WALK_TARGET),
        ("esp-threat:hunt-", R, WALK_TARGET),
        ("seek-loot", R, WALK_TARGET),
        ("wait", T, EFFECT),
    ),
)
del R, O, T

def owners_with(kind: str, content: str) -> frozenset[str]:
    """The families that have a row of this kind and content (rev 9.2 U)."""
    return frozenset(
        row.family for row in GOAL_TYPING
        if row.kind == kind and row.content == content and row.family != "misc"
    )


# The owners a shared store goal can belong to, derived from the table so the
# closing sites of rev 9.2 item U name owners without a hand-kept list.
ENTRANCE_OWNERS = owners_with(GOAL_REACH, ENTRANCE)
STORE_OPERATION_OWNERS = owners_with(GOAL_OBSERVE, STORE_OPERATION)
# The owners whose walks share one committed target, named by the closing
# sites that drop or reach that target (rev 9.2 U).  Each is the set of
# families whose producers write that target into the slot.
LOOT_OWNERS = frozenset(
    {"floor-loot", "fundraising", "departure"}  # seek-loot, fundraise:, return:
)
EXPLORE_GOAL_OWNERS = frozenset(
    # explore; return:explore; breakout:seek-frontier; the fundraising and
    # quest-sweep exploration legs
    {"explore", "departure", "detectors", "fundraising", "quest-sweep"}
)
MONSTER_CHASE_OWNERS = frozenset(
    {"hunt", "departure", "survival"}  # hunt, clear-descent, town:kill-mob-approach
)
# A confirmed Home withdrawal or deposit completes the Home operation of any
# owner that posts one, under the sources those owners declare it with: the
# store-operation and transaction table contents, and the expectation names
# they post.
HOME_EFFECT_OWNERS = frozenset(
    {"home-visit", "home-errand", "home-scan", "equipment-txn"}
)
# Rev 9.3 (R6): the withdraw and deposit names only -- not ``home:``, which
# also names ``home:store-context-exit`` / ``home:route-claim-unfulfilled``,
# whose leave a late withdraw/deposit confirmation must not complete.
HOME_EFFECT_SOURCES = (
    STORE_OPERATION,
    TRANSACTION,
    "equipment-transaction",
    "home-errand:",
    "home-withdrawal:",
)

# The note ``_town_teleport_key`` writes into the goal slot, which its caller
# may adopt (``_adopt_decision_goal``).
TELEPORT_WALK_NOTE = "teleport-walk"

_GOAL_ROWS_BY_FAMILY: dict[str, tuple[GoalTypingRow, ...]] = {}
for _row in GOAL_TYPING:
    _GOAL_ROWS_BY_FAMILY[_row.family] = (*_GOAL_ROWS_BY_FAMILY.get(_row.family, ()), _row)
del _row


def goal_typing(family: str, reason: str | None) -> GoalTypingRow | None:
    """The row of ``family`` whose prefix is the longest that ``reason`` has.

    ``reason`` is normalised exactly as the arbiter normalises it (an empty
    reason is ``policy:none``), so the census and this table read the same
    string.  ``None`` means the family has no row for the reason.
    """
    normalized = reason or "policy:none"
    best: GoalTypingRow | None = None
    for row in _GOAL_ROWS_BY_FAMILY.get(family, ()):
        if normalized.startswith(row.prefix) and (
            best is None or len(row.prefix) > len(best.prefix)
        ):
            best = row
    return best


# -- survival (design rev 9 item 3) ---------------------------------------

# The emergency ladder's output (P:5558-5562 enters them into EscapeState as
# ``emergency``), the disengage family, the unseen-attacker family and the
# ESP-threat floor exit.
SURVIVAL_REASON_PREFIXES = (
    "emergency:",
    "unseen-recall:",
    "guardian:teleport-to-cover",
    "combat:disengage",
    "unseen:",
    "esp-threat:leave-",
    "town:seek-shelter",
    "town:recover",
)
# A ``return:`` decision is survival only while the trigger that started the
# return is a danger trigger (policy_combat.py ``_last_return_trigger``).
SURVIVAL_RETURN_PREFIX = "return:"
# Rev 9.3: ``guardian-reposition`` is not in it -- a guardian reposition never
# starts a return (policy_combat.py sets ``_returning_to_town`` only when not
# repositioning), so it can never be the trigger a return began with.
SURVIVAL_RETURN_TRIGGERS = frozenset({"esp-threat", "unseen-attacker"})
SURVIVAL_RETURN_TRIGGER_PREFIX = "emergency-"
def is_survival_return_trigger(trigger: str | None) -> bool:
    return bool(trigger) and (
        trigger in SURVIVAL_RETURN_TRIGGERS
        or trigger.startswith(SURVIVAL_RETURN_TRIGGER_PREFIX)
    )


def is_survival(reason: str | None, return_trigger: str | None = None) -> bool:
    """Whether a decision is survival in the sense of design rev 9 item 3."""
    reason = reason or ""
    if reason.startswith(SURVIVAL_REASON_PREFIXES):
        return True
    return reason.startswith(SURVIVAL_RETURN_PREFIX) and is_survival_return_trigger(
        return_trigger
    )



# --- The town hold's state (structure stage 2 B, slice 3) -------------------
# Everything of the former claim recording that a later decision still reads:
# the standing claim, the suspended stack and the bars (the claim register),
# the executor delegations, and the current decision's producer offers.  The
# policy keeps one ``TownHold`` in ``_town_hold``; every other module reaches
# it through the functions below and never through policy attributes.

@dataclass
class ExecutionDelegation:
    """Recorded, explicitly opened executor work; never inferred at a hold."""

    parent_claim_id: int | None
    parent_family: str
    delegate_family: str
    work_identity: tuple
    purpose_identity: tuple
    opening_decision: int
    expected_effect: str
    budget_reference: str
    lifecycle: str = "reserved"
    ending: str | None = None
    execution: object = None


@dataclass
class DecisionOffers:
    """Transient producer proposals, consumed only by the claim exit."""

    steps: list = field(default_factory=list)
    no_steps: list = field(default_factory=list)
    waits: list = field(default_factory=list)
    admitted_commands: dict = field(default_factory=dict)
    sequence: int = 0

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence


class _OfferSlot:
    """The current decision's offers; shared by a hold and its observer copy."""

    __slots__ = ("buffer",)

    def __init__(self) -> None:
        self.buffer: DecisionOffers | None = None


class TownHold:
    """The town hold's live state.

    ``claims`` is the claim register (``None`` only when a caller switched
    the recording off).  ``delegations`` are the executor delegations.  The
    offers belong to one decision and to this process: they are never pickled
    or deep-copied (a restored or copied policy starts without offers), and a
    telemetry observer copy shares them, as the decision it observes does.

    ``last_reason``, ``last_reach`` and ``last_rung`` are what the latest
    ``advance_hold`` saw (all None when the register is off): the decision's
    reason (the next decision's seek-shelter release reads it), the Reach
    progress of its claim, ``(claim_id, distance)`` (the driver's town fuse),
    and the rung it ranked at (the decision log).  A hold pickled before
    slice 4 reads the class defaults until ``policy_state`` adopts them.
    """

    last_reason: str | None = None
    last_reach: tuple[int, int] | None = None
    last_rung: str | None = None

    def __init__(self, claims: ClaimRegister | None = None,
                 delegations: list | None = None) -> None:
        self.claims = claims
        self.delegations = delegations if delegations is not None else []
        self._offers = _OfferSlot()

    @classmethod
    def fresh(cls) -> "TownHold":
        return cls(ClaimRegister())

    def __getstate__(self) -> dict:
        state = dict(self.__dict__)
        del state["_offers"]
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._offers = _OfferSlot()

    def observer_copy(self) -> "TownHold":
        """A copy a telemetry observer may write: the register is copied
        shallowly (it rebinds its current claim on every transition), the
        delegation list is a new list, the offers are shared and the latest
        decision's record is the same."""
        duplicate = TownHold(copy(self.claims) if self.claims is not None else None,
                             list(self.delegations))
        duplicate._offers = self._offers
        duplicate.last_reason, duplicate.last_reach, duplicate.last_rung = (
            self.last_reason, self.last_reach, self.last_rung)
        return duplicate


# Checkpoints pickled before structure stage 2 B slice 4 name the claim
# records by their former module (claim_register); they load as these.
retired_module(
    "hengbot.claim_register", Bar=Bar, Claim=Claim, ClaimOwner=ClaimOwner,
    ClaimRegister=ClaimRegister, ClaimState=ClaimState,
    ExecutionDeclaration=ExecutionDeclaration, Goal=Goal,
)


def town_hold(policy: Any) -> TownHold | None:
    return getattr(policy, "_town_hold", None)


def decision_reach(policy: Any) -> tuple[int, int] | None:
    """The latest decision's Reach progress, ``(claim_id, distance)``, or None."""
    return getattr(town_hold(policy), "last_reach", None)


def decision_rung(policy: Any) -> str | None:
    """The rung the latest decision ranked at (for the decision log)."""
    return getattr(town_hold(policy), "last_rung", None)


def hold_claims(policy: Any) -> ClaimRegister | None:
    """The claim register of the town hold: the one place claims change."""
    return getattr(town_hold(policy), "claims", None)


def standing_claim(policy: Any):
    """The standing (current) claim, open or just closed, or None."""
    return getattr(hold_claims(policy), "current", None)


def suspended_claims(policy: Any) -> tuple:
    register = hold_claims(policy)
    return register.suspended if register is not None else ()


def hold_bars(policy: Any) -> tuple:
    register = hold_claims(policy)
    return register.bars if register is not None else ()


def hold_delegations(policy: Any) -> list:
    """The executor delegation records (an empty list without a hold)."""
    hold = town_hold(policy)
    return hold.delegations if hold is not None else []


def offer_buffer(policy: Any) -> DecisionOffers:
    """This decision's offer buffer, opened on first use."""
    slot = policy._town_hold._offers
    if slot.buffer is None:
        slot.buffer = DecisionOffers()
    return slot.buffer


def open_offers(policy: Any) -> DecisionOffers | None:
    """This decision's offer buffer if a producer opened one, else None."""
    hold = town_hold(policy)
    return hold._offers.buffer if hold is not None else None


def take_offers(policy: Any) -> DecisionOffers | None:
    """Close this decision's offer buffer and return it (None if unopened)."""
    hold = town_hold(policy)
    if hold is None:
        return None
    buffer, hold._offers.buffer = hold._offers.buffer, None
    return buffer


def offered_steps(policy: Any) -> tuple:
    """The step offers producers made on this decision, in order."""
    buffer = open_offers(policy)
    return tuple(buffer.steps) if buffer is not None else ()

# The family each town rung's entry admits under when its call site passes
# no ``family=`` (formerly the claim ladder's rung table).
RUNG_FAMILIES: dict[str, tuple[str, ...]] = {
    "combat": ("_direction_key#2", "_ranged_attack_key#1", "_ranged_attack_key#2",
        "_summoner_ranged_kill_key", "_immobile_summoner_exit_key"),
    "curse-enchant": ("_town_enchant_launcher_key", "_town_remove_curse_key"),
    "departure": ("_descent_step", "_hunt_step#2", "_normal_loot_key#1", "_return_to_town_key#1",
        "_return_to_town_key#2", "_return_to_town_key#3"),
    "detectors": ("_breakout_restore_weapon_key#1", "_breakout_restore_weapon_key#2",
        "_dark_locomotion_key", "_explore_step#1", "_navigation_livelock_key"),
    "equipment-txn": ("_equipment_transaction_town_key#1", "_equipment_transaction_town_key#2",
        "_equipment_transaction_town_owner_key", "_heavy_curse_inscription_key",
        "_home_catalogue_work_key", "_shopping_approach_key#1",
        "_town_random_teleport_suppression_key", "_town_restore_weapon_key"),
    "escape": ("_blocking_escape_melee_key", "_breeder_breakthrough_escape_key",
        "_breeder_breakthrough_key", "_direction_key#1", "_emergency_item", "_flee_step#2",
        "_fruitless_disengage_key", "_item_destroying_breeder_leave_key", "_unseen_retreat_key"),
    "esp-threat": ("_esp_threat_hunt_key", "_esp_threat_rest_key"),
    "explore": ("_explore_step#2", "_immobile_breeder_giveup_key"),
    "floor-loot": ("_chest_processing_key#1", "_chest_processing_key#2", "_conquest_loot_key",
        "_normal_loot_key#2", "_victory_loot_key"),
    "fundraising": ("_fundraising_key#1", "_fundraising_key#2"),
    "home-scan": ("_home_full_knowledge_key",),
    "home-visit": ("_home_disposal_processing_key", "_home_full_relief_key", "_home_full_skip_key"),
    "hunt": ("_hunt_step#1", "_hunt_step#3"),
    "identification": ("_town_device_processing_key", "_town_equipped_identification_key"),
    "positioning": ("_choke_engagement_key", "_detected_threat_preparation_key", "_flee_step#3",
        "_flee_step#4", "_melee_swarm_combat_key", "_paralyzer_prevention_key",
        "_unseen_retreat_intercept_key"),
    "quest-request": ("_fixed_quest_key#1", "_fixed_quest_key#2",
        "_kill_quest_floor_recovery_key", "_start_kill_quest_regeneration",
        "_town_order_step4_key#1", "_town_order_step4_key#2"),
    "quest-sweep": ("navigator.decide",),
    "shop-sell": ("_overweight_surplus_sale_key",),
    "store-router": ("_released_restock_store_key", "_shopping_approach_key#2",
        "_town_space_deposit_key"),
    "survival": ("_experience_potion_quaff_key", "_flee_step#1", "_mana_food_loot_key",
        "_mana_food_survival_override_key", "_stat_gain_quaff_key", "_stat_restore_quaff_key",
        "_survival_gate_key#1", "_survival_gate_key#2", "_town_kill_mob_key"),
    "town-plan": ("_town_overflow_destroy_key",),
}
_FAMILY_OF_RUNG = {name: family for family, names in RUNG_FAMILIES.items() for name in names}
TERMINALS = {name: decl._replace(family=_FAMILY_OF_RUNG.get(name, ""))
             for name, decl in TERMINALS.items()}

# The registered owner families (``town_arbiter.owner_families``); any other
# family a call site passes is admitted as UNREGISTERED_FAMILY.
_OWNER_FAMILIES = frozenset(owner_families())
# The town errand families whose store operation, exit or Reach/Observe errand
# names its acting owner (the ladder's S3 families).
TOWN_OWNER_FAMILIES = frozenset({
    "store-router",
    "shop-buy",
    "shop-sell",
    "home-visit",
    "home-errand",
    "home-scan",
    "equipment-txn",
    "identification",
    "curse-enchant",
    "cross-town",
    "rumor",
})
# The holders of the town errand hold: the town owners and the quest request.
_ERRAND_HOLD_FAMILIES = TOWN_OWNER_FAMILIES | {"quest-request"}


# --- The ladder (formerly claim_ladder) -------------------------------------
# The rank of each rung: the post-decision rewrites first, then every rung
# ``_decide`` consults in its order, then the town errands (one shared rank),
# then the fallbacks.  ``claim_owner_transition`` lets a strictly higher rung
# suspend a held Reach/Observe claim (``owner_change``), and a resumed claim
# keeps its own rank.

SECTION_REWRITE = "rewrite"
SECTION_DECIDE = "decide"
SECTION_TOWN = "town"
SECTION_FALLBACK = "fallback"

# Rev 10 item 1 / rev 10.1 item 2: the families that share one town rank.
TOWN_ERRAND_FAMILIES = frozenset({
    "home-errand",
    "home-scan",
    "home-visit",
    "shop-sell",
    "shop-buy",
    "store-router",
    "equipment-opt",
    "equipment-txn",
    "identification",
    "curse-enchant",
    "cross-town",
    "rumor",
})
# Rev 10.1 item 9: the families whose Reach/Observe claims record the monsters
# that triggered them.
TRIGGER_FAMILIES = frozenset({
    "positioning", "hunt", "esp-threat", "combat", "escape",
})

PREEMPTION = "preemption"
VIOLATION = "violation"
# Survival that does not outrank the holder replaces it (not a violation).
SURVIVAL_DISPLACED = "survival-displaced"


@dataclass(frozen=True)
class Rung:
    """One rung: a producer call site and the family its reasons belong to.

    ``reasons``           reason prefixes that identify this call site among
                          the family's rungs (empty: only its position).
    ``ordinary``          the family's rung for a reason no prefix claims.
    ``marked``            (``decide``) the call is an ``@claims``-marked
                          ``self`` method; otherwise ``producer`` is the call
                          as written (``navigator.decide``).
    ``owns_transaction``  (``equipment-txn``) the rung that holds a stripped
                          character; matched by ``non_discardable`` only.
    ``town``              a ``decide`` rung outside the town errand families
                          that still shares the town rank (fundraising's town
                          call).
    """

    producer: str
    family: str
    section: str
    reasons: tuple[str, ...] = ()
    ordinary: bool = False
    marked: bool = True
    owns_transaction: bool = False
    town: bool = False
    rank: int = field(default=-1, compare=False)
    # ``producer``, or ``producer#n`` for the n-th call site of a producer
    # ``_decide`` calls more than once: the rung's unique name in a row.
    name: str = field(default="", compare=False)

    @property
    def shares_town_rank(self) -> bool:
        if self.section == SECTION_TOWN:
            return True
        if self.section != SECTION_DECIDE or self.owns_transaction:
            return False
        return self.town or self.family in TOWN_ERRAND_FAMILIES


def _rewrite(producer, family, *reasons, ordinary=False):
    return Rung(producer, family, SECTION_REWRITE, tuple(reasons), ordinary)


def _decide(producer, family, *reasons, ordinary=False, marked=True,
            owns_transaction=False, town=False):
    return Rung(
        producer, family, SECTION_DECIDE, tuple(reasons), ordinary, marked,
        owns_transaction, town,
    )


def _town(producer, family, *reasons, ordinary=True):
    return Rung(producer, family, SECTION_TOWN, tuple(reasons), ordinary)


def _fallback(producer, family, *reasons):
    return Rung(producer, family, SECTION_FALLBACK, tuple(reasons), True)


# The line numbers in the comments are ``policy.py`` at 43802ae4; the test
# compares the order with the source itself, never with these numbers.
_RUNGS: tuple[Rung, ...] = (
    _town("absorb_key", "quest-request", "magic-eater:absorb", ordinary=False),
    # -- rewrite: after the ladder has spoken (design 3.3.1) ------------------
    _rewrite("_refuse_no_progress_cycle", "detectors", ordinary=True),
    _rewrite("_forbid_wait_while_damaged", "detectors", "no-wait:"),
    _rewrite("_break_positional_oscillation", "detectors", "nav:"),
    _rewrite("_break_livelock", "detectors"),
    _rewrite("_bound_escape_wait", "detectors"),
    _rewrite("_town_procurement_decision", "town-plan", ordinary=True),
    _rewrite("_skill_exp_request_key", "bookkeeping", "periodic:skill-exp"),
    _rewrite("_periodic_game_save_key", "bookkeeping", ordinary=True),
    _rewrite(
        "_periodic_character_dump_key", "bookkeeping",
        "periodic:character-dump", "town:character-dump",
    ),
    # -- decide: the order _decide consults them ------------------------------
    _decide("_home_errand_knowledge_key", "home-errand",
            "home-errand:request-knowledge:", "home-errand:await-fresh-knowledge:",
            "home-errand:leave-for-knowledge:"),
    _decide("_overweight_surplus_sale_key", "shop-sell", "town:overweight-surplus-"),
    _decide("_home_full_relief_key", "home-visit", "home:full-",
            "home:junk-sweep:", "home:junk-sweep-withdraw"),
    _decide("_equipment_transaction_town_key", "equipment-txn",
            owns_transaction=True),                                    # 5765
    _decide("_equipment_transaction_town_owner_key", "equipment-txn",
            owns_transaction=True),                                    # 5799
    _decide("_town_order_step4_key", "quest-request"),                 # 5883
    _decide("_esp_threat_hunt_key", "esp-threat", ordinary=True),      # 5986
    _decide("_summoner_ranged_kill_key", "combat",
            "summoner:ranged-kill"),                                   # 5991
    _decide("_emergency_item", "escape",
            "emergency:", "unseen-recall:", "guardian:teleport-to-cover",
            marked=False),                                             # 5996
    _decide("_item_destroying_breeder_leave_key", "escape",
            "breeder-item-damage:"),                                  # 6001
    _decide("_mana_food_survival_override_key", "survival",
            "survival:mana-", marked=False),                           # 6011
    _decide("_paralyzer_prevention_key", "positioning",
            "threat:paralyzer-avoid", "paralyzer-guard:",
            marked=False),                                             # 6015
    # The census-only immobile-summoner dispatcher's own step out of the
    # summoner's line-of-fire zone (its exits rank at the exit rung below).
    _decide("_immobile_summoner_key", "explore",
            "explore:avoid-immobile-summoner", marked=False),
    _decide("_unseen_retreat_intercept_key", "positioning"),           # 6021
    _decide("_unseen_retreat_key", "escape", "unseen:"),               # 6026
    _decide("_detected_threat_preparation_key", "positioning",
            "detected:", ordinary=True),                               # 6031
    _decide("_return_to_town_key", "departure"),                       # 6043
    _decide("_dark_locomotion_key", "detectors", "dark:"),             # 6056
    _decide("_breakout_restore_weapon_key", "detectors",
            "breakout:restore-combat-weapon"),                         # 6079
    _decide("_survival_gate_key", "survival"),                         # 6087
    _decide("_chest_processing_key", "floor-loot"),                    # 6116
    _decide("navigator.decide", "quest-sweep", "quest-strategy:",
            ordinary=True, marked=False),                              # 6125
    _decide("_town_kill_mob_key", "survival", "town:kill-mob"),        # 6156
    _decide("_breeder_breakthrough_key", "escape",
            "breeder-breakthrough:recall",
            "breeder-breakthrough:wait-recall",
            "breeder-breakthrough:teleport"),                          # 6170
    _decide("_choke_engagement_key", "positioning", "melee:choke"),    # 6178
    _decide("_ranged_attack_key", "combat"),                           # 6194
    _decide("_fruitless_disengage_key", "escape",
            "combat:disengage", "combat:fruitless"),                   # 6204
    _decide("_breeder_breakthrough_escape_key", "escape",
            "breeder-breakthrough:"),                                  # 6247
    _decide("_melee_swarm_combat_key", "positioning"),                 # 6264
    _decide("_flee_step", "survival", "status-threat:"),               # 6302
    _decide("_blocking_escape_melee_key", "escape",
            "combat:disengage-clear-path"),                            # 6351
    _decide("_flee_step", "escape", "flee", ordinary=True),            # 6362
    _decide("_direction_key", "escape", "flee:cornered-attack"),       # 6387
    _decide("_direction_key", "combat", "melee", ordinary=True),       # 6469
    _decide("_ranged_attack_key", "combat", "ranged:"),                # 6476
    _decide("_flee_step", "positioning", "threat:reposition"),         # 6494
    _decide("_hunt_step", "hunt", "hunt:quest-target"),                # 6513
    _decide("_survival_gate_key", "survival", "survival:",
            "weak-fainting", ordinary=True),                           # 6524
    _decide("_mana_food_loot_key", "survival", "mana-food:"),          # 6528
    _decide("_kill_quest_floor_recovery_key", "quest-request",
            "quest:regen:"),                                           # 6534
    _decide("_home_disposal_processing_key", "home-visit",
            "home-disposal:", ordinary=True),                          # 6538
    _decide("_town_restore_weapon_key", "equipment-txn"),              # 6598
    _decide("_fixed_quest_key", "quest-request"),                      # 6606
    _decide("_town_space_deposit_key", "store-router"),                # 6610
    _decide("_victory_loot_key", "floor-loot", "victory:"),            # 6614
    _decide("_conquest_loot_key", "floor-loot", "conquest:"),          # 6618
    _decide("_fixed_quest_key", "quest-request", "fixedquest:",
            ordinary=True),                                            # 6622
    _decide("_stat_restore_quaff_key", "survival", "restore:"),        # 6626
    _decide("_experience_potion_quaff_key", "survival",
            "experience:"),                                            # 6632
    _decide("_stat_gain_quaff_key", "survival", "stat-gain:"),         # 6638
    _decide("_town_order_step4_key", "quest-request", "bounty:"),      # 6642
    _decide("_fundraising_key", "fundraising", "fundraise:",
            ordinary=True),                                            # 6652
    _decide("_chest_processing_key", "floor-loot", "chest:"),          # 6690
    _decide("_normal_loot_key", "departure", "return:seek-loot"),      # 6709
    _decide("_navigation_livelock_key", "detectors",
            "livelock:ascend", "livelock:recall-escape",
            "livelock:seek-", "livelock:teleport-explore"),            # 6726
    _decide("_return_to_town_key", "departure"),                       # 6739
    _decide("_return_to_town_key", "departure", "return:",
            ordinary=True),                                            # 6756
    # Step 3 D2a (2026-10-13): catalogue-only work asks the knowledge screen
    # where the character stands; same owner and position as the Home
    # approach below, which remains for physical Home work.
    _decide("_home_catalogue_work_key", "equipment-txn",
            "equipment-transaction:catalogue-request-knowledge",
            "equipment-transaction:catalogue-await-knowledge"),
    _decide("_shopping_approach_key", "equipment-txn",
            "equipment-transaction:acquire-home-catalog",
            "equipment-transaction:travel-home"),                      # 6788
    _decide("_town_equipped_identification_key", "identification",
            ordinary=True),                                            # 6796
    _decide("_town_device_processing_key", "identification",
            "identify:device"),                                        # 6804
    _decide("_heavy_curse_inscription_key", "equipment-txn"),          # 6818
    _decide("_town_remove_curse_key", "curse-enchant",
            ordinary=True),                                            # 6822
    _decide("_town_enchant_launcher_key", "curse-enchant"),            # 6826
    _decide("_town_random_teleport_suppression_key",
            "equipment-txn"),                                          # 6830
    _decide("_equipment_transaction_town_key", "equipment-txn",
            ordinary=True),                                            # 6847
    _decide("_normal_loot_key", "floor-loot", "seek-loot", "loot:",
            ordinary=True),                                            # 6855
    _decide("_home_full_knowledge_key", "home-scan"),  # posted named-take prerequisite
    _decide("_shopping_approach_key", "store-router",
            ordinary=True),                                            # 6923
    # Its own site writes ``town:blocked:overflow-no-legal-disposal``, which
    # ranks here, not at town-plan's rewrite rung; the shop-sell
    # ``town:destroy-overflow`` it passes to ``_verified_destroy_key`` ranks
    # at shop-sell's town rung below.
    _decide("_town_overflow_destroy_key", "town-plan",
            "town:blocked:overflow-no-legal-disposal"),                # 6940
    _decide("_fundraising_key", "fundraising", "town:",
            town=True),                                                # 6980
    _decide("_released_restock_store_key", "store-router"),            # 6993
    # S2b.1b: the uncommitted WEAK / MEDIUM hunt is produced only here (the
    # rest slot, ``policy_combat._esp_threat_rest_key``), below the combat
    # rungs; without its prefixes it ranked at the committed STRONG hunt's
    # rung (5986) and a swing that took the walk over read as a violation.
    # ``esp-threat:hunt-strong`` is emitted at both sites and keeps the
    # ordinary rung (see ``rung_of``).
    _decide("_esp_threat_rest_key", "esp-threat",
            "esp-threat:hunt-weak", "esp-threat:hunt-medium"),         # 7015
    _decide("_flee_step", "positioning",
            "threat:avoid-engagement"),                                # 7114
    _decide("_descent_step", "departure",
            "seek-downstairs", "approach-descent"),                    # 7128
    _decide("_hunt_step", "departure", "clear-descent"),               # 7135
    _decide("_hunt_step", "hunt", "hunt", ordinary=True),              # 7155
    _decide("_breakout_restore_weapon_key", "detectors"),              # 7202
    _decide("_explore_step", "detectors", "breakout:", "stuck:"),      # 7248
    _decide("_immobile_breeder_giveup_key", "explore", "explore:"),    # 7283
    _decide("_explore_step", "explore", "explore", "search", "probe",
            "seek-secret-wall", ordinary=True),                        # 7288
    _decide("_immobile_summoner_exit_key", "combat",
            "summoner:seek-downstairs", "summoner:seek-upstairs", "summoner:teleport-level",
            "summoner:recall", "summoner:wait-recall"),
    _decide("_start_kill_quest_regeneration", "quest-request",
            "quest:regen:exhausted"),                                  # 7344
    # -- town: errands no _decide call site names; departure in town --------
    _town("_home_full_skip_key", "home-visit", "home:full-skip:", ordinary=False),
    _town("town-errand:home-errand", "home-errand"),
    _town("town-errand:home-scan", "home-scan"),
    _town("town-errand:shop-buy", "shop-buy"),
    _town("town-errand:shop-sell", "shop-sell"),
    _town("town-errand:equipment-opt", "equipment-opt"),
    _town("town-errand:cross-town", "cross-town"),
    _town("town-errand:rumor", "rumor"),
    _town(
        "town-errand:departure", "departure",
        "town:", "depart", "repetition-depart", "wilderness:",
        ordinary=False,
    ),
    # -- fallback -------------------------------------------------------------
    _fallback("fallback:idle", "idle", "policy:", "wait"),
    _fallback("fallback:misc", "misc"),
    _fallback("fallback:unregistered", "unregistered"),
)


def _ranked(rungs: tuple[Rung, ...]) -> tuple[tuple[Rung, ...], int]:
    """Give every rung its rank; returns the ladder and ``TOWN_RANK``."""
    rewrite_families: list[str] = []
    for rung in rungs:
        if rung.section == SECTION_REWRITE and rung.family not in rewrite_families:
            rewrite_families.append(rung.family)
    next_rank = len(rewrite_families)
    dungeon: dict[int, int] = {}
    for position, rung in enumerate(rungs):
        if rung.section == SECTION_DECIDE and not rung.shares_town_rank:
            dungeon[position] = next_rank
            next_rank += 1
    town_rank = next_rank
    calls: dict[str, int] = {}
    for rung in rungs:
        calls[rung.producer] = calls.get(rung.producer, 0) + 1
    seen: dict[str, int] = {}
    ranked = []
    for position, rung in enumerate(rungs):
        seen[rung.producer] = seen.get(rung.producer, 0) + 1
        name = (
            rung.producer
            if calls[rung.producer] == 1
            else f"{rung.producer}#{seen[rung.producer]}"
        )
        if rung.section == SECTION_REWRITE:
            rank = rewrite_families.index(rung.family)
        elif position in dungeon:
            rank = dungeon[position]
        elif rung.shares_town_rank:
            rank = town_rank
        else:
            rank = town_rank + 1
        ranked.append(Rung(
            rung.producer, rung.family, rung.section, rung.reasons,
            rung.ordinary, rung.marked, rung.owns_transaction, rung.town, rank,
            name,
        ))
    return tuple(ranked), town_rank


CLAIM_LADDER, TOWN_RANK = _ranked(_RUNGS)
FALLBACK_RANK = TOWN_RANK + 1

_RUNGS_BY_FAMILY: dict[str, tuple[Rung, ...]] = {}
_RUNG_BY_NAME: dict[str, Rung] = {}
for _rung in CLAIM_LADDER:
    _RUNGS_BY_FAMILY[_rung.family] = (*_RUNGS_BY_FAMILY.get(_rung.family, ()), _rung)
    _RUNG_BY_NAME[_rung.name] = _rung
del _rung


def rung_named(name: str | None) -> Rung | None:
    """The rung a row or a claim names, if the ladder still has it."""
    return _RUNG_BY_NAME.get(name) if name else None


def ordinary_rung(family: str) -> Rung | None:
    for rung in _RUNGS_BY_FAMILY.get(family, ()):
        if rung.ordinary:
            return rung
    return None


def rung_of(
    family: object, reason: str | None, *, non_discardable: bool = False
) -> Rung:
    """The rung a decision of this census family and reason came from.

    The one function the live writer and the offline reader both use (rev
    10.1 item 11).  ``family`` may be a ``ClaimOwner`` or its string value.
    """
    name = str(getattr(family, "value", family) or "unregistered")
    rungs = _RUNGS_BY_FAMILY.get(name)
    if not rungs:
        return ordinary_rung("unregistered")
    if non_discardable:
        for rung in rungs:
            if rung.owns_transaction:
                return rung
    normalized = reason or "policy:none"
    best: Rung | None = None
    best_length = -1
    for rung in rungs:
        if rung.owns_transaction:
            continue
        for prefix in rung.reasons:
            if normalized.startswith(prefix) and len(prefix) > best_length:
                best, best_length = rung, len(prefix)
    if best is not None:
        return best
    return ordinary_rung(name) or ordinary_rung("unregistered")


def rung_of_claim(
    family: object, rung_name: str | None, *, non_discardable: bool = False
) -> Rung:
    """A held claim's rung: the one it recorded, else its family's ordinary.

    A claim restored from a checkpoint pickled before the ladder carries no
    rung name; its family's ordinary rung is the honest answer.
    """
    return rung_named(rung_name) or rung_of(
        family, None, non_discardable=non_discardable
    )


def never_suspended(goal_kind: str | None, goal_source: str | None) -> bool:
    """Rev 10.1 item 6: a store-operation or transaction Observe claim."""
    return goal_kind == GOAL_OBSERVE and goal_source not in (
        FLOOR_CHANGE, "store-entry", "knowledge"
    )


def owner_change(
    *,
    held_rank: int,
    held_goal_kind: str | None,
    held_goal_source: str | None,
    held_survival: bool,
    new_rank: int,
    new_survival: bool,
) -> str:
    """Preemption, survival displacement or violation, for a held open
    Reach/Observe claim given way to another owner.

    * Rev 10 item 2 / rev 10.1 item 5: only a strictly higher rank suspends
      the holder (``PREEMPTION``), survival or not -- every push is by a
      strictly higher rank, which is what bounds the stack by the number of
      ranks.
    * Survival that does not rank strictly higher cannot suspend the holder;
      it *replaces* it (``SURVIVAL_DISPLACED``): the holder is released, and
      because survival is exempt (design 3.2, rev 9 item 3) it is not a
      violation.
    * Rev 10.1 item 6: a store-operation or transaction Observe claim is
      never suspended nor exempted; giving it way is a violation.
    * Anything else is a violation (rev 10 item 4).

    ``held_survival`` is part of the signature for the reader's records; a
    held survival claim is suspended or dropped like any other.
    """
    del held_survival
    if never_suspended(held_goal_kind, held_goal_source):
        return VIOLATION
    if new_rank < held_rank:
        return PREEMPTION
    if new_survival:
        return SURVIVAL_DISPLACED
    return VIOLATION


def nests_over(*, top_rank: int, new_rank: int) -> bool:
    """Rule (iii): only a new owner ranked strictly above the top nests."""
    return new_rank < top_rank


def resumable_index(stack, owner, goal, non_discardable: bool = False):
    """Where in the stack a claim of this owner and goal is suspended.

    The topmost match anywhere in the stack, not only the top (a claim can be
    buried under ones a later decision outranks), or ``None``.
    """
    for index in range(len(stack) - 1, -1, -1):
        claim = stack[index]
        if (
            claim.owner == owner
            and claim.goal == goal
        ):
            return index
    return None


def rung_family(rung_name: str, family: Any = None) -> str:
    """The family a town rung's entry admits under.

    A call site's own ``family=`` wins (a registered family is itself, any
    other is UNREGISTERED_FAMILY); otherwise the rung's declared family.
    """
    if family is not None:
        name = str(getattr(family, "value", family) or UNREGISTERED_FAMILY)
        return name if name in _OWNER_FAMILIES else UNREGISTERED_FAMILY
    decl = TERMINALS.get(rung_name)
    if decl is None or not decl.family:
        raise ValueError(f"unknown town producer rung: {rung_name}")
    return decl.family


def claim_family_of(policy: Any, reason: str | None) -> str:
    """The census family of a reason, answered by the live arbiter."""
    if reason == "shop:in-store-done":
        # A sale's no-effect exit is still that seller's operation. The
        # acting owner declares it; the generic reason cannot turn it into
        # a competing buyer while the sale observation is outstanding.
        for offer in reversed(offered_steps(policy)):
            if offer[0] == LEAVE_STORE_KEY and offer[2] == "shop:in-store-leave":
                return offer[1]
    if reason == "home:request-knowledge-scan":
        # The scan can be a step of registered equipment catalogue work,
        # rather than a new errand. Require the producer's explicit offer.
        for offer in reversed(offered_steps(policy)):
            if (offer[2] == "equipment:acquire-home-catalog"
                    and offer[5] == "home-catalog-available"
                    and offer[0] == HOME_KNOWLEDGE_MACRO):
                return offer[1]
    if reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}:
        return visit_exit_family(policy)
    if reason and reason.startswith("town:entrance-step-off:"):
        return claim_family_of(policy, reason.split(":", 2)[2])
    if reason and reason.startswith((
        "home:atomic-withdraw-target-unobserved",
        "home:atomic-withdraw-slot-unobserved",
        "home:atomic-withdraw-address-invalid",
    )):
        previous = standing_claim(policy)
        if (previous is not None and previous.owner.value in {'equipment-txn'}):
            return previous.owner.value
    visit = getattr(policy, "_store_visit", None)
    if reason in {"shop:one-shot-in-flight", "store:entry-await-observation"}:
        family = (
            getattr(visit, "operation_producer_family", None)
            or getattr(visit, "claim_owner", None)
            or getattr(visit, "opened_producer_family", None)
        )
        if family in TOWN_OWNER_FAMILIES:
            return family
    if (reason and reason.startswith(('home:leave-', 'home:store-context-exit')) and (visit is not None) and (getattr(visit, 'operation_producer_family', None) in {'equipment-txn'})):
        return visit.operation_producer_family
    if (reason and reason.startswith(("home:leave-", "home:store-context-exit"))
            and visit is not None
            and visit.owner == "equipment-transaction"):
        return (
            'equipment-txn'
        )
    if (reason and reason.startswith(('home:leave-', 'home:store-context-exit')) and (visit is not None) and (getattr(visit, 'claim_operation_identity', None) is not None) and (visit.claim_owner in {'home-visit', 'equipment-txn'})):
        return visit.claim_owner
    current = standing_claim(policy)
    if (reason and reason.startswith(('home:leave-', 'home:store-context-exit')) and (current is not None) and current.is_open and (current.owner.value in {'equipment-txn'}) and (current.goal.source in {'transaction'})):
        return current.owner.value
    composing_family = getattr(visit, "operation_producer_family", None)
    if composing_family is None:
        composing_family = getattr(visit, "opened_producer_family", None)
    if (reason and reason.startswith('home:atomic-') and (composing_family in {'equipment-txn'})):
        return composing_family
    if reason and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:leave-', 'home:store-context-exit')) and (composing_family in {'equipment-txn'}) and (getattr(policy, '_home_atomic_deposit_pending', None) is not None or getattr(policy, '_home_atomic_withdraw_pending', None) is not None):
        return composing_family
    arbiter = getattr(policy, "_town_turn_arbiter", None)
    if arbiter is not None:
        return arbiter.ownership_family(reason or "")
    return reason_owner_family(reason or "")




def advance_hold(policy: Any, snapshot: Any, key: Any) -> None:
    """Advance the town hold on the ``choose_key`` exit (the state step).

    Closes the claim this board ends (a producer's own closing, the exit's
    completion or expiry test, a preemption or a survival displacement),
    ends the suspended claims the board ends, resumes or declares this
    decision's claim, sets the bars of the claims that ended without their
    goal, binds and retires the executor delegations and declares the
    execution the producer offered.  Later decisions read all of it (the
    errand hold, the bars, the delegation tokens), so it runs on every
    decision.  It also keeps what the next decision and the driver read
    (``TownHold.last_reason`` / ``last_reach`` / ``last_rung``); all three
    are None when the claim recording is switched off.
    """
    registry = getattr(policy, "_owner_expectations", None)
    pops = (
        registry.drain_pops()
        if registry is not None and hasattr(registry, "drain_pops")
        else []
    )
    hold = town_hold(policy)
    register = hold_claims(policy)
    if register is None:
        if hold is not None:
            hold.last_reason = hold.last_reach = hold.last_rung = None
        return
    previous_reason = hold.last_reason
    # S2b.2: the bars this board lifts (a pure function of the board).
    claim_bar_lift(policy, snapshot, register)
    reason = policy.last_reason or ""
    standing = register.current
    claim_exit_completion(policy, snapshot, standing, pops)
    standing = register.current
    if (
        standing is not None and standing.is_open
        and standing.goal.kind == GOAL_REACH
        and previous_reason == "town:seek-shelter"
        and not getattr(policy, "_took_damage", False)
    ):
        policy._release_claim_goal(
            "seek-shelter-trigger-gone", owners=(standing.owner,),
            kinds=(GOAL_REACH,),
        )
    # S2b.1 (rev 10.1 item 6, rules i-ii): the suspended claims this board
    # ends -- a floor change, or a goal the board shows met.
    claim_suspended_exit(policy, snapshot, register)
    policy._claim_home_knowledge_observed = False
    # Rev 9.2 (S): the danger trigger of *this* return, recorded where the
    # return began -- never ``_last_return_trigger``, which outlives it.
    survival = is_survival(
        reason, getattr(policy, "_survival_return_trigger", None)
    ) or reason == "town:kill-mob" or (
        snapshot.in_town and reason == "melee"
        and any(
            not monster.pet
            and snapshot.player.position.distance_to(monster.position) <= 1
            for monster in snapshot.visible_monsters
        )
    )
    # S2a: the claim records the **census** family -- who owns the
    # producer -- not the arbitration bucket its reason spends in town.
    # A posted combat-weapon Home withdrawal can pass through the generic
    # Home confirmation and one-shot wait exits.  Their reason strings
    # name the wrapper, while the still-open operation belongs to the
    # filed Home errand.  Keep its recorded claim through both waits.
    standing = register.current
    continuing_home_errand = (
        reason in {
            "home:atomic-withdraw-await-confirmation",
            "shop:one-shot-in-flight",
        }
        and standing is not None and standing.is_open
        and standing.owner.value == "home-errand"
        and standing.goal.source == STORE_OPERATION
        and getattr(policy, "_home_atomic_withdraw_pending", None) is not None
    )
    suspended_holder = next((claim for claim in reversed(register.suspended)
                             if claim.closed is None
                             and claim.state.value == "suspended"
                             and reason.endswith(f":{claim.owner.value}")), None)
    continuing_holder_wait = (
        reason.startswith(("ownership:holder-silent:",
                           "ownership:holder-await:",
                           "ownership:declaration-"))
        and ((standing is not None and standing.is_open
              and reason.endswith(f":{standing.owner.value}"))
             or suspended_holder is not None)
    )
    continuing_owner = (
        continuing_home_errand or continuing_holder_wait
    )
    continuation_claim = (
        suspended_holder
        if continuing_holder_wait and suspended_holder is not None
        and (standing is None or not standing.is_open
             or not reason.endswith(f":{standing.owner.value}"))
        else standing
    )
    owner = (
        continuation_claim.owner if continuing_owner
        else owner_of(claim_family_of(policy, reason))
    )
    if reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}:
        family = visit_exit_family(policy)
        if family != "barrier-provenance-missing":
            owner = owner_of(family)
    claim_refresh_non_discardable(policy, owner)
    # S2b.1 (rev 10.1 items 1-2): the rung and rank of this decision.
    non_discardable = (
        continuation_claim.non_discardable
        if continuing_owner
        else getattr(policy, "_decision_non_discardable", None) == owner.value
    ) and not reason.endswith(":await-entry")
    rung = rung_of(owner, reason, non_discardable=non_discardable)
    standing = register.current
    goal = (
        continuation_claim.goal
        if continuing_owner
        else claim_goal(policy, snapshot, key, owner, reason, standing)
    )
    if (
        standing is not None and standing.is_open
        and standing.owner == owner
        and reason.startswith("equipment-transaction:stale-identity-invalidated:")
    ):
        policy._release_claim_goal('transaction-identity-stale', owners=(owner,), kinds=(GOAL_OBSERVE,), sources=('transaction',))
        standing = register.current
    if (
        standing is not None and standing.is_open
        and standing.owner == owner
        and standing.goal.source == STORE_ENTRY
        and goal.kind == GOAL_TERMINAL
    ):
        policy._release_claim_goal(
            f"entry-abandoned:{reason}", owners=(owner,),
            kinds=(GOAL_OBSERVE,),
            sources=(STORE_ENTRY,),
        )
        standing = register.current
    if (
        standing is not None and standing.is_open
        and standing.owner == owner
        and standing.goal.source == STORE_OPERATION
        and goal.kind == GOAL_OBSERVE
        and standing.goal != goal
        and getattr(policy, "_home_atomic_withdraw_pending", None) is None
        and getattr(policy, "_home_atomic_deposit_pending", None) is None
    ):
        policy._release_claim_goal(
            "operation-identity-stale", owners=(owner,),
            kinds=(GOAL_OBSERVE,),
            sources=(STORE_OPERATION,),
        )
        standing = register.current
    action, label, dropped = claim_owner_transition(
        policy, register, standing, owner, goal, rung, survival, non_discardable,
        snapshot=snapshot,
    )
    if action == PREEMPTION:
        # Design 3.2 / rev 10 item 2: a strictly higher rung suspends the
        # holder with its goal intact.  The one caller of ``suspend``.
        register.suspend(
            label, sequence=policy._decision_sequence, turn=snapshot.turn
        )
        # Round 3: a holder restored with no floor takes this board's.
        register.stamp_suspended_floor(standing.claim_id, snapshot.floor_key)
    elif action == SURVIVAL_DISPLACED:
        # Survival that does not outrank the holder replaces it: released,
        # exempt, not a violation (round 2, F1/F2).
        register.release(label)
    if action is not None:
        # S2a.1's order: the goal is read after the holder closed, exactly
        # as it was when survival was the only preemptor.
        goal = claim_goal(
            policy, snapshot, key, owner, reason, register.current
        )
    resumed = claim_resolve_suspended(
        policy, register, owner, goal, rung, survival, non_discardable
    )
    if resumed is not None:
        # The resumed claim keeps its own rank unless this decision's rung
        # is strictly higher, so it still outranks nothing it sat under.
        outranks = resumed.rank is None or rung.rank < resumed.rank
        claim = register.resume(
            resumed.claim_id,
            sequence=policy._decision_sequence,
            turn=snapshot.turn,
            rank=rung.rank if outranks else resumed.rank,
            rung=rung.name if outranks else resumed.rung,
            perceived_turn=claim_trigger_perceived(
                snapshot, resumed.trigger_monsters
            ),
        )
    else:
        current = register.current
        continuing = register.continues(owner, goal, non_discardable)
        triggers = (
            current.trigger_monsters
            if continuing and current is not None
            else claim_trigger_monsters(policy, owner, goal)
        )
        register.declare(
            owner,
            goal,
            non_discardable=non_discardable,
            opened_sequence=policy._decision_sequence,
            floor=snapshot.floor_key,
            survival=survival,
            opened_turn=snapshot.turn,
            rank=rung.rank,
            rung=rung.name,
            trigger_monsters=triggers,
            perceived_turn=claim_trigger_perceived(snapshot, triggers),
        )
    if claim_owner_retired(policy, owner):
        claim = register.retire()
    elif key is None or key == "":
        claim = register.await_observation()
    else:
        claim = register.keep_active()
    # The store visit records which claim operates it (``claim_family_of``
    # reads ``claim_owner``).
    visit = getattr(policy, "_store_visit", None)
    if visit is not None and claim.is_open and claim.owner.value in TOWN_OWNER_FAMILIES:
        visit.claim_id = claim.claim_id
        visit.claim_owner = claim.owner.value
    claim_set_bars(policy, snapshot, register, dropped=standing if dropped else None)
    bind_execution_delegations(policy, claim)
    observe_execution_delegations(policy)
    record_execution_declaration(policy, claim, key, reason)
    declared = register.current
    distance = claim_goal_distance(policy, snapshot, declared.goal)
    hold.last_reason = reason
    hold.last_reach = (
        (declared.claim_id, distance)
        if declared.goal.kind == GOAL_REACH and isinstance(distance, int)
        else None
    )
    hold.last_rung = rung.name


def errand_hold(policy: Any, family: str, *, enforced: bool = False,
                arrival_board: Any = None) -> Any:
    """Return the open town errand that owns a different producer's turn.

    Callers ask before changing their own session, plan, or selection
    state. ON also restores a town errand suspended by a higher owner
    before a different errand can displace it.

    ``arrival_board``: a standing cell Reach whose arrival that board
    shows is finished work, not a holder.  S3.3 ON closes it on the same
    evidence before any town producer asks (``choose_key``); the
    cross-area Home hold reads that evidence without closing the claim.
    """
    def town_errand(claim):
        return claim.owner.value in _ERRAND_HOLD_FAMILIES

    register = hold_claims(policy)
    standing = getattr(register, "current", None)
    if (
        standing is not None
        and standing.is_open
        and town_errand(standing)
        and standing.owner.value != family
        and standing.goal.kind in {GOAL_REACH, GOAL_OBSERVE}
        and not (arrival_board is not None
                 and claim_reach_arrival(policy, arrival_board, standing)
                 is not None)
    ):
        return standing
    if enforced and register is not None:
        for claim in reversed(register.suspended):
            if (claim.closed is None
                    and claim.state.value == "suspended"
                    and town_errand(claim)
                    and claim.owner.value != family
                    and claim.goal.kind in {
                        GOAL_REACH, GOAL_OBSERVE
                    }
                    and not (claim.goal.source == KNOWLEDGE
                             and policy._home_knowledge_current)):
                return claim
    return None


def home_catalogue_sequence_enforced(policy: Any) -> bool:
    """Protect physical Home work under cross-area enforcement."""
    return bool(getattr(policy, "_crossarea_fundraising_enforced", False))


def home_catalogue_work_holder(policy: Any) -> Any:
    holder = errand_hold(policy, "__none__", enforced=True)
    declaration = getattr(holder, "execution", None)
    if (declaration is not None
            and declaration.work_id == "equipment:acquire-home-catalog"
            and declaration.expected_effect == "home-catalog-available"):
        return holder
    return None


def home_hold_board(policy: Any) -> Any:
    """The board whose observed arrival ends a route for the Home hold.

    S3.3 ON already closed that arrival before the producers ask, so ON
    passes no board and keeps its own verdicts unchanged.
    """
    return getattr(policy, "_map_predicate_snapshot", None)


def home_sequence_has_holder(policy: Any) -> bool:
    if not home_catalogue_sequence_enforced(policy):
        return False
    # A route that this board shows arrived (at the Home it reached) is
    # not a physical Home sequence; holding Home producers for it made
    # every routed Home pass leave unfulfilled (live 2026-10-02 06:16).
    holder = errand_hold(
        policy, "__none__", enforced=True, arrival_board=home_hold_board(policy))
    visit = getattr(policy, "_store_visit", None)
    return bool(holder is not None and (
        home_catalogue_work_holder(policy) is not None
        or (visit is not None and visit.store_type == STORE_HOME)
        or (holder.goal.source == STORE_OPERATION
            and str(STORE_HOME) in holder.goal.expectation)))


# --- Advancing the hold (moved from the policy, structure stage 2 B slice 4) -
# The steps ``advance_hold`` and the errand hold take on the policy's state:
# closing, suspending and resuming claims, the goal of a decision, the bars,
# and the executor delegations' lifecycle.

def visit_exit_family(policy) -> str:
    """Return the captured operation's owner for a store leave barrier."""
    visit = getattr(policy, "_store_visit", None)
    producer = getattr(visit, "operation_producer_family", None)
    if producer in TOWN_OWNER_FAMILIES:
        return producer
    requester = getattr(visit, "exit_requester", None)
    if (requester in TOWN_OWNER_FAMILIES
            and requester in getattr(visit, "requester_families", ())):
        return requester
    return "barrier-provenance-missing"


def record_execution_declaration(policy, claim, key, reason: str) -> None:
    register = hold_claims(policy)
    buffer = take_offers(policy)
    offers = buffer.steps if buffer is not None else ()
    no_steps = buffer.no_steps if buffer is not None else ()
    waits = buffer.waits if buffer is not None else ()
    offer = next((candidate for candidate in reversed(offers)
                  if key == candidate[0]
                  and claim.owner.value == candidate[1]), None)
    no_step = (
        next((candidate for candidate in reversed(no_steps)
              if claim.owner.value == candidate[0]), None)
        if key is None else None
    )
    wait = next((candidate for candidate in reversed(waits)
                 if key == candidate[0]
                 and claim.owner.value == candidate[1]), None)
    posted_wait = (
        key is None and claim.execution is not None
        and claim.execution.state == "awaiting"
        and claim.execution.operation_ref is not None
    )
    if posted_wait:
        # A producer's no-key result cannot settle an unresolved send.
        offer = None
        no_step = None
        wait = None
    if wait is not None and (offer is None or wait[6] > offer[12]) and (
        no_step is None or wait[6] > no_step[3]
    ):
        _, producer, work_id, operation_ref, effect, continuation, _ = wait
        current_execution = claim.execution
        if (current_execution is None
                or current_execution.state != "awaiting"
                or current_execution.operation_ref != operation_ref):
            register.declare_execution(
                claim.claim_id, work_id=work_id, producer=producer,
                state="awaiting", operation_ref=operation_ref,
                expected_effect=effect, continuation=continuation,
            )
        offer = None
        no_step = None
    if no_step is not None and (offer is None or no_step[3] > offer[12]):
        producer, work_id, fact, _, state = no_step
        if state == "done":
            register.declare_execution(
                claim.claim_id, work_id=work_id, producer=producer,
                state="done", evidence=fact,
            )
        else:
            register.declare_execution(
                claim.claim_id, work_id=work_id, producer=producer,
                state="releasing", cause=fact,
            )
        offer = None
    if offer is not None:
        (_, producer, work_id, step, args, effect, continuation, budget,
         state, evidence, cause, post_on_emit, _, entry) = offer
        register.declare_execution(
            claim.claim_id, work_id=work_id, producer=producer,
            state=state, next_step=step, arguments=args,
            expected_effect=effect, continuation=continuation,
            budget_ref=budget, evidence=evidence, cause=cause,
            producer_entry=entry,
        )
        # The driver alone can turn an emitted command into a posted wait.
        if state == "acting" and post_on_emit and key not in (None, ""):
            policy._execution_pending_post = (claim.claim_id, key, work_id)


def claim_refresh_non_discardable(policy, owner) -> None:
    """Refresh the producer's per-decision slot from its live obligation."""
    family = owner.value
    if family == "equipment-txn" and getattr(
        policy, "_equipment_transaction_owned_items", None
    ):
        policy._declare_non_discardable(family)
    elif family in {'home-visit', 'home-errand', 'equipment-txn'} and (getattr(policy, '_home_atomic_withdraw_pending', None) is not None or getattr(policy, '_home_atomic_deposit_pending', None) is not None or False) and (not (family == 'home-errand' and (policy.last_reason or '').startswith('home-errand:request-knowledge'))):
        policy._declare_non_discardable(family)
    else:
        chain = getattr(policy, "_staged_prompt_chain", None)
        if chain is not None and claim_family_of(policy, chain.get("owner")) == family:
            policy._declare_non_discardable(family)


def close_claim(
    policy,
    event: str,
    label: str,
    *,
    owners,
    cell=CLAIM_ANY_CELL,
    kinds: tuple[str, ...] | None = None,
    sources: tuple[str, ...] | None = None,
    monsters=None,
) -> None:
    """Close the standing claim when it is exactly the goal ended here.

    The standing claim is the one the previous decision declared.  Rev
    9.2 (U): every closing names the owners it may close, and closes
    nothing when the standing claim belongs to another; beyond that it
    closes only a claim that is still open and of one of ``kinds``, and

    * a site that names the ``cell`` it drops closes only a Reach goal
      aimed at exactly that cell (``None`` names no goal: nothing
      closes), and by default only Reach goals;
    * a site that names ``monsters`` closes only a Reach goal on one of
      those ``(index, race_id)`` identities;
    * an ``Observe`` goal closes only when ``sources`` is ``None`` or one
      of them is a prefix of its source.

    S2b.1b: a ``complete`` or ``release`` that names exactly the goal it
    ends (a ``cell`` or ``monsters``) also closes that goal while a
    preemption holds it on the suspended stack (design rev 10.1 item 5).
    The producer drops its goal where it always did; before, the closing
    found another owner's claim standing and closed nothing, so the
    suspended claim was later displaced and counted as a violation.
    """
    register = hold_claims(policy)
    if register is None:
        return
    names = {getattr(owner, "value", owner) for owner in owners}
    cell_named = cell is not CLAIM_ANY_CELL
    named_monsters = None if monsters is None else set(monsters)
    if kinds is None:
        kinds = (
            (GOAL_REACH,)
            if cell_named or named_monsters is not None
            else (GOAL_REACH, GOAL_OBSERVE)
        )

    def matches(claim) -> bool:
        if claim.owner.value not in names:
            return False
        goal = claim.goal
        if goal.kind not in kinds:
            return False
        if goal.kind == GOAL_REACH and cell_named:
            if not isinstance(cell, Position) or goal.cell != (cell.y, cell.x):
                return False
        if goal.kind == GOAL_REACH and named_monsters is not None:
            if goal.monster is None or goal.monster not in named_monsters:
                return False
        if goal.kind == GOAL_OBSERVE and sources is not None:
            if goal.source is None or not str(goal.source).startswith(
                tuple(sources)
            ):
                return False
        return True

    standing = register.current
    if standing is not None and standing.is_open and matches(standing):
        if event == "complete":
            register.complete(label)
        elif event == "expire":
            register.expire(label)
        else:
            register.release(label)
        return
    if event == "expire" or (
        event != "complete" and not (cell_named or named_monsters is not None)
    ):
        return
    for claim in reversed(register.suspended):
        if matches(claim):
            register.close_suspended(
                claim.claim_id,
                "complete" if event == "complete" else "release",
                label,
            )
            return


def claim_operation_goal(policy, snapshot, owner, reason, content):
    """The active operation's stable identity, independent of step posts."""
    if content == STORE_ENTRY:
        return None
    if owner.value == "equipment-txn" and content == "transaction":
        session = getattr(policy, "_equipment_transaction_session", None)
        if session is not None:
            opened = getattr(session, "opened_sequence", None)
            if opened is None:
                opened = policy._decision_sequence
                session.opened_sequence = opened
            return observe_goal(
                (opened, tuple(map(repr, session.plan.actions))),
                EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
                source="transaction",
            )
    if content == KNOWLEDGE:
        return observe_goal(
            (STORE_HOME, "knowledge",
             getattr(policy, "_home_knowledge_scan_epoch", None)
             or getattr(policy, "_town_visit_epoch", None)),
            STORE_STUCK_LIMIT, source=KNOWLEDGE,
        )
    if content != STORE_OPERATION:
        return None
    visit = getattr(policy, "_store_visit", None)
    if owner.value in {"shop-buy", "shop-sell"} and visit is not None:
        if visit.operation_key is not None:
            return observe_goal(
                (visit.store_type, visit.operation_key, visit.opened_sequence),
                STORE_STUCK_LIMIT, source=STORE_OPERATION,
            )
    if owner.value in {'home-visit', 'equipment-txn'} and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:morivant-restore-temporary-deposit', 'home:leave-', 'home:store-context-exit')) and (visit is not None) and (visit.store_type == STORE_HOME):
        withdrawal = getattr(policy, "_home_atomic_withdraw_pending", None)
        deposit = getattr(policy, "_home_atomic_deposit_pending", None)
        withdraw_step = "withdraw" in reason or reason.startswith(
            ("home:leave-", "home:store-context-exit")
        )
        identity = getattr(visit, "claim_operation_identity", None)
        if identity is None and visit.operation_key is not None:
            identity = (STORE_HOME, visit.opened_sequence, visit.operation_key)
        if withdrawal is not None and identity is not None and withdraw_step:
            return observe_goal(
                identity,
                STORE_STUCK_LIMIT, source=STORE_OPERATION,
            )
        if deposit is not None and identity is not None:
            return observe_goal(
                identity,
                STORE_STUCK_LIMIT, source=STORE_OPERATION,
            )
    if owner.value == "home-errand":
        request = getattr(getattr(policy, "_home_errand", None), "request", None)
        if request is not None:
            operation = (
                "knowledge",
                getattr(policy, "_home_knowledge_scan_epoch", None)
                or getattr(policy, "_town_visit_epoch", None),
            ) if reason.startswith("home-errand:request-knowledge") else (
                getattr(visit, "claim_operation_identity", None)
                if visit is not None and visit.store_type == STORE_HOME
                else None
            )
            return observe_goal(
                (STORE_HOME, "errand", repr(request.signature), operation),
                STORE_STUCK_LIMIT, source=STORE_OPERATION,
            )
    chain = getattr(policy, "_staged_prompt_chain", None)
    if chain is not None and owner.value in {"identification", "curse-enchant"}:
        return observe_goal(
            (chain.get("owner"), len(chain.get("gates", ()))),
            len(chain.get("gates", ())),
            source=STORE_OPERATION,
        )
    return None


def claim_goal(
    policy, snapshot: Snapshot, key, owner: ClaimOwner, reason: str, standing
) -> Goal:
    """This decision's goal from the slot.

    Design rev 9 item 2 and rev 9.2 (C).  The kind comes from the
    checked-in typing table (``goal_typing``); the content comes
    from what a producer wrote on this board, and only when that
    producer's family is the row's owner:

    * ``Reach``: the slot's goal (a cell, a monster, or a place) when its
      family is this owner; otherwise the decision declares ``Terminal``
      (no slot, or a slot of another owner).
    * ``Observe``: a floor change is always the table's own content; any
      other ``Observe`` takes the expectation posted on this board by
      this owner (another owner's is not used: ``owner-mismatch``), else
      the same owner's still-open ``Observe`` claim (a transaction's later
      keys continue it), else the table's content.
    * ``Terminal``: the effect label.
    """
    if reason.startswith("town:entrance-step-off:"):
        reason = reason.split(":", 2)[2]
    # Catalogue acquisition owns its observed result across entry and
    # scan steps. Opening the page alone cannot discharge that work.
    if any(offer[0] == key and offer[1] == owner.value
           and offer[5] == "home-catalog-available"
           for offer in offered_steps(policy)):
        if (standing is not None and standing.is_open
                and standing.owner == owner
                and (standing.goal.source == KNOWLEDGE
                     or (standing.goal.source == STORE_ENTRY
                         and standing.execution is not None
                         and standing.execution.expected_effect == "home-catalog-available"))):
            return standing.goal
        return observe_goal(
            (STORE_HOME, "knowledge", policy._town_visit_epoch),
            STORE_STUCK_LIMIT, source=KNOWLEDGE,
        )
    if (
        standing is not None and standing.is_open and (standing.owner == owner) and (reason == 'store:entry-await-observation' and standing.goal.source in {STORE_OPERATION, 'transaction'} or (reason == 'home:scan-incomplete-open-page' and standing.goal.source == KNOWLEDGE) or (reason == 'shop:one-shot-in-flight' and standing.goal.source == STORE_OPERATION))
    ):
        # Neither a lagged store entry nor an incomplete Home page ends
        # the operation or knowledge observation it is waiting for.
        return standing.goal
    if (reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}
            and standing is not None and standing.is_open
            and standing.owner == owner
            and standing.goal.kind == GOAL_OBSERVE
            and standing.goal.source == STORE_OPERATION
            and not getattr(getattr(policy, "_store_visit", None),
                            "operation_effect_observed", False)):
        return standing.goal
    visit = getattr(policy, "_store_visit", None)
    completed_transaction = (
        reason == "home:leave-after-one-operation"
        and hold_claims(policy) is not None
        and standing_claim(policy) is not None
        and standing_claim(policy).closed == "complete"
        and standing_claim(policy).closed_reason == "equipment-transaction-complete"
    )
    if (
        reason in {"shop:leave", "shop:store-context-exit",
                   "shop:await-leave-confirmation",
                   "shop:await-leave-generation"}
        or reason.startswith("home:leave-")
        or reason == "home:store-context-exit"
    ) and (completed_transaction or (visit is not None and visit.operation_effect_observed)):
        if (
            standing is not None and standing.is_open and (standing.owner == owner) and (standing.goal.kind == GOAL_OBSERVE) and (standing.goal.source in {STORE_OPERATION, 'transaction'})
        ):
            return standing.goal
        return terminal_goal(reason)
    if owner.value in {'equipment-txn'} and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:leave-', 'home:store-context-exit', 'equipment-transaction:await-confirmation', 'equipment-transaction:home-route-unavailable')):
        if (standing is not None and standing.is_open and (standing.owner == owner) and (standing.goal.source in {'transaction'})):
            return standing.goal
        operation = claim_operation_goal(policy, snapshot, owner, reason, "transaction")
        if operation is not None:
            return operation
    row = goal_typing(owner.value, reason)
    effect = terminal_goal(reason or "policy:none")
    chain = getattr(policy, "_staged_prompt_chain", None)
    if chain is not None and claim_family_of(policy, chain.get("owner")) == owner.value:
        staged = claim_operation_goal(
            policy, snapshot, owner, reason, STORE_OPERATION
        )
        if staged is not None:
            return staged
    if row is None or row.kind == GOAL_TERMINAL:
        if owner.value == "home-visit" and reason.startswith((
            "home:leave-", "home:store-context-exit",
        )):
            operation = claim_operation_goal(
                policy, snapshot, owner, reason, STORE_OPERATION
            )
            if operation is not None:
                return operation
        if (
            standing is not None and standing.is_open
            and standing.owner == owner
            and standing.goal.source == FLOOR_CHANGE
            and reason.startswith("town:wait-recall")
        ):
            return standing.goal
        return effect
    if (
        standing is not None and standing.is_open
        and standing.owner == owner
        and standing.goal.source == FLOOR_CHANGE
        and reason.startswith("town:wait-recall")
    ):
        return standing.goal
    # A route to the next transaction step is still the same open
    # session. The separately ruled await-entry wait keeps its own
    # store-entry goal once the entrance command has been posted.
    if (
        row.kind == GOAL_REACH and owner.value in {'equipment-txn'} and (not reason.endswith(':await-entry'))
    ):
        operation = claim_operation_goal(
            policy, snapshot, owner, reason, "transaction"
        )
        if operation is not None:
            return operation
    if row.kind == GOAL_REACH:
        slot = getattr(policy, "_decision_goal", None)
        if not (
            isinstance(slot, tuple)
            and len(slot) in (2, 3)
            and isinstance(slot[1], Goal)
            and slot[1].kind == GOAL_REACH
        ):
            return effect
        if slot[0] != owner.value:
            return effect
        return slot[1]
    within = OBSERVE_WITHIN.get(row.content, OWNER_EXPECTATION_MAX_TURNS)
    if row.content == STORE_ENTRY:
        visit = getattr(policy, "_store_visit", None)
        if (
            reason == "store:entry-await-observation"
            and visit is not None and visit.goal is not None
            and (snapshot.player.position.y, snapshot.player.position.x)
                != (visit.goal.y, visit.goal.x)
        ):
            return reach_goal((visit.goal.y, visit.goal.x))
        target = getattr(policy, "_store_entry_wait_owner", None)
        if target is None and visit is not None:
            target = visit.store_type
        return observe_goal(
            (STORE_ENTRY, target), within,
            source=STORE_ENTRY,
        )
    if row.content == FLOOR_CHANGE:
        return observe_goal(FLOOR_EXPECTATION, within, source=FLOOR_CHANGE)
    operation = claim_operation_goal(policy, snapshot, owner, reason, row.content)
    if operation is not None:
        return operation
    posted = getattr(policy, "_decision_expectation", None)
    if (
        isinstance(posted, tuple)
        and len(posted) == 2
        and isinstance(posted[1], Goal)
        and posted[1].kind == GOAL_OBSERVE
    ):
        if posted[0] == owner.value:
            return posted[1]
    if (
        standing is not None
        and standing.is_open
        and standing.owner == owner
        and standing.goal.kind == GOAL_OBSERVE
        and standing.goal.source != FLOOR_CHANGE
    ):
        return standing.goal
    return observe_goal((row.content,), within, source=row.content)


def claim_owner_retired(policy, owner) -> bool:
    """Whether the arbiter already holds this owner's claim as retired."""
    arbiter = getattr(policy, "_town_turn_arbiter", None)
    telemetry = getattr(arbiter, "telemetry", None) if arbiter else None
    if not isinstance(telemetry, dict):
        return False
    return bool(
        telemetry.get("retired")
        and telemetry.get("producer_owner") == owner.value
    )


def claim_perceived_monster(snapshot: Snapshot, identity):
    """The perceived monster with this ``(index, race_id)``, if any."""
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if (monster.index, monster.race_id) == tuple(identity):
            return monster
    return None


def claim_entered_store_at(policy, snapshot: Snapshot, cell) -> bool:
    """The board is inside the store whose entrance is ``cell``."""
    visit = getattr(policy, "_store_visit", None)
    entrance = getattr(visit, "goal", None)
    return (
        snapshot.store is not None
        and isinstance(entrance, Position)
        and tuple(cell) == (entrance.y, entrance.x)
    )


def claim_reach_arrival(policy, snapshot: Snapshot, claim) -> str | None:
    """The observed arrival that completes a cell Reach claim, read-only.

    The same evidence ``_claim_exit_completion`` closes the claim on: the
    player stands on the goal cell of the claim's own floor (never the
    open wilderness), or is inside the store whose entrance is the cell.
    """
    goal = claim.goal
    if (goal.kind != GOAL_REACH or goal.monster is not None
            or goal.cell is None):
        return None
    if claim.floor is not None and tuple(claim.floor) != tuple(snapshot.floor_key):
        return None
    if snapshot.on_open_wilderness:
        return None
    position = snapshot.player.position
    if goal.cell == (position.y, position.x):
        return "reached"
    if claim_entered_store_at(policy, snapshot, goal.cell):
        return "entered-store"
    return None


def claim_exit_completion(policy, snapshot: Snapshot, standing, pops) -> None:
    """Close the standing claim on what this board shows.

    * Reach, cell: the player stands on the goal cell on the claim's own
      floor (never on the open wilderness, whose grids are not local-map
      cells), or stands in the store whose entrance is the goal.
    * Reach, monster (rev 9.2 M): ``complete`` when the monster is
      adjacent, ``release`` when it is no longer perceived (it left
      perception or died).
    * Reach, place: only its producer's arrival test closes it.
    * Observe, floor change: ``snapshot.floor_key`` differs from the
      floor the claim was opened on; after 350 game turns it expires.
    * Observe, posted expectation: ``complete`` when the registry popped
      it as satisfied, or (rev 9.2 O) when the registry's own
      satisfaction test holds for it now, read-only and without a pop.
    * Observe older than its ``within`` (rev 9.2 E) closes ``expired``.
      ``within`` is counted in the unit its constant is defined in: game
      turns for the floor change (``RECALL_ACTIVATION_MAX_GAME_TURNS``),
      decisions for ``OWNER_EXPECTATION_MAX_TURNS`` and
      ``STORE_STUCK_LIMIT``, which both count decisions where they are
      defined.
    """
    if standing is None or not standing.is_open:
        return
    own = (standing.owner,)
    goal = standing.goal
    position = snapshot.player.position
    same_floor = standing.floor is None or tuple(standing.floor) == tuple(
        snapshot.floor_key
    )
    if goal.kind == GOAL_REACH:
        if goal.monster is not None:
            monster = claim_perceived_monster(snapshot, goal.monster)
            if monster is None or not same_floor:
                policy._release_claim_goal("target-lost", owners=own)
            elif position.distance_to(monster.position) <= 1:
                policy._complete_claim_goal("target-adjacent", owners=own)
            return
        if goal.cell is None:
            return
        if not same_floor or snapshot.on_open_wilderness:
            return
        arrival = claim_reach_arrival(policy, snapshot, standing)
        if arrival is not None:
            policy._complete_claim_goal(arrival, owners=own)
            return
        visit = getattr(policy, "_store_visit", None)
        entrance = getattr(visit, "goal", None)
        context = getattr(getattr(policy, "_home_visit", None), "context_token", None)
        if (
            entrance is not None
            and goal.cell == (entrance.y, entrance.x)
            and (
                (isinstance(context, tuple) and context[0] == "outside-ready")
                or getattr(policy, "_home_entry_operation_posted", False)
                or getattr(policy, "_intentional_entrance_activation", False)
            )
        ):
            policy._complete_claim_goal("entered-outside", owners=own)
        return
    if goal.kind != GOAL_OBSERVE:
        return
    if (
        goal.source == KNOWLEDGE
        and (getattr(policy, "_home_knowledge_current", False)
             or getattr(policy, "_claim_home_knowledge_observed", False))
    ):
        policy._complete_claim_goal("home-knowledge-current", owners=own)
        return
    session = getattr(policy, "_equipment_transaction_session", None)
    opened = getattr(session, "opened_sequence", None)
    session_replaced = (
        session is not None
        and any(part.isdecimal() for part in goal.expectation)
        and (opened is None or str(opened) not in goal.expectation)
    )
    if (
        goal.source in {'transaction'} and standing.owner.value in {'equipment-txn'} and (session_replaced or (session is None and (getattr(policy, '_equipment_transaction_owned_items', None) or False)))
    ):
        terminal = (
            getattr(policy, "_equipment_transaction_restore_terminal", None)
            or ("session-replaced" if session_replaced else None)
            or policy.last_reason or "session-cleared"
        )
        policy._release_claim_goal(
            f"abandoned:{terminal}", owners=own,
            kinds=(GOAL_OBSERVE,), sources=(goal.source,),
        )
        return
    if goal.source == FLOOR_CHANGE:
        if standing.floor is not None and not same_floor:
            policy._complete_claim_goal("floor-changed", owners=own)
        elif (
            goal.within is not None
            and standing.opened_turn is not None
            # S2b.1 (rev 10.1 item 6): the turns spent suspended do not
            # count against a resumed claim's ``within``.
            and snapshot.turn - standing.opened_turn
            - (standing.suspended_turns or 0) > goal.within
        ):
            close_claim(policy, "expire", "within-exceeded", owners=own)
        return
    if goal.source == STORE_ENTRY:
        # Restored pre-live23 declarations also named catalogue work,
        # although their goal was typed as entry. Honor the named effect.
        declaration = getattr(standing, "execution", None)
        catalogue_work = (declaration is not None
                          and declaration.expected_effect == "home-catalog-available")
        if catalogue_work and policy._home_knowledge_current:
            policy._complete_claim_goal("home-knowledge-current", owners=own)
            return
        visit = getattr(policy, "_store_visit", None)
        entrance = getattr(visit, "goal", None)
        if (
            not catalogue_work
            and snapshot.store is not None
            and str(snapshot.store.store_type) in goal.expectation
            and (
                entrance is None
                or claim_entered_store_at(
                    policy, snapshot, (entrance.y, entrance.x)
                )
            )
        ):
            policy._complete_claim_goal("entered-store", owners=own)
            return
    if any(
        owner == goal.source and why == EXPECTATION_POP_SATISFIED
        for owner, why in pops
    ):
        policy._complete_claim_goal("expectation-satisfied", owners=own)
        return
    registry = getattr(policy, "_owner_expectations", None)
    if (
        registry is not None
        and goal.source is not None
        and hasattr(registry, "verdict")
        and registry.pending(goal.source) is not None
        and registry.verdict(
            goal.source, policy._progress_core_of(snapshot)
        ) == EXPECTATION_POP_SATISFIED
    ):
        policy._complete_claim_goal("expectation-satisfied", owners=own)
        return
    if (
        goal.within is not None
        and standing.opened_sequence is not None
        # S2b.1 (rev 10.1 item 6): nor do the decisions spent suspended.
        and policy._decision_sequence - standing.opened_sequence
        - (standing.suspended_decisions or 0) >= goal.within
    ):
        close_claim(policy, "expire", "within-exceeded", owners=own)


def claim_goal_distance(policy, snapshot: Snapshot, goal: Goal):
    position = snapshot.player.position
    if goal.kind != GOAL_REACH:
        return None
    if goal.cell is not None:
        return position.distance_to(Position(*goal.cell))
    if goal.monster is not None:
        monster = claim_perceived_monster(snapshot, goal.monster)
        return (
            position.distance_to(monster.position)
            if monster is not None
            else None
        )
    return None


def claim_suspended_exit(policy, snapshot: Snapshot, register) -> None:
    """Rules (i) and (ii) of rev 10.1 item 6, on the suspended stack.

    (i) After a floor change (a town departure is one) a suspended
    floor-change ``Observe`` completes and every other suspended claim is
    released ``suspended-expired``.  (ii) On the same floor, a suspended
    ``Reach`` completes when the board shows it met, by the tests an
    active claim uses: the player on its cell, or next to its monster; and
    (S2b.1b) a suspended chase whose monster is no longer perceived is
    released ``target-lost``, as an active one is.  No store-operation or
    transaction ``Observe`` is ever on the stack
    (``never_suspended``).
    """
    position = snapshot.player.position
    for claim in register.suspended:
        goal = claim.goal
        if (
            goal.kind == GOAL_OBSERVE
            and goal.source == KNOWLEDGE
            and (getattr(policy, "_home_knowledge_current", False)
                 or getattr(policy, "_claim_home_knowledge_observed", False))
        ):
            register.close_suspended(
                claim.claim_id, "complete", "home-knowledge-current"
            )
            continue
        if claim.floor is None:
            # Round 3: a claim restored from before ``floor`` existed.
            # The first board that sees it suspended is its floor, so it
            # expires on the first floor change from here.
            register.stamp_suspended_floor(claim.claim_id, snapshot.floor_key)
            continue
        if tuple(claim.floor) != tuple(
            snapshot.floor_key
        ):
            if (
                goal.kind == GOAL_OBSERVE
                and goal.source == FLOOR_CHANGE
            ):
                register.close_suspended(
                    claim.claim_id, "complete", "floor-changed"
                )
            else:
                register.close_suspended(
                    claim.claim_id, "release", SUSPENDED_EXPIRED
                )
            continue
        if goal.kind == GOAL_OBSERVE and goal.source == STORE_ENTRY:
            if (
                snapshot.store is not None
                and str(snapshot.store.store_type) in goal.expectation
            ):
                register.close_suspended(
                    claim.claim_id, "complete", "entered-store"
                )
            continue
        if goal.kind != GOAL_REACH:
            continue
        if goal.monster is not None:
            monster = claim_perceived_monster(snapshot, goal.monster)
            if monster is None:
                # S2b.1b: the active claim's own rule (rev 9.2 M,
                # ``_claim_exit_completion``): a chased monster that is
                # no longer perceived -- killed by the preemptor's shot,
                # or gone -- releases the chase, suspended or not.
                register.close_suspended(
                    claim.claim_id, "release", "target-lost"
                )
            elif position.distance_to(monster.position) <= 1:
                register.close_suspended(
                    claim.claim_id, "complete", "target-adjacent"
                )
        elif goal.cell is not None and not snapshot.on_open_wilderness:
            # Round 3: the same tests as an active Reach claim
            # (``_claim_exit_completion``): on the cell, or inside the
            # store whose entrance is the cell.
            if goal.cell == (position.y, position.x):
                register.close_suspended(
                    claim.claim_id, "complete", "reached"
                )
            elif claim_entered_store_at(policy, snapshot, goal.cell):
                register.close_suspended(
                    claim.claim_id, "complete", "entered-store"
                )


def claim_owner_transition(
    policy, register, standing, owner, goal, rung, survival, non_discardable,
    *, snapshot
):
    """How this decision treats the claim the previous one declared.

    Returns ``(action, label, dropped)``: ``dropped`` is True when this
    decision drops the held claim without closing it (a violation of the
    ladder; ``claim_set_bars`` bars it).  Only a held claim that is still
    open with a Reach or Observe goal matters:

    * an owner change to a strictly higher rung (rev 10 item 2) is a
      preemption -- the caller suspends the holder (``survival-preemption``
      when the new decision is survival, as S2a.1 labelled it);
    * survival that does not outrank the holder, or the same owner turning
      to another goal on a survival decision, replaces it -- the caller
      releases it ``survival-displaced``; survival is exempt, so this is
      not a violation (round 2 F1/F2);
    * the same owner replacing its own open goal otherwise is a retarget
      violation (rev 10 item 4) -- never a preemption followed by
      ``resume-goal-changed`` on the same decision;
    * any other owner change is a violation, and so is any ordinary
      change away from a store-operation or transaction ``Observe`` claim
      (rev 10.1 item 6). A town survival decision suspends an S3 holder;
      adjacent melee also suspends a pending town monster chase.

    Nothing stops.
    """
    if (
        standing is None
        or not standing.is_open
        or standing.goal.kind not in (GOAL_REACH, GOAL_OBSERVE)
    ):
        return None, None, None
    if register.continues(owner, goal, non_discardable):
        # The same owner pursuing the same goal keeps its claim, survival
        # or not (``declare`` updates its survival flag).
        return None, None, None
    if (standing.owner == owner and standing.goal.source in {'transaction'} and (goal.source == STORE_ENTRY) and (policy.last_reason or '').endswith(':await-entry')):
        return PREEMPTION, "transaction-entry-wait", None
    # S3 town operations survive an emergency even when their Observe
    # source normally forbids suspension.  Other owners keep the ladder's
    # bounded-rank preemption rule.
    if (survival and standing.owner != owner
            and snapshot.in_town
            and (standing.owner.value in TOWN_OWNER_FAMILIES
                 or (standing.owner.value == "survival"
                     and policy.last_reason == "melee"))):
        return PREEMPTION, "survival-preemption", None
    held = rung_of_claim(
        standing.owner, standing.rung,
        non_discardable=standing.non_discardable,
    )
    if standing.owner == owner:
        verdict = SURVIVAL_DISPLACED if survival else VIOLATION
    else:
        verdict = owner_change(
            held_rank=held.rank,
            held_goal_kind=standing.goal.kind,
            held_goal_source=standing.goal.source,
            held_survival=standing.survival,
            new_rank=rung.rank,
            new_survival=survival,
        )
    if verdict == PREEMPTION:
        return PREEMPTION, (
            "survival-preemption"
            if survival
            else f"preempted-by:{owner.value}"
        ), None
    if verdict == SURVIVAL_DISPLACED:
        return SURVIVAL_DISPLACED, SURVIVAL_DISPLACED, None
    return None, None, True


def claim_resolve_suspended(
    policy, register, owner, goal, rung, survival, non_discardable
):
    """Rule (iii) of rev 10.1 item 6: resume, nest or displace.

    Unless this decision continues the current claim:

    * a claim of the same owner and goal suspended **anywhere** in the
      stack resumes (returned, for the caller to ``resume`` under its id);
      the claims above it that this decision outranks stay suspended, the
      others are displaced as below;
    * otherwise the stack is read from the top: the same owner with
      another goal releases it ``resume-goal-changed`` (rev 10 item 3), a
      new claim opens and the claims below are read on; a strictly
      higher rung nests over it (only a
      strictly higher rung: that is the bound on the depth); survival
      displaces it ``survival-displaced`` (exempt, no violation); any other
      owner displaces it -- a violation, recorded with the release
      ``resume-displaced`` -- and the next claim down is read the same
      way.
    """
    if register.continues(owner, goal, non_discardable):
        return None
    stack = register.suspended
    if survival and any(
        claim.owner.value in TOWN_OWNER_FAMILIES for claim in stack
    ):
        return None
    if (goal.source == STORE_ENTRY
            and (policy.last_reason or "").endswith(":await-entry")):
        return None
    match = resumable_index(stack, owner, goal, non_discardable)
    for index in range(len(stack) - 1, -1, -1):
        top = stack[index]
        if index == match:
            return top
        held = rung_of_claim(
            top.owner, top.rung, non_discardable=top.non_discardable
        )
        if match is None and top.owner == owner:
            register.close_suspended(
                top.claim_id, "release", "resume-goal-changed"
            )
            # the new claim opens here; the claims below are read the
            # same way, so it never sits above one it does not outrank
            continue
        if nests_over(top_rank=held.rank, new_rank=rung.rank):
            if match is None:
                return None
            continue
        if survival:
            register.close_suspended(
                top.claim_id, "release", SURVIVAL_DISPLACED
            )
            continue
        register.close_suspended(top.claim_id, "release", "resume-displaced")
    return None


def claim_trigger_monsters(policy, owner, goal):
    """Rev 10.1 item 9 / design 5.4.1: the monsters behind a new claim.

    For a Reach or Observe claim of positioning, hunt, esp-threat, combat
    or escape: the ``(index, race_id)`` pairs its producer declared on
    this board (``_declare_triggers``), plus the chased monster of a
    monster goal (hunt, whose target is its goal).  A producer that
    declared none records none -- never every perceived hostile.
    """
    if (
        owner.value not in TRIGGER_FAMILIES
        or goal.kind not in (GOAL_REACH, GOAL_OBSERVE)
    ):
        return ()
    found: set[tuple[int, int]] = set()
    slot = getattr(policy, "_decision_triggers", None)
    if (
        isinstance(slot, tuple)
        and len(slot) == 2
        and slot[0] == owner.value
    ):
        found.update(tuple(pair) for pair in slot[1])
    if goal.monster is not None:
        found.add((int(goal.monster[0]), int(goal.monster[1])))
    return tuple(sorted(found))


def claim_trigger_perceived(snapshot: Snapshot, triggers):
    """The game turn, when one of ``triggers`` is perceived on this board."""
    if not triggers:
        return None
    wanted = {tuple(pair) for pair in triggers}
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if (monster.index, monster.race_id) in wanted:
            return snapshot.turn
    return None


def claim_perceived_pairs(snapshot: Snapshot) -> frozenset:
    """Every ``(index, race_id)`` this board perceives (seen or detected)."""
    return frozenset(
        (int(monster.index), int(monster.race_id))
        for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
    )


def claim_durable_clearance(key):
    """The durable part of a retirement clearance key (round 2).

    User decision 2026-09-26: a town-errand bar lifts only when the
    durable part of the clearance key changes -- inventory, gold,
    equipment and the other durable facts of the progress vector, the
    quest and departure tuples -- never by the player's own movement.
    ``_town_retirement_clearance_key`` is the progress vector (its durable
    facts plus, for a walking owner, a ``("locomotion", ...)`` part that
    carries the distance to the goal), the departure tuple (whose last
    element is the same locomotion part), or the quest route-unavailable
    tuples (durable already).  So: the locomotion parts go, the departure
    tuple loses its last element, and the progress core -- position,
    turn and sequence already zeroed by the vector -- also forgets the
    hit points and the store the player stands in, which walking and
    waiting change without any errand being done.
    """
    if not isinstance(key, tuple):
        return key
    if key and key[0] == "departure":
        return key[:-1]
    durable = []
    for part in key:
        if isinstance(part, tuple) and part and part[0] == "locomotion":
            continue
        if isinstance(part, OwnerProgressCore):
            part = replace(
                part,
                position=Position(0, 0),
                turn=0,
                decision_sequence=0,
                hp=0,
                store_type=None,
            )
        durable.append(part)
    return tuple(durable)


def claim_errand_clearance(policy, snapshot: Snapshot, owner: str, reason):
    """The durable clearance key of an errand owner on this board."""
    return claim_durable_clearance(
        policy._town_retirement_clearance_key(snapshot, owner, reason)
    )


def claim_bar_after(
    policy, snapshot: Snapshot, bar: Bar, perceived=None
) -> Bar | None:
    """``bar`` as this board leaves it, ``None`` when the board lifts it."""
    return bar_after_board(
        bar,
        turn=snapshot.turn,
        perceived=(
            perceived
            if perceived is not None
            else claim_perceived_pairs(snapshot)
        ),
        hold=DETECTED_THREAT_HOLD_MAX_GAME_TURNS,
        clearance_of=lambda errand: claim_errand_clearance(
            policy, snapshot, errand.owner.value, errand.reason
        ),
    )


def claim_bar_lift(policy, snapshot: Snapshot, register) -> None:
    """Design 3.2 / 3.3: the lift pass of this board.

    A threat-triggered bar lifts once ``DETECTED_THREAT_HOLD_MAX_GAME_TURNS``
    game turns (the existing 50-turn clock of the detected-threat choke
    release) have passed with none of its trigger monsters perceived; an
    errand bar lifts when the durable part of its owner's retirement
    clearance key differs from the one recorded when it was set.
    """
    bars = register.bars
    if not bars:
        return
    perceived = claim_perceived_pairs(snapshot)
    kept = [after for after in (claim_bar_after(policy, snapshot, bar, perceived) for bar in bars)
            if after is not None]
    if kept != list(bars):
        register.replace_bars(kept)


def claim_bar_for(policy, snapshot: Snapshot, claim, ending: str):
    """The bar a claim that ended this way earns, or ``None``.

    Design 3.2: a preemptor that does not reach its own goal is barred;
    survival is exempt (the claim's ``survival`` flag, rev 10.1 item 3).
    Design 3.3: a retired claim bars its owner for the same goal.

    * Only a Reach or Observe claim, never a survival one, and never one
      that completed.
    * The preemptors are the threat-triggered owners (rev 10.1 item 9's
      ``TRIGGER_FAMILIES``: positioning, hunt, esp-threat, combat,
      escape) -- the owners that take the decision from the ordinary ones
      because of monsters.  Their claim is barred when it ends without
      its goal: released, expired, retired, dropped by another owner or by
      its own retarget (a violation), or displaced from the stack.  Two
      endings are not the claim's own failure and bar nothing: survival
      replacing it (``survival-displaced``, design 3.4) and a floor change
      while it was suspended (``suspended-expired``).
    * Any other owner is barred by retirement only, as an errand owner;
      the bar records the durable part of its retirement clearance key
      (round 2) and lifts when that changes.
    * A Terminal claim never ends abandoned, so combat melee is never
      barred (rev 10.1 item 4, the known gap).
    """
    if claim is None or claim.survival:
        return None
    if claim.goal.kind not in (GOAL_REACH, GOAL_OBSERVE):
        return None
    if ending == CLOSED_BY_COMPLETE:
        return None
    if claim.closed_reason in (
        SURVIVAL_DISPLACED, SUSPENDED_EXPIRED
    ):
        return None
    threat = claim.owner.value in TRIGGER_FAMILIES
    perceived_now = claim_trigger_perceived(
        snapshot, claim.trigger_monsters
    )
    common = {
        "owner": claim.owner,
        "goal": claim.goal,
        "rung": rung_of_claim(
            claim.owner, claim.rung, non_discardable=claim.non_discardable
        ).name,
        "since_turn": snapshot.turn,
        "since_sequence": policy._decision_sequence,
        "claim_id": claim.claim_id,
        "ending": (
            ending if claim.closed_reason is None
            else f"{ending}:{claim.closed_reason}"
        ),
    }
    if threat:
        return Bar(
            kind=BAR_THREAT,
            triggers=tuple(claim.trigger_monsters),
            last_perceived_turn=(
                perceived_now
                if perceived_now is not None
                else claim.last_perceived_turn
            ),
            **common,
        )
    no_step = (claim.closed_reason or "").startswith("no-step:")
    if ending != CLOSED_BY_RETIRED and not no_step:
        return None
    # The retirement is this decision's (``_claim_owner_retired``), so the
    # reason the key is computed for is the decision's own.
    reason = None if no_step else (
        policy.last_reason
        if claim_family_of(policy, policy.last_reason) == claim.owner.value
        else None
    )
    return Bar(
        kind=BAR_ERRAND,
        clearance=claim_errand_clearance(
            policy, snapshot, claim.owner.value, reason
        ),
        reason=reason,
        **common,
    )


def claim_set_bars(policy, snapshot: Snapshot, register, *, dropped=None):
    """Bar the claims that ended on this decision.

    ``register.take_ended`` gives every claim a closing call ended since
    the last declaration (a producer's release, the exit's expiry, a
    retirement, a suspended claim displaced or released); ``dropped`` is
    the held claim this decision dropped without a closing.
    """
    ended = [(claim, claim.closed) for claim in register.take_ended()]
    if dropped is not None:
        ended.append((dropped, "abandoned"))
    for claim, ending in ended:
        bar = claim_bar_for(policy, snapshot, claim, ending)
        if bar is not None:
            register.set_bar(bar)


def open_execution_delegation(
    policy, parent_family: str, delegate_family: str,
    work_identity: tuple, purpose_identity: tuple,
    expected_effect: str, budget_reference: str,
) -> ExecutionDelegation:
    """Reserve a named child before invoking its executor."""
    work_identity = tuple(work_identity)
    purpose_identity = tuple(purpose_identity)
    for record in hold_delegations(policy):
        if (record.lifecycle in {"reserved", "open"}
                and record.parent_family == parent_family
                and record.delegate_family == delegate_family
                and record.work_identity == work_identity
                and record.purpose_identity == purpose_identity):
            return record
    record = ExecutionDelegation(
        None, parent_family, delegate_family, work_identity,
        purpose_identity, policy._decision_sequence, expected_effect,
        budget_reference, "reserved",
    )
    hold_delegations(policy).append(record)
    return record


def end_execution_delegation(
    policy, delegate_family: str, work_identity: tuple,
    *, completed: bool, cause: str,
) -> None:
    for record in hold_delegations(policy):
        if (record.lifecycle in {"reserved", "open"}
                and record.delegate_family == delegate_family
                and record.work_identity == tuple(work_identity)):
            record.lifecycle = "completed" if completed else "released"
            record.ending = cause


def bind_execution_delegations(policy, claim) -> None:
    """Bind same-decision reservations or cancel an unmatched opening."""
    for record in hold_delegations(policy):
        if (record.lifecycle != "reserved"
                or record.opening_decision != policy._decision_sequence):
            continue
        if claim is not None and claim.is_open and (
            claim.owner.value == record.parent_family
        ):
            record.parent_claim_id = claim.claim_id
            record.lifecycle = "open"
            record.execution = ExecutionDeclaration(
                claim.claim_id, str(record.work_identity), 1,
                record.delegate_family, "acting",
                next_step="delegate.dispatch",
                arguments=record.work_identity,
                expected_effect=record.expected_effect,
                continuation="parent.resume",
                budget_ref=record.budget_reference,
            )
        else:
            record.lifecycle = "released"
            record.ending = "exit-owner-mismatch"


def cancel_unbound_execution_delegations(policy) -> None:
    """End reservations left behind by a decision without a claim exit."""
    for record in hold_delegations(policy):
        if record.lifecycle == "reserved":
            record.lifecycle = "released"
            record.ending = "exit-not-reached"


def observe_execution_delegations(policy) -> None:
    """Retire children only when their named source resolves."""
    session = policy._equipment_transaction_session
    visit = policy._store_visit
    for record in hold_delegations(policy):
        if record.lifecycle != "open":
            continue
        work = record.work_identity
        if work[:1] == ("session",):
            same_session = (
                session is not None
                and session.target_loadout_id == work[2]
                and tuple((action.kind, action.target_slot,
                           action.item_identity)
                          for action in session.plan.actions) == work[3]
            )
            if not same_session:
                record.lifecycle = "released"
                record.ending = "session-replaced-or-ended"
            elif session.complete:
                record.lifecycle = "completed"
                record.ending = "session-effect-observed"
        elif work[:1] in {("home-operation",), ("staged-tail",)}:
            identity = tuple(work[1:])
            if visit is not None and visit.claim_operation_identity == identity:
                if visit.operation_effect_observed:
                    record.lifecycle = "completed"
                    record.ending = "home-operation-effect-observed"
            elif visit is None or visit.phase == StoreVisitPhase.CLOSED:
                record.lifecycle = "released"
                record.ending = "home-operation-ended-unobserved"
        elif work[:1] == ("route",):
            if visit is not None and visit.opened_sequence == work[1]:
                parent = standing_claim(policy)
                arrived_claim = (
                    parent is not None
                    and parent.claim_id == record.parent_claim_id
                    and parent.closed == CLOSED_BY_COMPLETE
                )
                if arrived_claim or visit.phase in {
                    StoreVisitPhase.OPERATING, StoreVisitPhase.LEAVING,
                    StoreVisitPhase.CLOSED,
                }:
                    record.lifecycle = "completed"
                    record.ending = "route-arrived"
            elif visit is None:
                record.lifecycle = "released"
                record.ending = "route-ended-unobserved"
        elif record.delegate_family == "home-scan":
            if policy._home_knowledge_current:
                record.lifecycle = "completed"
                record.ending = "catalogue-adopted"
        elif work[:1] == ("filed",):
            request = policy._home_errand.request
            if request is None or (
                request.signature, request.quantity,
                request.origin, request.purpose
            ) != work[1:]:
                record.lifecycle = "released"
                record.ending = "filed-request-replaced"
            elif not policy._home_errand.active:
                record.lifecycle = "completed" if (
                    policy._home_errand.state.value == "done"
                ) else "released"
                record.ending = f"filed-request:{policy._home_errand.state.value}"
        if record.lifecycle == "open" and record.parent_claim_id is not None:
            register = hold_claims(policy)
            live = [register.current, *register.suspended]
            if not any(
                claim is not None and claim.claim_id == record.parent_claim_id
                and claim.is_open for claim in live
            ):
                record.lifecycle = "released"
                record.ending = "parent-claim-ended"
    for record in hold_delegations(policy):
        declaration = getattr(record, "execution", None)
        if declaration is None or record.lifecycle == "open":
            continue
        state = "done" if record.lifecycle == "completed" else "releasing"
        if declaration.state != state:
            record.execution = replace(
                declaration, revision=declaration.revision + 1,
                state=state, next_step=None, arguments=(),
                evidence=record.ending if state == "done" else None,
                cause=record.ending if state == "releasing" else None,
            )


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
    if (policy._fundraising_mode == "prepare"
            and policy._diggerless_scavenge_allowed(board)):
        # No digger can be had: scavenge 1F with the carried detection (owner
        # 2026-10-23; n1-a life-454 waited in prepare for the kit).
        policy._settle_fundraising_detection(board)
        return
    if policy._fundraising_mode not in {"mine", "scavenge"}:
        cause = "fundraising-mode-inactive"
    elif (policy._fundraising_mode == "scavenge"
          and not policy._scavenge_allowed(board)):
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
    if (admission.admitted and terminal.terminal_id == "quest-claim"
            and report_waits_for_room(board, terminal.args[0])):
        admission = refused(("free_pack_slots_ready",))
    if (admission.admitted and terminal.terminal_id in TOWN_LEAVING_TERMINALS
            and holds_town(policy, board)):
        admission = refused((QUEST_REWARD_FIRST,))
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
    record.
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


# ------------------------------------------------------------------ town end
# Owner 2026-11-02 「決まった終わり方だけにする」: a town board on which no
# owner answers ends the visit in one of three declared ways, never by the
# dungeon wander fallbacks (breakout:least-visited, stuck:wander).  Owner
# 2026-11-02 「満たせなければ採掘を1サイクル行い再度トライ。条件未達の出発は
# 拒否する。」: no departure leaves with a condition unmet.  Owner 2026-11-02
# 「購入に関する問題以外は採掘せずに名前を付けて停止を採用」: only a purchase
# gap (a supply the seen shelves sell above the carried gold) is mined for.
#   depart  every ordinary departure condition holds;
#   mine    every unmet condition is a purchase gap: one mining cycle through
#           the fundraising owners (town_end_mining), then the conditions are
#           retried;
#   stop    a condition other than a purchase gap is unmet (an owner's defect
#           to fix; it names the stop even beside a purchase gap), or the
#           mining cycle cannot leave (a mining set is already open and no
#           owner answered, this visit's cycle was closed in town, the opening
#           Q34 holds fundraising, or a transfer is still in flight):
#           town:blocked:survival:<leaf> for a departure-minimum leaf
#           (policy._departure_minimum), else town:blocked:unmet:<name>.
TOWN_END_CAUSE = "no-owner-answered"
TOWN_END_STEP_OFF = "town:end-step-off"
# The minimum leaves a mining preparation cannot start over (the transfer
# gate the supply-stockout mining fallback of force_visit_departure applies).
MINING_START_TRANSFER_LEAVES = (
    "home_atomic_withdraw_clear", "store_transfer_clear", "equipment_transfer_clear")


@dataclass(frozen=True)
class TownEndMaterial:
    """The unmet departure conditions and whether a mining cycle may start."""

    unmet: tuple[str, ...]
    survival_unmet: tuple[str, ...]
    mining_set_open: bool
    mining_startable: bool
    # The unmet conditions that are purchase gaps (``purchase_gaps``).
    purchase_gaps: tuple[str, ...] = ()


class TownEnd(NamedTuple):
    kind: str
    conditions: tuple[str, ...]


def purchase_gaps(policy: Any, board: Any, unmet: tuple[str, ...]) -> tuple[str, ...]:
    """The ``unmet`` leaves whose every short supply cannot be bought this
    visit: priced above the gold, or out of stock at every supplier visited
    (owner 2026-11-02 「品切れも採掘に回す」)."""
    ledger = policy._supply_ledger(board, policy._planned_depth())

    def unbuyable(name: str) -> bool:
        if name == "identify_staff_ready":
            return policy._identify_staff_purchase_gap(board)
        short = [kind for kind in {SUPPLY_LABEL_KINDS[label]
                                   for label in LEAF_SUPPLY_LABELS.get(name, ())}
                 if kind in ledger and ledger[kind].count < ledger[kind].required_departure]
        return bool(short) and all(policy._supply_purchase_gap(board, kind) for kind in short)

    return tuple(name for name in unmet if unbuyable(name))


def gather_town_end(policy: Any, board: Any) -> TownEndMaterial:
    minimum, _destination, _depth = policy._visit_departure_minimum(board)
    unmet = gather_recall_departure(policy, board).failed
    survival_unmet = tuple(minimum["failed"])
    return TownEndMaterial(
        unmet=unmet,
        survival_unmet=survival_unmet,
        purchase_gaps=purchase_gaps(
            policy, board, tuple(dict.fromkeys((*survival_unmet, *unmet)))),
        mining_set_open=town_end_mining.mining_set_open(policy),
        mining_startable=(
            all(minimum["values"][name] is True for name in MINING_START_TRANSFER_LEAVES)
            and not policy._opening_q34_holds_fundraising(board)
            and not town_end_mining.closed_in_town(policy)))


def verdict_town_end(material: TownEndMaterial) -> TownEnd:
    """Pure: depart when nothing is unmet, mine once for purchase gaps, else stop."""
    unmet = tuple(dict.fromkeys((*material.survival_unmet, *material.unmet)))
    if not unmet:
        return TownEnd("depart", ())
    defects = tuple(name for name in unmet if name not in material.purchase_gaps)
    if defects:
        return TownEnd("stop", defects)
    if material.mining_set_open or not material.mining_startable:
        return TownEnd("stop", unmet)
    return TownEnd("mine", unmet)


def town_end_stop_reason(material: TownEndMaterial, end: TownEnd) -> str:
    """The named stop's blocked reason: the first condition the stop names."""
    first = end.conditions[0]
    if first in material.survival_unmet:
        return f"survival:{first}"
    return f"unmet:{first}"


def overweight_home_key(policy: Any, board: Any) -> str | None:
    """Home's own answer for a carried overload, before the town end.

    A mining cycle cannot shed weight, so the end's "start one mining cycle"
    never applies to an overload that Home claims.  A Home pass that ended
    without the deposit (deferred or never posted) routes Home again while
    Home's pass/approach bound remains; once that bound is used up (or Home
    refused the re-arm) the visit stops under the named
    overweight-home-unreachable (owner 2026-09-03: a deposit that really
    fails is a stop).
    """
    if (getattr(policy, "_town_liveness_claim_retired", False)
            or not policy._inventory_overweight(board)
            or not policy._town_claims_active(board)
            or "weight-overload" not in policy._town_claim_categories):
        return None
    attempted = STORE_HOME in policy._town_store_attempted
    if attempted and not policy._overweight_home_bound_exhausted():
        # Each unfulfilled pass is charged to Home's bound; the router's own
        # approach step files and begins the Home visit request.
        policy._rearm_town_store_for_new_work(STORE_HOME)
        if (STORE_HOME not in policy._town_store_attempted
                and (step := policy._shopping_approach_step(
                    board, router_plan_stop=True)) is not None
                and (key := policy._shopping_approach_key(
                    board, step, "shop:travel")) is not None):
            policy._record_shop_selector_diagnostics(board, key)
            return key
    if attempted or policy._overweight_home_bound_exhausted():
        policy._town_blocked_reason = "overweight-home-unreachable"
        return policy._town_blocked_key(board)
    return None


def town_end_key(policy: Any, board: Any) -> str:
    """End a town visit that no owner can continue (the only town fallback).

    The store router's composed procurement progress that makes progress
    (the step the progress seam used to substitute for a wander, judged by
    the same predicate), Home's answer for a carried overload
    (``overweight_home_key``) and the mining walk-in's own
    departure (a town without its entrance) still answer first.  A board
    with every condition met leaves through the established forced visit
    departure, which reads the recall or walks in exactly as the departure
    owner chooses; one with a condition unmet starts one mining cycle there.  A
    departure the visit already forced once and lost is not forced again: it
    stops under the existing departure-unsatisfiable.
    """
    progress = policy._town_procurement_progress_key(board)
    if progress is not None and progress[0] and policy._town_result_makes_progress(
            board, progress[0], reason=progress[1]):
        key, policy.last_reason = progress
        return key
    overweight = overweight_home_key(policy, board)
    if overweight is not None:
        return overweight
    walk_in = policy._mining_walk_in_return_key(board)
    if walk_in is not None:
        return walk_in
    here = board.grid_at(board.player.position)
    if board.store is None and here is not None and here.is_store:
        # A board right after a store page is still on its entrance, where
        # the town owners do not compose (Home batches, approaches).  The
        # established safe step off the entrance comes before the end.
        return policy._town_entrance_step_off_key(board, TOWN_END_STEP_OFF)
    material = gather_town_end(policy, board)
    end = verdict_town_end(material)
    if end.kind != "stop" and holds_town(policy, board):
        # The town-map quest reward holds the town (leaving terminals are
        # refused, QUEST_REWARD_FIRST) and none of its servers answered.
        policy._town_blocked_reason = QUEST_REWARD_FIRST
        return policy._town_blocked_key(board)
    if end.kind != "stop" or policy._visit_departure_committed:
        # The forced visit departure departs or starts the mining cycle by
        # the same verdict (one place for every visit-closing cause).
        key = policy.force_visit_departure(board, TOWN_END_CAUSE)
        if key is not None:
            return key
    policy._town_blocked_reason = (
        town_end_stop_reason(material, end) if end.kind == "stop"
        else "departure-unsatisfiable")
    return policy._town_blocked_key(board)
