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
                       commit: bool = False,
                       kill_descent: bool = False) -> QuestEntryMaterial:
    """Read the entry material; ``commit`` only for the entry's own call site."""
    expedition = policy._morivant_full_identify
    if expedition is not None and expedition.temporary_deposits:
        return QuestEntryMaterial(quest_id, morivant_deposits=True)
    kill_ok = (policy._kill_quest_descent_allowed(board)
               if kill_descent else True)
    if policy._opening_q34_active(board) and quest_id == 34:
        sink: list[dict] = []
        ready = policy._evaluate_fixed_quest_readiness(
            board, quest_id, require_target_town=True,
            commit=commit, telemetry_sink=sink)
        return QuestEntryMaterial(
            quest_id, q34=True, kill_descent_allowed=kill_ok,
            readiness_reason=(
                None if ready else sink[0].get("reason", "unready")))
    info = policy._quest_knowledge.get(quest_id)
    quest = board.quests.get(quest_id)
    depth = max(1, info.level if info is not None else quest.level if quest is not None else 1)
    codes: list[str] = []
    if commit:
        # The entry's own call site: the historical call and its commits.
        ready = policy._equipment_departure_ready(board, destination_depth=depth)
    else:
        ready = policy._equipment_departure_ready(
            board, destination_depth=depth, commit=False, codes=codes)
    return QuestEntryMaterial(
        quest_id, kill_descent_allowed=kill_ok,
        equipment_ready=ready, equipment_codes=tuple(codes))


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
})

_IDENTIFICATION_SERVERS = (
    Server("identification"), Server("cross-town"),
    Server("home-errand"), Server("shop-buy", "identify-staff"),
)
_SPACE_SERVERS = (Server("home-visit"), Server("shop-sell"), Server("town-plan"))
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
    "overweight": (Server("shop-sell"), Server("home-visit")),
    "not-full-hp": (Server("survival"),),
    "temporary-status": (Server("survival"),),
    "morivant-temporary-deposits": (Server("cross-town"), Server("home-visit")),
    **{code: () for code in (
        "unsupported-class", "missing-natural-stats", "skill-exp-unknown",
        "missing-monrace-knowledge", "calibration-required", "calibration-stale:*",
        "illegal-target:*", "missing-item:*", "empty-encounter-set",
        "optimization-timeout", "no-valid-loadout", "equipment-transaction-failed",
        "home-route-unavailable", "town-owner-retired", "preparation-unavailable",
        "missing-ability:*", "loadout-unconfirmed", "not-in-town", "unknown-quest",
        "strategy-force", "departure", "empty-roster", "unknown-monster",
        "three-turn-threat", "toughest-kill-time", "unready", "kill-descent",
    )},
}


def declared_code(code: str) -> str | None:
    """The declaration a returned code belongs to, or None when undeclared."""
    if code in QUEST_ENTRY_CODES:
        return code
    head, sep, _detail = code.partition(":")
    if sep and f"{head}:*" in QUEST_ENTRY_CODES:
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
        return None
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
        # A taken kill quest descends by ordinary stairs (S2: ``descent``).
        return None
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
    if terminal.terminal_id != "quest-entry":
        admission = ADMIT
    else:
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
