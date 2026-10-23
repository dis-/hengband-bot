"""Whether a town owner may take the board: its terminal's admission (ROOT-FIX S1).

Design: plans/DESIGN-town-claim-rootfix-1023.md.  A town rung declares the
last action it intends on a board (``intended_terminal``).  Each terminal kind
splits into a material read (``gather_*``), a pure verdict that returns the
admission *and* its refusal codes from the same branch (``verdict_*``), and
the commit that only the terminal's own call site performs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, NamedTuple

from hengbot.policy_constants import (
    FIXED_QUEST_REWARD_POSITIONS,
    FIXED_QUEST_TOWNS,
    MORIVANT_TOWN_ID,
    QUEST_STATUS_COMPLETED,
    QUEST_STATUS_FINISHED,
    QUEST_STATUS_REWARDED,
    QUEST_STATUS_TAKEN,
    QUEST_STATUS_UNTAKEN,
    TOWN_TRAVEL_STALL_LIMIT,
)
from hengbot.model import STORE_HOME
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
# Every declared code: the keys of REFUSAL_SERVERS (design 3.3 (1)).
TERMINAL_CODES = QUEST_ENTRY_CODES | STORE_BUY_CODES

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
    **{code: () for code in (
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
        "verified-disposal",
    })


SHADOW_RUNGS = _shadow_rungs()
# Producers ``_decide`` still calls outside the entry (S1->S2 list, design
# 3.6 item 3 / 3.7 item 3); S2 moves them behind named entries.
DIRECT_PRODUCERS_S1 = frozenset({
    "_darkness_recovery_key", "_dig_to_known_downstairs_key", "_entrance_travel_key",
    "_escape_by_stairs", "_finish_mining_floor", "_full_pack_destroy_key",
    "_fundraising_combat_equipment_key", "_opening_q34_town_key",
    "_pack_pressure_identify_key", "_read_dungeon_recall_scroll_key",
    "_recall_restock_key", "_step_toward", "_town_blocked_key",
    "_town_cancel_unsafe_recall_key", "_town_destroy_key", "_town_special_key",
    "_unprofitable_unique_disengage_key", "_warning_prompt_response_key",
    "_wield_digging_tool_key", "_wilderness_survival_key",
    "_worthless_junk_destroy_key",
})
# Parallel predicates still deciding beside the quest rung's terminal (S2).
PARALLEL_PREDICATES_S1 = frozenset({
    "_fixed_quest_prepare_return_required",
})
EXEMPT_RUNGS = frozenset({
    "_breakout_restore_weapon_key#1", "_breakout_restore_weapon_key#2",
    "_dark_locomotion_key", "_experience_potion_quaff_key", "_explore_step#1",
    "_flee_step#1", "_mana_food_loot_key", "_mana_food_survival_override_key",
    "_navigation_livelock_key", "_stat_gain_quaff_key", "_stat_restore_quaff_key",
    "_survival_gate_key#1", "_survival_gate_key#2", "_town_kill_mob_key",
})

# Every ``_town_producer_entry`` rung (checked against the source by AST).
TERMINALS: dict[str, TerminalDecl] = {
    "_fixed_quest_key#1": TerminalDecl(fixed_quest_intended_terminal, ENFORCE),
    "_fixed_quest_key#2": TerminalDecl(fixed_quest_intended_terminal, ENFORCE),
    **{name: TerminalDecl(None, SHADOW) for name in SHADOW_RUNGS},
    **{name: TerminalDecl(None, EXEMPT_SURVIVAL) for name in EXEMPT_RUNGS},
}


# --- The board verdict (design 3.5) --------------------------------------

def terminal_admission(policy: Any, board: Any, terminal: TerminalRef) -> Admission:
    """The terminal's verdict, gathered once per decision and terminal."""
    memo_key = (policy._decision_sequence, terminal)
    memo = getattr(policy, "_terminal_admission_memo", None)
    if memo is not None and memo_key in memo:
        return memo[memo_key]
    admission = (verdict_quest_work(gather_quest_work(policy, board))
                 if terminal.terminal_id in QUEST_WORK_TERMINALS else ADMIT)
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


def may_take_board(policy: Any, rung_name: str, family: str, board: Any) -> bool:
    """Whether this town rung may take the board (design 3.5).

    A refused terminal yields while a server progresses, and closes for the
    visit after TOWN_TRAVEL_STALL_LIMIT yields without progress, or at once
    when no server is live.  Closing never stops the bot.  SHADOW rungs only
    record.  Independent of --enforce-town-claims.
    """
    if family in EXEMPT_FAMILIES or board is None:
        return True
    decl = TERMINALS.get(rung_name)
    if decl is None or decl.intended_terminal is None:
        return True
    terminal = decl.intended_terminal(policy, board)
    if terminal is None:
        return True
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
