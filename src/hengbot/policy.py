from __future__ import annotations
from hengbot.item_reservation import reserved_item_command, reservation_verdict
from hengbot.item_reservation import reservation_decision, reservation_shadow, item_available

from collections import Counter, deque
import random
from dataclasses import dataclass, field, replace
from heapq import heappop, heappush
from itertools import count
from math import ceil
import json
import re
import sys
from enum import Enum
from typing import Callable, Iterable, Literal, Mapping
from pathlib import Path
from weakref import WeakKeyDictionary


@dataclass
class _DecisionOffers:
    """Transient producer proposals, consumed only by the claim exit."""

    steps: list = field(default_factory=list)
    no_steps: list = field(default_factory=list)
    waits: list = field(default_factory=list)
    sequence: int = 0

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence


_decision_offers: WeakKeyDictionary = WeakKeyDictionary()


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

    def as_dict(self) -> dict[str, object]:
        row = {name: getattr(self, name) for name in (
            "parent_claim_id", "parent_family", "delegate_family",
            "work_identity", "purpose_identity", "opening_decision",
            "expected_effect", "budget_reference", "lifecycle", "ending",
        )}
        row["execution"] = (
            self.execution.as_dict() if self.execution is not None else None
        )
        return row

from hengbot.latch_onset_capture import (
    CAPTURE_DECISIONS_AFTER_ONSET,
    assignment_provenance,
    checkpoint as latch_capture_checkpoint,
    decision_record as latch_capture_decision_record,
    write_window as write_latch_capture_window,
)

from hengbot.town_maps import TownMap
from hengbot.baseitem_knowledge import item_base_cost
from hengbot.ammo_carry import ammo_carry_plan
from hengbot.wilderness_map import WildernessMap
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.equipment_optimizer import (
    AMMUNITION_TVALS,
    FIXED_SLOTS,
    SLOT_BODY,
    SLOT_MAIN_HAND,
    SLOT_MAIN_RING,
    SLOT_SUB_HAND,
    SLOT_SUB_RING,
    TR_TELEPORT,
    Loadout,
    OwnedEquipmentCatalog,
    current_loadout,
    divable_depth,
    equipment_identity,
    equipment_move_identity,
    operational_equipment_candidate,
    optimizer_item_projection,
    random_teleport_is_suppressed,
    slot_for,
)
from hengbot.equipment_transaction_session import (
    EquipmentTransactionObservation,
    EquipmentTransactionSession,
    observe_equipment_transactions,
)
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP,
    PHASE_HOME_PREPARE,
    EquipmentTransaction,
    EquipmentTransactionPlan,
    _EQUIP_ORDER as EQUIP_ORDER,
    plan_equipment_transactions,
)
from hengbot.monrace_knowledge import NON_HP_DAMAGE_BLOW_EFFECTS, MonraceKnowledge
from hengbot.navigation import NavigationLedger
from hengbot.exploration_ledger import ExplorationLedger
from hengbot.loop_detection import LOOP_MAX_DISTINCT
from hengbot.home_disposal import HomeDisposalCandidate, HomeDisposalState
from hengbot.home_errand import (
    HomeErrandExecutor,
    HomeErrandRequest,
    HomeErrandState,
)
from hengbot.home_visit import (
    HomeVisitExecutor,
    HomeVisitKind,
    HomeVisitRequest as PhysicalHomeVisitRequest,
    HomeVisitState,
)
from hengbot.equipment_mutation import (
    EquipmentMutationExecutor,
    EquipmentMutationResult,
    EquipmentMutationState,
)
from hengbot.claim_register import (
    CLAIM_OWNER_ATTRIBUTE,
    BAR_ERRAND as CLAIM_BAR_ERRAND,
    BAR_THREAT as CLAIM_BAR_THREAT,
    CLOSED_BY_COMPLETE as CLAIM_CLOSED_BY_COMPLETE,
    CLOSED_BY_RETIRED as CLAIM_CLOSED_BY_RETIRED,
    SUSPENDED_EXPIRED as CLAIM_SUSPENDED_EXPIRED,
    Bar as ClaimBar,
    ClaimOwner,
    ClaimState,
    ExecutionDeclaration,
    ClaimRegister,
    ClaimScope,
    Goal,
    bar_after_board as claim_bar_after_board,
    declaration_mismatch as claim_declaration_mismatch,
    claims,
    observe as claim_observe,
    owner_of as claim_owner_of,
    reach as claim_reach,
    reach_monster as claim_reach_monster,
    reach_place as claim_reach_place,
    terminal as claim_terminal,
    GOAL_OBSERVE as CLAIM_GOAL_OBSERVE,
    GOAL_REACH as CLAIM_GOAL_REACH,
    GOAL_TERMINAL as CLAIM_GOAL_TERMINAL,
)
from hengbot.claim_goal_typing import (
    FLOOR_CHANGE as CLAIM_FLOOR_CHANGE,
    FLOOR_EXPECTATION as CLAIM_FLOOR_EXPECTATION,
    OBSERVE_WITHIN as CLAIM_OBSERVE_WITHIN,
    STORE_OPERATION as CLAIM_OBSERVE_STORE_OPERATION,
    STORE_ENTRY as CLAIM_OBSERVE_STORE_ENTRY,
    KNOWLEDGE as CLAIM_OBSERVE_KNOWLEDGE,
    ENTRANCE_OWNERS as CLAIM_ENTRANCE_OWNERS,
    STORE_OPERATION_OWNERS as CLAIM_STORE_OPERATION_OWNERS,
    GOAL_NOTE_NO_SLOT as CLAIM_GOAL_NOTE_NO_SLOT,
    GOAL_NOTE_OWNER_MISMATCH as CLAIM_GOAL_NOTE_OWNER_MISMATCH,
    TELEPORT_WALK_NOTE as CLAIM_TELEPORT_WALK_NOTE,
    GOAL_NOTE_ONE_STEP as CLAIM_GOAL_NOTE_ONE_STEP,
    HOME_EFFECT_OWNERS as CLAIM_HOME_EFFECT_OWNERS,
    HOME_EFFECT_SOURCES as CLAIM_HOME_EFFECT_SOURCES,
    LOOT_OWNERS as CLAIM_LOOT_OWNERS,
    EXPLORE_GOAL_OWNERS as CLAIM_EXPLORE_GOAL_OWNERS,
    MONSTER_CHASE_OWNERS as CLAIM_MONSTER_CHASE_OWNERS,
    goal_typing as claim_goal_typing,
    is_survival as claim_is_survival,
)
from hengbot.claim_ladder import (
    BAR_GATED_RUNGS as CLAIM_BAR_GATED_RUNGS,
    PREEMPTION as CLAIM_PREEMPTION,
    SURVIVAL_DISPLACED as CLAIM_SURVIVAL_DISPLACED,
    TRIGGER_FAMILIES as CLAIM_TRIGGER_FAMILIES,
    VIOLATION as CLAIM_VIOLATION,
    nests_over as claim_nests_over,
    owner_change as claim_owner_change,
    pair_scope as claim_pair_scope,
    resumable_index as claim_resumable_index,
    rung_of as claim_rung_of,
    rung_of_claim as claim_rung_of_claim,
    rung_named as claim_rung_named,
    S3_FAMILIES as CLAIM_S3_FAMILIES,
    TOWN_ERRAND_FAMILIES as CLAIM_TOWN_ERRAND_FAMILIES,
)
from hengbot.policy_types import (
    EXPECTATION_POP_SATISFIED,
    OWNER_EXPECTATION_MAX_TURNS,
    DecisionCandidate,
    DecisionContext,
    TownTravelProgress,
    StoreVisitPhase,
    StoreVisit,
    EmissionState,
    OwnerProgressCore,
    OwnerExpectation,
    OwnerExpectationRegistry,
    TownNeed,
    NeedSpec,
    TownVisitLedger,
    CrossTownShoppingExpedition,
    MorivantFullIdentifyExpedition,
    EscapeState,
    ChokeEngagementPlan,
    CrossDecisionLatch,
    SupplyStatus,
    TownErrandPlan,
    ProcurementHomeGate,
)
from hengbot.policy_constants import (
    ADJ_STR_WEIGHT_LIMIT,
    AMMO_CARRY_TARGET,
    HOME_VISIT_LIMIT,
    CALIBRATION_HOME_VISIT_LIMIT,
    DEPTH_ABILITY_REQUIREMENTS,
    DESTRUCTION_GATE_DEPTH,
    DESTRUCTION_GATE_LABEL,
    FUNDRAISING_START_GOLD,
    SPEED_GATE_DEPTH,
    SPEED_GATE_LABEL,
    SPEED_GATE_MINIMUM,
    WEAPON_BLOCK_LIMIT,
    _required_abilities_for_depth,
    required_depth_gates,
    BREEDER_STALEMATE_TURN_LIMIT,
    COMBAT_OUTCOME_WINDOW,
    COMBAT_REASON_PREFIXES,
    EMERGENCY_RETURN_COUNT,
    ENGAGEMENT_AVOID_DAMAGE_RATIO,
    FIRE_KEY,
    FIXED_QUEST_HEAL_HP_RATIO,
    FLEE_HP_RATIO,
    HEAL_HP_RATIO,
    LOW_HP_WALK_MARGIN,
    LOW_HP_WALK_RATIO,
    HEAL_POTION_SVALS,
    HUNT_HP_RATIO,
    HUNT_MAX_HOSTILES,
    HUNT_RANGE,
    QUAFF_KEY,
    RANGED_SLEEPER_MAX_DISTANCE,
    RANGED_TARGET_FAILURE_LIMIT,
    RESIST_FLAG_BY_ABILITY,
    SUMMONER_EXPOSED_NEIGHBORS,
    SUMMONER_RANGED_KILL_SHOTS,
    SWARM_COUNT,
    SWARM_LOOKAHEAD,
    THREAT_PREDICTION_MEMO_LIMIT,
    THROW_KEY,
    TORCH_THROW_MAX_DEPTH,
    TOWN_IDS_WITH_HOME,
    UNIQUE_COMBAT_HP_RESERVE_RATIO,
    ZUL_TOWN_ID,
    BARREN_FLOOR_SKIP_THRESHOLD,
    BREEDER_CONTAINMENT_WINDOW,
    DETECTED_THREAT_HOLD_MAX_GAME_TURNS,
    CURE_CRITICAL_REQUIRED_DEPTH,
    FOOD_STOCK_TARGET,
    IDENTIFY_CHARGE_FLOOR,
    LANTERN_REFILL_FUEL,
    MANA_FOOD_DEVICE_TARGET,
    OIL_TARGET,
    QUEST_STATUS_UNTAKEN,
    STAFF_IDENTIFY_MAX_COUNT,
    STAFF_IDENTIFY_MIN_CHARGES,
    STAFF_IDENTIFY_MIN_DEPTH,
    SUMMONER_CHOKE_NEIGHBORS,
    SUPPLY_STORES,
    TELEPORT_REQUIRED_DEPTH,
    TORCH_REFILL_FUEL,
    BUY_KEY,
    BUY_CONFIRM_SUFFIX,
    CARDINAL_OFFSETS,
    CHARACTER_DUMP_MACRO,
    HOME_CHARACTER_DUMP_MACRO,
    HOME_KNOWLEDGE_MACRO,
    SKILL_KNOWLEDGE_MACRO,
    CHEST_COLLECT_BUDGET,
    CHEST_DISARM_BUDGET,
    CHEST_DISARM_KEY,
    CHEST_DROP_KEY,
    CHEST_OPEN_BUDGET,
    CHEST_OPEN_KEY,
    CHEST_SEARCH_BUDGET,
    CHEST_SEARCH_KEY,
    DIRECTION_KEYS,
    DOWN_STAIRS_KEY,
    DESTROY_COMMAND,
    EMERGENCY_ESCAPE_REASONS,
    EMERGENCY_POTION_CARRY_TARGET,
    EMPTY_DIVE_LIMIT,
    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
    EQUIPMENT_TRANSACTION_FINAL_STOP_REASONS,
    ENTER_DUNGEON_MACRO,
    EAT_KEY,
    ExplorationPathOutcome,
    FOOD_MIN_SVAL,
    FOOD_TYPE_RATION,
    FOOD_TYPE_MANA,
    HEAVY_CURSE_TAG,
    HOME_PLAN_OWNED_PROCESSING_REASONS,
    INN_BUILDING_TYPE,
    INSCRIBE_KEY,
    LOW_VALUE_POTION_SVALS,
    DISPOSABLE_POTION_SVALS,
    DISPOSABLE_SCROLL_SVALS,
    FULL_IDENTIFY_DISMISS_SUFFIX,
    FUNDRAISING_GOLD_TARGET,
    FUNDRAISING_DETECTION_BASE_PRICE,
    FUNDRAISING_DIGGER_BASE_PRICE,
    FUNDRAISING_KIT_MARGIN,
    FUNDRAISING_KIT_RESERVE,
    IDENTIFY_FAIL_LIMIT,
    IDENTIFY_PURCHASE_MAX,
    DETECTION_SCROLL_BUFFER,
    IDENTIFY_PRESSURE_FREE_SLOTS,
    LEAVE_STORE_KEY,
    LANTERN_MIN_GOLD,
    LOOT_DEFER_BLOCKERS,
    LOOT_THREAT_DAMAGE_RATIO,
    DIGGER_WIELD_LIMIT,
    MINING_COMBAT_CONTACT_LIMIT,
    MINING_DETECTION_RADIUS,
    MINING_NAVIGATION_REVISIT_LIMIT,
    MINING_OSCILLATION_RETARGET_LIMIT,
    MINING_ROUTE_REVISIT_LIMIT,
    MINING_STALL_LIMIT,
    MINING_SWEEP_HARD_LIMIT,
    MINING_SWEEP_NO_PROGRESS_LIMIT,
    MINING_THREAT_FREE_LIMIT,
    MINING_RUNS_PER_SET,
    MIN_TERMINAL_FREE_PACK_SLOTS,
    MOVE_REASONS,
    NEIGHBOR_OFFSETS,
    NO_DEPTH_PROGRESS_DIVE_LIMIT,
    OVEREXTEND_EMERGENCY_MIN,
    OVEREXTEND_LOOT_MAX,
    PACK_CAPACITY,
    PICKUP_REASONS,
    HOME_BATCH_RESERVED_SLOTS,
    PLAYER_CLASS_BERSERKER,
    PROBE_LIMIT,
    RANGED_MAX_DISTANCE,
    READ_KEY,
    RECALL_ISSUE_CONFIRM_TURNS,
    RECALL_MIN_DEPTH,
    REFILL_KEY,
    SEARCH_KEY,
    SEARCH_LIMIT,
    SELL_KEY,
    SELL_ATTEMPT_LIMIT,
    STAFF_IDENTIFY_MIN_SUCCESS,
    STORE_RESTOCK_WAIT_TURNS,
    STORE_RESTOCK_REASON_NAMES,
    STORE_RESTOCK_REST_GAME_TURNS,
    STORE_ACCEPTED_TVALS,
    STORE_RETRY_TURNS,
    STORE_STUCK_LIMIT,
    STUCK_FAMILY_REASONS,
    STUCK_NEUTRAL_REASONS,
    RESTOCK_WAIT_MACRO,
    RUMOR_COST,
    RUMOR_GOLD_RESERVE,
    RUMOR_KEY,
    RUMOR_READ_KEY,
    RUMOR_READS_PER_VISIT,
    STUCK_ESCAPE_LIMIT,
    TERMINAL_NUDGE_LIMIT,
    TORCH_THROW_TARGET,
    TOWN_TRAVEL_STORE_SYMBOLS,
    TOWN_CLAIM_ADVANCING_MOVE_REASONS,
    CROSS_TOWN_SHOPPING_RESERVE,
    TOWN_CYCLE_IGNORED_REASONS,
    TOWN_CYCLE_MAX_DISTINCT,
    TOWN_CYCLE_WINDOW,
    TOWN_FAST_TRAVEL_MAX_POSITIONS,
    TOWN_FAST_TRAVEL_MIN_ROWS,
    TOWN_FAST_TRAVEL_WINDOW,
    TOWN_NO_PROGRESS_LIMIT,
    TOWN_STOP_PASS_LIMIT,
    TOWN_TELEPORT_BUILDING_TYPES,
    TOWN_TRAVEL_MIN_DISTANCE,
    TOWN_CYCLE_BREAK_LIMIT,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
    TOWN_WANDER_LIMIT,
    TOWN_WANDER_REASONS,
    STAIR_OBSERVATION_WAIT_LIMIT,
    SHOP_APPROACH_STUCK_LIMIT,
    ALTER_KEY,
    OPEN_KEY,
    VISIT_PENALTY,
    BACKTRACK_PENALTY,
    DOOR_OPEN_LIMIT,
    RUBBLE_DIG_LIMIT,
    RUBBLE_REJECT_LIMIT,
    NAV_ESCAPE_STEP_LIMIT,
    STUCK_WINDOW,
    EXTENDED_STUCK_WINDOW,
    TUNNEL_KEY,
    UP_STAIRS_KEY,
    UNUSED_DIVE_LIMIT,
    USE_STAFF_KEY,
    WAIT_KEY,
    WALK_OUT_MAX_DEPTH,
    SPEED_ENERGY_90,
    ZAP_ROD_KEY,
)
from hengbot.policy_constants import (
    AIM_WAND_KEY,
    EQUIPMENT_SLOT_KEY,
    EXECUTABLE_QUEST_STRATEGY_IDS,
    FIXED_QUEST_ALLOWLIST,
    FIXED_QUEST_ALWAYS_OFFERED,
    FIXED_QUEST_CURE_CRITICAL_HP,
    FIXED_QUEST_MAX_DAMAGE_RATIO,
    FIXED_QUEST_REWARD_POSITIONS,
    FIXED_QUEST_SIMULTANEOUS_MONSTERS,
    FIXED_QUEST_THREAT_TURNS,
    FIXED_QUEST_TOUGHEST_KILL_TURNS,
    FIXED_QUEST_TOWNS,
    HEALING_POTION_HP,
    MIN_FREE_PACK_SLOTS,
    MORIVANT_FULL_IDENTIFY_COST,
    MORIVANT_FULL_IDENTIFY_THRESHOLD,
    MORIVANT_LIBRARY_BUILDING_TYPE,
    MORIVANT_TOWN_ID,
    PANIC_HP_RATIO,
    Q2_BLUE_CONFIRM_POSITION,
    Q2_BREACH_ATTEMPT_LIMIT,
    Q2_BREACH_CORRIDOR,
    Q2_BREACH_MIN_DIGGING,
    Q2_BREACH_POSITION,
    Q2_BREACH_STANDING,
    Q2_BREEDER_RACES,
    Q2_POST_BLUE_SEQUENCE,
    Q2_RESIDUAL_SWEEP_RACES,
    Q2_WERERAT_RACE,
    Q2_WHITE_CROCODILE_RACE,
    QUEST_AMMO_TVALS,
    QUEST_ID_THIEF,
    QUEST_SCROLL_SVALS,
    QUEST_STATUS_COMPLETED,
    QUEST_STATUS_FINISHED,
    QUEST_STATUS_REWARDED,
    QUEST_STATUS_TAKEN,
    REST_MACRO,
    SPEED_POTION_BONUS,
    TOWN_TELEPORT_COST,
    UNIQUE_COMBAT_MAX_ATTACKS,
    WIN_QUEST_IDS,
)
from hengbot.town_arbiter import (
    UNREGISTERED_FAMILY,
    TownArbiterMixin,
    _new_town_turn_arbiter,
    reason_owner_family,
)
from hengbot.policy_calibration import CalibrationMixin
from hengbot.policy_identification import IdentificationMixin
from hengbot.policy_fundraising import (
    FundraisingMixin, FundraisingPurpose, FundraisingPurposeRecord,
)
from hengbot.policy_supply import SupplyMixin
from hengbot.policy_helpers import PolicyHelpersMixin
from hengbot.quest_knowledge import (
    QUEST_FLAG_ONCE,
    QUEST_FLAG_SILENT,
    QUEST_TYPE_KILL_LEVEL,
    QUEST_TYPE_KILL_NUMBER,
    QUEST_TYPE_RANDOM,
    QuestInfo,
)
from hengbot.quest_strategies import StrategyProfile
from hengbot.quest_navigator import PICKUP_KEY, QuestFloorNavigator
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext,
    aggregate_ranged_damage_percentile,
    ability_selection_probabilities,
    cause_damage_percentile,
    evaluate_ability_effect,
    expected_ability_hp_damage,
    maximum_ability_hp_damage,
)
from hengbot.projection_path import projection_path
from hengbot.protocol import ProtocolSchemaError
from hengbot.warrior_optimization import (
    INCREMENTAL_SEARCH_CATALOG_THRESHOLD,
    CharacterCalibration,
    ConfirmedLoadoutRecord,
    WarriorEvaluatorCache,
    WarriorOptimizationPreparation,
    calibrate_character_constants,
    character_intrinsic_flags,
    confirmed_loadout_record,
    load_character_calibration,
    load_confirmed_loadout,
    prepare_warrior_optimization,
    save_character_calibration,
    save_confirmed_loadout,
    warrior_optimizer_input_key,
    warrior_optimizer_knowledge_key,
    weapon_expected_dps,
    # warrior_optimization owns the per-source supersede rule; policy consumes it.
    _effective_intrinsic_abilities,
)
from hengbot.warrior_loadout_evaluator import (
    LAUNCHER_PROPERTIES,
    STORE_AMMO_AVERAGE_DAMAGE,
)
from hengbot.warrior_loadout_search import disposable_dominated_item_ids
from hengbot.warrior_equipment_evaluator import melee_hit_chance
from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_CHAMELEON_CAVE,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_MAGIC,
    STORE_TEMPLE,
    STORE_WEAPON,
    SV_LITE_LANTERN,
    SV_LITE_FEANOR,
    SV_LITE_TORCH,
    SV_POTION_SLEEP,
    SV_POTION_SPEED,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_HEALING,
    SV_POTION_RESIST_COLD,
    SV_SCROLL_PHASE_DOOR,
    SV_SCROLL_TELEPORT,
    RESTORE_POTION_SVAL_BY_STAT,
    STAT_GAIN_POTION_SVALS,
    SV_ROD_IDENTIFY,
    SV_ROD_LITE,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_DETECT_INVISIBLE,
    SV_SCROLL_DETECT_TRAP,
    SV_SCROLL_DETECT_ITEM,
    SV_SCROLL_DETECT_DOOR,
    SV_SCROLL_LIGHT,
    SV_SCROLL_BLESSING,
    SV_SCROLL_HOLY_CHANT,
    SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE,
    SV_SCROLL_STAR_REMOVE_CURSE,
    SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
    SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
    SV_SCROLL_STAR_DESTRUCTION,
    SV_SCROLL_WORD_OF_RECALL,
    SV_STAFF_DESTRUCTION,
    SV_STAFF_IDENTIFY,
    SV_WAND_STONE_TO_MUD,
    SV_WAND_TELEPORT_AWAY,
    SV_HAFTED_WIZSTAFF,
    SPELLBOOK_TVALS,
    TVAL_AMULET,
    TVAL_ARROW,
    TVAL_BOLT,
    TVAL_BOW,
    TVAL_BOOTS,
    TVAL_CROWN,
    TVAL_CLOAK,
    TVAL_SOFT_ARMOR,
    TVAL_HARD_ARMOR,
    TVAL_DRAG_ARMOR,
    TVAL_GLOVES,
    TVAL_HELM,
    TVAL_SHIELD,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_LIFE_BOOK,
    TVAL_CRUSADE_BOOK,
    TVAL_HISSATSU_BOOK,
    TVAL_POTION,
    TVAL_RING,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_SHOT,
    TVAL_STAFF,
    TVAL_WAND,
    StoreState,
    TVAL_HAFTED,
    TVAL_POLEARM,
    TVAL_SWORD,
    TVAL_WHISTLE,
    TVAL_SPIKE,
    TVAL_FIGURINE,
    TVAL_STATUE,
    TVAL_CAPTURE,
    TVAL_CARD,
    TVAL_BOTTLE,
    TVAL_CHEST,
    GridState,
    InventoryItem,
    MonsterState,
    Position,
    QuestState,
    Snapshot,
    StoreItem,
    item_requires_full_identification,
)


def _persistent_grid_signature(grid: GridState) -> tuple:
    """All terrain/player-memory fields, deliberately excluding transients."""
    return (
        grid.position,
        grid.known,
        grid.passable,
        grid.wall,
        grid.has_down_stairs,
        grid.has_up_stairs,
        grid.unsafe,
        grid.terrain_id,
        grid.is_closed_door,
        grid.is_door,
        grid.trap,
        grid.has_entrance,
        grid.store_number,
        grid.can_dig,
        grid.tunnel,
        grid.permanent,
        grid.has_gold,
        grid.entrance_dungeon_id,
        grid.building_type,
        grid.has_quest_enter,
        grid.has_quest_exit,
        grid.quest_id,
        grid.building_special,
        grid.allows_los,
        grid.marked,
        grid.glow,
        grid.mnlt,
        grid.mndk,
        grid.visibility_flags_present,
    )

# ``-o`` forces Hengband's original command set. In its travel-point selector,
# the displayed store landmarks 1-8 are selected with their shifted number-row
# symbols (roguelike mode uses the bare digits instead).
# Travel-selector macro for the surface walk to the dungeon entrance: ` opens
# travel, n declines a possible "continue previous travel?" prompt (point
# selection ignores it otherwise), > jumps the cursor to the nearest known
# STAIRS+DOWN_STAIRS grid — the wilderness dungeon entrance carries BOTH flags
# (TerrainDefinitions ENTRANCE, id 193) — and . confirms. The bot never accepts
# castle quests, so > cannot land on a quest entrance; the user allows this
# shortcut exactly on that condition.
# Escape first clears a pending -more-/prompt and is a no-op at the command loop,
# ensuring the following backtick reaches the travel selector.
ENTRANCE_TRAVEL_MACRO = "\x1b`n>."
# Adjacent-ish goals are cheaper on foot than a travel round-trip.
# Consecutive travel issues without getting closer before giving the goal back
# to BFS walking (an unknown approach makes the game reject the route).
# Positive page-state observations after a posted Home SPACE.
# store-key-processor.cpp:90-106: when the whole stock fits one page, SPACE
# prints this message and does NOT redraw — the observation is current and the
# page really is the entire inventory (a recurrence is a legitimate wrap).
HOME_PAGE_SINGLE_PAGE_MESSAGES = (
    "これで全部です。",
    "Entire inventory is shown.",
)
STORE_INVEN_MAX = 24
POWERUP_HOME_MULTIPLIER = 10
MIN_STORE_PAGE_SIZE = 12
# Derived from store.cpp/store.h and cmd-store.cpp, not a tuning cap: Home has
# 24 slots, or 24 * 10 with powerup_home, and at least 12 displayed slots.
# Twenty pages cover every reachable Home; one more SPACE guarantees a wrap.
# Store entry calls disturb(), and the live flush_disturb option makes the
# first store inkey() discard every character queued after the entry key.
# Enter separately; subsequent decisions advance one observed page at a time.
# The exported message text carries at most two decorations, both fixed in
# source: a save-persisted cheat_turn option prepends `T:<turn> - `
# (display-messages.cpp:289-291, format "T:%d - %s"; registered at
# option-types-table.cpp:368 and restored from the save at
# option-loader.cpp:58, so "assume it is off" is not an available invariant),
# and a repeated message appends ` <x<count>>` (display-messages.cpp:107-110).
# Matching therefore happens on the NORMALIZED body — decorations stripped,
# then an exact match for the single-page message and a prefix match for the
# version banner.
_HOME_PAGE_MESSAGE_DECORATION = re.compile(
    r"^(?:T:\d+ - )?(?P<body>.*?)(?: <x\d+>)?$",
    re.DOTALL,
)


def home_page_message_body(message: str) -> str:
    """Strip the two registered game message decorations before matching."""
    match = _HOME_PAGE_MESSAGE_DECORATION.match(message)
    return match.group("body") if match else message


def staged_prompt_chain_matches(chain: dict, key) -> bool:
    """Whether ``key`` is the command a staged prompt chain gates.

    The sender releases a chain's tail at the gate offsets it staged, so the
    emitted key must keep the staged command byte and length; only a read
    rebind (``validate_read_key``) may change the selected letters.
    """
    chain_key = str(chain.get("key", ""))
    key = str(key) if key is not None else ""
    return bool(key and chain_key) and key[0] == chain_key[0] and len(key) == len(
        chain_key
    )


# A TR_WARNING item's forecast (object/warning.cpp:504-516, damage over half of
# current HP) and its trap forecast (:528-538) both end in the same
# input_check(「本当にこのまま進むか？」/"Really want to go ahead? ").
# input_check appends "[y/n]" to the prompt before message_add records it
# (core/asking-player.cpp:226-248), so the exported message carries that
# suffix; recognition therefore matches the prompt as a PREFIX of the
# normalized body (both registered decorations stripped first).  Matching the
# prompt covers both call sites — the handler answers the prompt, not one
# forecast.
WARNING_PROMPT_MESSAGE_PREFIXES = (
    "本当にこのまま進むか？",
    "Really want to go ahead?",
)

# Word of Recall asks this only when the current floor is shallower than the
# dungeon's saved recall destination. Refusing preserves the deepest floor;
# the executor owns this question only for the return:recall operation.
RECALL_DEPTH_PROMPT_MESSAGE_PREFIXES = (
    "ここは最深到達階より浅い階です。この階に戻って来ますか？",
    "Reset recall depth?",
)

# それならば一旦多少の非効率は許容する。訪問回数の最大値を300回まで緩和することを許可するのでまずは処理を
# 完遂させること。効率化はその後。
# Cash retained after buying every departure-blocking shortage on a cross-town
# shopping expedition, covering the user-specified round trip.


# R300 costs about 300 player turns at roughly 10 game turns per rest.
# Use that measured game-turn cost when crediting one rest command; the stock
# turnover interval is a separate clock and is not a valid charge clamp.
# A store visited once and found to have nothing to buy/sell latches into
# _town_store_attempted for the rest of the town stay (see that field), which
# is normally fine — the fresh-town reset re-arms it on the next visit. But a
# town stay that never departs (a stuck/blocked bot pacing for hours, as in the
# 2026-07-15 incident) never gets that reset, so a store latched early while
# genuinely out of stock stays skipped even after it would have restocked and
# supplies keep draining (oil, teleport scrolls...) with no re-attempt ever
# firing. Expire each latch after this many GAME turns (not decisions) so an
# abnormally long town stay still periodically re-checks every store. At
# normal speed a town step is roughly 100 game turns, so this is about 50
# moves between retries per store — cheap insurance against supplies quietly
# running out forever, and far looser than STORE_RESTOCK_WAIT_TURNS's
# deliberate short wait for a store the bot is actively depending on.
# Oberon and the Serpent are factual game constants: fixed WIN quests that are
# TAKEN from birth and are never completable by the bot's fixed-quest machinery.
# This is executor capability, not strategy approval or a tuning threshold.
# These quest offers are unconditional once their quest state is exported.
# Other fixed quests are conditional chains and only become candidates when a
# live town building actually advertises them.
# Building 0 is the Outpost inn/castle.  The ordinary inns in Telmora,
# Morivant, and Angwil are building 4.  Zul's tavern does not offer town
# teleportation, so it is intentionally absent.
# The static town maps 01-04 each contain exactly one Home (`8`).  Zul's
# 05_Zul map contains none.  A negative runtime route is not evidence that a
# Home-bearing town lacks a Home; it is a visible bot defect instead.
# lib/edit/towns/03_Morivant.txt advertises building action 1 for 1300 gold;
# every eligible Inn advertises action 42 for 500.  Building service prices are
# not present in bot JSON, so these factual data-file values cannot be learned
# from a runtime snapshot.
# Fixed quest maps are one-shot commitments.  Quest 25 and 28 are open rooms,
# so model the eight most dangerous placed monsters occupying every adjacent
# grid. Acceptance requires operational three-turn damage to be strictly below
# half the HP available from full health plus the healing that can actually be
# quaffed during that window, and enough AC-100 melee output to kill the
# toughest placed monster within ten player turns.
# A closed door does not open just by walking into it (that depends on game
# options and fails on locked doors); explicitly open it with 'o' + direction.
# Descending a wilderness/town dungeon *entrance*: the FIRST time you enter a
# given dungeon the game msg_print()s an entrance line ("ここには〜の入り口があ
# ります") — a '-more-' prompt — BEFORE the "本当にこのダンジョンに入りますか？"
# [y/n] check (see cmd-move.cpp:272). So we must dismiss the -more- (Return) and
# THEN confirm (y): a bare ">y" has its 'y' eaten by the -more-, leaving the
# [y/n] unanswered until the stall-nudge Escape cancels it — an infinite
# >y/<esc> loop at the entrance. Return dismisses the -more- (Escape would answer
# the [y/n] as "no"); on later entrances there is no message and the extra keys
# are harmless no-ops.
# Write a character dump before diving, for the human to inspect the full sheet
# (stats, resistances, equipment). C = character screen, f = file dump, Return
# accepts the default filename, y confirms an overwrite, and two Escapes return to
# the command loop (so the next snapshot is emitted). Spare Escapes are harmless.
# Rest until HP/SP recover or we are disturbed. The rest prompt defaults to "&"
# (rest as needed); we type it explicitly and confirm with Return.

# Exploration
# Extra cost for stepping straight back to where we just came from, so open
# areas are swept in one direction instead of oscillating between two tiles.
# The pathfinder only walks KNOWN tiles, so it can circle frontiers whose unknown
# side never comes into view. When stuck, step directly into an adjacent unknown
# tile to reveal it; give up on a direction after this many bumps (it is a wall).
# 'o' attempts to open (and pick the lock of) a closed door. After three tries
# it is treated as impassable (jammed / too hard) and routed around.
# BOT_PLAY is launched with ``-o``, so tunnelling is always the raw original
# command. Prefixing it with the keymap-bypass command can leave the Windows
# build waiting at an intermediate command prompt instead of consuming the
# direction key.
# 's' searches the adjacent tiles for SECRET doors/passages, which are invisible
# until found. When stuck at a dead-end we search this many times per tile before
# giving up on it — a hidden corridor often caps an otherwise-unreachable frontier.
# A floor tile counts as a frontier because a neighbour is unknown. Some
# neighbours are *unrevealable* from that tile — a dark-room floor cell shows only
# while you stand next to it (is_view) and is not remembered (is_mark) once you
# step away, so the frontier flickers back and the bot is drawn to the same tile
# forever (observed: 776 visits oscillating between two cells while a real door
# frontier sat unreached). After standing on a would-be frontier this many times
# without it ceasing to be one, treat it as exhausted (not a frontier).
FRONTIER_EXHAUST_VISITS = 8

# Combat / survival thresholds
# ...but the bot flees it only when those hostiles could carve off a big share of
# HP over the next few turns. Judging by predicted damage (not a raw count or
# sleep state) stops a full-HP character fleeing weak sleepers: a low-stealth
# character wakes them at once anyway, and _predicted_damage already assumes they
# attack, so "asleep" is deliberately not a factor.
SWARM_FLEE_DAMAGE_RATIO = 0.6  # flee a swarm only if it could take this share of HP
# Consecutive "stuck" turns on one dungeon floor (searching for secret ways,
# breaking out of a visited pocket, or plain wandering — never actually exploring
# a frontier or fighting) before we give up and Word-of-Recall out. A level whose
# down-stairs are walled off otherwise traps the bot forever: supplies stay fine,
# so the town-return never fires, and it just searches/wanders in place.
# Floor upkeep that a stuck bot still does between searches (relight, heal, eat).
# These must neither grow the stuck streak nor RESET it — otherwise a relight
# every few turns keeps the streak pinned near zero and the escape never fires.
# Only genuine progress (exploring a frontier, fighting, descending) resets it.
# Mode-independent navigation invariant (R1 redesign): a dungeon decision makes
# "progress" only when it grows remembered map coverage, improves a committed
# navigation target's best distance, changes gold/pack/equipment, fights, or
# waits out a recall. This many consecutive decisions with NONE of those means
# every navigation mode is livelocked no matter how varied its reasons look —
# the incident this replaces cycled three modes over 41 cells for 1600+
# decisions while each individual detector saw "progress". Big enough that a
# legitimate secret-door hunt (SEARCH_LIMIT per tile across a handful of
# dead-ends) finishes well under it. Accepted tradeoff: a pathological
# 400+-decision stretch of pure backtracking (an extreme serpentine return
# over fully-visited ground) ends in a VISIBLE stop rather than a silent
# loop — per the operating rule, stopping for investigation beats guessing.
NAV_NO_PROGRESS_LIMIT = 400
# Once the invariant trips, the escape route (recall/up-stairs) gets its own
# bounded budget so a broken escape cannot itself loop forever: past it, the
# policy reports livelock:exhausted and the CLI stops the bot visibly.
# A fight may legitimately hold one area for a while, but combat is not progress
# forever merely because attack keys keep being issued.  Retain one extra sample
# so a full window has both endpoints to compare.
# Experience gain is not proof that a breeder swarm is being contained: a
# kill-and-reproduce equilibrium can award XP forever without clearing a route.
# This MUST stay below cli's MULTIPLIER_COMBAT_LOOP_WINDOW (80): a full-HP
# character surrounded by a harmless multiplying swarm (e.g. giant white lice)
# never trips the damage-gated swarm flee, so the graceful "disengage to town"
# below has to arm before the position loop guard hard-stops the bot.  At 120 it
# never did, and the multiplier-combat loop guard stopped the bot instead.
WEAK_BREEDER_MAX_DAMAGE_RATIO = 0.05
FRUITLESS_DISENGAGE_LIMIT = 100
# WAIT terminals which are deliberately allowed to outlive the CLI's positional
# guard.  Each entry names an existing policy bound; cli imports this registry
# rather than maintaining a broader reason-prefix exemption.
ESCAPE_BUDGETED_WAIT_LIMITS = {
    "status-threat:wait": NAV_ESCAPE_STEP_LIMIT,
    "flee:wait": NAV_ESCAPE_STEP_LIMIT,
    "return:wait": NAV_ESCAPE_STEP_LIMIT,
    "combat:disengage-wait": FRUITLESS_DISENGAGE_LIMIT,
    "emergency:wait": NAV_ESCAPE_STEP_LIMIT,
    "town:blocked:repetition": NAV_ESCAPE_STEP_LIMIT,
}
# Town circuit breaker: unlike a dungeon floor, town positions vary across most of
# the map, so cli's position-based loop guard never fires on wandering alone — a
# live logic deadlock (Home identification stuck behind an equipment-optimizer
# blocker) paced town for 2 real hours (11,617 stuck:wander decisions) before
# anyone noticed. Count consecutive in-town decisions that are non-productive
# wandering; TOWN_WANDER_LIMIT is several times larger than any legitimate town
# traverse (so real shopping/travel never trips it) yet small enough to bound a
# future deadlock to roughly a minute of wall-clock play instead of hours.

# Generic town-repetition detector (user directive: auto-detect and repair this
# CLASS). Every observed shape — Home-door bounce, store-to-store travel
# ping-pong — is a short cycle of (reason, position) signatures with no
# progress, and each one evaded the cell-based loop guard (store snapshots
# reset it; travel keeps the position changing). A window of town decisions
# whose signatures collapse to a handful of distinct values while gold, pack
# and equipment all stay unchanged IS such a cycle, whatever subsystem drives
# it. Waits are excluded (deliberate stationary states), and any progress
# resets the window.
# Native town travel is comparatively slow, so the generic 48-decision window
# can represent many minutes.  A route that emits at least eight travel rows
# while collapsing to three cells is not a legitimate cross-town traverse.
# d309c2a lowered this fallback only to beat cli.py's 40-decision cell guard in
# town.  1e46bb5 removed that guard from town entirely, so that race no longer
# exists and the tighter bound only adds false positives: on a first visit,
# native travel may reject an unknown approach and leave a long per-tile walking
# leg (roughly one recorded locomotion decision per tile) while the progress
# marker remains frozen until the first transaction.  The original 96-decision
# bound is safe for every known legitimate shape: Home scans are page-bounded,
# and purchases reset the marker per transaction.
# Over-extension: this many dives into the recall-target dungeon that collect ZERO
# loot means it is too deep for the character (a clvl-24 warrior in Angband, whose
# recommended level is 30, grabs one trivial item, burns escape scrolls on repeated
# emergency teleports, and returns when its kit runs low). After a run of such dives
# recall into a level-appropriate dungeon it has already unlocked.
#
# A dive is judged "over-extended" (not merely unlucky) when it collected almost
# nothing AND the character had to bail out under fire more than once — the escape
# spam is what drains the kit, so counting escapes captures the kit-depletion the
# user pointed to. A quiet zero-loot dive (just found nothing, no danger) does NOT
# count; an over-deep dive is defined by the danger, not the empty pack alone.

# Authoritative depth-requirement table (bot-client/AGENTS.md "Authoritative depth
# requirements"). Each (min_depth, max_depth, required abilities) band lists the
# mandatory resistances/abilities to survive that depth; the bot never descends into
# a band whose abilities the character lacks. Keys match the emitter's player.abilities.
# "*Destruction*" and the 81F speed gate are handled outside this resistance table.

# tr_type flag index (object-enchant/tr-types.h) that grants each ability. An item's
# known_flags carries these indices, so an item confers ability X exactly when
# RESIST_FLAG_BY_ABILITY[X] is among its known_flags — used to prefer resistance gear
# for a depth requirement the character is missing.

# object-enchant/tr-types.h. This disables the emergency teleport scrolls that
# the survival policy relies on, so it is disqualifying on exploration gear.
TR_NO_TELE = 68




# AGENTS.md's two mandatory gates that are NOT player.abilities flags: from 50F a
# usable *Destruction* method (scroll or charged staff in the pack), and from 81F
# speed +25. They join the resistance table in every depth-requirement check.




# threat_prediction memo entries kept before the (per-snapshot) cache is reset;
# a decision needs at most a few (turns=1 and turns=3 variants).

# Value-keyed aggregate-p95 results kept ACROSS decisions — a dive meets at most
# a few hundred distinct (race, actions, distance, player-profile) combinations,
# and every input is part of the key, so entries can never go stale.
AGGREGATE_RANGED_CACHE_LIMIT = 4096
# Bailing out under fire: teleport/phase away, recall out, or run for the stairs.
# Being forced into these repeatedly is the signature of a too-deep floor.

# Descending / healing. Dive only when healthy, and recover between fights so we
# are never caught deep and weak (the classic too-fast-dive death).
DESCEND_MIN_HP_RATIO = 0.85  # only take downstairs at/above this HP
REST_TARGET_HP_RATIO = 0.90  # rest to recover up to here when no enemy is in sight
REST_CAP = 25  # bound consecutive rest commands as a safety valve

# Hunting (opportunistic XP while no downstairs is known)

# Anti-stuck
# A six-cell frontier cycle needs a longer sample than the tight 2-4 cell
# detector so one ordinary pass through a small room is not treated as stuck.
# If a pathing move is re-issued this many times without the player actually
# moving, treat it as a rejected move (e.g. a locked door) and break out.
LIVELOCK_LIMIT = 4
# Reasons whose keys are ordinary "walk toward something" moves; only these are
# watched for livelock (melee/flee/rest deliberately keep us in place). "pickup"
# is included so a stuck ``g`` on an un-grabbable pile forces us to move on.

# Consumable use (item command + inventory letter, sent as a macro).
# Ranged attack: prefer fire (f) / throw (v) + item slot + a direction digit.
# get_aim_dir resolves a direction key immediately with no targeting UI, so
# the bot only shoots RAY-ALIGNED targets (8 directions) it can verify a clear
# known path to — no target_set cursor session, snapshot-safe as a macro.
# Fire range is 13+tmul/80 (shoot.cpp:531) ≈ 15 for a sling; the bot stays
# conservative because every ray tile must be KNOWN passable to fire at all.
# Don't wake distant sleepers with a shot — approach quietly instead (the
# existing hunt path); close sleepers get softened before they act anyway.
# A full launcher stack is operationally useful and user-approved, but duplicate
# stacks beyond it must not impose an inventory-speed penalty.
# Different enchantments do not combine, so floor recovery can otherwise turn
# one 99-shot supply target into most of the pack.  Keep two dense stacks; Home
# owns every additional compatible stack.
# The standard Hengband main term displays 12 store entries per page
# (src/store/cmd-store.cpp MIN_STOCK). Bot JSON exposes the complete stock with
# absolute letters, while the store command prompt selects within this page.
# User directive (2026-07-16): potions are never thrown (weak), and on early
# floors the bot actively throws CHEAP TORCHES instead — a thrown light
# survives 50% (object-broken.cpp) and costs ~1g at the General Store, so it
# is near-free ranged pressure while the launcher has no matching ammo.
# Speed and Healing are valuable emergency supplies, but carrying an unlimited
# Black Market stockpile can impose a speed penalty.  Keep a useful field stock
# while shelving everything above the user-approved per-kind limit at Home.
# Source: player-status-table.cpp adj_str_wgt.  Values become internal
# decipounds after multiplication by 50 in calc_weight_limit().
# Chest processing (user-specified procedure): drop the carried chest, step
# to an adjacent tile, `s` to discover its trap (search() marks adjacent
# trapped chests known — player-move.cpp discover_hidden_things), `D` to
# disarm, `o` to open (repeats pick a lock). The bot cannot OBSERVE the
# "trap discovered" message through snapshots, so each phase runs a fixed
# budget instead: search chances are skill_srh% per press, disarm may fail,
# a locked chest needs several picks.
UNINSCRIBE_KEY = "}"
# BOT_PLAY is launched with -o, which forces Hengband's original command set.
# Keep item commands aligned with that contract: use staff = u, zap rod = z,
# destroy = k, and numeric direction keys.
# The "0<count>" prefix sets command_arg, putting
# select_destroying_item in force mode (skipping the "Really destroy?" prompt —
# whose y/n answers can otherwise leak) and is reused by input_quantity (no
# quantity prompt), so the whole stack is destroyed with no stray keys leaking.
# Consecutive destroy attempts that leave the pack unchanged before we give up on
# an item and mark it undestroyable (e.g. an artifact the game refuses to break).
DESTROY_FAIL_LIMIT = 3
# Hengband's normal-light dim warning threshold
# (src/object/lite-processor.cpp:73).

# Shopping. In a store, 'p' is the (rewritten-to-'g') Purchase command. It
# consumes an item letter, a quantity plus Return for stacked wares, and one
# [Y/n] confirmation key. DEFAULT_Y makes Return itself the affirmative key.
# Leaving the store is Escape. See the store-subsystem notes.
# A one-count ware skips input_quantity, so only its confirmation Return follows.
# Live economy records show that stacked purchases consume the quantity Return
# and one DEFAULT_Y confirmation Return; no intervening -more- is present.
STACKED_BUY_CONFIRM_SUFFIX = "1\r\r"
# *Identify* always opens screen_object(); equipment with many attributes can
# add several ``-- more --`` pages before the final continue prompt.  Escape
# closes each page and is harmless after control returns to the command loop.
SELL_CONFIRM_SUFFIX = "\r"
# Mirrors store/service-checker.cpp's per-store tval switches.  The policy's
# sale paths only need these ordinary, unconditional cases; the Temple's
# blessed-weapon/figurine exceptions and the General/Magic special svals are
# deliberately not claimed from tval alone.
# Fuel flasks to stock for the lantern. We only walk to the shop if we have at
# least a little gold; true affordability is re-checked against the live price in
# the store (and if we can't afford it there we give up rather than loop).
# If the same purchase is re-issued this many times with no effect (gold
# unchanged, item still on the shelf — a buy that never registers), give up and
# leave the store. The store re-emits a snapshot every loop with no loop-detector
# or stall exit, so without this the bot would hammer the buy macro forever.
# Posted equipment commands get the reviewed store no-progress budget.  The
# observation count remains diagnostic: exhaustion releases the session as a
# visible failure and never substitutes for the action's physical postcondition.
# Oscillating store-approach turns (while _is_oscillating) tolerated before giving
# up an unreachable store and diving with what we have. Above STUCK_WINDOW so a
# reachable store one tile on is still pursued; below the cli loop guard's window
# so we abandon BEFORE it stops the bot.
# Backstop only: the digging-tool wield normally takes at once (answering the
# "Equip which hand?" prompt when both hands are full). If it still keeps not taking
# this many times, the main weapon is genuinely stuck/cursed — abandon the mining run.
# Two adjacent observations distinguish persisted contact from one transient
# redraw without spending seven rounds fighting with mining tools. No existing
# 2--3 decision hysteresis constant describes this combat transition.
# Eight quiet observations cover four complete two-contact combat windows.  This
# is deliberately a mining readiness window, independent of terminal recovery.
# Consecutive turns spent tunnelling toward a walled-off vein before giving up on it
# and ascending. Digging holds the player on one tile, so `fundraise:tunnel-to-treasure`
# is EXEMPT from the harness loop guard (cli.py STATIONARY_EXEMPT_REASONS) — this leash, not the
# 40-decision window, is what bounds a dig, so it can run long: a vein 3-4 rock tiles deep
# needs ~30 turns per granite tile. Reaching a vein (mine-treasure) resets it, so a
# productive floor mines indefinitely; only an unreachably-deep vein burns the full leash.
# Never spends a Teleport/Recall scroll. (Pure oscillation with nothing diggable gives up
# at once instead — that path is NOT harness-exempt, so it must not linger.)
# Decision-log trip analysis (2026-07-28) found a sharp yield cliff:
# mining.detected_total ≤10 → 27–142 g/min; detected_total ≥12 → 2,100–6,000 g/min.
# Target selection may churn across a large Treasure Detection result and clear
# the per-target route counter.  This floor-route counter survives retargeting so
# a two-cell approach/explore bounce still terminates before the harness guard.

# Consecutive in-town decisions tolerated with only a digging tool (pickaxe) wielded
# before the pre-recall weapon check gives up and dives anyway. The check normally clears
# in one Home round-trip (withdraw the real weapon, wield it); this backstop only fires if
# the character genuinely owns no combat weapon, so it must never hang the bot in town.

# Fixed quests have no ordinary retreat/recovery loop.  Preserve the scarce
# healing stock until HP is below 30%; lethal prediction and status cures still
# run first and are unaffected by this lower routine-healing threshold.
# A successful emergency relocation is not itself expedition-ending. Reassess
# the landing and return only when recovery is genuinely unsafe or this is the
# second forced escape of the dive.
EMERGENCY_RETURN_HP_RATIO = 0.50
# PlayerRaceFoodType::MANA — undead/construct races (Zombie, ...) restore hunger
# by eating wand/staff CHARGES rather than food. bot-test (a Zombie) starved to
# death next to a 20-charge staff it could have eaten.

# Return to town before supplies become fatal, or as soon as every normal pack
# slot is occupied. INVEN_PACK_SLOTS contains slots 0..22; slot 23 is only the
# temporary overflow slot and is not emitted in bot snapshots.
# Home identification works in batches but keeps enough space for purchases,
# swapped-out equipment, and an emergency floor pickup while town work continues.
# Rations to keep stocked; the General Store sells them, and a town return that
# restocks nothing just bounces straight back down and returns again.
# MANA races may eat their identification workhorse, but ordinary hunger must
# leave enough charges for the staff to remain functional. Weakness/fainting
# overrides this reserve because survival is the device's final purpose.
# Five slots is the normal loot-space target.  Four remains a usable terminal
# fallback when every safe town route for freeing another slot is exhausted.
TELEPORT_SCROLL_TARGET = 3
# Deep runs (10F+) escape far more often, so carry a big teleport buffer and only
# head back to restock once it is drawn down to the low reserve.
TELEPORT_SCROLL_DEEP_TARGET = 15
TELEPORT_RETURN_THRESHOLD = 3
# Once the character has reached this dungeon depth, returning to the dungeon
# from town uses Word of Recall (which lands at the deepest level reached) rather
# than walking to the wilderness entrance and re-descending from level 1.
RECALL_RETURN_THRESHOLD = 3
# Below this floor every ledger item is a convenience: if its suppliers are
# exhausted (or the item is unaffordable), walking out is safer than bouncing.
# Safe floor items remain worthwhile around distant weak monsters, but not when
# the visible group can remove a substantial share of current HP in three turns.
# Pre-engagement navigation should tolerate ordinary attrition. The loot gate
# may conservatively defer an optional pickup at 25%, but retreating from a
# route needs a substantially material threat; otherwise weak monsters create
# avoidance loops while the player is healthy.
# Once a route to remembered loot reveals one of these threats, leave that loot
# for the rest of the floor.  Otherwise stepping just outside line of sight makes
# the blocker disappear and immediately sends the bot back across the same edge.
# An ordinary supply return may make a short detour for realised value. Critical
# returns (food/light/pack/emergency) never wait for loot.
RETURN_LOOT_SWEEP_MAX_DISTANCE = 12
RETURN_LOOT_SWEEP_TRIGGERS = frozenset(
    {"recall-low", "teleport-low", "cure-low", "next-depth-kit"}
)
# escape-kit-empty deliberately skips the loot sweep: reaching town before the
# last escape method is spent is more important than an optional detour.
# loot-before-recall (user 2026-09-23) needs no trigger of its own here: it
# collects only inside the recall countdown, which no trigger can shorten, so
# the critical returns keep this set exactly as it is.
CURE_CRITICAL_TARGET = 3
CURE_CRITICAL_DEEP_DEPTH = 10
CURE_CRITICAL_DEEP_TARGET = 10
CURE_CRITICAL_DEEP_RETURN_THRESHOLD = 1
# From this depth the loot stream is dense enough that carrying a Staff of
# Identify pays for itself.  The same 10F boundary selects deep teleport stock.
# The complete supply policy lives here.  Values are (minimum floor, minimum
# carried stock); the ledger selects the last applicable band.  Departure uses
# the expedition target while return uses the reserve.  Supplier assignments
# match store/articles-on-sale.cpp (Recall additionally uses the Alchemist's
# random-stock precedent established by dc216f8).
SUPPLY_THRESHOLDS: dict[str, dict[str, tuple[tuple[int, int], ...]]] = {
    "teleport": {
        "return": ((1, 0), (TELEPORT_REQUIRED_DEPTH, TELEPORT_SCROLL_TARGET), (STAFF_IDENTIFY_MIN_DEPTH, TELEPORT_RETURN_THRESHOLD + 1)),
        "departure": ((1, 1), (TELEPORT_REQUIRED_DEPTH, TELEPORT_SCROLL_TARGET + 1), (STAFF_IDENTIFY_MIN_DEPTH, TELEPORT_SCROLL_DEEP_TARGET)),
    },
    "cure": {
        "return": ((1, 0), (CURE_CRITICAL_REQUIRED_DEPTH, CURE_CRITICAL_TARGET), (CURE_CRITICAL_DEEP_DEPTH, CURE_CRITICAL_DEEP_RETURN_THRESHOLD + 1)),
        "departure": ((1, 1), (CURE_CRITICAL_REQUIRED_DEPTH, CURE_CRITICAL_TARGET + 1), (CURE_CRITICAL_DEEP_DEPTH, CURE_CRITICAL_DEEP_TARGET)),
    },
    "oil": {"return": ((1, 0),), "departure": ((1, OIL_TARGET),)},
    "food": {"return": ((1, 0),), "departure": ((1, FOOD_STOCK_TARGET),)},
}
# Unique fights may justify spending rare Black Market potions, but only when
# the 95% operational damage model says the whole fight can be finished with a
# real HP reserve.  Keeping the attack cap below the minimum Speed duration also
# avoids assuming that one dose lasts through an arbitrarily long battle.
# Cure Critical Wounds heals 6d8 in Hengband: use its 27 HP mean in the
# readiness pool.  Healing uses its documented flat 300 HP value above.
# From this depth the loot stream is dense enough that carrying a Staff of Identify
# (rechargeable, unlike scrolls) pays for itself: unknowns get resolved in the
# dungeon so junk can be shed instead of hoarded. Required in the departure kit.
# ...and carry enough total identify charges (across staves) to last a deep run.
# Keep a useful reserve without accumulating every charged staff found.
# Identify unknowns once the pack has only this many free slots left, so the
# disposal/sale logic can judge them before they crowd out genuine loot.
# Consecutive pack-pressure identify attempts that leave the pack's unknown count
# unchanged before we give up on a target (the device use did not land) — stops
# a stalled identify from looping forever.
# Staff of Identify ("Perception", BaseitemDefinitions id 326) base level and the
# device-use minimum from gamevalue.h (USE_DEVICE).  They model the staff
# activation success rate per use-execution.cpp: chance = device_skill - level,
# and the use fails when randint1(chance) < USE_DEVICE, so success is
# (chance - 2) / chance.  Below STAFF_IDENTIFY_MIN_SUCCESS the town identify
# errand stays on scrolls, because a staff misfire leaks the pending target key
# onto the town map (the shop-underfoot identify/leave loop).
# A single Identify/*Identify* purchase covers the whole outstanding tier (see
# _outstanding_identification_count) instead of one scroll per store trip, but
# is capped so one unusually large Home batch cannot empty the wallet in a
# single transaction.
# User-approved standing float: it enables the strict spare-scroll barren-floor
# clause and is consumed only by incidental losses such as fire, acid, or theft.
# Mining has substantial fixed overhead: town processing, two wilderness crossings
# for shallow runs, and one Treasure Detection scroll per fresh floor.  Build a
# useful reserve in one batch instead of restarting fundraising after every dive.
# Outpost base prices are about 20g for the General Store's cheapest Shovel and
# 15g for one Alchemist Treasure Detection scroll.  Keep a deliberately round
# 100g reserve to cover charisma/store-price variation and a useful margin.
# When either missing component is visible in the live store snapshot, its
# observed price replaces that component's base price for the reserve decision.
HUNTER_OFFICE_BUILDING_TYPE = 13
RUMOR_EXIT_SUFFIX = "\r\r\x1b"
# Unlocking destinations can take many medium ("u") rumors. Keep each visit
# bounded so PostMessage input finishes well below the CLI's stalled-send
# diagnostic, then re-read exported progress before spending more gold.
# Gold kept in reserve so a rumor batch never spends the character dry; the batch
# size adapts to whatever is affordable above it. Below this, top up by mining.
# A descent block from one bad landing must not ratchet the bot upward forever:
# besides clearing on a level-up, it expires after this many decisions.
DESCENT_BLOCK_DECISIONS = 200
# A reconnect can begin on the downstairs because the one-shot launcher and
# long-lived follower hand off at a waiting turn.  It should step away before
# reusing that stair, but must re-arm well before cli.py's confined-cell loop
# fail-safe (40 decisions).  Hazardous landings still use the full cooldown.
RESUME_DESCENT_BLOCK_DECISIONS = 16

# Potion svals that restore HP (cure wounds / healing / life), from sv-potion-types.h.
# Expected raw HP restored by the combat-healing potions.  Cure Serious is
# 4d8; Healing and *Healing* are fixed in quaff-effects.cpp; Life restores to
# full and is therefore capped dynamically by the current missing HP.
HEAL_POTION_EXPECTED_HP = {35: 18, 37: 300, 38: 1200}
TELEPORT_SCROLL_SVALS = frozenset({9, 10})  # teleport, teleport level

Q34_WOODEN_CHEST_POSITION = Position(10, 8)

# Food svals that actually nourish (rations/biscuits/…); lower svals are mushrooms.


class ExplorationGoalKind(str, Enum):
    VISIT = "VISIT"
    FRONTIER = "FRONTIER"
    WINDOW_EDGE = "WINDOW_EDGE"




@dataclass(frozen=True)
class ExplorationGoalIdentity:
    kind: ExplorationGoalKind
    position: Position
    evidence_signature: tuple[int, bool, bool, bool, int]


from hengbot.policy_navigation import NavigationMixin
from hengbot.policy_combat import CombatMixin
from hengbot.policy_quest import QuestMixin
from hengbot.policy_equipment import EquipmentMixin
from .policy_home import HomeMixin
from .policy_shop import ShopMixin
from .policy_town import TownMixin
from .policy_observation import ObservationMixin


class HengbotPolicy(ObservationMixin, TownMixin, TownArbiterMixin, ShopMixin, HomeMixin, EquipmentMixin, QuestMixin, PolicyHelpersMixin, CombatMixin, NavigationMixin, SupplyMixin, FundraisingMixin, IdentificationMixin, CalibrationMixin):
    """Goal-seeking policy: survive, gain levels, and keep descending.

    Every decision resolves to a single, side-effect-safe key (a movement
    digit, ``>``/``<`` while standing on stairs, or a wait). None of them opens
    a sub-prompt, so the snapshot/keypress lockstep is never broken.
    """

    def __init__(
        self,
        town_map: "TownMap | None" = None,
        town_maps: "dict[int, TownMap] | None" = None,
        wilderness_map: "WildernessMap | None" = None,
        dungeon_knowledge: "dict[int, DungeonInfo] | None" = None,
        monrace_knowledge: "dict[int, MonraceKnowledge] | None" = None,
        damaging_terrain_ids: frozenset[int] | None = None,
        quest_knowledge: "dict[int, QuestInfo] | None" = None,
        quest_strategies: "dict[int, StrategyProfile] | None" = None,
        home_disposal_state: HomeDisposalState | None = None,
        exploration_ledger_path: Path | None = None,
        baseitem_costs: dict[tuple[int, int], int] | None = None,
    ) -> None:
        # A pre-loaded static town layout (lib/edit/towns) the bot may know in
        # advance, like a returning player — used to route across a dark town to a
        # store without the emitter revealing anything the player cannot see.
        self._town_map = town_map
        self._town_maps = dict(town_maps or {})
        self._wilderness_map = wilderness_map
        if town_map is not None:
            self._town_maps.setdefault(0, town_map)
        # Static dungeon depth/level facts (lib/edit/DungeonDefinitions), also prior
        # knowledge — used to recall into a level-appropriate dungeon when the main
        # one is too deep to loot. See _pick_alternate_dungeon.
        self._dungeon_knowledge = dungeon_knowledge or {}
        self._monrace_knowledge = monrace_knowledge or {}
        self._damaging_terrain_ids = damaging_terrain_ids or frozenset()
        self._quest_knowledge = quest_knowledge or {}
        self._quest_strategies = quest_strategies or {}
        self._baseitem_costs = dict(baseitem_costs or {})
        self._look_floor_items: dict[Position, tuple[InventoryItem, ...]] = {}
        self._look_floor_object_counts: dict[Position, int] = {}
        self._look_floor_key: tuple[int, int, int] | None = None
        self._look_probe_inflight = False
        self._posting_refusal_probe: tuple[str, OwnerProgressCore] | None = None
        self._last_policy_progress_core: OwnerProgressCore | None = None
        self._quest_navigators: dict[int, QuestFloorNavigator] = {}
        self._quest_strategy_visible_never_move: dict[int, set[int]] = {}
        self._quest_strategy_defeated_never_move: dict[int, set[int]] = {}
        self._quest_strategy_visible_targets: dict[
            int, set[tuple[int, int, int]]
        ] = {}
        self._quest_strategy_cleared_targets: dict[
            int, set[tuple[int, int, int]]
        ] = {}
        self._quest_strategy_pending_recovery: dict[int, dict[str, object]] = {}
        self._quest_strategy_recovery_claims: dict[
            int, set[tuple[object, ...]]
        ] = {}
        self._quest_strategy_recovery_pickup_prepared: tuple[
            int, Position, tuple[int, tuple[int, ...]]
        ] | None = None
        self._quest_strategy_recovery_pickup_prepared_key: str | None = None
        self._quest_strategy_recovery_pickup_posted: tuple[
            int, Position, tuple[int, tuple[int, ...]]
        ] | None = None
        self._q2_blue_recovery_perceived: set[Position] = set()
        self._quest_strategy_initial_hold_turns: dict[int, int] = {}
        self._quest_strategy_surveyed_placements: dict[int, set[Position]] = {}
        self._quest_strategy_sweep_rounds: dict[int, int] = {}
        self._quest_strategy_opening_phase: dict[int, int] = {}
        self._quest_strategy_hold_positions: dict[int, Position] = {}
        self._quest_strategy_post_wave_light_attempted: set[int] = set()
        self._quest_light_attempted: set[tuple[tuple[int, int, int], Position]] = set()
        self._q2_phase_light_attempted: set[tuple[object, ...]] = set()
        self._q2_phase_visited_goals: set[
            tuple[tuple[int, int, int], int, Position, Position]
        ] = set()
        self._q2_phase_route_targets: dict[
            tuple[tuple[int, int, int], int, Position], Position
        ] = {}
        self._q2_phase_last_move: tuple[
            tuple[int, int, int], int, Position, Position
        ] | None = None
        self._q2_phase_step_failures: Counter[
            tuple[tuple[int, int, int], int, Position, Position]
        ] = Counter()
        self._q2_phase_blocked_steps: dict[
            tuple[tuple[int, int, int], int], set[Position]
        ] = {}
        self._q2_speed_attempted: set[int] = set()
        self._q2_surveyed_placements: set[Position] = set()
        self._q2_residual_surveyed_races: set[int] = set()
        self._q2_final_patrol_visited: set[Position] = set()
        self._q2_final_patrol_target: Position | None = None
        self._q2_breeder_last_seen: Position | None = None
        self._q2_breeder_last_seen_floor: tuple[int, int, int] | None = None
        self._q2_cleared_races: set[int] = set()
        self._q2_breach_attempts = 0
        self._q2_breach_complete = False
        self._q2_blue_recovery_complete = False
        self._q2_ammo_recovery_floor: tuple[int, int, int] | None = None
        # Map-based Q2 progress reconstruction is valid only when the first
        # observation of this policy process is already on Q2.  A normal
        # town-to-quest transition sees the fixed quest map as known too, so
        # applying reconnect recovery there would skip the opening/light and
        # gremlin phases.
        self._q2_reconnect_recovery_floor: tuple[int, int, int] | None = None
        self._home_disposal = home_disposal_state or HomeDisposalState.in_repo()
        self._home_disposal_pass = False
        self._home_disposal_seen_pages: set[tuple[tuple[str, str, int, int], ...]] = set()
        self._home_disposal_candidates: dict[tuple[str, int, int], HomeDisposalCandidate] = {}
        self._home_disposal_pending: tuple[tuple[str, int, int], str] | None = None
        self._home_capacity_observation = None
        self._home_full_relief = None
        self._home_full_refused = False
        self._home_full_retry_deposits = None
        self._home_history_inflight: tuple[str, tuple[str, int, int], int, int] | None = None
        self._saw_dungeon_recall = False
        self._dive_dungeon: int | None = None  # dungeon id of the dive in progress
        self._dive_start_recall_depth: int | None = None
        self._dive_loot = 0  # items grabbed on the current dive
        self._dive_emergencies = 0  # emergency escapes forced on the current dive
        self._target_empty_dives = 0  # consecutive over-extended dives of the target
        # How many dives of that streak were guardian-kit-insufficient bounces.
        # Restored checkpoints predating it read 0 (getattr), i.e. the streak is
        # judged as ordinary over-extension.
        self._guardian_bounce_dives = 0
        # Whether the current dive's return began on a blocked guardian floor
        # (restored checkpoints read False through getattr: not counted).
        self._dive_guardian_return = False
        # Loot is useful, but it is not dungeon progression.  Keep a separate
        # leash for repeated Recall expeditions that never raise that dungeon's
        # saved landing depth; otherwise a few trivial pickups can keep the bot
        # farming the same blocked floor forever.
        self._no_depth_progress_dives = 0
        self._last_overextended_depth = 0  # recall depth we could not loot at
        self._alternate_dungeon: int | None = None  # switched-to level-fit dungeon
        self._pending_recall_dungeon_id: int | None = None
        # destination, command turn, and pre-read stack count.  JSON snapshots
        # can redraw several times at the same game turn before ``recalling`` is
        # exported; without an issue watch each stale redraw consumes another
        # Word of Recall scroll.
        self._town_recall_issue_watch: tuple[int, int, int] | None = None
        # Whether this town visit already cancelled a recall as unready.  The
        # read point never reads again in the same visit (read/cancel class
        # bound); restored checkpoints read False through getattr.
        self._town_visit_unready_recall_cancelled = False
        # A repetition fallback recall is the sole sanctioned exception to
        # ordinary town departure readiness.  Keep its ownership explicit so
        # the readiness cancel path cannot fight the cycle breaker's read.
        self._emergency_recall_sanctioned = False
        # floor, command turn, and pre-read stack count.  Dungeon recalls can
        # produce the same stale/interleaved recalling=False snapshots as town
        # recalls.  Without a transaction watch the latched return reads a new
        # scroll on each redraw, repeatedly restarting/cancelling the command
        # until the process loop detector stops the bot.
        self._dungeon_recall_issue_watch: tuple[
            tuple[int, int, int], int, int
        ] | None = None
        # Emergency scroll commands can be followed by an exact stale snapshot
        # after the CLI's duplicate retry interval.  Reissuing the same read on
        # that board spends a second escape scroll and also double-counts one
        # hazard as two emergencies.  Track the command until turn/item/position
        # state proves whether Hengband accepted it.
        self._emergency_consumable_issue_watch: tuple[
            tuple[int, int, int], int, Position, tuple[str, int, int], int, str
        ] | None = None
        # A fresh policy process can attach while a town recall is already
        # active. Its empty Home/equipment catalog is not evidence that the
        # established recall became unsafe; preserve that engine-owned action.
        self._startup_town_recall = False
        # Idle-item tracking: an item carried but never used (consumed or wielded)
        # across several dives is dead weight to stash at home. See UNUSED_DIVE_LIMIT.
        self._item_idle_dives: dict[tuple[str, int, int], int] = {}
        self._dive_used_sigs: set[tuple[str, int, int]] = set()
        self._prev_inv_counts: dict[tuple[str, int, int], int] = {}
        self._char_dump_done_this_visit = False  # wrote a pre-dive character dump?
        # An unidentified lantern hides its fuel. Refill it exactly once before
        # departure, then let the ordinary oil ledger replace the spent flask.
        self._unknown_lantern_departure_refilled = False
        self._periodic_dump_requested = False
        self._periodic_save_requested = False
        self._shopping_stuck = False  # gave up an unreachable store approach this visit
        self._shop_approach_stuck_count = 0  # oscillating-approach turns without arriving
        self._shop_approach_stuck_store = None
        self._shop_approach_previous_origin = None
        self._staged_shop_approach = None
        self._pending_shop_approach = None
        # Town stores are fixed landmarks.  Try Hengband's native travel command
        # once per approach; if it stops short, retain that goal here and finish
        # with the existing one-step pathfinder instead of retrying forever.
        # One deliberate store trip has one owner and lifecycle.  Compatibility
        # accessors below expose the old diagnostic names without retaining
        # independent ownership facts.
        # The arbiter owns the store visit; the mixin exposes compatibility
        # accessors for the policy's existing lifecycle producers.
        self._cross_decision_latches: dict[str, CrossDecisionLatch] = {
            "_store_visit": CrossDecisionLatch(
                "store-router",
                "_release_invalid_store_visit",
                release_sites=("_close_store_visit",),
            )
        }
        self._store_visit_last_closed: StoreVisit | None = None
        self._store_visit_pending_goal: Position | None = None
        self._store_entry_failed_owner: int | None = None
        self._store_entry_wait_owner: int | None = None
        self._store_entry_wait_key: str | None = None
        self._store_entry_wait_turn: int | None = None
        self._store_entrance_step_off: tuple[int, int, Position] | None = None
        # A store-entry command becomes outstanding only after the CLI confirms
        # that it was posted.  The next snapshot observes its result;
        # store=None is a failed entry, including at the unchanged entrance.
        # Shared progress tracker for every native-travel leg (stores, Home and
        # the dungeon entrance): the current goal, the best distance seen for
        # it, and how many issues brought no progress. See _town_travel_key.
        self._descent_target_goal: Position | None = None
        self._town_travel_state: TownTravelProgress | None = None
        self._town_travel_fallback: Position | None = None
        self._town_hunt_target: Position | None = None
        self._digger_wield_attempts = 0  # consecutive un-taking digging-tool wields
        self._equipment_mutation = EquipmentMutationExecutor()
        self._equipment_mutation_result = EquipmentMutationResult(None)
        self._equipment_mutation_observed_changes = 0
        self._equipment_mutation_post_commit: tuple[str, str] | None = None
        self._pending_mutation_report: str | None = None
        # The board the equipment executor's fruitless count last saw.
        self._equipment_mutation_counted_board = None
        self._hunt_progress_floor: tuple[int, int, int] | None = None
        self._hunt_progress: dict[tuple[int, int, Position], dict[str, int]] = {}
        self._hunt_target_identities: dict[int, tuple[int, int, Position]] = {}
        self._hunt_cooled_targets: set[tuple[int, int, Position]] = set()
        self._hunt_cooling_exempt_targets: set[tuple[int, int, Position]] = set()
        self._pending_hunt_report: str | None = None
        self._mining_combat_contact_streak = 0
        self._mining_threat_free_streak = 0
        self._swarm_distance_floor: tuple[int, int, int] | None = None
        self._swarm_previous_distances: dict[int, tuple[int, Position]] = {}
        # Consecutive in-town decisions spent wielding only a digging tool (no combat
        # weapon). The pre-recall weapon check blocks a dive until this clears (weapon
        # re-armed) or hits WEAPON_BLOCK_LIMIT (own no weapon → dive anyway).
        self._weapon_block_streak = 0
        # Page signatures already inspected while searching the Home for a
        # combat weapon. Home only exposes its current page in each snapshot;
        # Space advances a page and seeing a signature twice means we wrapped.
        self._home_rearm_seen_pages: set[tuple[tuple[str, str, int, int], ...]] = set()
        self._home_digger_seen_pages: set[
            tuple[tuple[str, str, int, int], ...]
        ] = set()
        self._home_quest_launcher_seen_pages: set[
            tuple[tuple[str, str, int, int], ...]
        ] = set()
        # Normal Home processing has the same paged view. Do not treat an empty
        # current page as completion and recall while later pages still contain
        # equipment that needs identification or comparison.
        self._home_processing_seen_pages: set[
            tuple[tuple[str, str, int, int], ...]
        ] = set()
        self._visit_counts: Counter[Position] = Counter()
        self._exploration_ledger = ExplorationLedger(exploration_ledger_path)
        self._probed_frontiers: set[Position] = set()
        self._floor_key: tuple[int, int, int] | None = None
        # Hengband does not mark dark floor permanently, so walked corridors can
        # disappear from later nearby_grids snapshots. Retain the last terrain
        # observation for this floor visit; dynamic occupancy is stripped below.
        self._remembered_grid_region: (
            tuple[int, int, int, int, int, int, bool] | None
        ) = None
        self._remembered_grids: dict[Position, GridState] = {}
        self._remembered_grid_signatures: dict[Position, tuple] = {}
        self._remembered_grid_sources: dict[Position, GridState] = {}
        # The last known town id the routing terrain was learned in (see
        # _with_grid_memory); None until a board of a known town arrives.
        self._terrain_town_id: int | None = None
        # Region-local town facts are updated from emitted cells. Missing cells
        # retain their last known value, which is essential for unlit towns.
        self._town_fact_region: tuple[int, int, int, int, int, int, bool] | None = None
        self._town_store_positions: dict[int, set[Position]] = {}
        self._town_emitted_entrances: set[Position] = set()
        # Shape metadata can flicker between interleaved surface snapshots.
        # Retain disclosed entrance cells independently until the town visit
        # actually ends, so that flicker cannot authorize a stay on a door.
        self._town_visit_entrances: set[Position] = set()
        self._town_entrance_cache: frozenset[Position] | None = None
        self._town_fact_snapshot: Snapshot | None = None
        # Predicate results are valid only for one merged decision snapshot.
        self._map_predicate_snapshot: Snapshot | None = None
        self._decision_input_snapshot: Snapshot | None = None
        self._fixed_quest_offers: frozenset[int] = frozenset()
        # Derived only for the current public decision.  Each identity entry
        # holds its Snapshot reference so a recycled id can never hit.
        self._fixed_quest_offer_cache: dict[
            int, tuple[Snapshot, frozenset[int]]
        ] = {}
        self._fixed_quest_head_cache: dict[
            int, tuple[Snapshot, QuestState | None]
        ] = {}
        self._equipment_departure_cache_token: tuple[int, int] | None = None
        self._equipment_departure_cache_value = False
        self._hazard_cache: dict[Position, bool] = {}
        self._town_border_cache: dict[Position, bool] = {}
        self._last_position: Position | None = None
        self._recent: deque[Position] = deque(maxlen=EXTENDED_STUCK_WINDOW)
        self._osc_positions: deque[Position] = deque(
            maxlen=EXTENDED_STUCK_WINDOW
        )
        self._explore_path: list[Position] = []
        # Stage 2 observational state: selectors do not read either field.
        self._explore_goal_identity: ExplorationGoalIdentity | None = None
        self._explore_path_outcome: ExplorationPathOutcome | None = None
        # A one-step explore route is consumed before the next snapshot can
        # confirm arrival. Remember its origin until then; failures from several
        # different adjacent cells retire a goal without pretending it was
        # visited. Terrain/occupancy changes revive the coordinate.
        self._pending_one_step_explore: (
            tuple[Position, Position, tuple[int, bool, bool, bool, int]] | None
        ) = None
        self._one_step_explore_failures: dict[Position, set[Position]] = {}
        self._one_step_explore_signatures: dict[
            Position, tuple[int, bool, bool, bool, int]
        ] = {}
        self._unenterable_explore_goals: dict[
            Position, tuple[int, bool, bool, bool, int]
        ] = {}
        # Cells from which the material-engagement gate deliberately retreated.
        # Generic exploration/hunting must not immediately route back onto them.
        # Two owners contribute members: the engagement/status-threat retreat
        # logic (via _claim_engagement_avoid_cells, tracked in
        # _engagement_owned_avoid_cells) and the warning-grid latch below.
        # Only the warning owner ever withdraws cells, and it may never remove
        # another owner's claim (see _refresh_warning_avoidance).
        self._engagement_avoid_cells: set[Position] = set()
        self._engagement_owned_avoid_cells: set[Position] = set()
        # Floor-visit memory for monsters whose blows can paralyze. Both
        # stationary and moving threats retain their last observed cell while
        # unseen, and observation of that cell without the monster retires it.
        self._paralyzer_avoid_cells: set[Position] = set()
        self._remembered_paralyzers: dict[Position, bool] = {}
        # Grids whose entry a TR_WARNING prompt refused (this floor).  Injected
        # into _engagement_avoid_cells every decision — the same hard weight as
        # a lethal-danger cell — until the supply ledger is entirely exhausted,
        # at which point the user-sanctioned forced walk (direction key + 'y')
        # is the only remaining way off the situation.
        self._warning_refused_cells: set[Position] = set()
        # The single walk issued by the previous decision, so the warning
        # prompt reported by the NEXT snapshot can be attributed to the grid
        # that was being entered: (decision_sequence, floor_key, origin, step).
        self._warning_step_pending: (
            tuple[int, tuple[int, int, int], Position, Position] | None
        ) = None
        self._warning_prompt_stops_decision = False
        # Per-decision grid indexes (y, x) tuples: floor we can walk onto,
        # closed doors we can open, and all currently-known tiles. Rebuilt each
        # decision so the hot BFS loops use set lookups instead of dict access
        # and Position allocation (the full-map snapshot is ~10k tiles).
        self._floor_t: set[tuple[int, int]] = set()
        self._door_t: set[tuple[int, int]] = set()
        self._rubble_t: set[tuple[int, int]] = set()
        self._marked_t: set[tuple[int, int]] = set()
        self._remembered_floor_t: set[tuple[int, int]] = set()
        self._remembered_door_t: set[tuple[int, int]] = set()
        self._remembered_rubble_t: set[tuple[int, int]] = set()
        self._remembered_wall_t: set[tuple[int, int]] = set()
        self._remembered_known_t: set[tuple[int, int]] = set()
        self._remembered_marked_t: set[tuple[int, int]] = set()
        self._emitted_t: set[tuple[int, int]] = set()
        self._window_edge_goals: set[Position] = set()
        self._window_edge_fallback_pending = False
        self._remembered_downstairs: set[Position] = set()
        self._remembered_upstairs: set[Position] = set()
        self._remembered_entrances: set[Position] = set()
        # Diagnostic only: the latest predicate that declined a remembered
        # descent. It is surfaced by the flight recorder and never read by play.
        self._descent_refusal_reason: str | None = None
        # Diagnostic only: evidence from the latest in-store selector pass.
        # Gameplay never reads this field.
        self._shop_selector_diagnostics: dict[str, object] = {}
        # Result-level town procurement invariant.  This is diagnostic state,
        # but unlike the older in-store selector record it is written at the
        # public decision seam and therefore also covers approach/entry pages.
        self._town_progress_invariant_defect: dict[str, object] = {}
        # Result-level progress is measured across decisions, not inferred from
        # one step alone.  Reusing the established town-cycle window keeps a
        # returned walk productive only while its durable state is net-new.
        self._town_progress_fingerprint_history: deque[tuple[object, ...]] = deque(
            maxlen=TOWN_CYCLE_WINDOW
        )
        self._town_progress_last_fingerprint: tuple[object, ...] | None = None
        self._town_supplier_stock: dict[int, StoreState] = {}
        # Provenance for general-store shelf snapshots.  Shelf contents are kept
        # in the long-standing mapping above for its existing consumers, while
        # decisions that require negative stock evidence must prove that the
        # page was observed during this town visit and in this town.
        self._town_supplier_stock_observations: dict[int, tuple[int, int]] = {}
        # A stair command is verified by the following snapshot. Hengband rejects
        # a stair key without spending a turn, which gives stronger evidence than
        # ordinary navigation stalls that remembered terrain is a phantom.
        self._pending_stair_command: (
            tuple[str, tuple[int, int, int], Position, int, Snapshot] | None
        ) = None
        self._stair_observation_waits = 0
        self._stair_rejection_strikes: Counter[tuple[str, Position]] = Counter()
        self._unverified_stairs: set[tuple[str, Position]] = set()
        self._known_treasure: set[Position] = set()
        self._treasure_target: Position | None = None
        # Bumping an unseen wall marks it so Hengband will accept the following
        # tunnel command. Bound stale-emitter retries with DIGGER_WIELD_LIMIT.
        self._mining_mark_bumps: Counter[Position] = Counter()
        self._mining_unmarkable_grids: set[Position] = set()
        # Consecutive stalled (oscillating) turns while mining. Digging toward a
        # walled-off vein keeps the player on one tile, so this bounds how long we
        # claw at an unreachable vein before giving up and ascending — WITHOUT ever
        # spending a scarce Teleport/Recall scroll to relocate (survival escapes are
        # handled upstream). Kept below the harness loop window so we self-abort first.
        self._mining_stall_turns = 0
        self._mining_route_visits: Counter[Position] = Counter()
        self._mining_navigation_visits: Counter[Position] = Counter()
        self._mining_oscillation_retargets = 0
        # Two-phase mining (user design): after each detection read, SWEEP the
        # detected area first (explore -> approaches become walkable), then
        # collect every distance-1 vein until none qualify. Veins whose walk
        # keeps failing go into the dropped set — _observe re-adds any grid that
        # still shows gold on every observation, so without this persistent
        # exclusion "skip to the next vein" silently retries the same one until
        # a revisit limit ends the whole floor with most treasure uncollected.
        self._mining_sweep_done = False
        self._mining_viability_pending_floor: tuple[int, int, int] | None = None
        self._mining_sweep_steps = 0
        self._mining_sweep_no_progress = 0
        self._mining_sweep_revealed_grids = 0
        self._mining_sweep_goal: Position | None = None
        self._mining_sweep_goal_distance: int | None = None
        self._mining_sweep_escape_pairs: deque[
            tuple[Position, Position]
        ] = deque(maxlen=3)
        self._mining_swept_dead_targets: set[Position] = set()
        # Chest pipeline: position of the dropped chest and the per-phase key
        # budgets already spent (search/disarm/open). None = no chest placed.
        self._chest_position: Position | None = None
        self._chest_phase_counts: dict[str, int] = {}
        self._chest_drop_origin: Position | None = None
        self._chest_collecting = False
        self._chest_preopen_objects: dict[Position, tuple[int, int]] | None = None
        self._processed_chest_positions: set[Position] = set()
        # Known-grid high-water mark at the moment the sweep latched done. A
        # tapped-out RESUME must show the map grew past this (mining exposed
        # new floor); resuming on mere frontier existence re-runs the exact
        # sweep that just dead-ended (live: a done→resume macro-cycle bounced
        # a junction until the loop guard killed the bot). 0 = no evidence
        # recorded (fresh process/floor) → resume stays permitted.
        self._mining_grids_at_sweep_done = 0
        self._mining_dropped_veins: set[Position] = set()
        self._mining_veins_collected = 0
        self._mining_veins_dropped = 0
        self._mining_target_distance: int | None = None
        self._mining_target_revealed_grids = 0
        self._mining_target_collected = 0
        # Gold when scavenge mode was last entered — the scavenge->prepare
        # transition re-checks latched stores only if gold actually rose.
        self._scavenge_entry_gold = 0
        # Town-repetition detector state — see TOWN_CYCLE_WINDOW.
        self._town_signature_history: deque[tuple] = deque(
            maxlen=TOWN_CYCLE_WINDOW
        )
        self._town_progress_marker: tuple | None = None
        self._town_no_progress_count = 0
        self._town_visit_ledger = TownVisitLedger()
        # The maximum existing Home bound is installed once per town epoch.
        # Ordinary route bounds may stop earlier; no optimizer/session rebuild
        # can replenish this physical-visit budget.
        self._home_visit = HomeVisitExecutor(HOME_VISIT_LIMIT)
        self._pending_home_visit_report: str | None = None
        self._home_route_refusal: dict[str, object] | None = None
        self._home_route_refusal_sequence: int | None = None
        self._town_was_in_town = False
        self._town_visit_epoch: int | None = None
        self._town_cycle_pending = False
        self._town_cycle_breaks = 0
        self._observed_town_id: int | None = None
        self._town_restock_suppressed = False
        self._town_suppression_claim_stores: set[int] = set()
        self._town_errand_plan: TownErrandPlan | None = None
        # Four free slots are accepted only after the productive town pipeline
        # has declined every action for this exact inventory.  Keep the readiness
        # gate pure: calling disposal/store planners from it recurses through the
        # supply ledger and equipment departure checks.
        self._terminal_pack_space_signature: tuple[tuple[object, ...], ...] | None = None
        self._known_loot: set[Position] = set()
        self._loot_target: Position | None = None
        self._deferred_loot: set[Position] = set()
        self._safety_deferred_loot: set[Position] = set()
        # Of the deferred positions, the ones the navigation ledger expired
        # (blocker "navigation-ledger:loot"), and positions that already used
        # their one relocation/recall rearm budget. Both are per floor visit.
        self._nav_ledger_deferred_loot: set[Position] = set()
        self._loot_ledger_rearmed: set[Position] = set()
        self._loot_safety_rearmed: set[Position] = set()
        self._loot_defer_blocker: str | None = None
        self._pending_loot_pickup: tuple[tuple[int, int, int], Position, int] | None = None
        self._multiplier_target: Position | None = None
        self._multiplier_target_grace = 0
        self._probe_counts: Counter[tuple[int, int]] = Counter()
        self._dark_goal_counts: Counter[tuple[int, int]] = Counter()
        self._dark_route: list[Position] = []
        self._dark_route_goal: Position | None = None
        self._dark_route_expected: Position | None = None
        self._floor_trap_disarm_attempts: Counter[tuple[int, int]] = Counter()
        self._door_attempts: Counter[tuple[int, int]] = Counter()
        self._blocked_doors: set[tuple[int, int]] = set()
        self._dig_attempts: Counter[tuple[int, int]] = Counter()
        self._last_dig_signature: tuple[tuple[int, int], int] | None = None
        self._rejected_dig_attempts = 0
        self._blocked_rubble: set[tuple[int, int]] = set()
        self._search_counts: Counter[tuple[int, int]] = Counter()
        self._wall_search_counts: Counter[tuple[int, int]] = Counter()
        # Unknown tiles we probed to the limit and concluded are unrevealable
        # walls; they must stop counting as "unexplored neighbour" or the floor
        # tile beside them stays a permanent frontier and we oscillate toward it.
        self._blocked_unknown: set[tuple[int, int]] = set()
        self._rest_count = 0
        # Last detected-threat rest tiering (esp-threat-rest); diagnostic only,
        # rewritten before every read.
        self._esp_threat_assessment: dict | None = None
        # Committed STRONG-tier hunt (floor, indices, floor_hp, speed plan)
        # and the cause that last ended one.
        self._esp_threat_hunt: dict | None = None
        self._esp_threat_hunt_end: str | None = None
        self._last_move_key: str | None = None
        self._last_move_pos: Position | None = None
        self._move_repeat = 0
        self._position_changed = False
        # HP last decision, to notice damage from an attacker we cannot see
        # (a monster in the dark / invisible) — resting through that is fatal.
        self._last_hp: int | None = None
        self._took_damage = False
        self._took_curse_damage = False
        self._took_trap_or_terrain_damage = False
        # Set once we visit the General Store but cannot buy a lantern (can't
        # afford it / not stocked), so we stop walking back to it forever.
        self._shopping_abandoned = False
        # (item letter, gold) of the last buy we tried, and how many times we have
        # re-tried it unchanged — to bail out of a purchase that never registers.
        self._last_buy_sig: tuple[str, int] | None = None
        self._store_stuck_count = 0
        # A store redraw can repeat the exact pre-purchase state after Hengband
        # has accepted the command.  Do not issue another buy until inventory or
        # gold confirms the first one, or a bounded wait proves it was rejected.
        self._store_buy_inflight: tuple[
            int, tuple[str, int, int], int, int, int, int
        ] | None = None
        # Latest authoritative normal-shop page, consumed only while outside.
        self._shop_observation: tuple[StoreState, int] | None = None
        # In-store shop operations and shelf evidence
        # (SOL-DESIGN-store-reentry-20261003, policy_instore.py).  The switch
        # is the CLI's ``--in-store-shop-ops``; the breaker survives restarts
        # through its sidecar file.
        self._in_store_ops_enabled = False
        self._in_store_breaker: tuple[str, int | None] | None = None
        self._in_store_breaker_path: Path | None = None
        self._in_store_entry_ledger: dict | None = None
        self._in_store_screen_verified: bool | None = None
        self._in_store_shop_fallback: dict | None = None
        self._in_store_shadow_last: dict[int, dict] = {}
        self._in_store_telemetry: dict | None = None
        self._shelf_evidence: dict = {}
        self._shelf_evidence_cache: dict = {}
        self._plan_shadow_pending: dict = {}
        self._plan_shadow_visits: dict = {}
        # Store actions share the decision sequence as a monotonic correctness
        # generation.  A leave owns older store snapshots until the feed shows
        # either the surface or a non-older in-store action generation.
        # A Home entry may dispatch exactly one deposit or withdrawal.  Keep
        # this latched across interleaved surface records until an Escape-owned
        # outside snapshot proves that the visit ended; otherwise a redraw
        # while an item chooser is open can turn a repeated command letter into
        # an unintended pack selection.
        self._emission_occurrences: dict[
            EmissionState, tuple[int, int, str]
        ] = {}
        self._emission_previous_state: EmissionState | None = None
        # Ordinary Home deposits are posted while standing on the entrance tile
        # as one stay/deposit/exit string.  This identifies that special visit
        # until the next outside observation; withdrawals and transaction
        # commands retain their existing in-store prepare/post/observe path.
        # (identity, count before posting, posting turn, newer unchanged pages).
        # A same-turn surface record is part of the composed entry/deposit/exit
        # command, not a negative observation of its effect.
        self._home_atomic_deposit_pending: tuple[
            tuple[tuple[tuple[str, int, int], int, int], ...], None, int, int
        ] | None = None
        # Same target and shortage after a registered, money-spending buy is a
        # distinct defect from a transport failure at unchanged gold.
        self._last_buy_progress_sig: tuple[str, int, int] | None = None
        self._store_buy_no_progress_count = 0
        self._descent_blocked = False
        self._descent_block_countdown = 0
        self._returning_to_town = False
        # Rev 9.2 (S), record-only: the trigger the *running* return began
        # with, set where a return starts and cleared where it ends.  Only the
        # claim register's survival test reads it.
        self._survival_return_trigger: str | None = None
        self._last_return_trigger: str | None = None  # why the last town return began
        self._escape_state = EscapeState()
        self._decision_sequence = 0
        self._departure_block_sequence: int | None = None
        self._acquire_store_visit_attempt: dict[str, object] = {
            "acquire_store_visit_called": False,
            "requested_owner": None,
            "requested_store": None,
            "acquire_result": None,
        }
        self._decision_context: DecisionContext | None = None
        self.decision_attribution = "unregistered"
        # S1 attribution: the register records who owns each decision and the
        # goal it declared.  Setting it to None disables recording entirely,
        # which is how the neutrality pin replays the same boards without it.
        self._claim_register = ClaimRegister()
        self.decision_claim: dict | None = None
        # S2b.2 (design 3.2 / 3.3): the switch that lets the bar table change
        # a decision.  OFF is the default and the only shipped setting: the
        # table is kept and every decision records what it *would* bar
        # (``would_bar``), but no rung is skipped.  Turned on only by tests
        # until a live measurement decides otherwise (user decision
        # 2026-09-26).
        self._claim_bar_enforced = False
        # S3.3 town errand admission is independent of the S2b.2 threat bar.
        # A restored checkpoint may predate this attribute; readers use
        # getattr(..., False) until its first decision.
        self._town_claim_bar_enforced = False
        self._crossarea_fundraising_enforced = False
        self._owner_expectations = OwnerExpectationRegistry()
        self._town_turn_arbiter = _new_town_turn_arbiter()
        self._unviable_quest_floor: tuple[int, int, int] | None = None
        self._escape_sustain_floor: tuple[int, int, int] | None = None
        self._escape_sustain_active = False
        self._escape_sustain_non_escape_decisions = 0
        self._escape_speed_baseline: int | None = None
        self._escape_speed_attempted = False
        self._last_damage_amount = 0
        self._unseen_recall_damage_streak = 0
        self._unseen_retreat_floor: tuple[int, int, int] | None = None
        self._unseen_retreat_direction: tuple[int, int] | None = None
        self._unseen_retreat_target: Position | None = None
        self._unseen_choke_position: Position | None = None
        self._unseen_choke_started_turn: int | None = None
        self._unseen_attack_evidence: str | None = None
        self._unexplained_damage_streak = 0
        # Total HP lost over the current unexplained-damage streak.
        self._unexplained_damage_streak_loss = 0
        # (floor, observed loss, deadline game turn) of a lethal escape the
        # blindness/confusion cure pre-empted; the next readable board owes it.
        self._blind_cure_escape_carry: (
            tuple[tuple[int, int, int], int, int] | None
        ) = None
        # (floor, monster index) of summoners a posted shot or throw may have
        # damaged on this floor: they may hold a counter-attack target.
        self._summoner_counter_targets: frozenset[
            tuple[tuple[int, int, int], int]
        ] = frozenset()
        # Floor of the strong-fight run whose start was handled (a Speed
        # potion quaffed, or haste already shown); None between runs.
        self._strong_fight_speed_floor: tuple[int, int, int] | None = None
        # Floor of an unseen hit not yet seen by the unseen-attacker retreat
        # (read with getattr: restored checkpoints predate it).
        self._unseen_hit_pending_floor: tuple[int, int, int] | None = None
        # (floor, position, game turn, Teleportation scrolls carried) of a
        # posted Teleportation read whose landing has not been observed yet;
        # read with getattr (restored checkpoints predate it).
        self._teleport_read_watch: (
            tuple[tuple[int, int, int], Position, int, int] | None
        ) = None
        # (floor, positions observed since) the player's own teleport landed
        # on this floor: ``_recent`` entries older than these are the far
        # side of the jump.  Read with getattr (restored checkpoints).
        self._recent_since_teleport: tuple[tuple[int, int, int], int] | None = None
        # (floor, {(index, race_id)}) of status threats already fled from;
        # read with getattr (restored checkpoints predate it).
        self._status_threat_latch: tuple[
            tuple[int, int, int], frozenset[tuple[int, int]]
        ] | None = None

        # threat_prediction results for the CURRENT snapshot, keyed by object
        # identity — see threat_prediction. Bounded; cleared when it fills.
        self._threat_prediction_memo: dict[tuple, dict] = {}
        # Value-keyed aggregate-p95 cache shared across decisions — see
        # _aggregate_ranged_percentile. Bounded; cleared when it fills.
        self._aggregate_ranged_cache: dict[tuple, object] = {}
        # A targeting macro ending in Escape made no observable progress when
        # the same player/grid pair is offered again.  Bound those retries and
        # clear the guard as soon as the player moves.
        self._ranged_target_guard_position: Position | None = None
        self._ranged_target_attempts: dict[int, int] = {}
        # Cursor-targeted fire can fail before launching a projectile (for
        # example when Hengband's target list selects an out-of-range member of
        # a moving pack).  Per-monster HP tracking alone is insufficient because
        # the visible monster index can change every decision.  Remember the
        # ammunition stack offered to the last targeting macro so an unchanged
        # stack bounds failures across the whole pack.
        self._ranged_target_macro_signature: tuple[
            tuple[int, int, int], Position, int, int, int
        ] | None = None
        self._ranged_target_macro_failures = 0
        # Last observed HP for cursor-targeted shots.  Position is deliberately
        # excluded: a monster pacing between two cells is not evidence that a
        # shot landed and must not reset the failed-targeting guard.
        self._ranged_target_signatures: dict[int, int] = {}
        self._emergency_escape_pending = False
        # Once an emergency escape fires, routine return looting stays disabled
        # for the rest of this floor visit even after relocation makes the
        # immediate threat look safe.
        self._emergency_return_active = False
        # Speed-potion state for the currently engaged unique.  The baseline is
        # the speed observed before quaffing; after the bonus expires we may dose
        # again, while a failed command is not blindly repeated forever.
        self._unique_speed_race_id: int | None = None
        self._unique_speed_baseline: int | None = None
        self._unique_speed_attempted = False
        self._unique_speed_was_active = False
        self._unique_combat_committed_race_id: int | None = None
        self._stuck_escape_streak = 0
        # R1 navigation redesign: the shared per-floor-visit target ledger and
        # the mode-independent no-progress invariant (see NAV_NO_PROGRESS_LIMIT).
        self._nav_ledger = NavigationLedger()
        self._nav_stall_count = 0
        self._nav_exhausted = False
        self._nav_escape_steps = 0
        self._nav_known_high = 0
        self._nav_progress_marker: tuple[int, int, int] | None = None
        self._oscillation_outcome_marker: tuple | None = None
        self._combat_outcomes: deque[tuple] = deque(maxlen=COMBAT_OUTCOME_WINDOW + 1)
        self._combat_outcome_floor: tuple[int, int, int] | None = None
        self._combat_fruitful = True
        self._breeder_engagement_floor: tuple[int, int, int] | None = None
        self._breeder_engagement_score = 0
        self._breeder_engagement_start_count: int | None = None
        self._breeder_engagement_start_turn: int | None = None
        self._breeder_kills = 0
        self._breeder_previous_exp: int | None = None
        self._breeder_previous_indices: set[int] = set()
        self._choke_engagement_plan: ChokeEngagementPlan | None = None
        # Floor and snapshot turn of the decision that first waited for a
        # detected pack at a reached choke.  Retain an expired episode until an
        # inherited release stimulus occurs so it cannot immediately re-arm.
        self._detected_threat_hold: tuple[tuple[int, int, int], int] | None = None
        # The anticipatory retreat's committed goal: floor, the covered cell it
        # chose, and the detected pack it was opened for.  Without it the owner
        # gives the decision back the moment its own step widens the gap, and
        # the next owner walks that step back (alternating owners, 2026-09-23).
        self._detected_threat_route: tuple[
            tuple[int, int, int], Position, frozenset[int]
        ] | None = None
        # A plan is disposable, but fruitless work against the same observed
        # swarm is not.  Values are (spent decisions, high-water outcome marker)
        # and live for the whole floor visit so release/re-plan cannot mint a
        # fresh combat budget.
        self._choke_outcome_floor: tuple[int, int, int] | None = None
        self._choke_outcome_budgets: dict[Position, tuple[int, tuple[int, ...]]] = {}
        self._breeder_choke_attempt_ended_floor: tuple[int, int, int] | None = None
        self._cross_decision_latches["_choke_engagement_plan"] = CrossDecisionLatch(
            "melee-engagement",
            "_release_invalid_choke_plan",
            release_sites=("_release_choke_plan",),
        )
        self._breeder_breakthrough_floor: tuple[int, int, int] | None = None
        # A breeder floor left by stairs remains an observed walk-out fact until
        # town (or another dungeon) proves the escape complete.  This is not a
        # cooldown: while we are above that floor in the same dungeon, the
        # return owner keeps taking concrete up-stair exits and ordinary descent
        # cannot send us back into the multiplied population.
        self._breeder_fled_floor: tuple[int, int, int] | None = None
        self._fruitless_disengage_floor: tuple[int, int, int] | None = None
        self._fruitless_disengage_decisions = 0
        self._fruitless_disengage_marked_high = 0
        self._fruitless_disengage_spent_this_decision = False
        self._escape_wait_budget_floor: tuple[int, int, int] | None = None
        self._escape_wait_decisions: Counter[str] = Counter()
        self.escape_ladder_telemetry: dict[str, object] | None = None
        self.town_teleport_refusal: dict[str, int] | None = None
        self._town_wander_streak = 0
        self._deepest_level = 0
        self._target_dungeon_id = DUNGEON_YEEK_CAVE
        self._yeek_victory_loot = False
        # Generic conquest-loot: which dungeons we already know are conquered, and the
        # dungeon whose final-guardian drop we are collecting before we recall out.
        self._conquered_seen: set[int] = set()
        self._victory_loot_dungeon: int | None = None
        self._fixed_quest_reward_pending: int | None = None
        self._fixed_quest_readiness: dict = {}
        self._fixed_quest_speed_floor: tuple[int, int, int] | None = None
        self._fixed_quest_speed_attempted = False
        # Regenerating a depleted KILL_LEVEL floor is a two-floor transaction:
        # leave upward, then return immediately.  Three fruitless fresh floors
        # are a phase bound: enough to distinguish bad luck from a broken quest
        # feed without turning regeneration into another invisible infinite loop.
        self._quest_regen_id: int | None = None
        self._quest_regen_phase: str | None = None
        self._quest_regen_kills_before = 0
        self._quest_regen_zero_rounds = 0
        self._quest_regen_exhausted_floor: tuple[int, int, int] | None = None
        self._telmora_q2_errand = False
        # The conquest target latch (see _conquest_target): sticky once chosen, so
        # consumable possession (a Speed potion bought/drunk/stashed) cannot flip
        # the recall destination back and forth.
        self._conquest_committed: int | None = None
        # The conquest clear is a one-shot transition per target.  A standing
        # but not-yet-launchable target must not fight the low-gold router on
        # every observation.
        self._fundraising_cleared_for_conquest: int | None = None
        self._rumor_unlock_pending = False
        # Inn travel only lists towns marked as visited by the game.  Rumors can
        # reveal those towns, so keep the intended destination latched until the
        # exported progress confirms that the service can actually select it.
        self._town_travel_rumor_pending: int | None = None
        # store_type -> the game turn it was latched at (see STORE_RETRY_TURNS),
        # except that Home's terminal claim verdict retains its named reason.
        self._town_store_attempted: dict[int, int | str] = {}
        self._home_claim_uncomposable_signature: tuple[object, ...] | None = None
        self._home_latch_active: dict[str, object] | None = None
        self._home_latch_history: list[dict[str, object]] = []
        self._home_gate_telemetry: dict[str, object] = {}
        self._home_atomic_withdraw_telemetry: dict[str, object] = {}
        self._town_restock_wait_until: int | None = None
        self._town_restock_waiting_for: tuple[int, ...] = ()
        self._town_restock_rechecked: set[int] = set()
        self._town_restock_waited_turns = 0
        self._town_restock_last_wait_turn: int | None = None
        # Normal Remove Curse can fail against a heavy curse.  A confirmed
        # unchanged read records that fact both in the runtime latch and in a
        # player-visible, savefile-persistent inscription.  All curse consumers
        # consult _curse_unremovable(), never either backing store directly.
        self._remove_curse_watch: tuple[tuple[str, int, int], int, int] | None = None
        self._permanent_cursed_items: set[tuple[str, int, int]] = set()
        self._heavy_cursed_items: set[tuple[str, int, int]] = set()
        self._heavy_curse_inscription_pending: tuple[str, int, int] | None = None
        self._launcher_enchant_attempted: set[int] = set()
        self._launcher_enchant_watch: tuple[int, tuple[str, int, int], int] | None = None
        self._last_sell_sig: tuple | None = None
        self._store_sell_stuck_count = 0
        # Item signature, last observed count, and consecutive attempts. Unlike
        # _last_sell_sig, this survives turn changes and store exit/re-entry so
        # an unanswered prompt cannot evade rejection by advancing the turn.
        self._store_sell_attempt: tuple[tuple[str, int, int], int, int] | None = None
        # Every store sale is a tag-bound transaction.  The pending record
        # spans inscription observation, sale, and post-sale verification.
        self._batch_sell_pending: dict[str, object] | None = None
        # Explicit Home-capacity failures may stop deposits for one town visit.
        # Input-level rejection is tracked separately per item below.
        # Exhausted input retries mean only that deposits should be abandoned
        # for this visit; they do not prove that the Home is at capacity.
        self._home_deposit_abandoned = False
        # A command can reject one item even while the Home still has free pages.
        self._home_rejected_deposits: set[tuple[str, int, int]] = set()
        # Store purchases are retained for the rest of the current town visit.
        self._town_visit_purchases: set[tuple[str, int, int]] = set()
        self._town_visit_purchase_quantities: dict[tuple[str, int, int], int] = {}
        # Successful sales are retained for the same town visit. Buying the
        # same tval/sval item back is semantic churn, not shopping progress.
        self._town_visit_sale_signatures: set[tuple[int, int]] = set()
        # Most per-staff charges of an Identify staff sold this visit.  The
        # 2026-10-03 swap sells the emptiest staff to buy a fuller one, which
        # is an upgrade, not a sell-then-rebuy of the same item.
        self._town_visit_sale_identify_charges: int | None = None
        self.town_visit_report: str | None = None
        # A6a: Home remains the preferred source for the two-tool mining kit.
        # The count remains useful as terminal-failure evidence, but no longer
        # authorizes buying around stock that Home still records.
        self._digger_home_withdraw_failures = 0
        self._digger_fallback_bought_this_visit = False
        self._home_procurement_withdraw_failure: dict[str, object] | None = None
        # Prices are learned only from shelves actually shown by the emitter.
        # Values are (unit price, units supplied); no guessed/default shopping
        # price is permitted for the cross-town funds gate.
        self._observed_departure_prices: dict[str, tuple[int, int]] = {}
        self._cross_town_shopping: CrossTownShoppingExpedition | None = None
        self._cross_town_shopping_funds: dict[str, object] = {}
        self._morivant_full_identify: MorivantFullIdentifyExpedition | None = None
        self._morivant_full_identify_attempted: set[
            tuple[tuple[str, int, int], ...]
        ] = set()
        # A fixed quest's carry contract may ask for stock that no supplier has
        # this visit.  Town procurement may waive only those exhausted entries;
        # quest-entry readiness continues to check the original contract.
        self._abandoned_quest_carry_requirements: dict[str, str] = {}
        # Pack-pressure identify verification: items whose identify never lands
        # (device use stalls), plus a watch on the last attempt to detect that
        # the pack's unknown count did not change afterwards.
        self._unidentifiable_sigs: set[tuple[str, int, int]] = set()
        # Carried equipment whose identification sources were exhausted is
        # skipped only for the current town visit.  Unlike the dungeon-facing
        # failure set above, this must survive every in-town observation.
        self._town_unidentifiable_carried_sigs: set[tuple[str, int, int]] = set()
        # Full-*Identify* scrolls may not exist in a game. Remember equipment
        # proven unobtainable across town visits, but retry it if a source later
        # appears in the pack.
        self._unbuyable_full_identify_sigs: set[tuple[str, int, int]] = set()
        self._identify_watch: tuple[tuple[str, int, int], int] | None = None
        self._identify_fail_streak = 0
        self._staged_prompt_chain: dict | None = None
        self._prompt_gated_posting: bool = True
        # Town device identification uses the same staff/scroll flow; guard it the
        # same way (dedicated watch, not reset every town turn) so a device whose
        # identify never lands is deferred instead of looped on.
        self._device_identify_watch: tuple[tuple[str, int, int], int] | None = None
        self._device_identify_fail_streak = 0
        # Rejections are only authoritative for the current town visit.  A full
        # store can reject an otherwise sellable item, so retry it after the next
        # dungeon trip instead of blacklisting it for the whole bot session.
        self._unsellable_items: set[tuple[str, int, int]] = set()
        # Store types that refused a sale this town visit because they are FULL
        # (no room), not because of the item type. While a store is latched here
        # the bot must stop routing spare weapons to it and stop pulling more from
        # Home to sell there — otherwise it churns futile trips to the full store.
        self._store_sale_refused: set[int] = set()
        self._town_blocked_reason: str | None = None
        self._cross_decision_latches["_town_blocked_reason"] = CrossDecisionLatch(
            "town-router",
            "_release_stale_town_block",
            (
                "departure-unsatisfiable",
                "no-safe-recall-destination",
                "guardian-bounce-no-alternate",
                "equipment-work-home-route-exhausted",
                "overweight-home-unreachable",
                "restock-wait-exhausted",
            ),
            retained_values=("repetition",),
            retained_prefixes=("equipment-transaction:",),
            release_sites=("_release_stale_town_block",),
        )
        self._latch_capture_path: Path | None = None
        self._latch_capture_rotate_bytes = 0
        self._latch_capture_generations = 0
        self._latch_capture_previous: dict[str, object] | None = None
        self._latch_capture_assignment: dict[str, object] | None = None
        self._latch_capture_remaining = 0
        self._home_entry_capture = None
        self._departure_block: dict[str, object] = {}
        self._loadout_report_path = None
        self._fundraising_mode: str | None = None
        self._fundraising_run_purpose: FundraisingPurpose | None = None
        self._fundraising_purpose_record: FundraisingPurposeRecord | None = None
        # Unknown on a fresh attachment until save-backed progress proves that
        # Yeek Cave has never been entered.  A restart is not a new character.
        self._fundraising_runs_started: int | None = None
        self._fundraising_affordable_food_seen = False
        self._mining_runs_completed = 0
        self._planned_mining_runs: int | None = None
        self._identify_staff_mining_plan = False
        # Marks the one-run D1 recall-stockout time-pass (not a funding set):
        # the gold set-end leaves it running while the stockout persists.
        self._recall_stockout_mining_plan = False
        # Supply-stockout time-pass state survives town resets/checkpoints;
        # old captures read these with getattr defaults.
        self._supply_stockout_cycles = 0
        self._supply_stockout_gold_target = None
        self._mining_scroll_used_floor: tuple[int, int, int] | None = None
        self._mining_detection_centers: list[Position] = []
        self._sell_scavenged_consumables = False
        self._normal_weapon_name: str | None = None
        self._normal_sub_hand_name: str | None = None
        self._normal_weapon_identity: str | None = None
        self._normal_sub_hand_identity: str | None = None
        self._normal_weapon_is_optimal = False
        self._normal_sub_hand_is_optimal = False
        self._mining_combat_loadout_remembered = False
        self._breakout_dig_floor: tuple[int, int, int] | None = None
        self._no_teleport_rearm_pending = False
        self._yeek_conquest_processed = False
        self._home_pending_item: tuple[str, int, int] | None = None
        self._home_errand = HomeErrandExecutor()
        self._home_random_teleport_withdrawal: tuple[str, int, int] | None = None
        self._home_pending_slot: str | None = None
        self._home_pending_quantity: int | None = None
        self._home_pending_quantities: dict[tuple[str, int, int], int] = {}
        self._home_procurement_batch_active = False
        self._home_pending_batch: list[tuple[str, int, int]] = []
        self._deferred_home_item_sites: dict[tuple[str, int, int], str] = {}
        self._home_batch_review_items: set[tuple[str, int, int]] = set()
        self._home_active_from_batch = False
        # One Home take is bound to a fresh-entry macro.  The pending record is
        # observation-only: it is cleared as success or reported as failure on
        # the first ordinary outside snapshot and is never used to repost.
        self._home_atomic_withdraw_pending: tuple[
            tuple[str, int, int], int, StoreItem, int
        ] | tuple[
            tuple[str, int, int],
            int,
            StoreItem,
            int,
            tuple[tuple[tuple[str, int, int], int, StoreItem, int, int], ...],
        ] | None = None
        self._home_atomic_withdraw_procurement_class: tuple[int, int] | None = None
        self._home_atomic_withdraw_move_identity: str | None = None
        self._home_atomic_withdraw_index: int | None = None
        self._home_atomic_withdraw_posted_turn: int | None = None
        # The pending item whose own posted take was confirmed.  It stays the
        # pending item for carried-item processing, but its withdrawal is done:
        # the atomic composer must neither take it again nor read its shifted
        # shelf slot as a failed withdrawal.  Only a new request for the same
        # identity (``_requeue_home_withdrawal``) makes it withdrawal work
        # again; other work queued beside it does not.
        # Restored checkpoints read None through getattr.
        self._home_pending_take_confirmed: tuple[str, int, int] | None = None
        # Outcome-keyed supervisor for a requested Home take.  The count is in
        # unsatisfied Home-stop passes, not raw decisions, so ordinary page and
        # confirmation latency does not consume the bound.
        self._withdrawal_unsatisfied_for: tuple[
            tuple[str, int, int], int, int, bool
        ] | None = None
        self._withdrawal_unfulfilled_defect: dict[str, object] = {}
        # True only while a charged Identify staff withdrawn from Home is being
        # carried to the Magic shop for sale.  Home used to be a one-way sink:
        # departure readiness counted pack charges only, while useful charged
        # devices in Home were never withdrawn or disposed of.
        self._home_identify_staff_sale_pending = False
        self._home_identify_staff_sold_this_magic_visit = False
        self._home_withdrawal_queued = False
        self._home_digger_withdraw_pending = False
        self._home_candidate_waiting = False
        self._identification_need: str | None = None
        self._identification_candidate: tuple[str, int, int] | None = None
        # An identification errand owns the next source acquired for it.  Keep
        # the acquisition baseline so a pre-existing source remains unreserved
        # and a newly enlarged stack reserves only one unit.
        self._identification_source_reservation: dict[str, object] | None = None
        # A read command is a capability bound to one scroll identity, not to a
        # pack letter.  Loot can insert an item and shift every following letter
        # between composition and the CLI post boundary.
        self._read_binding: (
            tuple[int, int, str, str, dict[str, object] | None] | None
        ) = None
        self.read_telemetry: dict[str, object] = {}
        self._device_identification_candidate: tuple[str, int, int] | None = None
        self._deferred_device_items: set[tuple[str, int, int]] = set()
        self._processed_home_items: set[tuple[str, int, int]] = set()
        self._deferred_home_items: set[tuple[str, int, int]] = set()
        self._retried_deferred_home_items: set[tuple[str, int, int]] = set()
        self._retried_home_identification_items: set[tuple[str, int, int]] = set()
        # ``~9`` is authoritative content knowledge, but its order is not a
        # shelf address.  Keep addresses separately from observed Home pages.
        self._home_knowledge_items: tuple[InventoryItem, ...] = ()
        self._home_knowledge_valid_before = 0
        self._home_knowledge_current = False
        # A purchase is legal only after the current Home catalogue has been
        # evaluated for the same item class.  This latch names the class whose
        # scan/withdrawal owns routing before an ordinary store may compose p.
        self._home_procurement_probe: tuple[int, int] | None = None
        self._home_procurement_fallthrough: str | None = None
        self._home_procurement_fallthrough_equivalence: str | None = None
        self._mana_survival_device_price: int | None = None
        self._home_knowledge_invalidated = False
        self._home_page_size: int | None = None
        self._home_observed_addresses: dict[
            tuple[str, int, int], tuple[int, int, int, str] | None
        ] = {}
        # A knowledge-only withdrawal must visit Home pages until its selector
        # is observed.  Store the target and pages already requested so a
        # missing target terminates after one bounded pass over the Home.
        self._home_withdraw_page_probe: tuple[
            tuple[str, int, int], tuple[int, ...]
        ] | None = None
        # Consumables are deliberately absent from OwnedEquipmentCatalog.  Keep
        # the one Home consumable whose exact stock matters in the complete
        # duplicate-preserving knowledge catalogue.
        self._home_star_remove_curse_count: int | None = None
        self._home_knowledge_scan_requested = False
        self._home_knowledge_scan_inflight = False
        self._home_knowledge_scan_retries_remaining = 1
        self._home_knowledge_scan_epoch: int | None = None
        # Protocol 3 only: the ~f skill list's two-weapon / shield skill_exp,
        # (two_weapon, shield, level read at, town visit epoch read in).
        # None = unknown; see _skill_exp_cache_valid for invalidation.
        self._skill_exp_cache: tuple[int, int, int, int | None] | None = None
        self._skill_exp_request_inflight = False
        # A Home leave can briefly yield an interleaved surface page while the
        # game still owns input in the store loop.  A later turn is positive
        # evidence that an ordinary command was processed after that leave.
        self._home_knowledge_scan_leave_turn: int | None = None
        self._home_scan_source: str | None = None
        self._home_scan_item_count: int | None = None
        self._star_remove_curse_shelf_seen = False
        self._star_remove_curse_reserve_deposit_pending = False
        self._star_remove_curse_reserve_withdraw_pending = False
        self._star_remove_curse_reserve_buy_inflight: tuple[
            tuple[str, int, int], int
        ] | None = None
        self._star_remove_curse_reserve_deposit_inflight: tuple[
            tuple[str, int, int], int
        ] | None = None
        # Full, duplicate-preserving catalog for the complete-loadout optimizer.
        # The legacy dict above remains temporarily for old sale/deposit paths;
        # it is not authoritative for global optimization because its short
        # signature collapses physically distinct identical items.
        self._equipment_catalog = OwnedEquipmentCatalog()
        self._equipment_optimization_signature: tuple | None = None
        self._equipment_optimization_pack_items: int | None = None
        self._equipment_optimization_preparation: (
            WarriorOptimizationPreparation | None
        ) = None
        self._equipment_optimization_timed_out_this_visit = False
        self._equipment_optimization_telemetry: dict[str, object] = {}
        self._equipment_fresh_search_target_ids: frozenset[str] = frozenset()
        self._town_plan_projection_telemetry: dict[str, object] = {
            "evaluated": False,
            "plan_rebuilt": False,
            "rebuilt_stops": [],
        }
        self._equipment_optimization_search_surviving_ids: frozenset[str] = (
            frozenset()
        )
        self._warrior_evaluator_cache = WarriorEvaluatorCache()
        # Constants from session-correlated equipped character dumps.
        self._character_calibration: CharacterCalibration | None = None
        self._character_calibration_path: Path | None = None
        self._character_calibration_loaded = False
        self._character_dump_path: Path | None = None
        self._calibration_dump_prepared = None
        self._calibration_dump_pending = None
        # The correlated C response, held until its posted dump completes.
        self._calibration_dump_response = None
        self._calibration_unavailable_reason = None
        self._calibration_rejection = None
        # One identity per bot process: a persisted equipped record is
        # accepted only from this process (policies of one process agree).
        from hengbot.policy_calibration import process_calibration_session_id
        self._calibration_session_id = process_calibration_session_id()
        self._character_response_sequence = None
        self._confirmed_loadout: ConfirmedLoadoutRecord | None = None
        self._confirmed_loadout_path: Path | None = None
        self._confirmed_loadout_loaded = False
        self._equipment_optimizer_input_key: str | None = None
        self._equipment_optimizer_knowledge_key: str | None = None
        # Ordinary town-order operations retain their observation identity.
        self._town_order_operation: str | None = None
        self._town_order_expected_observation: str | None = None
        # Refreshed by the existing periodic character observation.
        self._mutation_signature: tuple[int, ...] | None = None
        self._equipment_transaction_session: EquipmentTransactionSession | None = None
        # #8 record-only explicit executor grants.  A reserved child binds to
        # the parent's claim at the choose_key exit, before the next gate.
        self._execution_delegations: list[ExecutionDelegation] = []
        self._equipment_atomic_withdraw_leave_count = 0
        # Physical equipment removed by the live optimizer transaction remains
        # owned by that transaction until it is observed worn again.  This is
        # deliberately independent of the town-owner gate: classifiers must
        # still refuse these pack items if routing ever bypasses that gate.
        self._equipment_transaction_owned_items: list[tuple[str, str]] = []
        self._cross_decision_latches[
            "_equipment_transaction_owned_items"
        ] = CrossDecisionLatch(
            "equipment-transaction",
            "_equipment_ownership_release_due",
            release_sites=(
                "_release_equipment_transaction_owned_item",
                "_abandon_blocked_equipment_transaction",
            ),
        )
        self._equipment_transaction_restoring = False
        self._equipment_transaction_restore_terminal: str | None = None
        self._equipment_transaction_restore_remainder: tuple[str, ...] = ()
        self._equipment_transaction_route_abandonment: tuple[
            str, str, object
        ] | None = None
        self._equipment_transaction_route_terminal_pending = False
        self._equipment_transaction_route_terminal: str | None = None
        self._equipment_transaction_failed_items: set[str] = set()
        # A structurally actionless failed transaction may retire for the
        # remainder of this town visit.  Pin the confirmed worn identities as
        # the optimizer target as well as clearing the blocker: otherwise the
        # next rebuild can select the same failed item and recreate work.
        self._equipment_retired_worn_item_ids: frozenset[str] = frozenset()
        self._equipment_transaction_last_failure: dict[str, object] | None = None
        self._equipment_transaction_prepared_key: str | None = None
        self._equipment_transaction_prepared_catalog_update: tuple[
            str, object, tuple[object, ...]
        ] | None = None
        self._equipment_transaction_posted_catalog_update = None
        self._equipment_transaction_home_pages = None
        self._equipment_optional_failure_departure = None
        self._equipment_optional_failure_pending = None
        # Item ids readmitted to the optimizer view because a quarantine held
        # every owned source of a mandatory depth gate (strictly diagnostic).
        self._equipment_quarantine_readmitted_ids: tuple[str, ...] = ()
        # Monotonic second-chance ledger for last-source quarantine escapes.
        # An id enters second_chance when the release valve or the last-source
        # readmission puts it back in the optimizer view; if it is quarantined
        # AGAIN afterwards it is burned and never released or readmitted for
        # the rest of the town visit.  Each owned source is therefore retried
        # at most once per visit and the withdraw->stall->release->withdraw
        # cycle is structurally impossible: the candidate set only shrinks.
        # Both sets share the failed-item lifecycle (cleared on town entry).
        self._equipment_quarantine_second_chance_ids: set[str] = set()
        self._equipment_quarantine_burned_ids: set[str] = set()
        # Depth the last optimization pass was asked about, for diagnostics
        # emitted when no snapshot is at hand.
        self._equipment_optimization_last_depth: int | None = None
        self._pending_disposal_slot: str | None = None
        self._pending_disposal_item: tuple[str, int, int] | None = None
        self._disposal_store_attempts: set[int] = set()
        self._destroy_pending = False
        self._destroy_attempts = 0
        # The emitter can interleave a store-loop snapshot with a main-loop
        # town snapshot at the same door tile. Retain one decision of store
        # context so a latched town stop closes that UI before it waits.
        self._last_snapshot_was_store = False
        self._last_snapshot_store_type: int | None = None
        # Full-pack disposal verification: signatures of items the game would not
        # destroy (so we stop re-selecting them and forever looping), plus a watch
        # on the last attempt to detect that the pack did not change afterwards.
        self._undestroyable_sigs: set[tuple[str, int, int]] = set()
        self._destroy_watch: tuple[tuple[str, int, int], int, int] | None = None
        self._destroy_fail_streak = 0
        self.last_reason = ""
        self.prompt_owner_handoff: str | None = None
        self._policy_state_version = 4
        self._execution_pending_post = None
        self._decision_goal = None
        self._decision_expectation = None
        self._decision_triggers = None
        self._decision_bar_skips = None
        self._hunt_step_target = None

    def __setstate__(self, state):
        # Direct unpickle and deepcopy: upgrade an older state; a current
        # state is copied exactly, so a copy decides as its original does.
        self.__dict__.update(state)
        from hengbot.policy_state import normalize_policy_state
        normalize_policy_state(self)

    # ------------------------------------------------------------------ core
    def _with_grid_memory(self, snapshot: Snapshot) -> Snapshot:
        """Merge this observation with terrain seen earlier in the floor visit.

        Missing grids are normally dark, unmarked floor rather than unknown
        terrain. Monster occupancy is different: it is authoritative only in the
        current snapshot and must never survive after its grid leaves view.
        """
        # A store page without grids is not a terrain observation.  In
        # particular, its metadata must not select/reset a terrain region: the
        # store prompt has not moved the player or changed the surface map, and
        # every store decision which needs an entrance/grid fact must see the
        # retained last surface observation.  Map-bearing store pages from an
        # older emitter continue through the ordinary merge below.
        if snapshot.store is not None and not snapshot.grids:
            return replace(snapshot, grids=dict(self._remembered_grids))

        # Every surface view uses floor_key=(0, 0, 0), including fixed towns,
        # local wilderness, and the differently-sized global map.  Terrain from
        # one of those coordinate spaces must never leak into another one.
        region = (
            *snapshot.floor_key,
            snapshot.width,
            snapshot.height,
            snapshot.town_id,
            snapshot.in_town,
        )
        if self._remembered_grid_region != region:
            self._remembered_grid_region = region
            self._remembered_grids = {}
            self._remembered_grid_signatures = {}
            self._remembered_grid_sources = {}
        self._scope_terrain_to_town(snapshot)

        remembered = self._remembered_grids
        for position, grid in snapshot.grids.items():
            if self._remembered_grid_sources.get(position) is grid:
                continue
            signature = _persistent_grid_signature(grid)
            self._remembered_grid_sources[position] = grid
            if self._remembered_grid_signatures.get(position) == signature:
                continue
            self._remembered_grid_signatures[position] = signature
            remembered[position] = replace(
                grid,
                has_monster=False,
                monster_index=0,
                object_count=0,
                object_tvals=(),
                lit=False,
                in_view=False,
                # Protocol 3 lighting variant: how the map draws the cell now.
                map_lighting=None,
                currently_observed=False,
            )
        merged = dict(remembered)
        merged.update(snapshot.grids)
        return replace(snapshot, grids=merged)

    @staticmethod
    def _grid_region(snapshot: Snapshot) -> tuple[int, int, int, int, int, int, bool]:
        return (
            *getattr(snapshot, "floor_key", (0, 0, 0)),
            getattr(snapshot, "width", 0),
            getattr(snapshot, "height", 0),
            getattr(snapshot, "town_id", -1),
            getattr(snapshot, "in_town", False),
        )


    def _begin_map_predicate_cache(self, snapshot: Snapshot) -> None:
        self._map_predicate_snapshot = snapshot
        self._fixed_quest_offers = frozenset(
            grid.building_special
            for grid in snapshot.grids.values()
            if grid.building_special
        )
        self._hazard_cache.clear()
        self._town_border_cache.clear()
        self._refresh_town_facts(snapshot)

    @reservation_decision
    def choose_key(self, snapshot: Snapshot) -> str | None:
        # Recorded checkpoints predating full-Home recovery lack these fields.
        self._home_capacity_observation = getattr(self, "_home_capacity_observation", None)
        self._home_full_relief = getattr(self, "_home_full_relief", None)
        self._home_full_refused = getattr(self, "_home_full_refused", False)
        self._home_full_retry_deposits = getattr(self, "_home_full_retry_deposits", None)
        from hengbot.policy_state import normalize_policy_state
        normalize_policy_state(self)
        self._observe_cross_town_shopping_arrival(snapshot)
        # A decision board is emitted only after the posted C macro returned
        # to the main loop, so its dump file is complete: read it once now.
        self._complete_character_dump(snapshot)
        # A producer that never reached the previous decision's claim exit
        # cannot carry an unbound grant into this decision.
        self._cancel_unbound_execution_delegations()
        # S2a.1 (design rev 9 item 2): the per-decision goal slot.  Only a
        # producer writes it, on the board whose key uses its target; the
        # declaration at the exit reads nothing else.  Record-only.
        self._decision_goal = None
        self._decision_expectation = None
        self._decision_non_discardable = None
        self._decision_displaced_producer = None
        self._decision_plan_rebuild_deferred = 0
        self._decision_plan_change_evidence = None
        self._decision_home_approach_fails_before = (
            self._town_visit_ledger.approach_fails[STORE_HOME]
        )
        # S2b.1 (rev 10.1 item 9): the trigger monsters a producer declares.
        self._decision_triggers = None
        # S2b.2: the rungs the bar skipped on this decision (switch on only).
        self._decision_bar_skips = None
        self._decision_errand_deferred = []
        self._decision_gate_final_count = 0
        self._decision_rewrite_refused = []
        self._decision_no_step_release = False
        self._decision_cancelled_home_reservation = None
        self._observe_home_atomic_deposit_outside(snapshot)
        self._observe_home_full_identification(snapshot)
        # Round 4 (F3): an armed path-target capture never outlives the
        # decision that armed it (each arm/take pair is also try/finally).
        self.__dict__.pop("_claim_target_capture", None)
        self._staged_prompt_chain = None
        self._intentional_entrance_activation = False
        pending_reward = self._fixed_quest_reward_pending
        if pending_reward is not None:
            town_reward = FIXED_QUEST_REWARD_POSITIONS.get(pending_reward)
            if (
                town_reward is None
                or snapshot.town_id not in {-1, town_reward[0]}
            ):
                self._fixed_quest_reward_pending = None
        # Snapshot-derived answers must never survive a public decision
        # boundary, even when a caller reuses and mutates a Snapshot object.
        self._fixed_quest_offer_cache = {}
        self._fixed_quest_head_cache = {}
        self._disposable_armour_cache = None
        # The public boundary is also the diagnostic boundary: capture hooks
        # checkpoint policy state before delegating to ``_choose_key``.  Keep
        # the carried catalogue authoritative here so a freshly observed
        # strip cannot be recorded (or reasoned about) beside the preceding
        # decision's worn set.
        # Combat ends the current entrance-approach episode.  Reset on the
        # following public decision before a resumed route can add to the old
        # count; ordinary route relabelling keeps existing replay behaviour.
        if self._shop_approach_stuck_count and (
            self.last_reason == "melee"
            or (self.last_reason or "").startswith("ranged:")
        ):
            self._shop_approach_stuck_count = 0
            self._shop_approach_stuck_store = None
            self._shop_approach_previous_origin = None
            self._staged_shop_approach = None
            self._pending_shop_approach = None
        self._acquire_store_visit_attempt = {
            "acquire_store_visit_called": False,
            "requested_owner": None,
            "requested_store": None,
            "acquire_result": None,
        }
        self.prompt_owner_handoff = None
        self._town_progress_invariant_defect = {}
        self._withdrawal_unfulfilled_defect = {}
        self._town_liveness_invariant_defect = {}
        self._town_liveness_claim_retired = False
        arbiter = getattr(self, "_town_turn_arbiter", None)
        if arbiter is None:
            # restore_checkpoint upgrades older captures with this explicit
            # slot; reconstruct its advisory observer on first use.
            arbiter = _new_town_turn_arbiter()
            self._town_turn_arbiter = arbiter
        self._decision_context = DecisionContext(
            equipment_transaction_owned=(
                self._equipment_transaction_session is not None
            ),
            identity=self._decision_sequence + 1,
        )
        snapshot = self._with_cached_skill_exp(snapshot)
        # Protocol 3: before any evaluator needs the two-weapon / shield
        # skill_exp, read them off the ~f skill list.  Like the look probe
        # below, this observation-only key costs no game time and is not a
        # policy turn: no decision bookkeeping runs, so the decision on the
        # unchanged board that follows is the one the bot would have made.
        # Probes and terminal results finish one decision block.
        # Every envelope reaches final enforcement and claim recording.
        for _decision_pass in (None,):
            skill_request = self._skill_exp_request_key(snapshot)
            if skill_request is not None:
                arbiter.observe(
                    in_town=bool(snapshot.in_town or snapshot.store is not None),
                    reason=self.last_reason,
                    progress_vector=self._town_arbiter_progress_vector(
                        snapshot, self.last_reason
                    ),
                    probe=True,
                    retirement_key_for=lambda owner: self._town_retirement_clearance_key(
                        snapshot, owner
                    ),
                )
                self.decision_attribution = arbiter.decision_owner_for_reason(
                    self.last_reason
                )
                key = skill_request
                break
            self._refresh_carried_equipment_catalog(snapshot)
            self._request_priority_body_rearm(snapshot)
            current_progress_core = self._owner_progress_core(snapshot)
            refusal_probe = self._posting_refusal_probe
            if refusal_probe is not None:
                self._posting_refusal_probe = None
                refusal_owner, refusal_core = refusal_probe
                if replace(
                    current_progress_core, decision_sequence=0
                ) == replace(refusal_core, decision_sequence=0):
                    # The probe is the explicit observation barrier after any
                    # sender-side refusal.  A stair watch may belong to an older,
                    # successfully accepted decision (for example when an
                    # interleaved Home scan was refused before the stair result
                    # arrived).  Keeping that watch across the identity-breaking
                    # probe makes the recovered stair key disappear into
                    # stair:await-observation forever.  Release it here: the next
                    # decision either reposts the stair against the new identity or
                    # routes elsewhere visibly.
                    if self._pending_stair_command is not None:
                        self._pending_stair_command = None
                        self._owner_expectations.release("stair-command")
                    self._last_policy_progress_core = current_progress_core
                    decided_reason = self.last_reason
                    key = self._look_probe_key(snapshot)
                    # G2: this observation-only key breaks the posting identity;
                    # it is not a policy turn and cannot replace the last decided
                    # owner's reason.
                    self.last_reason = decided_reason
                    arbiter.observe(
                        in_town=bool(snapshot.in_town or snapshot.store is not None),
                        reason=refusal_owner,
                        progress_vector=self._town_arbiter_progress_vector(
                            snapshot, refusal_owner
                        ),
                        probe=True,
                        retirement_key_for=lambda owner: self._town_retirement_clearance_key(
                            snapshot, owner
                        ),
                    )
                    self.decision_attribution = arbiter.decision_owner_for_reason(
                        decided_reason
                    )
                    break
            self._last_policy_progress_core = current_progress_core
            if (getattr(self, "_town_claim_bar_enforced", False)
                    and (snapshot.in_town or snapshot.store is not None)):
                # Finish an observed arrival or store entry before asking the next
                # town producer.  Otherwise its entry gate sees yesterday's route.
                standing = getattr(self._claim_register, "current", None)
                if standing is not None and standing.is_open:
                    self._claim_exit_completion(snapshot, standing, [])
                self._observe_execution_delegations()
                self._retire_finished_home_errand_plan_stop()
            home_capture = self._home_entry_capture
            def choose_ladder():
                chosen = (home_capture.choose_key(self, snapshot)
                          if home_capture is not None
                          else self._choose_key_with_latch_capture(snapshot))
                return self._enforce_town_claim_result(snapshot, chosen)

            key = choose_ladder()
            if (getattr(self, "_town_claim_bar_enforced", False)
                    and (snapshot.in_town or snapshot.store is not None)
                    and not self._warning_prompt_stops_decision):
                retried = set()
                released_any = False
                while (key is None and not self._decision_gate_final_count
                       and not (self.last_reason or "").startswith((
                    "ownership:holder-silent:", "ownership:declaration-",
                    "ownership:gate-missing:", "ownership:item-reserved:",
                ))):
                    holder = self._claim_errand_hold("__none__")
                    if holder is not None:
                        if holder.claim_id in retried:
                            key = self._town_holder_ladder_result(holder, snapshot)
                            break
                        retried.add(holder.claim_id)
                        if holder is getattr(self._claim_register, "current", None):
                            self._claim_exit_completion(snapshot, holder, [])
                        holder = self._claim_errand_hold("__none__")
                        if holder is not None:
                            key = self._town_holder_ladder_result(holder, snapshot)
                            if key is not None or (self.last_reason or "").startswith((
                                "ownership:holder-silent:", "ownership:declaration-",
                            )):
                                break
                            if not getattr(self, "_decision_no_step_release", False):
                                break
                    elif not getattr(self, "_decision_no_step_release", False):
                        break
                    # An observed completion or named release gives the next
                    # eligible producer the same immutable board.
                    released_any = released_any or self._decision_no_step_release
                    self._decision_no_step_release = False
                    self._decision_errand_deferred = []
                    key = choose_ladder()
                if (key == "" and (self.last_reason or "").startswith(
                    "ownership:holder-await:home-scan"
                )):
                    key = WAIT_KEY
                    self.last_reason = "home:scan-await-observation"
                if (key is None and (released_any or self._decision_no_step_release)
                        and self._claim_errand_hold("__none__") is None):
                    self.last_reason = "town:blocked:owner-retired"
                    key = WAIT_KEY
                if (self.last_reason or "").startswith((
                    "ownership:holder-silent:", "ownership:declaration-",
                    "ownership:gate-missing:", "ownership:item-reserved:",
                )):
                    key = None
                    break
            # The producers below commit the store visit to the key they return:
            # an in-store leave arms _store_leave_inflight and a composed one-shot
            # marks operation_posted.  Every rewrite between here and the return
            # can replace that key, so remember what the commitment was bound to.
            decided_key = key
            decided_visit = self._store_visit
            if (
                key == WAIT_KEY
                and self.last_reason == "warning:blocked-step"
                and any(
                    home_page_message_body(message).startswith(
                        WARNING_PROMPT_MESSAGE_PREFIXES
                    )
                    for message in snapshot.messages
                )
            ):
                # The prompt-bearing fixed-quest snapshot has no alternative rung;
                # preserve its no-command seam after the refusal was processed.
                # A later snapshot without the stale prompt returns the ordinary
                # warning:blocked-step wait, while the CLI now bounds quiet None.
                key = None
                break
            if key is None and self._warning_prompt_stops_decision:
                key = None
                break
            if (
                key
                and (self.last_reason or "").startswith("equipment-transaction:")
                and not (self.last_reason or "").startswith(
                    "equipment-transaction:await-"
                )
            ):
                self._post_owner_expectation(
                    snapshot,
                    "equipment-transaction",
                    "inventory",
                    "equipment",
                    "store_type",
                    "gold",
                )
            holder_for_key = self._town_held_decision(key)
            if holder_for_key is not None:
                self._town_refuse_rewrite("no-progress", holder_for_key)
            else:
                key = self._refuse_no_progress_cycle(snapshot, key)
            key = self._enforce_town_claim_result(snapshot, key)
            if (self.last_reason or "").startswith("ownership:gate-missing:"):
                key = None
                break
            holder_for_key = self._town_held_decision(key)
            if holder_for_key is not None:
                self._town_refuse_rewrite("procurement", holder_for_key)
            else:
                procurement_key = self._town_procurement_decision(snapshot, key)
                if procurement_key is not None:
                    key = procurement_key
                if (
                    self._town_blocked_reason
                    == "town:blocked:home-withdraw-failed-stock-present"
                ):
                    key = WAIT_KEY
                    self.last_reason = self._town_blocked_reason
            if self._withdrawal_unfulfilled_defect:
                self._record_shop_selector_diagnostics(snapshot, key)
            unresolved_quest_candidate = (
                key
                if isinstance(key, DecisionCandidate)
                and key.reason in {
                    "fixedquest:q22-travel:route-unavailable",
                    "fixedquest:prepare-return:route-unavailable",
                    "quest:enter:approach:route-unavailable",
                    "fixedquest:claim:approach:route-unavailable",
                    "fixedquest:request:approach:route-unavailable",
                    "fixedquest:reward-approach:route-unavailable",
                }
                else None
            )
            unresolved_quest_reason = (
                unresolved_quest_candidate.reason
                if unresolved_quest_candidate is not None else None
            )
            # Safety detector rewrites below are judged on their own evidence,
            # after the holder's producer and the two retirement rewrites have
            # passed the holder check. They do not masquerade as another errand.
            key = self._forbid_wait_while_damaged(snapshot, key)
            # USER DECISION 2026-10-03: the last word on a walking move at low HP
            # or right after a hit, after every producer and the no-wait rewrite.
            key = self._low_hp_walk_gate(snapshot, key)
            # A shot or throw may leave a summoner a counter-attack target (the
            # summoner emergency's reach, USER DECISION 2026-10-03 06:1x).
            self._note_summoner_counter_targets(snapshot, key)
            if (
                unresolved_quest_candidate is not None
                and key is not unresolved_quest_candidate
                and key == WAIT_KEY
            ):
                unresolved_reason = unresolved_quest_candidate.reason
                unresolved_vector = self._town_arbiter_progress_vector(
                    snapshot, unresolved_reason, unresolved_quest_candidate
                )
                unresolved_clearance = self._town_retirement_clearance_key(
                    snapshot, "quest-request", unresolved_reason,
                    unresolved_quest_candidate,
                )
                if not arbiter.preview_may_select(
                    unresolved_reason, unresolved_vector,
                    retirement_key=unresolved_clearance,
                ):
                    # A no-op rewrite must not erase the exact unresolved claim
                    # once that claim has retired.  A real safety action keeps its
                    # detector ownership and always wins over quest arbitration.
                    key = unresolved_quest_candidate
                    self.last_reason = unresolved_reason
            vector = self._town_arbiter_progress_vector(snapshot, self.last_reason, key)
            in_town = bool(snapshot.in_town or snapshot.store is not None)
            arbiter.observe(
                in_town=in_town,
                reason=self.last_reason,
                progress_vector=vector,
                probe=True,
                retirement_key_for=lambda owner: self._town_retirement_clearance_key(
                    snapshot, owner, self.last_reason
                ),
            )
            current_owner = arbiter.owner_for_reason(self.last_reason)
            current_retirement_key = self._town_retirement_clearance_key(
                snapshot, current_owner, self.last_reason,
                key if isinstance(key, DecisionCandidate) else None,
            )
            town_kill_owns_visible_target = (
                (
                    (self.last_reason or "").startswith("town:kill-mob")
                    or self.last_reason == "melee"
                )
                and any(not monster.pet for monster in snapshot.visible_monsters)
            )
            town_order_owns_step4 = bool(
                self._town_order_operation == "normal-step4-bounty"
                and self._town_order_step4_pending(snapshot)
                and (self.last_reason or "").startswith("bounty:")
            )
            held_claim_decision = self._town_held_decision(key) is not None
            visit = self._store_visit
            posted_shop_observation_wait = bool(
                getattr(self, "_town_claim_bar_enforced", False)
                and key == ""
                and self.last_reason == "shop:one-shot-in-flight"
                and visit is not None
                and visit.operation_posted
                and not visit.operation_effect_observed
                and visit.claim_operation_identity is not None
                and (not visit.operation_released
                     or self._store_buy_inflight is not None
                     or (self._batch_sell_pending is not None
                         and self._batch_sell_pending.get("phase") == "await-sale"))
            )
            if (
                in_town
                and not town_kill_owns_visible_target
                and not town_order_owns_step4
                and not held_claim_decision
                and not posted_shop_observation_wait
                and not arbiter.preview_may_select(
                    self.last_reason, vector, retirement_key=current_retirement_key
                )
            ):
                rejected_candidate = key
                retired_owner = arbiter.owner_for_reason(self.last_reason)
                self._arbiter_close_store_visit(retired_owner, "arbiter-retired-claim")
                supplier = self._departure_supplier_counterfactual(snapshot)
                step = (
                    self._shopping_approach_step(
                        snapshot, supplier, router_plan_stop=True
                    )
                    if (
                        supplier is not None
                        and snapshot.store is None
                        and retired_owner != "store-router"
                        and not self._defer_town_errand(
                            "store-router", "counterfactual-approach"
                        )
                        and arbiter.preview_may_select(
                            "shop:approach",
                            self._town_arbiter_progress_vector(snapshot, "shop:approach"),
                            retirement_key=self._town_retirement_clearance_key(
                                snapshot, arbiter.owner_for_reason("shop:approach"),
                                "shop:approach",
                            ),
                        )
                    )
                    else None
                )
                if self._route_unavailable_terminal_candidate(
                    rejected_candidate, key
                ):
                    self.last_reason = (
                        "fixedquest:prepare-return:unsatisfiable"
                        if rejected_candidate.reason.startswith(
                            "fixedquest:prepare-return:"
                        ) else (
                            "quest:enter:approach:unsatisfiable"
                            if rejected_candidate.reason.startswith(
                                "quest:enter:approach:"
                            ) else (
                                rejected_candidate.reason.replace(
                                    ":route-unavailable", ":unsatisfiable"
                                ) if rejected_candidate.reason.startswith(
                                    ("fixedquest:claim:approach:",
                                     "fixedquest:request:approach:",
                                     "fixedquest:reward-approach:")
                                ) else "fixedquest:q22-travel:unsatisfiable"
                            )
                        )
                    )
                    key = WAIT_KEY
                elif step is not None:
                    transaction_owns_relocation = (
                        self._equipment_transaction_owns_town_relocation(snapshot)
                    )
                    foreign_relocation = (
                        self._shopping_approach_store_type != STORE_HOME
                    )
                    if transaction_owns_relocation and foreign_relocation:
                        # Arbitration may retire the transaction's claim, but it
                        # cannot hand the remainder of this decision to a foreign
                        # locomotion owner.  Preserve an executor WAIT unchanged;
                        # a progressing key must instead converge on the existing
                        # named terminal rather than becoming an unnamed WAIT.
                        if key != WAIT_KEY:
                            self.last_reason = "town:blocked:owner-retired"
                            key = WAIT_KEY
                    elif not transaction_owns_relocation:
                        self.last_reason = "shop:approach"
                        key = self._shopping_approach_key(snapshot, step, "shop:travel")
                else:
                    self.last_reason = "town:blocked:owner-retired"
                    key = WAIT_KEY
                vector = self._town_arbiter_progress_vector(snapshot, self.last_reason)
            elif (in_town and held_claim_decision
                  and not arbiter.preview_may_select(
                      self.last_reason, vector,
                      retirement_key=current_retirement_key)):
                self._town_refuse_rewrite(
                    "arbiter-retirement", self._town_held_decision(key))
            if snapshot.store is not None and key in DIRECTION_KEYS.values():
                # This is the final policy emission seam.  No producer or
                # downstream town owner may post a bare direction into Hengband's
                # store command loop; leave through its established command path.
                self.last_reason = "store:direction-refused-leave"
                key = LEAVE_STORE_KEY
                vector = self._town_arbiter_progress_vector(snapshot, self.last_reason)
            # This is the first mutating accounting point and follows every key
            # rewrite.  Only the exact surviving envelope can authorize a route.
            final_candidate = key if isinstance(key, DecisionCandidate) else None
            vector = self._town_arbiter_progress_vector(
                snapshot, self.last_reason, final_candidate
            )
            terminal = self._town_arbiter_terminal_result(key)
            arbiter.observe(
                in_town=bool(snapshot.in_town or snapshot.store is not None),
                reason=self.last_reason,
                progress_vector=vector,
                terminal=terminal,
                observation_wait=(posted_shop_observation_wait or bool(
                    key == ""
                    and self._store_visit is not None
                    and self._store_visit.operation_posted
                    and not self._store_visit.operation_released
                )),
                close_visit=self._arbiter_close_store_visit,
                retirement_key=self._town_retirement_clearance_key(
                    snapshot, arbiter.owner_for_reason(self.last_reason),
                    self.last_reason, final_candidate,
                ),
                retirement_key_for=lambda owner: self._town_retirement_clearance_key(
                    snapshot, owner,
                    unresolved_quest_reason
                    if owner == "quest-request" and unresolved_quest_reason is not None
                    else self.last_reason,
                    final_candidate if owner == arbiter.owner_for_reason(self.last_reason) else None,
                ),
            )
            self.decision_attribution = arbiter.decision_owner_for_reason(self.last_reason)
            if self.last_reason in {"shop:await-leave-confirmation",
                                    "shop:await-leave-generation"}:
                self.decision_attribution = self._visit_exit_family()
            if (
                self._equipment_transaction_session is None
                and STORE_HOME in self._town_visit_ledger.blocked_stores
                and self._store_visit is not None
                and self._store_visit.store_type == STORE_HOME
            ):
                # E5: locomotion metrics belong only to a live owner.  Close the
                # retired Home approach after observation so a same-decision
                # counterfactual cannot leak its target across owner stamps.
                self._close_store_visit("equipment-transaction-owner-retired")
                self._release_claim_goal(
                    "shop-approach:equipment-transaction-owner-retired",
                    self._shopping_approach_goal,
                    owners=CLAIM_ENTRANCE_OWNERS,
                )
                self._shopping_approach_goal = None
                self._release_town_travel_claim(
                    "town-travel:equipment-transaction-owner-retired"
                )
                self._town_travel_state = None
                self._town_travel_fallback = None
            here = snapshot.grid_at(snapshot.player.position)
            if (
                key == WAIT_KEY
                and here is not None
                and here.store_number == STORE_HOME
                and self._home_pending_item is not None
                and self._shopping_approach_store_type == STORE_HOME
                and self._shopping_approach_goal == snapshot.player.position
                and not (self.last_reason or "").startswith("town:blocked:")
            ):
                self._intentional_entrance_activation = True
            if (self.last_reason or "").startswith("town:blocked:"):
                self._intentional_entrance_activation = False
            if (
                key == WAIT_KEY
                and snapshot.in_town
                and snapshot.store is None
                and here is not None
                and (
                    here.has_entrance
                    or here.store_number >= 0
                    or here.building_special >= 0
                )
                and not self._intentional_entrance_activation
                and not (self.last_reason or "").startswith(
                    "quest:enter:approach:unsatisfiable"
                )
            ):
                # This is the final emitted-envelope seam, after every owner and
                # stage-2 accounting mutation has observed the producer's original
                # WAIT claim.  Hengband interprets that byte as entrance activation.
                wait_reason = self.last_reason
                key = self._town_entrance_step_off_key(snapshot, wait_reason)
                if (wait_reason or "").startswith("fixedquest:prepare-return"):
                    # Stage-2 quest-travel arbitration/accounting remains owned by
                    # its original producer even though the emitted byte is the
                    # safety step-off envelope.
                    self.last_reason = wait_reason
                if key == WAIT_KEY:
                    key = ""
                    if not (wait_reason or "").startswith(
                        "fixedquest:prepare-return"
                    ):
                        self.last_reason = (
                            f"town:entrance-wait-refused:{wait_reason or 'wait'}"
                        )
            self._release_rewritten_store_posting(decided_visit, decided_key, key)
            self._release_rewritten_prompt_chain(key)
            # A candidate can be discarded by town arbitration and retried on the
            # same board. Only the final envelope has a posted stair identity.
            self._remember_stair_command(snapshot, key)
            if getattr(self, "_crossarea_fundraising_enforced", False):
                if key and key[0] == UP_STAIRS_KEY and self.last_reason == "fundraise:ascend":
                    self._post_fundraising_transport(snapshot, "return")
                elif (key and key[0] == DOWN_STAIRS_KEY
                      and self.last_reason == "descend" and snapshot.in_town
                      and self._fundraising_mode in {"mine", "scavenge"}):
                    self._fundraising_runs_started = (
                        (self._fundraising_runs_started or 0) + 1
                    )
                    self._post_fundraising_transport(snapshot, "depart")
            if (getattr(self, "_town_claim_bar_enforced", False)
                    and self._town_unbound_entry_wait(key)):
                # The holder check above gave procurement a chance to replace the
                # empty wait.  If no route exists, stop visibly rather than emit
                # an undeclared observation from an unposted visit.
                self.last_reason = "ownership:declaration-missing:store-router"
                key = None
                break
        key = self._enforce_town_claim_result(snapshot, key)
        self._record_decision_claim(snapshot, key)
        return key

    # -- S1 attribution (SOL-DESIGN-ownership-contract.md 3.1, 4, 6/S1) ----
    #
    # Recording only.  Nothing below is read back by a producer, the ladder or
    # the driver, and no branch here can reach a key or a reason.

    def claim(self, owner, goal: Goal, *, non_discardable: bool = False):
        """``with self.claim(owner, goal):`` -- the marker of design 5.1.

        With recording switched off (``_claim_register is None``) the scope
        still works and declares into a register nobody reads, so disabling
        the recording cannot change what a producer does.
        """
        register = getattr(self, "_claim_register", None)
        return ClaimScope(
            register if register is not None else ClaimRegister(),
            owner,
            goal,
            non_discardable=non_discardable,
            opened_sequence=self._decision_sequence,
        )

    # -- S2a.1 goal slot and closing paths (design rev 9.1/9.2) -------------
    #
    # Every helper below is record-only: it writes the per-decision goal slot
    # or calls the claim register, and returns nothing a producer reads.  A
    # producer calls them on the board that uses its own target; the
    # declaration at the ``choose_key`` exit reads only the slot.

    def _visit_exit_family(self) -> str:
        """Return the captured operation's owner for a store leave barrier."""
        visit = getattr(self, "_store_visit", None)
        producer = getattr(visit, "operation_producer_family", None)
        if producer in CLAIM_S3_FAMILIES:
            return producer
        requester = getattr(visit, "exit_requester", None)
        if (requester in CLAIM_S3_FAMILIES
                and requester in getattr(visit, "requester_families", ())):
            return requester
        return "barrier-provenance-missing"

    def _claim_family_of(self, reason: str | None) -> str:
        """The census family of a reason, answered by the live arbiter."""
        if reason == "shop:in-store-done":
            # A sale's no-effect exit is still that seller's operation. The
            # acting owner declares it; the generic reason cannot turn it into
            # a competing buyer while the sale observation is outstanding.
            for offer in reversed(self._execution_offers_for()):
                if offer[0] == LEAVE_STORE_KEY and offer[2] == "shop:in-store-leave":
                    return offer[1]
        if reason == "home:request-knowledge-scan":
            # The scan can be a step of registered equipment catalogue work,
            # rather than a new errand. Require the producer's explicit offer.
            for offer in reversed(self._execution_offers_for()):
                if (offer[2] == "equipment:acquire-home-catalog"
                        and offer[5] == "home-catalog-available"
                        and offer[0] == HOME_KNOWLEDGE_MACRO):
                    return offer[1]
        if reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}:
            return self._visit_exit_family()
        if reason and reason.startswith("town:entrance-step-off:"):
            return self._claim_family_of(reason.split(":", 2)[2])
        if reason and reason.startswith((
            "home:atomic-withdraw-target-unobserved",
            "home:atomic-withdraw-slot-unobserved",
            "home:atomic-withdraw-address-invalid",
        )):
            previous = getattr(getattr(self, "_claim_register", None), "current", None)
            if (previous is not None and previous.owner.value in {'equipment-txn'}):
                return previous.owner.value
        visit = getattr(self, "_store_visit", None)
        if reason in {"shop:one-shot-in-flight", "store:entry-await-observation"}:
            family = (
                getattr(visit, "operation_producer_family", None)
                or getattr(visit, "claim_owner", None)
                or getattr(visit, "opened_producer_family", None)
            )
            if family in CLAIM_S3_FAMILIES:
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
        current = getattr(getattr(self, "_claim_register", None), "current", None)
        if (reason and reason.startswith(('home:leave-', 'home:store-context-exit')) and (current is not None) and current.is_open and (current.owner.value in {'equipment-txn'}) and (current.goal.source in {'transaction'})):
            return current.owner.value
        composing_family = getattr(visit, "operation_producer_family", None)
        if composing_family is None:
            composing_family = getattr(visit, "opened_producer_family", None)
        if (reason and reason.startswith('home:atomic-') and (composing_family in {'equipment-txn'})):
            return composing_family
        if reason and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:leave-', 'home:store-context-exit')) and (composing_family in {'equipment-txn'}) and (getattr(self, '_home_atomic_deposit_pending', None) is not None or getattr(self, '_home_atomic_withdraw_pending', None) is not None):
            return composing_family
        arbiter = getattr(self, "_town_turn_arbiter", None)
        if arbiter is not None:
            return arbiter.ownership_family(reason or "")
        return reason_owner_family(reason or "")

    def _declare_goal(
        self, goal: Goal, family: str | None = None, note: str | None = None
    ) -> None:
        """Write the Reach slot, carrying the writing producer's family.

        Rev 9.2 (C): the family is the writer's -- given explicitly by a shared
        helper that knows whose errand it runs (the store router's
        ``travel_reason``), otherwise the census family of the reason the
        producer has already set.  The declaration uses the slot only when
        that family is the row's own owner.
        """
        self._decision_goal = (
            family if family is not None else self._claim_family_of(self.last_reason),
            goal,
            note,
        )

    def _declare_reach(
        self, cell, *, family: str | None = None, note: str | None = None
    ) -> None:
        """The producer names the cell this decision walks toward.

        ``note`` travels to the row's ``goal_note``: ``last-known`` for a walk
        to where a lost chase target was last seen (rev 9.3), and the
        internal ``teleport-walk`` marker of ``_town_teleport_key`` that
        ``_adopt_decision_goal`` requires.
        """
        if isinstance(cell, Position):
            self._declare_goal(claim_reach((cell.y, cell.x)), family, note)

    def _declare_monster(self, identity, *, family: str | None = None) -> None:
        """The producer closes with one monster, named ``(index, race_id)``."""
        if isinstance(identity, tuple) and len(identity) == 2:
            self._declare_goal(claim_reach_monster(*identity), family)

    def _declare_place(self, place: str, *, family: str | None = None) -> None:
        """The producer walks to a named place with no local-map cell."""
        self._declare_goal(claim_reach_place(place), family)

    def _take_claim_target(self) -> Position | None:
        """Record-only (rev 9.3 R2): the target an armed path helper chose.

        A claim site arms the capture (``self._claim_target_capture = []``)
        right before it calls the path helper whose first step it walks, and
        takes the helper's chosen target here right after.  The capture is
        removed again, so the policy's state is what it was.  A helper that
        was replaced (a test double) captures nothing: the site then declares
        no goal.
        """
        capture = self.__dict__.pop("_claim_target_capture", None)
        target = capture[-1] if capture else None
        return target if isinstance(target, Position) else None

    def _adopt_decision_goal(self) -> None:
        """The caller that relabels a helper's walk takes its goal as its own.

        A teleport helper writes the walk to the teleport building under its
        own reason; the caller (a cross-town or quest errand) then sets the
        decision's reason.  The caller asked for that walk, so it re-stamps
        the slot with its family.  Record-only.
        """
        slot = getattr(self, "_decision_goal", None)
        # Rev 9.3 (R7): only the slot the teleport helper itself wrote on this
        # board; on its step-off path it writes none, and an earlier
        # producer's slot must not be adopted.
        if (
            isinstance(slot, tuple)
            and len(slot) == 3
            and slot[2] == CLAIM_TELEPORT_WALK_NOTE
        ):
            self._decision_goal = (
                self._claim_family_of(self.last_reason), slot[1], None
            )

    def _declare_expectation(self, goal: Goal, owner_name: str) -> None:
        """``_post_owner_expectation`` names the observation (rev 9.2 C).

        The family is the census family of the registry owner name the
        producer posted under; a name the census does not know (``stair-
        command``, ``home-withdrawal:*``) falls back to the reason already set.
        """
        family = self._claim_family_of(owner_name)
        if family == UNREGISTERED_FAMILY:
            family = self._claim_family_of(self.last_reason)
        self._decision_expectation = (family, goal)

    def _declare_non_discardable(self, family: str | None = None) -> None:
        """Record that this producer's operation cannot be dropped mid-step."""
        self._decision_non_discardable = (
            family if family is not None else self._claim_family_of(self.last_reason)
        )

    def _offer_execution(self, key: str | None, *, producer: str, work_id: str,
                         next_step: str | None = None, arguments: tuple = (),
                         expected_effect: str | None = None,
                         continuation: str | None = None,
                         budget_ref: str | None = None,
                         state: str = "acting", evidence: str | None = None,
                         cause: str | None = None,
                         post_on_emit: bool = True) -> None:
        """Producer's plain-data step; the exit accepts only its final key."""
        buffer = self._decision_offer_buffer()
        # Keep the producer's board entry for diagnostics and checkpoint
        # compatibility. The normal ladder calls the producer on each board.
        entry = None
        frame = sys._getframe().f_back
        while frame is not None:
            code = frame.f_code
            if (frame.f_locals.get("self") is self
                    and "snapshot" in frame.f_locals
                    and code.co_argcount == 2):
                method = getattr(self, code.co_name, None)
                owner = getattr(getattr(method, "__func__", None),
                                CLAIM_OWNER_ATTRIBUTE, None)
                if (getattr(method, "__code__", None) is code
                        and getattr(owner, "value", None) == producer):
                    entry = code.co_name
                    break
            frame = frame.f_back
        buffer.steps.append((
            key, producer, work_id, next_step, tuple(arguments),
            expected_effect, continuation, budget_ref, state, evidence, cause,
            post_on_emit, buffer.next_sequence(), entry,
        ))

    def _decision_offer_buffer(self) -> _DecisionOffers:
        buffer = _decision_offers.get(self)
        if buffer is None:
            buffer = _DecisionOffers()
            _decision_offers[self] = buffer
        return buffer

    def _execution_offers_for(self) -> tuple:
        buffer = _decision_offers.get(self)
        return tuple(buffer.steps) if buffer is not None else ()

    def _offer_execution_no_step(self, *, producer: str, cause: str,
                                 work_id: str) -> None:
        """A producer explicitly reports that it has no command to issue."""
        buffer = self._decision_offer_buffer()
        buffer.no_steps.append((producer, work_id, cause,
                                buffer.next_sequence(), "releasing"))

    def _offer_execution_done(self, *, producer: str, evidence: str,
                              work_id: str) -> None:
        """A producer reports observed completion without emitting a key."""
        buffer = self._decision_offer_buffer()
        buffer.no_steps.append((producer, work_id, evidence,
                                buffer.next_sequence(), "done"))

    def _offer_execution_awaiting(
        self, key: str | None, *, producer: str, work_id: str,
        operation_ref: str, expected_effect: str,
        continuation: str | None = None,
    ) -> None:
        """A producer names an already accepted operation it is observing."""
        buffer = self._decision_offer_buffer()
        buffer.waits.append((
            key, producer, work_id, operation_ref, expected_effect,
            continuation, buffer.next_sequence(),
        ))

    def _offer_home_scan_leave(self) -> None:
        """A complete Home catalogue still has a page-exit command to send."""
        self._offer_execution(
            LEAVE_STORE_KEY, producer="home-scan",
            work_id=f"home-scan-page:{self._decision_sequence}",
            next_step="store.leave.send", arguments=(STORE_HOME,),
            expected_effect="outside-store",
            continuation="home.knowledge.done",
            budget_ref="home-knowledge-existing-epoch",
        )

    def _record_execution_declaration(self, claim, key, reason: str) -> None:
        register = self._claim_register
        buffer = _decision_offers.pop(self, None)
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
                self._execution_pending_post = (claim.claim_id, key, work_id)
        claim = register.current
        inferred = (
            "silent" if reason.startswith("ownership:holder-silent:")
            else "unposted-await" if reason == "stair:await-observation"
                and (register.current.execution is None
                     or register.current.execution.operation_ref is None)
            else "awaiting" if claim.state == ClaimState.AWAITING
            else "done" if claim.state == ClaimState.COMPLETE
            else "acting"
        )
        self._decision_declaration_mismatch = (
            claim_declaration_mismatch(claim, inferred, reason) if claim.owner.value in {'store-router', 'home-visit', 'equipment-txn', 'departure', 'fundraising'} else None
        )

    def _claim_refresh_non_discardable(self, owner) -> None:
        """Refresh the producer's per-decision slot from its live obligation."""
        family = owner.value
        if family == "equipment-txn" and getattr(
            self, "_equipment_transaction_owned_items", None
        ):
            self._declare_non_discardable(family)
        elif family in {'home-visit', 'home-errand', 'equipment-txn'} and (getattr(self, '_home_atomic_withdraw_pending', None) is not None or getattr(self, '_home_atomic_deposit_pending', None) is not None or False) and (not (family == 'home-errand' and (self.last_reason or '').startswith('home-errand:request-knowledge'))):
            self._declare_non_discardable(family)
        else:
            chain = getattr(self, "_staged_prompt_chain", None)
            if chain is not None and self._claim_family_of(chain.get("owner")) == family:
                self._declare_non_discardable(family)

    _CLAIM_ANY_CELL = object()

    def _claim_close(
        self,
        event: str,
        label: str,
        *,
        owners,
        cell=_CLAIM_ANY_CELL,
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
        register = getattr(self, "_claim_register", None)
        if register is None:
            return
        names = {getattr(owner, "value", owner) for owner in owners}
        cell_named = cell is not self._CLAIM_ANY_CELL
        named_monsters = None if monsters is None else set(monsters)
        if kinds is None:
            kinds = (
                (CLAIM_GOAL_REACH,)
                if cell_named or named_monsters is not None
                else (CLAIM_GOAL_REACH, CLAIM_GOAL_OBSERVE)
            )

        def matches(claim) -> bool:
            if claim.owner.value not in names:
                return False
            goal = claim.goal
            if goal.kind not in kinds:
                return False
            if goal.kind == CLAIM_GOAL_REACH and cell_named:
                if not isinstance(cell, Position) or goal.cell != (cell.y, cell.x):
                    return False
            if goal.kind == CLAIM_GOAL_REACH and named_monsters is not None:
                if goal.monster is None or goal.monster not in named_monsters:
                    return False
            if goal.kind == CLAIM_GOAL_OBSERVE and sources is not None:
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

    def _release_esp_threat_rest_hunt(self, label: str) -> None:
        """Record-only (S2b.1b): the rest slot's WEAK / MEDIUM hunt ends.

        ``_esp_threat_rest_key`` recomputes that hunt on every board and keeps
        no plan, and it is asked only where the ordinary rest rule would rest
        (``_decide`` step 4).  So the walk ends -- standing, or suspended under
        the swing that took it over -- on the board where that slot is passed
        without a hunt: the rest gate closed (HP back at the rest target), or
        the slot chose rest, exploration or nothing.  Only a Reach claim
        opened at that rung is closed; the committed STRONG hunt ends through
        its own rung.
        """
        register = getattr(self, "_claim_register", None)
        if register is None:
            return
        rung = claim_rung_of(ClaimOwner.ESP_THREAT, "esp-threat:hunt-weak").name

        def matches(claim) -> bool:
            return (
                claim.owner == ClaimOwner.ESP_THREAT
                and claim.goal.kind == CLAIM_GOAL_REACH
                and claim.rung == rung
            )

        standing = register.current
        if standing is not None and standing.is_open and matches(standing):
            register.release(label)
            return
        for claim in reversed(register.suspended):
            if matches(claim):
                register.close_suspended(claim.claim_id, "release", label)
                return

    def _release_claim_goal(
        self, label: str, cell=_CLAIM_ANY_CELL, *, owners, **scope
    ) -> None:
        """A producer gives up its multi-decision goal (design rev 9 item 3)."""
        self._claim_close("release", label, owners=owners, cell=cell, **scope)

    def _complete_claim_goal(
        self, label: str, cell=_CLAIM_ANY_CELL, *, owners, **scope
    ) -> None:
        """A producer's own arrival or confirmation branch saw the goal met."""
        self._claim_close("complete", label, owners=owners, cell=cell, **scope)

    def _complete_observed_effect(self, label: str, *, owners, sources) -> None:
        """A posted store/Home operation's effect was confirmed (item 3).

        Rev 9.2 (U): the confirmation names the owners and sources whose
        operation it confirms, so a late confirmation cannot complete the
        claim of whatever owner happens to hold the decision now.
        """
        self._complete_claim_goal(
            label, owners=owners, kinds=(CLAIM_GOAL_OBSERVE,), sources=sources
        )

    def _complete_equipment_transaction_claim(self) -> None:
        """End the session under the family used for its recorded claim."""
        register = getattr(self, "_claim_register", None)
        session = getattr(self, "_equipment_transaction_session", None)
        opened_sequence = getattr(session, "opened_sequence", None)
        claims = (() if register is None else (
            register.current, *register.suspended
        ))
        recorded = next((claim for claim in claims if claim is not None and claim.is_open and (claim.owner.value in {'equipment-txn'}) and (claim.goal.source in {'transaction'}) and (opened_sequence is None or str(opened_sequence) in claim.goal.expectation)), None)
        if recorded is None:
            return
        self._complete_observed_effect(
            "equipment-transaction-complete",
            owners=(recorded.owner.value,), sources=(recorded.goal.source,),
        )

    def _release_town_travel_claim(self, label: str) -> None:
        """Record-only: native travel toward ``_town_travel_state.goal`` ends."""
        state = getattr(self, "_town_travel_state", None)
        self._release_claim_goal(
            label, getattr(state, "goal", None), owners=CLAIM_ENTRANCE_OWNERS
        )

    def _claim_store_visit_closed(
        self, visit, outcome: str, *, operation_posted: bool = False
    ) -> None:
        """``_close_store_visit`` ended the visit that owned a store goal.

        The visit's entrance (``visit.goal``) is the Reach goal of the trip's
        owner, and its posted operation is the ``Observe`` goal of the store
        owner. A completed visit ends a posted operation with its observed
        effect, or expires it when no effect was observed. Other outcomes
        release the visit's open goals.
        """
        if outcome == "completed":
            operation_owners = ('shop-buy', 'shop-sell', 'home-visit', 'home-errand', 'equipment-txn')
            if getattr(visit, "operation_effect_observed", False):
                self._complete_observed_effect(
                    "store-visit:completed", owners=operation_owners,
                    sources=(CLAIM_OBSERVE_STORE_OPERATION,),
                )
            elif operation_posted:
                self._claim_close(
                    "expire", "completed-unobserved",
                    owners=operation_owners,
                    kinds=(CLAIM_GOAL_OBSERVE,),
                    sources=(CLAIM_OBSERVE_STORE_OPERATION,),
                )
            else:
                self._claim_close(
                    "release", "visit-closed-no-operation",
                    owners=operation_owners,
                    kinds=(CLAIM_GOAL_OBSERVE,),
                    sources=(CLAIM_OBSERVE_STORE_OPERATION,),
                )
            return
        label = f"store-visit:{outcome}"
        self._release_claim_goal(
            label, getattr(visit, "goal", None), owners=CLAIM_ENTRANCE_OWNERS
        )
        self._release_claim_goal(
            label,
            owners=CLAIM_STORE_OPERATION_OWNERS,
            kinds=(CLAIM_GOAL_OBSERVE,),
            sources=(CLAIM_OBSERVE_STORE_OPERATION,),
        )
        self._release_claim_goal(
            label, owners=CLAIM_ENTRANCE_OWNERS,
            kinds=(CLAIM_GOAL_OBSERVE,), sources=(CLAIM_OBSERVE_STORE_ENTRY,),
        )

    def _claim_operation_goal(self, snapshot, owner, reason, content):
        """The active operation's stable identity, independent of step posts."""
        if content == CLAIM_OBSERVE_STORE_ENTRY:
            return None
        if owner.value == "equipment-txn" and content == "transaction":
            session = getattr(self, "_equipment_transaction_session", None)
            if session is not None:
                opened = getattr(session, "opened_sequence", None)
                if opened is None:
                    opened = self._decision_sequence
                    session.opened_sequence = opened
                return claim_observe(
                    (opened, tuple(map(repr, session.plan.actions))),
                    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
                    source="transaction",
                )
        if content == CLAIM_OBSERVE_KNOWLEDGE:
            return claim_observe(
                (STORE_HOME, "knowledge",
                 getattr(self, "_home_knowledge_scan_epoch", None)
                 or getattr(self, "_town_visit_epoch", None)),
                STORE_STUCK_LIMIT, source=CLAIM_OBSERVE_KNOWLEDGE,
            )
        if content != CLAIM_OBSERVE_STORE_OPERATION:
            return None
        visit = getattr(self, "_store_visit", None)
        if owner.value in {"shop-buy", "shop-sell"} and visit is not None:
            if visit.operation_key is not None:
                return claim_observe(
                    (visit.store_type, visit.operation_key, visit.opened_sequence),
                    STORE_STUCK_LIMIT, source=CLAIM_OBSERVE_STORE_OPERATION,
                )
        if owner.value in {'home-visit', 'equipment-txn'} and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:morivant-restore-temporary-deposit', 'home:leave-', 'home:store-context-exit')) and (visit is not None) and (visit.store_type == STORE_HOME):
            withdrawal = getattr(self, "_home_atomic_withdraw_pending", None)
            deposit = getattr(self, "_home_atomic_deposit_pending", None)
            withdraw_step = "withdraw" in reason or reason.startswith(
                ("home:leave-", "home:store-context-exit")
            )
            identity = getattr(visit, "claim_operation_identity", None)
            if identity is None and visit.operation_key is not None:
                identity = (STORE_HOME, visit.opened_sequence, visit.operation_key)
            if withdrawal is not None and identity is not None and withdraw_step:
                return claim_observe(
                    identity,
                    STORE_STUCK_LIMIT, source=CLAIM_OBSERVE_STORE_OPERATION,
                )
            if deposit is not None and identity is not None:
                return claim_observe(
                    identity,
                    STORE_STUCK_LIMIT, source=CLAIM_OBSERVE_STORE_OPERATION,
                )
        if owner.value == "home-errand":
            request = getattr(getattr(self, "_home_errand", None), "request", None)
            if request is not None:
                operation = (
                    "knowledge",
                    getattr(self, "_home_knowledge_scan_epoch", None)
                    or getattr(self, "_town_visit_epoch", None),
                ) if reason.startswith("home-errand:request-knowledge") else (
                    getattr(visit, "claim_operation_identity", None)
                    if visit is not None and visit.store_type == STORE_HOME
                    else None
                )
                return claim_observe(
                    (STORE_HOME, "errand", repr(request.signature), operation),
                    STORE_STUCK_LIMIT, source=CLAIM_OBSERVE_STORE_OPERATION,
                )
        chain = getattr(self, "_staged_prompt_chain", None)
        if chain is not None and owner.value in {"identification", "curse-enchant"}:
            return claim_observe(
                (chain.get("owner"), len(chain.get("gates", ()))),
                len(chain.get("gates", ())),
                source=CLAIM_OBSERVE_STORE_OPERATION,
            )
        return None

    def _claim_goal(
        self, snapshot: Snapshot, key, owner: ClaimOwner, reason: str, standing
    ) -> tuple[Goal, bool, str | None]:
        """This decision's goal from the slot, whether it is missing, and why.

        Design rev 9 item 2 and rev 9.2 (C).  The kind comes from the
        checked-in typing table (``claim_goal_typing``); the content comes
        from what a producer wrote on this board, and only when that
        producer's family is the row's owner:

        * ``Reach``: the slot's goal (a cell, a monster, or a place) when its
          family is this owner; otherwise the decision declares ``Terminal``
          and records ``goal_missing`` with ``no-slot`` or ``owner-mismatch``.
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
               for offer in self._execution_offers_for()):
            if (standing is not None and standing.is_open
                    and standing.owner == owner
                    and (standing.goal.source == CLAIM_OBSERVE_KNOWLEDGE
                         or (standing.goal.source == CLAIM_OBSERVE_STORE_ENTRY
                             and standing.execution is not None
                             and standing.execution.expected_effect == "home-catalog-available"))):
                return standing.goal, False, None
            return claim_observe(
                (STORE_HOME, "knowledge", self._town_visit_epoch),
                STORE_STUCK_LIMIT, source=CLAIM_OBSERVE_KNOWLEDGE,
            ), False, None
        if (
            standing is not None and standing.is_open and (standing.owner == owner) and (reason == 'store:entry-await-observation' and standing.goal.source in {CLAIM_OBSERVE_STORE_OPERATION, 'transaction'} or (reason == 'home:scan-incomplete-open-page' and standing.goal.source == CLAIM_OBSERVE_KNOWLEDGE) or (reason == 'shop:one-shot-in-flight' and standing.goal.source == CLAIM_OBSERVE_STORE_OPERATION))
        ):
            # Neither a lagged store entry nor an incomplete Home page ends
            # the operation or knowledge observation it is waiting for.
            return standing.goal, False, None
        if (reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}
                and standing is not None and standing.is_open
                and standing.owner == owner
                and standing.goal.kind == CLAIM_GOAL_OBSERVE
                and standing.goal.source == CLAIM_OBSERVE_STORE_OPERATION
                and not getattr(getattr(self, "_store_visit", None),
                                "operation_effect_observed", False)):
            return standing.goal, False, None
        visit = getattr(self, "_store_visit", None)
        completed_transaction = (
            reason == "home:leave-after-one-operation"
            and getattr(self, "_claim_register", None) is not None
            and self._claim_register.current is not None
            and self._claim_register.current.closed == "complete"
            and self._claim_register.current.closed_reason == "equipment-transaction-complete"
        )
        if (
            reason in {"shop:leave", "shop:store-context-exit",
                       "shop:await-leave-confirmation",
                       "shop:await-leave-generation"}
            or reason.startswith("home:leave-")
            or reason == "home:store-context-exit"
        ) and (completed_transaction or (visit is not None and visit.operation_effect_observed)):
            if (
                standing is not None and standing.is_open and (standing.owner == owner) and (standing.goal.kind == CLAIM_GOAL_OBSERVE) and (standing.goal.source in {CLAIM_OBSERVE_STORE_OPERATION, 'transaction'})
            ):
                return standing.goal, False, None
            return claim_terminal(reason), False, None
        if owner.value in {'equipment-txn'} and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:leave-', 'home:store-context-exit', 'equipment-transaction:await-confirmation', 'equipment-transaction:home-route-unavailable')):
            if (standing is not None and standing.is_open and (standing.owner == owner) and (standing.goal.source in {'transaction'})):
                return standing.goal, False, None
            operation = self._claim_operation_goal(snapshot, owner, reason, "transaction")
            if operation is not None:
                return operation, False, None
        row = claim_goal_typing(owner.value, reason)
        effect = claim_terminal(reason or "policy:none")
        chain = getattr(self, "_staged_prompt_chain", None)
        if chain is not None and self._claim_family_of(chain.get("owner")) == owner.value:
            staged = self._claim_operation_goal(
                snapshot, owner, reason, CLAIM_OBSERVE_STORE_OPERATION
            )
            if staged is not None:
                return staged, False, None
        if row is None or row.kind == CLAIM_GOAL_TERMINAL:
            if owner.value == "home-visit" and reason.startswith((
                "home:leave-", "home:store-context-exit",
            )):
                operation = self._claim_operation_goal(
                    snapshot, owner, reason, CLAIM_OBSERVE_STORE_OPERATION
                )
                if operation is not None:
                    return operation, False, None
            if (
                standing is not None and standing.is_open
                and standing.owner == owner
                and standing.goal.source == CLAIM_FLOOR_CHANGE
                and reason.startswith("town:wait-recall")
            ):
                return standing.goal, False, None
            return effect, False, None
        if (
            standing is not None and standing.is_open
            and standing.owner == owner
            and standing.goal.source == CLAIM_FLOOR_CHANGE
            and reason.startswith("town:wait-recall")
        ):
            return standing.goal, False, None
        # A route to the next transaction step is still the same open
        # session. The separately ruled await-entry wait keeps its own
        # store-entry goal once the entrance command has been posted.
        if (
            row.kind == CLAIM_GOAL_REACH and owner.value in {'equipment-txn'} and (not reason.endswith(':await-entry'))
        ):
            operation = self._claim_operation_goal(
                snapshot, owner, reason, "transaction"
            )
            if operation is not None:
                return operation, False, None
        if row.kind == CLAIM_GOAL_REACH:
            slot = getattr(self, "_decision_goal", None)
            if (
                getattr(self, "_town_claim_bar_enforced", False)
                and owner.value in CLAIM_S3_FAMILIES
                and standing is not None and standing.is_open
                and standing.owner == owner
                and standing.goal.kind == CLAIM_GOAL_REACH
                and reason in {"shop:approach", "shop:travel"}
            ):
                # A one-cell fallback can emit the held route's next key
                # without writing a new goal slot. The committed entrance
                # remains its goal until arrival.
                return standing.goal, False, None
            if not (
                isinstance(slot, tuple)
                and len(slot) in (2, 3)
                and isinstance(slot[1], Goal)
                and slot[1].kind == CLAIM_GOAL_REACH
            ):
                return effect, True, CLAIM_GOAL_NOTE_NO_SLOT
            if slot[0] != owner.value:
                return effect, True, CLAIM_GOAL_NOTE_OWNER_MISMATCH
            note = slot[2] if len(slot) == 3 else None
            return slot[1], False, (
                note if note != CLAIM_TELEPORT_WALK_NOTE else None
            )
        within = CLAIM_OBSERVE_WITHIN.get(row.content, OWNER_EXPECTATION_MAX_TURNS)
        if row.content == CLAIM_OBSERVE_STORE_ENTRY:
            visit = getattr(self, "_store_visit", None)
            if (
                reason == "store:entry-await-observation"
                and visit is not None and visit.goal is not None
                and (snapshot.player.position.y, snapshot.player.position.x)
                    != (visit.goal.y, visit.goal.x)
            ):
                return claim_reach((visit.goal.y, visit.goal.x)), False, None
            target = getattr(self, "_store_entry_wait_owner", None)
            if target is None and visit is not None:
                target = visit.store_type
            return claim_observe(
                (CLAIM_OBSERVE_STORE_ENTRY, target), within,
                source=CLAIM_OBSERVE_STORE_ENTRY,
            ), False, None
        if row.content == CLAIM_FLOOR_CHANGE:
            return (
                claim_observe(
                    CLAIM_FLOOR_EXPECTATION, within, source=CLAIM_FLOOR_CHANGE
                ),
                False,
                None,
            )
        operation = self._claim_operation_goal(snapshot, owner, reason, row.content)
        if operation is not None:
            return operation, False, None
        note = None
        posted = getattr(self, "_decision_expectation", None)
        if (
            isinstance(posted, tuple)
            and len(posted) == 2
            and isinstance(posted[1], Goal)
            and posted[1].kind == CLAIM_GOAL_OBSERVE
        ):
            if posted[0] == owner.value:
                return posted[1], False, None
            note = CLAIM_GOAL_NOTE_OWNER_MISMATCH
        if (
            standing is not None
            and standing.is_open
            and standing.owner == owner
            and standing.goal.kind == CLAIM_GOAL_OBSERVE
            and standing.goal.source != CLAIM_FLOOR_CHANGE
        ):
            return standing.goal, False, note
        return claim_observe((row.content,), within, source=row.content), False, note

    def _claim_owner_retired(self, owner) -> bool:
        """Whether the arbiter already holds this owner's claim as retired."""
        if (getattr(self, "_town_claim_bar_enforced", False)
                and owner.value == "store-router"
                and (holder := getattr(getattr(self, "_claim_register", None),
                                      "current", None)) is not None
                and holder.is_open and holder.owner == owner
                and ((owner.value == "store-router"
                      and holder.goal.kind == CLAIM_GOAL_REACH)
                     or (self.last_reason or "").startswith(
                         "ownership:holder-"))):
            # An open errand keeps its route or observation wait even if the
            # town plan retired the need while the claim was pending.
            return False
        arbiter = getattr(self, "_town_turn_arbiter", None)
        telemetry = getattr(arbiter, "telemetry", None) if arbiter else None
        if not isinstance(telemetry, dict):
            return False
        return bool(
            telemetry.get("retired")
            and telemetry.get("producer_owner") == owner.value
        )

    @staticmethod
    def _claim_perceived_monster(snapshot: Snapshot, identity):
        """The perceived monster with this ``(index, race_id)``, if any."""
        for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
            if (monster.index, monster.race_id) == tuple(identity):
                return monster
        return None

    def _claim_entered_store_at(self, snapshot: Snapshot, cell) -> bool:
        """The board is inside the store whose entrance is ``cell``."""
        visit = getattr(self, "_store_visit", None)
        entrance = getattr(visit, "goal", None)
        return (
            snapshot.store is not None
            and isinstance(entrance, Position)
            and tuple(cell) == (entrance.y, entrance.x)
        )

    def _claim_reach_arrival(self, snapshot: Snapshot, claim) -> str | None:
        """The observed arrival that completes a cell Reach claim, read-only.

        The same evidence ``_claim_exit_completion`` closes the claim on: the
        player stands on the goal cell of the claim's own floor (never the
        open wilderness), or is inside the store whose entrance is the cell.
        """
        goal = claim.goal
        if (goal.kind != CLAIM_GOAL_REACH or goal.monster is not None
                or goal.cell is None):
            return None
        if claim.floor is not None and tuple(claim.floor) != tuple(snapshot.floor_key):
            return None
        if snapshot.on_open_wilderness:
            return None
        position = snapshot.player.position
        if goal.cell == (position.y, position.x):
            return "reached"
        if self._claim_entered_store_at(snapshot, goal.cell):
            return "entered-store"
        return None

    def _claim_exit_completion(self, snapshot: Snapshot, standing, pops) -> None:
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
        if goal.kind == CLAIM_GOAL_REACH:
            if goal.monster is not None:
                monster = self._claim_perceived_monster(snapshot, goal.monster)
                if monster is None or not same_floor:
                    self._release_claim_goal("target-lost", owners=own)
                elif position.distance_to(monster.position) <= 1:
                    self._complete_claim_goal("target-adjacent", owners=own)
                return
            if goal.cell is None:
                return
            if not same_floor or snapshot.on_open_wilderness:
                return
            arrival = self._claim_reach_arrival(snapshot, standing)
            if arrival is not None:
                self._complete_claim_goal(arrival, owners=own)
                return
            visit = getattr(self, "_store_visit", None)
            entrance = getattr(visit, "goal", None)
            context = getattr(getattr(self, "_home_visit", None), "context_token", None)
            if (
                entrance is not None
                and goal.cell == (entrance.y, entrance.x)
                and (
                    (isinstance(context, tuple) and context[0] == "outside-ready")
                    or getattr(self, "_home_entry_operation_posted", False)
                    or getattr(self, "_intentional_entrance_activation", False)
                )
            ):
                self._complete_claim_goal("entered-outside", owners=own)
            return
        if goal.kind != CLAIM_GOAL_OBSERVE:
            return
        if (
            goal.source == CLAIM_OBSERVE_KNOWLEDGE
            and (getattr(self, "_home_knowledge_current", False)
                 or getattr(self, "_claim_home_knowledge_observed", False))
        ):
            self._complete_claim_goal("home-knowledge-current", owners=own)
            return
        session = getattr(self, "_equipment_transaction_session", None)
        opened = getattr(session, "opened_sequence", None)
        session_replaced = (
            session is not None
            and any(part.isdecimal() for part in goal.expectation)
            and (opened is None or str(opened) not in goal.expectation)
        )
        if (
            goal.source in {'transaction'} and standing.owner.value in {'equipment-txn'} and (session_replaced or (session is None and (getattr(self, '_equipment_transaction_owned_items', None) or False)))
        ):
            terminal = (
                getattr(self, "_equipment_transaction_restore_terminal", None)
                or ("session-replaced" if session_replaced else None)
                or self.last_reason or "session-cleared"
            )
            self._release_claim_goal(
                f"abandoned:{terminal}", owners=own,
                kinds=(CLAIM_GOAL_OBSERVE,), sources=(goal.source,),
            )
            return
        if goal.source == CLAIM_FLOOR_CHANGE:
            if standing.floor is not None and not same_floor:
                self._complete_claim_goal("floor-changed", owners=own)
            elif (
                goal.within is not None
                and standing.opened_turn is not None
                # S2b.1 (rev 10.1 item 6): the turns spent suspended do not
                # count against a resumed claim's ``within``.
                and snapshot.turn - standing.opened_turn
                - (standing.suspended_turns or 0) > goal.within
            ):
                self._claim_close("expire", "within-exceeded", owners=own)
            return
        if goal.source == CLAIM_OBSERVE_STORE_ENTRY:
            # Restored pre-live23 declarations also named catalogue work,
            # although their goal was typed as entry. Honor the named effect.
            declaration = getattr(standing, "execution", None)
            catalogue_work = (declaration is not None
                              and declaration.expected_effect == "home-catalog-available")
            if catalogue_work and self._home_knowledge_current:
                self._complete_claim_goal("home-knowledge-current", owners=own)
                return
            visit = getattr(self, "_store_visit", None)
            entrance = getattr(visit, "goal", None)
            if (
                not catalogue_work
                and snapshot.store is not None
                and str(snapshot.store.store_type) in goal.expectation
                and (
                    entrance is None
                    or self._claim_entered_store_at(
                        snapshot, (entrance.y, entrance.x)
                    )
                )
            ):
                self._complete_claim_goal("entered-store", owners=own)
                return
        if any(
            owner == goal.source and why == EXPECTATION_POP_SATISFIED
            for owner, why in pops
        ):
            self._complete_claim_goal("expectation-satisfied", owners=own)
            return
        registry = getattr(self, "_owner_expectations", None)
        if (
            registry is not None
            and goal.source is not None
            and hasattr(registry, "verdict")
            and registry.pending(goal.source) is not None
            and registry.verdict(
                goal.source, self._progress_core_of(snapshot)
            ) == EXPECTATION_POP_SATISFIED
        ):
            self._complete_claim_goal("expectation-satisfied", owners=own)
            return
        if (
            goal.within is not None
            and standing.opened_sequence is not None
            # S2b.1 (rev 10.1 item 6): nor do the decisions spent suspended.
            and self._decision_sequence - standing.opened_sequence
            - (standing.suspended_decisions or 0) >= goal.within
        ):
            self._claim_close("expire", "within-exceeded", owners=own)

    def _claim_goal_distance(self, snapshot: Snapshot, goal: Goal):
        position = snapshot.player.position
        if goal.kind != CLAIM_GOAL_REACH:
            return None
        if goal.cell is not None:
            return position.distance_to(Position(*goal.cell))
        if goal.monster is not None:
            monster = self._claim_perceived_monster(snapshot, goal.monster)
            return (
                position.distance_to(monster.position)
                if monster is not None
                else None
            )
        return None

    def _record_decision_claim(self, snapshot: Snapshot, key) -> None:
        """Attribute this decision to a claim and record it for the row.

        The declaration point of design section 4.  It runs on the decided
        board at the ``choose_key`` exit, so the claim, its goal and the
        measured distance to that goal reach the decision row as plain data
        (like ``decision_attribution``).  It deliberately does *not* run in
        the telemetry capture: that is an observer scope whose work is
        discarded (design 5.4), so a claim computed there would never be the
        claim the decision was made under.

        S2a.1 (design rev 9.1/9.2): before declaring, the previous decision's
        claim is closed if this board ends it -- a closing a producer already
        recorded during this decision, the exit's own completion or expiry
        test, or the survival preemption (``suspend``, survival only).  The
        row carries the closed claim as ``closed_claim``, because the row that
        owned it is already written.

        S2b.1 (design rev 10.1): the decision's rung and rank come from
        ``claim_ladder.rung_of``; a strictly higher rung preempts (suspends)
        the held Reach/Observe claim as survival does, anything else that
        drops it is a violation recorded on the row; the suspended stack is
        resolved (resume under the same id, nest, displace, release) and the
        trigger monsters of item 9 are recorded.  Still record-only.

        S2b.2 (design 3.2 / 3.3): the board's lift pass runs first; the
        decision's owner and goal are then matched against the bar table
        (``would_bar``), and the claims that ended on this decision without
        their goal are barred (``bars_set``).  With ``_claim_bar_enforced``
        off -- the default and the only shipped setting -- that is all.
        """
        registry = getattr(self, "_owner_expectations", None)
        pops = (
            registry.drain_pops()
            if registry is not None and hasattr(registry, "drain_pops")
            else []
        )
        register = getattr(self, "_claim_register", None)
        if register is None:
            self.decision_claim = None
            return
        # S2b.2: the bars this board lifts (a pure function of the board).
        bars_lifted = self._claim_bar_lift(snapshot, register)
        reason = self.last_reason or ""
        standing = register.current
        self._claim_exit_completion(snapshot, standing, pops)
        standing = register.current
        if (
            standing is not None and standing.is_open
            and standing.goal.kind == CLAIM_GOAL_REACH
            and (getattr(self, "decision_claim", None) or {}).get("reason")
                == "town:seek-shelter"
            and not getattr(self, "_took_damage", False)
        ):
            self._release_claim_goal(
                "seek-shelter-trigger-gone", owners=(standing.owner,),
                kinds=(CLAIM_GOAL_REACH,),
            )
        # S2b.1 (rev 10.1 item 6, rules i-ii): the suspended claims this board
        # ends -- a floor change, or a goal the board shows met.
        self._claim_suspended_exit(snapshot, register)
        self._claim_home_knowledge_observed = False
        # Judge the holder after the recording seam's existing observed
        # completions, but before it consumes offers or declares this winner.
        shadow = (self._s33_shadow_verdict(snapshot, key)
                  if (snapshot.in_town or snapshot.store is not None)
                  and not getattr(self, "_town_claim_bar_enforced", False)
                  else None)
        # Rev 9.2 (S): the danger trigger of *this* return, recorded where the
        # return began -- never ``_last_return_trigger``, which outlives it.
        survival = claim_is_survival(
            reason, getattr(self, "_survival_return_trigger", None)
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
            and standing.goal.source == CLAIM_OBSERVE_STORE_OPERATION
            and getattr(self, "_home_atomic_withdraw_pending", None) is not None
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
        continuing_store_exit = (
            getattr(self, '_town_claim_bar_enforced', False) and reason == 'policy:none-store-exit' and (standing is not None) and standing.is_open and (standing.goal.kind == CLAIM_GOAL_OBSERVE) and (standing.goal.source in {CLAIM_OBSERVE_STORE_OPERATION, 'transaction'})
        )
        continuing_owner = (
            continuing_home_errand or continuing_holder_wait
            or continuing_store_exit
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
            else claim_owner_of(self._claim_family_of(reason))
        )
        if reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}:
            family = self._visit_exit_family()
            if family != "barrier-provenance-missing":
                owner = claim_owner_of(family)
        self._claim_refresh_non_discardable(owner)
        # S2b.1 (rev 10.1 items 1-2): the rung and rank of this decision.
        non_discardable = (
            continuation_claim.non_discardable
            if continuing_owner
            else getattr(self, "_decision_non_discardable", None) == owner.value
        ) and not reason.endswith(":await-entry")
        rung = claim_rung_of(owner, reason, non_discardable=non_discardable)
        standing = register.current
        goal, goal_missing, goal_note = (
            (continuation_claim.goal, False, None)
            if continuing_owner
            else self._claim_goal(snapshot, key, owner, reason, standing)
        )
        if (
            standing is not None and standing.is_open
            and standing.owner == owner
            and reason.startswith("equipment-transaction:stale-identity-invalidated:")
        ):
            self._release_claim_goal('transaction-identity-stale', owners=(owner,), kinds=(CLAIM_GOAL_OBSERVE,), sources=('transaction',))
            standing = register.current
        if (
            standing is not None and standing.is_open
            and standing.owner == owner
            and standing.goal.source == CLAIM_OBSERVE_STORE_ENTRY
            and goal.kind == CLAIM_GOAL_TERMINAL
        ):
            self._release_claim_goal(
                f"entry-abandoned:{reason}", owners=(owner,),
                kinds=(CLAIM_GOAL_OBSERVE,),
                sources=(CLAIM_OBSERVE_STORE_ENTRY,),
            )
            standing = register.current
        if (
            standing is not None and standing.is_open
            and standing.owner == owner
            and standing.goal.source == CLAIM_OBSERVE_STORE_OPERATION
            and goal.kind == CLAIM_GOAL_OBSERVE
            and standing.goal != goal
            and getattr(self, "_home_atomic_withdraw_pending", None) is None
            and getattr(self, "_home_atomic_deposit_pending", None) is None
        ):
            self._release_claim_goal(
                "operation-identity-stale", owners=(owner,),
                kinds=(CLAIM_GOAL_OBSERVE,),
                sources=(CLAIM_OBSERVE_STORE_OPERATION,),
            )
            standing = register.current
        action, label, violation = self._claim_owner_transition(
            register, standing, owner, goal, rung, survival, non_discardable,
            snapshot=snapshot,
        )
        if action == CLAIM_PREEMPTION:
            # Design 3.2 / rev 10 item 2: a strictly higher rung suspends the
            # holder with its goal intact.  The one caller of ``suspend``.
            register.suspend(
                label, sequence=self._decision_sequence, turn=snapshot.turn
            )
            # Round 3: a holder restored with no floor takes this board's.
            register.stamp_suspended_floor(standing.claim_id, snapshot.floor_key)
        elif action == CLAIM_SURVIVAL_DISPLACED:
            # Survival that does not outrank the holder replaces it: released,
            # exempt, not a violation (round 2, F1/F2).
            register.release(label)
        if action is not None:
            # S2a.1's order: the goal is read after the holder closed, exactly
            # as it was when survival was the only preemptor.
            goal, goal_missing, goal_note = self._claim_goal(
                snapshot, key, owner, reason, register.current
            )
        resumed = self._claim_resolve_suspended(
            register, owner, goal, rung, survival, non_discardable
        )
        finished = register.take_closing()
        closed = finished.closing_dict() if finished is not None else None
        home_visit = getattr(self, "_home_visit", None)
        active_operation = getattr(self, "_claim_active_operation_identity", None)
        completed_operation = (
            active_operation[1]
            if finished is not None
            and isinstance(active_operation, tuple)
            and len(active_operation) == 2
            and active_operation[0] == finished.claim_id
            else None
        )
        if (
            finished is not None and finished.closed == CLAIM_CLOSED_BY_COMPLETE and (finished.goal.kind == CLAIM_GOAL_OBSERVE) and (finished.owner.value in {'home-visit', 'home-errand', 'equipment-txn'})
        ):
            self._claim_last_completed_home = (
                finished, getattr(home_visit, "visit_id", None),
                completed_operation,
            )
        verdict = None
        report = getattr(home_visit, "report", None)
        if "target-unobserved" in reason:
            verdict = "target-unobserved"
        elif report is not None and getattr(report, "outcome", None) == "unfulfilled":
            verdict = "unfulfilled"
        elif self._town_visit_ledger.approach_fails[STORE_HOME] > getattr(
            self, "_decision_home_approach_fails_before",
            self._town_visit_ledger.approach_fails[STORE_HOME],
        ):
            verdict = "approach_fails"
        recent = getattr(self, "_claim_last_completed_home", None)
        if recent is not None and recent[1] != getattr(home_visit, "visit_id", None):
            recent = None
        operation = getattr(home_visit, "operation", None)
        operation_generation = getattr(home_visit, "operation_generation", None)
        if operation is None and home_visit is not None:
            reports = getattr(home_visit, "operation_reports", ())
            if reports and reports[-1].visit_id == home_visit.visit_id:
                operation = (reports[-1].action, reports[-1].identity)
                operation_generation = reports[-1].posted_generation
        operation_identity = (
            (operation, operation_generation) if operation is not None else None
        )
        same_operation = (
            recent is not None and len(recent) > 2
            and recent[2] is not None and recent[2] == operation_identity
        )
        completed = next((candidate for candidate in (finished if same_operation else None, standing if same_operation else None, recent[0] if same_operation else None) if candidate is not None and candidate.closed == CLAIM_CLOSED_BY_COMPLETE and (candidate.goal.kind == CLAIM_GOAL_OBSERVE) and (candidate.owner.value in {'home-visit', 'home-errand', 'equipment-txn'})), None)
        claim_verdict_conflict = (
            {
                "claim_id": completed.claim_id,
                "claim_ending": completed.closed,
                "verdict": verdict,
                "attempts_used": getattr(home_visit, "attempts_used", None),
            }
            if completed is not None and verdict is not None else None
        )
        if claim_verdict_conflict is not None:
            self._claim_last_completed_home = None
        suspended_closed = register.take_suspended_closings()
        if resumed is not None:
            # The resumed claim keeps its own rank unless this decision's rung
            # is strictly higher, so it still outranks nothing it sat under.
            outranks = resumed.rank is None or rung.rank < resumed.rank
            claim = register.resume(
                resumed.claim_id,
                sequence=self._decision_sequence,
                turn=snapshot.turn,
                rank=rung.rank if outranks else resumed.rank,
                rung=rung.name if outranks else resumed.rung,
                perceived_turn=self._claim_trigger_perceived(
                    snapshot, resumed.trigger_monsters
                ),
            )
        else:
            current = register.current
            continuing = register.continues(owner, goal, non_discardable)
            triggers = (
                current.trigger_monsters
                if continuing and current is not None
                else self._claim_trigger_monsters(owner, goal)
            )
            register.declare(
                owner,
                goal,
                non_discardable=non_discardable,
                opened_sequence=self._decision_sequence,
                floor=snapshot.floor_key,
                survival=survival,
                opened_turn=snapshot.turn,
                rank=rung.rank,
                rung=rung.name,
                trigger_monsters=triggers,
                perceived_turn=self._claim_trigger_perceived(snapshot, triggers),
            )
        if self._claim_owner_retired(owner):
            claim = register.retire()
        elif key is None or key == "":
            claim = register.await_observation()
        else:
            claim = register.keep_active()
        transition_violation = violation
        # A filed Home request keeps its purpose until the errand ends.  The
        # purpose record is independent of a claim transition violation.
        filed = getattr(getattr(self, "_home_errand", None), "request", None)
        purpose_duplicates = []
        purpose_identity = None
        if reason in {
            "town:restore-combat-weapon", "town:replace-no-teleport-weapon"
        }:
            purpose_identity = ("equipment-slot", "main_hand")
        elif isinstance(key, str) and len(key) >= 2 and (
            (filed is not None and filed.purpose in {
                "identification", "identification-catalog"
            }
             and reason.startswith(("identify:", "identification:")))
            or (filed is not None and filed.purpose == "experience-potion"
                and reason == "experience:quaff")
        ):
            # Identify macros are command + source slot + target slot, often
            # followed by a prompt-dismissal suffix.  Quaff is command + item
            # slot.  Unknown shapes have no provable target and stay untyped.
            selected_slot = (
                key[1] if reason == "experience:quaff" and key.startswith("q")
                else key[2] if reason.startswith(("identify:", "identification:"))
                and key[0] in "uzr" and len(key) >= 3
                else None
            )
            selected = [item for item in snapshot.inventory
                        if item.slot == selected_slot]
            if len(selected) == 1:
                purpose_identity = ("item", self._item_signature(selected[0]))
        filed_identity = None
        if filed is not None:
            filed_identity = (
                ("equipment-slot", "main_hand")
                if filed.purpose == "combat-weapon"
                else ("item", filed.signature)
            )
        if (
            getattr(self._home_errand, "active", False)
            and filed_identity is not None
            and purpose_identity == filed_identity
            and owner.value != "home-errand"
            and (standing is None or not standing.is_open or standing.owner != owner)
        ):
            duplicate = {
                "kind": "purpose-duplicate", "scope": "S3",
                "from": "home-errand", "to": owner.value,
                "purpose": [filed.purpose, purpose_identity[1]],
                "holders": [
                    {"family": "home-errand", "key": "filed:" + filed.purpose,
                     "request_identity": list(filed.signature)},
                    {"family": owner.value, "key": reason,
                     "claim_id": claim.claim_id},
                ],
            }
            purpose_duplicates.append(duplicate)
            if violation is None:
                violation = duplicate
        if claim.is_open and claim.owner.value in {'home-visit', 'home-errand', 'equipment-txn'}:
            operation = getattr(home_visit, "operation", None)
            identity = (
                (operation, getattr(home_visit, "operation_generation", None))
                if operation is not None else None
            )
            previous_identity = getattr(self, "_claim_active_operation_identity", None)
            if (
                not isinstance(previous_identity, tuple)
                or len(previous_identity) != 2
                or previous_identity[0] != claim.claim_id
                or (previous_identity[1] is None and identity is not None)
            ):
                self._claim_active_operation_identity = (claim.claim_id, identity)
        visit = getattr(self, "_store_visit", None)
        visit_owner_mismatch = None
        visit_owner_structure = None
        visit_requester = None
        leave_confirmation_interruption = None
        if visit is not None and claim.is_open and claim.owner.value in CLAIM_S3_FAMILIES:
            visit_requester = getattr(visit, "opened_for_family", None)
            if (
                getattr(self, "_store_leave_inflight", None) is not None
                and self._store_leave_inflight[0] != self._decision_sequence
                and claim.goal.kind == CLAIM_GOAL_OBSERVE
                and claim.goal.source in {
                    CLAIM_OBSERVE_STORE_OPERATION, CLAIM_OBSERVE_KNOWLEDGE,
                }
                and visit_requester is not None
                and visit_requester != claim.owner.value
                and reason != "shop:await-leave-confirmation"
                and not reason.startswith("ownership:holder-")
                and not reason.startswith("home:leave-")
                and reason != "home:store-context-exit"
            ):
                leave_confirmation_interruption = {
                    "kind": "leave-confirmation-interruption", "scope": "S3",
                    "from": visit_requester, "to": claim.owner.value,
                    "claim_id": claim.claim_id,
                }
                if violation is None:
                    violation = leave_confirmation_interruption
            visit.claim_id = claim.claim_id
            visit.claim_owner = claim.owner.value
            aliases = {
                "shop-handler": visit.opened_producer_family,
                "shop-one-shot": visit.opened_producer_family,
                "home-one-shot": "home-visit",
                "equipment-transaction": (
                    'equipment-txn'
                ),
            }
            alias = aliases.get(visit.owner, visit.owner)
            if alias == "town-errand":
                alias = visit.opened_producer_family
            requester_missing = (
                alias == "store-router"
                and getattr(visit, "opened_for_family", None) is None
            )
            router_for_operation = (
                alias == "store-router"
                and claim.owner.value == getattr(visit, "opened_for_family", None)
            )
            if router_for_operation:
                visit_owner_structure = (
                    "router-plan-stop"
                    if getattr(visit, "request_structure", None) == "router-plan-stop"
                    else "router-opens-family-operates"
                )
            if requester_missing:
                visit_owner_structure = "requester-missing"
            if (
                alias != claim.owner.value
                and not router_for_operation
                and not requester_missing
            ):
                visit_owner_mismatch = {
                    "visit_owner": alias, "claim_owner": claim.owner.value,
                    "claim_id": claim.claim_id,
                }
        # S2b.2 (record-only while the switch is off): the bar this decision's
        # owner and goal would meet -- read before this row's own endings are
        # barred, as the ladder would have read the table while deciding.
        would_bar = self._claim_would_bar(register, claim, survival)
        would_skip = self._claim_would_skip(register, rung, survival)
        bars_set = self._claim_set_bars(
            snapshot, register,
            dropped=standing if transition_violation is not None else None,
        )
        self._bind_execution_delegations(claim)
        self._observe_execution_delegations()
        self._record_execution_declaration(claim, key, reason)
        claim = register.current
        closed_declaration_mismatch = (
            claim_declaration_mismatch(finished, 'awaiting', reason) if finished is not None and finished.execution is not None and (finished.execution.state == 'done') and (claim.claim_id == finished.claim_id or claim.execution is None) and (finished.owner.value in {'home-visit', 'equipment-txn'}) and (visit is not None) and visit.operation_posted and (not visit.operation_released) else None
        )
        self.decision_claim = {
            **({"item_reservation_shadow": reservation_shadow(self)}
               if reservation_shadow(self) else {}),
            **claim.as_dict(distance=self._claim_goal_distance(snapshot, claim.goal)),
            "decision_sequence": self._decision_sequence,
            "reason": reason,
            "fundraising_purpose": (
                {
                    "register_kind": "separate-purpose-ledger",
                    "id": purpose_record.purpose.identity,
                    "mode": purpose_record.purpose.mode,
                    "first_run_food_waiver": (
                        purpose_record.purpose.first_run_food_waiver
                    ),
                    "status": purpose_record.status,
                    "failure": purpose_record.failure,
                    "child": (
                        None if purpose_record.child is None else {
                            "direction": purpose_record.child.direction,
                            "state": purpose_record.child.state,
                            "posted_sequence": (
                                purpose_record.child.posted_sequence
                            ),
                        }
                    ),
                }
                if (getattr(self, "_crossarea_fundraising_enforced", False)
                    and (purpose_record := getattr(
                        self, "_fundraising_purpose_record", None
                    )) is not None)
                else None
            ),
            "closed_claim": closed,
            "goal_missing": goal_missing,
            "goal_note": goal_note,
            "survival": survival,
            # S2b.1 (design rev 10.1), record-only.
            "rank": rung.rank,
            "rung": rung.name,
            "violation": violation,
            "purpose_duplicates": purpose_duplicates,
            "visit_owner_mismatch": visit_owner_mismatch,
            "visit_owner_structure": visit_owner_structure,
            "visit_requester": visit_requester,
            "visit_operator": claim.owner.value if visit is not None else None,
            "barrier_provenance": (
                self._visit_exit_family()
                if reason in {"shop:await-leave-confirmation",
                              "shop:await-leave-generation"} else None
            ),
            "leave_confirmation_interruption": leave_confirmation_interruption,
            "leave_confirmation_pending": (
                getattr(self, "_store_leave_inflight", None) is not None
            ),
            "requester_missing": visit_owner_structure == "requester-missing",
            "claim_verdict_conflict": claim_verdict_conflict,
            "scan-during-pending-atomic": bool(
                (owner.value == "home-scan" or (
                    owner.value == "home-errand"
                    and reason.startswith("home-errand:request-knowledge")
                ))
                and (
                    getattr(self, "_home_atomic_withdraw_pending", None) is not None
                    or getattr(self, "_home_atomic_deposit_pending", None) is not None
                )
            ),
            "plan_rebuild_deferred": getattr(
                self, "_decision_plan_rebuild_deferred", 0
            ),
            "plan_change_evidence": getattr(
                self, "_decision_plan_change_evidence", None
            ),
            "displaced_non_discardable_producer": getattr(
                self, "_decision_displaced_producer", None
            ),
            "resumed": (
                None
                if resumed is None
                else {
                    "claim_id": claim.claim_id,
                    "owner": claim.owner.value,
                    "goal_kind": claim.goal.kind,
                    "suspended_decisions": claim.suspended_decisions,
                    "suspended_turns": claim.suspended_turns,
                }
            ),
            "suspended_closed": suspended_closed or None,
            "suspended_depth": len(register.suspended),
            "trigger_monsters": (
                [list(pair) for pair in claim.trigger_monsters]
                if claim.trigger_monsters
                else None
            ),
            "last_perceived_turn": claim.last_perceived_turn,
            # S2b.2 (design 3.2 / 3.3), record-only while the switch is off.
            "would_bar": would_bar,
            "would_skip": would_skip,
            "bars_set": bars_set or None,
            "bars_lifted": bars_lifted or None,
            "bars_active": len(register.bars),
            "bar_skipped": list(getattr(self, "_decision_bar_skips", None) or ())
            or None,
            "errand_deferred": list(
                getattr(self, "_decision_errand_deferred", None) or ()
            ) or None,
            "gate_final_count": getattr(self, "_decision_gate_final_count", 0),
            "rewrite_refused": list(
                getattr(self, "_decision_rewrite_refused", ())
            ) or None,
            "requester_families": sorted(
                getattr(getattr(self, "_store_visit", None),
                        "requester_families", ())
            ),
            "execution_delegations": [
                record.as_dict() for record in self._delegation_records()
                if record.lifecycle in {"reserved", "open"}
                and record.parent_claim_id == claim.claim_id
            ] or None,
            "cancelled_home_reservation": getattr(
                self, "_decision_cancelled_home_reservation", None
            ),
            "declaration_mismatch": getattr(
                self, "_decision_declaration_mismatch", None
            ) or closed_declaration_mismatch,
        }
        if shadow is not None:
            if shadow["holder_family"] is None:
                shadow["holder_family"] = claim.owner.value
                shadow["holder_claim_id"] = claim.claim_id
                shadow["declaration_state"] = (
                    claim.execution.state if claim.execution is not None else None)
                shadow["declaration_gap"] = claim.execution is None
            shadow["mismatch"] = self.decision_claim["declaration_mismatch"]
            self.decision_claim["s33_shadow"] = shadow
        if isinstance(key, DecisionCandidate):
            # Design 5.4: the declaration token travels on the candidate that
            # already carries the decision's provenance, rather than on a
            # second str subclass.  Nothing reads it before S2's port-side
            # check, so writing it cannot change this decision.
            key.claim_id = claim.claim_id

    # -- S2b.1: the ladder, preemption and violations (design rev 10.1) -------
    #
    # Record-only, like everything above: these helpers read the snapshot and
    # the claim register, and write only the register and the decision row.

    def _claim_suspended_exit(self, snapshot: Snapshot, register) -> None:
        """Rules (i) and (ii) of rev 10.1 item 6, on the suspended stack.

        (i) After a floor change (a town departure is one) a suspended
        floor-change ``Observe`` completes and every other suspended claim is
        released ``suspended-expired``.  (ii) On the same floor, a suspended
        ``Reach`` completes when the board shows it met, by the tests an
        active claim uses: the player on its cell, or next to its monster; and
        (S2b.1b) a suspended chase whose monster is no longer perceived is
        released ``target-lost``, as an active one is.  No store-operation or
        transaction ``Observe`` is ever on the stack
        (``claim_ladder.never_suspended``).
        """
        position = snapshot.player.position
        for claim in register.suspended:
            goal = claim.goal
            if (
                goal.kind == CLAIM_GOAL_OBSERVE
                and goal.source == CLAIM_OBSERVE_KNOWLEDGE
                and (getattr(self, "_home_knowledge_current", False)
                     or getattr(self, "_claim_home_knowledge_observed", False))
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
                    goal.kind == CLAIM_GOAL_OBSERVE
                    and goal.source == CLAIM_FLOOR_CHANGE
                ):
                    register.close_suspended(
                        claim.claim_id, "complete", "floor-changed"
                    )
                else:
                    register.close_suspended(
                        claim.claim_id, "release", CLAIM_SUSPENDED_EXPIRED
                    )
                continue
            if goal.kind == CLAIM_GOAL_OBSERVE and goal.source == CLAIM_OBSERVE_STORE_ENTRY:
                if (
                    snapshot.store is not None
                    and str(snapshot.store.store_type) in goal.expectation
                ):
                    register.close_suspended(
                        claim.claim_id, "complete", "entered-store"
                    )
                continue
            if goal.kind != CLAIM_GOAL_REACH:
                continue
            if goal.monster is not None:
                monster = self._claim_perceived_monster(snapshot, goal.monster)
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
                elif self._claim_entered_store_at(snapshot, goal.cell):
                    register.close_suspended(
                        claim.claim_id, "complete", "entered-store"
                    )

    def _claim_owner_transition(
        self, register, standing, owner, goal, rung, survival, non_discardable,
        *, snapshot
    ):
        """How this decision treats the claim the previous one declared.

        Returns ``(action, label, violation)``.  Only a held claim that is
        still open with a Reach or Observe goal matters:

        * an owner change to a strictly higher rung (rev 10 item 2) is a
          preemption -- the caller suspends the holder (``survival-preemption``
          when the new decision is survival, as S2a.1 labelled it);
        * survival that does not outrank the holder, or the same owner turning
          to another goal on a survival decision, replaces it -- the caller
          releases it ``survival-displaced``; survival is exempt, so this is
          not a violation (round 2 F1/F2);
        * the same owner replacing its own open goal otherwise is a retarget
          violation (rev 10 item 4) -- never a preemption followed by
          ``resume-goal-changed`` on the same row;
        * any other owner change is a violation, and so is any ordinary
          change away from a store-operation or transaction ``Observe`` claim
          (rev 10.1 item 6). A town survival decision suspends an S3 holder;
          adjacent melee also suspends a pending town monster chase.

        Nothing stops: the row records it.
        """
        if (
            standing is None
            or not standing.is_open
            or standing.goal.kind not in (CLAIM_GOAL_REACH, CLAIM_GOAL_OBSERVE)
        ):
            return None, None, None
        if register.continues(owner, goal, non_discardable):
            # The same owner pursuing the same goal keeps its claim, survival
            # or not (``declare`` updates its survival flag).
            return None, None, None
        if (standing.owner == owner and standing.goal.source in {'transaction'} and (goal.source == CLAIM_OBSERVE_STORE_ENTRY) and (self.last_reason or '').endswith(':await-entry')):
            return CLAIM_PREEMPTION, "transaction-entry-wait", None
        # S3 town operations survive an emergency even when their Observe
        # source normally forbids suspension.  Other owners keep the ladder's
        # bounded-rank preemption rule.
        if (survival and standing.owner != owner
                and snapshot.in_town
                and (standing.owner.value in CLAIM_S3_FAMILIES
                     or (standing.owner.value == "survival"
                         and self.last_reason == "melee"))):
            return CLAIM_PREEMPTION, "survival-preemption", None
        held = claim_rung_of_claim(
            standing.owner, standing.rung,
            non_discardable=standing.non_discardable,
        )
        if standing.owner == owner:
            verdict = CLAIM_SURVIVAL_DISPLACED if survival else CLAIM_VIOLATION
            kind = "retarget"
        else:
            verdict = claim_owner_change(
                held_rank=held.rank,
                held_goal_kind=standing.goal.kind,
                held_goal_source=standing.goal.source,
                held_survival=standing.survival,
                new_rank=rung.rank,
                new_survival=survival,
            )
            kind = "owner-change"
        if verdict == CLAIM_PREEMPTION:
            return CLAIM_PREEMPTION, (
                "survival-preemption"
                if survival
                else f"preempted-by:{owner.value}"
            ), None
        if verdict == CLAIM_SURVIVAL_DISPLACED:
            return CLAIM_SURVIVAL_DISPLACED, CLAIM_SURVIVAL_DISPLACED, None
        plan_changed = bool(getattr(self, "_decision_plan_change_evidence", None))
        from hengbot.plan_handoff import is_plan_handoff
        if kind == "owner-change" and is_plan_handoff(
            holder_family=standing.owner.value,
            next_family=owner.value,
            holder_kind=standing.goal.kind,
            holder_non_discardable=standing.non_discardable,
            same_rank=held.rank == rung.rank,
            plan_changed=plan_changed,
        ):
            kind = "plan-handoff"
        if (kind == 'owner-change' and standing.non_discardable and non_discardable and (standing.owner.value in {'equipment-txn', 'home-visit', 'home-errand'}) and (owner.value in {'equipment-txn', 'home-visit', 'home-errand'})):
            kind = "transaction-contention"
        return None, None, {
            "kind": kind,
            "from": standing.owner.value,
            "to": owner.value,
            "claim_id": standing.claim_id,
            "goal": standing.goal.as_dict(),
            "from_rank": held.rank,
            "to_rank": rung.rank,
            "scope": claim_pair_scope(held, rung),
            "survival": bool(standing.survival or survival),
        }

    def _claim_resolve_suspended(
        self, register, owner, goal, rung, survival, non_discardable
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
            claim.owner.value in CLAIM_S3_FAMILIES for claim in stack
        ):
            return None
        if (goal.source == CLAIM_OBSERVE_STORE_ENTRY
                and (self.last_reason or "").endswith(":await-entry")):
            return None
        match = claim_resumable_index(stack, owner, goal, non_discardable)
        for index in range(len(stack) - 1, -1, -1):
            top = stack[index]
            if index == match:
                return top
            held = claim_rung_of_claim(
                top.owner, top.rung, non_discardable=top.non_discardable
            )
            if match is None and top.owner == owner:
                register.close_suspended(
                    top.claim_id, "release", "resume-goal-changed"
                )
                # the new claim opens here; the claims below are read the
                # same way, so it never sits above one it does not outrank
                continue
            if claim_nests_over(top_rank=held.rank, new_rank=rung.rank):
                if match is None:
                    return None
                continue
            if survival:
                register.close_suspended(
                    top.claim_id, "release", CLAIM_SURVIVAL_DISPLACED
                )
                continue
            register.close_suspended(
                top.claim_id,
                "release",
                "resume-displaced",
                violation={
                    "kind": "displaced",
                    "from": top.owner.value,
                    "to": owner.value,
                    "claim_id": top.claim_id,
                    "goal": top.goal.as_dict(),
                    "from_rank": held.rank,
                    "to_rank": rung.rank,
                    "scope": claim_pair_scope(held, rung),
                    "survival": bool(top.survival or survival),
                },
            )
        return None

    def _declare_triggers(self, monsters, family: str | None = None) -> None:
        """Record-only (rev 10.1 item 9): the monsters this producer acted on.

        A producer of positioning, esp-threat or escape calls it with the
        selection it already made on this board -- the look-ahead pack it
        retreats from, the committed hunt targets, the hostiles it flees --
        right after setting its reason, as ``_declare_reach`` does.  The slot
        carries the writer's census family; the declaration uses it only when
        that family is the row's owner.  Nothing is recomputed here.
        """
        self._decision_triggers = (
            family if family is not None
            else self._claim_family_of(self.last_reason),
            tuple(sorted({
                (int(monster.index), int(monster.race_id))
                for monster in monsters
            })),
        )

    def _claim_trigger_monsters(self, owner, goal):
        """Rev 10.1 item 9 / design 5.4.1: the monsters behind a new claim.

        For a Reach or Observe claim of positioning, hunt, esp-threat, combat
        or escape: the ``(index, race_id)`` pairs its producer declared on
        this board (``_declare_triggers``), plus the chased monster of a
        monster goal (hunt, whose target is its goal).  A producer that
        declared none records none -- never every perceived hostile.
        """
        if (
            owner.value not in CLAIM_TRIGGER_FAMILIES
            or goal.kind not in (CLAIM_GOAL_REACH, CLAIM_GOAL_OBSERVE)
        ):
            return ()
        found: set[tuple[int, int]] = set()
        slot = getattr(self, "_decision_triggers", None)
        if (
            isinstance(slot, tuple)
            and len(slot) == 2
            and slot[0] == owner.value
        ):
            found.update(tuple(pair) for pair in slot[1])
        if goal.monster is not None:
            found.add((int(goal.monster[0]), int(goal.monster[1])))
        return tuple(sorted(found))

    @staticmethod
    def _claim_trigger_perceived(snapshot: Snapshot, triggers):
        """The game turn, when one of ``triggers`` is perceived on this board."""
        if not triggers:
            return None
        wanted = {tuple(pair) for pair in triggers}
        for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
            if (monster.index, monster.race_id) in wanted:
                return snapshot.turn
        return None

    # -- S2b.2: the bar table (design 3.2, 3.3, 5.4.1) ----------------------
    #
    # Record-only while ``_claim_bar_enforced`` is off (the default and the
    # only shipped setting): the helpers below write the register and the
    # decision row.  With the switch on, ``_claim_bar_skips`` also keeps a
    # barred rung from running at all (design 3.3's plumbing), which is
    # exercised by tests only.

    @staticmethod
    def _claim_perceived_pairs(snapshot: Snapshot) -> frozenset:
        """Every ``(index, race_id)`` this board perceives (seen or detected)."""
        return frozenset(
            (int(monster.index), int(monster.race_id))
            for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
        )

    @staticmethod
    def _claim_durable_clearance(key):
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

    def _claim_errand_clearance(self, snapshot: Snapshot, owner: str, reason):
        """The durable clearance key of an errand owner on this board."""
        return self._claim_durable_clearance(
            self._town_retirement_clearance_key(snapshot, owner, reason)
        )

    def _claim_bar_after(
        self, snapshot: Snapshot, bar: ClaimBar, perceived=None
    ) -> ClaimBar | None:
        """``bar`` as this board leaves it, ``None`` when the board lifts it."""
        return claim_bar_after_board(
            bar,
            turn=snapshot.turn,
            perceived=(
                perceived
                if perceived is not None
                else self._claim_perceived_pairs(snapshot)
            ),
            hold=DETECTED_THREAT_HOLD_MAX_GAME_TURNS,
            clearance_of=lambda errand: self._claim_errand_clearance(
                snapshot, errand.owner.value, errand.reason
            ),
        )

    def _claim_bar_lift(self, snapshot: Snapshot, register) -> list[dict]:
        """Design 3.2 / 3.3: the lift pass of this board.

        A threat-triggered bar lifts once ``DETECTED_THREAT_HOLD_MAX_GAME_TURNS``
        game turns (the existing 50-turn clock of the detected-threat choke
        release) have passed with none of its trigger monsters perceived; an
        errand bar lifts when the durable part of its owner's retirement
        clearance key differs from the one recorded when it was set.  Returns
        the lifted bars as row entries.
        """
        bars = register.bars
        if not bars:
            return []
        perceived = self._claim_perceived_pairs(snapshot)
        kept = []
        lifted = []
        for bar in bars:
            after = self._claim_bar_after(snapshot, bar, perceived)
            if after is None:
                lifted.append({
                    **bar.as_dict(),
                    "lifted_turn": snapshot.turn,
                    "lifted_sequence": self._decision_sequence,
                })
            else:
                kept.append(after)
        if lifted or kept != list(bars):
            register.replace_bars(kept)
        return lifted

    def _claim_bar_for(self, snapshot: Snapshot, claim, ending: str):
        """The bar a claim that ended this way earns, or ``None``.

        Design 3.2: a preemptor that does not reach its own goal is barred;
        survival is exempt (the row's ``survival`` flag, rev 10.1 item 3).
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
        if claim.goal.kind not in (CLAIM_GOAL_REACH, CLAIM_GOAL_OBSERVE):
            return None
        if ending == CLAIM_CLOSED_BY_COMPLETE:
            return None
        if claim.closed_reason in (
            CLAIM_SURVIVAL_DISPLACED, CLAIM_SUSPENDED_EXPIRED
        ):
            return None
        threat = claim.owner.value in CLAIM_TRIGGER_FAMILIES
        perceived_now = self._claim_trigger_perceived(
            snapshot, claim.trigger_monsters
        )
        common = {
            "owner": claim.owner,
            "goal": claim.goal,
            "rung": claim_rung_of_claim(
                claim.owner, claim.rung, non_discardable=claim.non_discardable
            ).name,
            "since_turn": snapshot.turn,
            "since_sequence": self._decision_sequence,
            "claim_id": claim.claim_id,
            "ending": (
                ending if claim.closed_reason is None
                else f"{ending}:{claim.closed_reason}"
            ),
        }
        if threat:
            return ClaimBar(
                kind=CLAIM_BAR_THREAT,
                triggers=tuple(claim.trigger_monsters),
                last_perceived_turn=(
                    perceived_now
                    if perceived_now is not None
                    else claim.last_perceived_turn
                ),
                **common,
            )
        no_step = (claim.closed_reason or "").startswith("no-step:")
        if ending != CLAIM_CLOSED_BY_RETIRED and not no_step:
            return None
        # The retirement is this decision's (``_claim_owner_retired``), so the
        # reason the key is computed for is the decision's own.
        reason = None if no_step else (
            self.last_reason
            if self._claim_family_of(self.last_reason) == claim.owner.value
            else None
        )
        return ClaimBar(
            kind=CLAIM_BAR_ERRAND,
            clearance=self._claim_errand_clearance(
                snapshot, claim.owner.value, reason
            ),
            reason=reason,
            **common,
        )

    def _claim_set_bars(self, snapshot: Snapshot, register, *, dropped=None):
        """Bar the claims that ended on this decision; returns row entries.

        ``register.take_ended`` gives every claim a closing call ended since
        the last declaration (a producer's release, the exit's expiry, a
        retirement, a suspended claim displaced or released); ``dropped`` is
        the held claim this row's violation left without a closing.
        """
        ended = [(claim, claim.closed) for claim in register.take_ended()]
        if dropped is not None:
            ended.append((dropped, "abandoned"))
        entries = []
        for claim, ending in ended:
            bar = self._claim_bar_for(snapshot, claim, ending)
            if bar is None:
                continue
            register.set_bar(bar)
            entries.append(bar.as_dict())
        return entries

    def _claim_would_bar(self, register, claim, survival):
        """Design 3.2 / 3.3 at the exit: the bar this decision would meet.

        The decided owner and goal matched against the table as the ladder
        would have read it; survival is never barred.  Recorded on the row;
        with the switch off it changes nothing.
        """
        if survival or claim is None:
            return None
        bar = register.barring(claim.owner, claim.goal)
        if bar is None:
            return None
        return {
            "owner": bar.owner.value,
            "goal": bar.goal.as_dict(),
            "bar_since_turn": bar.since_turn,
            "triggers": [list(pair) for pair in bar.triggers],
        }

    @staticmethod
    def _claim_would_skip(register, rung, survival):
        """Round 2: the skip the switch would have made on this decision.

        The switch decides before a rung runs, so it can only know the rung,
        not the goal the rung would choose: a gated rung
        (``claim_ladder.BAR_GATED_RUNGS``) is skipped while a bar that a claim
        of that rung earned stands.  Recorded when the decided rung is one of
        them, beside ``would_bar``'s exact owner-and-goal match.
        """
        if survival or rung.name not in CLAIM_BAR_GATED_RUNGS:
            return None
        for bar in register.bars:
            if bar.rung == rung.name:
                return {
                    "rung": rung.name,
                    "owner": bar.owner.value,
                    "goal": bar.goal.as_dict(),
                    "bar_since_turn": bar.since_turn,
                }
        return None

    def _claim_bar_skips(self, snapshot: Snapshot, rung_name: str) -> bool:
        """Design 3.3's plumbing, decided before the rung runs (switch on).

        ``_decide`` asks this right before it calls a gated rung
        (``claim_ladder.BAR_GATED_RUNGS``), and does not call the rung when
        the answer is True, so a barred producer spends none of its own state
        (a choke plan's decision counters, a committed route).  With the
        switch off -- the default and the only shipped setting -- it answers
        False at once and the rung runs exactly as before.  With it on, the
        rung is skipped while a bar that a claim of this rung earned stands
        on this board.  The gated rungs cannot answer survival, and survival
        claims earn no bar.
        """
        if not getattr(self, "_claim_bar_enforced", False):
            return False
        register = getattr(self, "_claim_register", None)
        if register is None:
            return False
        for bar in register.bars:
            if bar.rung != rung_name or self._claim_bar_after(snapshot, bar) is None:
                continue
            self._decision_bar_skips = [
                *(getattr(self, "_decision_bar_skips", None) or ()),
                {
                    "rung": rung_name,
                    "owner": bar.owner.value,
                    "goal": bar.goal.as_dict(),
                    "bar_since_turn": bar.since_turn,
                },
            ]
            return True
        return False

    def _claim_errand_hold(self, family: str, *, enforced: bool | None = None,
                           arrival_board: Snapshot | None = None):
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
            return claim.owner.value in CLAIM_S3_FAMILIES | {"quest-request"}

        register = getattr(self, "_claim_register", None)
        standing = getattr(register, "current", None)
        if (
            standing is not None
            and standing.is_open
            and town_errand(standing)
            and standing.owner.value != family
            and standing.goal.kind in {CLAIM_GOAL_REACH, CLAIM_GOAL_OBSERVE}
            and not (arrival_board is not None
                     and self._claim_reach_arrival(arrival_board, standing)
                     is not None)
        ):
            return standing
        if enforced is None:
            enforced = getattr(self, "_town_claim_bar_enforced", False)
        if enforced and register is not None:
            for claim in reversed(register.suspended):
                if (claim.closed is None
                        and claim.state.value == "suspended"
                        and town_errand(claim)
                        and claim.owner.value != family
                        and claim.goal.kind in {
                            CLAIM_GOAL_REACH, CLAIM_GOAL_OBSERVE
                        }
                        and not (claim.goal.source == CLAIM_OBSERVE_KNOWLEDGE
                                 and self._home_knowledge_current)):
                    return claim
        return None

    def _delegation_records(self) -> list[ExecutionDelegation]:
        records = getattr(self, "_execution_delegations", None)
        if records is None:
            records = []
            self._execution_delegations = records
        return records

    def _open_execution_delegation(
        self, parent_family: str, delegate_family: str,
        work_identity: tuple, purpose_identity: tuple,
        expected_effect: str, budget_reference: str,
    ) -> ExecutionDelegation:
        """Reserve a named child before invoking its executor (record-only)."""
        work_identity = tuple(work_identity)
        purpose_identity = tuple(purpose_identity)
        for record in self._delegation_records():
            if (record.lifecycle in {"reserved", "open"}
                    and record.parent_family == parent_family
                    and record.delegate_family == delegate_family
                    and record.work_identity == work_identity
                    and record.purpose_identity == purpose_identity):
                return record
        record = ExecutionDelegation(
            None, parent_family, delegate_family, work_identity,
            purpose_identity, self._decision_sequence, expected_effect,
            budget_reference, "reserved",
        )
        self._delegation_records().append(record)
        return record

    def _end_execution_delegation(
        self, delegate_family: str, work_identity: tuple,
        *, completed: bool, cause: str,
    ) -> None:
        for record in self._delegation_records():
            if (record.lifecycle in {"reserved", "open"}
                    and record.delegate_family == delegate_family
                    and record.work_identity == tuple(work_identity)):
                record.lifecycle = "completed" if completed else "released"
                record.ending = cause

    def _bind_execution_delegations(self, claim) -> None:
        """Bind same-decision reservations or cancel an unmatched opening."""
        for record in self._delegation_records():
            if (record.lifecycle != "reserved"
                    or record.opening_decision != self._decision_sequence):
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

    def _cancel_unbound_execution_delegations(self) -> None:
        """End reservations left behind by a decision without a claim exit."""
        for record in self._delegation_records():
            if record.lifecycle == "reserved":
                record.lifecycle = "released"
                record.ending = "exit-not-reached"

    def _observe_execution_delegations(self) -> None:
        """Retire children only when their named source resolves."""
        session = self._equipment_transaction_session
        visit = self._store_visit
        for record in self._delegation_records():
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
                    parent = getattr(self._claim_register, "current", None)
                    arrived_claim = (
                        parent is not None
                        and parent.claim_id == record.parent_claim_id
                        and parent.closed == CLAIM_CLOSED_BY_COMPLETE
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
                if self._home_knowledge_current:
                    record.lifecycle = "completed"
                    record.ending = "catalogue-adopted"
            elif work[:1] == ("filed",):
                request = self._home_errand.request
                if request is None or (
                    request.signature, request.quantity,
                    request.origin, request.purpose
                ) != work[1:]:
                    record.lifecycle = "released"
                    record.ending = "filed-request-replaced"
                elif not self._home_errand.active:
                    record.lifecycle = "completed" if (
                        self._home_errand.state.value == "done"
                    ) else "released"
                    record.ending = f"filed-request:{self._home_errand.state.value}"
            if record.lifecycle == "open" and record.parent_claim_id is not None:
                register = self._claim_register
                live = [register.current, *register.suspended]
                if not any(
                    claim is not None and claim.claim_id == record.parent_claim_id
                    and claim.is_open for claim in live
                ):
                    record.lifecycle = "released"
                    record.ending = "parent-claim-ended"
        for record in self._delegation_records():
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

    def _town_errand_deferral(self, family, reason, snapshot=None,
                              *, work_identity=None, enforced=True,
                              arrival_board=None):
        """Pure entry admission verdict; recording belongs to the caller."""
        register = getattr(self, "_claim_register", None)
        if enforced and snapshot is not None and register is not None:
            for bar in register.bars:
                if (bar.kind == CLAIM_BAR_ERRAND
                        and ":no-step:" in (bar.ending or "")
                        and bar.owner.value == family
                        and self._claim_bar_after(snapshot, bar) is not None):
                    return {"holder_family": family, "holder_claim_id": None,
                            "deferred_family": family, "deferred_reason": reason,
                            "token_would_admit": False, "token_work_identity": None,
                            "active_bar": True}
        holder = self._claim_errand_hold(
            family, enforced=enforced,
            arrival_board=arrival_board if arrival_board is not None else snapshot)
        if holder is None:
            return None
        token = self._recorded_execution_token(
            holder, family, reason, work_identity=work_identity)
        return {"holder_family": holder.owner.value,
                "holder_claim_id": holder.claim_id, "deferred_family": family,
                "deferred_reason": reason, "token_would_admit": token is not None,
                "token_work_identity": token.work_identity if token else None}

    def _defer_town_errand(
        self, family: str, reason: str, *, work_identity: tuple | None = None,
        preserve_home_hold: bool = True,
    ) -> bool:
        """Apply the S3.3 hold to the requested town producer."""
        enforced = (getattr(self, "_town_claim_bar_enforced", False)
                    or (preserve_home_hold and self._home_sequence_has_holder()))
        row = self._town_errand_deferral(
            family, reason, getattr(self, "_map_predicate_snapshot", None),
            work_identity=work_identity, enforced=True,
            arrival_board=self._home_hold_board() if enforced else None)
        if row is None:
            return False
        active_bar = row.pop("active_bar", False)
        if (family in {"home-scan", "home-errand"}
                and reason in {"choose-key-scan", "outside-scan", "open-home-scan"}):
            # These entries immediately guard the knowledge macro. OFF still
            # emits it; ON never reaches its producer when this verdict holds.
            # Bind that fact to the candidate key, not merely to a family that
            # might also have an unrelated, ungated output later this decision.
            row["producer_key"] = ("~9\x1b\x1b" if reason == "outside-scan"
                                   else HOME_KNOWLEDGE_MACRO)
        if not active_bar:
            if getattr(self, "_decision_errand_deferred", None) is None:
                self._decision_errand_deferred = []
            self._decision_errand_deferred.append(row)
        deferred_now = enforced and not row["token_would_admit"]
        if (deferred_now and family == "home-scan"
                and not row["deferred_reason"].startswith("restore-debt:")):
            self._offer_execution_no_step(
                producer="home-scan",
                work_id=f"home-knowledge:{self._home_knowledge_scan_epoch}",
                cause=(f"deferred:{reason}:active-bar" if active_bar else
                       f"deferred:{reason}:holder:{row['holder_claim_id']}"),
            )
        return deferred_now

    def _town_plan_defers(self, family):
        """Pure plan-order entry predicate shared with the shadow census."""
        if (family not in CLAIM_TOWN_ERRAND_FAMILIES | {
                "departure", "fundraising", "explore"}
                or self._claim_errand_hold("__none__", enforced=True) is not None):
            return False
        plan = getattr(self, "_town_errand_plan", None)
        if plan is None or plan.index >= len(plan.stops):
            return False
        next_families = tuple(plan.requester_families.get(plan.stops[plan.index], ()))
        return (family not in next_families and family != 'store-router')

    def _retire_finished_home_errand_plan_stop(self) -> None:
        """Drop a Home stop whose sole requester has already finished."""
        plan = getattr(self, "_town_errand_plan", None)
        if plan is None or plan.index >= len(plan.stops):
            return
        stop = plan.stops[plan.index]
        if (stop != STORE_HOME
                or set(plan.requester_families.get(stop, ())) != {"home-errand"}
                or self._home_errand.active
                or self._home_errand.request is not None):
            return
        plan.completed_this_visit.append(stop)
        plan.current_stop_passes = 0
        plan.index += 1

    def _town_gate_exempt(self, family: str, reason: str = "",
                          snapshot: Snapshot | None = None) -> bool:
        """Families and survival outputs outside the town errand hold."""
        if family in {"survival", "detectors", "bookkeeping"}:
            return True
        if (claim_is_survival(reason, self._survival_return_trigger)
                or reason.startswith("town:kill-mob")):
            return True
        return bool(
            snapshot is not None and reason == "melee"
            and any(
                not monster.pet
                and snapshot.player.position.distance_to(monster.position) <= 1
                for monster in snapshot.visible_monsters
            )
        )

    def _town_producer_entry(self, rung_name: str, call,
                             *, family: str | None = None):
        """Ask the town holder before running a ladder producer.

        The rung table supplies the producer's family.  In particular, this
        test precedes any reservation, visit mutation, or execution offer in
        the producer.  Survival and detectors remain outside the errand hold.
        """
        board = getattr(self, "_map_predicate_snapshot", None)
        if (board is not None
                and not (getattr(board, "in_town", False)
                         or getattr(board, "store", None) is not None)):
            return call()
        rung = (claim_rung_named(rung_name) if family is None
                else claim_rung_of(family, None))
        if rung is None:
            raise ValueError(f"unknown town producer rung: {rung_name}")
        session = self._equipment_transaction_session
        holder = self._claim_errand_hold("__none__", enforced=True, arrival_board=board)
        before = len(getattr(self, "_decision_errand_deferred", ()) or ())
        if (session is not None and not session.complete
                and holder is not None and holder.owner.value == "equipment-txn"
                and rung.family == "equipment-txn"
                and rung_name not in {
                    "_equipment_transaction_town_key#1", "_equipment_transaction_town_key#2",
                    "_equipment_transaction_town_owner_key", "_equipment_transaction_home_key",
                    "home-atomic-withdraw", "home-atomic-deposit", "_shopping_approach_key#1",
                }):
            # The family also contains suppression, inscriptions and rearming.
            # OFF records the same pre-call verdict that ON enforces.
            if getattr(self, "_decision_errand_deferred", None) is None:
                self._decision_errand_deferred = []
            self._decision_errand_deferred.append({
                "holder_family": "equipment-txn", "holder_claim_id": holder.claim_id,
                "deferred_family": rung.family, "deferred_reason": f"entry:{rung_name}",
                "token_would_admit": False, "token_work_identity": None,
            })
            if getattr(self, "_town_claim_bar_enforced", False):
                return None
        if (not self._town_gate_exempt(rung.family)
                and self._defer_town_errand(
                    rung.family, f"entry:{rung_name}",
                    # These entries were added by S3.3. OFF must only observe
                    # them; historical rungs retain their cross-area Home hold.
                    preserve_home_hold=rung_name not in {
                        "verified-disposal", "town-item-processing", "idle-fallback",
                        "home-atomic-withdraw", "home-atomic-deposit", "town-teleport",
                    })):
            return None
        if (getattr(self, "_town_claim_bar_enforced", False)
                and self._town_plan_defers(rung.family)):
            plan = self._town_errand_plan
            if getattr(self, "_decision_errand_deferred", None) is None:
                self._decision_errand_deferred = []
            self._decision_errand_deferred.append({
                "holder_family": "town-plan", "holder_claim_id": None,
                "deferred_family": rung.family,
                "deferred_reason": f"plan-next:{plan.stops[plan.index]}:{rung_name}",
                "token_would_admit": False, "token_work_identity": None,
            })
            return None
        key = call()
        # OFF runs the same admission probe, then runs the historical producer.
        # Bind a refused entry to that producer's actual result. A later output
        # of the same family cannot borrow this evidence.
        for row in (getattr(self, "_decision_errand_deferred", ()) or ())[before:]:
            if (row["deferred_reason"] == f"entry:{rung_name}"
                    and row["deferred_family"] == rung.family
                    and isinstance(key, str)
                    and self._claim_family_of(self.last_reason) == rung.family):
                row["producer_key"] = key
        return key

    def _town_held_decision(self, key):
        """The selected key belongs to the live town holder's own family."""
        if (not getattr(self, "_town_claim_bar_enforced", False)
                or key is None):
            return None
        if self._town_unbound_entry_wait(key):
            # An entry sequence can be armed without a store operation.  Let
            # the downstream progress invariant route that unbound wait.
            return None
        holder = self._claim_errand_hold("__none__")
        if (holder is not None
                and self._claim_family_of(self.last_reason or "")
                == holder.owner.value):
            return holder
        return None

    def _town_unbound_entry_wait(self, key) -> bool:
        visit = getattr(self, "_store_visit", None)
        return bool(
            key == ""
            and self.last_reason == "store:entry-await-observation"
            and visit is not None
            and not visit.operation_posted
            and visit.claim_operation_identity is None
        )

    def _town_shop_entry_family(self) -> str:
        """The shop family authorized by the current visit or its holder."""
        visit = getattr(self, "_store_visit", None)
        family = getattr(visit, "opened_for_family", None)
        if family in {"shop-buy", "shop-sell"}:
            return family
        holder = self._claim_errand_hold("__none__")
        if holder is not None and holder.owner.value in {"shop-buy", "shop-sell"}:
            return holder.owner.value
        return "shop-buy"

    def _town_refuse_rewrite(self, stage: str, holder) -> None:
        refused = getattr(self, "_decision_rewrite_refused", None)
        if refused is None:
            refused = []
            self._decision_rewrite_refused = refused
        refused.append({
            "stage": stage, "holder_family": holder.owner.value,
            "holder_claim_id": holder.claim_id,
        })

    def _recorded_execution_token(
        self, holder, family: str, reason: str,
        *, work_identity: tuple | None = None,
    ):
        """Find the live, identity-matching grant for this executor."""
        for record in getattr(self, "_execution_delegations", ()) or ():
            bound = (record.lifecycle == "open"
                     and record.parent_claim_id == holder.claim_id)
            reserved_for_holder = (
                record.lifecycle == "reserved"
                and record.opening_decision == self._decision_sequence
                and record.parent_claim_id is None
                and holder is getattr(self._claim_register, "current", None)
            )
            if (not (bound or reserved_for_holder)
                    or record.parent_family != holder.owner.value
                    or record.delegate_family != family):
                continue
            work = record.work_identity
            if family == "equipment-txn" and work[:1] == ("session",):
                session = self._equipment_transaction_session
                if ((work_identity is None
                     or work == tuple(work_identity))
                        and session is not None
                        and session.target_loadout_id == work[2]
                        and tuple((action.kind, action.target_slot,
                                   action.item_identity)
                                  for action in session.plan.actions) == work[3]):
                    return record
            elif family == "home-scan" and reason in {
                "choose-key-scan", "outside-scan", "open-home-scan",
                "final:home:request-knowledge-scan",
            }:
                request = self._home_errand.request
                if (request is not None and self._home_errand.needs_knowledge
                        and work[:1] == ("knowledge",)
                        and work[2:] == (request.signature, request.purpose)
                        and self._home_atomic_deposit_pending is None
                        and self._home_atomic_withdraw_pending is None):
                    return record
            elif family == "store-router" and work[:1] == ("route",):
                visit = self._store_visit
                if (visit is not None and visit.opened_sequence == work[1]
                        and visit.store_type == work[2]):
                    return record
            elif family == "home-visit" and work[:1] == ("home-operation",):
                visit = self._store_visit
                if (visit is not None and visit.operation_posted
                        and visit.claim_operation_identity == work[1:]
                        and visit.operation_producer_family == holder.owner.value):
                    return record
            elif family == "home-errand" and work[:1] == ("filed",):
                session = self._equipment_transaction_session
                visit = self._store_visit
                unfinished_transaction = (
                    holder.owner.value == "equipment-txn"
                    and (
                        (session is not None and not session.complete)
                        or (visit is not None and visit.operation_posted
                            and not visit.operation_effect_observed)
                    )
                )
                if (reason in {
                        "file", "file-combat-weapon", "file-identification"
                    }
                        and work_identity is not None
                        and work == tuple(work_identity)
                        and not unfinished_transaction
                        and self._home_atomic_deposit_pending is None
                        and self._home_atomic_withdraw_pending is None):
                    return record
        return None

    def _town_declaration_stop(self, family: str, cause: str = "missing") -> None:
        self.last_reason = f"ownership:declaration-{cause}:{family}"
        return None

    def _town_release_declared_holder(self, holder, snapshot: Snapshot,
                                      cause: str) -> None:
        register = self._claim_register
        if holder is register.current:
            ended = register.release(f"no-step:{cause}")
        else:
            register.close_suspended(holder.claim_id, "release",
                                     f"no-step:{cause}")
            ended = replace(holder, closed="release",
                            closed_reason=f"no-step:{cause}")
        if ended is not None:
            bar = self._claim_bar_for(snapshot, ended, ended.closed)
            if bar is not None:
                register.set_bar(bar)
        self._decision_no_step_release = True
        self.last_reason = f"ownership:holder-released:{holder.owner.value}"
        return None

    def _town_declared_producer_result(self, holder, snapshot: Snapshot,
                                       key: str | None,
                                       since_sequence: int,
                                       *, require_offer: bool = False) -> str | None:
        if key is not None:
            if require_offer:
                buffer = _decision_offers.get(self)
                offered = () if buffer is None else tuple(
                    offer for offer in buffer.steps
                    if offer[0] == key and offer[1] == holder.owner.value
                    and offer[12] > since_sequence
                )
                matching = any(
                    offer[2] == holder.execution.work_id
                    and offer[3] == holder.execution.next_step
                    and offer[4] == holder.execution.arguments
                    for offer in offered
                )
                if not matching:
                    if not offered:
                        return self._silent_holder_stop(holder.owner.value)
                    return self._town_declaration_stop(
                        holder.owner.value, "stale")
            return key
        buffer = _decision_offers.get(self)
        endings = () if buffer is None else buffer.no_steps
        outcome = next((entry for entry in reversed(endings)
                        if entry[0] == holder.owner.value
                        and entry[3] > since_sequence), None)
        if outcome is None:
            return self._silent_holder_stop(holder.owner.value)
        if require_offer and outcome[1] != holder.execution.work_id:
            return self._town_declaration_stop(holder.owner.value, "stale")
        if holder is not self._claim_register.current:
            return self._town_declaration_stop(holder.owner.value, "stale")
        _, work_id, fact, _, state = outcome
        if state == "done":
            self._claim_register.declare_execution(
                holder.claim_id, work_id=work_id,
                producer=holder.owner.value, state="done", evidence=fact)
        else:
            self._claim_register.declare_execution(
                holder.claim_id, work_id=work_id,
                producer=holder.owner.value, state="releasing", cause=fact)
        return self._town_holder_declared_key(
            self._claim_register.current, snapshot)

    def _town_holder_ladder_result(self, holder, snapshot: Snapshot) -> str | None:
        """Resolve the holder only after the ordinary town ladder has ended."""
        declaration = getattr(holder, "execution", None)
        if declaration is not None and declaration.state == "acting":
            buffer = _decision_offers.get(self)
            if buffer is not None and any(
                producer == holder.owner.value and work_id == declaration.work_id
                for producer, work_id, *_ in buffer.no_steps
            ):
                return self._town_declared_producer_result(
                    holder, snapshot, None, 0, require_offer=True)
        return self._town_holder_declared_key(holder, snapshot)

    def _home_tail_leave_ready(self, holder, snapshot):
        """Pure identity predicate for the posted Home tail."""
        if holder is None:
            return False
        family = holder.owner.value
        visit = self._store_visit
        return bool(family == "home-visit"
                and snapshot.store is None
                and visit is not None
                and visit.store_type == STORE_HOME
                and visit.phase == StoreVisitPhase.LEAVING
                and visit.operation_posted
                and visit.operation_released
                and not visit.operation_effect_observed
                and visit.claim_id == holder.claim_id
                and visit.claim_operation_identity is not None
                and getattr(self._home_visit, "state", None)
                == HomeVisitState.EXIT_PENDING
                and any(
                    record.lifecycle == "open"
                    and record.parent_claim_id == holder.claim_id
                    and record.parent_family == family
                    and record.delegate_family == "home-tail"
                    and record.work_identity == (
                        "staged-tail", *visit.claim_operation_identity)
                    for record in getattr(self, "_execution_delegations", ()) or ()
                ))

    def _home_tail_leave_continuation(self, holder, snapshot: Snapshot) -> str | None:
        """Continue the bound Home exit while its posted effect is unresolved."""
        if holder is None:
            return None
        family = holder.owner.value
        visit = self._store_visit
        if self._home_tail_leave_ready(holder, snapshot):
            # The staged operation has left its Home page, but its effect has
            # not been observed.  Keep the visit's own exit continuation in
            # control until that exact operation settles.
            self.last_reason = "home:leave-after-one-operation"
            self._offer_execution(
                LEAVE_STORE_KEY, producer=family,
                work_id=(f"home:leave:{visit.opened_sequence}:"
                         f"{visit.operation_key}"),
                next_step="store.leave.send",
                arguments=visit.claim_operation_identity,
                expected_effect="home-inventory-effect",
                continuation="home.operation.observe",
                budget_ref="home-operation-existing-budget",
            )
            return LEAVE_STORE_KEY
        return None

    @staticmethod
    def _town_declaration_binding_stop(holder):
        """Check identity and terminal state without dispatching a producer."""
        family = holder.owner.value
        declaration = getattr(holder, "execution", None)
        if (declaration is None or declaration.claim_id != holder.claim_id
                or declaration.producer != family):
            return f"ownership:declaration-missing:{family}"
        if declaration.state in {"done", "releasing"} and (
                declaration.operation_ref is not None or (
                    declaration.state == "releasing" and holder.non_discardable)):
            return f"ownership:declaration-stale:{family}"
        if declaration.state == "awaiting" and (
                not declaration.operation_ref
                or not declaration.operation_ref.startswith("decision:")):
            # Confirmed entry has no purchase operation reference yet.
            if (declaration.operation_ref is None
                    and family in {"shop-buy", "shop-sell"}
                    and declaration.continuation == "shop.one-shot.send"
                    and declaration.expected_effect == "store-page-open"):
                return None
            return f"ownership:declaration-stale:{family}"
        return None

    def _town_holder_structural_stop(self, holder, snapshot):
        """Pure dispatch validity; successful branches still run once in ON."""
        stop = self._town_declaration_binding_stop(holder)
        if stop is not None:
            return stop
        family = holder.owner.value
        declaration = holder.execution
        if declaration.state in {"done", "releasing"}:
            return None
        step = declaration.next_step
        if (declaration.expected_effect == "home-catalog-available"
                and declaration.work_id == "equipment:acquire-home-catalog"
                and (step == "home.approach-for-equipment-catalog"
                     or declaration.continuation == "home.catalogue.acquire")):
            return None
        if declaration.state == "awaiting":
            continuation = declaration.continuation
            if continuation == "equipment.suppression.observe":
                if (family == "equipment-txn"
                        and declaration.work_id == "suppress-random-teleport"
                        and len(declaration.arguments) == 1
                        and any(self._suppression_target_matches(item, declaration.arguments[0])
                                and "." in item.inscription
                                for item in (*snapshot.inventory, *snapshot.equipment))):
                    return None
                return f"ownership:declaration-stale:{family}"
            if continuation == "equipment.restore-observe":
                if family != "equipment-txn" or len(declaration.arguments) != 2:
                    return f"ownership:declaration-stale:{family}"
                slot, identity = declaration.arguments
                equipped = next((item for item in snapshot.equipment
                                 if item.slot == slot), None)
                if declaration.expected_effect == "digger-removed":
                    observed = (equipped is None and any(
                        equipment_identity(item) == identity
                        for item in snapshot.inventory))
                else:
                    observed = (equipped is not None
                                and equipment_identity(equipped) == identity)
                if not observed:
                    return f"ownership:declaration-stale:{family}"
                return None
            if (family in {"shop-buy", "shop-sell"}
                    and continuation == "shop.one-shot.send"):
                visit = self._store_visit
                if (visit is None
                        or declaration.arguments != (visit.store_type, visit.operation_key)
                        or declaration.work_id != (
                            f"shop-operation:{visit.opened_sequence}:"
                            f"{visit.store_type}:{visit.operation_key}")
                        or (snapshot.store is not None
                            and snapshot.store.store_type != visit.store_type)):
                    return f"ownership:declaration-stale:{family}"
                return None
            if continuation == "equipment.next-action":
                session = self._equipment_transaction_session
                if session is None:
                    return f"ownership:declaration-stale:{family}"
                if session.pending_action is not None:
                    return None
                step = "equipment.next-action"
                declaration = replace(declaration, arguments=())
            elif continuation == "route.resume":
                step = "route.resume"
            elif family == "quest-request" and continuation == "bounty.resume":
                step = "bounty.resume"
            elif continuation == "town.teleport.resume":
                step = "town.teleport.resume"
            elif continuation in {"home.knowledge.observe", "store.entry.observe",
                                  "home.operation.observe", "shop.one-shot.dispatch"}:
                return None
            elif continuation == "departure.step-off-entrance":
                if (len(declaration.arguments) == 2 and snapshot.store is None
                        and snapshot.player.position == Position(*declaration.arguments)):
                    return None
                return f"ownership:declaration-stale:{family}"
            else:
                return f"ownership:declaration-stale:{family}"
        elif declaration.state != "acting" or not step:
            return f"ownership:declaration-stale:{family}"
        if step == "route.resume":
            if len(declaration.arguments) != 2:
                return f"ownership:declaration-stale:{family}"
            route_kind, cell = declaration.arguments
            if route_kind not in {"entrance", "store"}:
                return f"ownership:declaration-stale:{family}"
            if not isinstance(cell, (tuple, list)) or len(cell) != 2:
                return f"ownership:declaration-stale:{family}"
            goal = Position(*cell)
            if (holder.goal.kind != CLAIM_GOAL_REACH
                    or holder.goal.cell != tuple(cell)):
                return f"ownership:declaration-stale:{family}"
        elif step == "town.teleport.resume":
            if (len(declaration.arguments) != 2
                    or not isinstance(declaration.arguments[0], int)):
                return f"ownership:declaration-stale:{family}"
        elif step == "bounty.resume":
            if (family != "quest-request"
                    or declaration.work_id != "normal-step4-bounty"):
                return f"ownership:declaration-stale:{family}"
        elif step == "equipment.next-action":
            session = self._equipment_transaction_session
            if session is None or session.current_action is None:
                return f"ownership:declaration-stale:{family}"
            args = declaration.arguments
            if args:
                action = session.current_action
                if args[0] in {"strip", "restore", "deposit"} and len(args) == 1:
                    return f"ownership:declaration-stale:{family}"
                elif (args[0] != action.kind
                      or args[-1] != action.item_identity
                      or (len(args) == 3
                          and args[1] != action.target_slot)):
                    return f"ownership:declaration-stale:{family}"
        elif step == "stair.post":
            if len(declaration.arguments) != 3:
                return f"ownership:declaration-stale:{family}"
            direction, floor, cell = declaration.arguments
            if (floor != snapshot.floor_key
                    or tuple(cell) != (snapshot.player.position.y,
                                       snapshot.player.position.x)
                    or direction not in {"<", ">"}
                    or snapshot.store is not None):
                return f"ownership:declaration-stale:{family}"
        elif step in {"home.knowledge.observe", "equipment.action.observe",
                      "home.operation.observe", "store.entry.observe"}:
            return f"ownership:declaration-stale:{family}"
        return None

    def _town_holder_declared_key(self, holder, snapshot: Snapshot) -> str | None:
        """Dispatch the holder's bound producer step; never reconstruct work."""
        family = holder.owner.value
        declaration = getattr(holder, "execution", None)
        if holder is self._home_catalogue_work_holder():
            return self._home_catalogue_work_key(snapshot)
        home_tail = self._home_tail_leave_continuation(holder, snapshot)
        if home_tail is not None:
            return home_tail
        stop = self._town_holder_structural_stop(holder, snapshot)
        if stop is not None:
            self.last_reason = stop
            return None
        if declaration.state in {"done", "releasing"}:
            if declaration.state == "done":
                return self._town_release_declared_holder(
                    holder, snapshot,
                    f"done:{declaration.evidence or 'producer-complete'}")
            return self._town_release_declared_holder(
                holder, snapshot, declaration.cause or declaration.evidence
                or "producer-complete")
        if declaration.state == "awaiting":
            # A posted native route can end short of its destination. The
            # declaration itself carries its next route step and destination.
            if declaration.continuation == "equipment.suppression.observe":
                self._observe_town_equipment_work(snapshot)
                self._decision_no_step_release = True
                self.last_reason = "ownership:holder-released:equipment-txn"
                return None
            if declaration.continuation == "route.resume":
                updated = self._claim_register.declare_execution(
                    holder.claim_id, work_id=declaration.work_id,
                    producer=family, state="acting", next_step="route.resume",
                    arguments=declaration.arguments,
                    expected_effect=declaration.expected_effect,
                    continuation="route.resume", budget_ref=declaration.budget_ref)
                if updated is None:
                    # Survival still owns current; dispatch the suspended
                    # route locally. Recording resumes its original claim.
                    declaration = replace(declaration, state="acting", next_step="route.resume")
                    holder = replace(holder, execution=declaration)
                else:
                    holder = self._claim_register.current
                    declaration = holder.execution
            elif family == "quest-request" and declaration.continuation == "bounty.resume":
                since = self._decision_offer_buffer().sequence
                key = self._town_order_step4_key(snapshot)
                return self._town_declared_producer_result(holder, snapshot, key, since)
            elif declaration.continuation == "equipment.restore-observe":
                since = self._decision_offer_buffer().sequence
                key = self._town_restore_weapon_key(snapshot)
                return self._town_declared_producer_result(
                    holder, snapshot, key, since)
            elif declaration.continuation == "equipment.next-action":
                session = self._equipment_transaction_session
                if session is None:
                    return self._town_declaration_stop(family, "stale")
                if session.pending_action is None:
                    updated = self._claim_register.declare_execution(
                        holder.claim_id, work_id=declaration.work_id,
                        producer=family, state="acting",
                        next_step="equipment.next-action",
                        arguments=(), expected_effect=declaration.expected_effect,
                        continuation="equipment.next-action",
                        budget_ref=declaration.budget_ref)
                    if updated is None:
                        declaration = replace(declaration, state="acting",
                                              next_step="equipment.next-action", arguments=())
                        holder = replace(holder, execution=declaration)
                    else:
                        holder = self._claim_register.current
                        declaration = holder.execution
                else:
                    self.last_reason = "equipment-transaction:await-confirmation"
                    return WAIT_KEY if snapshot.store is None else LEAVE_STORE_KEY
            elif declaration.continuation in {
                "home.knowledge.observe", "store.entry.observe",
                "home.operation.observe", "shop.one-shot.dispatch",
            }:
                self.last_reason = (
                    "home:scan-await-observation" if family == "home-scan"
                    else "store:entry-await-observation" if
                    declaration.continuation == "store.entry.observe"
                    else "shop:one-shot-in-flight")
                return WAIT_KEY
            elif (family in {"shop-buy", "shop-sell"}
                  and declaration.continuation == "shop.one-shot.send"):
                since = self._decision_offer_buffer().sequence
                key = self._release_staged_store_operation(snapshot)
                if key is None:
                    self.last_reason = "shop:one-shot-in-flight"
                    return ""
                self.last_reason = ("shop:one-shot-buy" if family == "shop-buy"
                                    else "shop:one-shot-sell")
                return self._town_declared_producer_result(holder, snapshot, key, since)
            elif declaration.continuation == "departure.step-off-entrance":
                if (
                    len(declaration.arguments) == 2
                    and snapshot.player.position
                    == Position(*declaration.arguments)
                    and snapshot.store is None
                ):
                    return self._town_release_declared_holder(
                        holder, snapshot, "entrance-cell-cleared"
                    )
                return self._town_declaration_stop(family, "stale")
            elif declaration.continuation == "town.teleport.resume":
                destination, reason = declaration.arguments
                return self._town_teleport_key(
                    snapshot, destination, producer=family, reason=reason)
            else:
                return self._town_declaration_stop(family, "stale")
        if declaration.state != "acting" or not declaration.next_step:
            return self._town_declaration_stop(family, "stale")
        step = declaration.next_step
        if family == "quest-request" and step == "bounty.resume":
            since = self._decision_offer_buffer().sequence
            key = self._town_order_step4_key(snapshot)
            return self._town_declared_producer_result(holder, snapshot, key, since)
        if step == "route.resume":
            route_kind, cell = declaration.arguments
            goal = Position(*cell)
            if route_kind == "entrance":
                key = self._town_travel_key(
                    snapshot, goal, ENTRANCE_TRAVEL_MACRO,
                    "town:travel-entrance")
                if key is not None:
                    return key
            next_cell = (self._town_map_goal_step(snapshot, goal)
                         or self._nearest_goal_step(
                             snapshot, lambda grid: grid.position == goal))
            if next_cell is None:
                return self._silent_holder_stop(family)
            self.last_reason = (
                "equipment-transaction:travel-home" if family == "equipment-txn"
                else "fixedquest:request:approach" if family == "quest-request"
                else "shop:approach")
            self._declare_reach(goal, family=family)
            key = self._direction_key(snapshot.player.position, next_cell)
            self._offer_execution(
                key, producer=family, work_id=declaration.work_id,
                next_step="route.resume", arguments=declaration.arguments,
                expected_effect=declaration.expected_effect,
                continuation="route.resume", budget_ref=declaration.budget_ref)
            return key
        if step == "equipment.next-action":
            since = self._decision_offer_buffer().sequence
            key = (self._equipment_transaction_home_key(snapshot)
                   if snapshot.store is not None
                   and snapshot.store.store_type == STORE_HOME
                   else self._equipment_transaction_town_key(snapshot))
            return self._town_declared_producer_result(
                holder, snapshot, key, since)
        if step == "town.teleport.resume" or (
                declaration.state == "awaiting"
                and declaration.continuation == "town.teleport.resume"):
            destination, reason = declaration.arguments
            return self._town_teleport_key(
                snapshot, destination, producer=family, reason=reason)
        if step == "stair.post":
            direction, floor, cell = declaration.arguments
            self.last_reason = "town:descend" if direction == ">" else "town:ascend"
            self._offer_execution(
                direction, producer=family, work_id=declaration.work_id,
                next_step="stair.post", arguments=declaration.arguments,
                expected_effect="floor-change",
                continuation="stair.observe-arrival",
                budget_ref=declaration.budget_ref)
            return direction
        if step in {"home.knowledge.observe", "equipment.action.observe",
                    "home.operation.observe", "store.entry.observe"}:
            # An acting observation without a posted operation is not a wait.
            return self._town_declaration_stop(family, "stale")
        # The other acting steps belong to producers in the ordinary ladder.
        # Re-entering one here repeats its broad side effects and may skip
        # intervening rungs. Reaching this branch means that producer was
        # silent on this board.
        return self._silent_holder_stop(family)

    def _town_holder_wait_key(self, holder, snapshot: Snapshot) -> str | None:
        """Advance the named holder, release an exhausted one, or stop."""
        declaration = holder.execution
        if getattr(self, "_town_claim_bar_enforced", False):
            return self._town_holder_declared_key(holder, snapshot)
        route_unresolved = False
        if (holder.owner.value == "store-router"
                and holder.goal.kind == CLAIM_GOAL_REACH
                and holder.goal.cell is not None):
            goal = Position(*holder.goal.cell)
            previous = holder.execution
            if (previous is not None and previous.state == "awaiting"
                    and previous.continuation == "route.resume"
                    and snapshot.player.position != goal
                    and holder is getattr(self._claim_register, "current", None)):
                self._claim_register.declare_execution(
                    holder.claim_id, work_id=previous.work_id,
                    producer=previous.producer, state="acting",
                    next_step="route.resume", arguments=previous.arguments,
                    expected_effect=previous.expected_effect,
                    continuation="route.resume", budget_ref=previous.budget_ref,
                )
                holder = self._claim_register.current
            store_type = (
                self._shopping_approach_store_type
                if self._shopping_approach_goal == goal else None
            )
            visit = getattr(self, "_store_visit", None)
            if (store_type is None and visit is not None
                    and visit.goal == goal):
                store_type = visit.store_type
            if (store_type is None and snapshot.store is None
                    and (entrance := snapshot.grids.get(goal)) is not None
                    and self._is_active_dungeon_entrance(entrance)):
                # The entrance is a store-router Reach without a store visit.
                # Native travel may release short of it; continue toward the
                # recorded cell under the same claim and travel stall budget.
                key = self._town_travel_key(
                    snapshot, goal, ENTRANCE_TRAVEL_MACRO,
                    "town:travel-entrance",
                )
                if key is not None:
                    return key
                step = (self._town_map_goal_step(snapshot, goal)
                        or self._nearest_goal_step(
                            snapshot, lambda grid: grid.position == goal
                        ))
                if step is not None:
                    self.last_reason = "shop:approach"
                    self._declare_reach(goal, family="store-router")
                    key = self._direction_key(snapshot.player.position, step)
                    self._offer_execution(
                        key, producer="store-router",
                        work_id=f"route:entrance:{goal.y},{goal.x}",
                        next_step="route.resume",
                        arguments=("entrance", (goal.y, goal.x)),
                        expected_effect=f"arrive:{goal.y},{goal.x}",
                        continuation="route.resume", budget_ref="town-travel",
                    )
                    return key
            if store_type is not None:
                step = self._shopping_approach_step(
                    snapshot, store_type, requester="store-router"
                )
                if step is not None and self._shopping_approach_goal == goal:
                    self.last_reason = "shop:approach"
                    key = self._shopping_approach_key(
                        snapshot, step, "shop:travel"
                    )
                    if (key not in {None, "", WAIT_KEY}
                            and self._claim_family_of(self.last_reason)
                            == "store-router"):
                        # This is the held route's step, even when a direct
                        # one-cell fallback did not write a fresh goal slot.
                        self._declare_reach(goal, family="store-router")
                    return key
            # A store plan may cease returning its old route after the posted
            # action ends short. The open Reach still names its destination;
            # keep walking there rather than treating the holder as silent.
            step = (self._town_map_goal_step(snapshot, goal)
                    or self._nearest_goal_step(
                        snapshot, lambda grid: grid.position == goal
                    ))
            if step is not None:
                self.last_reason = "shop:approach"
                self._declare_reach(goal, family="store-router")
                key = self._direction_key(snapshot.player.position, step)
                self._offer_execution(
                    key, producer="store-router",
                    work_id=f"route:store:{goal.y},{goal.x}",
                    next_step="route.resume",
                    arguments=("store", (goal.y, goal.x)),
                    expected_effect=f"arrive:{goal.y},{goal.x}",
                    continuation="route.resume", budget_ref="town-travel",
                )
                return key
            # A Reach still en route cannot be released as a no-step errand.
            # The final §3 branch reports an unresolved route consistently.
            route_unresolved = True
        session = self._equipment_transaction_session
        if (holder.owner.value in {'equipment-txn'} and session is not None and (not getattr(session, 'complete', False))):
            if session.pending_action is not None:
                self.last_reason = "equipment-transaction:await-confirmation"
                key = LEAVE_STORE_KEY if snapshot.store is not None else WAIT_KEY
                self._offer_execution(
                    key, producer=holder.owner.value,
                    work_id=("equipment:pending:"
                             f"{getattr(session, 'target_loadout_id', holder.claim_id)}"),
                    next_step="equipment.action.observe",
                    expected_effect="equipment-action-confirmed",
                    continuation="equipment.next-action",
                )
                return key
            if getattr(session, "current_action", None) is not None:
                key = (self._equipment_transaction_home_key(snapshot)
                       if snapshot.store is not None
                       and snapshot.store.store_type == STORE_HOME
                       else self._equipment_transaction_town_key(snapshot))
                if key is not None:
                    return key
        visit = self._store_visit
        if (visit is not None and visit.operation_posted
                and not visit.operation_released
                and not visit.operation_effect_observed
                and visit.operation_producer_family == holder.owner.value):
            if snapshot.store is not None:
                self.last_reason = "shop:await-leave-confirmation"
                return (LEAVE_STORE_KEY if snapshot.store.store_type == STORE_HOME
                        and self._home_entry_operation_posted else "\r")
            self.last_reason = (
                "equipment-transaction:await-confirmation"
                if holder.owner.value == "equipment-txn"
                else "home:atomic-deposit-await-confirmation"
                if holder.owner.value == "home-visit"
                else "shop:one-shot-in-flight"
            )
            return WAIT_KEY
        if (holder.goal.source == CLAIM_OBSERVE_STORE_ENTRY
                and self._store_entry_wait_owner is not None
                and self._store_entry_posted_owner is not None):
            self.last_reason = "store:entry-await-observation"
            return WAIT_KEY
        if (holder.goal.source == CLAIM_OBSERVE_KNOWLEDGE
                and self._home_knowledge_scan_requested):
            if holder is getattr(self._claim_register, "current", None):
                self.last_reason = "home:scan-await-observation"
                self._offer_execution(
                    WAIT_KEY, producer="home-scan",
                    work_id=f"home-knowledge:{self._home_knowledge_scan_epoch}",
                    next_step="home.knowledge.observe",
                    expected_effect="catalogue-adopted",
                    continuation="home.knowledge.observe",
                    budget_ref="home-knowledge-existing-epoch",
                )
                return WAIT_KEY
            # A suspended scan cannot be safely released while posted.
            knowledge_unresolved = True
        else:
            knowledge_unresolved = False
        children = [record for record in self._delegation_records()
                    if record.lifecycle == "open"
                    and record.parent_claim_id == holder.claim_id]
        unresolved = (route_unresolved or knowledge_unresolved or holder.non_discardable or bool(children) or (holder.owner.value in {'equipment-txn'} and False) or (visit is not None and visit.operation_posted and (not visit.operation_effect_observed) and (not visit.operation_released)) or (self._home_atomic_withdraw_pending is not None))
        if not unresolved:
            register = self._claim_register
            if holder is register.current:
                ended = register.release("no-step:unposted")
            else:
                register.close_suspended(
                    holder.claim_id, "release", "no-step:unposted"
                )
                ended = replace(holder, closed="release",
                                closed_reason="no-step:unposted")
            if ended is not None:
                bar = self._claim_bar_for(snapshot, ended, ended.closed)
                if bar is not None:
                    register.set_bar(bar)
            self._decision_no_step_release = True
            self.last_reason = f"ownership:holder-released:{holder.owner.value}"
            return None
        return self._silent_holder_stop(holder.owner.value)

    def _silent_holder_stop(self, family: str) -> None:
        self.last_reason = f"ownership:holder-silent:{family}"
        return None

    def _offer_home_knowledge_request(self, *, producer: str) -> None:
        """A catalogue scan continues its registered work, without a handoff."""
        holder = (self._home_catalogue_work_holder()
                  if producer == "home-scan" else None)
        self._offer_execution(
            HOME_KNOWLEDGE_MACRO,
            producer=holder.owner.value if holder is not None else producer,
            work_id=("equipment:acquire-home-catalog" if holder is not None
                     else f"home-knowledge:{self._town_visit_epoch}"),
            next_step="home.knowledge.request",
            expected_effect=("home-catalog-available" if holder is not None
                             else "catalogue-adopted"),
            continuation=("home.catalogue.acquire" if holder is not None
                          else "home.knowledge.observe"),
            budget_ref="home-knowledge-existing-epoch",
        )

    def _home_catalogue_sequence_enforced(self) -> bool:
        """Protect physical Home work under cross-area or S3.3 enforcement."""
        return bool(getattr(self, "_crossarea_fundraising_enforced", False)
                    or getattr(self, "_town_claim_bar_enforced", False))

    def _home_catalogue_work_holder(self):
        holder = self._claim_errand_hold("__none__", enforced=True)
        declaration = getattr(holder, "execution", None)
        if (declaration is not None
                and declaration.work_id == "equipment:acquire-home-catalog"
                and declaration.expected_effect == "home-catalog-available"):
            return holder
        return None

    def _home_hold_board(self) -> Snapshot | None:
        """The board whose observed arrival ends a route for the Home hold.

        S3.3 ON already closed that arrival before the producers ask, so ON
        passes no board and keeps its own verdicts unchanged.
        """
        if getattr(self, "_town_claim_bar_enforced", False):
            return None
        return getattr(self, "_map_predicate_snapshot", None)

    def _home_sequence_has_holder(self) -> bool:
        if not self._home_catalogue_sequence_enforced():
            return False
        # A route that this board shows arrived (at the Home it reached) is
        # not a physical Home sequence; holding Home producers for it made
        # every routed Home pass leave unfulfilled (live 2026-10-02 06:16).
        holder = self._claim_errand_hold(
            "__none__", enforced=True, arrival_board=self._home_hold_board())
        visit = getattr(self, "_store_visit", None)
        return bool(holder is not None and (
            self._home_catalogue_work_holder() is not None
            or (visit is not None and visit.store_type == STORE_HOME)
            or (holder.goal.source == CLAIM_OBSERVE_STORE_OPERATION
                and str(STORE_HOME) in holder.goal.expectation)))

    @claims(ClaimOwner.EQUIPMENT_TXN)
    def _home_catalogue_work_key(self, snapshot: Snapshot) -> str | None:
        """Advance registered catalogue work before a later Home errand."""
        holder = self._home_catalogue_work_holder()
        if holder is None:
            return None
        family = holder.owner.value
        if snapshot.store is not None:
            if snapshot.store.store_type != STORE_HOME:
                self._release_claim_goal("catalogue-wrong-store", owners=(family,))
                return None
            if self._open_home_page_is_complete(snapshot):
                self._adopt_home_catalogue(tuple(
                    self._inventory_item_from_store_item(item)
                    for item in snapshot.store.items))
                self._claim_exit_completion(snapshot, holder, [])
                self.last_reason = "equipment-transaction:home-catalog-acquired"
                self._offer_execution(
                    LEAVE_STORE_KEY, producer=family,
                    work_id="equipment:home-catalog-acquired",
                    next_step="store.leave.send", arguments=(STORE_HOME,),
                    expected_effect="outside-store",
                )
                return LEAVE_STORE_KEY
            # A partial page is not catalogue evidence. Exit under the same
            # work, then request the complete ~9 list from outside the UI.
            self.last_reason = "equipment-transaction:catalogue-leave-for-scan"
            key = LEAVE_STORE_KEY
        else:
            if self._home_knowledge_scan_inflight:
                self.last_reason = "equipment-transaction:catalogue-await-knowledge"
                # '5' on the Home entrance activates entry. Observe the
                # already posted scan without sending another game command.
                self._offer_execution_awaiting(
                    "", producer=family, work_id="equipment:acquire-home-catalog",
                    operation_ref=holder.execution.operation_ref,
                    expected_effect="home-catalog-available",
                    continuation="home.catalogue.acquire",
                )
                return ""
            else:
                self.last_reason = "equipment-transaction:catalogue-request-knowledge"
                key = HOME_KNOWLEDGE_MACRO
        self._offer_execution(
            key, producer=family, work_id="equipment:acquire-home-catalog",
            next_step="home.catalogue.acquire", expected_effect="home-catalog-available",
            continuation="home.catalogue.acquire", budget_ref="home-knowledge-existing-epoch",
        )
        return key

    def _s33_shadow_verdict(self, snapshot, key):
        """Resolve ON admission for the decided OFF board, without dispatch."""
        reason = self.last_reason or ""
        family = self._claim_family_of(reason)
        holder = self._claim_errand_hold("__none__", enforced=True,
                                         arrival_board=snapshot)
        declaration = getattr(holder, "execution", None)
        skipped = set()
        # Census the families the ON entry helper would refuse on this board.
        # Do not call any producer or create a delegation/offer buffer here.
        for entry_family in sorted(CLAIM_TOWN_ERRAND_FAMILIES | {
                "departure", "fundraising", "explore"}):
            if self._town_gate_exempt(entry_family):
                continue
            row = self._town_errand_deferral(
                entry_family, "entry:shadow", snapshot)
            if ((row is not None and not row["token_would_admit"])
                    or self._town_plan_defers(entry_family)):
                skipped.add(entry_family)
        stop = None
        if key is not None:
            stop = self._town_unrestored_stop(snapshot, holder, target_only=True)
            if stop is None:
                stop = (self._town_unrestored_stop(snapshot, holder)
                        or self._town_final_declaration_stop(snapshot, key, holder))
                if (stop is None and not reason.startswith((
                        "ownership:holder-", "ownership:declaration-"))
                        and not self._town_gate_exempt(family, reason, snapshot)):
                    foreign = self._claim_errand_hold(family, enforced=True,
                                                     arrival_board=snapshot)
                    if (foreign is not None and self._recorded_execution_token(
                            foreign, family, f"final:{reason}") is None):
                        entry_refused = any(
                            row.get("producer_key") == key
                            and row.get("holder_claim_id") == foreign.claim_id
                            and row.get("holder_family") == foreign.owner.value
                            and row.get("deferred_family") == family
                            and row.get("token_would_admit") is False
                            for row in getattr(self, "_decision_errand_deferred", ()) or ()
                        )
                        # A gated OFF output is not an ON gate escape. Keep
                        # genuine final-only outputs visible, and still verify
                        # that the holder has a valid registered continuation.
                        stop = (self._town_holder_structural_stop(foreign, snapshot)
                                if entry_refused else f"ownership:gate-missing:{family}")
        elif holder is not None and not self._home_tail_leave_ready(holder, snapshot):
            stop = self._town_holder_structural_stop(holder, snapshot)
            if (stop is None and declaration.state == 'acting' and (declaration.next_step not in {'route.resume', 'bounty.resume', 'equipment.next-action', 'stair.post'})):
                buffer = _decision_offers.get(self)
                no_steps = () if buffer is None else buffer.no_steps
                if not any(entry[0] == holder.owner.value
                           and entry[1] == declaration.work_id for entry in no_steps):
                    stop = f"ownership:holder-silent:{holder.owner.value}"
        if reason.startswith(("ownership:declaration-", "ownership:holder-silent:",
                              "ownership:gate-missing:")):
            stop = reason
        return {"would_stop": stop, "would_skip_families": sorted(skipped),
                "holder_family": holder.owner.value if holder is not None else None,
                "holder_claim_id": holder.claim_id if holder is not None else None,
                "declaration_state": declaration.state if declaration else None,
                "declaration_gap": holder is not None and declaration is None,
                "mismatch": None}

    def _town_unrestored_stop(self, snapshot, holder, *, target_only=False):
        """Pure restoration-debt check in the ON precedence order."""
        if target_only or (holder is not None and False):
            return None
        return None

    def _town_final_declaration_stop(self, snapshot, key, route):
        """Pure validity checks shared by enforcement and OFF shadow."""
        reserved = next((row["would_stop"] for row in reservation_shadow(self)
                         if row.get("would_stop")), None)
        if reserved is not None:
            return reserved
        reason = self.last_reason or ""
        family = self._claim_family_of(reason)
        if key == "" and reason == "shop:one-shot-in-flight":
            visit = self._store_visit
            declaration = getattr(route, "execution", None)
            identity = getattr(visit, "claim_operation_identity", None)
            if not (
                route is not None and declaration is not None
                and visit is not None and identity is not None
                and visit.operation_posted and not visit.operation_effect_observed
                and visit.posted_sequence is not None
                and identity == (visit.store_type, visit.opened_sequence,
                                 visit.operation_key)
                and route.owner.value == visit.operation_producer_family
                and route.goal.source == CLAIM_OBSERVE_STORE_OPERATION
                and route.goal.expectation == tuple(sorted(map(str, identity)))
                and declaration.claim_id == route.claim_id
                and declaration.producer == route.owner.value
                and declaration.state == "awaiting"
                and (
                    (declaration.operation_ref is None
                     and declaration.expected_effect == "store-page-open"
                     and declaration.continuation == "shop.one-shot.send"
                     and visit.composed_key
                     and self._town_holder_structural_stop(route, snapshot) is None)
                    or (declaration.operation_ref
                        and declaration.operation_ref in {
                            f"decision:{visit.posted_sequence}:{posted_key}"
                            for posted_key in (visit.operation_key, visit.composed_key)
                            if posted_key
                        })
                )
                and declaration.expected_effect
                and (snapshot.store is None
                     or snapshot.store.store_type == visit.store_type)
            ):
                return f"ownership:declaration-stale:{family}"
            return None
        if (route is not None and route.owner.value == family
                and key is not None
                and not reason.startswith("ownership:")
                and (declaration := getattr(route, "execution", None)) is not None
                and declaration.state == "acting"):
            buffer = _decision_offers.get(self)
            offers = () if buffer is None else buffer.steps
            own = tuple(offer for offer in offers
                        if offer[0] == key and offer[1] == family)
            delegated = any(
                record.lifecycle == "open"
                and record.parent_claim_id == route.claim_id
                and record.delegate_family == family
                and getattr(record, "execution", None) is not None
                and record.execution.work_id == declaration.work_id
                and record.work_identity[-1:] == (key,)
                for record in getattr(self, "_execution_delegations", ()) or ()
            )
            if own and not delegated and not any(
                offer[2] == declaration.work_id
                and offer[3] in {declaration.next_step,
                                 declaration.continuation}
                and offer[4] == declaration.arguments
                for offer in own
            ):
                session = self._equipment_transaction_session
                action = session.current_action if session is not None else None
                if (family == "equipment-txn" and session is not None
                        and session.executable and action is not None
                        and ((session.prepared_action == action
                              and self._equipment_transaction_prepared_key == key)
                             or (key == " " and action.kind == "withdraw"
                                 and session.required_context == "home"
                                 and snapshot.store is not None
                                 and snapshot.store.store_type == STORE_HOME
                                 and any(offer[5] == "home-page-changed" for offer in own)))
                        and declaration.continuation == "equipment.next-action"
                        and any(
                            offer[2] == f"equipment:{session.target_loadout_id}:{session.index}"
                            and offer[3] == "equipment.next-action"
                            and offer[4] == (action.kind, action.target_slot, action.item_identity)
                            for offer in own)):
                    # The same physical session moved from its leave/travel
                    # envelope to the next prepared action. This is an exact
                    # observed session transition, not foreign admission.
                    return None
                return f"ownership:declaration-stale:{family}"
        if reason == "store:entry-await-observation" and key == "":
            # Check the entry declaration first.  An entry can be armed before
            # its store operation exists; the final emit seam rejects an
            # unbound empty wait if procurement cannot replace it.
            declaration = getattr(route, "execution", None)
            visit = getattr(self, "_store_visit", None)
            if (route is not None and declaration is not None
                    and declaration.claim_id == route.claim_id
                    and declaration.state == "awaiting"
                    and declaration.operation_ref
                    and declaration.expected_effect == "store-page-open"
                    and visit is not None
                    and route.goal.source == CLAIM_OBSERVE_STORE_ENTRY
                    and str(visit.store_type) in route.goal.expectation
                    and visit.posted_sequence is not None
                    and declaration.operation_ref.startswith(
                        f"decision:{visit.posted_sequence}:")
                    and self._store_entry_posted_owner == visit.store_type):
                return None
            return "ownership:declaration-missing:" + (
                route.owner.value if route is not None else "store-router")
        return None

    def _enforce_town_claim_result(self, snapshot: Snapshot, key):
        """Detect a producer that escaped the town entry gate."""
        if not (snapshot.in_town or snapshot.store is not None):
            return key
        if (getattr(self, "_town_claim_bar_enforced", False)
                and any(row.get("would_stop") for row in reservation_shadow(self))):
            stop = self._town_final_declaration_stop(snapshot, key, None)
            if stop is not None:
                self.last_reason = stop
                return None
        if key is None:
            return key
        enforced = getattr(self, "_town_claim_bar_enforced", False)
        holder = self._claim_errand_hold("__none__") if enforced else None
        if enforced:
            stop = self._town_unrestored_stop(snapshot, holder, target_only=True)
            if stop is not None:
                self.last_reason = stop
                return None
        if enforced:
            stop = self._town_unrestored_stop(snapshot, holder)
            if stop is not None:
                self.last_reason = stop
                return None
        register = getattr(self, "_claim_register", None)
        if enforced and register is not None and register.suspended:
            self._claim_suspended_exit(snapshot, register)
        reason = self.last_reason or ""
        family = self._claim_family_of(reason)
        route = self._claim_errand_hold("__none__")
        if enforced:
            stop = self._town_final_declaration_stop(snapshot, key, route)
            if stop is not None:
                self.last_reason = stop
                return None
            if key == "" and reason == "shop:one-shot-in-flight":
                declaration = route.execution
                self._offer_execution_awaiting(
                    key, producer=declaration.producer,
                    work_id=declaration.work_id,
                    operation_ref=declaration.operation_ref,
                    expected_effect=declaration.expected_effect,
                    continuation=declaration.continuation,
                )
                return key
            if key == "" and reason == "store:entry-await-observation":
                return key
        if reason.startswith(("ownership:holder-", "ownership:declaration-")):
            return key
        if self._town_gate_exempt(family, reason, snapshot):
            return key
        holder = self._claim_errand_hold(family)
        if holder is None:
            return key
        if self._recorded_execution_token(
            holder, family, f"final:{reason}"
        ) is not None:
            return key
        self._decision_gate_final_count = (
            getattr(self, "_decision_gate_final_count", 0) + 1)
        if not enforced:
            return key
        self._defer_town_errand(family, f"final:{reason}")
        self.last_reason = f"ownership:gate-missing:{family}"
        return None

    # -- rev 9.2 (S): the survival return trigger ----------------------------

    def _note_return_start(self, trigger: str | None) -> None:
        """Record-only: a return starts here.

        Called just before ``_returning_to_town = True``.  Rev 9.3: the
        trigger is written only when no return is running yet; re-asserting
        the latch during a running return -- with or without a trigger of its
        own -- keeps the trigger that return began with.
        """
        if not getattr(self, "_returning_to_town", False):
            self._survival_return_trigger = trigger

    def _note_return_end(self) -> None:
        """Record-only: the return ended (``_returning_to_town = False``)."""
        self._survival_return_trigger = None

    def _release_rewritten_prompt_chain(self, key) -> None:
        """Drop a staged prompt chain whose command is not the emitted key.

        A producer stages its prompt-gated chain together with the key it
        returns (identification, launcher enchantment).  The public seam then
        lets detectors and safety rewrites replace that key -- live
        2026-09-25 12:56, sequence 7288: ``town:enchant-launcher-tohit``
        staged 'rlc' and the town progress invariant emitted its approach
        travel instead.  The chain belongs to the replaced command, which is
        never posted, so it cannot gate the replacement: left staged, the
        sender refused the replacement as ``key-replaced`` and the idle game
        produced no further board.  Only the emitted key's own chain may
        survive this seam.
        """
        chain = self._staged_prompt_chain
        if chain is not None and not staged_prompt_chain_matches(chain, key):
            producer = getattr(self, "_decision_non_discardable", None)
            if producer is not None:
                self._decision_displaced_producer = {
                    "family": producer, "key": chain.get("key"),
                }
            self._release_claim_goal(
                "staged-tail-dropped",
                owners=(self._claim_family_of(chain["owner"]),),
                kinds=(CLAIM_GOAL_OBSERVE,),
                sources=(CLAIM_OBSERVE_STORE_OPERATION,),
            )
            self._staged_prompt_chain = None

    def _release_rewritten_store_posting(
        self, decided_visit, decided_key, key,
    ) -> None:
        """Release a store posting whose key never reached the game.

        ``_choose_key`` binds the store visit to the key it returns: an
        in-store leave arms ``_store_leave_inflight`` and a composed one-shot
        marks ``operation_posted`` with the entry ``composed_key``.  The public
        seam then lets detectors and safety rewrites replace that key, and the
        replacement is what is posted.  The bound command therefore never
        reached Hengband, yet the visit keeps waiting for the board it would
        have produced: the entering wait emits no key and the leave
        confirmation repeats its no-op until a driver bound ends the run.  The
        posting did not happen, so end it here and let the ordinary machinery
        re-derive the visit from the next board.  A key that survives this seam
        unchanged keeps its legitimate wait (pinned by
        test_policy_shop.test_pin_fresh_home_catalogue_composes_one_shot_purchase
        and test_posted_effect_unobserved
        .test_p4_posted_one_shot_still_waits_at_its_own_entrance).
        """
        visit = self._store_visit
        if (
            visit is None
            or visit is not decided_visit
            or decided_key is None
            or key is None
            or str(key) == str(decided_key)
        ):
            return
        if (self.last_reason or "").startswith("town:blocked:"):
            # A town-block terminal is the bot's declared, visible stop and the
            # block machinery owns the visit through it (see the arbiter
            # retirement seam above, which closes the retired claim itself).
            # Only a silent rewrite strands a posting.
            return
        entry_bound = (
            visit.operation_posted
            and not visit.operation_released
            and visit.composed_key is not None
            and str(visit.composed_key) == str(decided_key)
        )
        leave_bound = (
            visit.phase == StoreVisitPhase.LEAVING
            and visit.posted_sequence == self._decision_sequence
            and str(decided_key) == LEAVE_STORE_KEY
        )
        if not (entry_bound or leave_bound):
            return
        self._store_entry_wait_owner = None
        self._store_entry_wait_turn = None
        self._town_visit_ledger.pending_store_transaction = None
        self._town_visit_ledger.pending_store_context_waits = 0
        self._close_store_visit("posting-rewritten")

    @staticmethod
    def _route_unavailable_terminal_candidate(rejected_candidate, key) -> bool:
        """Route only the exact rejected unresolved quest claim to its terminal."""
        return (
            isinstance(rejected_candidate, DecisionCandidate)
            and rejected_candidate.reason in {
                "fixedquest:q22-travel:route-unavailable",
                "fixedquest:prepare-return:route-unavailable",
                "quest:enter:approach:route-unavailable",
                "fixedquest:claim:approach:route-unavailable",
                "fixedquest:request:approach:route-unavailable",
                "fixedquest:reward-approach:route-unavailable",
            }
            and rejected_candidate is key
        )





    # Closed list: additions are policy changes and require a dedicated pin.
    TOWN_PROGRESS_ALLOW_SET = frozenset({
        "emergency-lethal-danger",
        "weak-fainting-survival-absorb",
        "recall-entry-invariant",
        "nearby-threat-defer",
        "reserve-already-satisfied",
    })
























    def _refresh_carried_equipment_catalog(self, snapshot: Snapshot) -> None:
        """Refresh carried gear and release Home-only deferrals after withdrawal."""
        self._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        carried_signatures = {
            self._item_signature(owned.item)
            for owned in self._equipment_catalog.items
            if owned.origin in {"pack", "equipped"}
        }
        home_signatures = {
            self._item_signature(owned.item)
            for owned in self._equipment_catalog.items
            if owned.origin == "home"
        }
        if self._equipment_catalog.home_scan_complete:
            self._deferred_home_items.difference_update(
                carried_signatures - home_signatures
            )

    def _choose_key_with_latch_capture(self, snapshot: Snapshot) -> str:
        capture_path = self._latch_capture_path
        if capture_path is None:
            return self._choose_key(snapshot)
        before = self._town_blocked_reason
        withdrawal_defect_before = bool(
            getattr(self, "_withdrawal_unfulfilled_defect", {})
        )
        try:
            predecision = latch_capture_checkpoint(self)
        except Exception:
            return self._choose_key(snapshot)
        key = self._choose_key(snapshot)
        try:
            assignment = self._latch_capture_assignment
            onset = (
                (
                    before is None
                    and self._town_blocked_reason is not None
                )
                or (
                    not withdrawal_defect_before
                    and bool(getattr(
                        self, "_withdrawal_unfulfilled_defect", {}
                    ))
                )
            ) and assignment is not None
            relative = 0 if onset else (
                CAPTURE_DECISIONS_AFTER_ONSET - self._latch_capture_remaining + 1
                if self._latch_capture_remaining > 0
                else -1
            )
            current = latch_capture_decision_record(
                self, snapshot, key, self.last_reason, before, predecision,
                assignment if onset else None, relative,
            )
            if onset:
                records = []
                if self._latch_capture_previous is not None:
                    previous = dict(self._latch_capture_previous)
                    previous["relative_decision"] = -1
                    records.append(previous)
                records.append(current)
                write_latch_capture_window(
                    capture_path,
                    records,
                    replace=True,
                    rotate_bytes=self._latch_capture_rotate_bytes,
                    generations=self._latch_capture_generations,
                )
                self._latch_capture_remaining = CAPTURE_DECISIONS_AFTER_ONSET
                self._latch_capture_assignment = None
            elif self._latch_capture_remaining > 0:
                write_latch_capture_window(
                    capture_path,
                    [current],
                    replace=False,
                    rotate_bytes=self._latch_capture_rotate_bytes,
                    generations=self._latch_capture_generations,
                )
                self._latch_capture_remaining -= 1
            self._latch_capture_previous = current
        except Exception:
            # Serialization and file-system failures are diagnostic failures;
            # the already-selected gameplay decision remains authoritative.
            pass
        return key

    @claims(ClaimOwner.HOME_VISIT)
    def _observe_home_atomic_withdrawal_outside(self, snapshot: Snapshot) -> None:
        """Reconcile one posted single-item Home take on its outside board."""
        pending_withdrawal = self._home_atomic_withdraw_pending
        if (
            pending_withdrawal is not None
            and snapshot.store is None
            and (
                self._store_visit is None
                or not self._store_visit.operation_posted
                or self._store_visit.operation_released
            )
            and (
                self._home_atomic_withdraw_posted_turn is None
                or snapshot.turn > self._home_atomic_withdraw_posted_turn
            )
        ):
            signature, before_count, withdrawn, quantity = pending_withdrawal
            procurement_class = self._home_atomic_withdraw_procurement_class
            move_identity = getattr(
                self, "_home_atomic_withdraw_move_identity", None
            )
            after_count = (
                self._inventory_move_identity_count(snapshot, move_identity)
                if move_identity is not None
                else self._inventory_signature_count(snapshot, signature)
            )
            if getattr(self, "_home_visit", None) is not None:
                self._home_visit.observe_outside(
                    effect_observed=after_count >= before_count + quantity
                )
            if (
                self._home_errand.request is not None
                and self._home_errand.request.signature == signature
            ):
                self._home_errand.observe_outside(after_count)
            if after_count < before_count + quantity:
                self._release_claim_goal(
                    "target-unobserved", owners=("home-visit", "home-errand"),
                    kinds=(CLAIM_GOAL_OBSERVE,),
                    sources=(CLAIM_OBSERVE_STORE_OPERATION,),
                )
            self._home_atomic_withdraw_pending = None
            self._home_atomic_withdraw_procurement_class = None
            self._home_atomic_withdraw_move_identity = None
            self._home_atomic_withdraw_posted_turn = None
            self._home_entry_operation_posted = False
            if after_count >= before_count + quantity:
                # Design rev 9 item 3: the posted Home withdrawal's effect is
                # confirmed.  Before ``_release_invalid_store_visit``, which
                # can close the visit before the exit sees it.
                self._complete_observed_effect(
                    "home-withdraw-observed",
                    owners=CLAIM_HOME_EFFECT_OWNERS,
                    sources=CLAIM_HOME_EFFECT_SOURCES,
                )
                self._observe_home_operation_effect()
                if (
                    self._store_visit is not None
                    and self._store_visit.store_type == STORE_HOME
                ):
                    self._store_visit.operation_effect_observed = True
                    self._release_invalid_store_visit(snapshot)
                failure = self._home_procurement_withdraw_failure
                if (
                    failure is not None
                    and failure.get("item_class")
                    == self._procurement_equivalence(
                        self._procurement_class(withdrawn)
                    )
                ):
                    self._home_procurement_withdraw_failure = None
                tracked = getattr(self, "_withdrawal_unsatisfied_for", None)
                if tracked is not None and tracked[0] == signature:
                    self._withdrawal_unsatisfied_for = None
                self._confirm_home_withdrawal_address(
                    signature, self._home_atomic_withdraw_index
                )
                if signature == self._home_pending_item:
                    self._home_pending_take_confirmed = signature
                if signature in self._home_pending_batch:
                    self._home_pending_batch.remove(signature)
                self._home_pending_quantities.pop(signature, None)
                if withdrawn.is_digging_tool:
                    # The queued operation, rather than the standing two-tool
                    # optimization target, is the departure premise.  Its
                    # observed inventory gain is confirmed completion.
                    self._home_digger_withdraw_pending = False
                suppression_withdrawal = (
                    self._home_random_teleport_withdrawal == signature
                )
                self._equipment_catalog.record_home_withdrawal(
                    withdrawn,
                    intent=(snapshot.turn, signature, before_count, quantity),
                )
                self._refresh_carried_equipment_catalog(snapshot)
                if suppression_withdrawal and self._home_pending_item == signature:
                    self._home_pending_item = None
                    self._home_pending_slot = None
                    self._home_random_teleport_withdrawal = None
                if suppression_withdrawal:
                    # This atomic visit has no intervening store snapshot on
                    # which the ordinary leave handler can close the owning
                    # stop.  Report only this suppression withdrawal; other
                    # atomic Home operations retain their existing owners.
                    self._report_town_stop_pass(
                        snapshot,
                        STORE_HOME,
                        goal_satisfied=not self._home_owner_goal_pending(snapshot),
                        operation_completed=True,
                    )
                if (
                    withdrawn.tval == TVAL_SCROLL
                    and withdrawn.sval
                    in {SV_SCROLL_IDENTIFY, SV_SCROLL_STAR_IDENTIFY}
                    and (
                        self._home_pending_item == signature
                        or (
                            self._home_errand.request is not None
                            and self._home_errand.request.signature == signature
                            and self._home_errand.request.purpose == "identification"
                        )
                    )
                    and self._identification_need is not None
                ):
                    # This was the source transaction, not the downstream gear
                    # transaction. Release its address and re-arm the original
                    # candidate now that the source is physically carried.
                    self._home_pending_item = None
                    self._home_pending_slot = None
                    self._home_candidate_waiting = True
                if (
                    withdrawn.tval == TVAL_STAFF
                    and withdrawn.sval == SV_STAFF_IDENTIFY
                ):
                    if self._home_pending_item == signature:
                        self._home_pending_item = None
                        self._home_pending_slot = None
                    self._home_pending_quantities.pop(signature, None)
                    self._report_town_stop_pass(
                        snapshot,
                        STORE_HOME,
                        goal_satisfied=self._identify_staff_ready(snapshot),
                        operation_completed=True,
                    )
            else:
                if self._home_random_teleport_withdrawal == signature:
                    self._home_random_teleport_withdrawal = None
                retry_digger = (
                    withdrawn.is_digging_tool
                    and self._digger_home_withdraw_failures < 1
                )
                if retry_digger:
                    # The command failed against a page-relative address.  Do
                    # not let the generic observed/uncomposable rule consume
                    # the Home stop: retain the exact queued operation, discard
                    # the stale address space, and make the next attempt earn a
                    # fresh ~9 observation.  This is state based; the existing
                    # visible two-failure fallback is the bound.
                    self._home_pending_item = signature
                    self._home_digger_withdraw_pending = True
                    self._invalidate_home_observation()
                    self._rearm_town_store_for_new_work(
                        STORE_HOME, release_visit_bound=True
                    )
                else:
                    self._defer_home_item(signature, "atomic-withdraw-observed-failure")
                    if signature in self._home_pending_batch:
                        self._home_pending_batch.remove(signature)
                    self._home_pending_quantities.pop(signature, None)
                    if self._home_pending_item == signature:
                        self._home_pending_item = None
                        self._home_pending_slot = None
                    if withdrawn.is_digging_tool:
                        # This is the bounded visible abandonment.  The
                        # standing fallback purchase now owns procurement.
                        self._home_digger_withdraw_pending = False
                self.last_reason = (
                    self._home_errand.reason("withdraw-failed")
                    if (
                        self._home_errand.request is not None
                        and self._home_errand.request.signature == signature
                    )
                    else "home:atomic-withdraw-failed"
                )
                if withdrawn.is_digging_tool:
                    self._digger_home_withdraw_failures += 1
                terminal_failure = not retry_digger
                if (
                    terminal_failure
                    and procurement_class is not None
                ):
                    self._home_procurement_withdraw_failure = {
                        "item_class": self._procurement_equivalence(
                            procurement_class
                        ),
                        "identity": signature,
                        "reason": self.last_reason,
                        "attempts": (
                            self._digger_home_withdraw_failures
                            if withdrawn.is_digging_tool else 1
                        ),
                        "turn": snapshot.turn,
                    }
                    # The failed command leaves the old catalogue unable to
                    # distinguish a rejected take from concurrently vanished
                    # stock.  Require the next gate decision to use a fresh
                    # complete Home census before applying the failure rule.
                    self._invalidate_home_observation()
                    self._rearm_town_store_for_new_work(
                        STORE_HOME, release_visit_bound=True
                    )
            self._home_atomic_withdraw_index = None

    @claims(ClaimOwner.HOME_VISIT)
    def _observe_home_atomic_deposit_outside(self, snapshot: Snapshot) -> None:
        """Consume the legacy deposit delta before any producer can take over."""
        if self._home_atomic_deposit_pending is not None and any(
                "我が家にはもう置く場所がない" in message
                or "Your home is full" in message for message in snapshot.messages):
            self._home_full_refused = True
        pending_deposit = self._home_atomic_deposit_pending
        if (
            snapshot.store is None
            and pending_deposit is not None
            and (
                self._store_visit is None
                or not self._store_visit.operation_posted
                or self._store_visit.operation_released
            )
        ):
            entries, _unused, posted_turn, unchanged_pages = pending_deposit
            if snapshot.turn > posted_turn:
                landed = tuple(
                    signature
                    for signature, count_before, expected_count in entries
                    if self._inventory_signature_count(snapshot, signature)
                    <= count_before - expected_count
                )
                deposit_observed = len(landed) == len(entries)
                if deposit_observed:
                    self._home_full_refused = False
                    if self._home_full_retry_deposits is not None:
                        self._home_full_retry_deposits = tuple(
                            entry for entry in self._home_full_retry_deposits
                            if entry[0] not in landed) or None
                    # Design rev 9 item 3: the posted Home deposit's effect is
                    # confirmed, before ``_release_invalid_store_visit``.
                    self._complete_observed_effect(
                        "home-deposit-observed",
                        owners=CLAIM_HOME_EFFECT_OWNERS,
                        sources=CLAIM_HOME_EFFECT_SOURCES,
                    )
                    self._observe_home_operation_effect()
                    if (
                        self._store_visit is not None
                        and self._store_visit.store_type == STORE_HOME
                    ):
                        self._store_visit.operation_effect_observed = True
                        self._release_invalid_store_visit(snapshot)
                    if getattr(self, "_home_visit", None) is not None:
                        self._home_visit.observe_outside(effect_observed=True)
                    self._home_entry_operation_posted = False
                    self._home_atomic_deposit_pending = None
                    self._invalidate_home_observation()
                elif unchanged_pages + 1 >= STORE_STUCK_LIMIT:
                    # A11r2 discipline: never recompose against the page that
                    # failed to show the mutation.  Terminate this visit
                    # visibly and reject that identity for this visit.  It may
                    # become eligible only in a later visit epoch, whose normal
                    # Home scan supplies a new address space.
                    if getattr(self, "_home_visit", None) is not None:
                        self._home_visit.observe_outside(effect_observed=False)
                        report = self._home_visit.consume_report()
                        if report is not None:
                            marker = report.defect or report.outcome
                            self._pending_home_visit_report = (
                                f"home-visit:{report.request.requester}:{marker}"
                            )
                    self._home_entry_operation_posted = False
                    self._release_claim_goal(
                        "target-unobserved", owners=("home-visit", "home-errand"),
                        kinds=(CLAIM_GOAL_OBSERVE,),
                        sources=(CLAIM_OBSERVE_STORE_OPERATION,),
                    )
                    self._home_atomic_deposit_pending = None
                    blocked_entries = tuple(entry for entry in entries
                                            if entry[0] not in landed)
                    self._home_full_retry_deposits = None
                    if self._home_full_refused:
                        self._begin_home_full_relief(snapshot, blocked_entries, refused=True)
                    elif self._home_is_full(snapshot):
                        self._begin_home_full_relief(snapshot, blocked_entries)
                    self._home_rejected_deposits.update(
                        signature
                        for signature, _count_before, _expected_count in entries
                        if signature not in landed
                    )
                    if (self._store_visit is not None
                            and self._store_visit.store_type == STORE_HOME):
                        self._close_store_visit("home-deposit-unobserved")
                    self.last_reason = "home:deposit-unobserved-rescan"
                else:
                    self._home_atomic_deposit_pending = (
                        entries, None, posted_turn, unchanged_pages + 1
                    )

    def _choose_key(self, snapshot: Snapshot) -> str | None:
        _decision_offers.pop(self, None)
        self._execution_pending_post = None
        self._staged_shop_approach = None
        self._read_binding = None
        self.read_telemetry = {}
        self._store_entry_wait_owner = None
        self._store_entry_wait_key = None
        self._store_entry_wait_turn = None
        self._intentional_entrance_activation = False
        self._store_entry_failed_owner = None
        self._decision_sequence += 1
        self._equipment_departure_cache_token = None
        # The executor's POSTED state is the in-flight gate every reader of
        # ``state`` (weight shedding, the space deposit, Home knowledge scans,
        # destroys) consults.  Observe the posted wield/takeoff on each board,
        # not only when the next mutation is requested: a transaction's last
        # wield otherwise stays POSTED after its worn change was observed, and
        # those owners stay silenced for the rest of the town visit.  Each
        # fruitless board counts toward the executor's bounded release, once
        # per board (the driver re-decides the same board after a refused
        # post).  A command prepared on an earlier decision and never posted
        # is discarded first, in the executor and in the equipment
        # transaction that bound the same key (a key rewritten after
        # ``_choose_key`` returned it leaves both halves prepared).
        discarded = self._equipment_mutation.discard_unposted()
        if getattr(self, "_equipment_transaction_prepared_key", None) is not None:
            self._discard_unposted_equipment_transaction_command()
        released = self._equipment_mutation.observe(
            snapshot,
            count_fruitless=(
                snapshot
                is not getattr(self, "_equipment_mutation_counted_board", None)
            ),
        )
        self._equipment_mutation_counted_board = snapshot
        if (released or discarded) is not None:
            self._pending_mutation_report = released or discarded
        self._escape_state.begin_decision(snapshot, self._decision_sequence)
        self._observe_town_equipment_work(snapshot)
        if snapshot.store is not None and snapshot.player.recalling:
            # A lagged or externally observed store page cannot revive shopping
            # after departure is armed.  Leave under the departure owner so the
            # store handler cannot recover a fresh visit and later re-approach it.
            self._close_store_visit("recall-in-flight")
            self.last_reason = "town:wait-recall-leave"
            self._offer_execution(
                LEAVE_STORE_KEY, producer="departure",
                work_id="town:recall-leave-store",
                next_step="store.leave-for-recall",
                expected_effect="store-exited",
                continuation="recall.observe-arrival",
            )
            return LEAVE_STORE_KEY
        if (snapshot.store is None and snapshot.in_town
                and (catalogue_holder := self._home_catalogue_work_holder()) is not None
                and catalogue_holder.execution.continuation == "home.catalogue.acquire"):
            # The posted partial-page exit owns its outside continuation, even
            # with S3.3 OFF. Dispatch it before entrance acquisition can replace
            # the same work with another approach. A returned catalogue closes
            # this work before any subsequent Home operation is considered.
            self._store_leave_inflight = None
            if self._home_knowledge_current and not self._home_knowledge_invalidated:
                self._claim_exit_completion(snapshot, catalogue_holder, [])
            else:
                return self._home_catalogue_work_key(snapshot)
        if (snapshot.in_town and self._home_knowledge_scan_inflight
                and not self._home_knowledge_current
                and (self._home_full_relief is not None
                     or self._home_full_retry_deposits is not None)):
            # A posted surplus-sale census keeps its observed scan owner even
            # when the unchanged board still shows the selling store.
            scan_key = self._town_producer_entry(
                "home-full-knowledge", lambda: self._home_full_knowledge_key(snapshot),
                family="home-scan")
            if scan_key is not None:
                return scan_key
        if (
            snapshot.store is not None and snapshot.store.store_type == STORE_HOME and (not self._equipment_catalog.home_scan_complete or self._home_knowledge_invalidated) and (self._home_errand.needs_knowledge or 'home-scan-incomplete' in getattr(self._equipment_optimization_preparation, 'blockers', ()) or (self._home_procurement_probe is not None or (self._home_visit.request is not None and self._home_visit.request.kind == HomeVisitKind.SCAN))) and (not self._home_knowledge_scan_requested) and (self._home_knowledge_scan_epoch is None) and (self._equipment_transaction_session is None) and (not self._town_space_deposit_actionable(snapshot)) and (not (getattr(self, '_town_claim_bar_enforced', False) and self._store_leave_inflight is not None)) and (not (getattr(self, '_town_claim_bar_enforced', False) and (self._home_atomic_deposit_pending is not None or self._home_atomic_withdraw_pending is not None))) and (not self._defer_town_errand('home-errand' if self._home_errand.needs_knowledge else 'home-scan', 'choose-key-scan'))
        ):
            self.last_reason = (
                self._home_errand.reason("request-knowledge")
                if self._home_errand.needs_knowledge
                else "home:request-knowledge-scan"
            )
            self._offer_home_knowledge_request(
                producer="home-errand" if self._home_errand.needs_knowledge
                else "home-scan")
            return HOME_KNOWLEDGE_MACRO
        if (
            snapshot.store is None
            and snapshot.in_town
            and snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and self._active_quest_id(snapshot) is None
            and "quest-request" not in self._town_turn_arbiter._retired
            and len(snapshot.inventory) >= PACK_CAPACITY - HOME_BATCH_RESERVED_SLOTS - 1
            and not self._town_space_deposit_actionable(snapshot)
            and self._home_atomic_withdraw_pending is None
            and self._home_atomic_deposit_pending is None
            and not self._home_entry_operation_posted
            and (not self._equipment_catalog.home_scan_complete
                 or self._home_knowledge_invalidated)
            and not self._defer_town_errand("equipment-txn", "acquire-home-catalog")
        ):
            here = snapshot.grid_at(snapshot.player.position)
            if (
                (here is not None and here.store_number == STORE_HOME)
                or (here is None and self._current_town_has_home(snapshot))
            ):
                self._ensure_home_visit_request(snapshot)
                self._request_store_trip(STORE_HOME, 'equipment-txn')
                self.last_reason = "equipment-transaction:acquire-home-catalog"
                key = self._shopping_approach_key(
                    snapshot, snapshot.player.position,
                    "equipment-transaction:travel-home",
                )
                if key is not None:
                    self._offer_execution(
                        key, producer="equipment-txn",
                        work_id="equipment:acquire-home-catalog",
                        next_step="home.approach-for-equipment-catalog",
                        expected_effect="home-catalog-available",
                    )
                else:
                    self._offer_execution_no_step(
                        producer="equipment-txn",
                        work_id="equipment:acquire-home-catalog",
                        cause="home-approach-unavailable",
                    )
                return key
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._home_knowledge_current
            and getattr(snapshot.store, "stock_num", None) is not None
            and snapshot.store.stock_num != self._home_scan_item_count
        ):
            # The in-store count and ~9 are independent observations.  Whichever
            # arrives second invalidates a contradictory address catalogue.
            self._invalidate_home_observation()
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and getattr(snapshot.store, "page_size", None) is not None
            and snapshot.store.page_size > 0
        ):
            self._home_page_size = snapshot.store.page_size
            self._record_observed_home_addresses(snapshot)
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and not snapshot.store.items
            and (snapshot.store.stock_num == 0
                 or (snapshot.store.stock_num is None
                     and snapshot.store.page_top is None
                     and snapshot.store.page_size is None))
        ):
            # Zero stock (or the legacy unpaged envelope) proves empty Home.
            # An empty page of known nonzero stock cannot prove absence.
            self._adopt_home_catalogue(())
            self._home_scan_item_count = 0
            self._home_scan_source = "observed-home-page"
            self._prepare_equipment_optimization(snapshot)
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and getattr(self, "_home_visit", None) is not None
            and self._home_visit.entry_pending
        ):
            self._home_visit.observe_inside(
                (
                    snapshot.store.page_top,
                    snapshot.store.page_size,
                    tuple(
                        self._item_signature(item)
                        for item in snapshot.store.items
                    ),
                ),
                self._decision_sequence,
            )
        decision_floor = getattr(snapshot, "floor_key", None)
        if self._unviable_quest_floor != decision_floor:
            self._unviable_quest_floor = None
        if self._escape_sustain_floor != decision_floor:
            self._escape_sustain_floor = decision_floor
            self._escape_sustain_active = False
            self._escape_sustain_non_escape_decisions = 0
            self._escape_speed_baseline = None
            self._escape_speed_attempted = False
        latest_snapshot = snapshot
        self._decision_input_snapshot = latest_snapshot
        self._emitted_t = {
            (position.y, position.x)
            for position in getattr(snapshot, "grids", {})
        }
        snapshot = self._with_grid_memory(snapshot)
        self._begin_map_predicate_cache(snapshot)
        # Posted entry observation is handled before ``_decide``, so its empty
        # wait would otherwise bypass the registered release evaluators.  Run
        # them only at that early-return seam: a blanket public-boundary call
        # would reorder every decision path, while the ordinary one-shot wait
        # still reaches the same evaluators at the start of ``_decide``.
        if self._store_entry_posted_owner is not None:
            self._evaluate_cross_decision_latches(snapshot)
        posted_entry_owner = self._store_entry_posted_owner
        if posted_entry_owner is not None:
            if (
                snapshot.store is not None
                and snapshot.store.store_type == posted_entry_owner
                and self._store_visit is not None
            ):
                self._store_visit.transition(StoreVisitPhase.OPERATING)
                self._store_visit.posted_sequence = None
                posted_entry_owner = None
            elif snapshot.store is not None:
                # The store page is positive game-state evidence. A posted
                # entry for a different store cannot remain authoritative or
                # be retried as a surface direction while this page is open.
                # Release the mismatched visit at its source; the ordinary
                # in-store handler below now owns the observed store.
                self._store_entry_posted_owner = None
                self._close_store_visit("different-store-observed")
                posted_entry_owner = None
        if posted_entry_owner is not None:
            observed_failed_entry = snapshot.store is None and any(
                "The doors are locked." in message
                or "ドアに鍵がかかっている" in message
                for message in snapshot.messages
            )
            here = snapshot.grid_at(snapshot.player.position)
            # The executor's binding is (sequence, owner), but the owner is the
            # decision's final reason label, which detectors may relabel (e.g.
            # the town progress invariant emitting this same native travel as
            # "...=>town-progress-invariant:approach").  posted_sequence is set
            # only when the posted key equalled the armed native-travel wait
            # key, so the sequence alone identifies the travel operation; an
            # owner-label allowlist left relabelled travels waiting forever.
            interrupted_travel_entry = bool(
                snapshot.store is None
                and self._store_visit is not None
                and (self._store_entry_wait_key or "").startswith("\x1b`")
                and snapshot.completed_operation_sequence is not None
                and snapshot.completed_operation_sequence
                    == self._store_visit.posted_sequence
                and here is not None
                and here.store_number != posted_entry_owner
            )
            travel_continue_prompt = snapshot.store is None and any(
                "トラベルを継続しますか" in message
                or "continue previous travel" in message.lower()
                for message in snapshot.messages
            )
            # Failure requires positive message evidence; a lagged store=None
            # is not evidence.  Termination is nevertheless total: both
            # branches discharge the one-shot owner in this decision.  The
            # refusal branch lets routing step off below; the in-flight branch
            # returns an empty, unsent decision now and normal routing owns the
            # next snapshot.  Neither branch retains a wait or emits a filler.
            if observed_failed_entry:
                self._store_entry_posted_owner = None
                self._store_entry_failed_owner = posted_entry_owner
            elif interrupted_travel_entry or travel_continue_prompt:
                # The executor bound this board to the same accepted native
                # travel operation. Reaching its post-key COMMAND barrier
                # proves travel ended. A non-entrance cell therefore proves
                # entry was not achieved. Release only the entry post and let the
                # existing approach owner re-plan in this same decision.
                self._store_entry_posted_owner = None
                if self._store_visit is not None:
                    self._store_visit.transition(StoreVisitPhase.APPROACHING)
                if interrupted_travel_entry:
                    self._release_town_travel_claim(
                        "town-travel:interrupted-entry"
                    )
                    self._town_travel_state = None
                # Short native travel ended outside Home. Keep the phase's
                # producer responsible for composing and declaring its retry.
                step = self._shopping_approach_step(
                    snapshot, posted_entry_owner, router_plan_stop=True
                )
                if step is not None:
                    self.last_reason = "store:entry-interrupted-replan"
                    return self._shopping_approach_key(
                        snapshot, step, self.last_reason
                    )
            else:
                visit = self._store_visit
                entry_observation_pending = bool(
                    visit is not None
                    and visit.posted_sequence is not None
                    and self._decision_sequence == visit.posted_sequence + 1
                )
                if (
                    visit is not None
                    and visit.store_type == STORE_HOME
                    and visit.operation_posted
                ):
                    # The staged command and entrance are one owner. A lagged
                    # surface snapshot cannot discharge only the entry half:
                    # that strands operation_posted in APPROACHING, where no
                    # producer can consume or release it. Keep the posted
                    # sequence for the matching page or the existing whole-
                    # visit posted-entry-unobserved release.
                    withdrawal = self._home_atomic_withdraw_pending
                    deposit = self._home_atomic_deposit_pending
                    deposit_observed = bool(
                        deposit is not None
                        and all(
                            self._inventory_signature_count(snapshot, signature)
                            <= count_before - expected_count
                            for signature, count_before, expected_count
                            in deposit[0]
                        )
                    )
                    observed_effect = bool(
                        withdrawal is not None
                        and (
                            self._inventory_move_identity_count(
                                snapshot,
                                getattr(
                                    self, "_home_atomic_withdraw_move_identity", None
                                ),
                            ) >= withdrawal[1] + withdrawal[3]
                            if getattr(
                                self, "_home_atomic_withdraw_move_identity", None
                            ) is not None
                            else self._inventory_signature_count(
                                snapshot, withdrawal[0]
                            ) >= withdrawal[1] + withdrawal[3]
                        )
                    ) or deposit_observed
                    if not observed_effect:
                        self.last_reason = "store:entry-await-observation"
                        return ""
                    # A completed composed command is stronger evidence than
                    # the absent intermediate store page. Let the established
                    # outside observers consume and close it below.
                    visit.operation_released = True
                if not entry_observation_pending and not (
                    visit is not None
                    and visit.operation_posted
                    and not visit.operation_released
                ):
                    # Only the first decision after a confirmed post can be
                    # the lagged surface paired with that entry. Later surface
                    # snapshots are routing observations, so release the
                    # posted owner instead of absorbing the captured window.
                    self._store_entry_posted_owner = None
                    if self._store_visit is not None:
                        self._store_visit.transition(StoreVisitPhase.APPROACHING)
                state = self._town_travel_state
                short_travel = bool(
                    state is not None
                    and visit is not None
                    and not visit.operation_posted
                    and not entry_observation_pending
                    and (self._store_entry_wait_key or "").startswith("\x1b`")
                    and snapshot.turn > state.last_turn
                    and snapshot.player.position != state.goal
                    and snapshot.player.position.distance_to(state.goal)
                    < state.best_distance
                )
                if short_travel:
                    # The prior decision already consumed the lagged surface
                    # board paired with the native-travel post.  A subsequent
                    # later-turn board still short of the entrance proves the
                    # travel completed without entering; release the barrier
                    # and let the existing approach owner route immediately.
                    self._store_entry_posted_owner = None
                    if self._store_visit is not None:
                        self._store_visit.transition(StoreVisitPhase.APPROACHING)
                    self.last_reason = "store:entry-interrupted-replan"
                    travel = self._town_travel_key(
                        snapshot,
                        state.goal,
                        self._store_entry_wait_key,
                        self.last_reason,
                    )
                    if travel is not None:
                        self._store_entry_wait_owner = posted_entry_owner
                        self._store_entry_wait_key = travel
                        self._store_entry_wait_turn = snapshot.turn
                        return travel
                if (
                    state is not None
                    and (self._store_entry_wait_key or "").startswith("\x1b`")
                    and self.last_reason == "store:entry-interrupted-replan"
                    and state.last_turn == snapshot.turn
                    and snapshot.player.position.distance_to(state.goal)
                    >= state.best_distance
                ):
                    # The first interrupted-travel observation already proved
                    # that the original native route ended away from the
                    # entrance. If its immediate replan returns the same board,
                    # abandon native travel and route by the walking fallback.
                    # A duplicate board after the original post alone is only
                    # a lagged entry observation and must retain the barrier.
                    self._town_travel_fallback = state.goal
                    self._release_town_travel_claim(
                        "town-travel:interrupted-replan-repeated"
                    )
                    self._town_travel_state = None
                    if (
                        entry_observation_pending
                        and snapshot.player.position != state.goal
                    ):
                        # The native route has stopped away from its entrance,
                        # so there is no longer an entry observation to await.
                        # Release the post and immediately let the established
                        # approach owner route using the walking fallback.
                        self._store_entry_posted_owner = None
                        if self._store_visit is not None:
                            self._store_visit.transition(
                                StoreVisitPhase.APPROACHING
                            )
                        step = self._shopping_approach_step(
                            snapshot, posted_entry_owner, router_plan_stop=True
                        )
                        if step is not None:
                            self.last_reason = (
                                "store:entry-interrupted-replan"
                            )
                            return self._shopping_approach_key(
                                snapshot, step, self.last_reason
                            )
                if entry_observation_pending:
                    self.last_reason = (
                        "shop:one-shot-in-flight"
                        if visit is not None and visit.operation_posted
                        and visit.operation_producer_family in {"shop-buy", "shop-sell"}
                        else "store:entry-await-observation"
                    )
                    return ""
        pending_store_transaction = (
            self._town_visit_ledger.pending_store_transaction
        )
        if (
            snapshot.store is not None
            and pending_store_transaction is not None
            and snapshot.store.store_type == pending_store_transaction[0]
            and self._decision_sequence > pending_store_transaction[1]
            and not (
                snapshot.store.store_type == STORE_HOME
                and self._home_entry_operation_posted
            )
            and not (
                self._store_buy_inflight is not None
                and self._store_buy_inflight[0] == snapshot.store.store_type
            )
        ):
            # Any subsequent page from the same store is the observation the
            # transaction was waiting for.  The individual buy/sell/Home
            # handlers still decide whether it made progress; this correlation
            # only prevents an interleaved surface page from authorizing a
            # step-off/re-entry by itself.
            self._town_visit_ledger.pending_store_transaction = None
            self._town_visit_ledger.pending_store_context_waits = 0
        self._observe_home_history(snapshot)
        self._observe_star_remove_curse_reserve_inflight(snapshot)
        self._observe_home_atomic_withdrawal_outside(snapshot)
        # Shop one-shots complete (or become retryable) only from the following
        # outside inventory/gold observation.  No in-store confirmation phase
        # owns a key.  An in-store operation's own post-operation store board
        # is state-bound by the executor and confirms it in place
        # (SOL-DESIGN-store-reentry-20261003 3.1 "effect confirmation").
        in_store_board = self._in_store_post_op_board(snapshot)
        if (
            (snapshot.store is None or in_store_board)
            and self._store_buy_inflight is not None
            and (
                self._store_visit is None
                or not self._store_visit.operation_posted
                or self._store_visit.operation_released
            )
        ):
            (
                watched_store,
                watched_signature,
                before_count,
                before_gold,
                wait_count,
                action_generation,
            ) = self._store_buy_inflight
            confirmed = (
                self._inventory_signature_count(snapshot, watched_signature)
                > before_count
                or snapshot.player.gold < before_gold
            )
            if confirmed:
                # Design rev 9 item 3: the posted purchase is confirmed.
                self._complete_observed_effect(
                    "purchase-observed",
                    owners=(ClaimOwner.SHOP_BUY,),
                    sources=(CLAIM_OBSERVE_STORE_OPERATION,),
                )
                self._town_visit_purchases.add(watched_signature)
                bought = max(
                    0,
                    self._inventory_signature_count(snapshot, watched_signature)
                    - before_count,
                )
                self._town_visit_purchase_quantities[watched_signature] = (
                    self._town_visit_purchase_quantities.get(watched_signature, 0)
                    + bought
                )
                # A successful purchase is fresh evidence for this supplier.
                # In particular, the repetition repair may have inherited an
                # attempted-store latch and restock wait from the cycle it is
                # breaking; neither may survive observed purchase progress.
                self._town_store_attempted.pop(watched_store, None)
                self._town_restock_wait_until = None
                if self._store_visit is not None:
                    self._store_visit.operation_posted = False
                    self._store_visit.operation_effect_observed = True
                self._store_buy_inflight = None
                self._in_store_best_effort("_note_shelf_trade",
                    snapshot, watched_store, "buy", watched_signature, bought,
                    gold_spent=before_gold - snapshot.player.gold,
                )
                if in_store_board:
                    self._in_store_effect_confirmed(snapshot)
            elif in_store_board:
                # No effect on the state-bound page: no in-store retry and no
                # outside wait is charged here; the entry ends.
                pass
            elif wait_count + 1 >= STORE_STUCK_LIMIT:
                self._store_buy_inflight = None
                self._close_store_visit("one-shot-buy-unconfirmed")
            else:
                self._store_buy_inflight = (
                    watched_store,
                    watched_signature,
                    before_count,
                    before_gold,
                    wait_count + 1,
                    action_generation,
                )
        if (
            (snapshot.store is None or in_store_board)
            and self._batch_sell_pending is not None
            and self._batch_sell_pending.get("phase") == "await-sale"
            and (
                self._store_visit is None
                or not self._store_visit.operation_posted
                or self._store_visit.operation_released
            )
        ):
            # Match the buy lifecycle: lagged surface and intermediate store
            # pages remain owned by the posted one-shot.  Only its own pack or
            # gold effect, visit closure, or the shared wait budget can release
            # it.  In particular, a merely outside page is not a negative sale
            # observation and must not advance the ordinary attempt record.
            pending = self._batch_sell_pending
            entries = pending["entries"]
            confirmed = snapshot.player.gold > pending["before_gold"]
            for entry in entries:
                survivor = next((
                    current for current in snapshot.inventory
                    if self._sale_item_identity(current) == entry["signature"]
                    and self._item_has_sale_tag(current, str(entry["tag"]))
                ), None)
                expected = entry["count"] - entry["quantity"]
                if survivor is None or survivor.count <= expected:
                    confirmed = True
            wait_count = int(pending.get("wait_count", 0))
            if confirmed or (not in_store_board and wait_count + 1 >= STORE_STUCK_LIMIT):
                pending_store = int(pending["store_type"])
                self._batch_sell_key(
                    replace(snapshot, store=StoreState(pending_store, []))
                )
                if confirmed:
                    for entry in entries:
                        self._in_store_best_effort("_note_shelf_trade",
                            snapshot, pending_store, "sell",
                            entry["signature"], int(entry.get("quantity", 0)),
                        )
                    if in_store_board:
                        self._in_store_effect_confirmed(snapshot)
            elif not in_store_board:
                pending["wait_count"] = wait_count + 1
        self._in_store_best_effort("_in_store_shadow_visit_outcome", snapshot)
        self._refresh_carried_equipment_catalog(snapshot)
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            fresh_home_entry = not self._last_snapshot_was_store
            if fresh_home_entry:
                self._home_knowledge_scan_requested = False
                self._home_knowledge_scan_inflight = False
                self._home_knowledge_scan_retries_remaining = 1
                self._home_knowledge_scan_leave_turn = None
        if self._equipment_transaction_session is not None:
            session = self._equipment_transaction_session
            pending = session.pending_action
            posted_command = session.posted_command_id
            operation_outcome = getattr(
                self, "_equipment_transaction_operation_outcome", None
            )
            advanced = session.observe(observe_equipment_transactions(
                snapshot, operation_outcome=operation_outcome,
            ))
            self._equipment_transaction_operation_outcome = None
            if (advanced and pending is not None and pending.kind in {"deposit", "withdraw"}
                    and self._equipment_transaction_posted_catalog_update is not None):
                # Legacy atomic Home operations reconcile their knowledge at
                # their own observed effect seam. Direct prepared transaction
                # operations carry the update fenced to this session below.
                self._invalidate_home_observation()
                self._equipment_transaction_home_pages = None
            catalog_update = self._equipment_transaction_posted_catalog_update
            if advanced and catalog_update is not None:
                target_id, action_index, command, kind, item, intent = catalog_update
                if (target_id == session.target_loadout_id
                        and action_index == session.index - 1
                        and command == posted_command):
                    if self._open_home_page_is_complete(snapshot):
                        self._adopt_home_catalogue(tuple(
                            self._inventory_item_from_store_item(ware)
                            for ware in snapshot.store.items))
                    elif item.count > 1:
                        # Reacquire a split stack's actual name/count from
                        # observed pages, preserving its physical move identity.
                        self._equipment_catalog.invalidate_home()
                    elif kind == "deposit":
                        self._equipment_catalog.record_home_deposit(item, intent=intent)
                    elif kind == "withdraw":
                        self._equipment_catalog.record_home_withdrawal(item, intent=intent)
                self._equipment_transaction_posted_catalog_update = None
            if (
                advanced
                and pending is not None
                and pending.kind in {"deposit", "withdraw"}
            ):
                # The confirmed transaction moved an item into or out of Home.
                self._observe_home_operation_effect()
            if (getattr(self, "_town_claim_bar_enforced", False)
                    and advanced and pending is not None):
                visit = self._store_visit
                if (visit is not None
                        and visit.store_type == STORE_HOME
                        and visit.operation_posted
                        and visit.operation_producer_family == "equipment-txn"
                        and visit.operation_key == posted_command):
                    # The session and the visit describe the same posted
                    # action. Its observed effect completes both ledgers so
                    # the next action can run on this Home board.
                    visit.operation_effect_observed = True
                    visit.operation_released = True
            if advanced and pending is not None:
                if (
                    pending.kind == 'takeoff' and pending.target_slot is not None
                ):
                    self._equipment_transaction_owned_items.append(
                        (
                            pending.move_identity or pending.item_identity,
                            pending.target_slot,
                        )
                    )
                elif pending.kind in {"equip", "reposition"}:
                    self._release_equipment_transaction_owned_item(
                        pending.move_identity or pending.item_identity
                    )
                elif pending.kind == "deposit":
                    self._release_equipment_transaction_owned_item(
                        pending.move_identity or pending.item_identity
                    )
            reconciled_any = False
            reconciled_index = session.index
            while session.reconcile_carried(snapshot):
                reconciled_any = True
                # Only already observed carried/worn targets can advance here.
                for reconciled in session.plan.actions[reconciled_index:session.index]:
                    if reconciled.kind in {"equip", "reposition"}:
                        self._release_equipment_transaction_owned_item(
                            reconciled.move_identity or reconciled.item_identity)
                reconciled_index = session.index
            if (advanced or reconciled_any) and not session.complete:
                held = self._claim_register.current
                declaration = getattr(held, "execution", None)
                if (held is not None and held.owner.value == "equipment-txn"
                        and declaration is not None
                        and declaration.continuation == "equipment.next-action"):
                    action = session.current_action
                    self._claim_register.declare_execution(
                        held.claim_id, producer="equipment-txn",
                        work_id=f"equipment:{session.target_loadout_id}:{session.index}",
                        state="acting", next_step="equipment.next-action",
                        arguments=(action.kind, action.target_slot, action.item_identity),
                        expected_effect="equipment-action-confirmed",
                        continuation="equipment.next-action", budget_ref=declaration.budget_ref)
            if self._equipment_transaction_session.complete:
                self._retire_replaced_equipment_transaction_owned_items(
                    snapshot, self._equipment_transaction_session
                )
                if (
                    self._equipment_transaction_restoring
                    and self._equipment_transaction_owned_items
                ):
                    # The recoverable prefix is complete.  Reconcile it and
                    # rebuild the remainder before any ordinary town policy can
                    # observe a session gap.
                    self._abandon_blocked_equipment_transaction(snapshot)
                    self._equipment_optimization_signature = None
                else:
                    self._complete_equipment_transaction_claim()
                    self._equipment_transaction_session = None
                    self._equipment_transaction_restoring = False
                    self._equipment_transaction_restore_terminal = None
                    self._equipment_transaction_restore_remainder = ()
                    self._equipment_optimization_signature = None
                    if self._equipment_transaction_route_terminal_pending:
                        self._equipment_transaction_route_terminal_pending = False
                        self._equipment_transaction_route_terminal = (
                            "equipment-transaction:home-route-repeat-terminal"
                        )
                        self._town_visit_ledger.blocked_stores.add(STORE_HOME)
        if (getattr(self, '_crossarea_fundraising_enforced', False) and self.last_reason in {*()}):
            return WAIT_KEY
        self._observe(snapshot, observation=latest_snapshot)
        if not self._observe_fundraising_transport(snapshot):
            purpose_record = self._fundraising_purpose_record
            if purpose_record is not None:
                self._claim_register.set_bar(ClaimBar(
                    owner=ClaimOwner.FUNDRAISING,
                    goal=claim_observe(
                        ("fundraising-purpose",
                         str(purpose_record.purpose.identity)), None,
                        source="fundraising-purpose",
                    ),
                    kind=CLAIM_BAR_ERRAND,
                    clearance=self._claim_errand_clearance(
                        snapshot, "fundraising", None
                    ),
                    rung="fundraising",
                    since_turn=snapshot.turn,
                    since_sequence=self._decision_sequence,
                    claim_id=purpose_record.purpose.identity,
                    ending=f"failed:{purpose_record.failure}",
                ))
            self.last_reason = (
                "ownership:contract-conflict:fundraising:wrong-destination"
            )
            return WAIT_KEY
        self._nav_ledger.begin_decision()
        self.escape_ladder_telemetry = None
        self.town_teleport_refusal = None
        self._fruitless_disengage_spent_this_decision = False
        if self._home_errand.state == HomeErrandState.STOPPED:
            self._release_claim_goal(
                "home-errand-stopped", owners=("home-errand",),
                kinds=(CLAIM_GOAL_OBSERVE,),
                sources=(CLAIM_OBSERVE_STORE_OPERATION,),
            )
            self.last_reason = self._home_errand.reason("stopped")
            return WAIT_KEY
        if (
            snapshot.store is None
            and getattr(snapshot, "in_town", False)
            and (
                "home-scan-incomplete" in getattr(
                    self._equipment_optimization_preparation, "blockers", ()
                )
                or self._home_available(snapshot)
            )
            and not snapshot.player.recalling
            and not any(
                grid.store_number >= 0
                for grid in (snapshot.grid_at(snapshot.player.position),)
                if grid is not None
            )
            and (
                not self._equipment_catalog.home_scan_complete
                or self._home_knowledge_invalidated
            )
            # A Home observation permits ordinary first acquisition.  Once
            # optimization names incomplete contents as its blocker, however,
            # no Home existence, reachability, route, visit state, or other
            # outstanding equipment work may veto ``~9``.
            and not self._home_knowledge_scan_requested
            and self._home_knowledge_scan_epoch is None
            and self._equipment_transaction_session is None
            and self._store_leave_inflight is None
            and self._store_entry_posted_owner is None
            and (
                self._equipment_mutation.state.name == "IDLE"
                or self._equipment_mutation.goal == "transaction-apply"
            )
            and not self._town_space_deposit_actionable(snapshot)
            and not self._defer_town_errand("home-scan", "outside-scan")
        ):
            if (getattr(self, "_town_claim_bar_enforced", False)
                    and self._home_atomic_deposit_pending is not None
                    and not getattr(self._store_visit, "operation_posted", False)
                    and self._claim_errand_hold("__none__") is None):
                # A staged but unposted deposit owns no turn without a claim.
                # Cancel its named reservation before choosing the scan.
                visit = self._store_visit
                identity = getattr(visit, "claim_operation_identity", None)
                if identity is not None:
                    self._end_execution_delegation(
                        "home-tail", ("staged-tail", *identity),
                        completed=False, cause="unposted-reservation-cancelled",
                    )
                pending = self._home_atomic_deposit_pending
                self._decision_cancelled_home_reservation = {
                    "work_identity": ("unposted-home-deposit",
                                      tuple(pending[0]), pending[2]),
                    "cause": "selected-home-scan",
                }
                self._home_atomic_deposit_pending = None
                self._home_entry_operation_posted = False
                self._store_entry_wait_owner = None
                self._store_entry_wait_key = None
                self._store_entry_wait_turn = None
                self._town_visit_ledger.pending_store_transaction = None
                self._intentional_entrance_activation = False
            if self._home_errand.needs_knowledge:
                return self._home_errand_knowledge_key(snapshot)
            else:
                self.last_reason = "home:request-knowledge-scan"
            self._offer_execution(
                "~9\x1b\x1b",
                producer=("home-errand" if self._home_errand.needs_knowledge
                          else "home-scan"),
                work_id=f"home-knowledge:{self._town_visit_epoch}",
                next_step="home.knowledge.request",
                expected_effect="catalogue-adopted",
                continuation="home.knowledge.observe",
                budget_ref="home-knowledge-existing-epoch",
            )
            return "~9\x1b\x1b"
        leaving_home = (
            self._store_leave_inflight is not None
            and self._store_leave_inflight[2] == STORE_HOME
        )
        pending_deposit = self._home_atomic_deposit_pending
        if (
            snapshot.store is None
            and leaving_home
            and self._home_atomic_deposit_pending is None
            and pending_deposit is None
        ):
            if getattr(self, "_home_visit", None) is not None:
                self._home_visit.observe_outside(
                    effect_observed=bool(
                        self._store_visit is not None
                        and self._store_visit.operation_effect_observed
                    )
                )
            self._home_entry_operation_posted = False
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._store_visit is None
            and self._equipment_transaction_session is not None
        ):
            # Reconnect/import boundary: turn the already-existing operation
            # owner into a visit once, before any in-store decision is routed.
            self._store_visit = StoreVisit(
                owner="equipment-transaction", purpose="equipment-work",
                store_type=STORE_HOME, phase=StoreVisitPhase.OPERATING,
                visit_origin="equipment-transaction-recovery",
                opened_sequence=self._decision_sequence,
                opened_producer_family="equipment-txn",
            )
        elif snapshot.store is not None and self._store_visit is None:
            self._store_visit = StoreVisit(
                owner="shop-handler", purpose="recovered-shopping",
                store_type=snapshot.store.store_type,
                phase=StoreVisitPhase.OPERATING,
                visit_origin="shop-handler-recovery",
                opened_sequence=self._decision_sequence,
                opened_producer_family=None,
            )
        unintended_store_context = (
            snapshot.store is not None and self._store_visit is None
        )
        if unintended_store_context:
            if (
                snapshot.store.store_type == STORE_HOME and self._home_knowledge_current and (self._home_scan_item_count == 0) and (self._home_atomic_deposit_pending is None) and (self._equipment_transaction_session is None)
            ):
                self._report_town_stop_pass(
                    snapshot, STORE_HOME, goal_satisfied=True,
                )
                self.last_reason = "home:scan-complete-from-open-page"
            else:
                self.last_reason = (
                    "home:store-context-exit"
                    if snapshot.store.store_type == STORE_HOME
                    else "shop:store-context-exit"
                )
            key = LEAVE_STORE_KEY
            if self.last_reason == "home:scan-complete-from-open-page":
                self._offer_home_scan_leave()
            else:
                self._offer_execution(
                    key, producer=self._claim_family_of(self.last_reason),
                    work_id="store:unexpected-context-exit",
                    next_step="store.leave.send",
                    arguments=(snapshot.store.store_type,),
                    expected_effect="outside-store",
                )
        elif (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._store_visit is not None
            and self._store_visit.store_type != STORE_HOME
            and self._home_scan_source != "foreign-store-page"
            and self._equipment_transaction_session is None
            and not self._identify_staff_ready(snapshot)
            and self._home_knowledge_current
            and self._home_pending_item is None
            and not self._home_pending_batch
            and self._home_atomic_withdraw_pending is None
            and not any(
                item.tval == TVAL_STAFF
                and item.sval == SV_STAFF_IDENTIFY
                and item.charges > 0
                and self._identify_staff_acquisition_worthwhile(
                    snapshot, item.charges
                )
                and self._item_signature(item) not in self._deferred_home_items
                for item in self._home_knowledge_items
            )
        ):
            # The first lagged Home page cannot transfer a different shop's
            # live visit to Home or spend Home's unavailable-stock terminal.
            # Record that page, leave it, and let a later proper Home pass own
            # the terminal if the shortage remains.
            self._home_scan_source = "foreign-store-page"
            self.last_reason = "home:scan-complete-from-open-page"
            key = LEAVE_STORE_KEY
            self._offer_home_scan_leave()
        elif (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and (
                staged_home_operation :=
                self._town_producer_entry(
                    "_release_staged_store_operation",
                    lambda: self._release_staged_store_operation(snapshot),
                    family=(getattr(self._store_visit,
                                    "operation_producer_family", None)
                            or "home-visit"))
            )
            is not None
        ):
            # Home has an earlier store-context owner than ordinary shops.  A
            # surplus tail staged by another Home-purpose visit is already
            # pack-letter-bound here; never derive a new letter from this page.
            # Release through the same StoreVisit fields at that seam so its
            # legacy leave-after-one-operation branch cannot steal the fresh
            # page that authorizes this two-stage tail.
            key = staged_home_operation
            self.last_reason = (
                "home:atomic-withdraw"
                if key.lstrip().startswith(BUY_KEY)
                else (
                    "home:weight-overload-deposit"
                    if self._inventory_overweight(snapshot)
                    else "home:atomic-deposit"
                )
            )
        elif (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and (self._home_full_relief is not None
                 or self._home_full_retry_deposits is not None)
            and not self._equipment_transaction_owned_items
            and self._home_atomic_deposit_pending is None
            and self._home_atomic_withdraw_pending is None
        ):
            # The suspended equipment continuation cannot deposit more items
            # into this full Home while its prerequisite sale is still pending.
            key = self._town_producer_entry(
                "_home_full_relief_key", lambda: self._home_full_relief_key(snapshot),
                family="home-visit")
        elif (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._equipment_transaction_session is not None
            and not self._home_entry_operation_posted
            and self._store_leave_inflight is None
        ):
            # An independently observed Home page is not transaction failure:
            # Home is the required context for deposits and the handoff back to
            # the entrance-bound atomic withdrawal.  The Home handler may only
            # advance that existing plan or leave; it still cannot bind a new
            # item command from the store page.
            key = self._town_producer_entry(
                "_equipment_transaction_home_key",
                lambda: self._equipment_transaction_home_key(snapshot),
                family="equipment-txn")
            if key is None and self.last_reason == "equipment-transaction:defer-identification":
                key = LEAVE_STORE_KEY
        elif (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._home_entry_operation_posted
            and self._equipment_transaction_session is None
        ):
            # The combined command already completed this entry's sole input
            # operation.  Leave immediately; confirmation comes from the next
            # ordinary outside snapshot, never from waiting or retrying inside.
            self.last_reason = "home:leave-after-one-operation"
            key = LEAVE_STORE_KEY
            self._offer_execution(
                key, producer=self._claim_family_of(self.last_reason),
                work_id="home:leave-after-one-operation",
                next_step="store.leave.send", arguments=(STORE_HOME,),
                expected_effect="outside-store",
            )
        elif (
            snapshot.store is None
            and self._shop_observation is not None
            and self._store_leave_inflight is not None
            and self._can_compose_shop_observation(snapshot)
        ):
            # The saved ordinary-store page is the address of the second
            # visit.  Claim it before generic routing can turn the entrance
            # board into another approach.  The page/position predicate is
            # sufficient provenance even when the derived LEAVING view was
            # lost between the posted ESC and this authoritative board.
            self._store_leave_inflight = None
            observed_store = self._shop_observation[0].store_type
            arbiter = self._town_turn_arbiter
            if arbiter is None:
                arbiter = _new_town_turn_arbiter()
                self._town_turn_arbiter = arbiter
            visit = arbiter.acquire_store_visit(
                owner="shop-one-shot",
                purpose="observed-transaction",
                store_type=observed_store,
                opened_sequence=self._decision_sequence,
                opened_producer_family=None,
                close_visit=self._close_store_visit,
            )
            assert visit is not None, (
                "an adjacent saved shop page must own its one-shot visit"
            )
            self._acquire_store_visit_attempt = {
                "acquire_store_visit_called": True,
                "requested_owner": "shop-one-shot",
                "requested_store": observed_store,
                "acquire_result": "granted-observed-outside",
            }
            key = self._town_producer_entry(
                "_atomic_shop_transaction_key",
                lambda: self._atomic_shop_transaction_key(snapshot),
                family=self._town_shop_entry_family())
            if key is not None:
                visit.opened_producer_family = self._claim_family_of(self.last_reason)
            if key is None:
                self._close_store_visit("one-shot-no-operation")
                key = self._decide(snapshot)
        elif self._store_leave_inflight is not None:
            leave_generation, leave_turn, leave_store = self._store_leave_inflight
            home_tail = (
                self._home_tail_leave_continuation(
                    getattr(self._claim_register, "current", None), snapshot)
                if getattr(self, "_town_claim_bar_enforced", False)
                else None
            )
            if home_tail is not None:
                key = home_tail
            elif snapshot.store is None:
                self._store_leave_inflight = None
                # Visit A has just produced its authoritative page and left.
                # Give the derived address first ownership of this adjacent
                # outside generation; unrelated town waits cannot interleave
                # between observation and the one-shot Visit B.
                if (
                    leave_store != STORE_HOME
                    and self._shop_observation is not None
                    and self._shop_observation[0].store_type == leave_store
                ):
                    # _store_leave_inflight is a derived view of _store_visit.
                    # Clearing it above closes that visit, so the arbiter slot
                    # is provably empty and this acquire always grants a new
                    # visit.
                    arbiter = self._town_turn_arbiter
                    if arbiter is None:
                        arbiter = _new_town_turn_arbiter()
                        self._town_turn_arbiter = arbiter
                    visit = arbiter.acquire_store_visit(
                        owner="shop-one-shot",
                        purpose="observed-transaction",
                        store_type=leave_store,
                        opened_sequence=self._decision_sequence,
                        close_visit=self._close_store_visit,
                    )
                    assert visit is not None, (
                        "clearing derived _store_leave_inflight must empty "
                        "the arbiter slot before one-shot acquire"
                    )
                    self._acquire_store_visit_attempt = {
                        "acquire_store_visit_called": True,
                        "requested_owner": "shop-one-shot",
                        "requested_store": leave_store,
                        "acquire_result": "granted-new",
                    }
                    key = self._town_producer_entry(
                        "_atomic_shop_transaction_key",
                        lambda: self._atomic_shop_transaction_key(snapshot),
                        family=self._town_shop_entry_family())
                    if key is None:
                        self._close_store_visit("one-shot-no-operation")
                        key = self._decide(snapshot)
                else:
                    key = self._decide(snapshot)
            elif snapshot.store.store_type != leave_store:
                self._store_leave_inflight = None
                key = self._decide(snapshot)
            elif getattr(snapshot, "turn", 0) > leave_turn:
                self._store_leave_inflight = None
                if snapshot.store.store_type == STORE_HOME:
                    if (
                        self._home_knowledge_current and self._home_scan_item_count == 0 and (self._home_atomic_deposit_pending is None) and (self._equipment_transaction_session is None)
                    ):
                        self._report_town_stop_pass(
                            snapshot, STORE_HOME, goal_satisfied=True,
                        )
                        self.last_reason = "home:scan-complete-from-open-page"
                    else:
                        self.last_reason = "home:store-context-exit"
                    key = LEAVE_STORE_KEY
                    if self.last_reason == "home:scan-complete-from-open-page":
                        self._offer_home_scan_leave()
                    else:
                        self._offer_execution(
                            key, producer="home-visit",
                            work_id="home:store-context-exit",
                            next_step="store.leave.send",
                            arguments=(STORE_HOME,),
                            expected_effect="outside-store",
                        )
                else:
                    key = self._decide(snapshot)
            elif (
                self._decision_sequence <= leave_generation
                or getattr(snapshot, "turn", 0) < leave_turn
            ):
                self.last_reason = "shop:await-leave-generation"
                key = "\r"
            elif (
                self._decision_sequence - leave_generation >= STORE_STUCK_LIMIT
            ):
                # The confirmation key of an open Home page is a no-op that
                # cannot advance the turn, so ``turn > leave_turn`` above is
                # not reachable by waiting: without a bound this branch repeats
                # forever and the driver's prompt bound ends the run.  A whole
                # confirmation budget without a new store generation means the
                # posted leave never took effect; release the visit and decide
                # this page again, exactly as the other releases above do.
                self._close_store_visit("leave-unconfirmed")
                key = self._decide(snapshot)
            else:
                # Planning itself may reserve inventory or transaction state.
                # An unchanged store generation is therefore a hard barrier,
                # not a filter applied after a side-effecting decision.
                self.last_reason = "shop:await-leave-confirmation"
                key = (
                    LEAVE_STORE_KEY
                    if snapshot.store.store_type == STORE_HOME
                    and self._home_entry_operation_posted
                    else "\r"
                    if snapshot.store.store_type == STORE_HOME
                    else LEAVE_STORE_KEY
                )
        elif (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
        ):
            # Home item selection is never decided in the store loop.  Every
            # authorized deposit/withdrawal is a complete outside-composed
            # one-shot; an independently observed Home context is recovery-only.
            session = self._equipment_transaction_session
            active_holder = (
                self._claim_errand_hold("__none__")
                if getattr(self, "_town_claim_bar_enforced", False) else None
            )
            if (self._home_catalogue_sequence_enforced()
                    and (catalogue_key := self._home_catalogue_work_key(snapshot)) is not None):
                key = catalogue_key
            elif (active_holder is not None
                    and active_holder.owner.value == "equipment-txn"
                    and session is not None
                    and getattr(self._store_visit, "operation_posted", False)
                    and not getattr(self._store_visit, "operation_released", False)):
                self.last_reason = "equipment-transaction:atomic-deposit"
                key = WAIT_KEY
                self._offer_execution(
                    key, producer="equipment-txn",
                    work_id="equipment:atomic-deposit-pending",
                    next_step="home.operation.observe",
                    expected_effect="home-inventory-effect",
                    continuation="equipment.next-action",
                )
            elif (rearm := self._town_producer_entry(
                "_home_rearm_key", lambda: self._home_rearm_key(snapshot),
                family="equipment-txn")) is not None:
                key = rearm
            elif (
                getattr(self, "_town_claim_bar_enforced", False)
                and self._equipment_transaction_session is not None
                and self._equipment_transaction_session.pending_action is None
                and (holder := self._claim_errand_hold("__none__")) is not None
                and holder.owner.value == "equipment-txn"
                and (equipment_key := self._town_producer_entry(
                    "_equipment_transaction_home_key",
                    lambda: self._equipment_transaction_home_key(snapshot),
                    family="equipment-txn")) is not None
            ):
                key = equipment_key
            elif (
                self._home_atomic_deposit_pending is None and self._equipment_transaction_session is None and (not self._town_space_deposit_actionable(snapshot)) and getattr(self, '_queue_home_catalogue_shortages', lambda _snapshot: False)(snapshot)
            ):
                # This is the single live catalogue-shortage owner.  Purchase
                # gates may route here first, but no shop shelf is required.
                self._request_store_trip(STORE_HOME, "home-visit")
                self.last_reason = "home:queue-catalogue-shortage"
                key = LEAVE_STORE_KEY
                self._offer_execution(
                    key, producer="home-visit", work_id="home:queue-catalogue-shortage",
                    next_step="store.leave.send", arguments=(STORE_HOME,),
                    expected_effect="outside-store",
                )
            elif (
                self._home_atomic_deposit_pending is None and self._equipment_transaction_session is None and (not self._identify_staff_ready(snapshot)) and (self._home_pending_item is None) and (not self._home_pending_batch) and (self._home_atomic_withdraw_pending is None) and (PACK_CAPACITY - len(snapshot.inventory) > max(HOME_BATCH_RESERVED_SLOTS, MIN_FREE_PACK_SLOTS)) and ((identify_staff := max(((catalogue_index, item) for catalogue_index, item in enumerate(self._home_knowledge_items if self._home_knowledge_current else snapshot.store.items) if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY and (item.charges > 0) and self._identify_staff_acquisition_worthwhile(snapshot, item.charges) and (self._item_signature(item) not in self._deferred_home_items)), key=lambda indexed_item: (indexed_item[1].charges, indexed_item[0]), default=None)) is not None)
            ):
                # The Home entry owner, unlike _shop(), is on the live path.
                # Bind the catalogue item here so the outside owner can compose
                # the complete withdrawal on the following decision.
                _catalogue_index, identify_staff = identify_staff
                signature = self._item_signature(identify_staff)
                self._home_pending_item = signature
                self._requeue_home_withdrawal(signature)
                self._home_pending_quantity = 1
                self._home_pending_quantities[signature] = 1
                self._home_withdrawal_queued = True
                self.last_reason = "home:queue-withdraw-identify-staff-reserve"
                key = LEAVE_STORE_KEY
            elif (
                self._home_atomic_deposit_pending is None and self._equipment_transaction_session is None and ((standing_digger := self._queue_standing_home_digger(snapshot)) is not None)
            ):
                # The open page is authoritative Home-stock evidence even when
                # entry ownership was recovered after a restart or lagged post.
                # Selection is bound here; the outside decision composes it.
                key = standing_digger
            elif (
                self._home_knowledge_current and self._home_scan_item_count == 0 and (self._home_atomic_deposit_pending is None) and (self._equipment_transaction_session is None)
            ):
                self._report_town_stop_pass(
                    snapshot, STORE_HOME, goal_satisfied=True,
                )
                self.last_reason = "home:scan-complete-from-open-page"
                key = LEAVE_STORE_KEY
                self._offer_home_scan_leave()
            elif (
                self._home_atomic_deposit_pending is None and self._equipment_transaction_session is None and self._open_home_page_is_complete(snapshot) and (not self._equipment_catalog.home_scan_complete or not self._home_knowledge_current or self._home_knowledge_invalidated)
            ):
                self._adopt_home_catalogue(tuple(
                    self._inventory_item_from_store_item(item)
                    for item in snapshot.store.items
                ))
                self._home_scan_source = "observed-home-page"
                self.last_reason = "home:scan-complete-from-open-page"
                key = LEAVE_STORE_KEY
                self._offer_home_scan_leave()
            elif (
                self._home_atomic_deposit_pending is None and self._equipment_transaction_session is None and self._home_knowledge_current and (not self._home_knowledge_invalidated) and (pending_withdrawals := {*((self._home_pending_item,) if self._home_pending_item is not None else ()), *self._home_pending_batch, *((self._home_atomic_withdraw_pending[0],) if self._home_atomic_withdraw_pending is not None else ())}) and pending_withdrawals.intersection({self._item_signature(item) for item in (snapshot.store.items if self._open_home_page_is_complete(snapshot) else (*snapshot.store.items, *self._home_knowledge_items))})
            ):
                # Ordinary withdrawals are composed only from the adjacent
                # outside snapshot.  This hand-off is not a failed stop pass.
                self._request_store_trip(STORE_HOME, "home-visit")
                self.last_reason = "home:leave-for-pending-withdraw"
                key = LEAVE_STORE_KEY
                self._offer_execution(
                    key, producer="home-visit", work_id="home:leave-for-pending-withdraw",
                    next_step="store.leave.send", arguments=(STORE_HOME,),
                    expected_effect="outside-store",
                )
            elif (
                self._home_atomic_deposit_pending is None and self._equipment_transaction_session is None and (not self._equipment_catalog.home_scan_complete or not self._home_knowledge_current or self._home_knowledge_invalidated)
            ):
                routed_home_visit = bool(
                    self._store_visit is not None
                    and self._store_visit.store_type == STORE_HOME
                    and self._store_visit.owner != "shop-handler"
                    and not self._store_visit.operation_released
                )
                if (
                    routed_home_visit
                    and self._home_knowledge_invalidated
                    and not self._home_knowledge_scan_requested
                    and self._home_knowledge_scan_epoch is None
                    and not (
                        getattr(self, "_town_claim_bar_enforced", False)
                        and self._store_leave_inflight is not None
                    )
                    and not (
                        getattr(self, "_town_claim_bar_enforced", False)
                        and (
                            self._home_atomic_deposit_pending is not None
                            or self._home_atomic_withdraw_pending is not None
                        )
                    )
                    and not self._defer_town_errand(
                        "home-scan", "open-home-scan"
                    )
                ):
                    self.last_reason = "home:request-knowledge-scan"
                    key = HOME_KNOWLEDGE_MACRO
                    self._offer_home_knowledge_request(producer="home-scan")
                else:
                    # A visible page of a multi-page (or metadata-poor) Home is
                    # useful evidence, but it cannot replace the complete ~9 list.
                    self.last_reason = "home:scan-incomplete-open-page"
                    key = LEAVE_STORE_KEY
                    self._offer_execution(
                        key, producer="home-scan",
                        work_id=f"home-knowledge-leave:{self._decision_sequence}",
                        next_step="store.leave.send",
                        expected_effect="outside-store",
                        continuation="home.knowledge.request",
                        budget_ref="home-knowledge-existing-epoch",
                    )
            elif (
                self._home_atomic_deposit_pending is None and self._equipment_transaction_session is None and ((open_page_deposit := self._town_producer_entry('_open_home_deposit_key', lambda: self._open_home_deposit_key(snapshot), family='home-visit')) is not None)
            ):
                key = open_page_deposit
            elif (
                self._home_atomic_deposit_pending is None and (not self._identify_staff_ready(snapshot)) and self._home_knowledge_current and (self._home_pending_item is None) and (not self._home_pending_batch) and (self._home_atomic_withdraw_pending is None) and (STORE_HOME not in self._town_store_attempted) and (PACK_CAPACITY - len(snapshot.inventory) <= max(HOME_BATCH_RESERVED_SLOTS, MIN_FREE_PACK_SLOTS) or not any((item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY and (item.charges > 0) and self._identify_staff_acquisition_worthwhile(snapshot, item.charges) and (self._item_signature(item) not in self._deferred_home_items) for item in self._home_knowledge_items)))
            ):
                has_usable_staff = any(
                    item.tval == TVAL_STAFF
                    and item.sval == SV_STAFF_IDENTIFY
                    and item.charges > 0
                    and self._identify_staff_acquisition_worthwhile(
                        snapshot, item.charges
                    )
                    and self._item_signature(item)
                    not in self._deferred_home_items
                    for item in self._home_knowledge_items
                )
                self._report_town_stop_pass(
                    snapshot, STORE_HOME, goal_satisfied=False
                )
                self._set_town_store_attempted(
                    STORE_HOME, snapshot.turn, "identify-staff-reserve-terminal"
                )
                self.last_reason = (
                    "home:identify-staff-reserve-no-pack-space"
                    if has_usable_staff
                    else "home:identify-staff-reserve-unavailable"
                )
                key = LEAVE_STORE_KEY
                self._offer_execution(
                    key, producer="home-visit",
                    work_id=self.last_reason,
                    next_step="store.leave.send", arguments=(STORE_HOME,),
                    expected_effect="outside-store",
                )
            elif (
                self._home_atomic_deposit_pending is None and self._equipment_transaction_session is None
            ):
                self._report_town_stop_pass(
                    snapshot, STORE_HOME, goal_satisfied=False
                )
                self._set_town_store_attempted(STORE_HOME, snapshot.turn, "home-capture-complete")
                self.last_reason = "home:route-claim-unfulfilled"
                self._post_owner_expectation(
                    snapshot, self.last_reason, "store_type"
                )
                key = LEAVE_STORE_KEY
                self._offer_execution(
                    key, producer="home-visit", work_id="home:route-claim-unfulfilled",
                    next_step="store.leave.send", arguments=(STORE_HOME,),
                    expected_effect="outside-store",
                )
            else:
                request = getattr(self._home_visit, "request", None)
                requester = (
                    request.requester if request is not None else "unknown-requester"
                )
                claim_uncomposable = bool(request is not None and False)
                if claim_uncomposable:
                    refusal = "home-knowledge-invalidated"
                    verdict = f"claim-uncomposable:{requester}:{refusal}"
                    self._report_town_stop_pass(
                        snapshot, STORE_HOME, goal_satisfied=False
                    )
                    self._home_claim_uncomposable_signature = (
                        self._home_claim_signature(request)
                    )
                    self._set_town_store_attempted(
                        STORE_HOME, snapshot.turn, verdict
                    )
                    self.last_reason = f"town:blocked:home-{verdict}"
                else:
                    self.last_reason = "home:store-context-exit"
                self._post_owner_expectation(
                    snapshot, self.last_reason, "store_type"
                )
                key = LEAVE_STORE_KEY
                self._offer_execution(
                    key, producer=self._claim_family_of(self.last_reason),
                    work_id=self.last_reason,
                    next_step="store.leave.send", arguments=(STORE_HOME,),
                    expected_effect="outside-store",
                    continuation=("equipment.next-action"
                        if self._claim_family_of(self.last_reason) == "equipment-txn"
                        and self._equipment_transaction_session is not None else None),
                )
        else:
            key = self._decide(snapshot)
        if (getattr(self, "_town_claim_bar_enforced", False)
                and key == "\r" and snapshot.store is not None
                and self._equipment_transaction_session is not None
                and (self._equipment_transaction_session.pending_action is not None
                     or (self._store_visit is not None
                         and self._store_visit.operation_posted
                         and not self._store_visit.operation_released))):
            # An unchanged store command loop cannot turn CR into evidence of
            # an equipment mutation or a successful leave. Do not spend the
            # visit budget repeating this no-effect continuation.
            key = self._silent_holder_stop("equipment-txn")
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and not self._home_entry_operation_posted
            and self._equipment_transaction_session is None
            # Released owners return None so the common fallback below can
            # choose the safe context-specific action.  The sell guard only
            # classifies concrete commands; it does not own that sentinel.
            and key is not None
            and key.startswith(SELL_KEY)
        ):
            # A resumed process may first observe an already-open Home.  An
            # ordinary deposit is only safe when its pack letter was bound in
            # the adjacent outside snapshot and posted with entry and exit.
            self.last_reason = "home:leave-unbound-deposit"
            key = LEAVE_STORE_KEY
            self._offer_execution(
                key, producer="home-visit", work_id="home:leave-unbound-deposit",
                next_step="store.leave.send", arguments=(STORE_HOME,),
                expected_effect="outside-store",
            )
        self._remember_swarm_distances(snapshot)
        if (getattr(self, "_town_claim_bar_enforced", False)
                and key is None and (self.last_reason or "").startswith((
                    "ownership:holder-silent:", "ownership:declaration-"))):
            return None
        if key is None and self._warning_prompt_stops_decision:
            return None
        key = self._flee_sustain_key(snapshot, key)
        # USER DECISION 2026-10-03 06:2x: Speed at a strong fight's start, in
        # place of the fighting action only.
        key = self._strong_fight_speed_filter(snapshot, key)
        # Bookkeeping is a separate, higher rung: save and dump may replace
        # the selected key under their safe-filler predicates. The result
        # detector excludes their family from town errand judgement.
        key = self._periodic_game_save_key(snapshot, key)
        key = self._periodic_character_dump_key(snapshot, key)
        if key is None:
            if (getattr(self, "_town_claim_bar_enforced", False)
                    and (snapshot.in_town or snapshot.store is not None)
                    and self._claim_errand_hold("__none__") is not None):
                return None
            def fallback():
                self.last_reason = (
                    "policy:none-store-exit" if snapshot.store is not None
                    else "policy:none-wait"
                )
                return LEAVE_STORE_KEY if snapshot.store is not None else WAIT_KEY
            key = self._town_producer_entry(
                "idle-fallback", fallback, family="idle",
            )
            if key is None:
                return None
        if snapshot.store is not None and key == WAIT_KEY:
            # Hengband's store command loop rejects the normal rest command.
            # Carriage return is an explicit no-op in the store command loop.
            key = "\r"
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and key == LEAVE_STORE_KEY
            and self.last_reason != "home:processing-complete"
            and not (
                self.last_reason == "home:leave-after-one-operation"
                and self._home_random_teleport_withdrawal is not None
            )
            and not (
                self.last_reason == "home:scan-complete-from-open-page"
                and self._store_visit is not None
                and self._store_visit.store_type != STORE_HOME
            )
            and not self.last_reason.startswith(
                "town:blocked:home-claim-uncomposable:"
            )
            # Abandonment is not a completed Home pass.  In particular, the
            # last-resort restore installed for already removed gear must not
            # spend the visit allowance that belongs to useful Home work.
            and not (
                self._equipment_transaction_restoring
                and not self._home_entry_operation_posted
            )
        ):
            self._report_town_stop_pass(
                snapshot,
                STORE_HOME,
                goal_satisfied=not self._home_owner_goal_pending(snapshot),
                operation_completed=bool(
                    self._store_visit is not None
                    and self._store_visit.operation_effect_observed
                ),
            )
        if (
            snapshot.store is not None
            and snapshot.store.store_type != STORE_HOME
            and key == LEAVE_STORE_KEY
        ):
            # Non-Home stops also need a bounded owner.  The ordinary attempted
            # latch can be deliberately re-opened by an identification request;
            # without advancing the plan, an out-of-stock Alchemist was entered
            # and left forever.  Count a completed store visit and block this
            # stop after TOWN_STOP_PASS_LIMIT unsatisfied passes, just like Home.
            store_type = snapshot.store.store_type
            goal_satisfied = not any(
                need.store_type == store_type
                for need in self._enumerate_town_needs(snapshot)
            )
            self._report_town_stop_pass(
                snapshot,
                store_type,
                goal_satisfied=goal_satisfied,
                operation_completed=bool(
                    self._store_visit is not None
                    and self._store_visit.operation_effect_observed
                ),
            )
        key = self._break_positional_oscillation(snapshot, key)
        key = self._break_livelock(snapshot, key)
        key = self._bound_escape_wait(snapshot, key)
        if (
            key == WAIT_KEY
            and snapshot.store is None
            and not (
                self._store_visit is not None
                and self._store_visit.operation_posted
                and not self._store_visit.operation_released
            )
            and (
                self._home_atomic_withdraw_pending is not None
                or (
                    self._equipment_transaction_session is not None
                    and self._equipment_transaction_session.pending_action is not None
                    and self._equipment_transaction_session.pending_action.kind == "withdraw"
                    and self._equipment_transaction_session.index + 1
                    < len(self._equipment_transaction_session.plan.actions)
                    and self._equipment_transaction_session.plan.actions[
                        self._equipment_transaction_session.index + 1
                    ].phase
                    != PHASE_EQUIP
                )
            )
        ):
            # The outside half of an atomic Home withdrawal is still owned by
            # the posted one-shot until inventory confirms it.  On the Home
            # entrance, ordinary WAIT would either re-enter the store or be
            # projected by the entrance invariant into a step away.  Escape is
            # a command-loop no-op: it preserves the entrance position so the
            # next queued Home operation can post directly from the same
            # derived catalogue address, without weakening the invariant for
            # any other caller.  A final withdrawal gets the ordinary bounded
            # confirmation behavior.
            here = snapshot.grid_at(snapshot.player.position)
            if here is not None and here.store_number == STORE_HOME:
                self.last_reason = (
                    "home:atomic-withdraw-await-confirmation"
                    if self._home_atomic_withdraw_pending is not None
                    else "equipment-transaction:await-confirmation-on-home"
                )
                key = LEAVE_STORE_KEY
        key = self._forbid_wait_on_town_entrance(snapshot, key)
        key = self._suppress_pending_stair_command(snapshot, key)
        self._update_combat_outcome(snapshot)
        self._update_navigation_progress(snapshot)
        if (
            snapshot.store is None
            and self._store_buy_inflight is not None
            and (
                self._town_visit_ledger.pending_store_transaction is None
                or self._town_visit_ledger.pending_store_transaction[0]
                != self._store_buy_inflight[0]
            )
        ):
            # The transaction ledger alone owns the correlation.  Neither a
            # surface decision reason nor player position proves rejection;
            # the store handler confirms or bounds the pending purchase.
            self._store_buy_inflight = None
        if (
            self._equipment_transaction_prepared_key is not None
            and key != self._equipment_transaction_prepared_key
        ):
            self._discard_unposted_equipment_transaction_command()
        if snapshot.store is not None and key == LEAVE_STORE_KEY:
            self._store_leave_inflight = (
                self._decision_sequence,
                getattr(snapshot, "turn", 0),
                snapshot.store.store_type,
            )
            if snapshot.store.store_type == STORE_HOME:
                self._home_knowledge_scan_leave_turn = getattr(snapshot, "turn", 0)
        elif snapshot.store is not None and key not in {WAIT_KEY, "\r"}:
            self._town_visit_ledger.pending_store_transaction = (
                snapshot.store.store_type,
                self._decision_sequence,
            )
            self._town_visit_ledger.pending_store_context_waits = 0
        if (
            snapshot.store is not None
            and snapshot.store.store_type != STORE_HOME
            and key.startswith(BUY_KEY)
            and len(key) > 1
            and self._store_buy_inflight is None
        ):
            bought = next(
                (item for item in snapshot.store.items if item.letter == key[1]),
                None,
            )
            if bought is not None:
                signature = self._item_signature(bought)
                self._store_buy_inflight = (
                    snapshot.store.store_type,
                    signature,
                    self._inventory_signature_count(snapshot, signature),
                    snapshot.player.gold,
                    0,
                    self._decision_sequence,
                )
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and key.startswith(SELL_KEY)
            and len(key) > 1
            and key != self._equipment_transaction_prepared_key
        ):
            deposited = next(
                (item for item in snapshot.inventory if item.slot == key[1]),
                None,
            )
            if deposited is not None:
                # Deposits are additive. Preserve the completed scan that the
                # withdrawal batch is consuming and add the new physical item
                # once, even if the same pre-command snapshot is observed again.
                self._equipment_catalog.record_home_deposit(
                    deposited,
                    intent=(
                        snapshot.turn,
                        deposited.slot,
                        self._item_signature(deposited),
                        deposited.count,
                        deposited.charges,
                        len(snapshot.inventory),
                    ),
                )
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and len(key) > 1
            and key[0] in {BUY_KEY, SELL_KEY}
        ):
            bound_content_update = (
                self._home_atomic_withdraw_pending is not None
                or self._home_atomic_deposit_pending is not None
                or self._equipment_transaction_prepared_catalog_update is not None
                or (
                    key.startswith(SELL_KEY)
                    and any(item.slot == key[1] for item in snapshot.inventory)
                )
            )
            if not bound_content_update:
                self._equipment_catalog.invalidate_home()
            self._home_entry_operation_posted = True
            self._invalidate_home_observation()
        self._capture_home_history_intent(snapshot, key)
        if (
            self._dark_without_recovery(snapshot)
            and self.last_reason != "dark:locomotion-exhausted"
        ):
            # Preserve the chosen action while making the otherwise invisible
            # failure state explicit in JSONL diagnostics.
            self.last_reason = f"dark:no-recovery:{self.last_reason}"
        # The rest counter only survives consecutive rests; anything else clears it.
        if self.last_reason != "rest":
            self._rest_count = 0
        self._last_snapshot_was_store = snapshot.store is not None
        self._last_snapshot_store_type = (
            snapshot.store.store_type if snapshot.store is not None else None
        )
        self._exploration_ledger.marked_high = max(
            self._exploration_ledger.marked_high,
            len(self._remembered_marked_t),
        )
        self._exploration_ledger.note_decision(latest_snapshot)
        return key








    @claims(ClaimOwner.FLOOR_LOOT)
    def _look_probe_key(self, snapshot: Snapshot) -> str:
        self._look_floor_key = snapshot.floor_key
        self._look_floor_items.clear()
        self._look_floor_object_counts = {
            grid.position: grid.object_count
            for grid in snapshot.grids.values()
            if grid.object_count > 0
        }
        self._look_probe_inflight = True
        self.last_reason = "loot:look-floor-items"
        return "l\x1b"

    def _skill_exp_cache_valid(self, snapshot: Snapshot) -> bool:
        """Whether the cached ~f values still describe this character.

        skill_exp only grows through combat (two-weapon blows, shield use),
        which never happens inside a town visit.  The cache is therefore
        invalid when it is empty, when the character level differs from
        the level it was read at, or when the board is in town under a
        different town visit (a new arrival) than the one it was read in.
        """
        cache = getattr(self, "_skill_exp_cache", None)
        if cache is None:
            return False
        _two_weapon, _shield, level, visit_epoch = cache
        if level != snapshot.player.level:
            return False
        current_epoch = getattr(self, "_town_visit_epoch", None)
        return not (
            snapshot.in_town
            and current_epoch is not None
            and current_epoch != visit_epoch
        )

    def with_known_skill_exp(self, snapshot: Snapshot) -> Snapshot:
        """Public: the board as the policy sees it (protocol-3 ~f values filled).

        Telemetry and report paths outside choose_key read this board so
        they agree with the decision; before ~f is read the values stay
        None and every evaluator reports them unknown.
        """
        if not hasattr(self, "_skill_exp_cache"):
            return snapshot
        return self._with_cached_skill_exp(snapshot)

    def _with_cached_skill_exp(self, snapshot: Snapshot) -> Snapshot:
        """Fill protocol-3 two-weapon / shield skill_exp from a valid cache."""
        if getattr(snapshot, "protocol_version", 2) < 3:
            return snapshot
        if not self._skill_exp_cache_valid(snapshot):
            return snapshot
        two_weapon, shield, _level, _epoch = self._skill_exp_cache
        return replace(
            snapshot,
            player=replace(
                snapshot.player, two_weapon_skill=two_weapon, shield_skill=shield
            ),
        )

    @claims(ClaimOwner.BOOKKEEPING)
    def _skill_exp_request_key(self, snapshot: Snapshot) -> str | None:
        """Request ~f while a protocol-3 board lacks the skill list values."""
        if getattr(snapshot, "protocol_version", 2) < 3:
            self._offer_execution_no_step(
                producer="bookkeeping", work_id="skill-exp-knowledge",
                cause="skill-list-protocol-unavailable",
            )
            return None
        if (
            snapshot.player.two_weapon_skill is not None
            and snapshot.player.shield_skill is not None
        ):
            self._offer_execution_done(
                producer="bookkeeping", work_id="skill-exp-knowledge",
                evidence="skill-list-already-known",
            )
            return None
        if any(
            home_page_message_body(message).startswith(WARNING_PROMPT_MESSAGE_PREFIXES)
            for message in snapshot.messages
        ):
            # An open TR_WARNING [y/n] prompt would consume the request keys;
            # its handler (which needs no evaluator) owns this board.
            self._offer_execution_no_step(
                producer="bookkeeping", work_id="skill-exp-knowledge",
                cause="warning-prompt-open",
            )
            return None
        if getattr(self, "_skill_exp_request_inflight", False):
            # The emitter writes the skill list before the viewer opens,
            # so a board after the posted request without it is a
            # protocol defect, not something to retry blindly.
            raise ProtocolSchemaError(
                "the requested ~f skill list did not arrive before the next board"
            )
        self.last_reason = "periodic:skill-exp-knowledge"
        self._offer_execution(
            SKILL_KNOWLEDGE_MACRO, producer="bookkeeping",
            work_id="skill-exp-knowledge", next_step="knowledge.skill-exp.request",
            expected_effect="skill-exp-list-observed",
            continuation="bookkeeping.resume",
        )
        return SKILL_KNOWLEDGE_MACRO

    def consume_skill_knowledge(self, data: Mapping[str, object]) -> None:
        """Cache the ~f skill list (knowledge category skill_exp).

        SKILL_EXP rows are PlayerSkillKindType ids (1 TWO_WEAPON,
        3 SHIELD); ``exp`` is printed only under show_actual_value and is
        capped at the class maximum, as on screen.
        """
        knowledge = data.get("knowledge")
        rows = knowledge.get("skills") if isinstance(knowledge, Mapping) else None
        if not isinstance(rows, list):
            raise ProtocolSchemaError("skill_exp knowledge lacks skills")
        by_id = {
            row.get("id"): row for row in rows if isinstance(row, Mapping)
        }
        values = []
        for skill_id in (1, 3):
            row = by_id.get(skill_id)
            exp = row.get("exp") if row is not None else None
            if isinstance(exp, bool) or not isinstance(exp, int):
                raise ProtocolSchemaError(
                    f"skill_exp knowledge row {skill_id} has no exp; "
                    "the save must enable show_actual_value"
                )
            values.append(exp)
        player = data.get("player")
        level = player.get("level") if isinstance(player, Mapping) else None
        if isinstance(level, bool) or not isinstance(level, int):
            raise ProtocolSchemaError("skill_exp knowledge lacks player.level")
        self._skill_exp_cache = (
            values[0], values[1], level, getattr(self, "_town_visit_epoch", None)
        )
        self._skill_exp_request_inflight = False

    def request_character_dump(self) -> None:
        """Latch a CLI timer request until an ordinary quiet filler decision."""
        self._periodic_dump_requested = True

    def request_game_save(self) -> None:
        """Latch a CLI timer request until an ordinary quiet filler decision."""
        self._periodic_save_requested = True


    @claims(ClaimOwner.BOOKKEEPING)
    def _periodic_game_save_key(self, snapshot: Snapshot, key: str) -> str:
        """Replace a safe filler with Ctrl-S; saving consumes no game energy."""
        if (
            not self._periodic_save_requested
            or key == CHARACTER_DUMP_MACRO
            or not self._periodic_filler_is_safe(snapshot)
        ):
            return key
        self._periodic_save_requested = False
        self.last_reason = "periodic:game-save"
        self._offer_execution(
            "\x13", producer="bookkeeping", work_id="periodic-game-save",
            next_step="game.save.send", expected_effect="game-save-confirmed",
        )
        return "\x13"

    @claims(ClaimOwner.BOOKKEEPING)
    def _periodic_character_dump_key(self, snapshot: Snapshot, key: str) -> str:
        """Replace a safe filler action without delaying combat or prompts."""
        if (
            not self._periodic_dump_requested
            or key == "\x13"
            or not self._periodic_filler_is_safe(snapshot)
        ):
            return key
        self._periodic_dump_requested = False
        self.last_reason = "periodic:character-dump"
        self._prepare_character_sheet_dump()
        self._offer_execution(
            CHARACTER_DUMP_MACRO, producer="bookkeeping",
            work_id="periodic-character-dump", next_step="character.dump.send",
            expected_effect="character-dump-confirmed",
        )
        return CHARACTER_DUMP_MACRO

    def prime(self, snapshot: Snapshot) -> None:
        """Remember a dangerous landing before follow mode begins tailing.

        The launcher uses a separate one-shot process for the first waiting turn.
        Priming lets the long-lived policy retain the safety consequence of that
        decision without sending a duplicate key.
        """
        snapshot = self._with_grid_memory(snapshot)
        self._last_snapshot_was_store = snapshot.store is not None
        self._last_snapshot_store_type = (
            snapshot.store.store_type if snapshot.store is not None else None
        )
        self._observe(snapshot)
        self._build_grid_index(snapshot)
        self._exploration_ledger.marked_high = max(
            self._exploration_ledger.marked_high,
            len(self._remembered_marked_t),
        )
        self._fruitless_disengage_marked_high = (
            self._exploration_ledger.marked_high
        )
        # Save-backed remembered terrain in the launch snapshot may describe the
        # pre-reload layout. Keep it targetable, but label stairs as unverified;
        # rejected commands below will self-heal them without a startup leash.
        self._unverified_stairs = {
            (direction, grid.position)
            for grid in snapshot.grids.values()
            for direction, present in (
                (DOWN_STAIRS_KEY, grid.has_down_stairs),
                (UP_STAIRS_KEY, grid.has_up_stairs),
            )
            if present and grid.position.distance_to(snapshot.player.position) <= 1
        }
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            # resume uses a one-shot policy to kick the waiting turn before the
            # long-lived policy starts. If that turn withdrew Home equipment,
            # reconstruct the pending item from the resulting store snapshot so
            # the fresh policy does not immediately deposit it again.
            # No current Home withdrawal path selects a light, so excluding
            # unknown lights is narrower than the old disposal-based check but
            # unreachable across all withdrawal emitters. When optimizer target
            # knowledge is unavailable, this may conservatively pin equipment
            # that disposal would retain; that mismatch is suppressive only.
            withdrawn = self._first_item(
                snapshot,
                lambda item: self._spare_equipment_deposit_shape(item)
                and not item.known,
            )
            if withdrawn is not None:
                self._home_pending_item = self._item_signature(withdrawn)
                self._home_pending_slot = withdrawn.slot
        if snapshot.in_town:
            # Inventory candidates are not evidence of Home membership.  The
            # identification flow owns them in the pack; only Home-sourced
            # observations may create Home withdrawal claims.
            if self._home_pending_item is not None or self._home_pending_batch:
                self._home_candidate_waiting = False
        treasure_scrolls = self._count_treasure_detection_scrolls(snapshot)
        fundraising_evidence = (
            snapshot.angband_recall_unlocked
            or self._equipped_digging_tool(snapshot) is not None
            or (
                treasure_scrolls >= 2
                and snapshot.player.gold < FUNDRAISING_START_GOLD
            )
            or (treasure_scrolls > 0 and self._has_digging_tool(snapshot))
        )
        if (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and treasure_scrolls >= 2
            and snapshot.player.gold < FUNDRAISING_START_GOLD
        ):
            self._fundraising_mode = "prepare"
        resumable_fundraising_floor = snapshot.dungeon_level == 1
        main_hand_digger = next(
            (
                item
                for item in snapshot.equipment
                if item.slot == "main_hand" and item.is_digging_tool
            ),
            None,
        )
        if (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and resumable_fundraising_floor
            and snapshot.player.class_id >= 0
            and fundraising_evidence
        ):
            self._fundraising_mode = (
                "mine"
                if main_hand_digger is not None
                or (treasure_scrolls > 0 and self._has_digging_tool(snapshot))
                else ("scavenge" if self._detectionless_scavenge_allowed(snapshot)
                      else "prepare")
            )
            if main_hand_digger is not None:
                # A fresh policy cannot remember that treasure detection was
                # already read before the bot restart.  A digger still wielded
                # in the main hand is stronger evidence of an interrupted mining
                # run than the remaining scroll count: resume from the saved
                # known-treasure map instead of downgrading to scavenge or
                # immediately returning for another detection scroll.
                self._mining_scroll_used_floor = snapshot.floor_key
        here = snapshot.grid_at(snapshot.player.position)
        # A fresh process standing on dungeon downstairs may be the follow-mode
        # half of an ascent performed by resume's one-shot process. Conservatively
        # step away and explore before using the same stairs again.
        if (
            here is not None
            and here.has_down_stairs
            and snapshot.dungeon_level > 0
        ):
            self._descent_blocked = True
            self._descent_block_countdown = RESUME_DESCENT_BLOCK_DECISIONS
        if here is None or not here.has_up_stairs:
            return

        hostiles = self._physical_hostiles(snapshot)
        adjacent = self._physical_adjacent_hostiles(snapshot)
        if self._should_flee(snapshot, hostiles, adjacent):
            self._defer_descent(snapshot)

    @claims(ClaimOwner.DETECTORS)
    def _break_livelock(self, snapshot: Snapshot, key: str) -> str:
        """Guard against re-issuing a move the game keeps rejecting.

        A rejected move (walking into a locked door, a blocked diagonal, ...)
        costs no energy, so the game re-emits the same snapshot and we would
        otherwise choose the same key forever. When we notice the player has not
        moved despite repeating a pathing key, force a guaranteed-valid step.
        """
        position = snapshot.player.position
        if (
            self.last_reason in MOVE_REASONS
            and key == self._last_move_key
            and position == self._last_move_pos
            # Opening a door and tunnelling rubble both legitimately repeat the
            # same key while the player stays put, and are already bounded by
            # DOOR_OPEN_LIMIT / RUBBLE_DIG_LIMIT — don't let the livelock guard
            # abort them early.
            and not key.startswith(OPEN_KEY)
            and not key.startswith(TUNNEL_KEY)
        ):
            self._move_repeat += 1
        else:
            self._move_repeat = 0
        self._last_move_key = key
        self._last_move_pos = position

        if self._move_repeat >= LIVELOCK_LIMIT:
            self._move_repeat = 0
            alternate = self._breakout_step(snapshot, key)
            if alternate is not None:
                self.last_reason = "breakout"
                key = self._direction_key(position, alternate)
                self._last_move_key = key
        return key


    def _escape_action_selected(self) -> bool:
        reason = self.last_reason
        return (
            reason.startswith(
                (
                    "emergency:",
                    "flee",
                    "return:",
                    "combat:disengage-",
                    "combat:avoid-unprofitable-unique-",
                    "unseen-recall:",
                )
            )
            or reason in {"status-threat:retreat", "threat:reposition"}
        )






    def _release_invalid_choke_plan(self, snapshot: Snapshot) -> None:
        """Release an active engagement when its defining floor no longer exists."""
        plan = self._choke_engagement_plan
        if (
            plan is not None
            and plan.phase in {"reposition", "validate", "hold"}
            and plan.floor != snapshot.floor_key
        ):
            self._release_choke_plan("floor-change")

    def _required_supply_suppresses_normal_loot(
        self, snapshot: Snapshot
    ) -> bool:
        if not snapshot.in_town:
            return False
        supplier = self._actionable_departure_supplier(snapshot)
        if supplier is None:
            return False
        return not any(
            grid.currently_observed and grid.object_count > 0
            for grid in snapshot.grids.values()
        )

    # -- low-HP walk gate (USER DECISION 2026-10-03 04:0x) -------------------
    # 「低HPのときの優先度を再度確認。特に「危険を確認せず歩行」は最悪手。
    # 普通に死ぬ。」 / 「HP50%と最大HP-300の大きい方を閾値とする」.  Below the
    # threshold, or right after taking damage, no producer's walking move is
    # posted unless it is a flee/reposition step that neither adds adjacent
    # hostiles nor turns away from an adjacent attacker at least as fast.
    # Instead: healing potion -> teleport/recall -> fight the adjacent enemy.
    LOW_HP_CHECKED_STEP_REASONS = frozenset({
        "flee", "no-wait:flee", "status-threat:retreat", "threat:reposition",
        "threat:avoid-engagement", "threat:paralyzer-avoid", "summoner:retreat",
        "combat:disengage-step", "melee:choke-reposition",
        "emergency:seek-upstairs", "emergency:clear-escape-path",
        "unseen-recall:move",
    })

    @staticmethod
    def _low_hp_walk_threshold(max_hp: int) -> float:
        return max(max_hp * LOW_HP_WALK_RATIO, max_hp - LOW_HP_WALK_MARGIN)

    def _low_hp_walk_gate_active(self, snapshot: Snapshot) -> tuple[bool, bool]:
        """(gate active, below the HP threshold).

        追加決定 (10-03 05:0x): 「含めない（閾値未満だけ）」 -- a hit alone
        does not arm the gate."""
        player = snapshot.player
        low = player.hp < self._low_hp_walk_threshold(player.max_hp)
        return low, low

    @claims(ClaimOwner.DETECTORS)
    def _low_hp_no_kit_hit_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Below the threshold with no heal/escape/recall and nothing adjacent,
        after a hit (追加決定2, 10-03 05:1x): 「近接で敵の方向が分からなければ
        ランダムな方向に攻撃。遠距離で射線が切れなければ遮蔽と敵のうち近い方に
        移動。」  Melee by an unseen attacker: attack a direction with the
        alter command (do_cmd_alter attacks a monster there, seen or not).
        Ranged: one step out of the line of fire, not next to a hostile; else
        toward the nearer of cover and the attacker."""
        if (
            not getattr(self, "_took_damage", False)
            or getattr(self, "_took_curse_damage", False)
            or getattr(self, "_took_trap_or_terrain_damage", False)
        ):
            return None
        player = snapshot.player
        here = player.position
        messages = [re.sub(r" <x[1-9]\d*>$", "", m) for m in snapshot.messages]
        unseen = [m for m in messages if self._is_unseen_attack_message(m)]
        named_shooters = [
            monster for monster in hostiles
            if monster.name
            and any(
                m.startswith(monster.name) and self._is_unseen_spell_message(m)
                for m in messages
            )
        ]
        melee = [m for m in unseen if not self._is_unseen_spell_message(m)]
        ranged = [m for m in unseen if self._is_unseen_spell_message(m)]
        if melee:
            cells = sorted(
                (
                    Position(here.y + dy, here.x + dx)
                    for dy, dx in DIRECTION_KEYS
                ),
                key=lambda cell: (cell.y, cell.x),
            )
            candidates = [
                cell for cell in cells
                if (grid := snapshot.grid_at(cell)) is not None
                and grid.passable
                and not grid.is_door
                and not any(m.position == cell for m in hostiles)
            ]
            if candidates:
                cell = random.Random(snapshot.turn).choice(candidates)
                self.last_reason = "no-wait:attack"
                return ALTER_KEY + self._direction_key(here, cell)
            return None
        if not (ranged or named_shooters):
            return None

        def exposed_to(cell: Position) -> bool:
            if named_shooters:
                return any(
                    self._has_line_of_fire(snapshot, m.position, cell)
                    for m in named_shooters
                )
            # The attacker's square is unknown: a choke square is the cover.
            return self._open_neighbor_count(snapshot, cell) > (
                SUMMONER_CHOKE_NEIGHBORS - 1
            )

        def next_to_hostile(cell: Position) -> bool:
            return any(m.position.distance_to(cell) <= 1 for m in hostiles)

        neighbors = [
            cell for cell in self._walkable_neighbors(snapshot, here)
            if not next_to_hostile(cell)
        ]
        for cell in neighbors:
            if not exposed_to(cell):
                self.last_reason = "no-wait:flee"
                return self._direction_key(here, cell)
        # Nearest cover by walking distance, against the nearest attacker.
        queue = deque((cell, cell, 1) for cell in neighbors)
        seen = {here, *neighbors}
        cover = None
        while queue:
            cell, first, depth = queue.popleft()
            if not exposed_to(cell):
                cover = (depth, first)
                break
            for neighbor in self._walkable_neighbors(snapshot, cell):
                if neighbor not in seen and not next_to_hostile(neighbor):
                    seen.add(neighbor)
                    queue.append((neighbor, first, depth + 1))
        enemy = min(
            named_shooters, key=lambda m: m.position.distance_to(here), default=None
        )
        if enemy is not None and (
            cover is None or enemy.position.distance_to(here) <= cover[0]
        ):
            self.last_reason = "no-wait:flee"
            return self._direction_key(here, enemy.position)
        if cover is not None:
            self.last_reason = "no-wait:flee"
            return self._direction_key(here, cover[1])
        return None

    def _walk_step_target(self, snapshot: Snapshot, key: str | None) -> Position | None:
        if not key:
            return None
        direction = key[1:] if key[0] in (OPEN_KEY, TUNNEL_KEY) else key
        delta = next(
            (offset for offset, value in DIRECTION_KEYS.items() if value == direction),
            None,
        )
        if delta is None:
            return None
        here = snapshot.player.position
        return Position(here.y + delta[0], here.x + delta[1])

    def _low_hp_walk_gate(self, snapshot: Snapshot, key: str | None) -> str | None:
        if (
            snapshot.in_town
            or snapshot.store is not None
            or self._on_global_wilderness_map(snapshot)
        ):
            return key
        target = self._walk_step_target(snapshot, key)
        if target is None:
            return key
        active, low = self._low_hp_walk_gate_active(snapshot)
        if not active:
            return key
        player = snapshot.player
        hostiles = [m for m in snapshot.visible_monsters if m.hostile]
        if key in DIRECTION_KEYS.values() and any(
            monster.position == target for monster in hostiles
        ):
            return key  # an attack, not a walk
        adjacent = [
            m for m in hostiles if m.position.distance_to(player.position) <= 1
        ]
        if (
            key in DIRECTION_KEYS.values()
            and self.last_reason in self.LOW_HP_CHECKED_STEP_REASONS
            and len([
                m for m in hostiles if m.position.distance_to(target) <= 1
            ]) <= len(adjacent)
            and not any(m.speed >= player.speed for m in adjacent)
        ):
            return key
        if low:
            threatened = bool(hostiles) or bool(
                [m for m in snapshot.detected_monsters if m.hostile]
            ) or getattr(self, "_took_damage", False)
            # USER DECISION 2026-10-03 06:0x (heal-vs-teleport): with an enemy
            # about, heal first only with a potion whose heal is at least the
            # next turn's predicted damage; otherwise teleport/recall first.
            potion = (
                self._low_hp_heal_first_potion(snapshot, hostiles)
                if threatened
                else self._find_heal_potion(snapshot, expected_damage=1)
            )
            if potion is not None:
                self.last_reason = "item:heal"
                return QUAFF_KEY + potion.slot
            scroll = self._escape_scroll(snapshot) if threatened else None
            if scroll is not None:
                return self._issue_emergency_consumable(
                    snapshot, scroll,
                    "emergency:teleport" if scroll.is_teleport_scroll
                    else "emergency:phase",
                )
            if (
                not player.recalling
                and not self._quest_floor_exit_locked(snapshot)
                and self._can_read_scrolls(snapshot)
            ):
                recall = self._find_recall_scroll(snapshot)
                if recall is not None:
                    return self._issue_emergency_consumable(
                        snapshot, recall, "emergency:recall"
                    )
            # No escape: the heal that loses to the next turn still beats a walk.
            potion = self._find_heal_potion(snapshot, expected_damage=1)
            if potion is not None:
                self.last_reason = "item:heal"
                return QUAFF_KEY + potion.slot
        if adjacent and not player.afraid:
            self.last_reason = "melee"
            return self._direction_key(
                player.position, self._weakest(adjacent).position
            )
        if low:
            answer = self._low_hp_no_kit_hit_key(snapshot, hostiles)
            if answer is not None:
                return answer
        if (
            not hostiles
            and not getattr(self, "_took_damage", False)
            and not player.poisoned
            and not player.cut
            and not player.confused
            and player.food_state in {"normal", "full", "gorged"}
        ):
            self.last_reason = "rest"
            return REST_MACRO
        self.last_reason = "emergency:wait"
        return WAIT_KEY

    def _decide(self, snapshot: Snapshot) -> str:
        self._evaluate_cross_decision_latches(snapshot)
        # Diagnostic: describes this decision's rest check only.
        self._esp_threat_assessment = None
        if (snapshot.in_town and self._home_errand.needs_knowledge
                and self._home_atomic_deposit_pending is None
                and self._home_atomic_withdraw_pending is None
                and snapshot.player.hp >= snapshot.player.max_hp
                and not (snapshot.player.poisoned or snapshot.player.cut
                         or snapshot.player.confused or snapshot.player.blind)
                and snapshot.player.food_state in {"normal", "full", "gorged"}
                and not self._physical_hostiles(snapshot)):
            knowledge_key = self._town_producer_entry(
                "home-errand-knowledge", lambda: self._home_errand_knowledge_key(snapshot),
                family="home-errand")
            if knowledge_key is not None:
                return knowledge_key
        if (snapshot.in_town and snapshot.store is None
                and self._home_atomic_deposit_pending is not None
                and self._store_visit is not None
                and self._store_visit.store_type == STORE_HOME
                and self._store_visit.operation_posted
                and self._store_visit.operation_released
                and self._store_visit.operation_producer_family == "home-visit"
                and snapshot.player.hp >= snapshot.player.max_hp
                and not (snapshot.player.poisoned or snapshot.player.cut
                         or snapshot.player.confused or snapshot.player.blind)
                and snapshot.player.food_state in {"normal", "full", "gorged"}
                and not self._physical_hostiles(snapshot)):
            # A released legacy deposit still owns its outside observation
            # budget. Do not enqueue an equipment Home visit before it ends.
            self.last_reason = "home:atomic-deposit-await-confirmation"
            self._offer_execution(
                WAIT_KEY, producer="home-visit",
                work_id=f"home-operation:{self._store_visit.opened_sequence}:{self._store_visit.operation_key}",
                next_step="home.operation.observe",
                expected_effect="home-inventory-effect",
                continuation="home.operation.observe",
                budget_ref="home-operation-existing-budget",
            )
            return WAIT_KEY
        if (snapshot.in_town and snapshot.player.hp >= snapshot.player.max_hp
                and not (snapshot.player.poisoned or snapshot.player.cut
                         or snapshot.player.confused or snapshot.player.blind)
                and snapshot.player.food_state in {"normal", "full", "gorged"}
                and not self._physical_hostiles(snapshot)
                and self._home_atomic_deposit_pending is None
                and self._home_atomic_withdraw_pending is None
                and self._store_buy_inflight is None
                and self._batch_sell_pending is None
                and (self._home_full_relief is not None
                     or self._home_full_retry_deposits is not None
                     or self._home_is_full(snapshot))):
            relief_key = self._town_producer_entry("_home_full_relief_key",
                lambda: self._home_full_relief_key(snapshot))
            if relief_key is not None:
                return relief_key
        # Admission of an already-built Home transaction precedes evaluators
        # that may ask whether town departure is ready.  Those evaluators are
        # allowed to build a plan only when no transaction owns the character;
        # rebuilding here would discard its recorded pack-letter continuation.
        admitted_session = self._equipment_transaction_session
        if (
            snapshot.in_town and admitted_session is not None and admitted_session.executable and (admitted_session.required_context == 'home') and (admitted_session.physical_context == 'home') and (self._home_pending_item is None) and (not self._home_pending_batch) and (self._home_atomic_withdraw_pending is None) and any((grid.store_number == STORE_HOME for grid in (snapshot.grid_at(snapshot.player.position),) if grid is not None)) and (snapshot.player.hp >= snapshot.player.max_hp) and (not any((monster.hostile for monster in snapshot.visible_monsters)))
        ):
            return self._town_producer_entry("_equipment_transaction_town_key#1", lambda: self._equipment_transaction_town_key(snapshot)) or WAIT_KEY
        # A TR_WARNING prompt reported by this snapshot is disposed of before
        # any other purpose is pursued: a refused movement is latched so it is
        # not re-chosen (the loop this handler removes), and an unsanctioned
        # tail-answered crossing is latched even when the walk opened a store
        # screen (the handler posts nothing in that case).
        warning_response = self._warning_prompt_response_key(snapshot)
        if warning_response is not None:
            return warning_response
        if self._warning_prompt_stops_decision:
            return None

        # A failed equipment transaction is a visit-local terminal, including
        # on the outside Home snapshot where the failure was discovered.  The
        # store-context guard in choose_key only owns an open/interleaved UI;
        # without this outside guard the ordinary need router can rebuild Home
        # immediately, despite there being no executable transaction to post.
        if (
            snapshot.in_town
            and not self._opening_q34_active(snapshot)
            and (self._town_blocked_reason or "").startswith(
                "equipment-transaction:withdraw-item-unobserved:"
            )
        ):
            return self._town_blocked_key(snapshot)

        # Once a transaction has physically stripped anything, restoration or
        # completion owns every town decision.  No shopping, sale, disposal,
        # fundraising, or errand classifier is reachable until ownership ends.
        if (
            snapshot.in_town
            and self._equipment_transaction_owned_items
            and not self._opening_q34_active(snapshot)
        ):
            return self._town_producer_entry("_equipment_transaction_town_owner_key", lambda: self._equipment_transaction_town_owner_key(snapshot)) or WAIT_KEY

        if snapshot.in_town and self._equipment_transaction_route_terminal is not None:
            self.last_reason = self._equipment_transaction_route_terminal
            return LEAVE_STORE_KEY if snapshot.store is not None else WAIT_KEY

        if (
            snapshot.store is None
            and self._store_visit is not None
            and self._store_visit.operation_posted
            and not self._store_visit.operation_released
            and (
                self._store_visit.store_type != STORE_HOME
                or self._store_visit.phase == StoreVisitPhase.ENTERING
            )
        ):
            # A player-turn at the entrance can be emitted after the leading
            # stay key but before the queued store UI consumes the transaction.
            # The posted macro owns that page just as it owns an intermediate
            # store page; only observed completion or visit closure releases it.
            # That queue is consumed at the entrance the operation was composed
            # on.  A later turn that finds the player somewhere else proves the
            # entry never happened and can never happen, so the wait has no
            # board to wait for; this wait emits no command, and the driver's
            # no-key bound ends the run long before the retry budget below.
            here = snapshot.grid_at(snapshot.player.position)
            posted_turn = self._store_visit.posted_turn
            if (
                posted_turn is not None
                and snapshot.turn > posted_turn
                and (here is None or here.store_number != self._store_visit.store_type)
            ):
                self._close_store_visit("one-shot-entrance-left")
            else:
                self._town_visit_ledger.pending_store_context_waits += 1
                if (
                    self._town_visit_ledger.pending_store_context_waits
                    < STORE_STUCK_LIMIT
                ):
                    self.last_reason = "shop:one-shot-in-flight"
                    return ""
                self._close_store_visit("one-shot-entry-unconfirmed")
        if (
            snapshot.store is None
            and (
                self._store_buy_inflight is not None
                or (
                    self._batch_sell_pending is not None
                    and self._batch_sell_pending.get("phase") == "await-sale"
                )
            )
        ):
            # A legacy/orphaned watch has no visit phase to own this page, but
            # its confirmation budget above remains authoritative.  Do not let
            # ordinary routing create a replacement visit before it resolves.
            self.last_reason = "shop:one-shot-in-flight"
            return ""

        # A town-block latch owns the store exit before ordinary Home/shop page
        # processing. WAIT_KEY is not a valid store command.
        if (
            self._town_blocked_reason is not None
            and self._town_blocked_store_context(snapshot)
            and not self._town_blocked_entrance_has_composable_operation(snapshot)
            and not (
                self._town_blocked_reason == "repetition"
                and snapshot.store is not None
                and self._store_visit is not None
                and self._store_visit.operation_posted
            )
        ):
            key = self._town_blocked_key(snapshot)
            if snapshot.store is not None:
                self._record_shop_selector_diagnostics(snapshot, key)
            return key

        # In a store the town map and monsters are irrelevant — only buy/leave.
        if snapshot.store is not None:
            if (
                snapshot.store.store_type != STORE_HOME
                and self._store_visit is not None
                and not self._store_visit.operation_posted
                and len(snapshot.inventory) < PACK_CAPACITY
            ):
                ordered = self._town_producer_entry("_town_order_step4_key#1", lambda: self._town_order_step4_key(snapshot))
                if ordered is not None:
                    return ordered
            if snapshot.store.store_type != STORE_HOME:
                self._town_supplier_stock[snapshot.store.store_type] = snapshot.store
                self._town_supplier_stock_observations[snapshot.store.store_type] = (
                    self._effective_town_id(snapshot),
                    snapshot.turn,
                )
                self._observe_restock_supplier_page(snapshot)
                self._in_store_best_effort("_observe_shelf_evidence", snapshot)
                if self._start_unobtainable_recall_stockout_mining(snapshot):
                    self.last_reason = "town:recall-stockout-mining"
                    self._offer_execution(
                        LEAVE_STORE_KEY, producer="fundraising",
                        work_id="fundraising:recall-stockout",
                        next_step="store.leave.send",
                        arguments=(snapshot.store.store_type,),
                        expected_effect="outside-store",
                    )
                    return LEAVE_STORE_KEY
            if snapshot.store.store_type != STORE_HOME:
                # An entry that already emitted an in-store operation continues
                # in the store or leaves; it never mixes with the one-shot
                # path (SOL-DESIGN-store-reentry-20261003 3.1).
                in_store_key = self._in_store_entry_key(snapshot)
                if in_store_key is not None:
                    return in_store_key
            visit = self._store_visit
            staged_operation = self._release_staged_store_operation(snapshot)
            if staged_operation is not None:
                # Selection and composition happened on the preceding outside
                # page.  This page makes no policy choice: it only proves that
                # this exact visit crossed the entry flush, so the sender may
                # release the already-bound operation tail.
                self.last_reason = (
                    "shop:one-shot-buy"
                    if staged_operation.startswith(BUY_KEY)
                    else "shop:one-shot-sell"
                )
                if snapshot.store.store_type != STORE_HOME:
                    self._in_store_best_effort("_in_store_shadow_agreement", snapshot, staged_operation)
                return staged_operation
            if (
                (self._store_visit is not None
                 and self._store_visit.operation_posted
                 and (not getattr(self, "_town_claim_bar_enforced", False)
                      or not self._store_visit.operation_released))
                or self._store_buy_inflight is not None
                or (
                    self._batch_sell_pending is not None
                    and self._batch_sell_pending.get("phase") == "await-sale"
                )
            ):
                # The already-posted one-shot owns these intermediate pages.
                # Its queued tail is the only input; policy contributes none.
                self.last_reason = "shop:one-shot-in-flight"
                return ""
            if snapshot.store.store_type != STORE_HOME:
                # Phase 0 shadow (pure), then Phase 1 when switched on.
                self._in_store_best_effort("_in_store_shadow", snapshot)
                in_store_key = self._in_store_try_start(snapshot)
                if in_store_key is not None:
                    return in_store_key
            # Observation visit: never select or answer an item prompt here.
            self._shop_observation = (snapshot.store, self._decision_sequence)
            self.last_reason = "shop:observe-and-leave"
            key = LEAVE_STORE_KEY
            self._offer_execution(
                key, producer="shop-buy", work_id="shop:observe-shelf",
                next_step="store.leave.send",
                arguments=(snapshot.store.store_type,),
                expected_effect="outside-store",
            )
            self._record_shop_selector_diagnostics(snapshot, key)
            return key

        self._build_grid_index(snapshot)
        self._refresh_warning_avoidance(snapshot)
        giveup_plan = self._choke_engagement_plan
        if (
            giveup_plan is not None
            and giveup_plan.floor == snapshot.floor_key
            and giveup_plan.release_cause in {
                "immobile-breeder-growth",
                "breeder-outcome-bound",
            }
        ):
            self._claim_engagement_avoid_cells([
                *giveup_plan.trigger_last_seen.values(),
                *(
                    monster.position
                    for monster in self._engagement_breeder_population(snapshot)
                ),
            ])
            if any(
                step in self._engagement_avoid_cells
                for step in self._explore_path
            ):
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
        player = snapshot.player
        strategic_hostiles = self._strategic_hostiles(snapshot)
        strategic_adjacent = self._strategic_adjacent_hostiles(snapshot)
        physical_hostiles = self._physical_hostiles(snapshot)
        physical_adjacent = self._physical_adjacent_hostiles(snapshot)
        paralyzers = self._refresh_paralyzer_avoidance(
            snapshot, physical_hostiles
        )
        self._observe_navigation_commitments(snapshot)
        # The global map is a distinct command space.  Town/store owners can
        # retain durable work while crossing it, but their travel, shopping,
        # repetition, and fundraising commands are not valid here.  Route or
        # enter the town before allowing any of those owners to select again.
        if self._on_global_wilderness_map(snapshot):
            return self._wilderness_survival_key(snapshot, physical_hostiles)
        self._update_mining_combat_streaks(
            snapshot, physical_hostiles, physical_adjacent
        )
        profile = self.approved_quest_strategy(snapshot.floor_key[2])

        self._latch_unviable_quest_return(snapshot, strategic_hostiles)

        # 0. Emergency consumables (teleport out / heal up / eat before fainting).
        # Emergency material-threat spending deliberately stays strategic. A
        # suppressed weak breeder must not re-arm emergency return after a
        # teleport; disabling blows are covered by the physical status rung.
        emergency_hostiles = (
            self._quest_strategy_emergency_hostiles(
                snapshot, profile, strategic_hostiles
            )
            if profile is not None
            else strategic_hostiles
        )
        # A committed STRONG-tier hunt (esp-threat-rest) owns its fight,
        # including Healing drinks, ahead of the emergency/flee ladder.
        esp_threat_hunt = self._town_producer_entry("_esp_threat_hunt_key", lambda: self._esp_threat_hunt_key(
            snapshot, strategic_hostiles
        ))
        if esp_threat_hunt is not None:
            return esp_threat_hunt
        summoner_ranged = self._town_producer_entry("_summoner_ranged_kill_key", lambda: self._summoner_ranged_kill_key(
            snapshot, emergency_hostiles
        ))
        if summoner_ranged is not None:
            return summoner_ranged
        emergency = self._town_producer_entry("_emergency_item", lambda: self._emergency_item(snapshot, emergency_hostiles))
        if emergency is not None:
            if self._choke_plan_active(snapshot):
                self._release_choke_plan("hp-emergency")
            if self.last_reason.startswith(
                ("emergency:", "unseen-recall:", "guardian:")
            ):
                # Survival may always pre-empt a lower-priority owner.
                self._escape_state.enter("emergency", self.last_reason)
            # Record-only: the hostiles the emergency ladder weighed.
            self._declare_triggers(emergency_hostiles)
            return emergency
        if self._escape_state.owner == "emergency":
            # The emergency ladder is exempt from sibling hysteresis: the
            # established post-teleport handoff must happen immediately.
            self._escape_state.release()

        mana_survival = self._town_producer_entry("_mana_food_survival_override_key", lambda: self._mana_food_survival_override_key(snapshot))
        if mana_survival is not None:
            return mana_survival

        paralyzer_prevention = self._town_producer_entry("_paralyzer_prevention_key", lambda: self._paralyzer_prevention_key(
            snapshot, paralyzers, physical_adjacent
        ))
        if paralyzer_prevention is not None:
            return paralyzer_prevention

        unseen_intercept = self._town_producer_entry("_unseen_retreat_intercept_key", lambda: self._unseen_retreat_intercept_key(
            snapshot, physical_hostiles, physical_adjacent
        ))
        unseen_action = unseen_intercept
        if unseen_action is None:
            unseen_action = self._town_producer_entry("_unseen_retreat_key", lambda: self._unseen_retreat_key(
                snapshot, physical_hostiles
            ))
        detected_preparation = None
        if unseen_action is None:
            detected_preparation = (
                None
                if self._claim_bar_skips(snapshot, "_detected_threat_preparation_key")
                else self._town_producer_entry("_detected_threat_preparation_key", lambda: self._detected_threat_preparation_key(
                    snapshot, physical_hostiles
                ))
            )
        contested_action = unseen_action or detected_preparation
        if contested_action is not None:
            # An ordinary or already-latched town return owns this contested
            # decision. Keep unseen retreat above anticipatory detected-threat
            # preparation when no return would act, without promoting return
            # above unrelated gates.
            town_return = (
                None
                if self._escape_state.owner not in {None, "return", "unseen"}
                else self._town_producer_entry("_return_to_town_key#1", lambda: self._return_to_town_key(snapshot, strategic_hostiles))
            )
            if town_return is not None:
                return town_return
            return contested_action

        # Player light radius >= 1 always gives CAVE_LITE to the player's own
        # square (cave-map.cpp update_lite); a non-blind player whose own square
        # is not lit therefore has radius zero. In darkness note_spot records
        # nothing (grid.cpp), so repair the light before combat/mining/navigation.
        darkness_recovery = self._darkness_recovery_key(snapshot)
        if darkness_recovery is not None:
            return darkness_recovery
        dark_locomotion = self._town_producer_entry("_dark_locomotion_key", lambda: self._dark_locomotion_key(snapshot))
        if dark_locomotion is not None:
            return dark_locomotion

        opening_q34 = self._opening_q34_town_key(snapshot, strategic_hostiles)
        if opening_q34 is not None:
            return opening_q34

        if (
            self._breakout_dig_floor is not None
            and (
                snapshot.floor_key != self._breakout_dig_floor
                or self._dig_to_known_downstairs_key(snapshot) is None
            )
        ):
            restore = self._town_producer_entry("_breakout_restore_weapon_key#1", lambda: self._breakout_restore_weapon_key(snapshot))
            if restore is not None:
                return restore

        if profile is not None:
            # Approved-floor survival remains above the navigator. Keeping this
            # scoped to the quest branch preserves byte-for-byte dispatch order
            # on every non-quest floor.
            survival = self._town_producer_entry("_survival_gate_key#1", lambda: self._survival_gate_key(snapshot, physical_hostiles))
            if survival is not None:
                return survival
            # Approved quest navigation owns the whole floor and returns before
            # the ordinary light-maintenance block below. Refill during a quiet
            # turn so a long fixed-map sweep cannot consume every remaining turn
            # of lantern fuel while oil is already in the pack.
            if not physical_hostiles and not player.confused:
                refill = self._light_refill_item(snapshot)
                if refill is not None:
                    self.last_reason = "refill-light"
                    return REFILL_KEY + refill.slot
            info = self._quest_knowledge.get(profile.quest_id)
            if info is None or info.battlefield is None:
                self.last_reason = "quest:blocked:enter"
                return WAIT_KEY
            navigator = self._quest_navigators.setdefault(
                profile.quest_id,
                QuestFloorNavigator(profile.quest_id, info.battlefield),
            )
            quest = snapshot.quests.get(profile.quest_id)
            if (
                quest is not None
                and quest.status == QUEST_STATUS_COMPLETED
                and not strategic_hostiles
            ):
                # Fixed-quest sweep would otherwise treat a chest as generic
                # loot and carry it out unopened. Process it on this floor so
                # only Chest::open() contents enter the pack.
                chest = self._town_producer_entry("_chest_processing_key#1", lambda: self._chest_processing_key(
                    snapshot,
                    physical_hostiles,
                    allowed_positions={Q34_WOODEN_CHEST_POSITION}
                    if profile.quest_id == 34
                    else None,
                ))
                if chest is not None:
                    return chest
            return self._town_producer_entry("navigator.decide", lambda: navigator.decide(
                self, snapshot, strategic_hostiles, strategic_adjacent
            ))

        # A reviewed one-shot quest is entered on the assumption that its carried
        # Speed dose is part of the action-economy budget.  Spend it on first
        # contact, once for this floor entry (a rejected command is not looped).
        active_quest = self._active_fixed_quest_id(snapshot) or self._active_kill_quest_id(snapshot)
        if (
            active_quest is not None
            and self.approved_quest_strategy(active_quest) is None
            and strategic_hostiles
            and self._unviable_quest_floor != snapshot.floor_key
            and not self._fixed_quest_speed_attempted
        ):
            self._fixed_quest_speed_attempted = True
            speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
            if speed is not None:
                self.last_reason = "quest:quaff-speed"
                return QUAFF_KEY + speed.slot

        # 0a. Open wilderness = a non-town surface tile the town routine strayed
        #     onto by crossing a map border. It spawns out-of-depth monsters (a
        #     Cyclops killed a clvl-4 bot here). Survival is the ONLY goal: flee,
        #     recall to safety, never shop/explore/fight for XP.
        if snapshot.on_open_wilderness:
            return self._wilderness_survival_key(snapshot, physical_hostiles)

        # Town is cleared before errands resume.  Unlike dungeon hunting this is
        # deliberately unconditional: every visible non-pet monster is a target,
        # regardless of friendliness, strength, range, or the hostile-count cap.
        town_kill = self._town_producer_entry("_town_kill_mob_key", lambda: self._town_kill_mob_key(snapshot))
        if town_kill is not None:
            return town_kill

        # 0b. Ride out confusion in a safe spot rather than stumbling randomly.
        if player.confused and not physical_hostiles:
            self.last_reason = "confused:wait"
            return WAIT_KEY

        if (
            self._choke_plan_active(snapshot)
            and self._breeder_breakthrough_floor == snapshot.floor_key
        ):
            self._release_choke_plan("breeder-breakthrough")
        breakthrough = (
            None
            if self._claim_bar_skips(snapshot, "_breeder_breakthrough_key")
            else self._town_producer_entry("_breeder_breakthrough_key", lambda: self._breeder_breakthrough_key(
                snapshot, strategic_hostiles
            ))
        )
        if breakthrough is not None:
            if self._choke_plan_active(snapshot):
                self._release_choke_plan("breeder-breakthrough")
            self._declare_triggers(strategic_hostiles)  # record-only
            return breakthrough

        choke_plan = (
            None
            if self._claim_bar_skips(snapshot, "_choke_engagement_key")
            else self._town_producer_entry("_choke_engagement_key", lambda: self._choke_engagement_key(
                snapshot, physical_hostiles, physical_adjacent
            ))
        )
        if choke_plan is not None:
            return choke_plan

        breeders = [
            monster for monster in strategic_hostiles if monster.can_multiply
        ]
        if (
            breeders
            and self._breeder_breakthrough_floor != snapshot.floor_key
        ):
            breeder_adjacent = [
                monster for monster in strategic_adjacent if monster.can_multiply
            ]
            ranged = self._town_producer_entry("_ranged_attack_key#1", lambda: self._ranged_attack_key(
                snapshot, breeders, breeder_adjacent
            ))
            if ranged is not None:
                return ranged

        # A fruitless breeder engagement latches this floor visit. Keep this
        # ahead of ordinary combat so the same cluster cannot pull us back in.
        disengage = None
        if not self._productive_choke_hold(snapshot):
            disengage = self._town_producer_entry("_fruitless_disengage_key", lambda: self._fruitless_disengage_key(
                snapshot, strategic_hostiles
            ))
        if disengage is not None:
            self._declare_triggers(strategic_hostiles)  # record-only
            return disengage
        if self._escape_state.owner == "disengage":
            self._escape_state.stable_decisions += 1
            if self._escape_state.stable_decisions >= 2:
                self._escape_state.release()

        # A harmless but extremely durable unique can otherwise fall through
        # the consumable projection and into ordinary melee forever.  Arm a
        # floor-level disengage while it is visible; the latch survives BLINK
        # and TELEPORT interruptions that reset the contiguous combat tracker.
        unprofitable_unique = self._unprofitable_unique_disengage_key(
            snapshot, strategic_hostiles
        )
        if unprofitable_unique is not None:
            return unprofitable_unique

        if (
            self._fundraising_mode in {"mine", "scavenge"}
            and self._breeder_breakthrough_floor == snapshot.floor_key
        ):
            combat_equip = self._fundraising_combat_equipment_key(
                snapshot, physical_hostiles
            )
            if combat_equip is not None:
                return combat_equip
            key = self._finish_mining_floor(snapshot)
            if (
                key != WAIT_KEY
                or self.last_reason != "fundraise:upstairs-not-found"
            ):
                return key
            # The fundraising exit ran out of actions: its terminal WAIT is
            # absorbing (no recall to wait on, no reachable stairs, nothing
            # to explore, wander, or dig — nothing external changes it).  The
            # extermination-impossible latch owns leaving, so fall back to
            # the breakthrough's own exits: through-the-swarm routing to a
            # remembered up-stairs, else to the nearest live frontier.  With
            # neither, fall through to the ordinary navigation ladder like
            # the non-mining exhausted floor.
            escape = (
                None
                if self._claim_bar_skips(snapshot, "_breeder_breakthrough_escape_key")
                else self._town_producer_entry("_breeder_breakthrough_escape_key", lambda: self._breeder_breakthrough_escape_key(snapshot))
            )
            if escape is not None:
                return escape

        # Mining/swarm contact has a deliberately ordered combat transition.
        # Keep the diggers on while a missile can repel the approach; once
        # contact persists, re-arm before any ordinary melee decision.
        mining_hostiles = (
            physical_hostiles
            if self._fundraising_mode in {"mine", "scavenge"}
            else strategic_hostiles
        )
        mining_adjacent = (
            physical_adjacent
            if self._fundraising_mode in {"mine", "scavenge"}
            else strategic_adjacent
        )
        swarm_combat = self._town_producer_entry("_melee_swarm_combat_key", lambda: self._melee_swarm_combat_key(
            snapshot, mining_hostiles, mining_adjacent
        ))
        if swarm_combat is not None:
            return swarm_combat

        # 1. Survival: flee when hurt, swarmed, or too afraid to fight back.
        # Once a confusion/paralysis attacker has triggered this rung on the
        # floor, it stays a threat while it can reach us: a one-step retreat
        # (or a speed potion) pushes it just outside its 3-turn reach, and
        # the ordinary ladder then fired at / meleed it until it closed again
        # (Castle 20F 2026-10-02 13:10:57-13:11:05, ピンク・ホラー: retreat at
        # path distance 3, ranged:fire-target at 4, alternating).
        latch = getattr(self, "_status_threat_latch", None)
        latched = (
            latch[1] if latch is not None and latch[0] == snapshot.floor_key
            else frozenset()
        )
        status_threats = self._unresisted_melee_status_threats(
            snapshot, physical_hostiles, latched=latched
        )
        if physical_adjacent and not any(
            monster.distance <= 1 for monster in status_threats
        ) and status_threats and all(
            any(
                blow.effect == "PARALYZE"
                for blow in self._monrace_knowledge[monster.race_id].blows
            )
            for monster in status_threats
        ):
            # Finish the fight already in contact; a merely approaching status
            # monster must not pull us away from a different adjacent enemy.
            status_threats = []
        if status_threats:
            self._status_threat_latch = (
                snapshot.floor_key,
                latched | {
                    (monster.index, monster.race_id) for monster in status_threats
                },
            )
            escape = self._escape_by_stairs(snapshot)
            if escape is not None:
                self.last_reason = "status-threat:stairs"
                return escape
            # Once a confusion/paralysis attacker is adjacent, taking a normal
            # retreat step donates the disabling blow.  Relocate before it lands.
            if (
                any(monster.distance <= 1 for monster in status_threats)
                and not player.blind
                and not player.confused
            ):
                scroll = self._escape_scroll(snapshot)
                if scroll is not None:
                    self.last_reason = "status-threat:scroll"
                    return self._read_key(snapshot, scroll)
            step = self._town_producer_entry("_flee_step#1", lambda: self._flee_step(snapshot, status_threats))
            if step is not None:
                # Make the retreat a persistent navigation veto for this floor.
                # Otherwise fundraising/exploration immediately re-enters the
                # disabling monster's melee ring and alternates forever against
                # a stationary confusion/paralysis monster (notably Floating Eye).
                # Remember the whole visible adjacency ring rather than only the
                # cell we happened to retreat from: loot routing can approach the
                # same unsafe drop from several different directions.
                for threat in status_threats:
                    self._claim_engagement_avoid_cells(
                        grid.position
                        for grid in snapshot.grids.values()
                        if grid.position.distance_to(threat.position) <= 1
                    )
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
                self.last_reason = "status-threat:retreat"
                self._declare_reach(step, note=CLAIM_GOAL_NOTE_ONE_STEP)
                return self._step_toward(snapshot, step)
            if not player.blind and not player.confused:
                scroll = self._escape_scroll(snapshot)
                if scroll is not None:
                    self.last_reason = "status-threat:scroll"
                    return self._read_key(snapshot, scroll)
            self.last_reason = "status-threat:wait"
            return WAIT_KEY

        # Ordinary flee deliberately stays strategic: once weak-breeder
        # extermination is impossible, their mere presence must not turn the
        # approved walk-out into flight. Physical status and escape hazards are
        # handled by the dedicated rungs above.
        if self._should_flee(
            snapshot, strategic_hostiles, strategic_adjacent
        ):
            # Record-only: every exit of this rung is escape, fleeing these.
            self._declare_triggers(strategic_hostiles, family="escape")
            escape = self._escape_by_stairs(snapshot)
            if escape is not None:
                self.last_reason = (
                    "flee:stairs-quest-fail"
                    if self._quest_exit_would_fail(snapshot)
                    else "flee:stairs"
                )
                return escape
            if (
                (
                    self._fruitless_disengage_floor == snapshot.floor_key
                    or self._returning_to_town
                    or self._escape_state.owner in {"disengage", "return"}
                )
                and (
                    blocker := self._town_producer_entry("_blocking_escape_melee_key", lambda: self._blocking_escape_melee_key(
                        snapshot, physical_hostiles, self._is_upstairs_target
                    ))
                )
                is not None
            ):
                # A declared walk-out must keep moving toward its known exit at
                # low HP too. One projected-easy corridor kill is safer than the
                # generic flee rung retreating back into the floor.
                self.last_reason = "combat:disengage-clear-path"
                return blocker
            step = self._town_producer_entry("_flee_step#2", lambda: self._flee_step(snapshot, strategic_hostiles))
            if step is not None:
                # A survival flee can pre-empt the material-threat gate below
                # (notably for an over-level monster).  Persist the abandoned
                # square here as well, otherwise a remembered loot target can
                # immediately route back into it when the monster flickers out
                # of view, producing a seek-loot/flee two-cell oscillation.
                if self._predicted_damage(
                    snapshot, strategic_hostiles, turns=3
                ) >= (
                    player.hp * ENGAGEMENT_AVOID_DAMAGE_RATIO
                ):
                    self._claim_engagement_avoid_cells(
                        (snapshot.player.position,)
                    )
                    self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
                self.last_reason = "flee"
                return self._step_toward(snapshot, step)
            # Cornered: try a relocation scroll before anything desperate.
            scroll = self._escape_scroll(snapshot)
            if scroll is not None:
                self.last_reason = "flee:scroll"
                return self._read_key(snapshot, scroll)
            if strategic_adjacent and not player.afraid:
                self.last_reason = "flee:cornered-attack"
                return self._town_producer_entry("_direction_key#1", lambda: self._direction_key(
                    player.position, self._weakest(strategic_adjacent).position
                ))
            self.last_reason = "flee:wait"
            return WAIT_KEY

        # A summoner with room around the player can turn a manageable fight into
        # an irreversible surround. Leave open terrain before engaging, ideally
        # breaking into a corridor where only a few monsters can reach us. But an
        # ALREADY-ADJACENT summoner is past that point: walking away just donates
        # free hits every step (and a faster summoner stays adjacent the whole
        # way) — kill it instead; melee below already targets summoners first.
        summoners = [
            monster for monster in strategic_hostiles
            if monster.can_summon and not monster.asleep
        ]
        # A KILL_NUMBER pack gets the same reviewed choke-point movement as a
        # summoner fight.  The normal ranged phase below then softens pursuers.
        corridor_threats = summoners
        if summoners and self._active_kill_quest_id(snapshot) is not None:
            corridor_threats = strategic_hostiles
        summoner_adjacent = any(
            player.position.distance_to(monster.position) <= 1 for monster in corridor_threats
        )
        if (
            corridor_threats
            and not summoner_adjacent
            and self._open_neighbor_count(snapshot, player.position)
            >= SUMMONER_EXPOSED_NEIGHBORS
            and not any(
                (shots := self._summoner_shots_to_kill(snapshot, monster))
                is not None and shots <= SUMMONER_RANGED_KILL_SHOTS
                and self._summoner_ranged_attack_available(snapshot, monster)
                for monster in summoners
            )
        ):
            current = snapshot.grid_at(player.position)
            if current is not None and self._is_upstairs_target(current) and not self._quest_floor_exit_locked(snapshot):
                self._defer_descent(snapshot)
                self.last_reason = (
                    "summoner:stairs-quest-fail"
                    if self._quest_exit_would_fail(snapshot)
                    else "summoner:stairs"
                )
                self._declare_triggers(corridor_threats)  # record-only
                return UP_STAIRS_KEY
            step = self._summoner_retreat_step(
                snapshot, corridor_threats, strategic_hostiles
            )
            if step is not None:
                # The same navigation veto as the flee / threat:reposition
                # retreats: persist the abandoned (exposed, in-view) square.
                # One step later the summoner is out of view, the retreat
                # rung falls silent, and a remembered loot target routed
                # straight back into this square -- summoner:retreat '3' /
                # seek-loot '7' between (23,115)/(24,116) until the loop
                # detector stopped the bot (Castle 20F, 2026-10-02 15:14-15:16).
                self._claim_engagement_avoid_cells((snapshot.player.position,))
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
                self.last_reason = "summoner:retreat"
                return self._step_toward(snapshot, step)

        combat_equip = self._fundraising_combat_equipment_key(
            snapshot, mining_hostiles
        )
        if combat_equip is not None:
            return combat_equip

        # With no approved fixed-map profile, a visible runtime quest race owns
        # ordinary combat selection after all emergency/flee/reposition gates.
        quest_targets = self._locked_kill_quest_targets(
            snapshot, strategic_hostiles
        )
        combat_hostiles = quest_targets or strategic_hostiles
        combat_adjacent = [
            monster
            for monster in strategic_adjacent
            if monster in combat_hostiles
        ]

        # 2. Melee an adjacent hostile (weakest first) — unless too afraid.
        if combat_adjacent and not player.afraid:
            # A chase closed on its monster: combat takes over (rev 9.2 M, for
            # whichever chasing owner holds it).
            self._complete_claim_goal(
                "closed-to-melee",
                owners=CLAIM_MONSTER_CHASE_OWNERS,
                monsters={
                    (monster.index, monster.race_id) for monster in combat_adjacent
                },
            )
            self.last_reason = "melee"
            return self._town_producer_entry("_direction_key#2", lambda: self._direction_key(
                player.position, self._weakest(combat_adjacent).position
            ))

        # 2r. Ranged attack: fire matching ammo (or throw a spare oil flask) at a
        # ray-aligned hostile before it closes. Fear blocks melee but NOT firing,
        # so an afraid archer still fights back while it retreats.
        ranged = self._town_producer_entry("_ranged_attack_key#2", lambda: self._ranged_attack_key(
            snapshot, combat_hostiles, combat_adjacent
        ))
        if ranged is not None:
            return ranged

        if summoners and all(monster.distance > 2 for monster in summoners):
            self.last_reason = "summoner:hold-choke"
            return WAIT_KEY

        # A material threat that cannot be attacked from the current square
        # must not fall through to descent or exploration.  Live on Orc cave
        # 19F, three fast monsters at distance two were already worth 57% of
        # current HP over three turns; ordinary exploration then stepped into
        # their pack and turned them into a five-monster surround.
        if strategic_hostiles and self._predicted_damage(
            snapshot, strategic_hostiles, turns=3
        ) >= player.hp * ENGAGEMENT_AVOID_DAMAGE_RATIO:
            step = self._town_producer_entry("_flee_step#3", lambda: self._flee_step(snapshot, strategic_hostiles))
            if step is not None:
                # This is the same navigation veto as the projected-melee gate
                # below.  Without persisting the abandoned square, generic
                # secret-wall exploration can immediately reverse this retreat
                # and alternate with it forever.
                self._claim_engagement_avoid_cells((snapshot.player.position,))
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
                self.last_reason = "threat:reposition"
                self._declare_reach(step, note=CLAIM_GOAL_NOTE_ONE_STEP)
                self._declare_triggers(strategic_hostiles)  # record-only
                return self._step_toward(snapshot, step)
            scroll = self._escape_scroll(snapshot)
            if scroll is not None:
                self.last_reason = "threat:scroll"
                return self._read_key(snapshot, scroll)
            self.last_reason = "threat:wait"
            return WAIT_KEY

        if quest_targets:
            step = self._town_producer_entry("_hunt_step#1", lambda: self._hunt_step(snapshot, quest_targets, allow_cooling=False))
            if step is not None:
                self.last_reason = "hunt:quest-target"
                self._declare_monster(getattr(self, "_hunt_step_target", None))
                return self._step_toward(snapshot, step)

        # 2s. Survival gate (R1): starvation safety is mode- and objective-
        # independent. It runs ABOVE fundraising/quests/descent because every
        # one of those returns keys on its own and would otherwise starve this
        # step of decisions — which is exactly how a mining run walked a
        # character to food_state "weak" with an empty pack (2026-07-17).
        survival = self._town_producer_entry("_survival_gate_key#2", lambda: self._survival_gate_key(snapshot, physical_hostiles))
        if survival is not None:
            return survival

        mana_food_loot = self._town_producer_entry("_mana_food_loot_key", lambda: self._mana_food_loot_key(
            snapshot, strategic_hostiles
        ))
        if mana_food_loot is not None:
            return mana_food_loot

        quest_floor_recovery = self._town_producer_entry("_kill_quest_floor_recovery_key", lambda: self._kill_quest_floor_recovery_key(snapshot))
        if quest_floor_recovery is not None:
            return quest_floor_recovery

        home_disposal = self._town_producer_entry("_home_disposal_processing_key", lambda: self._home_disposal_processing_key(snapshot))
        if home_disposal is not None:
            return home_disposal

        cancel_unsafe_recall = self._town_cancel_unsafe_recall_key(snapshot)
        if cancel_unsafe_recall is not None:
            return cancel_unsafe_recall
        if snapshot.in_town and snapshot.player.recalling:
            # Once Hengband has accepted a town recall, departure owns every
            # remaining surface decision.  This covers both a fresh process
            # attaching to an engine-owned recall and a recall armed by this
            # policy: rebuilding the optional town plan here could otherwise
            # start a new shop/Home errand after the final departure read.
            # Store tiles are still stepped off so the recall can complete.
            here = snapshot.grid_at(snapshot.player.position)
            if here is not None and here.is_store:
                neighbors = self._walkable_neighbors(
                    snapshot, snapshot.player.position
                )
                if neighbors:
                    self.last_reason = "town:wait-recall-step-off"
                    self._declare_reach(neighbors[0], note=CLAIM_GOAL_NOTE_ONE_STEP)
                    key = self._step_toward(snapshot, neighbors[0])
                    if key is not None:
                        self._offer_execution(
                            key, producer="departure",
                            work_id="town:recall-step-off",
                            next_step="recall.step-off-store",
                            expected_effect="store-cell-cleared",
                        )
                    else:
                        self._offer_execution_no_step(
                            producer="departure",
                            work_id="town:recall-step-off",
                            cause="step-off-unavailable",
                        )
                    return key
            self.last_reason = "town:wait-recall"
            self._offer_execution(
                WAIT_KEY, producer="departure",
                work_id="town:recall-countdown",
                next_step="recall.observe-arrival",
                expected_effect="floor-change",
            )
            return WAIT_KEY

        # Native travel can cross most of town without another bot decision.
        # Eat first once hunger is visible so a long shop trip cannot continue
        # into weakness merely because the ordinary food check is later below.
        if snapshot.in_town and player.hungry and not physical_hostiles:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "town:eat-before-travel"
                return EAT_KEY + food.slot

        # Wilderness monsters can enter town, so shopping is not safe while
        # injured. After an unseen hit, head for the nearest store entrance;
        # otherwise recover fully before crossing town again.
        if snapshot.in_town and not physical_hostiles:
            if self._took_damage:
                self._claim_target_capture = []
                try:
                    shelter = self._nearest_goal_step(snapshot, lambda grid: grid.is_store)
                finally:
                    shelter_target = self._take_claim_target()
                if shelter is not None:
                    self.last_reason = "town:seek-shelter"
                    self._declare_reach(shelter_target)
                    return self._step_toward(snapshot, shelter)
            if (
                player.hp < player.max_hp
                or player.mp < player.max_mp
                or not self._temporary_status_clear(snapshot)
            ) and player.food_state in {"normal", "full", "gorged"}:
                self.last_reason = "town:recover"
                self._offer_execution(
                    REST_MACRO, producer="survival", work_id="town:recover",
                    next_step="player.rest", expected_effect="hp/mp/status-recovered",
                )
                return REST_MACRO

        # An already-required combat-weapon restoration is an equipment safety
        # continuation, not new town work.  Finish it before pack-pressure
        # routing can relocate the player and invalidate the prepared mutation.
        restore_weapon = self._town_producer_entry("_town_restore_weapon_key", lambda: self._town_restore_weapon_key(snapshot))
        if restore_weapon is not None:
            return restore_weapon

        if (
            "quest-request" not in self._town_turn_arbiter._retired
            and self._fixed_quest_prepare_return_required(snapshot)
        ):
            fixed_quest = self._town_producer_entry("_fixed_quest_key#1", lambda: self._fixed_quest_key(snapshot, strategic_hostiles))
            if fixed_quest is not None:
                return fixed_quest

        space_deposit = self._town_producer_entry("_town_space_deposit_key", lambda: self._town_space_deposit_key(snapshot))
        if space_deposit is not None:
            return space_deposit

        victory_loot = self._town_producer_entry("_victory_loot_key", lambda: self._victory_loot_key(snapshot))
        if victory_loot is not None:
            return victory_loot

        conquest_loot = self._town_producer_entry("_conquest_loot_key", lambda: self._conquest_loot_key(snapshot))
        if conquest_loot is not None:
            return conquest_loot

        fixed_quest = self._town_producer_entry("_fixed_quest_key#2", lambda: self._fixed_quest_key(snapshot, strategic_hostiles))
        if fixed_quest is not None:
            return fixed_quest

        stat_restore = self._town_producer_entry("_stat_restore_quaff_key", lambda: self._stat_restore_quaff_key(
            snapshot, physical_hostiles
        ))
        if stat_restore is not None:
            return stat_restore

        experience = self._town_producer_entry("_experience_potion_quaff_key", lambda: self._experience_potion_quaff_key(
            snapshot, physical_hostiles
        ))
        if experience is not None:
            return experience

        stat_gain = self._town_producer_entry("_stat_gain_quaff_key", lambda: self._stat_gain_quaff_key(snapshot, physical_hostiles))
        if stat_gain is not None:
            return stat_gain

        bounty = self._town_producer_entry("_town_order_step4_key#2", lambda: self._town_order_step4_key(snapshot))
        if bounty is not None:
            return bounty

        dungeon_identify = self._dungeon_equipment_identify_key(
            snapshot, physical_hostiles
        )
        if dungeon_identify is not None:
            return dungeon_identify

        fundraising = self._town_producer_entry("_fundraising_key#1", lambda: self._fundraising_key(snapshot, strategic_hostiles))
        if fundraising is not None:
            return fundraising

        if (
            self._count_recall_scrolls(snapshot)
            < self._recall_shortage_retreat_threshold(snapshot.dungeon_level)
            and not self._recall_shortage_opening_exempt(snapshot)
            and self._fundraising_mode not in {"prepare", "mine", "scavenge"}
            and not snapshot.in_town
        ):
            # Preserve quest-floor exit locks below: setting the ordinary
            # return latch is sufficient, and the existing return owner
            # decides whether walking upward is currently legal.
            self._note_return_start("recall-shortage")
            self._returning_to_town = True
            self._last_return_trigger = "recall-shortage"

        identify = self._pack_pressure_identify_key(snapshot)
        if identify is not None:
            return identify

        # In town, compact before departure whenever fewer than the required
        # number of loot slots remain. Dungeon compaction still waits for a full
        # pack, where returning becomes necessary if nothing can be discarded.
        if len(snapshot.inventory) >= PACK_CAPACITY or (
            snapshot.in_town
            and PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS
        ):
            destroy = self._full_pack_destroy_key(snapshot)
            if destroy is not None:
                return destroy

        # Process a carried chest while things are calm — BEFORE committing to
        # a supply return: the pipeline takes a couple dozen decisions and the
        # contents may themselves be the supplies (drop → step beside → s ×N →
        # D ×N → o ×N, the user-specified procedure). Emergencies never reach
        # here (handled at the top), so only the leisurely return is deferred.
        chest = self._town_producer_entry("_chest_processing_key#2", lambda: self._chest_processing_key(snapshot, physical_hostiles))
        if chest is not None:
            return chest

        # A routine supply return can afford a short sweep for already-seen safe
        # loot. Hunger, darkness, a full pack, and emergency returns never detour.
        # loot-before-recall (user 2026-09-23) deliberately does NOT widen this
        # gate: nothing may delay reading the scroll.  The collection it asks
        # for happens afterwards, inside the recall countdown, where the return
        # owner would otherwise stand still (_return_to_town_key).
        return_starting = (
            not snapshot.in_town and self._should_start_town_return(snapshot)
        )
        if (
            (return_starting or self._returning_to_town)
            and not player.recalling
            and not self._emergency_return_active
            and self._last_return_trigger in RETURN_LOOT_SWEEP_TRIGGERS
        ):
            return_loot = self._town_producer_entry("_normal_loot_key#1", lambda: self._normal_loot_key(
                snapshot,
                strategic_hostiles,
                max_path_distance=RETURN_LOOT_SWEEP_MAX_DISTANCE,
                seek_reason="return:seek-loot",
            ))
            if return_loot is not None:
                return return_loot

        # R1 navigation invariant: every mode below (including a latched town
        # return that can only wander) is some form of navigation. When
        # NAV_NO_PROGRESS_LIMIT decisions have produced no new coverage, no
        # first-visit tile, no target-distance improvement and no combat, they
        # are collectively livelocked regardless of how varied their reasons
        # look — leave the floor (recall/up-stairs), or stop visibly. This must
        # run ABOVE the town return: a return with no reachable exit degrades
        # to return:wander forever and would shadow the escape.
        livelock = self._town_producer_entry("_navigation_livelock_key", lambda: self._navigation_livelock_key(snapshot))
        if livelock is not None:
            return livelock

        # A fled breeder floor turns the ordinary return into a persistent
        # walk-out, but it remains a navigation owner: survival/combat above
        # and the livelock escape immediately above must retain priority.
        if (
            self._breeder_walkout_active(snapshot)
            and self._escape_state.owner in {None, "return"}
        ):
            self._note_return_start(None)
            self._returning_to_town = True
            walkout = self._town_producer_entry("_return_to_town_key#2", lambda: self._return_to_town_key(
                snapshot,
                strategic_hostiles,
                allow_recall=(
                    self._fundraising_mode != "mine"
                    and self._active_quest_id(snapshot) is None
                ),
            ))
            if walkout is not None:
                self._escape_state.enter("return", self.last_reason)
                return walkout

        # Low supplies and a full pack are expedition-ending conditions. Once
        # triggered, keep heading upward even if using an item opens a pack slot.
        town_return = (
            None
            if self._escape_state.owner not in {None, "return"}
            else self._town_producer_entry("_return_to_town_key#3", lambda: self._return_to_town_key(snapshot, strategic_hostiles))
        )
        if town_return is not None:
            self._escape_state.enter("return", self.last_reason)
            return town_return

        # Identification can consume the same scarce gold as the mining setup.
        # While fundraising, finish Treasure Detection scrolls and a digging
        # tool first; retain any pending identification request for afterwards.
        if (
            snapshot.store is None
            and snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and self._active_quest_id(snapshot) is None
            and "quest-request" not in self._town_turn_arbiter._retired
            and len(snapshot.inventory) >= PACK_CAPACITY - HOME_BATCH_RESERVED_SLOTS - 1
            and not self._town_space_deposit_actionable(snapshot)
            and self._home_atomic_withdraw_pending is None
            and self._home_atomic_deposit_pending is None
            and not self._home_entry_operation_posted
            and (not self._equipment_catalog.home_scan_complete
                 or self._home_knowledge_invalidated)
            and not self._defer_town_errand("equipment-txn", "acquire-home-catalog")
            and self._ensure_home_visit_request(snapshot)
        ):
            step = self._shopping_approach_step(
                snapshot, STORE_HOME, requester="home-scan"
            )
            here = snapshot.grid_at(snapshot.player.position)
            if step is None and here is not None and here.store_number == STORE_HOME:
                # Acquiring an initial visit while already standing on the
                # entrance is the intentional WAIT activation, not a failed
                # route and not authority to step off/re-enter.
                step = snapshot.player.position
            if step is not None and self._shopping_approach_store_type == STORE_HOME:
                self.last_reason = "equipment-transaction:acquire-home-catalog"
                key = self._town_producer_entry("_shopping_approach_key#1", lambda: self._shopping_approach_key(
                    snapshot, step, "equipment-transaction:travel-home"
                ))
                if key is not None:
                    self._offer_execution(
                        key, producer="equipment-txn",
                        work_id="equipment:acquire-home-catalog",
                        next_step="home.approach-for-equipment-catalog",
                        expected_effect="home-catalog-available",
                    )
                else:
                    self._offer_execution_no_step(
                        producer="equipment-txn",
                        work_id="equipment:acquire-home-catalog",
                        cause="home-approach-unavailable",
                    )
                return key

        if not (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and not self._fundraising_supplies_ready(snapshot)
        ):
            equipped_identification = self._town_producer_entry("_town_equipped_identification_key", lambda: self._town_equipped_identification_key(snapshot, macro=True))
            if equipped_identification is not None:
                return equipped_identification

            item_processing = self._town_item_processing_key(snapshot)
            if item_processing is not None:
                return item_processing

            device_processing = self._town_producer_entry("_town_device_processing_key", lambda: self._town_device_processing_key(snapshot))
            if device_processing is not None:
                return device_processing

            # A Home-held identification source is upstream of the equipment
            # candidate that requested it. Bind that source from the completed
            # Home address catalog before optimization gets another chance to
            # reject the still-incomplete equipment catalog.
            self._queue_home_identification_source(snapshot)
            # The identification-withdrawal NeedSpec is only a routing claim;
            # bind its exact catalogue signature to the Home executor before
            # town-plan projection is allowed to approach Home.
            self._bind_catalogued_home_identification_withdrawal(snapshot)

        mark_heavy_curse = self._town_producer_entry("_heavy_curse_inscription_key", lambda: self._heavy_curse_inscription_key(snapshot))
        if mark_heavy_curse is not None:
            return mark_heavy_curse

        remove_curse = self._town_producer_entry("_town_remove_curse_key", lambda: self._town_remove_curse_key(snapshot))
        if remove_curse is not None:
            return remove_curse
        self._bind_home_star_remove_curse_withdrawal(snapshot)

        enchant_launcher = self._town_producer_entry("_town_enchant_launcher_key", lambda: self._town_enchant_launcher_key(snapshot))
        if enchant_launcher is not None:
            return enchant_launcher

        suppress_random_teleport = self._town_producer_entry("_town_random_teleport_suppression_key", lambda: self._town_random_teleport_suppression_key(
            snapshot
        ))
        if suppress_random_teleport is not None:
            return suppress_random_teleport

        # Equipment changes have one owner: after Home identification and the
        # complete-page scan, execute the globally optimized loadout transaction.
        # Legacy per-item weapon trials and jewellery upgrades must not race this
        # plan or repeatedly withdraw and re-deposit candidates.
        equipment_transaction = self._town_producer_entry("_equipment_transaction_town_key#2", lambda: self._equipment_transaction_town_key(snapshot))
        if equipment_transaction is not None:
            return equipment_transaction

        # USER DECISION 2026-10-02 「帰還が進んでいる間だけ止める」: the
        # emergency return shuts ordinary loot out only while it progresses
        # (recall read and waiting, or walking to the exit); on a floor it
        # cannot leave, the bot picks up even with the flag set.
        emergency_return_progressing = self._emergency_return_progressing(snapshot)
        if (
            not emergency_return_progressing
            and not self._required_supply_suppresses_normal_loot(snapshot)
        ):
            loot = self._town_producer_entry("_normal_loot_key#2", lambda: self._normal_loot_key(snapshot, strategic_hostiles))
            if loot is not None:
                return loot
        elif emergency_return_progressing:
            # S2b.1b, record-only: the progressing emergency return shuts
            # ordinary loot out, so the committed loot walk (often suspended
            # by the emergency that set the flag) ends here.
            self._release_claim_goal(
                "loot-suppressed:emergency-return",
                self._loot_target,
                owners=CLAIM_LOOT_OWNERS,
            )

        # Keep a light lit before any town errand can approach a store or the
        # dungeon entrance: native town travel is rejected at night unless a
        # light is equipped. Skip equipment changes while confused, and while
        if not player.confused:
            restore_lantern = self._empty_lantern_to_restore(snapshot)
            if restore_lantern is not None:
                self.last_reason = "restore-lantern"
                return self._equipment_wield(
                    snapshot, "light-loadout", restore_lantern, "light"
                )
            wield = self._light_to_wield(snapshot)
            if wield is not None:
                self.last_reason = "wield-light"
                key = self._equipment_wield(
                    snapshot, "light-loadout", wield, "light"
                )
                if key is not None:
                    self._offer_execution(
                        key, producer="equipment-txn",
                        work_id="equipment:wield-light",
                        next_step="equipment.wield-light",
                        arguments=(self._item_signature(wield),),
                        expected_effect="light-equipped",
                    )
                else:
                    self._offer_execution_no_step(
                        producer="equipment-txn",
                        work_id="equipment:wield-light",
                        cause="light-wield-unavailable",
                    )
                return key
            refill = self._light_refill_item(snapshot)
            if refill is not None:
                self.last_reason = "refill-light"
                return REFILL_KEY + refill.slot
            departure_refill = self._unknown_lantern_departure_refill_item(snapshot)
            if departure_refill is not None:
                self._unknown_lantern_departure_refilled = True
                self.last_reason = "refill-light"
                return REFILL_KEY + departure_refill.slot

        # _observe schedules the town circuit breaker before _decide runs.  It
        # must preempt the shopping approach below: that router otherwise
        # returns on every decision and starves _town_special_key forever,
        # leaving the breaker pending while the character repeats the same
        # unaffordable errand.
        if self._town_restock_suppressed:
            supplier = self._departure_supplier_counterfactual(snapshot)
            if supplier is not None:
                # E6 routes suppression release through the same I5
                # counterfactual as terminal selection.  The arbiter's
                # owner/vector recurrence budget, not this latch, bounds a
                # supplier that returns without durable progress.
                self._town_suppression_claim_stores.add(supplier)
                self._town_restock_suppressed = False
                self._town_blocked_reason = None
                self._retire_town_errand_plan_for_rebuild()
        if self._town_cycle_pending:
            town_cycle_repair = self._town_special_key(snapshot)
            if town_cycle_repair is not None:
                return town_cycle_repair

        # 2a. Before diving: while in town with money and no lantern, walk to the
        #     General Store to buy one. A brass lantern lights radius 2 vs a torch's
        #     radius 1 — seeing the dark is what the Half-Troll lacked when it died.
        if snapshot.in_town:
            self._end_fundraising_set_at_gold_target(snapshot)
            self._town_order_select_required_supply(snapshot)
            self._bind_home_star_remove_curse_withdrawal(snapshot)
            # The departure seam (_town_special_key) releases a stale Home
            # candidate latch before it evaluates departure; _observe re-derives
            # that latch on every in-town board (a Home identify scroll alone
            # sets it).  When that latch is the only failing departure leaf,
            # the release flips the verdict the claim registry reads (optional
            # claims register only when departure is ready).  Release it here
            # in exactly that case, so the registry below and the departure
            # seam read one departure verdict in one decision (live 2026-10-02
            # 17:00:51: not ready here hid the optional launcher-enchant claim
            # from this router, ready there kept it active and deferred the
            # departure verdict -> no owner).  With another leaf failing both
            # seams already read "not ready"; the latch is left as it was.
            if self._home_candidate_waiting and [
                name for name, ready
                in self._town_departure_conjuncts(snapshot).items()
                if not ready
            ] == ["home_candidate_resolved"]:
                self._release_stale_home_candidate_waiting(snapshot)
            claims_active = self._town_claims_active(snapshot)
            if not claims_active:
                # The former router performed terminal bookkeeping before it
                # returned None. Preserve those latch releases and pending-disposal
                # handoffs without letting the errand plan own this departure turn.
                self._town_terminal_transitions(snapshot)
            if claims_active:
                step = self._shopping_approach_step(
                    snapshot, router_plan_stop=True
                )
                if step is not None:
                    self.last_reason = "shop:approach"
                    return self._town_producer_entry("_shopping_approach_key#2", lambda: self._shopping_approach_key(snapshot, step, "shop:travel"))

        destroy = self._town_destroy_key(snapshot)
        if destroy is not None:
            return destroy

        # Last-resort overflow disposal: in town without the required expedition
        # free slots and no productive
        # action left (nothing to deposit, sell, buy, or fundraise), shed one
        # non-essential item so the pack can shrink and the bot can descend
        # again. Without this the bot cannot re-enter the dungeon (pack-full
        # blocks descent) and wanders the town forever. Skipped mid-fight.
        if (
            snapshot.in_town
            and not physical_adjacent
            and PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS
        ):
            overflow_destroy = self._town_producer_entry("_town_overflow_destroy_key", lambda: self._town_overflow_destroy_key(snapshot))
            if overflow_destroy is not None:
                self._terminal_pack_space_signature = None
                return overflow_destroy
            if PACK_CAPACITY - len(snapshot.inventory) >= MIN_TERMINAL_FREE_PACK_SLOTS:
                signature = self._town_pack_space_signature(snapshot)
                if self._terminal_pack_space_signature != signature:
                    self._terminal_pack_space_signature = signature

        town_special = self._town_special_key(snapshot)
        if town_special is not None:
            return town_special

        # The posted Home take owns this entrance until the outside inventory
        # observation confirms or clears it.  Survival, combat, town work, and
        # cycle repair above retain priority; this only prevents the generic
        # exploration breakout below from walking off the entrance.
        if self._home_atomic_withdraw_pending is not None:
            home_entrance = snapshot.grid_at(player.position)
            if (
                snapshot.in_town
                and snapshot.store is None
                and home_entrance is not None
                and home_entrance.store_number == STORE_HOME
            ):
                self.last_reason = "home:atomic-withdraw-pending-hold"
                return WAIT_KEY

        if (
            snapshot.in_town
            and self._recall_departure_shortage(snapshot)
            and not self._recall_shortage_opening_exempt(snapshot)
            and self._fundraising_mode not in {"prepare", "mine", "scavenge"}
            and not self._town_cycle_pending
            and self._town_blocked_reason != "repetition"
        ):
            # Existing shopping, processing, and restock owners above get their
            # normal opportunity. At the ordinary departure boundary, shortage
            # permits only the established fundraising or restock-wait flow.
            if self._start_fundraising(snapshot):
                fundraising = self._town_producer_entry("_fundraising_key#2", lambda: self._fundraising_key(
                    snapshot, strategic_hostiles
                ))
                if fundraising is not None:
                    return fundraising
            recall_stores = (STORE_TEMPLE, STORE_ALCHEMIST)
            if (
                not all(
                    store in self._town_store_attempted
                    for store in recall_stores
                )
                and getattr(self._town_map, "store_position", None) is not None
            ):
                return self._town_producer_entry("_released_restock_store_key", lambda: self._released_restock_store_key(
                    snapshot, recall_stores
                ))
            return self._recall_restock_key(snapshot)

        here = snapshot.grid_at(player.position)
        # 4. Recover between fights: with nothing hostile in sight and HP down
        #    (and not bleeding, and not being hit by something unseen), rest until
        #    healed. This is our main way to stay survivable without healing items.
        if (
            player.hp_ratio < REST_TARGET_HP_RATIO
            and not self._physical_hostiles(snapshot)
            and not self._took_damage
            and not player.poisoned
            and not player.cut
            and not player.confused
            and player.food_state in {"normal", "full", "gorged"}
            and self._rest_count < REST_CAP
        ):
            # Awake monsters known only by telepathy/detection interrupt every
            # rest (live Angband 41F loop, 2026-09-21): the user-confirmed
            # tiers hunt, keep exploring, or leave the floor instead.
            suppress_rest, esp_threat = self._town_producer_entry("_esp_threat_rest_key", lambda: self._esp_threat_rest_key(
                snapshot, strategic_hostiles
            ))
            if esp_threat is not None:
                return esp_threat
            # S2b.1b, record-only: the slot passed without a hunt.
            assessment = self._esp_threat_assessment
            self._release_esp_threat_rest_hunt(
                "esp-threat:rest-"
                + str(
                    assessment.get("action")
                    if isinstance(assessment, dict)
                    else "no-assessment"
                )
            )
            if not suppress_rest:
                # Note: resting burns many turns (= food). Skip it when hungry
                # so we don't starve — bot-test died of starvation partly from
                # over-resting.
                self._rest_count += 1
                self.last_reason = "rest"
                self._offer_execution(
                    REST_MACRO, producer="survival", work_id="rest",
                    next_step="player.rest", expected_effect="hp/mp-recovered",
                )
                return REST_MACRO
        else:
            # S2b.1b, record-only: the rest gate is closed, so the rest slot's
            # hunt is not asked for this board.
            self._release_esp_threat_rest_hunt("esp-threat:rest-gate-closed")

        # 5. Descend when standing on a downstairs or dungeon entrance — only
        #    while healthy, so we never dive deeper than we can handle.
        static_entrance_here = (
            snapshot.in_town
            and self._town_map_active(snapshot)
            and self._town_map_descent_entrance(snapshot) == player.position
            and here is not None
            and self._is_active_dungeon_entrance(here)
        )
        direct_destination_depth = (
            self._dungeon_entry_depth(
                snapshot, self._active_dungeon_target(), via_recall=False
            )
            if static_entrance_here
            or (
                snapshot.dungeon_level == 0
                and here is not None
                and here.has_entrance
                and self._is_active_dungeon_entrance(here)
            )
            else snapshot.dungeon_level + 1
            if snapshot.dungeon_level > 0
            and here is not None
            and here.is_descent
            else None
        )
        if (
            (
                here is not None
                and here.is_descent
                and self._is_descent_target(snapshot, here)
                or static_entrance_here
            )
            and player.hp_ratio >= DESCEND_MIN_HP_RATIO
            and not self._descent_is_blocked(snapshot)
            # Routing toward town may yield to another escape owner, but no
            # owner may route us back into the breeder floor we just fled.
            and not self._breeder_walkout_active(snapshot)
            and (
                direct_destination_depth is None
                or self._destination_depth_allowed(
                    snapshot, direct_destination_depth
                )
            )
            and (
                not (
                    static_entrance_here
                    or (
                        snapshot.dungeon_level == 0
                        and here is not None
                        and here.has_entrance
                    )
                )
                or self._dungeon_entry_allowed(
                    snapshot,
                    via_recall=False,
                    destination_depth=self._dungeon_entry_depth(
                        snapshot, self._active_dungeon_target(), via_recall=False
                    ),
                )
            )
        ):
            self.last_reason = "descend"
            if (getattr(self, "_crossarea_fundraising_enforced", False)
                    and snapshot.in_town
                    and self._fundraising_mode in {"mine", "scavenge"}):
                facts = self._fundraising_facts(snapshot)
                prior = self._fundraising_purpose_record
                self._fundraising_run_purpose = (
                    prior.purpose
                    if prior is not None and prior.status == "active"
                    else FundraisingPurpose(
                        identity=self._decision_sequence,
                        mode=self._fundraising_mode,
                        first_run_food_waiver=(
                            not facts.carried_edible and facts.first_run
                            and facts.procurement_exhausted
                        ),
                    )
                )
            return (
                ENTER_DUNGEON_MACRO
                if static_entrance_here or (here is not None and here.has_entrance)
                else DOWN_STAIRS_KEY
            )

        # If every known way forward fails the next-depth resistance gate,
        # invalidate the descent route and keep exploring this (highest safe)
        # floor.  The lack of readiness for depth N+1 is not a reason to abandon
        # useful exploration on safe depth N.
        if self._all_known_descents_blocked_by_next_depth_requirements(snapshot):
            self._nav_ledger.clear_descent_route()
            self._descent_target_goal = None

        # A monster can be just outside the material-threat threshold at its
        # current distance while becoming material after one closing step.
        # Preserve higher-priority concrete work such as safe loot recovery,
        # but retreat before descent, hunting, or generic exploration can
        # close into the engagement and alternate with the threat gate.
        if any(
            self._material_melee_engagement(snapshot, monster)
            for monster in strategic_hostiles
        ):
            step = self._town_producer_entry("_flee_step#4", lambda: self._flee_step(snapshot, strategic_hostiles))
            if step is not None:
                # Treat the retreat as a navigation veto, not a one-turn move.
                # A committed explore path otherwise walks straight back here.
                self._claim_engagement_avoid_cells((snapshot.player.position,))
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
                self.last_reason = "threat:avoid-engagement"
                self._declare_reach(step, note=CLAIM_GOAL_NOTE_ONE_STEP)
                self._declare_triggers(strategic_hostiles)  # record-only
                return self._step_toward(snapshot, step)

        # 6. Head for a known downstairs / dungeon entrance: path straight there
        #    if reachable, otherwise explore toward it (the entrance may be known
        #    but its approach still unmapped — e.g. the town's wilderness gate).
        #    A single BFS covers both, so the huge full-map scan runs only once.
        step = self._town_producer_entry("_descent_step", lambda: self._descent_step(snapshot))
        if step is not None:
            # A visible monster can temporarily split the only known route to
            # the stairs. Chasing a fallback frontier makes the monster vanish
            # from sight, after which we turn back toward the stairs forever.
            # Clear an easy blocker instead of bouncing at the visibility edge.
            if self.last_reason == "approach-descent" and strategic_hostiles:
                clear_step = self._town_producer_entry("_hunt_step#2", lambda: self._hunt_step(snapshot, strategic_hostiles))
                if clear_step is not None:
                    self.last_reason = "clear-descent"
                    self._declare_monster(
                        getattr(self, "_hunt_step_target", None)
                    )
                    key = self._step_toward(snapshot, clear_step)
                    if key is not None:
                        self._offer_execution(
                            key, producer="departure",
                            work_id="departure:clear-descent",
                            next_step="departure.clear-descent-blocker",
                            expected_effect="descent-route-cleared",
                        )
                    else:
                        self._offer_execution_no_step(
                            producer="departure",
                            work_id="departure:clear-descent",
                            cause="blocker-step-unavailable",
                        )
                    return key
            travel = self._entrance_travel_key(snapshot, self._descent_target_goal)
            if travel is not None:
                return travel
            key = self._step_toward(snapshot, step)
            if key is not None:
                self._offer_execution(
                    key, producer="departure",
                    work_id=f"departure:descent-route:{self._descent_target_goal}",
                    next_step="departure.approach-descent",
                    expected_effect="descent-target-reached",
                )
            else:
                self._offer_execution_no_step(
                    producer="departure", work_id="departure:descent-route",
                    cause="descent-step-unavailable",
                )
            return key

        # 7. Eat when hungry and it is safe to do so.
        if player.hungry and not physical_hostiles:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "eat"
                return EAT_KEY + food.slot

        # 7. Opportunistic hunt for easy XP while no downstairs is in sight.
        step = self._town_producer_entry("_hunt_step#3", lambda: self._hunt_step(snapshot, strategic_hostiles))
        if step is not None:
            self.last_reason = "hunt"
            self._declare_monster(getattr(self, "_hunt_step_target", None))
            return self._step_toward(snapshot, step)

        # 7b. Escape a walled-off floor. If we have spent STUCK_ESCAPE_LIMIT turns
        #     running only searching / breaking out / wandering here (no combat, no
        #     stairs, no new frontier — the streak is counted in _observe), the
        #     down-stairs are unreachable and supplies are fine, so the town-return
        #     never fires. Word-of-Recall out; the next dive regenerates the floor
        #     with reachable stairs. Checked BEFORE the search/explore cluster so it
        #     actually runs (those steps return before the old step-10 fallback).
        forgetting_maze = self._is_forgetting_maze(snapshot)
        completed_forgetting_maze = self._is_completed_forgetting_maze(snapshot)
        if (
            not snapshot.in_town
            and (
                self._stuck_escape_streak >= STUCK_ESCAPE_LIMIT
                or self._breakout_dig_floor == snapshot.floor_key
            )
            and (not forgetting_maze or completed_forgetting_maze)
            # Leaving an active quest floor can permanently fail a random quest.
            # Keep searching for its target instead of treating the floor as a
            # disposable bad generation.
            and snapshot.floor_key[2] == 0
            and not player.recalling
            and not player.blind
            and not player.confused
        ):
            # A known descent can be sealed behind ordinary diggable veins even
            # after every walkable frontier has been exhausted.  Recompute the
            # augmented route on every decision: successful tunnelling changes
            # the map, while the mode-independent navigation ledger eventually
            # takes over and recalls if repeated digs make no observable progress.
            if self._has_digging_tool(snapshot) and not self._nav_exhausted:
                dig = self._dig_to_known_downstairs_key(snapshot)
                if dig is not None:
                    if self._equipped_digging_tool(snapshot) is None:
                        wield = self._wield_digging_tool_key(
                            snapshot, "breakout:wield-digging-tool"
                        )
                        if wield is not None:
                            self._breakout_dig_floor = snapshot.floor_key
                            return wield
                    self.last_reason = "breakout:dig-to-stairs"
                    return dig
                restore = self._town_producer_entry("_breakout_restore_weapon_key#2", lambda: self._breakout_restore_weapon_key(snapshot))
                if restore is not None:
                    return restore
            recall = self._find_recall_scroll(snapshot)
            if recall is not None and self._can_read_scrolls(snapshot):
                self._stuck_escape_streak = 0
                self._note_return_start(None)
                self._returning_to_town = True
                self.last_reason = "stuck:recall-escape"
                return self._read_dungeon_recall_scroll_key(snapshot, recall)
            teleport = self._find_teleport_scroll(snapshot)
            if teleport is not None and self._can_read_scrolls(snapshot):
                self._stuck_escape_streak = 0
                self.last_reason = "stuck:teleport-escape"
                return self._read_key(snapshot, teleport)

        # 8. If we are circling the same few tiles (frontiers whose unknown side
        #    the pathfinder can't reach), break out by stepping directly into an
        #    adjacent unknown tile to reveal it. Only when actually oscillating,
        #    so normal directed exploration is unaffected. Wall bumps are harmless
        #    and bounded by PROBE_LIMIT.
        if self._is_oscillating():
            step = self._town_producer_entry(
                "oscillating-probe", lambda: self._probe_unknown_step(snapshot),
                family="explore")
            if step is not None:
                self._release_explore_walk("explore-oscillating:probe")
                self.last_reason = "probe"
                return self._step_toward(snapshot, step)
            # A dead-end may be a SECRET door/passage the map can't show until we
            # search for it. Search this spot a few times before treating it as
            # truly closed — it is what breaks an otherwise-unescapable circle
            # (verified live: 's' a few times reveals the hidden corridor).
            # Secret doors/passages only exist in the dungeon; searching in town
            # is wasted turns, so never 's' there — fall straight through to a
            # move instead.
            here_key = (player.position.y, player.position.x)
            if (
                not snapshot.in_town
                and not forgetting_maze
                and self._search_counts[here_key] < SEARCH_LIMIT
            ):
                self._search_counts[here_key] += 1
                self._release_explore_walk("explore-oscillating:search")
                self.last_reason = "search"
                return SEARCH_KEY
            # Once local probes and searches are exhausted, resume the committed
            # exploration planner. It can route across remembered, off-screen
            # floor to an older reachable frontier; choosing a local least-visited
            # neighbour first traps us in a fully-known room forever.
            step = self._town_producer_entry("_explore_step#1", lambda: self._explore_step(snapshot))
            if step is not None:
                # A valid committed route means the oscillation was escaped. Drop
                # the stale stationary/search history now; otherwise it remains
                # "oscillating" for several more decisions and searches at every
                # waypoint until the recall escape threshold is reached.
                self._recent.clear()
                self._stuck_escape_streak = 0
                self.last_reason = "breakout:seek-frontier"
                self._declare_explore_goal()
                return self._step_toward(snapshot, step)
            # No reachable unexplored floor or frontier remains. Only now use a
            # local least-visited step to keep moving while secret-wall searches
            # are exhausted elsewhere.
            step = self._least_visited_neighbor(snapshot)
            if step is not None:
                self.last_reason = "breakout:least-visited"
                return self._step_toward(snapshot, step)

        # Search a corridor dead-end before ordinary exploration routes us away.
        # This is opportunistic only: never detour toward a remote dead-end.
        if (
            not snapshot.in_town
            and snapshot.dungeon_level > 0
            and not forgetting_maze
            and self._open_neighbor_count(snapshot, player.position) <= 1
            and self._undersearched_walls(player.position)
        ):
            self._record_wall_search(player.position)
            self.last_reason = "search"
            return SEARCH_KEY

        # A released immobile-breeder plan is only an exploration fallback.
        # Ordinary combat, threat, loot, descent, and hunting owners above must
        # retain their normal priority when another mobile hostile is present.
        immobile_breeder_giveup = self._town_producer_entry("_immobile_breeder_giveup_key", lambda: self._immobile_breeder_giveup_key(snapshot))
        if immobile_breeder_giveup is not None:
            return immobile_breeder_giveup

        # 9. Explore toward the unknown (door- and edge-aware).
        step = self._town_producer_entry("_explore_step#2", lambda: self._explore_step(snapshot))
        if step is not None:
            self.last_reason = "explore"
            self._declare_explore_goal()
            return self._step_toward(snapshot, step)

        # The planner deliberately excludes the current tile as a destination.
        # When this tile is the floor's sole remaining frontier, probe through
        # its unknown edge instead of concluding that exploration is complete.
        # If those probes hit an unseen wall, search here for a secret passage
        # before falling back to stairs.
        frontier_here = here is not None and self._is_frontier(snapshot, here)
        probed_wall_here = any(
            (player.position.y + dy, player.position.x + dx)
            in self._blocked_unknown
            for dy, dx in NEIGHBOR_OFFSETS
        )
        if frontier_here or probed_wall_here:
            step = self._town_producer_entry(
                "frontier-probe", lambda: self._probe_unknown_step(snapshot),
                family="explore")
            if step is not None:
                self.last_reason = "probe"
                return self._step_toward(snapshot, step)
            # No secret passages in town — do not waste turns searching there.
            here_key = (player.position.y, player.position.x)
            if (
                not snapshot.in_town
                and not forgetting_maze
                and self._search_counts[here_key] < SEARCH_LIMIT
            ):
                self._search_counts[here_key] += 1
                self.last_reason = "search"
                return SEARCH_KEY

        has_downstairs = any(
            grid.has_down_stairs for grid in snapshot.grids.values()
        )
        if (
            snapshot.dungeon_level > 0
            and not forgetting_maze
            and not has_downstairs
        ):
            if self._undersearched_walls(player.position):
                self._record_wall_search(player.position)
                self.last_reason = "search"
                return SEARCH_KEY
            self._claim_target_capture = []
            try:
                step = self._secret_wall_search_step(snapshot)
            finally:
                step_target = self._take_claim_target()
            if step is not None:
                self.last_reason = "seek-secret-wall"
                self._declare_reach(step_target)
                return self._step_toward(snapshot, step)

        # 9. Nothing to explore: take any known stairs to reach a fresh floor.
        quest_regen = self._town_producer_entry("_start_kill_quest_regeneration", lambda: self._start_kill_quest_regeneration(snapshot))
        if quest_regen is not None:
            return quest_regen
        floor_exit_locked = self._floor_navigation_exit_locked(snapshot)
        allow_descent = not self._descent_is_blocked(snapshot)
        self._claim_target_capture = []
        try:
            step = self._nearest_goal_step(
                snapshot,
                lambda g: not floor_exit_locked
                and (
                    self._is_upstairs_target(g)
                    or (allow_descent and self._is_descent_target(snapshot, g))
                ),
            )
        finally:
            step_target = self._take_claim_target()
        if step is not None:
            self.last_reason = "stuck:seek-stairs"
            self._declare_reach(step_target)
            return self._step_toward(snapshot, step)
        if not floor_exit_locked and here is not None and self._is_upstairs_target(here):
            self._defer_descent(snapshot)
            self.last_reason = "stuck:ascend"
            return UP_STAIRS_KEY

        return self._town_producer_entry(
            "idle-fallback", lambda: self._town_idle_key(snapshot), family="idle")

    def _town_idle_key(self, snapshot: Snapshot) -> str:
        step = self._least_visited_neighbor(snapshot)
        if step is not None:
            self.last_reason = "stuck:wander"
            return self._step_toward(snapshot, step)

        self.last_reason = "wait"
        return WAIT_KEY

    # -------------------------------------------------------------- observers


    def _up_stairs_exit_to_wilderness(self) -> bool:
        """Whether '<' on this floor leaves the dungeon for the open wilderness.

        Going up from a floor whose ``dun_level - 1`` is below the dungeon's
        ``mindepth`` lands on the surface (src/floor/floor-leaver.cpp:335-338)
        at the dungeon's entrance tile (``exit_to_wilderness``).  That tile is
        a town only for a dungeon entered from a town (Yeek cave, Outpost);
        for every other dungeon the top floor's '<' puts the player in the
        wilderness, which the bot must never enter -- it returns to town by
        recall (live 2026-10-02 11:50: Castle 20F, ``status-threat:stairs``).
        Unknown floor, dungeon or map answers False (the previous behaviour).
        """
        floor_key = self._floor_key
        if floor_key is None:
            return False
        dungeon_id, level, _quest = floor_key
        if dungeon_id <= 0 or level <= 0:
            return False
        info = self._dungeon_knowledge.get(dungeon_id)
        wilderness = self._wilderness_map
        if info is None or wilderness is None:
            return False
        if level - 1 >= info.min_depth:
            return False
        y, x = getattr(info, "wild_y", None), getattr(info, "wild_x", None)
        if y is None or x is None:
            return False
        rows = wilderness.rows
        cell = rows[y][x] if 0 <= y < len(rows) and 0 <= x < len(rows[y]) else ""
        return not (cell.isdigit() and cell != "0")

    def _is_upstairs_target(self, grid: GridState) -> bool:
        return grid.has_up_stairs and not self._up_stairs_exit_to_wilderness() and (
            (
                grid.in_view
                and self._stair_rejection_strikes[(UP_STAIRS_KEY, grid.position)] < 2
            )
            or
            (UP_STAIRS_KEY, grid.position) in self._unverified_stairs
            or not self._nav_ledger.is_expired("ascend", grid.position)
        )

    def _is_downstairs_expired(self, position: Position) -> bool:
        """Let a launch-snapshot stair receive its conclusive command test."""
        return (
            (DOWN_STAIRS_KEY, position) not in self._unverified_stairs
            and self._nav_ledger.is_expired("descend", position)
        )

    def _observe_stair_command(
        self, snapshot: Snapshot, *, observation: Snapshot | None = None
    ) -> None:
        """Strike a remembered stair only on conclusive command rejection."""
        pending = self._pending_stair_command
        if pending is None:
            return
        direction, floor_key, position, turn, pending_observation = pending
        current_observation = snapshot if observation is None else observation
        if (
            current_observation is pending_observation
            or (
                pending_observation.messages
                and not current_observation.messages
                and current_observation.turn == pending_observation.turn
                and self._owner_progress_core(current_observation)
                == self._owner_progress_core(pending_observation)
            )
        ):
            return
        self._pending_stair_command = None
        self._stair_observation_waits = 0
        if (
            snapshot.floor_key != floor_key
            or snapshot.player.position != position
            or snapshot.turn != turn
        ):
            return
        strike_key = (direction, position)
        self._stair_rejection_strikes[strike_key] += 1
        if self._stair_rejection_strikes[strike_key] < 2:
            return
        kind = "descend" if direction == DOWN_STAIRS_KEY else "ascend"
        remembered = (
            self._remembered_downstairs
            if direction == DOWN_STAIRS_KEY
            else self._remembered_upstairs
        )
        remembered.discard(position)
        self._unverified_stairs.discard((direction, position))
        self._nav_ledger.expire(kind, position)


    # ---------------------------------------------------------------- combat
    @staticmethod
    def _is_weak_breeder(
        snapshot: Snapshot, monster: MonsterState
    ) -> bool:
        return (
            monster.can_multiply
            and max(monster.max_melee_damage, monster.max_ranged_damage)
            < snapshot.player.max_hp * WEAK_BREEDER_MAX_DAMAGE_RATIO
        )


    def _physical_hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        return [
            monster for monster in snapshot.visible_monsters
            if monster.hostile
        ]



    def _strategic_adjacent_hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        origin = snapshot.player.position
        return [
            monster
            for monster in self._strategic_hostiles(snapshot)
            if origin.distance_to(monster.position) <= 1
        ]

    def _physical_adjacent_hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        origin = snapshot.player.position
        return [
            monster
            for monster in self._physical_hostiles(snapshot)
            if origin.distance_to(monster.position) <= 1
        ]

    def _equipped_launcher(self, snapshot: Snapshot) -> InventoryItem | None:
        return next(
            (it for it in snapshot.equipment if it.is_launcher and it.ammo_tval is not None),
            None,
        )

    def _matching_ammo(self, snapshot: Snapshot) -> InventoryItem | None:
        launcher = self._equipped_launcher(snapshot)
        if launcher is None:
            return None
        return next(
            (it for it in snapshot.inventory if it.tval == launcher.ammo_tval),
            None,
        )

    def _estimated_ranged_damage_per_shot(self, snapshot: Snapshot) -> float:
        launcher = self._equipped_launcher(snapshot)
        ammo = self._matching_ammo(snapshot)
        if (
            launcher is None
            or ammo is None
            or launcher.sval not in LAUNCHER_PROPERTIES
            or ammo.damage_dice_num <= 0
            or ammo.damage_dice_sides <= 0
        ):
            return 0.0
        _ammo_tval, _energy, multiplier = LAUNCHER_PROPERTIES[launcher.sval]
        ammo_average = ammo.damage_dice_num * (ammo.damage_dice_sides + 1) / 2
        return max(
            0.0,
            (ammo_average + ammo.to_d + launcher.to_d) * multiplier,
        )

    def _summoner_shots_to_kill(
        self, snapshot: Snapshot, monster: MonsterState
    ) -> int | None:
        damage = self._estimated_ranged_damage_per_shot(snapshot)
        if damage <= 0:
            return None
        return max(1, ceil(monster.hp / damage))

    def _summoner_ranged_attack_available(
        self, snapshot: Snapshot, monster: MonsterState
    ) -> bool:
        player = snapshot.player
        distance = player.position.distance_to(monster.position)
        return (
            self._matching_ammo(snapshot) is not None
            and not player.blind
            and not player.confused
            and 2 <= distance <= RANGED_MAX_DISTANCE
            and not (
                monster.asleep and distance > RANGED_SLEEPER_MAX_DISTANCE
            )
        )

    @claims(ClaimOwner.COMBAT)
    def _summoner_ranged_kill_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Finish a summoner in at most three shots before summoning-space flee."""
        summoners = [
            monster for monster in hostiles
            if monster.can_summon and not monster.asleep
        ]
        candidates = [
            (shots, monster)
            for monster in summoners
            if (shots := self._summoner_shots_to_kill(snapshot, monster)) is not None
            and shots <= SUMMONER_RANGED_KILL_SHOTS
            and self._summoner_ranged_attack_available(snapshot, monster)
        ]
        if not candidates:
            return None
        _shots, target = min(
            candidates, key=lambda pair: (pair[0], pair[1].distance)
        )
        # Direct damage that can kill before the three-shot finish retains the
        # ordinary emergency escape priority.
        if self._predicted_damage(snapshot, hostiles, turns=3) >= snapshot.player.hp:
            return None
        ranged = self._ranged_attack_key(snapshot, [target], [])
        if ranged is not None:
            self.last_reason = "summoner:ranged-kill"
        return ranged

    def _count_throwing_torches(self, snapshot: Snapshot) -> int:
        # ``is_equipment`` describes a wearable kind, not its current location.
        # Inventory/equipment are already separate emitter arrays; live pack
        # torch stacks therefore legitimately carry is_equipment=True.
        return sum(
            it.count
            for it in snapshot.inventory
            if it.is_torch and it.fuel > 0
        )




    def _count_matching_ammo(self, snapshot: Snapshot) -> int:
        launcher = self._equipped_launcher(snapshot)
        return ammo_carry_plan(snapshot, launcher, AMMO_CARRY_TARGET).carried_count






    @staticmethod
    def _is_quest_wall_breach_item(item: InventoryItem | StoreItem) -> bool:
        return (
            item.tval == TVAL_WAND
            and item.sval == SV_WAND_STONE_TO_MUD
            and item.charges > 0
        ) or (item.is_digging_tool and item.pval >= Q2_BREACH_MIN_DIGGING)






    def _abandon_unobtainable_quest_carries(
        self, snapshot: Snapshot, strategy: StrategyProfile
    ) -> None:
        if not snapshot.in_town:
            return
        for name, status in self._quest_carry_status(
            snapshot, strategy.required_force
        ).items():
            if bool(status["ready"]) or name in self._abandoned_quest_carry_requirements:
                continue
            supply = self._quest_carry_obtainability(
                snapshot, strategy, name, status
            )
            if supply.stores and not supply.obtainable:
                self._abandoned_quest_carry_requirements[name] = (
                    "all-suppliers-visited-without-affordable-stock"
                )





    @staticmethod
    def _target_cursor_sort_key(
        origin: Position, monster: MonsterState
    ) -> tuple[int, int, int]:
        """target-sorter.cpp double-distance with its stable y/x scan tie."""
        dy = abs(monster.position.y - origin.y)
        dx = abs(monster.position.x - origin.x)
        return 2 * max(dy, dx) + min(dy, dx), monster.position.y, monster.position.x

    @staticmethod
    def _cursor_delta_keys(origin: Position, target: Position) -> str:
        """Move the free targeting cursor exactly to an arbitrary grid."""
        dy = target.y - origin.y
        dx = target.x - origin.x
        keys: list[str] = []
        while dy or dx:
            step_y = (dy > 0) - (dy < 0)
            step_x = (dx > 0) - (dx < 0)
            keys.append(DIRECTION_KEYS[(step_y, step_x)])
            dy -= step_y
            dx -= step_x
        return "".join(keys)

    @staticmethod
    def _is_processable_chest(item: InventoryItem) -> bool:
        """A chest still worth the drop/search/disarm/open pipeline.

        An opened or smashed chest announces itself in the display name
        (player-visible), in either language; those are junk, not work."""
        if not item.is_chest:
            return False
        name = item.name
        return not any(
            marker in name for marker in ("(empty)", "(空)", "壊れた", "(disarmed)")
        )


    def _should_flee(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> bool:
        player = snapshot.player
        if not hostiles:
            return False
        if player.afraid and adjacent:
            # Fear forbids melee, so back away instead of failing to attack.
            return True
        if self._committed_unique_fight_viable(snapshot, hostiles):
            # Once rare consumables have been committed, do not spend them and
            # then flee solely because the race is over-level or HP crossed the
            # generic threshold. The live 95% projection is rechecked every turn;
            # if it ceases to be viable, normal retreat immediately resumes.
            return False
        if player.hp_ratio < FLEE_HP_RATIO:
            return not self._engagement_is_winnable(snapshot, hostiles)
        # Surrounded: flee only if the swarm could take a big share of HP soon.
        # A raw adjacent count fled full-HP characters from weak (often sleeping)
        # packs — e.g. a clvl20 warrior stair-scumming away from three lvl-9 Skaven.
        # _predicted_damage assumes every hostile attacks (sleepers included), which
        # matches a low-stealth character that wakes them on arrival.
        if (
            len(adjacent) >= SWARM_COUNT
            and self._predicted_damage(
                snapshot, hostiles, turns=SWARM_LOOKAHEAD, expected=True
            )
            >= player.hp * SWARM_FLEE_DAMAGE_RATIO
        ):
            return True
        return False


    # -------------------------------------------------------------- consumables

    @staticmethod
    def _healing_potion_effective_hp(
        snapshot: Snapshot, item: InventoryItem
    ) -> int:
        missing_hp = max(0, snapshot.player.max_hp - snapshot.player.hp)
        raw = HEAL_POTION_EXPECTED_HP.get(item.sval, snapshot.player.max_hp)
        return min(raw, missing_hp)

    def _find_heal_potion(
        self, snapshot: Snapshot, *, expected_damage: int = 0
    ) -> InventoryItem | None:
        candidates = [
            item
            for item in snapshot.inventory
            if item.slot
            and item.is_potion
            and item.aware
            and item.sval in HEAL_POTION_SVALS
            and self._healing_potion_effective_hp(snapshot, item)
            >= expected_damage
        ]
        return min(
            candidates,
            key=lambda item: (self._healing_potion_effective_hp(snapshot, item), item.slot),
            default=None,
        )

    def _find_exact_potion(
        self, snapshot: Snapshot, sval: int
    ) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda item: item.is_potion and item.aware and item.sval == sval,
        )

    def _exact_potion_count(self, snapshot: Snapshot, sval: int) -> int:
        return sum(
            item.count
            for item in snapshot.inventory
            if item.is_potion and item.aware and item.sval == sval
        )

    def _find_low_value_potion(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: it.is_potion
            and it.aware
            and it.sval in LOW_VALUE_POTION_SVALS,
        )


    def _is_spare_lantern(self, snapshot: Snapshot, item: InventoryItem) -> bool:
        # A brass lantern in the pack while a light is already worn is a redundant
        # spare — sell it (General Store) or shed it. The equipped light lives in
        # the equipment list, not the pack, so it is never a candidate here. Keep
        # anything sensed special (a possible ego lantern) rather than dump it.
        equipped = next(
            (candidate for candidate in snapshot.equipment if candidate.is_light),
            None,
        )
        equipped_replaces_lantern = (
            equipped is not None
            and equipped.sval >= SV_LITE_LANTERN
            and self._expedition_light_ready(snapshot)
        )
        return (
            item.is_lantern
            and equipped_replaces_lantern
            and not item.is_ego
            and item.pseudo_feeling not in {"excellent", "special"}
        )



    @claims(ClaimOwner.IDENTIFICATION)
    def _verified_destroy_key(self, snapshot: Snapshot, finder, reason: str) -> str | None:
        return self._town_producer_entry(
            "verified-disposal", lambda: self._verified_destroy_dispatch_key(snapshot, finder, reason),
            family="identification")

    @claims(ClaimOwner.IDENTIFICATION)
    def _verified_destroy_dispatch_key(self, snapshot: Snapshot, finder, reason: str) -> str | None:
        """Destroy a selected item while detecting refused or stalled attempts."""
        if snapshot.in_town:
            self._claim_errand_hold("identification")
        transaction = self._equipment_transaction_session
        if (
            self._equipment_mutation.state == EquipmentMutationState.POSTED
            or (
                transaction is not None
                and transaction.pending_action is not None
            )
        ):
            self.last_reason = "inventory:destroy-deferred-equipment-mutation"
            self._offer_execution_no_step(
                producer="identification", work_id="verified-destroy",
                cause="equipment-mutation-pending",
            )
            return None

        candidate_snapshot = snapshot
        disposable = finder(candidate_snapshot)
        refused_superior = False
        while disposable is not None:
            owner = "equipment-txn" if reason.startswith("equipment:") else "identification"
            if not item_available(self, snapshot, disposable, owner, "destroy"):
                if getattr(self, "_town_claim_bar_enforced", False):
                    return None
                candidate_snapshot = replace(candidate_snapshot, inventory=[
                    item for item in candidate_snapshot.inventory if item is not disposable])
                skipped = disposable
                disposable = finder(candidate_snapshot)
                if disposable is skipped:
                    disposable = None
                continue
            if not self._entire_stack_is_surplus(candidate_snapshot, disposable):
                self._offer_execution_no_step(
                    producer="identification", work_id="verified-destroy",
                    cause="stack-not-surplus",
                )
                return None
            if self._destroy_would_discard_superior_item(snapshot, disposable):
                self.last_reason = "inventory:destroy-refused-superior-item"
                refused_superior = True
                candidate_snapshot = replace(
                    candidate_snapshot,
                    inventory=[
                        item
                        for item in candidate_snapshot.inventory
                        if item is not disposable
                    ],
                )
                disposable = finder(candidate_snapshot)
                continue
            watch = (
                self._item_signature(disposable),
                disposable.count,
                len(snapshot.inventory),
            )
            if watch == self._destroy_watch:
                self._destroy_fail_streak += 1
                if self._destroy_fail_streak >= DESTROY_FAIL_LIMIT:
                    self._undestroyable_sigs.add(self._item_signature(disposable))
                    self._destroy_watch = None
                    self._destroy_fail_streak = 0
                    disposable = finder(candidate_snapshot)
                    continue
            else:
                self._destroy_watch = watch
                self._destroy_fail_streak = 0
            self.last_reason = (
                "inventory:destroy-after-superior-item-refusal"
                if refused_superior
                else reason
            )
            key = self._destroy_item_key(disposable, snapshot, owner, policy=self)
            self._offer_execution(
                key, producer="identification",
                work_id=f"verified-destroy:{self._item_signature(disposable)}",
                next_step="inventory.destroy.send",
                arguments=(self._item_signature(disposable), disposable.count),
                expected_effect="surplus-stack-removed",
            )
            return key
        self._destroy_watch = None
        self._destroy_fail_streak = 0
        self._offer_execution_no_step(
            producer="identification", work_id="verified-destroy",
            cause="no-disposable-target",
        )
        return None

    def _destroy_would_discard_superior_item(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> bool:
        """Fail closed when destruction would discard the best comparable gear."""
        if self._item_is_procurement_protected(snapshot, item):
            return True
        counterparts = [
            candidate
            for candidate in (*snapshot.equipment, *snapshot.inventory)
            if candidate is not item
        ]
        if item.is_digging_tool:
            peers = [candidate for candidate in counterparts if candidate.is_digging_tool]
            return bool(peers) and self._digging_tool_sale_quality(item) > max(
                self._digging_tool_sale_quality(candidate) for candidate in peers
            )
        if item.tval == TVAL_BOW:
            peers = [candidate for candidate in counterparts if candidate.tval == TVAL_BOW]
            return bool(peers) and self._quest_launcher_quality(item) > max(
                self._quest_launcher_quality(candidate) for candidate in peers
            )
        if item.is_melee_weapon:
            peers = [candidate for candidate in counterparts if candidate.is_melee_weapon]
            calibration = self._validated_character_calibration(snapshot)
            quality = weapon_expected_dps(snapshot, item, 100, calibration)
            peer_qualities = [
                weapon_expected_dps(snapshot, candidate, 100, calibration)
                for candidate in peers
            ]
            known_peer_qualities = [value for value in peer_qualities if value is not None]
            if quality is None:
                return not self._is_disposable_item(
                    item, food_type=snapshot.player.food_type
                )
            return bool(known_peer_qualities) and quality > max(known_peer_qualities)
        if item.is_equipment and (
            slot_for(item) is not None
            or self._equipment_slot_group(item) is not None
            or item.tval == TVAL_RING
        ):
            if self._is_disposable_item(
                item, food_type=snapshot.player.food_type
            ) or self._is_spare_lantern(snapshot, item):
                return False
            item_group = self._equipment_slot_group(item)
            item_slot = slot_for(item)
            peers = [
                candidate
                for candidate in counterparts
                if candidate.is_equipment
                and candidate.known
                and not candidate.is_cursed
                and not candidate.is_broken
                and (
                    not item_requires_full_identification(candidate)
                    or candidate.fully_known
                )
                and (
                    (item.tval == TVAL_RING and candidate.tval == TVAL_RING)
                    or (
                        item.tval != TVAL_RING
                        and item_slot is not None
                        and slot_for(candidate) == item_slot
                    )
                    or (
                        item.tval != TVAL_RING
                        and item_slot is None
                        and item_group is not None
                        and self._equipment_slot_group(candidate) == item_group
                    )
                )
            ]
            return not any(
                self._equipment_dominates(candidate, item)
                for candidate in peers
            )
        return self._item_is_procurement_protected(snapshot, item)

    def _item_is_procurement_protected(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> bool:
        """Refuse disposal of anything the bot buys or reserves, any kind."""
        if self._retention_reservation_detail(snapshot, item)[0] > 0:
            return True
        if self._disposal_protected_by_identification(item):
            return True
        return self._item_matches_purchase_rung(snapshot, item)

    @claims(ClaimOwner.FLOOR_LOOT)
    def _floor_item_identify_key(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> str | None:
        if item.aware and item.sval >= 0:
            return None
        floor_grid = snapshot.grids.get(snapshot.player.position)
        if floor_grid is None or floor_grid.object_count != 1:
            return None
        source = self._find_identification_source(snapshot, full=False)
        if source is None:
            return None
        command, src = source
        self._look_floor_items.clear()
        self._look_floor_object_counts.clear()
        self.last_reason = "loot:identify-floor-item"
        # Hengband's item chooser uses '-' to select the floor object.
        # This completes selection without another prompt only while the game
        # option `carry_query_flag` remains off (its current default).
        if command == READ_KEY:
            return self._read_key(snapshot, src, "-")
        return command + src.slot + "-"



    def _find_cure_critical_potion(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: it.is_potion and it.aware and it.sval == SV_POTION_CURE_CRITICAL,
        )

    def _find_status_cure_potion(self, snapshot: Snapshot) -> InventoryItem | None:
        """Return the cheapest carried potion that clears confusion/blindness/cuts.

        Hengband implements Healing by calling the same cure-critical routine with
        a larger HP amount.  It is therefore a valid emergency status cure even at
        full HP.  Keep Cure Critical first so Healing is only spent when the cheap
        cure is exhausted; status treatment is intentionally independent of the
        combat-healing expected-damage gate.
        """
        return self._find_cure_critical_potion(snapshot) or self._find_exact_potion(
            snapshot, SV_POTION_HEALING
        )

    def _find_teleport_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot, lambda it: it.is_scroll and it.aware and it.sval in TELEPORT_SCROLL_SVALS
        )

    def _find_phase_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: (
                it.is_scroll and it.aware and it.sval == SV_SCROLL_PHASE_DOOR
            ),
        )

    def _has_light_equipped(self, snapshot: Snapshot) -> bool:
        return any(item.is_light for item in snapshot.equipment)

    def _find_light(
        self, snapshot: Snapshot, *, include_unknown: bool = True
    ) -> InventoryItem | None:
        light = max(
            (
                item for item in snapshot.inventory
                if self._is_usable_light(item)
                and not self._equip_blocked_by_identification(item)
            ),
            key=self._light_rank,
            default=None,
        )
        if light is not None:
            return light
        # Dungeon-found lights are unidentified, so their fuel is hidden (reads
        # as 0). With nothing else to light the way, wielding one is strictly
        # better than walking in the dark — the exact failure mode that killed
        # the torch-carrying Half-Troll.
        if not include_unknown:
            return None
        return max(
            (item for item in snapshot.inventory if item.is_light and not item.known),
            key=self._light_rank,
            default=None,
        )

    @staticmethod
    def _light_rank(item: InventoryItem) -> int:
        if item.sval >= SV_LITE_FEANOR:
            return 2
        if item.is_lantern:
            return 1
        return 0

    @staticmethod
    def _is_usable_light(item: InventoryItem) -> bool:
        # Torches and lanterns consume fuel; higher svals are permanent lights.
        # Fuel is only visible on identified lights (birth gear and store buys
        # are known); unknown ones are handled by _find_light's fallback.
        return item.is_light and (item.sval > SV_LITE_LANTERN or item.fuel > 0)

    def _light_to_wield(self, snapshot: Snapshot) -> InventoryItem | None:
        """Wield the best usable light: torch < lantern < permanent light."""
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if equipped is None:
            return self._find_light(
                snapshot,
                include_unknown=self._unknown_light_last_resort(snapshot),
            )
        candidate = self._find_light(snapshot, include_unknown=False)
        if candidate is None:
            if self._unknown_light_last_resort(snapshot):
                return self._find_light(snapshot)
            return None
        # A nearly exhausted known lantern can strand the character in town:
        # native travel consumes the last fuel before reaching the General
        # Store, while the ordinary rank comparison refuses to replace the
        # lantern with a lower-ranked but well-fuelled torch.  If no compatible
        # refill is already carried, temporarily prefer any usable spare light
        # so the shopping route can reach the oil supply.
        low_without_refill = (
            equipped.known
            and (
                (equipped.is_lantern and equipped.fuel <= LANTERN_REFILL_FUEL)
                or (equipped.sval == SV_LITE_TORCH and equipped.fuel <= TORCH_REFILL_FUEL)
            )
            and self._light_refill_item(snapshot) is None
        )
        if not low_without_refill and self._light_rank(candidate) <= self._light_rank(equipped):
            return None
        return candidate

    def _empty_lantern_to_restore(self, snapshot: Snapshot) -> InventoryItem | None:
        """Equip a carried empty lantern in town so the next action can oil it."""
        if self._owns_usable_permanent_light(snapshot):
            return None
        if self._first_item(snapshot, lambda it: it.is_oil and it.fuel > 0) is None:
            return None
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if equipped is not None and (
            equipped.sval > SV_LITE_LANTERN
            or (equipped.is_lantern and equipped.fuel > LANTERN_REFILL_FUEL)
        ):
            return None
        # Prefer an already usable lantern through the ordinary rank path.  The
        # restoration step is only for the case that every carried lantern is
        # currently excluded from `_find_light` by low/zero fuel.
        if any(
            item.is_lantern and item.known and item.fuel > LANTERN_REFILL_FUEL
            for item in snapshot.inventory
        ):
            return None
        candidates = [
            item
            for item in snapshot.inventory
            if item.is_lantern
            and not self._equip_blocked_by_identification(item)
            and item.fuel <= LANTERN_REFILL_FUEL
            and not item.is_cursed
            and not item.is_broken
        ]
        return max(
            candidates,
            key=lambda item: (item.is_artifact, item.is_ego, item.fuel),
            default=None,
        )



    def _is_dark(self, snapshot: Snapshot) -> bool:
        if snapshot.can_see_own_grid is not None:
            return (
                snapshot.dungeon_level >= 1
                and not snapshot.player.blind
                and not snapshot.can_see_own_grid
            )
        here = getattr(snapshot, "grids", {}).get(snapshot.player.position)
        return (
            snapshot.dungeon_level >= 1
            and not snapshot.player.blind
            and (
                # Real emitted own cells always carry grids_observed. Preserve
                # legacy synthetic snapshots that supplied grids without the
                # observation contract and treated their unlit default as inert.
                here is not None and snapshot.grids_observed and not here.lit
                # The emitter exports only perceivable cells. The game always
                # marks the player's own cell in view, so an observed grid set
                # that omits it means no_lite() and scroll reads are refused.
                or here is None and snapshot.grids_observed
            )
        )



    def _clear_dark_route(self) -> None:
        self._dark_route.clear()
        self._release_claim_goal(
            "dark-route-cleared", getattr(self, "_dark_route_goal", None), owners=("detectors",)
        )
        self._dark_route_goal = None
        self._dark_route_expected = None



    def _darkness_torch(self, snapshot: Snapshot) -> InventoryItem | None:
        worn = next((item for item in snapshot.equipment if item.is_light), None)
        if worn is not None and (
            worn.sval > SV_LITE_LANTERN
            or (worn.is_lantern and worn.fuel > LANTERN_REFILL_FUEL)
            or (worn.is_torch and worn.fuel > TORCH_REFILL_FUEL)
        ):
            # A fresher torch in the pack does not improve usable illumination.
            # Only the existing low-fuel rule can replace the worn torch.
            return None
        return max(
            (
                item
                for item in snapshot.inventory
                if item.is_light
                and item.sval == SV_LITE_TORCH
                and not self._equip_blocked_by_identification(item)
                and item.fuel > 0
            ),
            key=lambda item: item.fuel,
            default=None,
        )

    def _darkness_recovery_key(self, snapshot: Snapshot) -> str | None:
        if not self._is_dark(snapshot):
            # Protocol 3 reports whether the player can see their own square.
            # A stale/unlit grid flag cannot override that direct observation:
            # doing so swaps a healthy worn torch for a fresher pack torch.
            if snapshot.can_see_own_grid is not None:
                return None
            here = snapshot.grid_at(snapshot.player.position)
            legacy_unlit = (
                snapshot.dungeon_level >= 1
                and not snapshot.player.blind
                and here is not None
                and not here.lit
            )
            if not legacy_unlit:
                return None
        refill = self._light_refill_item(snapshot)
        if refill is not None:
            self.last_reason = "refill-light"
            return REFILL_KEY + refill.slot
        torch = self._darkness_torch(snapshot)
        if torch is not None:
            self.last_reason = "wield-light"
            return self._equipment_wield(
                snapshot, "light-loadout", torch, "light"
            )
        return None


    def _unknown_lantern_departure_refill_item(
        self, snapshot: Snapshot
    ) -> InventoryItem | None:
        if (
            not snapshot.in_town
            or self._unknown_lantern_departure_refilled
            or self._oil_below_departure_target(snapshot)
        ):
            return None
        equipped = next((item for item in snapshot.equipment if item.is_light), None)
        if equipped is None or equipped.known or not equipped.is_lantern:
            return None
        return self._first_item(snapshot, lambda item: item.is_oil and item.fuel > 0)

    def _oil_departure_count(self, snapshot: Snapshot) -> int:
        """Oil remaining after the refill already implied by this snapshot."""
        count = self._count_oil(snapshot)
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if (
            count > 0
            and equipped is not None
            and equipped.known
            and equipped.is_lantern
            and equipped.fuel <= LANTERN_REFILL_FUEL
        ):
            return count - 1
        return count

    # ------------------------------------------------------------------ shopping
    def _planned_depth(self) -> int:
        return self._equipment_optimization_last_depth or max(
            1, self._deepest_level + 1
        )

    @staticmethod
    def _effective_divable_depth(
        snapshot: Snapshot,
        loadout: Loadout,
        calibration: CharacterCalibration,
        *,
        has_destruction: bool,
        speed_bonus: int,
    ) -> int:
        return divable_depth(
            loadout,
            intrinsic_abilities=_effective_intrinsic_abilities(
                snapshot.player, calibration.intrinsic_abilities
            ),
            has_destruction=has_destruction,
            speed_bonus=speed_bonus,
        )


    @staticmethod
    def _recall_target(depth: int) -> int:
        if depth <= 4:
            return 3
        if depth <= 10:
            return 6
        if depth <= 15:
            return 6
        if depth <= 20:
            return 9
        return 10

    def _count_recall_scrolls(self, snapshot: Snapshot) -> int:
        return sum(it.count for it in snapshot.inventory if it.is_recall_scroll)

    def _count_teleport_scrolls(self, snapshot: Snapshot) -> int:
        return sum(it.count for it in snapshot.inventory if it.is_teleport_scroll)

    def _count_cure_critical_potions(self, snapshot: Snapshot) -> int:
        return sum(
            it.count
            for it in snapshot.inventory
            if it.is_potion
            and it.aware
            and it.sval == SV_POTION_CURE_CRITICAL
        )

    @staticmethod
    def _supply_threshold(kind: str, phase: str, depth: int) -> int:
        applicable = [
            target
            for minimum_depth, target in SUPPLY_THRESHOLDS[kind][phase]
            if depth >= minimum_depth
        ]
        # Town is depth 0, below the first expedition band.  Callers that
        # evaluate combat or store policy before choosing a planned depth must
        # still get the shallowest threshold instead of indexing an empty list.
        if not applicable:
            return SUPPLY_THRESHOLDS[kind][phase][0][1]
        return applicable[-1]






    def _destination_depth_allowed(
        self, snapshot: Snapshot, destination_depth: int
    ) -> bool:
        """Bind a deeper-floor decision and its refusal to the arrival depth."""
        missing = self._missing_required_abilities(snapshot, destination_depth)
        if not missing:
            return True
        self.last_reason = (
            f"depth-gate:destination-{destination_depth}:missing-"
            + ",".join(sorted(missing))
        )
        return False

    @staticmethod
    def _ledger_return_shortages(
        ledger: dict[str, SupplyStatus], depth: int
    ) -> list[SupplyStatus]:
        return [
            status for status in ledger.values()
            if status.kind != "recall"
            and status.count < status.required_return
            and (status.obtainable or depth > WALK_OUT_MAX_DEPTH)
        ]

    @staticmethod
    def _ledger_departure_shortages(
        ledger: dict[str, SupplyStatus]
    ) -> list[SupplyStatus]:
        return [
            status for status in ledger.values()
            if status.count < status.required_departure and status.obtainable
        ]

    def _count_treasure_detection_scrolls(self, snapshot: Snapshot) -> int:
        return sum(
            it.count for it in snapshot.inventory if it.is_treasure_detection_scroll
        )

    def _count_usable_torches(self, snapshot: Snapshot) -> int:
        return sum(
            it.count
            for it in snapshot.inventory
            if it.is_light and it.sval == 0 and it.known and it.fuel > 0
        )

    def _has_digging_tool(self, snapshot: Snapshot) -> bool:
        return any(
            it.is_digging_tool and not self._equip_blocked_by_identification(it)
            for it in snapshot.inventory
        ) or any(
            it.is_digging_tool and not self._equip_blocked_by_identification(it)
            for it in snapshot.equipment
        )

    def _digging_tool_count(self, snapshot: Snapshot) -> int:
        return sum(
            it.count for it in snapshot.inventory
            if it.is_digging_tool and not self._equip_blocked_by_identification(it)
        ) + sum(
            1 for it in snapshot.equipment
            if it.is_digging_tool and not self._equip_blocked_by_identification(it)
        )




    def _digger_buy_fallback_available(self, snapshot: Snapshot) -> bool:
        """Allow one visible replacement only while total stock is short.

        Two failed Home takes release the bot from retrying an unreachable
        address; they do not make known Home stock disappear.  A successful
        fallback buy can itself raise carried + withdrawable Home stock to the
        two-digger target, so every consumer must recheck that ceiling before
        routing or selecting another shop purchase.
        """
        return (
            self._digger_home_withdraw_failures >= 2
            and not self._digger_fallback_bought_this_visit
            and self._withdrawable_digging_tool_count(snapshot) < 2
        )






    @staticmethod
    def _stack_charges(item: InventoryItem) -> int:
        """Return total charges represented by an inventory stack."""
        return max(0, item.charges) * max(1, item.count)


    def _food_ready(self, snapshot: Snapshot) -> bool:
        status = self._supply_ledger(snapshot, self._planned_depth())["food"]
        return status.count >= status.required_departure




    def _can_read_scrolls(self, snapshot: Snapshot) -> bool:
        """Return whether Hengband permits reading on the current grid now."""
        if not self._is_dark(snapshot):
            return True
        equipped = next((item for item in snapshot.equipment if item.is_light), None)
        if equipped is None and not snapshot.equipment_observed:
            # Direct legacy Snapshot constructors predate equipment presence
            # tracking. Live parsed snapshots always mark this channel observed.
            return True
        if equipped is not None and (
            equipped.sval > SV_LITE_LANTERN or equipped.fuel > 0
        ):
            return True
        return False

    def _recall_ready(self, snapshot: Snapshot) -> bool:
        status = self._supply_ledger(snapshot, self._planned_depth())["recall"]
        return status.count >= status.required_departure

    def _recall_departure_ready(self, snapshot: Snapshot) -> bool:
        """Whether recall stock meets the depth-banded departure requirement."""
        status = self._supply_ledger(snapshot, self._planned_depth())["recall"]
        return status.count >= status.required_departure

    def _recall_departure_shortage(self, snapshot: Snapshot) -> bool:
        status = self._supply_ledger(snapshot, self._planned_depth())["recall"]
        return status.count < status.required_departure

    @staticmethod
    def _recall_shortage_retreat_threshold(depth: int) -> int:
        return 1 if depth <= 5 else RECALL_RETURN_THRESHOLD

    def _recall_shortage_opening_exempt(self, snapshot: Snapshot) -> bool:
        return (
            snapshot.player.class_id < 0
            or self._opening_q34_active(snapshot)
        )

    def _recall_destination_safe(
        self, snapshot: Snapshot, dungeon_id: int
    ) -> bool:
        """Reject recall when its landing floor violates mandatory depth gates.

        It also rejects a landing that is a guardian floor the current kit
        cannot pass.  Such a recall is answered at once by the
        guardian-kit-insufficient return (live 2026-09-25 06:22:31: the
        conquest latch held the Orc cave after the kit that made its guardian
        beatable was changed, and the recall landed on 23, its guardian
        floor).  ``_recall_refused_only_for_guardian`` tells that refusal
        apart.
        """
        depth = self._dungeon_entry_depth(snapshot, dungeon_id, via_recall=True)
        if self._missing_required_abilities(snapshot, depth):
            return False
        return not self._recall_landing_guardian_blocked(snapshot, dungeon_id, depth)

    def _recall_refused_only_for_guardian(
        self, snapshot: Snapshot, dungeon_id: int
    ) -> bool:
        """Whether the landing passes the depth gates but is a blocked guardian floor."""
        depth = self._dungeon_entry_depth(snapshot, dungeon_id, via_recall=True)
        return (
            not self._missing_required_abilities(snapshot, depth)
            and self._recall_landing_guardian_blocked(snapshot, dungeon_id, depth)
        )

    def _recall_landing_guardian_blocked(
        self, snapshot: Snapshot, dungeon_id: int, depth: int
    ) -> bool:
        """Whether a recall to ``dungeon_id`` lands on a blocked guardian floor."""
        return self._guardian_floor_blocked(snapshot, dungeon_id, depth)

    def _recall_departure_minimum(self, snapshot: Snapshot) -> int:
        """Hard minimum that must remain available when leaving town."""
        status = self._supply_ledger(snapshot, self._planned_depth())["recall"]
        return status.required_departure

    def _recall_required_target(self, snapshot: Snapshot) -> int:
        if self._fundraising_mode in {"mine", "scavenge"}:
            return 0
        return self._recall_target(self._planned_depth())

    def _taken_kill_quest_requires_walk_in(self, snapshot: Snapshot) -> bool:
        """Enter above a taken kill objective instead of recalling below it."""
        return any(
            quest.id in FIXED_QUEST_ALLOWLIST
            and quest.status == QUEST_STATUS_TAKEN
            and (info := self._quest_knowledge.get(quest.id)) is not None
            and info.type in {QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER}
            and info.dungeon == self._target_dungeon_id
            and info.level < snapshot.recall_depth
            for quest in snapshot.quests.values()
        )

    def _teleport_target(self, snapshot: Snapshot) -> int:
        # 10F+ escapes constantly, so carry a deep buffer; shallower runs need few.
        if self._planned_depth() >= STAFF_IDENTIFY_MIN_DEPTH:
            return TELEPORT_SCROLL_DEEP_TARGET
        return TELEPORT_SCROLL_TARGET

    def _teleport_ready(self, snapshot: Snapshot) -> bool:
        status = self._supply_ledger(snapshot, self._planned_depth())["teleport"]
        return status.count >= status.required_departure

    def _cure_critical_ready(self, snapshot: Snapshot) -> bool:
        status = self._supply_ledger(snapshot, self._planned_depth())["cure"]
        if status.count >= status.required_departure:
            return True
        # Keep the normal target strict while either supplier remains unchecked.
        # Once Temple and Alchemist are both known unavailable, however, a
        # one-potion shortfall is safer than an unbounded restock wait in town.
        return (
            status.count == status.required_departure - 1
            and not status.obtainable
        )

    @staticmethod
    def _count_potion(snapshot: Snapshot, sval: int) -> int:
        return sum(
            item.count
            for item in snapshot.inventory
            if item.is_potion and item.aware and item.sval == sval
        )

    @staticmethod
    def _cure_critical_target(depth: int) -> int:
        if depth >= CURE_CRITICAL_DEEP_DEPTH:
            return CURE_CRITICAL_DEEP_TARGET
        return CURE_CRITICAL_TARGET

    def _total_identify_staff_charges(self, snapshot: Snapshot) -> int:
        return sum(
            self._stack_charges(it)
            for it in snapshot.inventory
            if it.tval == TVAL_STAFF
            and it.aware
            and it.sval == SV_STAFF_IDENTIFY
        )

    def _owns_identify_staff(self, snapshot: Snapshot) -> bool:
        return self._total_identify_staff_charges(snapshot) > 0



    def _outstanding_equipment_work(self) -> bool:
        """Return whether the equipment lifecycle retains its Home allowance.

        This scope describes work that remains, not why optimization is stuck.
        In particular, optimizer success can open the transaction that applies
        its result; that success must not revoke the Home allowance the new
        session needs to execute.
        The allowance spans outside equip and posted observations; route and
        store-need projections separately ask for the current Home action.
        """
        preparation = self._equipment_optimization_preparation
        # R1: an unavailable calibration skips optimization; it is not work
        # that owns a Home route or can exhaust one.
        blockers = tuple(
            blocker for blocker in getattr(preparation, "blockers", ())
            if not (blocker == "calibration-required"
                    or blocker.startswith("calibration-stale:"))
        )
        optimization_already_applied = self._optimization_already_applied(preparation)
        return bool(blockers and (not optimization_already_applied) or (self._equipment_transaction_session is not None and not self._equipment_transaction_session.complete) or self._home_pending_item is not None or self._home_pending_batch or (self._home_atomic_withdraw_pending is not None) or (self._home_atomic_deposit_pending is not None))

    @staticmethod
    def _optimization_already_applied(preparation: object | None) -> bool:
        """Return whether the selected loadout is exactly the worn loadout."""
        result = getattr(preparation, "result", None)
        best = getattr(result, "best", None)
        current = getattr(preparation, "current", None)
        target = getattr(best, "loadout", None)
        transaction = getattr(preparation, "transaction", None)
        return bool(
            isinstance(current, Loadout)
            and isinstance(target, Loadout)
            and current.slots == target.slots
            and (
                transaction is None
                or (
                    isinstance(transaction, EquipmentTransactionPlan)
                    and not transaction.actions
                )
            )
        )

    def calibration_entry_state(self, snapshot: Snapshot) -> dict[str, object]:
        return {"source": "equipped-c-screen", "schema_version": 2,
                "pending": self._calibration_dump_pending is not None,
                "unavailable_reason": self._calibration_unavailable_reason}

    def equipment_transaction_entry_state(
        self, snapshot: Snapshot
    ) -> dict[str, object]:
        """Bounded diagnostics for equipment transaction's town gate."""
        session = self._equipment_transaction_session
        blocker = None
        if not snapshot.in_town:
            blocker = "not-in-town"
        elif (
            snapshot.store is not None
            and not (
                session is not None
                and session.required_context == "home"
                and snapshot.store.store_type == STORE_HOME
            )
        ):
            blocker = "inside-store"
        elif session is None:
            blocker = "no-session"
        elif not session.executable:
            blocker = "session-not-executable"
        elif session.pending_action is not None:
            blocker = "action-awaiting-confirmation"
        return {
            "context": session.required_context if session is not None else None,
            "entry_blocker": blocker,
        }





    def _set_equipment_transaction_session(
        self, session: EquipmentTransactionSession | None
    ) -> None:
        """Install a plan; the plan may request but never re-arm a Home visit."""
        previous = self._equipment_transaction_session
        if session is not previous:
            self._equipment_transaction_posted_catalog_update = None
            self._equipment_transaction_home_pages = None
        self._equipment_transaction_session = session
        if session is not None and session is not previous:
            action = getattr(session, "current_action", None)
            if action is not None:
                self._offer_execution(
                    "", producer="equipment-txn",
                    work_id=f"equipment-session:{self._decision_sequence}",
                    next_step="equipment.next-action",
                    arguments=(action.kind, action.item_identity),
                    expected_effect=f"equipment-effect:{action.kind}",
                    continuation="equipment.next-action",
                    budget_ref="equipment-session",
                )
        if session is not previous:
            self._equipment_atomic_withdraw_leave_count = 0
        if (
            session is None
            or session is previous
            or not session.executable
            or session.required_context != "home"
        ):
            return
        # _derived_home_visit_request snapshots this session on the next
        # outside observation.  In particular, do not pop STORE_HOME or rebuild
        # the route: those are visit history and a replacement optimizer
        # session has no authority to reset them.
        if (
            self._town_blocked_reason is not None
            and self._town_blocked_reason.startswith("equipment-")
        ):
            self._town_blocked_reason = None


    def equipment_optimization_state(
        self, snapshot: Snapshot | None = None
    ) -> dict[str, object]:
        catalog = self._equipment_catalog.items
        preparation = (
            self._prepare_equipment_optimization(snapshot)
            if snapshot is not None
            else self._equipment_optimization_preparation
        )
        session = self._equipment_transaction_session
        state: dict[str, object] = {
            "calibration": (
                self.calibration_entry_state(snapshot) if snapshot is not None else {'source': 'equipped-c-screen', 'schema': 2, 'pending': False, 'unavailable_reason': None}
            ),
            "equipment_transaction": (
                self.equipment_transaction_entry_state(snapshot)
                if snapshot is not None
                else {
                    "phase": (
                        session.required_context if session is not None else None
                    ),
                    "entry_blocker": None,
                }
            ),
            "home_scan_complete": self._equipment_catalog.home_scan_complete,
            "home_knowledge_current": self._home_knowledge_current,
            "home_knowledge_invalidated": self._home_knowledge_invalidated,
            "catalog_items": len(catalog),
            "incomplete_items": sum(
                item.identification_incomplete for item in catalog
            ),
            "incomplete_item_details": [
                {
                    "id": owned.id,
                    "origin": owned.origin,
                    "slot": owned.equipped_slot,
                    "tval": owned.item.tval,
                    "sval": owned.item.sval,
                    "known": owned.item.known,
                    "fully_known": owned.item.fully_known,
                    "processed": (
                        self._item_signature(owned.item)
                        in self._processed_home_items
                    ),
                    "retried": (
                        self._item_signature(owned.item)
                        in self._retried_home_identification_items
                    ),
                }
                for owned in catalog
                if owned.identification_incomplete
            ],
            "catalog_tval_counts": {
                str(tval): sum(owned.item.tval == tval for owned in catalog)
                for tval in sorted({owned.item.tval for owned in catalog})
            },
            "evaluator": "warrior-composite-confirmed-transaction-execution-enabled",
            # Quarantine visibility (2026-08-02 20:06 stop was undiagnosable
            # without these): the two live quarantine sets and any last-source
            # readmissions the optimizer view performed.  Strictly diagnostic.
            "failed_transaction_item_ids": sorted(
                key for key in self._equipment_transaction_failed_items
                if not key.startswith("identity:")
            ),
            "failed_transaction_item_identities": sorted(
                key.removeprefix("identity:")
                for key in self._equipment_transaction_failed_items
                if key.startswith("identity:")
            ),
            "deferred_home_item_signatures": [
                list(signature)
                for signature in sorted(self._deferred_home_items)
            ],
            "quarantine_readmitted_item_ids": list(
                self._equipment_quarantine_readmitted_ids
            ),
            "quarantine_second_chance_item_ids": sorted(
                key for key in self._equipment_quarantine_second_chance_ids
                if not key.startswith("identity:")
            ),
            "quarantine_second_chance_item_identities": sorted(
                key.removeprefix("identity:")
                for key in self._equipment_quarantine_second_chance_ids
                if key.startswith("identity:")
            ),
            "quarantine_burned_item_ids": sorted(
                key for key in self._equipment_quarantine_burned_ids
                if not key.startswith("identity:")
            ),
            "quarantine_burned_item_identities": sorted(
                key.removeprefix("identity:")
                for key in self._equipment_quarantine_burned_ids
                if key.startswith("identity:")
            ),
            "home_procurement": dict(getattr(self, "_home_procurement_approach_state", {})),
            "home_route_projection": {
                "home_owner_goal_pending": (
                    self._home_owner_goal_pending(snapshot)
                    if snapshot is not None else None
                ),
                "equipment_work_need_present": (
                    any(
                        need.category in {
                            "equipment-work", "equipment-transaction"
                        }
                        for need in self._enumerate_live_store_claims(snapshot)
                    )
                    if snapshot is not None else None
                ),
                "equipment_work_home_route_available": (
                    self._equipment_work_home_route_available()
                ),
                "outstanding_equipment_work": self._outstanding_equipment_work(),
                "town_plan_exhausted": (
                    self._town_errand_plan is not None
                    and self._town_errand_plan.index
                    >= len(self._town_errand_plan.stops)
                ),
                "home_approach_fails": self._town_visit_ledger.approach_fails[
                    STORE_HOME
                ],
                "home_visit_limit": self._town_store_visit_limit(STORE_HOME),
                "home_unsatisfied_passes": (
                    self._town_visit_ledger.unsatisfied_passes[STORE_HOME]
                ),
                "home_blocked": (
                    STORE_HOME in self._town_visit_ledger.blocked_stores
                ),
                "projection": dict(getattr(
                    self,
                    "_town_plan_projection_telemetry",
                    {"evaluated": False, "plan_rebuilt": False, "rebuilt_stops": []},
                )),
            },
        }
        state.update(self._equipment_optimization_telemetry)
        if snapshot is not None and (
            snapshot.player.class_id != PLAYER_CLASS_WARRIOR
            or not snapshot.in_town
        ):
            state["search_telemetry_freshness"] = "stale-republished"
        if state.get("result_source") != "fresh-search":
            state.pop("fresh_search_transition", None)
        if preparation is not None:
            if snapshot is not None:
                state["optimization_depth"] = self._equipment_optimization_depth(
                    snapshot
                )
            state["blockers"] = list(preparation.blockers)
            if "no-valid-loadout" in preparation.blockers:
                state["required_gate_sources"] = (
                    self._required_gate_source_report(snapshot)
                )
                state["required_gate_search_surviving_sources"] = [
                    {
                        "gate": entry["gate"],
                        "flag": entry["flag"],
                        "search_surviving_sources": sum(
                            item.id
                            in self._equipment_optimization_search_surviving_ids
                            for item in catalog
                            if entry["flag"] in item.flags
                        ),
                    }
                    for entry in state["required_gate_sources"]
                ]
            state["encounters_total"] = preparation.encounters_total
            state["encounters_evaluated"] = preparation.encounters_evaluated
            state["optimization_timed_out"] = bool(
                preparation.result is not None and preparation.result.timed_out
            )
            if preparation.result is not None:
                state["optimization_search"] = {
                    "considered": preparation.result.combinations_considered,
                    "evaluated": preparation.result.combinations_evaluated,
                    "invalid": preparation.result.invalid_combinations,
                    "elapsed_seconds": preparation.result.elapsed_seconds,
                    "truncated": preparation.result.search_truncated,
                }
            state["transaction_actions"] = (
                len(preparation.transaction.actions)
                if preparation.transaction is not None
                else 0
            )
        if session is not None:
            action = session.current_action
            pending = session.pending_action
            state["transaction_context"] = session.required_context
            state["transaction_next"] = (
                None
                if action is None
                else {
                    "phase": action.phase,
                    "kind": action.kind,
                    "item_id": action.item_id,
                    "target_slot": action.target_slot,
                }
            )
            state["transaction_pending"] = (
                None
                if pending is None
                else {
                    "phase": pending.phase,
                    "kind": pending.kind,
                    "item_id": pending.item_id,
                    "target_slot": pending.target_slot,
                }
            )
            state["transaction_target_loadout_id"] = session.target_loadout_id
            state["transaction_applied"] = session.complete
            state["transaction_unconfirmed_observations"] = (
                session.unconfirmed_observations
            )
            state["transaction_posted_command_id"] = session.posted_command_id
            state["transaction_posted_context"] = (
                session.posted_context_identity
            )
        if self._equipment_transaction_last_failure is not None:
            state["transaction_last_failure"] = dict(
                self._equipment_transaction_last_failure
            )
        optional_failure = (self._equipment_optional_failure_departure
                            or self._equipment_optional_failure_pending)
        if optional_failure is not None:
            state["optional_failure_departure"] = dict(optional_failure)
        if self._equipment_transaction_restore_remainder:
            state["transaction_restore_remainder"] = list(
                self._equipment_transaction_restore_remainder
            )
        return state

    def _required_gate_source_report(
        self, snapshot: Snapshot | None
    ) -> list[dict[str, object]]:
        """Census of owned sources for every mandatory depth gate (diagnostic).

        Emitted with a no-valid-loadout blocker so a live capture shows which
        required flag lost its sources and to which quarantine each source
        belongs.  Never gates behaviour.
        """
        depth = (
            self._equipment_optimization_depth(snapshot)
            if snapshot is not None
            else self._equipment_optimization_last_depth
        )
        if depth is None:
            return []
        report: list[dict[str, object]] = []
        for ability in sorted(required_depth_gates(depth)):
            flag = RESIST_FLAG_BY_ABILITY.get(ability)
            if flag is None:
                continue
            sources = [
                item
                for item in self._equipment_catalog.items
                if flag in item.flags
            ]
            report.append({
                "gate": ability,
                "flag": flag,
                "owned_sources": len(sources),
                "operational_sources": sum(
                    operational_equipment_candidate(item) for item in sources
                ),
                "failed_quarantined_ids": sorted(
                    item.id
                    for item in sources
                    if self._equipment_memory_contains(
                        self._equipment_transaction_failed_items, item
                    )
                ),
                "deferred_home_ids": sorted(
                    item.id
                    for item in sources
                    if item.origin == "home"
                    and self._item_signature(item.item)
                    in self._deferred_home_items
                ),
                "burned_ids": sorted(
                    item.id
                    for item in sources
                    if self._equipment_memory_contains(
                        self._equipment_quarantine_burned_ids, item
                    )
                ),
            })
        return report

    def _block_equipment_transaction(self, reason: str) -> None:
        session = self._equipment_transaction_session
        if session is not None:
            session.block(reason)
        self._town_blocked_reason = f"equipment-transaction:{reason}"




    def confirm_key_posted(self, key: str) -> bool:
        """Commit policy state whose command was successfully posted by CLI."""
        pending_execution = getattr(self, "_execution_pending_post", None)
        self._execution_pending_post = None
        if pending_execution is not None and pending_execution[1] == key:
            claim = getattr(self._claim_register, "current", None)
            if (claim is not None and claim.claim_id == pending_execution[0]
                    and claim.execution is not None
                    and claim.execution.work_id == pending_execution[2]):
                declaration = claim.execution
                self._claim_register.declare_execution(
                    claim.claim_id, work_id=declaration.work_id,
                    producer=declaration.producer, state="awaiting",
                    arguments=declaration.arguments,
                    # Entry dispatch waits for the page without posting the
                    # staged purchase/sale operation.
                    operation_ref=(
                        None if declaration.next_step == "shop.one-shot.dispatch"
                        else f"decision:{self._decision_sequence}:{key}"
                    ),
                    expected_effect=declaration.expected_effect,
                    continuation=declaration.continuation or declaration.next_step,
                    budget_ref=declaration.budget_ref,
                )
        self._confirm_staged_shopping_approach(key)
        if (
            self._store_visit is not None
            and self._store_visit.operation_posted
            and key == self._store_visit.operation_key
        ):
            # Executor completion means every owned segment has retired and a
            # fresh board is ready for same-loop business reconciliation.
            self._store_visit.operation_released = True
        if key.startswith(FIRE_KEY):
            # The ledger establishes that no bolt was visible on these cells
            # since the last policy-composed launcher shot. It cannot prove
            # absence after every possible source of a bolt.
            self._q2_blue_recovery_perceived.clear()
        read_binding = self._read_binding
        board = self._decision_input_snapshot
        self._confirm_optional_equipment_failure_departure(board, key)
        if (
            key.startswith(READ_KEY)
            and read_binding is not None
            and read_binding[0] == TVAL_SCROLL
            and read_binding[1] == SV_SCROLL_TELEPORT
            and board is not None
            and not board.in_town
        ):
            # The player's own Teleportation read: its landing is observed on
            # a later board as the stack one scroll smaller and the player two
            # or more cells from here.
            self._teleport_read_watch = (
                board.floor_key,
                board.player.position,
                board.turn,
                sum(
                    item.count
                    for item in board.inventory
                    if item.tval == TVAL_SCROLL
                    and item.sval == SV_SCROLL_TELEPORT
                ),
            )
        if (
            self._quest_strategy_recovery_pickup_prepared
            and key == getattr(
                self, "_quest_strategy_recovery_pickup_prepared_key", None
            )
        ):
            self._quest_strategy_recovery_pickup_posted = (
                self._quest_strategy_recovery_pickup_prepared
            )
            self._quest_strategy_recovery_pickup_prepared = None
            self._quest_strategy_recovery_pickup_prepared_key = None
        mutation_committed = self._equipment_mutation.confirm_posted(key)
        pending_mutation_commit = self._equipment_mutation_post_commit
        if (
            mutation_committed
            and pending_mutation_commit is not None
            and pending_mutation_commit[0] == key
        ):
            if pending_mutation_commit[1] == "breakout-restore":
                self._breakout_dig_floor = None
            elif pending_mutation_commit[1] == "no-teleport-rearm":
                self._no_teleport_rearm_pending = False
            self._equipment_mutation_post_commit = None
        if (
            self._store_entry_wait_owner is not None
            and self._store_visit is not None
            and getattr(self._store_visit, "armed_sequence", None)
            == self._decision_sequence
            and key == (self._store_entry_wait_key or WAIT_KEY)
        ):
            self._store_entry_posted_owner = self._store_entry_wait_owner
            armed_turn = self._store_entry_wait_turn
            if armed_turn is not None:
                self._store_visit.posted_turn = armed_turn
            if (
                self._store_visit.operation_posted
                and self._store_visit.operation_released
                and key == self._store_visit.composed_key
            ):
                # A composed entry+operation+leave macro has no intermediate
                # store page for the entry barrier to observe. Preserve the
                # operation ledger for outside effect reconciliation, but
                # retire ENTERING after acknowledging the whole posted macro.
                self._store_visit.transition(StoreVisitPhase.APPROACHING)
                self._intentional_entrance_activation = False
            if key != self._equipment_transaction_prepared_key:
                return True
        if key in {"~9\x1b\x1b", HOME_KNOWLEDGE_MACRO}:
            self._home_knowledge_scan_requested = True
            self._home_knowledge_scan_inflight = True
            self._home_knowledge_scan_epoch = self._town_visit_epoch
            return True
        if key == SKILL_KNOWLEDGE_MACRO:
            self._skill_exp_request_inflight = True
            return True
        if key in {CHARACTER_DUMP_MACRO, HOME_CHARACTER_DUMP_MACRO}:
            prepared = self._calibration_dump_prepared
            self._calibration_dump_pending = {
                "baseline": prepared["baseline"] if prepared else None,
                "started_ns": prepared["started_ns"] if prepared else None,
                "sequence": self._character_response_sequence,
            }
            return True
        if key != self._equipment_transaction_prepared_key:
            return mutation_committed
        session = self._equipment_transaction_session
        committed = session is not None and session.confirm_posted(key)
        if (getattr(self, "_town_claim_bar_enforced", False)
                and committed and session is not None):
            visit = self._store_visit
            if (visit is not None and visit.store_type == STORE_HOME
                    and visit.operation_posted
                    and (visit.operation_key in (None, key)
                         or (visit.operation_effect_observed
                             and visit.operation_released
                             and visit.operation_producer_family == "equipment-txn"))
                    and visit.operation_producer_family in (None, "equipment-txn")
                    and session.pending_action is not None):
                visit.operation_key = key
                visit.operation_producer_family = "equipment-txn"
                visit.operation_effect_observed = False
                visit.operation_released = False
                visit.claim_operation_identity = (
                    STORE_HOME, visit.opened_sequence,
                    session.target_loadout_id, session.index, key,
                )
        if committed and self._equipment_transaction_prepared_catalog_update is not None:
            kind, item, intent = self._equipment_transaction_prepared_catalog_update
            self._equipment_transaction_posted_catalog_update = (
                session.target_loadout_id, session.index, key, kind, item, intent)
        self._equipment_transaction_prepared_key = None
        self._equipment_transaction_prepared_catalog_update = None
        return committed or mutation_committed

    def reconcile_input_operation(self, owner: str, business_outcome: str | None) -> None:
        """Apply an executor-proven business result before the next decision."""
        if (
            owner.startswith("equipment-transaction:")
            and business_outcome in {"refused", "cancelled", "failed"}
        ):
            self._equipment_transaction_operation_outcome = business_outcome
        if owner == "shop:one-shot-buy" and business_outcome == "failed:purchase-refused":
            self._store_buy_inflight = None
            self._close_store_visit("one-shot-buy-refused")
        self._in_store_reconcile(owner, business_outcome)

    def peek_staged_prompt_chain(self) -> dict | None:
        """Return the current decision's prompt chain without consuming it."""
        return self._staged_prompt_chain

    def commit_staged_prompt_chain(self, result: dict) -> dict:
        """Record a transport outcome and clear the current prompt chain."""
        chain = self._staged_prompt_chain
        self._staged_prompt_chain = None
        if chain is None:
            return dict(result)
        owner = self._claim_family_of(chain["owner"])
        if result.get("outcome") == "released":
            self._complete_observed_effect(
                "staged-tail-posted", owners=(owner,),
                sources=(CLAIM_OBSERVE_STORE_OPERATION,),
            )
        else:
            self._release_claim_goal(
                "staged-tail-dropped", owners=(owner,),
                kinds=(CLAIM_GOAL_OBSERVE,),
                sources=(CLAIM_OBSERVE_STORE_OPERATION,),
            )
        return {
            **result,
            "owner": chain["owner"],
            "sequence": chain["sequence"],
            "turn": chain["turn"],
            "gates": chain["gates"],
        }

    def consume_pending_mutation_report(self) -> str | None:
        """Return the mutation report produced during this decision, once."""
        report = self._pending_mutation_report
        self._pending_mutation_report = None
        return report


    def consume_pending_hunt_report(self) -> str | None:
        """Return the hunt-abandonment report produced this decision, once."""
        report = self._pending_hunt_report
        self._pending_hunt_report = None
        return report


    def refuse_key_posting(self, owner: str, key: str) -> None:
        """Make a sender-side refusal actionable on the next policy decision."""
        pending_execution = getattr(self, "_execution_pending_post", None)
        self._execution_pending_post = None
        if pending_execution is not None and pending_execution[1] == key:
            claim = getattr(self._claim_register, "current", None)
            if (claim is not None and claim.claim_id == pending_execution[0]
                    and claim.execution is not None
                    and claim.execution.work_id == pending_execution[2]
                    and claim.execution.state == "acting"):
                declaration = claim.execution
                self._claim_register.declare_execution(
                    claim.claim_id, work_id=declaration.work_id,
                    producer=declaration.producer, state="acting",
                    next_step="transport.resolve-refusal",
                    arguments=(owner, key),
                    expected_effect=declaration.expected_effect,
                    continuation=declaration.continuation,
                    budget_ref=declaration.budget_ref,
                    evidence="posting-refused",
                )
        # The posting contract correctly refuses an identical key/effect pair.
        # Interleave the existing look probe while the issuing progress core is
        # frozen so a recovered modal cannot make that refusal absorbing.
        pending = self._owner_expectations._pending.get(owner)
        if pending is None and owner.startswith("equipment-transaction:"):
            pending = self._owner_expectations._pending.get(
                "equipment-transaction"
            )
        if pending is not None:
            self._posting_refusal_probe = (owner, pending.progress_core)
        else:
            core = self._last_policy_progress_core
            if core is not None:
                self._posting_refusal_probe = (owner, core)
        if key and key[0] in {UP_STAIRS_KEY, DOWN_STAIRS_KEY}:
            self._owner_expectations.release("stair-command")
        if owner == "return:recall" and key.startswith(READ_KEY):
            self._owner_expectations.yield_owner(owner)
            # The command was not posted, so there is nothing to await.  The
            # refusal latch above makes the existing walk-out route the next
            # return action without guessing why Hengband ignored the read.
            self._dungeon_recall_issue_watch = None
        if owner in {"shop:travel", "town:travel-entrance"}:
            state = self._town_travel_state
            if state is not None:
                self._town_travel_fallback = state.goal
                self._release_town_travel_claim("town-travel:posting-refused")
                self._town_travel_state = None
        if (
            owner in {"shop:leave", "shop:await-leave-confirmation"}
            and self._store_buy_inflight is not None
        ):
            # A buy prompt is still owned by the purchase that raised it.  If
            # a leave flow raced that prompt, restore the purchase observation
            # window so the fallback decision is the prompt owner's bounded
            # await, never another foreign Escape.
            store, signature, count, gold, _waits, _generation = (
                self._store_buy_inflight
            )
            self._store_buy_inflight = (
                store, signature, count, gold, 0, self._decision_sequence
            )
        self._discard_unposted_equipment_transaction_command()

    def _discard_unposted_equipment_transaction_command(self) -> None:
        self._equipment_transaction_prepared_key = None
        self._equipment_transaction_prepared_catalog_update = None
        session = self._equipment_transaction_session
        if session is not None and hasattr(session, "discard_prepared"):
            session.discard_prepared()




    def _release_equipment_transaction_owned_item(self, identity: str) -> None:
        """Release one physical member of a duplicate-preserving owned set."""
        for index, (owned_identity, _) in enumerate(
            self._equipment_transaction_owned_items
        ):
            if owned_identity == identity:
                del self._equipment_transaction_owned_items[index]
                return


    @claims(ClaimOwner.EQUIPMENT_TXN)
    def _release_stalled_equipment_transaction(
        self, snapshot: Snapshot | None = None
    ) -> bool:
        """Release a posted action after the reviewed store observation budget."""
        session = self._equipment_transaction_session
        if (
            session is None
            or session.pending_action is None
            or session.unconfirmed_observations
            < EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT
        ):
            return False
        action = session.pending_action
        self._equipment_transaction_last_failure = {
            "reason": "confirmation-stall-bound",
            "applied": False,
            "phase": action.phase,
            "kind": action.kind,
            "item_id": action.item_id,
            "target_slot": action.target_slot,
            "item_identity": action.item_identity,
            "observations": session.unconfirmed_observations,
            "budget": EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
            "bound": "STORE_STUCK_LIMIT",
            "target_loadout_id": session.target_loadout_id,
        }
        self._equipment_mutation.release()
        self._release_claim_goal(
            "confirmation-stall-bound", owners=("equipment-txn",),
            kinds=(CLAIM_GOAL_OBSERVE,),
            sources=("transaction", CLAIM_OBSERVE_STORE_OPERATION),
        )
        self._abandon_blocked_equipment_transaction(snapshot)
        self.last_reason = "equipment-transaction:confirmation-stall-bound"
        return True



    @claims(ClaimOwner.EQUIPMENT_TXN)
    def _invalidate_stale_equipment_transaction(
        self,
        snapshot: Snapshot,
        action: EquipmentTransaction,
        observed_identity: str | None,
    ) -> None:
        """Re-derive a plan when its current letter no longer names its item."""
        self._equipment_transaction_failed_items.update(
            self._equipment_action_memory_keys(action)
        )
        self._equipment_transaction_route_terminal_pending = False
        self._discard_unposted_equipment_transaction_command()
        self._set_equipment_transaction_session(None)
        self._equipment_optimization_signature = None
        self._equipment_optimization_preparation = None
        self._equipment_optimization_pack_items = None
        self._prepare_equipment_optimization(snapshot)
        self.last_reason = (
            "equipment-transaction:stale-identity-invalidated:"
            f"{action.kind}:{observed_identity or 'missing'}"
        )

    @staticmethod
    def _temporary_status_clear(snapshot: Snapshot) -> bool:
        player = snapshot.player
        return not any(
            (
                player.blind,
                player.confused,
                player.afraid,
                player.poisoned,
                player.stunned,
                player.cut,
                player.paralyzed,
                player.hallucinated,
            )
        )








    def _current_worn_loadout_confirmed(
        self, snapshot: Snapshot, preparation: object | None
    ) -> bool:
        """Match live snapshot equipment to the disk-backed confirmation."""
        live_carried = OwnedEquipmentCatalog()
        live_carried.refresh_carried(snapshot.inventory, snapshot.equipment)
        current = current_loadout(live_carried.items)
        result = getattr(preparation, "result", None)
        best = getattr(result, "best", None)
        if best is not None and not isinstance(getattr(best, "loadout", None), Loadout):
            return False
        record = self._validated_confirmed_loadout()
        return bool(
            current.item_ids
            and record is not None
            and current.item_ids == record.item_ids
            and self._equipment_optimizer_input_key is not None
            and self._equipment_optimizer_input_key == record.optimizer_input_key
        )

    def _validated_confirmed_loadout(self) -> ConfirmedLoadoutRecord | None:
        if not self._confirmed_loadout_loaded and self._confirmed_loadout_path is not None:
            self._confirmed_loadout = load_confirmed_loadout(self._confirmed_loadout_path)
            self._confirmed_loadout_loaded = True
        return self._confirmed_loadout

    def _record_confirmed_loadout(self, snapshot: Snapshot) -> None:
        live_carried = OwnedEquipmentCatalog()
        live_carried.refresh_carried(snapshot.inventory, snapshot.equipment)
        item_ids = current_loadout(live_carried.items).item_ids
        optimizer_input_key = self._equipment_optimizer_input_key
        if not item_ids or optimizer_input_key is None:
            return
        existing = self._validated_confirmed_loadout()
        if (
            existing is not None
            and existing.item_ids == item_ids
            and existing.optimizer_input_key == optimizer_input_key
        ):
            return
        record = confirmed_loadout_record(item_ids, optimizer_input_key)
        if self._confirmed_loadout_path is None:
            return
        if not save_confirmed_loadout(self._confirmed_loadout_path, record):
            return
        self._confirmed_loadout = record
        self._confirmed_loadout_loaded = True

    def _terminal_equipment_blocker(self, snapshot: Snapshot) -> str | None:
        """Name an unrepairable optimizer block after all town routes are spent."""
        preparation = self._prepare_equipment_optimization(snapshot)
        # R1: unavailable calibration skips optimization; it never names a
        # terminal equipment blocker.
        calibration_unavailable = preparation is not None and any(
            blocker == "calibration-required" or blocker.startswith("calibration-stale:")
            for blocker in preparation.blockers
        )
        if (
            not calibration_unavailable
            and STORE_HOME in self._town_visit_ledger.blocked_stores
            and (preparation is None or preparation.result is None)
        ):
            return "equipment-home-unavailable"
        if (
            not calibration_unavailable
            and preparation is not None
            and "optimization-timeout" in preparation.blockers
            and not self._equipment_departure_ready(snapshot)
        ):
            return "equipment-optimization-timeout"
        # The required-store evaluation also runs the town terminal
        # transitions (a stock-out installs its restock wait), so it runs
        # before the calibration return exactly as it did before R1.
        if (
            preparation is None
            or self._next_required_store_type(snapshot) is not None
            or calibration_unavailable
        ):
            return None
        if "no-valid-loadout" in preparation.blockers:
            return "equipment-no-valid-loadout"
        if "incomplete-equipment-catalog" in preparation.blockers:
            return "equipment-incomplete-catalog"
        return None

    def _activate_safe_recall_fallback(
        self, snapshot: Snapshot, unsafe_depth: int, *,
        guardian_bounced_dungeon: int | None = None,
    ) -> int | None:
        """Select the shallowest entered dungeon below an unsafe destination.

        ``unsafe_depth`` is the arrival depth the caller refused, not
        ``snapshot.recall_depth``.  The two differ whenever the objective's
        destination is not the destination the Word of Recall currently
        points at: the live 2026-09-23 18:23 board refused Angband's 50
        while the scroll still pointed at the Yeek cave's 13, so bounding the
        alternates by the board's own recall depth demanded a landing shallower
        than 12 and rejected every safe dungeon the character had entered.

        ``guardian_bounced_dungeon``: the destination was refused only
        because its landing is a guardian floor the kit cannot pass.  The
        recall would be a guardian bounce, so the choice is the guardian
        valve's (user decision 2026-09-25, 「倒せない階でなければ深くても可」):
        any landing that is not a blocked guardian floor, deeper allowed,
        never the refused dungeon itself.
        """
        if guardian_bounced_dungeon is not None:
            alternate = self._pick_alternate_dungeon(
                snapshot, guardian_bounced_dungeon=guardian_bounced_dungeon
            )
        else:
            alternate = self._pick_alternate_dungeon(
                snapshot,
                max_entry_depth=max(1, unsafe_depth - 1),
            )
        if alternate is None:
            return None
        self._alternate_dungeon = alternate
        self._target_dungeon_id = alternate
        self._conquest_committed = None
        self._equipment_optimization_signature = None
        self._equipment_optimization_preparation = None
        return alternate


















    def _target_loadout_known(self) -> bool:
        """Whether the optimizer currently supplies a concrete target loadout."""
        preparation = self._equipment_optimization_preparation
        if preparation is None:
            return False
        result = getattr(preparation, "result", None)
        best = getattr(result, "best", None)
        return getattr(best, "loadout", None) is not None












    def _is_surplus_digging_tool(self, snapshot: Snapshot, item: InventoryItem) -> bool:
        """Keep the best two carried tools; permit excess deposit/disposal."""
        if not item.is_digging_tool:
            return False
        if self._disposal_protected_by_identification(item):
            return False
        diggers = [
            candidate
            for candidate in (*snapshot.equipment, *snapshot.inventory)
            if candidate.is_digging_tool
            and not self._equip_blocked_by_identification(candidate)
        ]
        keep = sorted(
            diggers,
            key=self._digging_tool_sale_quality,
            reverse=True,
        )[:2]
        return all(candidate is not item for candidate in keep)




    @staticmethod
    def _survival_essential(item: InventoryItem) -> bool:
        # Items the bot actively depends on to survive and to get home; these are
        # never shed by the last-resort overflow drop.
        return (
            item.is_recall_scroll
            or item.is_teleport_scroll
            or (
                item.is_potion
                and item.aware
                and item.sval
                in {
                    SV_POTION_CURE_CRITICAL,
                    SV_POTION_SPEED,
                    SV_POTION_HEALING,
                }
            )
            or (item.is_food and item.aware and item.sval >= FOOD_MIN_SVAL)
            or item.is_light
            or item.is_oil
            or item.is_digging_tool
        )

    @staticmethod
    def _has_town_economic_path(item: InventoryItem) -> bool:
        # Items another town action can shed for value, so the overflow drop
        # leaves them alone: equipment goes to the Home, and unidentified
        # potions/scrolls sell to the Alchemist.
        return item.is_equipment or HengbotPolicy._is_high_value_book(item) or (
            not item.aware and (item.is_potion or item.is_scroll)
        )

    @staticmethod
    def _is_high_value_book(item: InventoryItem) -> bool:
        """Third and fourth realm books are valuable town-sale loot."""
        return item.tval in SPELLBOOK_TVALS and item.sval in {2, 3}

    @staticmethod
    def _book_sale_store_type(item: InventoryItem) -> int | None:
        if not HengbotPolicy._is_high_value_book(item):
            return None
        if item.tval in {TVAL_LIFE_BOOK, TVAL_CRUSADE_BOOK}:
            return STORE_TEMPLE
        if item.tval == TVAL_HISSATSU_BOOK:
            return STORE_WEAPON
        return STORE_MAGIC


    def _overflow_disposal_item(self, snapshot: Snapshot) -> InventoryItem | None:
        # A full pack of items no shop buys and the Home will not take — devices
        # (wand/staff/rod), ammo, books, chests, identified junk — strands the
        # bot in town: it cannot re-descend (pack-full blocks descent) and roams
        # forever below the loop-detector's radar. As a last resort, destroy one
        # such item so a slot always frees. Only reached after every productive
        # town action has declined this turn, so it never pre-empts a sale,
        # deposit, or purchase; survival gear and economically-useful items are
        # preserved.
        disposable = self._find_disposable_item(snapshot)
        if disposable is not None:
            return disposable
        return self._first_item(
            snapshot,
            # Destroy always removes the whole stack to free one pack slot.
            # A partially surplus stack still contains reserved supplies and
            # therefore cannot be an overflow victim.
            lambda item: self._entire_stack_is_surplus(snapshot, item)
            and not self._item_is_procurement_protected(snapshot, item)
            and not self._survival_essential(item)
            and not self._is_useful_device(item)
            and not self._has_town_economic_path(item)
            and self._item_signature(item) not in self._undestroyable_sigs,
        )


    @staticmethod
    def _item_signature(item: InventoryItem | StoreItem) -> tuple[str, int, int]:
        return (item.name, item.tval, item.sval)

    @staticmethod
    def _inventory_move_identity_count(snapshot: Snapshot, identity: str) -> int:
        return sum(
            max(1, item.count)
            for item in snapshot.inventory
            if equipment_move_identity(item) == identity
        )

    def _read_key(
        self, snapshot: Snapshot, item: InventoryItem, suffix: str = ""
    ) -> str:
        """Compose a read while retaining the selected scroll's identity."""
        composed_item = next(
            (candidate for candidate in snapshot.inventory if candidate.slot == item.slot),
            None,
        )
        self._read_binding = (
            item.tval,
            item.sval,
            item.name,
            item.slot,
            (
                {
                    "tval": composed_item.tval,
                    "sval": composed_item.sval,
                    "name": composed_item.name,
                }
                if composed_item is not None
                else None
            ),
        )
        return self.validate_read_key(snapshot, READ_KEY + item.slot + suffix)

    def validate_read_key(self, snapshot: Snapshot, key: str | None) -> str | None:
        """Rebind a composed read to its intended scroll in the acting snapshot."""
        if key is None or not key.startswith(READ_KEY) or len(key) < 2 or self._read_binding is None:
            return key
        (
            intended_tval,
            intended_sval,
            intended_name,
            composed_letter,
            composed_resolved,
        ) = self._read_binding
        old_letter = key[1]
        suffix = key[2:]
        resolved = next(
            (item for item in snapshot.inventory if item.slot == old_letter), None
        )
        selected = resolved
        if (
            selected is None
            or selected.tval != intended_tval
            or selected.sval != intended_sval
        ):
            selected = next(
                (
                    item
                    for item in snapshot.inventory
                    if item.tval == intended_tval and item.sval == intended_sval
                ),
                None,
            )
        posted_key = READ_KEY + selected.slot + suffix if selected is not None else WAIT_KEY
        self.read_telemetry = {
            "key": posted_key,
            "letter": selected.slot if selected is not None else None,
            "resolved": (
                {
                    "tval": selected.tval,
                    "sval": selected.sval,
                    "name": selected.name,
                }
                if selected is not None
                else None
            ),
            "intended": {
                "tval": intended_tval,
                "sval": intended_sval,
                "name": intended_name,
            },
            "composed": {
                "letter": composed_letter,
                "resolved": composed_resolved,
            },
        }
        return posted_key

    @classmethod
    def _normal_identification_flow_candidate(
        cls, item: InventoryItem | StoreItem,
    ) -> bool:
        """Union of carried/worn gear and device plain-Identify consumers.

        Scrolls (tval 70) deliberately have no town-identification owner:
        reading a scroll identifies its flavor through its normal use flow.
        """
        return (
            cls._identification_flow_candidate(item) and not item.known
        ) or (
            item.tval in {TVAL_WAND, TVAL_STAFF, TVAL_ROD} and not item.known
        )







    @staticmethod
    def _is_ammunition(item: InventoryItem | StoreItem) -> bool:
        return item.tval in {TVAL_SHOT, TVAL_ARROW, TVAL_BOLT}


    def _pending_inventory_item(self, snapshot: Snapshot) -> InventoryItem | None:
        pending_kind = (
            self._home_pending_item[1:]
            if self._home_pending_item is not None
            else None
        )
        if self._home_pending_slot is not None:
            item = next(
                (it for it in snapshot.inventory if it.slot == self._home_pending_slot),
                None,
            )
            if item is not None and (
                self._home_pending_item is None
                or self._item_signature(item) == self._home_pending_item
                or (item.tval, item.sval) == pending_kind
            ):
                return item
        if self._home_pending_item is None:
            return None
        item = self._first_item(
            snapshot, lambda it: self._item_signature(it) == self._home_pending_item
        )
        if item is None:
            # Consuming an Identify scroll can shift every later inventory slot,
            # while identification itself changes the item's name/signature.
            # Recover the pending equipment by its stable base kind instead of
            # accepting whichever unrelated item moved into the old slot.
            item = self._first_item(
                snapshot,
                lambda it: it.is_equipment and (it.tval, it.sval) == pending_kind,
            )
        if item is not None:
            self._home_pending_slot = item.slot
        return item


    def _reserve_next_identification_source(
        self,
        snapshot: Snapshot,
        target: tuple[str, int, int],
        *,
        full: bool,
    ) -> None:
        reservation = self._identification_source_reservation
        if reservation is not None and reservation.get("target") == target:
            return
        baseline: dict[tuple[str, int, int], int] = {}
        for item in self._identification_source_items(snapshot, full=full):
            signature = self._item_signature(item)
            baseline[signature] = (
                baseline.get(signature, 0) + self._identification_source_units(item)
            )
        self._identification_source_reservation = {
            "target": target,
            "kind": "full" if full else "normal",
            "source": None,
            "state": "awaiting-source",
            "baseline": baseline,
        }

    def _release_identification_source_reservation(
        self, target: tuple[str, int, int] | None = None
    ) -> None:
        reservation = self._identification_source_reservation
        if reservation is None:
            return
        if target is None or reservation.get("target") == target:
            self._identification_source_reservation = None



    @staticmethod
    def _is_useful_device(item: InventoryItem) -> bool:
        return (
            item.tval == TVAL_WAND
            and item.sval in {SV_WAND_STONE_TO_MUD, SV_WAND_TELEPORT_AWAY}
        ) or (
            # A drained Staff of Identify cannot identify anything, so it stops
            # counting as useful — it becomes sale/disposal fodder like any junk.
            item.tval == TVAL_STAFF
            and item.sval == SV_STAFF_IDENTIFY
            and item.charges > 0
        )

    @staticmethod
    def _is_weapon(item: InventoryItem | StoreItem) -> bool:
        # tvals 20-23 (DIGGING, HAFTED, POLEARM, SWORD) are the melee weapon group.
        return item.tval in {20, 21, 22, 23}

    @staticmethod
    def _weapon_is_high_grade(item: InventoryItem | StoreItem) -> bool:
        # 高級品以上: excellent/special pseudo-ID, or a known ego/artifact.
        return (
            item.is_ego
            or item.is_artifact
            or item.pseudo_feeling in {"excellent", "special"}
        )

    @staticmethod
    def _blocks_teleport(item: InventoryItem | StoreItem) -> bool:
        return TR_NO_TELE in item.known_flags

    def _equipped_weapon_high_grade(self, snapshot: Snapshot) -> bool:
        weapon = next(
            (it for it in snapshot.equipment if it.slot == "main_hand"), None
        )
        return weapon is not None and self._weapon_is_high_grade(weapon)

    def _weapon_is_inferior(self, item: InventoryItem) -> bool:
        # 上質以下: a melee weapon (not a digging tool, not a bounty remain) we are
        # sure is at most "good" quality. Two ways to be sure it is not secretly an
        # ego/artifact: it is *identified* (known) and turned out mundane, or it is
        # still unidentified but pseudo-sensed as good/average. An identified plain
        # weapon carries NO pseudo_feeling, so also requiring the pseudo tag used to
        # let every mundane +0,+0 spare slip through unsold. Worthless/cursed
        # weapons go down the disposal path instead.
        return (
            self._is_weapon(item)
            and not item.is_digging_tool
            and not getattr(item, "is_bounty", False)  # StoreItem lacks this field
            and not self._weapon_is_high_grade(item)
            and (item.known or item.pseudo_feeling in {"good", "average"})
        )


    def _device_food_reserve_slot(self, snapshot: Snapshot) -> str | None:
        if snapshot.player.food_type != FOOD_TYPE_MANA:
            return None
        wands = [item for item in snapshot.inventory if item.tval == TVAL_WAND and item.known]
        if wands:
            return max(wands, key=self._stack_charges).slot
        staffs = [item for item in snapshot.inventory if item.tval == TVAL_STAFF and item.known]
        if staffs:
            return max(staffs, key=self._stack_charges).slot
        return None



    def _request_identification(self, kind: str) -> None:
        if kind == "normal" and self._identification_need != kind:
            # Basic Identify is ordinary Alchemist stock. Re-arm both the coarse
            # attempted latch and the bounded errand plan for newly requested
            # normal-tier work. *Identify* is not sold there, so a full-tier
            # escalation must preserve the exhausted-store latch.
            self._rearm_town_store_for_new_work(STORE_ALCHEMIST)
        self._identification_need = kind






    def _defer_full_identification(self, signature: tuple[str, int, int]) -> None:
        """Defer unavailable *Identify* work without retaining its Home latch."""
        self._defer_home_item(signature, "full-identification-unavailable")
        self._release_identification_source_reservation(signature)
        self._unbuyable_full_identify_sigs.add(signature)
        self._identification_candidate = None
        if self._identification_need == "full":
            self._identification_need = None
        if self._home_pending_item == signature:
            self._home_pending_item = None
            self._home_pending_slot = None
            self._home_candidate_waiting = False






    @staticmethod
    def _ring_candidate(item: InventoryItem) -> bool:
        return (
            item.tval == TVAL_RING
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and (
                bool(item.known_flags)
                or item.pval > 0
                or item.to_a > 0
                or item.is_ego
                or item.is_artifact
            )
        )

    @staticmethod
    def _amulet_candidate(item: InventoryItem) -> bool:
        return (
            item.tval == TVAL_AMULET
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and (
                bool(item.known_flags)
                or item.pval > 0
                or item.to_a > 0
                or item.is_ego
                or item.is_artifact
            )
        )





    @claims(ClaimOwner.SURVIVAL)
    def _stat_gain_quaff_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        # Permanent stat-gain potions (Strength … Charisma, Augmentation) are one-
        # shot upgrades with no downside, so drink any identified one on sight when
        # safe. Never hoard them — a stat point banked in the pack is a stat point
        # not working for us (and pack weight we could shed).
        player = snapshot.player
        if hostiles or player.confused or player.blind:
            return None
        potion = next(
            (
                it
                for it in snapshot.inventory
                if it.is_potion and it.aware and it.sval in STAT_GAIN_POTION_SVALS
            ),
            None,
        )
        if potion is not None:
            self.last_reason = "stat-gain:quaff"
            key = QUAFF_KEY + potion.slot
            self._offer_execution(
                key, producer="survival", work_id="stat-gain:quaff",
                next_step="survival.quaff-stat-gain",
                arguments=(self._item_signature(potion),),
                expected_effect="stat-gain-observed",
            )
            return key
        return None

    def _is_disposable_dominated_armour(
        self, snapshot: Snapshot, candidate: InventoryItem | StoreItem
    ) -> bool:
        """Whether this fully known item is disposal-safe under the R1 prune."""
        if candidate.tval == TVAL_BOW:
            return self._is_disposable_dominated_launcher(snapshot, candidate)
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR:
            return False
        if (
            not candidate.is_equipment
            or not candidate.known
            or candidate.is_cursed
            or candidate.is_broken
            or (item_requires_full_identification(candidate) and not candidate.fully_known)
            or self._equipment_disposal_reserved(snapshot, candidate)
            or not self._equipment_catalog.home_scan_complete
        ):
            return False
        catalog = self._equipment_catalog.items
        protected = frozenset(
            owned.id
            for owned in catalog
            if owned.origin == "equipped"
            or owned.item.is_cursed
            or self._equipment_disposal_reserved(snapshot, owned.item)
        )
        candidate_identity = equipment_identity(candidate)
        # Full-Home relief asks this for every shelf item. Dominance depends
        # only on the immutable catalog and protected IDs, not the candidate.
        # Recheck both inputs so catalog/ownership changes within a decision
        # also invalidate the result (including direct helper callers).
        cached = getattr(self, "_disposable_armour_cache", None)
        if cached is None or cached[:2] != (catalog, protected):
            disposable = disposable_dominated_item_ids(catalog, protected)
            identities = frozenset(
                equipment_identity(owned.item)
                for owned in catalog
                if owned.id in disposable and owned.origin == "home"
            )
            cached = (catalog, protected, identities)
            self._disposable_armour_cache = cached
        return candidate_identity in cached[2]


    def _begin_pack_dominated_launcher_disposal(
        self, snapshot: Snapshot
    ) -> None:
        """Hand one dominated pack launcher to the normal disposal router."""
        if self._pending_disposal_item is not None:
            return
        candidate = next(
            (
                item
                for item in snapshot.inventory
                if self._is_disposable_dominated_launcher(snapshot, item)
            ),
            None,
        )
        if candidate is None:
            return
        self._pending_disposal_slot = candidate.slot
        self._pending_disposal_item = self._item_signature(candidate)
        self._disposal_store_attempts.clear()



    def _pending_disposal(self, snapshot: Snapshot) -> InventoryItem | None:
        if self._pending_disposal_slot is not None:
            item = next(
                (
                    it
                    for it in snapshot.inventory
                    if it.slot == self._pending_disposal_slot
                ),
                None,
            )
            if (
                item is not None
                and self._pending_disposal_item is not None
                and self._item_signature(item) == self._pending_disposal_item
            ):
                return item
        if self._pending_disposal_item is None:
            return None
        item = self._first_item(
            snapshot,
            lambda it: self._item_signature(it) == self._pending_disposal_item,
        )
        if item is not None:
            self._pending_disposal_slot = item.slot
        return item

    def _release_stale_home_candidate_waiting(
        self, snapshot: Snapshot | None = None
    ) -> None:
        """Release a Home latch with no owner or executable scan this visit."""
        if (
            self._home_candidate_waiting
            and self._home_pending_item is None
            and not self._home_pending_batch
            and not self._home_batch_review_items
            and self._home_atomic_withdraw_pending is None
            and self._identification_need is None
            and (
                self._equipment_catalog.home_scan_complete
                or (
                    snapshot is not None
                    and not self._home_catalog_routable(snapshot)
                )
            )
        ):
            # 2026-07-28/29: a consumed candidate or an exhausted Home pass can
            # leave this visit-scoped latch with no claim capable of clearing it.
            self._home_candidate_waiting = False

    def _clear_pending_disposal(self) -> None:
        self._pending_disposal_slot = None
        self._pending_disposal_item = None
        self._disposal_store_attempts.clear()
        self._destroy_pending = False
        self._destroy_attempts = 0
        self._release_stale_home_candidate_waiting()






    def _effective_mining_run_target(self) -> int:
        if getattr(self, "_supply_stockout_gold_target", None) is not None:
            return 1
        return self._planned_mining_runs or MINING_RUNS_PER_SET

    def _activate_partial_mining_plan(self, snapshot: Snapshot) -> bool:
        """Use the mining runs supported by detection scrolls already carried."""
        remaining_cap = max(
            0, MINING_RUNS_PER_SET - self._mining_runs_completed
        )
        additional_runs = min(
            remaining_cap,
            self._count_treasure_detection_scrolls(snapshot),
        )
        if additional_runs < 1:
            return False
        planned_total = self._mining_runs_completed + additional_runs
        if planned_total >= self._effective_mining_run_target():
            return False
        self._planned_mining_runs = planned_total
        self._identify_staff_mining_plan = False
        self._recall_stockout_mining_plan = False
        self._fundraising_mode = "mine"
        return True





    def _observe_restock_supplier_page(self, snapshot: Snapshot) -> None:
        """Record a recall recheck only when the observed shelf is empty."""
        store = snapshot.store
        waiting_for = self._town_restock_waiting_for
        if not waiting_for or store is None or store.store_type not in waiting_for:
            return
        if set(waiting_for) == {STORE_TEMPLE, STORE_ALCHEMIST}:
            recall_prices = [
                item.price
                for item in store.items
                if item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_WORD_OF_RECALL
            ]
            stocked = bool(recall_prices)
            if stocked and min(recall_prices) > snapshot.player.gold:
                # Price, not turnover, is the blocker.  Leave the restock
                # cycle and let the established preparation owners acquire a
                # one-run mining kit and earn the missing gold locally.
                self._town_restock_waiting_for = ()
                self._town_restock_wait_until = None
                self._planned_mining_runs = 1
                self._identify_staff_mining_plan = False
                self._recall_stockout_mining_plan = False
                self._mining_runs_completed = 0
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                self._retire_town_errand_plan_for_rebuild()
            elif not stocked:
                self._town_restock_rechecked.add(store.store_type)
        elif self._next_purchase(snapshot) is None:
            self._town_restock_rechecked.add(store.store_type)

    def _restock_wait_reason(self, snapshot: Snapshot) -> str:
        stores = self._town_restock_waiting_for
        store_name = (
            STORE_RESTOCK_REASON_NAMES.get(stores[0], str(stores[0]))
            if stores
            else "unknown"
        )
        missing = None
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            if STORE_GENERAL in stores and not self._has_digging_tool(snapshot):
                missing = "digging-tool"
            elif (
                STORE_ALCHEMIST in stores
                and self._count_treasure_detection_scrolls(snapshot)
                < self._mining_detection_scroll_target(snapshot)
            ):
                missing = "treasure-detection"
            elif STORE_GENERAL in stores and not self._fundraising_light_ready(snapshot):
                missing = "oil-light"
        suffix = f":{missing}" if missing is not None else ""
        return f"town:wait-restock:{store_name}{suffix}"


    def _recall_restock_key(self, snapshot: Snapshot) -> str:
        """Pass time locally, then re-observe both recall suppliers."""
        recall_stores = (STORE_TEMPLE, STORE_ALCHEMIST)
        if (
            self._town_restock_wait_until is None
            and all(store in self._town_restock_rechecked for store in recall_stores)
        ):
            self._town_restock_waiting_for = ()
            stocked_stores = []
            for store_type in recall_stores:
                remembered = getattr(
                    self, "_town_supplier_stock", {}
                ).get(store_type)
                if remembered is not None and any(
                        item.tval == TVAL_SCROLL
                        and item.sval == SV_SCROLL_WORD_OF_RECALL
                        and item.price <= snapshot.player.gold
                        for item in remembered.items
                ):
                    stocked_stores.append(store_type)
                    self._town_store_attempted.pop(store_type, None)
            if stocked_stores:
                return self._released_restock_store_key(
                    snapshot, tuple(stocked_stores)
                )
            if not self._food_ready(snapshot):
                return self._released_restock_store_key(snapshot, recall_stores)
            # Prefer exactly one safely gated Yeek Cave 1F mining run.  Start
            # in preparation mode so the ordinary Home/shop owners can fetch
            # an owned kit instead of requiring it to be carried already.
            owned_kit = (
                self._has_withdrawable_digging_tool(snapshot)
                and self._has_withdrawable_treasure_detection(snapshot)
            )
            if owned_kit:
                self._planned_mining_runs = 1
                self._identify_staff_mining_plan = False
                self._recall_stockout_mining_plan = True
                self._fundraising_mode = "prepare"
                self._mining_runs_completed = 0
                self._town_restock_rechecked.difference_update(recall_stores)
                self._town_store_attempted.clear()
                self._retire_town_errand_plan_for_rebuild()
                self.last_reason = "town:recall-stockout-mining"
                return WAIT_KEY
            self._town_restock_rechecked.difference_update(recall_stores)
            self._town_restock_wait_until = None
        released_store = self._retry_after_store_restock(snapshot, recall_stores)
        if released_store is not None:
            return self._released_restock_store_key(snapshot, recall_stores)
        self.last_reason = self._restock_wait_reason(snapshot)
        self._town_restock_last_wait_turn = snapshot.turn
        return RESTOCK_WAIT_MACRO

    def _start_unobtainable_recall_stockout_mining(
        self, snapshot: Snapshot
    ) -> bool:
        """Enter the local one-run wait flow once both suppliers are disproved."""
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            return False
        if (
            not self._recall_stockout_persists(snapshot)
            or not self._food_ready(snapshot)
        ):
            return False
        self._planned_mining_runs = 1
        self._identify_staff_mining_plan = False
        self._recall_stockout_mining_plan = True
        self._mining_runs_completed = 0
        self._fundraising_mode = "prepare"
        self._town_restock_waiting_for = ()
        self._town_restock_wait_until = None
        self._town_store_attempted.clear()
        self._town_restock_rechecked.difference_update(
            (STORE_TEMPLE, STORE_ALCHEMIST)
        )
        self._cross_town_shopping = None
        self._retire_town_errand_plan_for_rebuild()
        return True

    def _recall_stockout_persists(self, snapshot: Snapshot) -> bool:
        """Whether recall is short for departure with no actionable supplier.

        Judged against the ordinary (non-fundraising) departure requirement:
        the one-run time-pass itself reshapes the in-run recall requirement
        (zero while mining), which is not the shortage it waits out.
        """
        mode = self._fundraising_mode
        self._fundraising_mode = None
        try:
            recall = self._supply_ledger(snapshot, self._planned_depth())["recall"]
        finally:
            self._fundraising_mode = mode
        return recall.count < recall.required_departure and not recall.obtainable


    def _identify_staff_procurement_impossible(self, snapshot: Snapshot) -> bool:
        """Whether both local, ordered Identify-staff suppliers are exhausted."""
        if (
            not self._home_knowledge_current
            and STORE_HOME not in self._town_visit_ledger.blocked_stores
        ):
            return False
        # User 2026-10-03: at most STAFF_IDENTIFY_MAX_COUNT carried staves, so
        # Home helps only up to the fullest four staves of pack plus Home.
        per_staff_charges = [
            max(0, item.charges)
            for item in (
                *(
                    it for it in snapshot.inventory
                    if it.tval == TVAL_STAFF
                    and it.aware
                    and it.sval == SV_STAFF_IDENTIFY
                ),
                *(
                    it for it in self._home_knowledge_items
                    if it.tval == TVAL_STAFF
                    and it.aware
                    and it.known
                    and it.sval == SV_STAFF_IDENTIFY
                    and self._item_signature(it) not in self._deferred_home_items
                ),
            )
            for _ in range(max(1, item.count))
        ]
        reachable = sum(
            sorted(per_staff_charges, reverse=True)[:STAFF_IDENTIFY_MAX_COUNT]
        )
        if (
            self._home_knowledge_current
            and reachable >= STAFF_IDENTIFY_MIN_CHARGES
        ):
            return False
        supplier_pages = dict(self._town_supplier_stock)
        if snapshot.store is not None and snapshot.store.store_type in {
            STORE_MAGIC,
            STORE_BLACK,
        }:
            supplier_pages[snapshot.store.store_type] = snapshot.store
        if any(
            any(
                item.tval == TVAL_STAFF
                and item.sval == SV_STAFF_IDENTIFY
                and item.price <= snapshot.player.gold
                # At the four-staff cap a shelf staff is a supplier only when
                # it is fuller than the emptiest carried one (the swap).
                and self._identify_staff_acquisition_worthwhile(
                    snapshot, max(item.charges, item.pval)
                )
                for item in page.items
            )
            for store_type in (STORE_MAGIC, STORE_BLACK)
            if (page := supplier_pages.get(store_type)) is not None
        ):
            return False
        return STORE_MAGIC in self._town_store_attempted

    @claims(ClaimOwner.FUNDRAISING)
    def _identify_staff_stockout_key(self, snapshot: Snapshot) -> str:
        """Pass one Yeek Cave 1F mining run, then retry Home and Magic."""
        self._planned_mining_runs = 1
        self._identify_staff_mining_plan = True
        self._recall_stockout_mining_plan = False
        self._fundraising_mode = "prepare"
        self._mining_runs_completed = 0
        self._town_store_attempted.clear()
        self._retire_town_errand_plan_for_rebuild()
        self.last_reason = "town:identify-staff-stockout-mining"
        self._offer_execution(
            WAIT_KEY, producer="fundraising",
            work_id="fundraise:identify-staff-stockout",
            next_step="fundraising.prepare-one-mining-run",
            expected_effect="identify-staff-suppliers-rearmed",
        )
        return WAIT_KEY


    def _candidate_need(
        self,
        snapshot: Snapshot,
        category: str,
        ordering_class: str,
        occurrence: int,
    ) -> TownNeed | None:
        evaluated_snapshot = getattr(
            self, "_town_need_evaluation_snapshot", None
        )
        evaluated_candidates = getattr(
            self, "_town_need_evaluation_candidates", None
        )
        candidates = (
            evaluated_candidates
            if evaluated_snapshot is snapshot and evaluated_candidates is not None
            else self._town_need_candidates(snapshot)
        )
        matches = [
            need
            for need in candidates
            if need.category == category and need.ordering_class == ordering_class
        ]
        return matches[occurrence] if occurrence < len(matches) else None



    def _retire_actionless_equipment_failure(self, snapshot: Snapshot) -> bool:
        """Release a failed optimizer latch that has no in-town clearing owner."""
        if (self.last_reason or "").startswith("equipment-transaction:"):
            return False
        preparation = self._equipment_optimization_preparation
        if not self._safe_optional_equipment_failure_departure(snapshot, preparation):
            return False
        self._stage_optional_equipment_failure_departure(
            snapshot, self._equipment_departure_destination_depth(snapshot))
        live_carried = OwnedEquipmentCatalog()
        live_carried.refresh_carried(snapshot.inventory, snapshot.equipment)
        self._equipment_retired_worn_item_ids = current_loadout(
            live_carried.items
        ).item_ids
        self._equipment_transaction_failed_items.clear()
        self._equipment_quarantine_second_chance_ids.clear()
        self._equipment_quarantine_readmitted_ids = ()
        self._equipment_optimization_preparation = replace(
            preparation, blockers=()
        )
        self._equipment_optimization_signature = None
        self._town_liveness_claim_retired = True
        return True














    @staticmethod
    def _town_observable_effect_state(snapshot: Snapshot) -> tuple[object, ...]:
        """Project durable refusal evidence; ignore turn passage and walking."""
        workflow = HengbotPolicy._town_workflow_progress_state(snapshot)
        return (workflow[0], tuple(snapshot.messages), *workflow[1:])

    def _refresh_nonhome_effect_refusals(self, snapshot: Snapshot) -> None:
        """Release a refused route only after the game exposes different state."""
        state = self._town_observable_effect_state(snapshot)
        pending = self._town_visit_ledger.pending_nonhome_effect_observation
        if snapshot.store is None:
            for store_type in tuple(pending):
                self._town_visit_ledger.nonhome_attempted_without_effect[
                    store_type
                ] = state
                pending.discard(store_type)
        refused = self._town_visit_ledger.nonhome_attempted_without_effect
        for store_type, previous in tuple(refused.items()):
            if previous != state:
                refused.pop(store_type, None)









    def _remember_departure_price(
        self, category: str, price: int, units: int = 1
    ) -> None:
        if price <= 0 or units <= 0:
            return
        previous = self._observed_departure_prices.get(category)
        if previous is None or price * previous[1] < previous[0] * units:
            self._observed_departure_prices[category] = (price, units)

    def _observe_departure_prices(self, snapshot: Snapshot) -> None:
        """Retain only emitter-observed prices usable by the expedition gate."""
        store = snapshot.store
        if store is None:
            return
        for item in store.items:
            if item.is_recall_scroll:
                self._remember_departure_price("recall", item.price)
            if item.is_teleport_scroll:
                self._remember_departure_price("teleport", item.price)
            if item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
                self._remember_departure_price("cure-critical", item.price)
            if item.is_oil:
                self._remember_departure_price("oil", item.price)
            if item.tval == TVAL_FOOD and item.sval >= FOOD_MIN_SVAL:
                self._remember_departure_price("food", item.price)
            if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
                self._remember_departure_price(
                    "identification-source:normal", item.price
                )
            if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
                self._remember_departure_price(
                    "identification-source:full", item.price
                )
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY:
                charges = max(1, item.pval)
                self._remember_departure_price("identify-staff", item.price, charges)
            if item.tval == TVAL_LITE and item.sval in {
                SV_LITE_TORCH,
                SV_LITE_LANTERN,
            }:
                self._remember_departure_price("light", item.price)
            if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_REMOVE_CURSE:
                self._remember_departure_price("remove-curse", item.price)
            if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_REMOVE_CURSE:
                self._remember_departure_price("star-remove-curse", item.price)
                self._remember_departure_price("remove-curse", item.price)
            for stat, sval in RESTORE_POTION_SVAL_BY_STAT.items():
                if item.tval == TVAL_POTION and item.sval == sval:
                    self._remember_departure_price(
                        f"stat-restore:{stat}", item.price
                    )
        self._observe_cross_town_shelf(snapshot)









    def _carried_full_identify_targets(
        self, snapshot: Snapshot
    ) -> list[InventoryItem]:
        return [
            item
            for item in (*snapshot.inventory, *snapshot.equipment)
            if item.known
            and item_requires_full_identification(item)
            and not item.fully_known
        ]


    def _finish_morivant_full_identify(self) -> None:
        expedition = self._morivant_full_identify
        if expedition is None:
            return
        self._morivant_full_identify_attempted.add(expedition.target_signatures)
        expedition_targets = set(expedition.home_target_signatures)
        if self._home_pending_item in expedition_targets:
            self._home_pending_item = None
        self._home_pending_batch = [
            signature for signature in self._home_pending_batch
            if signature not in expedition_targets
        ]
        self._home_candidate_waiting = False
        self._morivant_full_identify = None




    def _defer_identification_for_conquest(self, snapshot: Snapshot) -> None:
        """Keep unavailable identification from blocking a viable guardian run."""
        pending = self._pending_inventory_item(snapshot)
        if pending is not None:
            signature = self._item_signature(pending)
            self._defer_home_item(signature, "full-identify-source-unavailable")
            self._unbuyable_full_identify_sigs.add(signature)
        elif self._identification_candidate is not None:
            self._defer_home_item(
                self._identification_candidate, "identify-candidate-source-unavailable"
            )
            self._unbuyable_full_identify_sigs.add(
                self._identification_candidate
            )
        elif self._device_identification_candidate is not None:
            self._deferred_device_items.add(self._device_identification_candidate)
        self._home_pending_item = None
        self._home_pending_slot = None
        self._identification_need = None
        self._identification_candidate = None
        self._device_identification_candidate = None
        self._home_candidate_waiting = False

    def _start_fundraising(self, snapshot: Snapshot) -> bool:
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            return True
        if (
            self._opening_q34_active(snapshot)
            and self._opening_q34_torch_shortage(snapshot) > 0
        ):
            return False
        if snapshot.player.gold >= FUNDRAISING_START_GOLD:
            return False
        self._planned_mining_runs = None
        self._identify_staff_mining_plan = False
        self._recall_stockout_mining_plan = False
        self._fundraising_mode = "prepare"
        self._town_store_attempted.clear()
        return True

    def _start_no_safe_destination_fundraising(
        self, snapshot: Snapshot, destination_depth: int
    ) -> bool:
        """Enter the ordinary fundraising set when no recall landing is safe.

        USER DECISION 2026-10-02 17:4x (no-safe-recall-fundraise-and-quests):
        「帰還先が全部条件不足の時は止めず ... イークの洞穴へ歩いて資金稼ぎ ...
        必要な能力の条件は緩めない」.  A ready fixed quest is chosen before
        this point (``_fixed_quest_key#2`` runs before ``_town_special_key``).

        It enters the same ``prepare`` set ``_start_fundraising`` opens, only
        without its poverty threshold, and therefore ends by the same rules:
        the gold set-end (``_end_fundraising_set_at_gold_target``) and the
        run-count end.  It is never opened at or above
        FUNDRAISING_GOLD_TARGET, where the gold set-end would close it on the
        next board and the next refusal would reopen it (a town cycle); there
        the named depth-gate stop stays.  Only equipment abilities qualify:
        the *Destruction* and speed gates are not answered by gold.
        """
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            return False
        missing = self._missing_required_abilities(snapshot, destination_depth)
        if not missing or missing & {DESTRUCTION_GATE_LABEL, SPEED_GATE_LABEL}:
            return False
        if snapshot.player.gold >= FUNDRAISING_GOLD_TARGET:
            return False
        if self._opening_q34_active(snapshot):
            return False
        self._planned_mining_runs = None
        self._identify_staff_mining_plan = False
        self._recall_stockout_mining_plan = False
        self._fundraising_mode = "prepare"
        self._town_store_attempted.clear()
        self._retire_town_errand_plan_for_rebuild()
        return True

    def _try_normal_expedition_after_detection_stockout(
        self, snapshot: Snapshot
    ) -> bool:
        """Trade a blocked mining campaign for an ordinary expedition.

        Once Home and the Alchemist have both proved that no treasure-detection
        scroll is available, a character above the poverty threshold should use
        its money on the normal recall/food/light/teleport/cure kit instead of
        immediately entering loot-only scavenge.  Re-arm only the stores that
        can satisfy current ordinary departure shortages; the next router pass
        buys those supplies and normal departure takes over when they are full.
        """
        if snapshot.player.gold < FUNDRAISING_START_GOLD:
            return False

        self._fundraising_mode = None
        self._planned_mining_runs = None
        self._scavenge_entry_gold = None
        self._town_restock_suppressed = False
        self._town_restock_wait_until = None
        self._retire_town_errand_plan_for_rebuild()
        self._town_blocked_reason = None

        ledger = self._supply_ledger(snapshot, self._planned_depth())
        supply_stores = {
            store_type
            for status in self._ledger_departure_shortages(ledger)
            for store_type in status.stores
        }
        if not self._light_ready(snapshot):
            supply_stores.add(STORE_GENERAL)
        if not self._identify_staff_ready(snapshot):
            supply_stores.add(STORE_MAGIC)
        for store_type in supply_stores:
            self._town_store_attempted.pop(store_type, None)
            self._town_restock_rechecked.discard(store_type)
        return True

    def _start_identification_fundraising(self, snapshot: Snapshot) -> bool:
        """Enter fundraising to reach the post-mining Home-identification retry.

        The completed mining trip is the user-approved retry boundary that
        re-arms Home gear stranded in _processed_home_items. This fires only for
        that recoverable deadlock (see _identification_deadlock_recoverable) and
        only once every ordinary town errand is exhausted, so a routine visit is
        never diverted into mining.
        """
        if not self._identification_deadlock_recoverable(snapshot):
            return False
        self._planned_mining_runs = None
        self._identify_staff_mining_plan = False
        self._recall_stockout_mining_plan = False
        self._fundraising_mode = "prepare"
        self._town_store_attempted.clear()
        return True

    def _retry_processed_home_identification(self, snapshot: Snapshot) -> bool:
        """Re-arm one exhausted Home-identification pass when mining is a no-op.

        The mining retry driver cannot run at or above its gold target.  In that
        state, an incomplete Home item already marked as processed otherwise
        leaves the equipment departure gate false with no remaining town errand.
        Permit one direct retry per item and town visit; a second failure becomes
        a visible terminal equipment blocker instead of town wandering.
        """
        if snapshot.player.gold < FUNDRAISING_GOLD_TARGET:
            return False
        preparation = self._prepare_equipment_optimization(snapshot)
        if (
            preparation is None
            or preparation.result is None
            or "incomplete-equipment-catalog" not in preparation.blockers
        ):
            return False
        catalog = {owned.id: owned for owned in self._equipment_catalog.items}
        signatures: set[tuple[str, int, int]] = set()
        for item_id in preparation.result.incomplete_item_ids:
            owned = catalog.get(item_id)
            if owned is None or owned.origin != "home":
                return False
            signature = self._item_signature(owned.item)
            if signature not in self._processed_home_items:
                return False
            if signature in self._retried_home_identification_items:
                return False
            signatures.add(signature)
        if not signatures:
            return False
        self._processed_home_items.difference_update(signatures)
        self._retried_home_identification_items.update(signatures)
        self._rearm_town_store_for_new_work(STORE_HOME)
        self._retire_town_errand_plan_for_rebuild()
        self._equipment_optimization_signature = None
        self._equipment_optimization_preparation = None
        return True

    def _owns_lantern(self, snapshot: Snapshot) -> bool:
        """Return whether the lantern requirement is met by it or a better light."""
        return self._owns_usable_permanent_light(snapshot) or any(
            it.is_lantern for it in (*snapshot.inventory, *snapshot.equipment)
        )

    def _count_oil(self, snapshot: Snapshot) -> int:
        return sum(it.count for it in snapshot.inventory if it.is_oil)

    def _oil_below_departure_target(self, snapshot: Snapshot) -> bool:
        oil = self._supply_ledger(snapshot, self._planned_depth())["oil"]
        return oil.count < oil.required_departure

    def _count_food(self, snapshot: Snapshot) -> int:
        return sum(
            it.count
            for it in snapshot.inventory
            if it.is_food and it.sval >= FOOD_MIN_SVAL
        )

    def _needs_food_restock(self, snapshot: Snapshot) -> bool:
        # MANA races restock charged devices at the Magic shop. WATER/OIL/BLOOD
        # races (food_type 1/2/3) intentionally retain the normal-food fallback.
        return not self._food_ready(snapshot)
























    def _preferred_home_quest_launcher(
        self, snapshot: Snapshot, profile: StrategyProfile
    ) -> InventoryItem | StoreItem | None:
        ammo_tval = self._quest_launcher_ammo(snapshot, profile.required_force)
        selected_launcher = self._quest_uses_selected_launcher(
            profile.required_force
        )
        equipped = self._equipped_launcher(snapshot)
        if self._quest_launcher_meets_force(equipped, profile.required_force):
            return None
        home = [
            owned.item
            for owned in self._equipment_catalog.items
            if owned.origin == "home"
            and owned.item.tval == TVAL_BOW
            and (selected_launcher or owned.item.ammo_tval == ammo_tval)
            and self._quest_launcher_meets_force(
                owned.item, profile.required_force
            )
        ]
        if not home:
            return None
        preferred = max(home, key=self._quest_launcher_quality)
        carried = [
            item for item in snapshot.inventory
            if item.tval == TVAL_BOW
            and (selected_launcher or item.ammo_tval == ammo_tval)
            and self._quest_launcher_meets_force(item, profile.required_force)
        ]
        if carried and self._quest_launcher_quality(preferred) <= max(
            self._quest_launcher_quality(item) for item in carried
        ):
            return None
        return preferred



    @staticmethod
    def _has_charged_stone_to_mud(snapshot: Snapshot) -> bool:
        return any(
            item.tval == TVAL_WAND
            and item.sval == SV_WAND_STONE_TO_MUD
            and item.charges > 0
            for item in (*snapshot.inventory, *snapshot.equipment)
        )




























    def _entrance_travel_key(self, snapshot: Snapshot, goal: Position | None) -> str | None:
        """Native-travel leg of the surface walk to the dungeon entrance.

        Walking the ~100-tile town/wilderness leg costs one bot decision (a full
        snapshot round-trip) PER TILE; the travel command crosses it in one
        command, so prefer it whenever _descent_step is heading for a far
        surface goal. Progress is judged by distance-to-goal: an interruption
        (a monster, a nudge Escape) just re-issues travel, while
        TOWN_TRAVEL_STALL_LIMIT issues with no progress at all latch a
        fallback to BFS walking (the game rejects travel over an unknown
        approach — the existing explore-toward path handles that)."""
        if snapshot.dungeon_level != 0 or goal is None:
            return None
        if not self._dungeon_entry_allowed(
            snapshot,
            via_recall=False,
            destination_depth=self._dungeon_entry_depth(
                snapshot, self._active_dungeon_target(), via_recall=False
            ),
        ):
            return None
        entrance = snapshot.grids.get(goal)
        if entrance is None or not self._is_active_dungeon_entrance(entrance):
            return None
        if self.last_reason not in {"seek-downstairs", "approach-descent"}:
            return None
        if not self._has_light_equipped(snapshot):
            return None
        # The stall nudge has already waited COMMAND_RESPONSE_GRACE and sent
        # Escape before this duplicate snapshot is reconsidered. Reopening the
        # same entrance selector can therefore only repeat a rejected route.
        # Give the goal straight back to BFS walking after that first failure.
        state = self._town_travel_state
        if (
            state is not None
            and state.goal == goal
            and state.last_turn == snapshot.turn
            and snapshot.player.position.distance_to(goal) >= state.best_distance
        ):
            self._town_travel_fallback = goal
            self._release_town_travel_claim("town-travel:entrance-rejected")
            self._town_travel_state = None
            return None
        clear_traveler = self._town_clear_traveler_key(snapshot, goal)
        if clear_traveler is not None:
            return clear_traveler
        return self._town_travel_key(
            snapshot, goal, ENTRANCE_TRAVEL_MACRO, "town:travel-entrance"
        )



    def _active_dungeon_target(self) -> int:
        if self._fundraising_mode in {"mine", "scavenge"}:
            return DUNGEON_YEEK_CAVE
        return self._target_dungeon_id


    def _is_forgetting_maze(self, snapshot: Snapshot) -> bool:
        info = self._dungeon_knowledge.get(snapshot.floor_key[0])
        flags = getattr(info, "flags", frozenset()) if info is not None else frozenset()
        return "MAZE" in flags and "FORGET" in flags

    def _recall_unready_blockers(
        self, snapshot: Snapshot, destination: int
    ) -> list[str]:
        """Return safety regressions that can justify cancelling an active recall.

        Pack readiness has exactly one authority: _town_pack_space_ready.  It
        accepts the terminal four-slot certificate written by the town fallback
        and must never be re-derived here (2026-09-12: the duplicate arithmetic
        caused nine 237-gold recall replacements).  Other genuinely changed
        readiness facts may still justify cancellation.
        Optional surplus Home deposits deliberately gate neither departure nor
        an active recall; they wait for the next town visit.

        One source (recall-read-cancel-pingpong, 2026-09-25): every blocker is
        a leaf of ``_recall_town_departure_conjuncts`` -- the map the read
        point requires to be all true -- evaluated on
        ``_recall_departure_board``, the board the armed read was authorised
        on.  A recall the read point authorised therefore has no blocker until
        some leaf genuinely changes; the read's own consumption is not one.
        """
        leaves = self._recall_town_departure_conjuncts(
            self._recall_departure_board(snapshot)
        )
        blockers: list[str] = []
        # Food gates a new town departure. An already armed recall belongs
        # to Hengband; the carried-only decision does not authorise cancelling
        # it for food alone (suitefix3 task, 2026-10-04).
        if not leaves["free_pack_slots_ready"]:
            blockers.append("pack-too-full")
        if (
            snapshot.player.class_id >= 0
            and not leaves["combat_weapon_ready"]
        ):
            blockers.append("weapon-not-ready")
        landing_depth = snapshot.dungeon_recall_depths.get(destination, 0)
        if landing_depth > 20 and not leaves["equipment_departure_ready"]:
            blockers.append("deep-loadout-unconfirmed")
        return blockers



    @staticmethod
    def _has_cursed_equipment(snapshot: Snapshot) -> bool:
        return any(item.is_cursed for item in snapshot.equipment)

    def _has_normal_remove_curse_target(self, snapshot: Snapshot) -> bool:
        return any(
            item.is_cursed
            and not self._curse_unremovable(item)
            and self._item_signature(item) not in getattr(self, "_permanent_cursed_items", ())
            for item in snapshot.equipment
        )


    def _has_unremovable_curse_target(self, snapshot: Snapshot) -> bool:
        return any(
            item.is_cursed and self._curse_unremovable(item)
            and self._item_signature(item) not in getattr(self, "_permanent_cursed_items", ())
            for item in snapshot.equipment
        )

    def _normal_remove_curse_actionable_this_visit(self, snapshot: Snapshot) -> bool:
        if not self._has_normal_remove_curse_target(snapshot):
            return False
        if any(
            item.is_scroll and item.aware and item.sval == SV_SCROLL_REMOVE_CURSE
            for item in snapshot.inventory
        ):
            return True
        store = snapshot.store
        if store is not None and store.store_type in {STORE_ALCHEMIST, STORE_TEMPLE}:
            return any(
                item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_REMOVE_CURSE
                and item.price <= snapshot.player.gold
                for item in store.items
            )
        suppliers = (STORE_ALCHEMIST, STORE_TEMPLE)
        if self._town_map_active(snapshot) and all(
            self._town_map.store_position(supplier) is None for supplier in suppliers
        ):
            return False
        return any(
            price <= snapshot.player.gold
            for supplier in suppliers
            for price, _units in self._town_visit_ledger.shelf_observations.get(
                (supplier, "remove-curse"), ())
        )


    @staticmethod
    def _carried_star_remove_curse_count(snapshot: Snapshot) -> int:
        return sum(
            item.count
            for item in snapshot.inventory
            if item.tval == TVAL_SCROLL
            and item.sval == SV_SCROLL_STAR_REMOVE_CURSE
        )


    def _observe_star_remove_curse_reserve_inflight(
        self, snapshot: Snapshot
    ) -> None:
        buy_watch = self._star_remove_curse_reserve_buy_inflight
        if buy_watch is not None:
            signature, before_count = buy_watch
            if self._inventory_signature_count(snapshot, signature) > before_count:
                self._star_remove_curse_reserve_buy_inflight = None
            elif (
                snapshot.store is None
                or snapshot.store.store_type != STORE_TEMPLE
            ):
                self._star_remove_curse_reserve_buy_inflight = None

        deposit_watch = self._star_remove_curse_reserve_deposit_inflight
        if deposit_watch is not None:
            signature, before_count = deposit_watch
            if self._inventory_signature_count(snapshot, signature) < before_count:
                self._star_remove_curse_reserve_deposit_inflight = None
                self._star_remove_curse_reserve_deposit_pending = False
                self._home_star_remove_curse_count = (
                    self._home_star_remove_curse_count or 0
                ) + 1
            elif (
                snapshot.store is None
                or snapshot.store.store_type != STORE_HOME
            ):
                self._star_remove_curse_reserve_deposit_inflight = None

    def _observe_remove_curse(self, snapshot: Snapshot) -> None:
        cursed_signatures = {
            self._item_signature(item)
            for item in snapshot.equipment
            if item.is_cursed
        }
        self._heavy_cursed_items.intersection_update(cursed_signatures)
        self.__dict__.setdefault("_permanent_cursed_items", set()).intersection_update(cursed_signatures)
        watch = self._remove_curse_watch
        if watch is None:
            return
        self._remove_curse_watch = None
        signature, scroll_sval, previous_count = watch
        current_count = sum(
            item.count for item in snapshot.inventory
            if item.is_scroll and item.aware and item.sval == scroll_sval
        )
        # A disturbance can reject a queued read without consuming anything.
        # Only a confirmed inventory delta makes it an attempt.
        if current_count >= previous_count:
            return
        still_cursed = any(
            item.is_cursed and self._item_signature(item) == signature
            for item in snapshot.equipment
        )
        if not still_cursed:
            self._heavy_cursed_items.discard(signature)
            return
        if scroll_sval == SV_SCROLL_REMOVE_CURSE:
            self._heavy_cursed_items.add(signature)
            self._heavy_curse_inscription_pending = signature
        elif scroll_sval == SV_SCROLL_STAR_REMOVE_CURSE:
            self._permanent_cursed_items.add(signature)

    @claims(ClaimOwner.EQUIPMENT_TXN)
    def _heavy_curse_inscription_key(self, snapshot: Snapshot) -> str | None:
        stale_tag = next(
            (
                item for item in snapshot.equipment
                if not item.is_cursed and HEAVY_CURSE_TAG in item.inscription
            ),
            None,
        )
        if stale_tag is not None:
            slot_key = EQUIPMENT_SLOT_KEY.get(stale_tag.slot)
            if slot_key is None:
                self._offer_execution_no_step(
                    producer="equipment-txn", work_id="heavy-curse-tag",
                    cause="tag-slot-unavailable",
                )
                return None
            self._heavy_cursed_items.discard(self._item_signature(stale_tag))
            cleaned = stale_tag.inscription.replace(HEAVY_CURSE_TAG, "").strip()
            if not cleaned:
                self.last_reason = "equipment:clear-heavy-curse-tag"
                key = reserved_item_command(self, snapshot, "uninscribe-equipped", stale_tag, "equipment-txn", address=slot_key)
                if key is None:
                    return None
                self._offer_execution(
                    key, producer="equipment-txn", work_id="heavy-curse-tag",
                    next_step="equipment.clear-heavy-curse-tag",
                    expected_effect="stale-tag-removed",
                )
                return key
            self.last_reason = "equipment:remove-heavy-curse-tag"
            prefix = reserved_item_command(self, snapshot, "inscribe-equipped", stale_tag, "equipment-txn", address=slot_key)
            if prefix is None:
                return None
            key = prefix + cleaned + "\r"
            self._offer_execution(
                key, producer="equipment-txn", work_id="heavy-curse-tag",
                next_step="equipment.remove-heavy-curse-tag",
                expected_effect="stale-tag-removed",
            )
            return key

        signature = self._heavy_curse_inscription_pending
        if signature is None or not snapshot.in_town:
            self._offer_execution_no_step(
                producer="equipment-txn", work_id="heavy-curse-tag",
                cause="no-town-heavy-curse-work",
            )
            return None
        target = next(
            (
                item for item in snapshot.equipment
                if item.is_cursed and self._item_signature(item) == signature
            ),
            None,
        )
        if target is None or HEAVY_CURSE_TAG in target.inscription:
            self._heavy_curse_inscription_pending = None
            self._offer_execution_no_step(
                producer="equipment-txn", work_id="heavy-curse-tag",
                cause="tag-target-unavailable-or-complete",
            )
            return None
        if snapshot.store is not None:
            self.last_reason = "equipment:leave-store-to-mark-heavy-curse"
            self._offer_execution(
                LEAVE_STORE_KEY, producer="equipment-txn",
                work_id="heavy-curse-tag",
                next_step="store.leave-for-heavy-curse-tag",
                expected_effect="store-exited",
            )
            return LEAVE_STORE_KEY
        slot_key = EQUIPMENT_SLOT_KEY.get(target.slot)
        if slot_key is None:
            self._offer_execution_no_step(
                producer="equipment-txn", work_id="heavy-curse-tag",
                cause="target-slot-unavailable",
            )
            return None
        self._heavy_curse_inscription_pending = None
        # The initial inscription opens in overwrite mode. Ctrl-E moves to its
        # end and switches to insert mode before the persistent marker is added.
        suffix = "\x05 " + HEAVY_CURSE_TAG
        self.last_reason = "equipment:mark-heavy-curse"
        prefix = reserved_item_command(self, snapshot, "inscribe-equipped", target, "equipment-txn", address=slot_key)
        if prefix is None:
            return None
        key = prefix + suffix + "\r"
        self._offer_execution(
            key, producer="equipment-txn", work_id="heavy-curse-tag",
            next_step="equipment.mark-heavy-curse-tag",
            expected_effect="heavy-curse-tag-added",
        )
        return key

    def _find_remove_curse_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval in {SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE},
        )




    def _observe_launcher_enchant(self, snapshot: Snapshot) -> None:
        watch = self._launcher_enchant_watch
        if watch is None:
            return
        self._launcher_enchant_watch = None
        sval, signature, previous_bonus = watch
        launcher = self._equipped_launcher(snapshot)
        if launcher is None or self._item_signature(launcher) != signature:
            return
        current_bonus = (
            launcher.to_h
            if sval == SV_SCROLL_ENCHANT_WEAPON_TO_HIT
            else launcher.to_d
        )
        # No increase means failure or a wrong target. The per-visit attempted
        # latch remains set, so either case is bounded instead of carouselling.
        if current_bonus <= previous_bonus:
            return
        self._launcher_enchant_attempted.discard(sval)



    def _needs_random_teleport_suppression(
        self, owned, selected_ids: frozenset[str]
    ) -> bool:
        item = owned.item
        return (
            item.is_equipment
            and item.known
            and not item.is_cursed
            and not owned.random_teleport_suppressed
            and (
                TR_TELEPORT in item.known_flags
                or (
                    owned.id in selected_ids
                    and owned.evaluable
                    and not item.fully_known
                    and item_requires_full_identification(item)
                )
            )
        )

    def _selected_random_teleport_suppressions(self, preparation) -> tuple:
        selected_ids = self._equipment_preparation_selected_ids(preparation)
        return tuple(
            owned
            for owned in self._equipment_catalog.items
            if owned.id in selected_ids
            and self._needs_random_teleport_suppression(owned, selected_ids)
        )

    def _has_selected_home_random_teleport_suppression(
        self, snapshot: Snapshot
    ) -> bool:
        preparation = self._prepare_equipment_optimization(snapshot)
        return any(
            owned.origin == "home"
            for owned in self._selected_random_teleport_suppressions(preparation)
        )

    def _random_teleport_suppression_actionable(
        self, snapshot: Snapshot, preparation
    ) -> bool:
        return any(
            owned.origin == "pack"
            or (
                owned.origin == "equipped"
                and owned.equipped_slot in EQUIPMENT_SLOT_KEY
            )
            or (
                owned.origin == "home"
                and self._home_available(snapshot)
                and STORE_HOME not in self._town_store_attempted
                and self._item_signature(owned.item)
                not in self._deferred_home_items
            )
            for owned in self._selected_random_teleport_suppressions(preparation)
        )











    def departure_block_state(
        self, snapshot: Snapshot | None = None
    ) -> dict[str, object]:
        """Return only the departure block observed by the current decision.

        ``snapshot`` identifies the recorder call but is deliberately not
        evaluated here: departure evaluation can prepare the optimizer and
        publish a confirmed loadout.  A latch from an earlier decision is not
        an observation for this row.  The writer omits an empty result, so a
        missing ``departure_block`` can mean either "not evaluated this
        decision" or "evaluated and ready".  Consumers must not distinguish
        those byte-identical cases.
        """
        if (
            snapshot is not None
            and self._departure_block_sequence != self._decision_sequence
        ):
            return {}
        return self._departure_block

    def _equipped_digging_tool(self, snapshot: Snapshot) -> InventoryItem | None:
        return next((it for it in snapshot.equipment if it.is_digging_tool), None)

    @staticmethod
    def _pack_has_melee_weapon(snapshot: Snapshot) -> bool:
        return any(it.is_melee_weapon for it in snapshot.inventory)

    def _pack_has_safe_melee_weapon(self, snapshot: Snapshot) -> bool:
        return any(
            item.is_melee_weapon
            and not self._equip_blocked_by_identification(item)
            and not item.is_broken
            and not self._blocks_teleport(item)
            for item in snapshot.inventory
        )

    def _combat_weapon_ready(self, snapshot: Snapshot) -> bool:
        """Pre-recall check: is a real weapon wielded? A mining digger (pickaxe) in the
        main hand is NOT a combat weapon — recalling into a fighting dungeon on it is what
        made the character churn supplies. Block the dive until the real weapon is re-armed
        (from the pack via _town_restore_weapon_key, or withdrawn from the Home — see
        _next_required_store_type routing). The streak backstop lets us dive anyway if we
        have been stuck in town this long unable to re-arm (we simply own no weapon)."""
        weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        if weapon is not None and self._blocks_teleport(weapon):
            return False
        # An ordinary curse is actionable town work, not a usable combat
        # loadout. Reject it until Remove Curse succeeds. A confirmed heavy or
        # permanent curse remains the bounded exception because normal removal
        # has already been attempted and recorded persistently.
        if (
            weapon is not None
            and weapon.is_cursed
            and not self._curse_unremovable(weapon)
        ):
            return False
        if weapon is not None and weapon.is_melee_weapon:
            return True
        if self._equipped_digging_tool(snapshot) is None:
            return True
        return self._weapon_block_streak >= WEAPON_BLOCK_LIMIT






    @claims(ClaimOwner.DETECTORS)
    def _breakout_restore_weapon_key(self, snapshot: Snapshot) -> str | None:
        """Re-arm the weapon displaced solely for a dig-to-stairs breakout."""
        if self._breakout_dig_floor is None:
            return None
        if self._equipped_digging_tool(snapshot) is None:
            self._breakout_dig_floor = None
            return None
        weapon = self._first_item(
            snapshot,
            lambda it: it.is_equipment
            and it.is_melee_weapon
            and not it.is_digging_tool
            and not self._blocks_teleport(it)
            and (
                self._normal_weapon_name is None
                or it.name == self._normal_weapon_name
            ),
        )
        if weapon is None:
            return None
        self.last_reason = "breakout:restore-combat-weapon"
        key = self._wield_weapon_key(snapshot, weapon)
        if key is not None:
            self._equipment_mutation_post_commit = (key, "breakout-restore")
        return key



    def _finish_mining_floor(self, snapshot: Snapshot) -> str:
        return self._leave_fundraising_floor(
            snapshot,
            allow_recall=not (
                self._fundraising_mode == "mine"
                and self._breeder_breakthrough_floor == snapshot.floor_key
            ),
        )





    def _drop_mining_vein(self, vein: Position) -> None:
        """Give up on ONE vein without ending the floor run. The dropped set is
        what makes this stick: _observe re-adds any still-golden grid to
        _known_treasure every observation, so a bare discard would re-select
        the same failed vein instead of moving on to the next."""
        self._known_treasure.discard(vein)
        if vein not in self._mining_dropped_veins:
            self._mining_dropped_veins.add(vein)
            self._mining_veins_dropped += 1




    def _reset_mining_sweep_progress(self, snapshot: Snapshot) -> None:
        self._mining_sweep_steps = 0
        self._mining_sweep_no_progress = 0
        self._mining_sweep_revealed_grids = len(snapshot.grids)
        self._mining_sweep_goal = None
        self._mining_sweep_goal_distance = None
        self._mining_sweep_escape_pairs.clear()
        self._mining_target_distance = None
        self._mining_target_revealed_grids = len(snapshot.grids)
        self._mining_target_collected = self._mining_veins_collected



    def _nearest_upstairs(self, snapshot: Snapshot) -> Position | None:
        """Nearest tile known to hold up-stairs, reachable by walking or not."""
        start = snapshot.player.position
        stairs = [
            grid.position
            for grid in snapshot.grids.values()
            if self._is_upstairs_target(grid) and grid.position != start
        ]
        if not stairs:
            return None
        return min(stairs, key=lambda p: (start.distance_to(p), p.y, p.x))

    def _nearest_remembered_floor(self, snapshot: Snapshot) -> Position | None:
        """Nearest remembered walkable tile other than where we stand — the target to
        dig back toward when a mining pocket has no walkable neighbour left."""
        start = snapshot.player.position
        best: Position | None = None
        best_key: tuple[int, int, int] | None = None
        for y, x in self._remembered_floor_t:
            if (y, x) == (start.y, start.x):
                continue
            key = (start.distance_to(Position(y, x)), y, x)
            if best_key is None or key < best_key:
                best_key = key
                best = Position(y, x)
        return best

    def _treasure_step(self, snapshot: Snapshot) -> Position | None:
        # Dropped veins are excluded here even though _observe keeps re-adding
        # them to _known_treasure while their gold is visible — otherwise
        # "skip this vein" would immediately re-select it.
        candidates = self._known_treasure - self._mining_dropped_veins
        target = self._treasure_target
        if target is not None and target in candidates:
            step = self._treasure_target_step(snapshot, target)
            if step is not None:
                return step

        # Commit to the first reachable vein. Re-selecting the nearest vein on
        # every turn can reverse direction at a junction when detected terrain
        # or temporary blockers change, leaving several treasures uncollected.
        approaches: dict[Position, list[Position]] = {}
        for treasure in candidates:
            for dy, dx in NEIGHBOR_OFFSETS:
                approach = Position(treasure.y + dy, treasure.x + dx)
                approaches.setdefault(approach, []).append(treasure)

        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            if pos != start and pos in approaches:
                selected = min(
                    approaches[pos], key=lambda item: (item.y, item.x)
                )
                if selected != self._treasure_target:
                    self._treasure_target = selected
                    self._mining_route_visits.clear()
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                # Avoided cells (latched warning grids, engagement retreats)
                # cost lethal-danger weight in every other routing BFS; a
                # mining route through one would repeat _step_toward's
                # refusal forever on this static floor.  Veins reachable only
                # through them are simply not selected.
                if neighbor in seen or neighbor in self._engagement_avoid_cells:
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        if target not in candidates:
            self._release_claim_goal("treasure-no-route", target, owners=("fundraising",))
            self._treasure_target = None
        return None

    def _treasure_target_step(
        self, snapshot: Snapshot, target: Position
    ) -> Position | None:
        """Route beside a vein using remembered floor outside the current view."""
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            if pos != start and (
                pos.distance_to(target) == 1
            ):
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                # Same lethal-danger weight as every other routing BFS (see
                # _treasure_step): never route the mining walk through an
                # avoided cell.
                if neighbor in seen or neighbor in self._engagement_avoid_cells:
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        return None



    def _position_target_step(
        self, snapshot: Snapshot, target: Position
    ) -> Position | None:
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            if pos == target:
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen or neighbor in self._engagement_avoid_cells:
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        return None

    def _current_floor_item_key(
        self,
        snapshot: Snapshot,
        *,
        pickup_reason: str,
        trigger_reason: str,
    ) -> str | None:
        if len(snapshot.inventory) >= PACK_CAPACITY:
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or here.object_count <= 0:
            return None
        if here.position in self._deferred_loot:
            return None
        if not self._position_changed:
            # Avoided cells (latched warning grids, engagement retreats) are
            # excluded up front: this static wiggle re-picks the same
            # min-visit neighbour every decision, so an avoided pick would
            # repeat _step_toward's refusal forever.  With no admissible
            # neighbour the pickup below is the exit.
            neighbors = [
                neighbor
                for neighbor in self._walkable_neighbors(
                    snapshot, snapshot.player.position
                )
                if neighbor not in self._engagement_avoid_cells
            ]
            if neighbors:
                step = min(neighbors, key=lambda pos: self._visit_counts[pos])
                self.last_reason = trigger_reason
                return self._step_toward(snapshot, step)
        self.last_reason = pickup_reason
        if pickup_reason == "pickup":
            self.prompt_owner_handoff = "seek-loot"
        self._pending_loot_pickup = (
            snapshot.floor_key,
            here.position,
            here.object_count,
        )
        # Hengband picks a lone floor item immediately, but a pile opens the
        # floor-item chooser and waits for one selection per item. Each accepted
        # selection rebuilds the list, so repeatedly choosing its first entry
        # drains the whole pile in the same command cycle.
        if here.object_count > 1:
            return PICKUP_KEY + ("a" * here.object_count)
        return PICKUP_KEY

    @claims(ClaimOwner.FLOOR_LOOT)
    def _victory_loot_key(self, snapshot: Snapshot) -> str | None:
        if not self._yeek_victory_loot or snapshot.floor_key[0] != DUNGEON_YEEK_CAVE:
            return None
        if len(snapshot.inventory) >= PACK_CAPACITY:
            triage = self._full_pack_loot_triage_key(snapshot)
            if triage is not None:
                return triage
            self._note_return_start(None)
            self._returning_to_town = True
            return self._return_to_town_key(
                snapshot, self._strategic_hostiles(snapshot)
            )
        current_loot = self._current_floor_item_key(
            snapshot,
            pickup_reason="victory:pickup",
            trigger_reason="victory:trigger-autodestroy",
        )
        if current_loot is not None:
            return current_loot
        step = self._loot_step(snapshot)
        if step is not None:
            self.last_reason = "victory:seek-loot"
            self._declare_reach(self._loot_target)
            return self._step_toward(snapshot, step)
        self._note_return_start(None)
        self._returning_to_town = True
        return self._return_to_town_key(
            snapshot, self._strategic_hostiles(snapshot)
        )


    def approved_quest_strategy(self, quest_id: int) -> StrategyProfile | None:
        """Return only a user-approved, executable profile."""
        profile = self._quest_strategies.get(quest_id)
        return profile if profile is not None and profile.execution_eligible else None


    def _visible_engagement_is_immobile_ranged_less(
        self, hostiles: list[MonsterState]
    ) -> bool:
        """Return whether every visible hostile must stay put and use melee."""
        visible = [
            monster
            for monster in hostiles
            if monster.perception != "detected"
        ]
        return bool(visible) and all(
            (knowledge := self._monrace_knowledge.get(monster.race_id)) is not None
            and "NEVER_MOVE" in knowledge.flags
            and knowledge.max_ranged_damage <= 0
            for monster in visible
        )






    def _immediate_quest_targets(
        self,
        profile: StrategyProfile,
        hostiles: list[MonsterState],
    ) -> list[MonsterState]:
        """Return visible targets that must preempt the current quest phase."""
        priority_races = tuple(
            int(race_id)
            for race_id in profile.engagement_plan.get(
                "immediate_priority_targets", ()
            )
        )
        for race_id in priority_races:
            targets = [
                monster for monster in hostiles
                if monster.race_id == race_id
            ]
            if targets:
                return targets
        return []





    # Kept as a narrow tactical probe for downstream policy integrations. Floor
    # dispatch never calls it: QuestFloorNavigator is the sole on-floor owner.
    def _approved_quest_strategy_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        return self._quest_execute_key(snapshot, hostiles, adjacent)





    def _approved_strategy_force_ready(
        self, snapshot: Snapshot, profile: StrategyProfile
    ) -> bool:
        force = self._strategy_force_for_snapshot(snapshot, profile)
        weapon = next((it for it in snapshot.equipment if it.slot == "main_hand"), None)
        # New strategy profiles must declare their target scale.  The fallback
        # preserves old third-party profiles without silently changing them.
        reference_ac = int(force.get("reference_ac", 100))
        dps = (
            weapon_expected_dps(
                snapshot,
                weapon,
                reference_ac,
                self._validated_character_calibration(snapshot),
            )
            if weapon is not None else 0.0
        )
        # Readiness evaluates the weapon that is already wielded.  Unlike a
        # hypothetical loadout comparison, that score does not require us to
        # reconstruct natural stats: the emitter exposes the resulting blows
        # and hand bonuses directly.  Fresh CL1 characters have not completed
        # a current character calibration yet, so use those observed combat results as a
        # conservative unbranded score instead of calling a real weapon 0 DPS.
        if dps is None and weapon is not None:
            blows = max(0, snapshot.player.main_hand_blows)
            if snapshot.player.melee_displayed_totals:
                from hengbot.warrior_equipment_evaluator import displayed_melee_hit_chance
                chance = (displayed_melee_hit_chance(
                    snapshot.player.melee_skill, snapshot.player.main_hand_to_h, reference_ac
                ) if snapshot.player.main_hand_to_h is not None else 0.0)
            else:
                hand_to_h = snapshot.player.main_hand_to_h - weapon.to_h
                chance = melee_hit_chance(
                    snapshot.player.melee_skill,
                    hand_to_h,
                    weapon.to_h,
                    reference_ac,
                )
            average_dice = (
                weapon.damage_dice_num * (weapon.damage_dice_sides + 1) / 2.0
            )
            damage = (max(0.0, average_dice + snapshot.player.main_hand_to_d)
                      if snapshot.player.main_hand_to_d is not None else 0.0)
            dps = blows * chance * damage
        dps = float(dps or 0.0)
        carry_status = self._quest_carry_status(snapshot, force)
        carries_ready = all(bool(item["ready"]) for item in carry_status.values())
        resists_ready = all(
            self._profile_resistance_name(str(name)) in snapshot.player.abilities
            for name in force.get("resists", ())
        )
        speed_count = self._exact_potion_count(snapshot, SV_POTION_SPEED)
        healing = self._exact_potion_count(snapshot, SV_POTION_HEALING)
        details = {
            "reference_ac": reference_ac,
            "dps": {"measured": dps, "required": float(force.get("min_expected_dps", 0) or 0)},
            "hp": {"measured": snapshot.player.max_hp, "required": int(force.get("min_hp", 0))},
            "carries": carry_status,
            "speed_potions": {"measured": speed_count, "required": int(force.get("speed_potions", 0))},
            "heal_potions": {"measured": healing, "required": int(force.get("heal_potions", 0))},
            "resists": {"ready": resists_ready, "required": list(force.get("resists", ()))},
        }
        lit_torch = carry_status.get("throwing_items.lit_torch")
        if lit_torch is not None:
            details["lit_torch"] = {
                "measured": lit_torch["measured"],
                "required": lit_torch["required"],
            }
        self._fixed_quest_readiness["strategy_force"] = details
        if not carries_ready or not resists_ready:
            details["failed"] = [
                name for name, item in carry_status.items()
                if not bool(item["ready"])
            ]
            if not resists_ready:
                details["failed"].append("resists")
            return False
        no_heal = force.get("no_healing_tier")
        if isinstance(no_heal, dict) and (
            snapshot.player.max_hp >= int(no_heal.get("min_hp", 0))
            and dps >= float(no_heal.get("min_expected_dps", 0) or 0)
        ):
            details["failed"] = []
            return True
        details["failed"] = [
            name for name, ready in (
                ("hp", snapshot.player.max_hp >= int(force.get("min_hp", 0))),
                ("dps", dps >= float(force.get("min_expected_dps", 0) or 0)),
                ("speed_potions", speed_count >= int(force.get("speed_potions", 0))),
                ("heal_potions", healing >= int(force.get("heal_potions", 0))),
            ) if not ready
        ]
        return (
            snapshot.player.max_hp >= int(force.get("min_hp", 0))
            and dps >= float(force.get("min_expected_dps", 0) or 0)
            and speed_count >= int(force.get("speed_potions", 0))
            and healing >= int(force.get("heal_potions", 0))
        )


    @claims(ClaimOwner.QUEST_REQUEST)
    def _telmora_q2_travel_key(
        self, snapshot: Snapshot, quest: QuestState
    ) -> str | None:
        """Use the inn service for the approved Q2 errand, never wilderness."""
        if self._defer_town_errand(
                "quest-request", "q2-travel", preserve_home_hold=False):
            return None
        if self._cross_town_shopping_holds_quest_travel(snapshot):
            return None
        if snapshot.visited_town_ids is None or 1 not in snapshot.visited_town_ids:
            return None
        if (
            self._effective_town_id(snapshot) == 1
            and self._telmora_q2_errand
            and quest.status in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}
        ):
            key = self._town_teleport_key(snapshot, 0, producer="quest-request", reason="fixedquest:q2-teleport")
            if key is not None:
                self.last_reason = "fixedquest:q2-teleport"
            return key
        if self.approved_quest_strategy(2) is None:
            return None
        if self._effective_town_id(snapshot) == 0 and quest.status in {
            QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN, QUEST_STATUS_COMPLETED
        }:
            if 2 not in EXECUTABLE_QUEST_STRATEGY_IDS:
                return None
            if quest.status == QUEST_STATUS_UNTAKEN and not self._fixed_quest_ready(snapshot, 2):
                return None
            if snapshot.player.gold < RUMOR_GOLD_RESERVE + 1000:
                self._fundraising_mode = "prepare"
                self.last_reason = "fixedquest:q2-travel-needs-funds"
                return WAIT_KEY
            self._telmora_q2_errand = True
            key = self._town_teleport_key(snapshot, 1, producer="quest-request", reason="fixedquest:q2-teleport")
            if key is not None:
                self.last_reason = "fixedquest:q2-teleport"
            return key
        return None


    def _active_fixed_quest_id(self, snapshot: Snapshot) -> int | None:
        """Return the allowlisted TAKEN fixed quest whose floor we occupy."""
        quest_id = snapshot.floor_key[2]
        if quest_id not in FIXED_QUEST_ALLOWLIST:
            return None
        quest = snapshot.quests.get(quest_id)
        if quest is None or quest.status != QUEST_STATUS_TAKEN:
            return None
        return quest_id

    def _active_kill_quest_id(self, snapshot: Snapshot) -> int | None:
        """Return an incomplete runtime kill quest occupying the current floor."""
        dungeon_id, level, floor_quest_id = snapshot.floor_key
        for quest in snapshot.quests.values():
            info = self._quest_knowledge.get(quest.id)
            quest_type = info.type if info is not None else quest.type
            target = self._kill_quest_completion_target(quest, info)
            quest_dungeon = (
                info.dungeon if info is not None else quest.dungeon_id
            )
            quest_level = info.level if info is not None else quest.level
            if (
                quest.status == QUEST_STATUS_TAKEN
                and quest_type
                in {
                    QUEST_TYPE_KILL_LEVEL,
                    QUEST_TYPE_KILL_NUMBER,
                    QUEST_TYPE_RANDOM,
                }
                and (
                    quest.cur_num is None
                    or target is None
                    or quest.cur_num < target
                )
                and (
                    floor_quest_id == quest.id
                    or (
                        quest_dungeon is not None
                        and dungeon_id == quest_dungeon
                        and level == quest_level
                    )
                )
            ):
                return quest.id
        return None

    def _active_quest_id(self, snapshot: Snapshot) -> int | None:
        """Return any active fixed, kill, or random quest on this floor."""
        return self._active_fixed_quest_id(snapshot) or self._active_kill_quest_id(
            snapshot
        )


    def _visible_unviable_quest_target(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> bool:
        quest_id = self._active_kill_quest_id(snapshot)
        if quest_id is None or self.approved_quest_strategy(quest_id) is not None:
            return False
        race_id = self._quest_target_race_id(snapshot.quests[quest_id])
        if race_id is None or race_id <= 0:
            return False
        targets = [
            monster for monster in hostiles if monster.race_id == race_id
        ]
        if len(targets) != 1:
            return False
        weapon = next(
            (
                item
                for item in snapshot.equipment
                if item.slot == "main_hand"
            ),
            None,
        )
        if (
            weapon is None
            or snapshot.player.main_hand_blows <= 0
            or self._main_hand_dps(snapshot, weapon) <= 0
        ):
            # No projection inputs means "unknown", not an unwinnable verdict.
            return False
        target = targets[0]
        if (
            self._unique_fight_projection(
                snapshot,
                hostiles,
                target,
                player_speed=snapshot.player.speed,
            )
            is not None
        ):
            return False
        speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
        return speed is None or self._unique_fight_projection(
            snapshot,
            hostiles,
            target,
            player_speed=snapshot.player.speed + SPEED_POTION_BONUS,
            extra_turns=1,
        ) is None

    def _latch_unviable_quest_return(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> None:
        """Delegate a visible unwinnable runtime quest to the return owner."""
        if (
            self._unviable_quest_floor != snapshot.floor_key
            and self._visible_unviable_quest_target(snapshot, hostiles)
        ):
            self._unviable_quest_floor = snapshot.floor_key
        if self._unviable_quest_floor != snapshot.floor_key:
            return
        self._note_return_start("quest-unviable")
        self._returning_to_town = True
        self._last_return_trigger = "quest-unviable"



    def _deepest_floor_escape_kit_empty(self, snapshot: Snapshot) -> bool:
        """Return whether this deepest floor has no usable scroll escape rung."""
        recall_max_depth = snapshot.dungeon_recall_depths.get(
            snapshot.floor_key[0], snapshot.dungeon_level
        )
        return (
            snapshot.player.class_id >= 0
            and snapshot.dungeon_level >= recall_max_depth
            and self._find_phase_scroll(snapshot) is None
            and self._count_teleport_scrolls(snapshot) == 0
        )


    def _locked_kill_quest_targets(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> list[MonsterState]:
        """Return visible runtime quest targets that ordinary combat should own."""
        quest_id = self._active_kill_quest_id(snapshot)
        if (
            quest_id is None
            or not self._quest_floor_exit_locked(snapshot)
            or self.approved_quest_strategy(quest_id) is not None
        ):
            return []
        race_id = self._quest_target_race_id(snapshot.quests[quest_id])
        if race_id is None or race_id <= 0:
            return []
        return [monster for monster in hostiles if monster.race_id == race_id]

    def _floor_navigation_exit_locked(self, snapshot: Snapshot) -> bool:
        """Gate exhausted-floor stair navigation for every active quest kind."""
        return (
            self._active_fixed_quest_id(snapshot) is not None
            or self._quest_floor_exit_locked(snapshot)
        )




    def _known_fixed_quests(self, snapshot: Snapshot) -> dict[int, QuestState]:
        """Join disclosed fixed-quest state with sanctioned static knowledge."""
        known = dict(snapshot.quests)
        for quest_id in FIXED_QUEST_ALLOWLIST:
            if quest_id in known:
                continue
            info = self._quest_knowledge.get(quest_id)
            if info is None or info.flags & QUEST_FLAG_SILENT:
                continue
            # The emitter exports TAKEN, COMPLETED, TOWER STAGE_COMPLETED,
            # FINISHED, FAILED, and FAILED_DONE quests.  Therefore a missing,
            # non-silent allowlisted quest from the static table can only be
            # UNTAKEN.  Exported state always wins above, in every status.
            known[quest_id] = QuestState(
                id=quest_id,
                name=info.name,
                status=QUEST_STATUS_UNTAKEN,
                type=info.type,
                level=info.level,
                flags=info.flags,
                fixed=True,
            )
        return known






    def fixed_quest_readiness_state(self) -> dict:
        return dict(self._fixed_quest_readiness)









    def _bounty_cashout_key(self, snapshot: Snapshot) -> str | None:
        """Redeem every known wanted remain before ordinary town maintenance."""
        if not snapshot.in_town:
            return None
        bounties = [item for item in snapshot.inventory if item.is_bounty]
        if not bounties:
            return None

        def offer(key):
            self._offer_execution(
                key, producer="quest-request", work_id="normal-step4-bounty",
                next_step="bounty.resume", continuation="bounty.resume",
                expected_effect="bounty-removed", budget_ref="quest-request",
            )
            return key

        office_pos = (
            self._town_map.building_position(HUNTER_OFFICE_BUILDING_TYPE)
            if self._town_map_active(snapshot)
            else None
        )
        here = snapshot.grid_at(snapshot.player.position)
        on_office = (
            here is not None and here.building_type == HUNTER_OFFICE_BUILDING_TYPE
        ) or (office_pos is not None and snapshot.player.position == office_pos)
        if on_office:
            # Walking onto the office opens its menu; standing on it is a no-op,
            # so a path-to-self returns nothing and the office reads as "missing".
            # Hop to an adjacent tile and let the next approach walk back on to
            # cash out the remaining bounties (mirrors the store re-entry hop).
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                self.last_reason = "bounty:step-off"
                self._declare_reach(neighbors[0], note=CLAIM_GOAL_NOTE_ONE_STEP)
                return offer(self._step_toward(snapshot, neighbors[0]))
            self._offer_execution_no_step(
                producer="quest-request", work_id="normal-step4-bounty",
                cause="bounty-office-step-off-unavailable",
            )
            return None

        self._claim_target_capture = []
        try:
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: grid.building_type == HUNTER_OFFICE_BUILDING_TYPE,
            )
        finally:
            step_target = self._take_claim_target()
        if step is None and office_pos is not None:
            step = self._town_map_goal_step(snapshot, office_pos)
        if step is None:
            # The remains keep. An unavailable office must not strand other
            # town errands behind a sticky block, even after the bounty goes.
            self._offer_execution_no_step(
                producer="quest-request", work_id="normal-step4-bounty",
                cause="bounty-office-route-unavailable",
            )
            return None

        self.last_reason = "bounty:approach"
        self._declare_reach(office_pos if office_pos is not None else step_target)
        grid = snapshot.grid_at(step)
        enters_office = (
            grid is not None
            and grid.building_type == HUNTER_OFFICE_BUILDING_TYPE
        ) or (office_pos is not None and step == office_pos)
        if enters_office:
            self.last_reason = "bounty:cashout"
            return offer(self._step_toward(
                snapshot,
                step,
                tail="c" + ("y" * len(bounties)) + LEAVE_STORE_KEY,
            ))
        return offer(self._step_toward(snapshot, step))

    def _observe_navigation_commitments(self, snapshot: Snapshot) -> None:
        """Charge a committed loot goal on every decision until it expires."""
        committed_loot = self._loot_target
        previous_position = self._recent[-2] if len(self._recent) >= 2 else None
        jumped = (
            previous_position is not None
            and previous_position.distance_to(snapshot.player.position) > 1
        )
        if (
            committed_loot is not None
            and jumped
            and committed_loot not in self._loot_ledger_rearmed
        ):
            self._loot_ledger_rearmed.add(committed_loot)
            self._nav_ledger.rearm(
                "loot", committed_loot,
                distance=snapshot.player.position.distance_to(committed_loot),
            )
        if committed_loot is not None and not jumped:
            self._nav_ledger.observe(
                "loot",
                committed_loot,
                snapshot.player.position.distance_to(committed_loot),
            )
            if self._nav_ledger.is_expired("loot", committed_loot):
                self._deferred_loot.add(committed_loot)
                self._nav_ledger_deferred_loot.add(committed_loot)
                if not (self._known_loot - self._deferred_loot):
                    self._loot_defer_blocker = "navigation-ledger:loot"
                elif self._loot_defer_blocker == "navigation-ledger:loot":
                    self._loot_defer_blocker = None
                if self._loot_target == committed_loot:
                    self._release_claim_goal(
                        "loot-navigation-expired", committed_loot, owners=CLAIM_LOOT_OWNERS
                    )
                    self._loot_target = None
        identity = self._explore_goal_identity
        if identity is not None:
            kind = f"explore:{identity.kind.value}"
            self._nav_ledger.observe(
                kind,
                identity.position,
                snapshot.player.position.distance_to(identity.position),
            )
            if self._nav_ledger.is_expired(kind, identity.position):
                self._retire_explore_goal(identity)

        guarded = self._guarded_paralyzers(snapshot, self._strategic_hostiles(snapshot))
        for monster in guarded:
            self._nav_ledger.observe(
                "paralyzer-guard",
                monster.position,
                snapshot.player.position.distance_to(monster.position),
            )
            if self._nav_ledger.is_expired("paralyzer-guard", monster.position):
                guarded_loot = {
                    loot for loot in self._known_loot
                    if loot.distance_to(monster.position) <= 1
                }
                self._deferred_loot.update(guarded_loot)
                self._safety_deferred_loot.update(guarded_loot)


    def _loot_before_recall_calm(self, snapshot: Snapshot) -> bool:
        """Nothing on this board threatens the player.

        User decision 2026-09-23 (topic loot-before-recall):
        「見えている分は全部拾う」, narrowed by the follow-up answer
        「待ち時間だけに統一（推奨）」 — reading the Word of Recall is never
        delayed; the countdown it starts (randint0(21) + 15 game turns, see
        recall_player in src/spell-kind/spells-world.cpp) is spent collecting
        the visible floor loot instead of standing still.  Danger returning
        sends the bot straight back to the wait/survival behaviour, so the
        whole condition is re-decided on every board rather than latched.

        Both of the decision's conditions are checked, plus the detected list:
        a monster known only through telepathy is a hostile the player can see
        on the map.  The prediction is the same quantity the decision log
        prints as ``threat_prediction.total``; on a board that passes the two
        emptiness checks it is zero by construction, and it is evaluated (not
        assumed) so the gate fails first if either list ever admits a monster.
        """
        if snapshot.in_town:
            return False
        # Below the low-HP walk threshold (user 2026-10-03) the board is not
        # calm, monsters or not:
        # live Forest 32F 2026-10-03 03:46:39, return:seek-loot at HP 108/731
        # right after an emergency teleport away from unseen casters.
        if snapshot.player.hp < self._low_hp_walk_threshold(snapshot.player.max_hp):
            return False
        hostiles = [
            monster for monster in snapshot.visible_monsters if monster.hostile
        ]
        detected = [
            monster for monster in snapshot.detected_monsters if monster.hostile
        ]
        if hostiles or detected:
            return False
        return self.threat_prediction(snapshot, [*hostiles, *detected])["total"] == 0

    def _rearm_navigation_ledger_loot(self) -> None:
        """Hand ledger-expired loot one fresh budget, once per floor visit.

        A calm recall countdown is a distinct opportunity to collect an item
        previously abandoned after a genuine pursuit stall. Relocation and
        recall share one fresh budget per position for the floor visit.
        """
        for position in sorted(
            self._nav_ledger_deferred_loot - self._loot_ledger_rearmed,
            key=lambda item: (item.y, item.x),
        ):
            self._loot_ledger_rearmed.add(position)
            self._nav_ledger_deferred_loot.discard(position)
            self._nav_ledger.rearm("loot", position)
            self._deferred_loot.discard(position)
        if (
            self._loot_defer_blocker == "navigation-ledger:loot"
            and not self._nav_ledger_deferred_loot
        ):
            self._loot_defer_blocker = None

    def _has_usable_ranged_option(self, snapshot: Snapshot) -> bool:
        return self._matching_ammo(snapshot) is not None or any(
            item.is_torch and item.fuel > 0
            and 1 <= snapshot.dungeon_level <= TORCH_THROW_MAX_DEPTH
            for item in snapshot.inventory
        )


    def _nearest_position_step(
        self, snapshot: Snapshot, targets: set[Position]
    ) -> Position | None:
        if not targets:
            return None
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        # Record-only (rev 9.3 R2): see ``_nearest_goal_step``.
        capture = self.__dict__.get("_claim_target_capture")
        while queue:
            position, first_step = queue.popleft()
            if position != start and position in targets:
                if capture is not None:
                    capture.append(position)
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, position):
                # Same lethal-danger weight as every other routing BFS: a
                # device-recovery route through an avoided cell would repeat
                # _step_toward's refusal forever on this static floor.
                if neighbor in seen or neighbor in self._engagement_avoid_cells:
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        return None

    def loot_state(self, snapshot: Snapshot) -> dict:
        """Decision telemetry for visible, remembered, and blocked floor loot."""
        hostiles = self._strategic_hostiles(snapshot)
        defer_blocker = getattr(self, "_loot_defer_blocker", None)
        visible = [
            {
                "position": {"y": grid.position.y, "x": grid.position.x},
                "count": grid.object_count,
                "unsafe": grid.unsafe,
                "distance": snapshot.player.position.distance_to(grid.position),
            }
            for grid in snapshot.grids.values()
            if grid.object_count > 0 and grid.passable
        ]
        return {
            "visible": visible,
            "known": [
                {"y": position.y, "x": position.x}
                for position in sorted(self._known_loot, key=lambda pos: (pos.y, pos.x))
            ],
            "target": (
                {"y": self._loot_target.y, "x": self._loot_target.x}
                if self._loot_target is not None
                else None
            ),
            "deferred": [
                {"y": position.y, "x": position.x}
                for position in sorted(
                    self._deferred_loot, key=lambda pos: (pos.y, pos.x)
                )
            ],
            "blocker": (
                self._loot_block_reason(snapshot, hostiles)
                or defer_blocker
            ),
        }


    def _find_recall_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(snapshot, lambda it: it.is_recall_scroll)



    def _track_idle_items(
        self, snapshot: Snapshot, previous_floor: tuple[int, int, int] | None
    ) -> None:
        # Per item signature, count consecutive dives it went unused — never consumed
        # (its carried count dropped: quaffed / read / eaten / wielded away). Used
        # items reset to 0; anything carried through >= UNUSED_DIVE_LIMIT whole dives
        # untouched is dead weight the Home-deposit routine can stash (see
        # _home_deposit_candidate). Runs every observe; the town<->dungeon edges drive
        # the accounting.
        cur_counts: dict[tuple[str, int, int], int] = {}
        for it in snapshot.inventory:
            sig = self._item_signature(it)
            cur_counts[sig] = cur_counts.get(sig, 0) + it.count
        prev_dungeon = previous_floor[0] if previous_floor else 0
        if not snapshot.in_town:
            if prev_dungeon == 0:  # a fresh dive begins
                self._dive_used_sigs = set()
            else:
                for sig, count in self._prev_inv_counts.items():
                    if cur_counts.get(sig, 0) < count:
                        self._dive_used_sigs.add(sig)  # consumed or wielded away = used
        elif prev_dungeon != 0:  # a dive just ended
            self._item_idle_dives = {
                sig: (
                    0
                    if sig in self._dive_used_sigs
                    else self._item_idle_dives.get(sig, 0) + 1
                )
                for sig in cur_counts  # drop signatures we no longer carry
            }
        self._prev_inv_counts = cur_counts

    def _resistance_depth_limit(self, snapshot: Snapshot) -> int:
        # The deepest floor the character can dive without a lethal resistance gap:
        # the deepest depth for which it (and every shallower band) has the mandatory
        # resistances. Free action and fire resistance open 20F; confusion
        # resistance is additionally required from 21F through 25F.
        limit = 0
        for depth in range(1, 128):
            if self._missing_required_abilities(snapshot, depth):
                break
            limit = depth
        return limit


    def _guardian_descent_blocked(self, snapshot: Snapshot) -> bool:
        return self._guardian_floor_blocked(
            snapshot, snapshot.floor_key[0], snapshot.dungeon_level
        )

    def _guardian_floor_blocked(
        self, snapshot: Snapshot, dungeon_id: int, depth: int
    ) -> bool:
        """Whether ``depth`` of ``dungeon_id`` is a guardian floor the kit cannot pass.

        The standing floor's form is ``_guardian_descent_blocked`` (the
        ``guardian-kit-insufficient`` return); ``_pick_alternate_dungeon`` asks
        the same question of a candidate's recall landing before switching to it.
        """
        info = self._dungeon_knowledge.get(dungeon_id)
        return bool(
            info is not None
            and info.guardian_id > 0
            and dungeon_id not in snapshot.conquered_dungeon_ids
            and depth >= info.max_depth - 1
            and not self._guardian_fight_viable(snapshot, info)
        )




    @staticmethod
    def _recall_selection_key(snapshot: Snapshot, dungeon_id: int) -> str | None:
        if snapshot.entered_dungeon_ids:
            try:
                index = snapshot.entered_dungeon_ids.index(dungeon_id)
            except ValueError:
                return "a" if snapshot.recall_dungeon_id == dungeon_id else None
            return chr(ord("a") + index)
        if snapshot.recall_dungeon_id == dungeon_id:
            return "a"
        return None






    def _next_depth_supply_shortage(self, snapshot: Snapshot) -> bool:
        if (
            snapshot.player.class_id < 0
            or snapshot.in_town
            or snapshot.dungeon_level < 1
        ):
            return False
        next_depth = snapshot.dungeon_level + 1
        ledger = self._supply_ledger(snapshot, next_depth)
        return any(
            status.kind != "recall"
            and status.count < status.required_return
            and (status.obtainable or next_depth > WALK_OUT_MAX_DEPTH)
            for status in ledger.values()
        )


    def _on_global_wilderness_map(self, snapshot: Snapshot) -> bool:
        """Classify the measured global-map command space."""
        global_map = self._wilderness_map
        return (
            global_map is not None
            and snapshot.width == global_map.width
            and snapshot.height == global_map.height
            and snapshot.town_id == -1
            and snapshot.town_index == 0
            and not snapshot.in_town
        )





    @claims(ClaimOwner.DETECTORS)
    def _bound_escape_wait(self, snapshot: Snapshot, key: str) -> str:
        """Let registered escape WAITs spend their policy budget, then stop.

        Counts are floor-scoped and are intentionally not reset by intervening
        ladder rungs: an escape ladder that alternates WAIT with rejected moves
        must still reach its visible terminal.
        """
        reason = self.last_reason
        limit = ESCAPE_BUDGETED_WAIT_LIMITS.get(reason)
        if key != WAIT_KEY or limit is None:
            return key
        if self._escape_wait_budget_floor != snapshot.floor_key:
            self._escape_wait_budget_floor = snapshot.floor_key
            self._escape_wait_decisions.clear()

        if reason == "combat:disengage-wait":
            used = self._fruitless_disengage_decisions
        else:
            self._escape_wait_decisions[reason] += 1
            used = self._escape_wait_decisions[reason]
        remaining = max(0, limit - used)
        self.escape_ladder_telemetry = {
            "ladder": reason.split(":", 1)[0],
            "rung": reason,
            "budget_remaining": remaining,
            "owner": self._escape_state.owner,
        }
        if reason == "combat:disengage-wait":
            # The next policy decision emits the ladder's established visible
            # terminal, combat:fruitless. Preserve that public reason.
            self.escape_ladder_telemetry["reason"] = reason
            return key
        if used >= limit:
            self.last_reason = "livelock:exhausted"
            self.escape_ladder_telemetry["reason"] = self.last_reason
        else:
            self.escape_ladder_telemetry["reason"] = reason
        return key

    def _update_navigation_progress(self, snapshot: Snapshot) -> None:
        """Advance the mode-independent no-progress invariant (R1).

        Called once per decision, after _decide. "Progress" is defined by
        observable outcomes, not by which mode produced the decision — reason
        exemption lists are exactly how the 41-cell descent triad evaded every
        earlier detector.
        """
        if snapshot.in_town or snapshot.store is not None:
            self._nav_stall_count = 0
            self._nav_exhausted = False
            self._nav_escape_steps = 0
            return
        coverage = len(self._remembered_marked_t)
        marker = (
            snapshot.player.gold,
            len(snapshot.inventory),
            len(snapshot.equipment),
        )
        progress = (
            coverage > self._nav_known_high
            or self._nav_ledger.improved_this_decision
            or marker != self._nav_progress_marker
            or snapshot.player.recalling
            # Stepped onto a first-visit tile this decision: any walk over
            # fresh ground (a long return backtrack aside) is real locomotion,
            # not a loop. Standing still never counts (position unchanged).
            or (
                self._position_changed
                and self._visit_counts[snapshot.player.position] <= 1
            )
            # Combat counts only when actually ENGAGED — adjacency or a
            # fighting decision. A monster merely visible across the floor
            # (unreachable, feared, asleep behind glass) must not reset the
            # counter, or a varied livelock with a spectator never trips.
            or (
                self._combat_fruitful
                and (
                    bool(self._physical_adjacent_hostiles(snapshot))
                    or self.last_reason.startswith(
                        ("melee", "ranged", "flee", "hunt", "emergency", "quest:")
                    )
                )
            )
        )
        self._nav_known_high = max(self._nav_known_high, coverage)
        self._nav_progress_marker = marker
        if progress:
            self._nav_stall_count = 0
            return
        self._nav_stall_count += 1
        if self._nav_stall_count >= NAV_NO_PROGRESS_LIMIT:
            self._nav_exhausted = True
            self._window_edge_fallback_pending = True


    def _productive_choke_hold(self, snapshot: Snapshot) -> bool:
        """A choke kill is progress and must not arm or dispatch walk-out."""
        if (
            not self.last_reason.startswith("melee:choke")
            or self._open_neighbor_count(snapshot, snapshot.player.position)
            > SUMMONER_CHOKE_NEIGHBORS - 1
            or not self._combat_outcomes
            or snapshot.floor_key != self._combat_outcome_floor
        ):
            return False
        previous = self._combat_outcomes[-1]
        # Visibility churn is not a kill: rear breeders routinely move behind
        # walls at a corridor mouth.  Use only engine-backed reward progress so
        # a kill-less shuffling swarm still reaches the bounded walk-out.
        return bool(
            snapshot.player.exp > previous[0]
            or snapshot.player.gold > previous[1]
        )


    @claims(ClaimOwner.ESCAPE)
    def _fruitless_disengage_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if self._fruitless_disengage_floor != snapshot.floor_key:
            return None
        if (
            not hostiles
            and any(
                monster.hostile and self._is_weak_breeder(snapshot, monster)
                for monster in snapshot.visible_monsters
            )
        ):
            self._fruitless_disengage_floor = None
            self._fruitless_disengage_decisions = 0
            if self._last_return_trigger is None:
                self._returning_to_town = False
                self._note_return_end()
            if self._escape_state.owner == "disengage":
                self._escape_state.release()
            return None

        breeders = [monster for monster in hostiles if monster.can_multiply]
        mining_preemption = (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and snapshot.dungeon_level == 1
        )
        mining_threat_survivable = mining_preemption and (
            not hostiles
            or self.threat_prediction(snapshot, hostiles, 3)[
                "operational_total"
            ]
            * 2
            < snapshot.player.hp
        )
        if (
            mining_preemption
            and mining_threat_survivable
            and (
                (
                    breeders
                    and self._breeder_engagement_score
                    < BREEDER_CONTAINMENT_WINDOW + FRUITLESS_DISENGAGE_LIMIT
                )
                or (
                    not breeders
                    and self._breeder_engagement_score
                    < BREEDER_CONTAINMENT_WINDOW
                )
            )
        ):
            # Mining owns a bounded first attempt at clearing weak multipliers.
            # The engagement score keeps advancing while breeders remain visible,
            # so a swarm whose count never trends down still falls back to the
            # unchanged disengage episode and its visible terminal. Once genuine
            # absence decays the score below the declaration threshold, the stale
            # latch no longer blocks mining.
            self._returning_to_town = False
            self._note_return_end()
            self._escape_state.release()
            return None
        if not breeders and self._fruitless_fight_is_winnable(snapshot, hostiles):
            return None
        threats = breeders or hostiles
        nearby_threat = bool(threats) and min(
            monster.distance for monster in threats
        ) <= 4
        quest_locked = self._floor_navigation_exit_locked(snapshot)

        # A quest floor cannot be abandoned, but once local retreat has broken
        # contact the disengage latch must not own every turn with WAIT.  Let
        # the ordinary quest objective continue until the swarm closes again;
        # only actual local-retreat attempts consume the bounded budget.
        if quest_locked and not nearby_threat:
            return None

        marked_now = len(self._remembered_marked_t)
        productive_walk_out = (
            self.last_reason == "combat:disengage-explore"
            and marked_now > self._fruitless_disengage_marked_high
        )
        self._fruitless_disengage_marked_high = max(
            self._fruitless_disengage_marked_high, marked_now
        )
        if (
            self._fruitless_disengage_decisions >= FRUITLESS_DISENGAGE_LIMIT
            and not productive_walk_out
        ):
            self.last_reason = "combat:fruitless"
            self._escape_state.release()
            return WAIT_KEY
        if not productive_walk_out and nearby_threat:
            # Productive walk-out steps do not spend the fruitless allowance.
            # Neither do decisions after contact has genuinely broken.
            # Termination is preserved because marked growth is bounded by the
            # finite floor; later zero-growth decisions under threat consume.
            self._fruitless_disengage_decisions += 1
            self._fruitless_disengage_spent_this_decision = True
        self._escape_state.budgets["fruitless-disengage"] = (
            self._fruitless_disengage_decisions
        )
        self._escape_state.enter("disengage", "combat:disengage")
        self._note_return_start(None)
        self._returning_to_town = True

        # On an ordinary floor, the latched return is the single owner of the
        # escape transaction.  Previously local retreat ran first whenever a
        # monster stayed within four cells, so it could starve recall issuance,
        # ignore an active recall countdown, and oscillate forever with a
        # pursuing monster.  Quest floors cannot use this exit path and retain
        # their bounded local-retreat behavior below.
        if snapshot.floor_key[2] == 0 and not quest_locked:
            # Once recall is active, local relocation can no longer starve the
            # recall transaction.  Do not stand still while breeders multiply
            # around the player merely because their attacks happen to deal no
            # damage: break contact first and let the existing countdown keep
            # running at the landing position.
            if snapshot.player.recalling and breeders and nearby_threat:
                if not snapshot.player.blind and not snapshot.player.confused:
                    scroll = self._escape_scroll(snapshot)
                    if scroll is not None:
                        reason = (
                            "emergency:teleport"
                            if scroll.is_teleport_scroll
                            else "emergency:phase"
                        )
                        return self._issue_emergency_consumable(
                            snapshot, scroll, reason
                        )
                # Recall is already counting down. Against a survivable swarm,
                # standing still costs nothing and holding avoids retreating into
                # a corner and ping-ponging there until recall lands. Only leave
                # the tile if staying is actually lethal, and then via a
                # non-oscillating move.
                threat = self.threat_prediction(
                    snapshot, hostiles, 3
                )["operational_total"]
                if threat * 2 < snapshot.player.hp:
                    self.last_reason = "combat:disengage-hold"
                    return WAIT_KEY
                move = self._disengage_move_or_escalate(
                    snapshot, breeders, hostiles
                )
                if move is not None:
                    return move
            key = self._return_to_town_key(snapshot, hostiles)
            if key is not None:
                if self.last_reason.startswith("return:"):
                    self.last_reason = (
                        "combat:disengage-" + self.last_reason[7:]
                    )
                self._escape_state.enter("disengage", self.last_reason)
                return key

        if nearby_threat:
            move = self._disengage_move_or_escalate(snapshot, threats, hostiles)
            if move is not None:
                return move

        # Quest floors must never be abandoned by the fruitless-combat escape
        # path.  Keep attempting local retreat until the visible stop lets an
        # operator resolve the encounter without silently failing the quest.
        if snapshot.floor_key[2] == 0:
            key = self._return_to_town_key(snapshot, hostiles)
            if key is not None:
                if self.last_reason.startswith("return:"):
                    self.last_reason = "combat:disengage-" + self.last_reason[7:]
                self._escape_state.enter("disengage", self.last_reason)
                return key
        self.last_reason = "combat:disengage-wait"
        return WAIT_KEY


    def _unprofitable_unique_disengage_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Leave a non-objective floor instead of grinding an inert unique."""
        if snapshot.in_town or snapshot.floor_key[2] != 0:
            return None
        if self._floor_navigation_exit_locked(snapshot):
            # A taken dungeon kill quest cannot leave or recall from its target
            # floor. Arming the floor-level disengage here transfers every turn
            # to local retreat; pursuing quest monsters then turn that retreat
            # into a damaging oscillation. Fight through the nearby pack (and
            # the harmless unique if it remains adjacent) instead.
            return None

        dungeon_id, level, _ = snapshot.floor_key
        dungeon = self._dungeon_knowledge.get(dungeon_id)
        objective_guardian_id = (
            dungeon.guardian_id
            if (
                dungeon is not None
                and dungeon_id == self._target_dungeon_id
                and level == dungeon.max_depth
            )
            else 0
        )
        candidates: list[MonsterState] = []
        for monster in hostiles:
            knowledge = self._monrace_knowledge.get(monster.race_id)
            if (
                knowledge is None
                or "UNIQUE" not in knowledge.flags
                or monster.race_id == objective_guardian_id
                or monster.can_summon
                or monster.can_multiply
                or knowledge.can_summon
                or knowledge.can_multiply
                or max(monster.max_melee_damage, knowledge.max_melee_damage) > 0
                or max(monster.max_ranged_damage, knowledge.max_ranged_damage) > 0
            ):
                continue
            if self._unique_fight_projection(
                snapshot,
                hostiles,
                monster,
                player_speed=snapshot.player.speed,
            ) is None:
                candidates.append(monster)

        if not candidates:
            return None

        self._fruitless_disengage_floor = snapshot.floor_key
        self._fruitless_disengage_decisions = self._escape_state.budgets[
            "fruitless-disengage"
        ]
        self._note_return_start(None)
        self._returning_to_town = True
        key = self._fruitless_disengage_key(snapshot, hostiles)
        if self.last_reason.startswith("combat:disengage-"):
            self.last_reason = self.last_reason.replace(
                "combat:disengage-",
                "combat:avoid-unprofitable-unique-",
                1,
            )
        return key

    def has_edible(self, snapshot: Snapshot) -> bool:
        """Return whether the current character can eat something in the pack."""
        return self._find_edible(snapshot) is not None

    def _escape_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        # Reading needs sight; a full teleport is preferred over a short phase.
        if snapshot.player.blind or not self._can_read_scrolls(snapshot):
            return None
        return self._find_teleport_scroll(snapshot) or self._find_phase_scroll(snapshot)


    def _consumable_fight_target(
        self, snapshot: Snapshot, monster: MonsterState
    ) -> bool:
        knowledge = self._monrace_knowledge.get(monster.race_id)
        if knowledge is not None and "UNIQUE" in knowledge.flags:
            return True
        quest_id = self._active_kill_quest_id(snapshot)
        if quest_id is None:
            return False
        quest = snapshot.quests.get(quest_id)
        race_id = self._quest_target_race_id(quest) if quest is not None else None
        return race_id is not None and race_id > 0 and monster.race_id == race_id


    def _committed_unique_fight_viable(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> bool:
        race_id = self._unique_combat_committed_race_id
        if race_id is None:
            return False
        targets = [
            monster
            for monster in hostiles
            if monster.race_id == race_id and monster.distance <= 1
        ]
        if (
            len(targets) != 1
            or snapshot.player.afraid
            or snapshot.player.blind
            or snapshot.player.confused
            or snapshot.player.paralyzed
            or any(monster.can_multiply for monster in hostiles)
            or any(
                monster.can_summon and monster.index != targets[0].index
                for monster in hostiles
            )
        ):
            return False
        return (
            self._unique_fight_projection(
                snapshot,
                hostiles,
                targets[0],
                player_speed=snapshot.player.speed,
            )
            is not None
        )





    @claims(ClaimOwner.QUEST_SWEEP)
    def _q22_opening_consumable_before_escape(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile | None,
    ) -> str | None:
        """Preserve Q22's reviewed speed -> one teleport opening order.

        Emergency handling runs before the approved quest executor.  Without
        this narrow bridge, a dangerous first frame can spend an ordinary
        teleport before the executor gets a chance to quaff Speed.
        """
        if profile is None or profile.quest_id != 22:
            return None
        reposition = profile.engagement_plan.get("opening_reposition")
        if not isinstance(reposition, dict):
            return None
        phase = self._quest_strategy_opening_phase.get(profile.quest_id, 0)
        if phase == 0 and bool(reposition.get("speed_first", False)):
            speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
            if speed is not None:
                self._quest_strategy_opening_phase[profile.quest_id] = 1
                self.last_reason = "quest-strategy:q22-opening-speed"
                return QUAFF_KEY + speed.slot
        if phase == 1 and bool(reposition.get("teleport_once", False)):
            teleport = self._find_teleport_scroll(snapshot)
            if teleport is not None:
                self._quest_strategy_opening_phase[profile.quest_id] = 2
                self.last_reason = "quest-strategy:q22-opening-teleport"
                return self._read_key(snapshot, teleport)
        return None

    def _q22_reposition_active(
        self, profile: StrategyProfile | None
    ) -> bool:
        return (
            profile is not None
            and profile.quest_id == 22
            and self._quest_strategy_opening_phase.get(profile.quest_id, 0) == 2
        )

    def _q22_reposition_recovery_before_escape(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile | None,
        hostiles: list[MonsterState],
    ) -> InventoryItem | None:
        """Apply Q22's sole HP-healing rule while routing to a goal cell.

        Movement owns this phase.  Healing may interrupt it only below the
        profile threshold with an adjacent enemy, and only when the potion's
        effective healing covers the next turn's expected damage.  In
        particular, three-turn operational lethality is not a healing trigger.
        """
        if not self._q22_reposition_active(profile):
            return None
        if not any(monster.distance <= 1 for monster in hostiles):
            return None
        heal_ratio = float(
            profile.consumable_plan.get(
                "heal_threshold_ratio", FIXED_QUEST_HEAL_HP_RATIO
            )
        )
        if snapshot.player.hp_ratio >= heal_ratio:
            return None
        expected_damage = self._predicted_damage(
            snapshot, hostiles, turns=1, expected=True
        )
        return self._find_heal_potion(snapshot, expected_damage=expected_damage)

    def _issue_emergency_consumable(
        self, snapshot: Snapshot, item: InventoryItem, reason: str
    ) -> str:
        self._emergency_return_active = True
        signature = self._item_signature(item)
        pre_use_count = sum(
            candidate.count
            for candidate in snapshot.inventory
            if self._item_signature(candidate) == signature
        )
        item_kind = (
            "recall"
            if item.is_recall_scroll
            else "teleport"
            if item.is_teleport_scroll
            else "phase"
        )
        self._emergency_consumable_issue_watch = (
            snapshot.floor_key,
            snapshot.turn,
            snapshot.player.position,
            signature,
            pre_use_count,
            item_kind,
        )
        self.last_reason = reason
        self._post_owner_expectation(
            snapshot, reason, "inventory", "position", "recalling", "floor"
        )
        return self._read_key(snapshot, item)


    def _unresisted_melee_status_threats(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        *,
        turns: int = 3,
        latched: frozenset[tuple[int, int]] = frozenset(),
    ) -> list[MonsterState]:
        """Find awake melee attackers that can soon confuse or paralyze us.

        ``latched`` holds the (index, race_id) of monsters that already
        triggered the status-threat escape on this floor; a latched mover
        stays a threat at any reachable path distance.

        HP-only prediction undervalues these blows: confusion disables aimed
        movement and scroll reading, while paralysis removes whole turns.  Treat
        either effect as a retreat trigger unless the corresponding intrinsic is
        present.  Reachability mirrors the melee portion of threat_prediction.
        """
        missing_confusion_resistance = "resist_conf" not in snapshot.player.abilities
        missing_free_action = not self._has_state_based_free_action(snapshot)
        if not missing_confusion_resistance and not missing_free_action:
            return []

        threats: list[MonsterState] = []
        for monster in hostiles:
            if monster.asleep:
                continue
            knowledge = self._monrace_knowledge.get(monster.race_id)
            if knowledge is None:
                continue
            effects = {blow.effect for blow in knowledge.blows}
            if not (
                (missing_confusion_resistance and "CONFUSE" in effects)
                or (missing_free_action and "PARALYZE" in effects)
            ):
                continue
            path_distance = self._monster_path_distance(snapshot, monster.position)
            if path_distance is None:
                continue
            actions = self._monster_actions(
                monster.speed, snapshot.player.speed, turns
            )
            never_moves = "NEVER_MOVE" in knowledge.flags
            attacks = (
                actions
                if path_distance <= 1
                else 0
                if never_moves
                else max(0, actions - (path_distance - 1))
            )
            if attacks > 0 or (
                not never_moves and (monster.index, monster.race_id) in latched
            ):
                threats.append(monster)
        return threats







    def _post_emergency_return_trigger(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        if player.hp_ratio <= EMERGENCY_RETURN_HP_RATIO:
            return "emergency-low-hp"
        if player.blind or player.confused or player.cut:
            return "emergency-status"
        if self._dive_emergencies >= EMERGENCY_RETURN_COUNT:
            return "emergency-repeat"
        if any(monster.can_summon or monster.can_multiply for monster in hostiles):
            return "emergency-material-threat"
        return None

    def _viable_target_guardian_visible(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> bool:
        info = self._dungeon_knowledge.get(snapshot.floor_key[0])
        if (
            info is None
            or snapshot.floor_key[0] != self._target_dungeon_id
            or snapshot.dungeon_level != info.max_depth
            or info.guardian_id <= 0
        ):
            return False
        guardians = [m for m in hostiles if m.race_id == info.guardian_id]
        return len(guardians) == 1 and self._guardian_fight_viable(snapshot, info)


    def _aggregate_ranged_percentile(
        self,
        knowledge: MonraceKnowledge,
        *,
        actions: int,
        selection_context: SpellSelectionContext,
        selection_probabilities: dict[str, float],
        flags: frozenset,
        player_hp: int,
        blind: bool,
        saving_skill: int,
    ):
        """Value-keyed, cross-decision cache around aggregate_ranged_damage_percentile.

        The convolution costs ~0.3-1s per deep-floor caster and its inputs are
        coarse: the frozen race knowledge, the action count, the selection
        context (which fully determines selection_probabilities — key the
        CONTEXT, not the derived dict, so enriching the context later cannot
        silently under-key), the player's resist/reflect flags, blindness, and
        saving skill. player_hp feeds ONLY HAND_DOOM, so it joins the key just
        for races that have it. A standoff or kiting fight therefore pays for
        one computation and reuses it for the rest of the engagement.
        """
        key = (
            knowledge,
            actions,
            selection_context,
            flags,
            blind,
            saving_skill,
            player_hp if "HAND_DOOM" in knowledge.abilities else None,
        )
        cached = self._aggregate_ranged_cache.get(key)
        if cached is None:
            cached = aggregate_ranged_damage_percentile(
                knowledge,
                actions=actions,
                selection_probabilities=selection_probabilities,
                flags=flags,
                player_hp=player_hp,
                blind=blind,
                saving_skill=saving_skill,
            )
            if len(self._aggregate_ranged_cache) >= AGGREGATE_RANGED_CACHE_LIMIT:
                self._aggregate_ranged_cache.clear()
            self._aggregate_ranged_cache[key] = cached
        return cached


    @staticmethod
    def _maximum_melee_blow_damage(
        snapshot: Snapshot, effect: str, damage: int
    ) -> int:
        if effect in NON_HP_DAMAGE_BLOW_EFFECTS:
            return 0
        abilities = snapshot.player.abilities
        if effect in {"HURT", "SHATTER", "SUPERHURT"}:
            damage -= damage * min(snapshot.player.ac, 150) // 250
            if effect == "SUPERHURT":
                damage *= 2
        resistance = {
            "ACID": "resist_acid",
            "ELEC": "resist_elec",
            "FIRE": "resist_fire",
            "COLD": "resist_cold",
        }.get(effect)
        if resistance in abilities:
            damage = damage * 34 // 100
        elif effect == "POISON" and "resist_pois" in abilities:
            damage = damage * 40 // 100
        elif effect == "DISEASE" and "resist_pois" in abilities:
            damage = damage * 8 // 9
        return max(0, damage)



    @classmethod
    def _monster_actions(cls, monster_speed: int, player_speed: int, turns: int) -> int:
        monster_energy = cls._speed_energy(monster_speed)
        player_energy = cls._speed_energy(player_speed)
        ratio_actions = (turns * monster_energy + player_energy - 1) // player_energy
        # Runtime energy phase is intentionally not emitted. In the worst phase
        # the monster can squeeze in one action beyond the steady-state ratio.
        # Within one player-turn interval, however, it can take at most the
        # floor of the energy ratio plus one boundary-phase action. Summing
        # that physical cap over the prediction window prevents the phase
        # margin from inventing a third action for a 1.5x-speed monster.
        per_turn_cap = monster_energy // player_energy + 1
        return max(1, min(ratio_actions + 1, turns * per_turn_cap))

    def _summoner_cover_in_one_step(self, snapshot: Snapshot) -> bool:
        for neighbor in self._walkable_neighbors(snapshot, snapshot.player.position):
            # A clipped visibility/snapshot edge can look artificially narrow.
            # Count it as cover only when an observed wall or closed door creates
            # the narrowing.
            if any(
                (grid := snapshot.grid_at(Position(neighbor.y + dy, neighbor.x + dx)))
                is not None
                and (grid.wall or grid.is_closed_door)
                for dy, dx in NEIGHBOR_OFFSETS
            ):
                return True
        return False


    def choke_engagement_state(self) -> dict[str, object]:
        plan = self._choke_engagement_plan
        if plan is None:
            return {}
        return {
            "phase": plan.phase,
            "floor": list(plan.floor),
            "destination": {"y": plan.destination.y, "x": plan.destination.x},
            "covered_retreat_direction": list(plan.covered_retreat_direction),
            "trigger_hostiles": [
                {
                    "index": index,
                    "last_seen": {"y": position.y, "x": position.x},
                }
                for index, position in sorted(plan.trigger_last_seen.items())
            ],
            "sight_loss_decisions": plan.sight_loss_decisions,
            "no_progress_decisions": plan.no_progress_decisions,
            "closest_destination_distance": plan.closest_destination_distance,
            "decisions_consumed": plan.decisions_consumed,
            "start_breeder_count": plan.start_breeder_count,
            "release_cause": plan.release_cause,
        }


    def _release_choke_plan(self, cause: str) -> None:
        plan = self._choke_engagement_plan
        if plan is None:
            return
        if plan.start_breeder_count > 0:
            self._breeder_choke_attempt_ended_floor = plan.floor
        # S2b.1b, record-only: the plan's reposition walk (``melee:choke-
        # reposition``, a Reach on ``plan.destination``) ends with the plan.
        self._release_claim_goal(
            f"choke-plan-released:{cause}",
            plan.destination,
            owners=(ClaimOwner.POSITIONING,),
        )
        plan.phase = "breakthrough" if cause == "breeder-breakthrough" else "release"
        plan.release_cause = cause



    def _inherit_choke_outcome_budget(
        self, snapshot: Snapshot, plan: ChokeEngagementPlan
    ) -> None:
        if self._choke_outcome_floor != snapshot.floor_key:
            self._choke_outcome_floor = snapshot.floor_key
            self._choke_outcome_budgets.clear()
        key = self._choke_outcome_key(plan)
        marker = self._choke_outcome_marker(
            snapshot, len(plan.trigger_last_seen), plan.start_breeder_count
        )
        spent, high = self._choke_outcome_budgets.get(key, (0, marker))
        plan.no_progress_decisions = spent
        self._choke_outcome_budgets[key] = (spent, high)

    def _spend_choke_outcome_budget(
        self,
        snapshot: Snapshot,
        plan: ChokeEngagementPlan,
        trigger_count: int,
        breeder_count: int,
    ) -> None:
        """Charge one decision unless an observable beneficial outcome improved."""
        key = self._choke_outcome_key(plan)
        marker = self._choke_outcome_marker(snapshot, trigger_count, breeder_count)
        spent, high = self._choke_outcome_budgets.get(key, (0, marker))
        improved = any(current > previous for current, previous in zip(marker, high))
        if improved:
            spent = 0
            high = tuple(max(current, previous) for current, previous in zip(marker, high))
        else:
            spent += 1
        plan.no_progress_decisions = spent
        self._choke_outcome_budgets[key] = (spent, high)

    @claims(ClaimOwner.EXPLORE)
    def _immobile_breeder_giveup_key(self, snapshot: Snapshot) -> str | None:
        plan = self._choke_engagement_plan
        if (
            plan is None
            or plan.floor != snapshot.floor_key
            or plan.release_cause not in {
                "immobile-breeder-growth",
                "breeder-outcome-bound",
            }
        ):
            return None
        breeders = self._engagement_breeder_population(snapshot)
        self._claim_engagement_avoid_cells(
            [*plan.trigger_last_seen.values(), *(monster.position for monster in breeders)]
        )
        if any(step in self._engagement_avoid_cells for step in self._explore_path):
            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
        step = self._explore_step(snapshot)
        if step is not None:
            self.last_reason = (
                "explore:breeder-giveup"
                if plan.release_cause == "breeder-outcome-bound"
                else "explore:immobile-breeder-giveup"
            )
            return self._step_toward(snapshot, step)
        return None

    def _validated_choke_route(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> tuple[Position, Position] | None:
        """Return a first step and an observed terrain-only openness-2 goal."""
        origin = snapshot.player.position
        origin_distance = min(
            origin.distance_to(monster.position) for monster in hostiles
        )
        queue: deque[Position] = deque([origin])
        previous: dict[Position, Position | None] = {origin: None}
        candidates: list[tuple[int, int, Position]] = []
        while queue:
            position = queue.popleft()
            if position != origin:
                grid = snapshot.grid_at(position)
                distance = position.distance_to(origin)
                if (
                    grid is not None
                    and grid.currently_observed
                    and self._open_neighbor_count(snapshot, position)
                    <= SUMMONER_CHOKE_NEIGHBORS - 1
                    and min(
                        position.distance_to(monster.position)
                        for monster in hostiles
                    )
                    >= origin_distance
                ):
                    candidates.append(
                        (
                            distance,
                            self._open_neighbor_count(snapshot, position),
                            position,
                        )
                    )
            for neighbor in self._walkable_neighbors(snapshot, position):
                if neighbor not in previous:
                    previous[neighbor] = position
                    queue.append(neighbor)
        if not candidates:
            return None
        destination = min(candidates, key=lambda candidate: candidate[:2])[2]
        step = destination
        while previous[step] != origin:
            parent = previous[step]
            if parent is None:
                return None
            step = parent
        return destination, step


    def _quest_plan_owns_detected(
        self, snapshot: Snapshot, monsters: list[MonsterState]
    ) -> bool:
        """Whether the approved Q2 phase strategy's plan names every monster."""
        profile = self.approved_quest_strategy(snapshot.floor_key[2])
        return (
            profile is not None
            and profile.quest_id == 2
            and bool(monsters)
            and all(
                monster.race_id in profile.priority_targets
                for monster in monsters
            )
        )

    @claims(ClaimOwner.POSITIONING)
    def _detected_threat_preparation_key(
        self, snapshot: Snapshot, visible_hostiles: list[MonsterState]
    ) -> str | None:
        """Anticipate detected threats without treating them as attack targets."""
        hold = getattr(self, "_detected_threat_hold", None)
        if hold is not None and hold[0] != snapshot.floor_key:
            self._detected_threat_hold = None
            hold = None
        route = getattr(self, "_detected_threat_route", None)
        if route is not None and route[0] != snapshot.floor_key:
            self._release_claim_goal("choke-floor-changed", route[1], owners=("positioning",))
            self._detected_threat_route = route = None
        if visible_hostiles:
            self._detected_threat_hold = None
            if route is not None:
                self._release_claim_goal("choke-hostile-visible", route[1], owners=("positioning",))
            self._detected_threat_route = None
            return None
        if (
            hold is not None
            and snapshot.turn - hold[1]
            > DETECTED_THREAT_HOLD_MAX_GAME_TURNS
        ):
            # Expiry releases this anticipatory owner for the rest of the
            # floor.  Keep the expired episode as the latch until a visible
            # hostile or a floor change supplies the only re-arm stimulus.
            if route is not None:
                self._release_claim_goal("choke-hold-expired", route[1], owners=("positioning",))
            self._detected_threat_route = None
            return None
        detected = [
            monster
            for monster in self._perceived_hostiles(snapshot)
            if monster.perception == "detected"
        ]
        if not detected:
            self._detected_threat_hold = None
            if route is not None:
                self._release_claim_goal("choke-threat-undetected", route[1], owners=("positioning",))
            self._detected_threat_route = None
            return None

        # Keep the lower-certainty channel in the normal damage model, but do
        # not pass it to melee, ranged, line-of-fire, or blocker-clearing code.
        self.threat_prediction(snapshot, detected, turns=3)
        converging = [
            monster
            for monster in detected
            if not monster.asleep and monster.distance <= SWARM_LOOKAHEAD
        ]
        breeders = [
            monster for monster in converging if monster.can_multiply
        ]
        melee_threats = [
            monster
            for monster in converging
            if monster.max_ranged_damage <= 0
        ]
        # The pack this owner is already retreating from, still perceived.  Its
        # own step widens the gap, so re-deciding the convergence gate from the
        # cell it just reached hands the decision straight back to looting or
        # exploration, which walks the step back and re-opens the gate: two
        # owners one cell apart until the loop detector stops the bot (live
        # 2026-09-23 06:00:17-18, seek-loot '4' <-> detected:prepare-choke '6').
        # A started retreat therefore keeps the decision until the player
        # reaches the cell it chose (progress) or the stimulus retires below.
        committed = (
            [monster for monster in detected if monster.index in route[2]]
            if route is not None
            else []
        )
        if self._quest_plan_owns_detected(
            snapshot, [*breeders, *melee_threats, *committed]
        ):
            # Inside the Sewer (Q2) the approved phase strategy owns every
            # monster its plan names, breeders included (formation P1-P9).
            # Retreating from them here only hands the turn back to that
            # strategy one cell later, which walks back into the window: two
            # owners alternating until the loop detector stopped the bot
            # (live 2026-10-02 14:15:27-14:16:21, detected gremlins 153).
            self._detected_threat_hold = None
            if route is not None:
                self._release_claim_goal("choke-quest-plan-owns", route[1], owners=("positioning",))
            self._detected_threat_route = None
            return None
        if not breeders and len(melee_threats) < 2 and not committed:
            self._detected_threat_hold = None
            if route is not None:
                self._release_claim_goal("choke-threat-dispersed", route[1], owners=("positioning",))
            self._detected_threat_route = None
            return None
        if (
            self._open_neighbor_count(snapshot, snapshot.player.position)
            <= SUMMONER_CHOKE_NEIGHBORS - 1
        ):
            # The visible-monster channel keeps ownership after reaching its
            # choke and waits there instead of letting ordinary navigation
            # immediately pull the player back into the open.  Detected melee
            # packs need the same hand-off boundary: the convergence gates
            # above release this hold when the pack disappears, becomes
            # visible, sleeps, moves out of range, or drops below its count.
            # Standing at a choke is the retreat's own goal: the episode is
            # handed to the bounded hold, which owns it from here.
            if route is not None:
                self._complete_claim_goal("choke-reached", route[1], owners=("positioning",))
            self._detected_threat_route = None
            hold = self._detected_threat_hold
            if hold is None or hold[0] != snapshot.floor_key:
                hold = (snapshot.floor_key, snapshot.turn)
                self._detected_threat_hold = hold
            if snapshot.turn - hold[1] <= DETECTED_THREAT_HOLD_MAX_GAME_TURNS:
                self.last_reason = "summoner:hold-choke"
                return WAIT_KEY
            return None
        self._detected_threat_hold = None
        if route is not None and committed:
            if snapshot.player.position != route[1]:
                step = self._position_target_step(snapshot, route[1])
                if step is not None:
                    self.last_reason = "detected:prepare-choke"
                    self._declare_reach(route[1])
                    # the committed pack this retreat is from, still perceived
                    self._declare_triggers(committed)
                    return self._step_toward(snapshot, step)
            # Arrived at the chosen cell without it being a choke any more, or
            # it is no longer reachable: the commitment is spent either way.
            # Re-derive one below from what is perceived now.
            if snapshot.player.position == route[1]:
                self._complete_claim_goal("choke-cell-reached", route[1], owners=("positioning",))
            else:
                self._release_claim_goal("choke-cell-unreachable", route[1], owners=("positioning",))
            self._detected_threat_route = route = None
            committed = []
        threats = breeders or melee_threats
        if not threats:
            self._detected_threat_route = None
            return None
        destination, step = self._summoner_retreat_route(
            snapshot, threats, detected
        )
        if step is None:
            self._detected_threat_route = None
            return None
        # A committed destination is a shortest-path goal, so each decision of
        # the episode stands strictly closer to it: the retreat leg ends by
        # arriving, and the hold above then bounds the wait.  The flee fallback
        # names no cell and commits to nothing.
        self._detected_threat_route = (
            None
            if destination is None or destination == snapshot.player.position
            else (
                snapshot.floor_key,
                destination,
                frozenset(monster.index for monster in threats),
            )
        )
        self.last_reason = "detected:prepare-choke"
        if self._detected_threat_route is not None:
            self._declare_reach(self._detected_threat_route[1])
        # Design 5.4.1: the look-ahead set -- the detected hostiles within
        # SWARM_LOOKAHEAD with no ranged damage (or the converging breeders),
        # the same selection the route above retreats from.
        self._declare_triggers(threats)
        return self._step_toward(snapshot, step)








    def _monster_can_approach(
        self, snapshot: Snapshot, monster: MonsterState
    ) -> bool:
        """Whether a visible melee monster can close from its present terrain."""
        if monster.distance <= 1:
            return True
        knowledge = self._monrace_knowledge.get(monster.race_id)
        if knowledge is None:
            return True
        if "NEVER_MOVE" in knowledge.flags:
            return False
        if "AQUATIC" not in knowledge.flags:
            return True
        monster_grid = snapshot.grid_at(monster.position)
        if monster_grid is None or monster_grid.terrain_id < 0:
            return True
        water_terrain = monster_grid.terrain_id
        return any(
            (grid := snapshot.grid_at(position)) is not None
            and grid.terrain_id == water_terrain
            for position in (
                snapshot.player.position,
                *(
                    Position(
                        snapshot.player.position.y + dy,
                        snapshot.player.position.x + dx,
                    )
                    for dy, dx in NEIGHBOR_OFFSETS
                ),
            )
        )

    def _monster_path_distance(
        self, snapshot: Snapshot, origin: Position
    ) -> int | None:
        target = snapshot.player.position
        queue = deque([(origin, 0)])
        seen = {origin}
        while queue:
            position, distance = queue.popleft()
            if position == target:
                return distance
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if neighbor in seen:
                    continue
                grid = snapshot.grid_at(neighbor)
                if neighbor != target and (grid is None or not grid.enterable):
                    continue
                if grid is not None and grid.is_door and dy != 0 and dx != 0:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, distance + 1))
        return None


    def _escape_by_stairs(self, snapshot: Snapshot) -> str | None:
        # Only ever escape UPWARD. Diving to flee just leads somewhere more
        # dangerous. This is called only after a threat triggered fleeing, so
        # use a landing staircase immediately instead of waiting until near death.
        if self._quest_floor_exit_locked(snapshot):
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and self._is_upstairs_target(here):
            self._defer_descent(snapshot)
            return UP_STAIRS_KEY
        return None

    def _defer_descent(self, snapshot: Snapshot) -> None:
        self._descent_blocked = True
        self._descent_block_countdown = DESCENT_BLOCK_DECISIONS


    def _is_descent_target(self, snapshot: Snapshot, grid: GridState) -> bool:
        if not grid.is_descent:
            return False
        if not self._kill_quest_descent_allowed(snapshot):
            return False
        # Yeek Cave shares the Outpost wilderness tile. A remembered entrance
        # at the same local coordinates in another town/wilderness region is
        # not a valid walking route to it.
        if (
            grid.has_entrance
            and self._active_dungeon_target() == DUNGEON_YEEK_CAVE
            and snapshot.town_id not in {-1, 0}
        ):
            return False
        # Town entrances are also emitted as downstairs.  Reject an entrance
        # for another dungeon before quest-depth steering: that steering may
        # decide whether to go deeper on the current quest route, but it must
        # never turn an unrelated town entrance into that route.
        if (
            snapshot.in_town
            and grid.has_entrance
            and not self._is_active_dungeon_entrance(grid)
        ):
            return False
        if self._active_fixed_quest_id(snapshot) is not None or self._quest_floor_exit_locked(snapshot):
            return False
        # Preserve the pre-existing UNTAKEN quest-depth steering.  The TAKEN
        # overshoot invariant is owned solely by _kill_quest_descent_allowed.
        untaken_kill_target = next(
            (
                info
                for quest in snapshot.quests.values()
                if quest.id in FIXED_QUEST_ALLOWLIST
                and quest.status == QUEST_STATUS_UNTAKEN
                and (info := self._quest_knowledge.get(quest.id)) is not None
                and info.type in {QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER}
                and info.dungeon == snapshot.floor_key[0]
            ),
            None,
        )
        if (
            untaken_kill_target is not None
            and snapshot.dungeon_level <= untaken_kill_target.level
        ):
            return snapshot.dungeon_level < untaken_kill_target.level
        if snapshot.player.class_id < 0:
            return True
        if snapshot.in_town and grid.has_entrance:
            if not self._is_active_dungeon_entrance(grid):
                return False
            # A deep, non-fundraising run returns by Word of Recall (see
            # _town_special_key) instead of walking to the entrance, so the town
            # entrance stops being a descent goal past RECALL_MIN_DEPTH. Fundraising
            # keeps walking in — it mines level 1, where recall would overshoot.
            if self._fundraising_mode in {"mine", "scavenge"}:
                return True
            if self._taken_kill_quest_requires_walk_in(snapshot):
                return True
            return self._deepest_level < RECALL_MIN_DEPTH
        if self._fundraising_mode in {"mine", "scavenge"}:
            return False
        if self._guardian_descent_blocked(snapshot):
            return False
        # Depth-requirement gate (AGENTS.md): never descend into a floor whose
        # mandatory resistances the character lacks — confusion / poison / chaos /
        # nether etc. at depth are lethal without the resistance. Applies to the
        # in-dungeon stairs (the next floor is one deeper).
        if self._missing_required_abilities(snapshot, snapshot.dungeon_level + 1):
            return False
        return True

    def _taken_dungeon_kill_level_quest(
        self, snapshot: Snapshot
    ) -> tuple[QuestState, QuestInfo] | None:
        """Return the incomplete TAKEN KILL_LEVEL quest for this dungeon."""
        dungeon_id = snapshot.floor_key[0]
        for quest in snapshot.quests.values():
            info = self._quest_knowledge.get(quest.id)
            if (
                info is not None
                and info.type == QUEST_TYPE_KILL_LEVEL
                and info.dungeon == dungeon_id
                and quest.status == QUEST_STATUS_TAKEN
                and (
                    quest.cur_num is None
                    or quest.cur_num < self._kill_quest_completion_target(quest, info)
                )
            ):
                return quest, info
        return None



    @claims(ClaimOwner.QUEST_REQUEST)
    def _start_kill_quest_regeneration(self, snapshot: Snapshot) -> str | None:
        """Start UP-then-DOWN regeneration at the existing exhausted-floor seam."""
        active = self._taken_dungeon_kill_level_quest(snapshot)
        if active is None:
            return None
        quest, info = active
        if snapshot.dungeon_level != info.level:
            return None
        if any(
            monster.race_id == info.monrace_id
            for monster in snapshot.visible_monsters
        ):
            return None
        if self._quest_regen_exhausted_floor == snapshot.floor_key:
            self.last_reason = "quest:regen:exhausted"
            return WAIT_KEY
        if self._quest_regen_phase == "ascend":
            pass
        elif self._quest_regen_id == quest.id:
            if quest.cur_num == self._quest_regen_kills_before:
                self._quest_regen_zero_rounds += 1
            else:
                self._quest_regen_zero_rounds = 0
            if self._quest_regen_zero_rounds >= 3:
                self._quest_regen_exhausted_floor = snapshot.floor_key
                self._quest_regen_phase = None
                self.last_reason = "quest:regen:exhausted"
                return WAIT_KEY
        else:
            self._quest_regen_zero_rounds = 0
        self._quest_regen_id = quest.id
        self._quest_regen_phase = "ascend"
        self._quest_regen_kills_before = quest.cur_num
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and self._is_upstairs_target(here):
            self.last_reason = "quest:regen:ascend"
            return UP_STAIRS_KEY
        step = self._nearest_goal_step(snapshot, self._is_upstairs_target)
        if step is not None:
            self.last_reason = "quest:regen:ascend"
            return self._step_toward(snapshot, step)
        return None

    def _all_known_descents_blocked_by_next_depth_requirements(
        self, snapshot: Snapshot
    ) -> bool:
        """Report when every known forward stair fails the next-depth gate."""
        if snapshot.in_town or self._returning_to_town:
            return False
        if (
            self._active_fixed_quest_id(snapshot) is not None
            or self._quest_floor_exit_locked(snapshot)
            or self._fundraising_mode in {"mine", "scavenge"}
            or self._guardian_descent_blocked(snapshot)
        ):
            # These veto owners must not acquire a resistance-return latch.  In
            # particular, an incomplete quest may reject the resulting return.
            return False
        if not self._missing_required_abilities(
            snapshot, snapshot.dungeon_level + 1
        ):
            return False
        visible = {
            grid.position
            for grid in snapshot.grids.values()
            if grid.is_descent
        }
        if not visible:
            return False
        expired = self._nav_ledger.expired_targets("descend")
        remembered_only = self._remembered_downstairs - visible - expired
        if remembered_only or any(
            position not in expired
            and self._is_descent_target(snapshot, snapshot.grids[position])
            for position in visible
        ):
            return False
        return True





    def _clear_unseen_retreat(self) -> None:
        if self._escape_state.owner == "unseen":
            self._escape_state.release()
        self._unseen_retreat_floor = None
        self._unseen_retreat_direction = None
        self._unseen_retreat_target = None
        self._unseen_choke_position = None
        self._unseen_choke_started_turn = None

    @staticmethod
    def _is_unseen_spell_message(message: str) -> bool:
        return any(
            fragment in message
            for fragment in (
                "呪文を唱え",
                "ブレスを吐いた",
                "を放った",
                "つぶやいた",
                "身振りをした",
                "を指さして",
                "叫んだ",
                "を射った",
                "を発射した",
                "を投げた",
                " casts ",
                " breathes",
                " fires ",
                " mumbles",
                " gestures ",
                " invokes ",
                " shoots ",
                " throws ",
                " points at ",
                " screams ",
                " tries to cast ",
            )
        )

    @staticmethod
    def _is_unseen_attack_message(message: str) -> bool:
        """Whether a monster attack names Hengband's hidden actor.

        The finite method text comes from monster-attack-describer.cpp:64-229.
        monster-attack-player.cpp:297-310 joins the actor to that text, while
        monster-describer.cpp:39-53,91 supplies 何か / it / something when the
        attacking monster is hidden. Spell wording comes from mspell-bolt.cpp,
        mspell-ball.cpp, mspell-breath.cpp and mspell-curse.cpp.
        """
        message = re.sub(r" <x[1-9]\d*>$", "", message)
        # mspell-util.cpp formats the hidden actor through monster_name().
        # The spell tables use many different verbs and spell names; keep the
        # actor anchor, then accept the spell/breath/shot families they emit.
        if message.startswith("何か") and HengbotPolicy._is_unseen_spell_message(
            message
        ):
            return True
        if message.startswith(("It ", "Something ")) and HengbotPolicy._is_unseen_spell_message(
            message
        ):
            return True
        japanese_acts = (
            "殴られた。",
            "触られた。",
            "パンチされた。",
            "蹴られた。",
            "ひっかかれた。",
            "噛まれた。",
            "刺された。",
            "斬られた。",
            "角で突かれた。",
            "押し潰された。",
            "飲み込まれた。",
            "よだれをたらされた。",
            "唾を吐かれた。",
            "にらまれた。",
            "泣き叫ばれた。",
            "胞子を飛ばされた。",
            "金をせがまれた。",
        )
        japanese_subject_acts = (
            "は請求書をよこした。",
            "が体の上を這い回った。",
            "は爆発した。",
            "が XXX4 を発射した。",
        )
        english_acts = (
            "hits you.",
            "touches you.",
            "punches you.",
            "kicks you.",
            "claws you.",
            "bites you.",
            "stings you.",
            "slashes you.",
            "butts you.",
            "crushes you.",
            "engulfs you.",
            "charges you.",
            "crawls on you.",
            "drools on you.",
            "spits on you.",
            "explodes.",
            "gazes at you.",
            "wails at you.",
            "releases spores at you.",
            "projects XXX4's at you.",
            "begs you for money.",
        )
        return (
            message in {f"何かに{act}" for act in japanese_acts}
            or message in {f"何か{act}" for act in japanese_subject_acts}
            or message
            in {
                f"{actor} {act}"
                for actor in ("It", "Something")
                for act in english_acts
            }
        )

    def _recent_reverse_direction(self, origin: Position) -> tuple[int, int] | None:
        recent = list(self._recent)
        # Movement from before the player's own teleport points back across
        # the jump, at the place it teleported away from (Forest 32F
        # 2026-10-03 11:11:13: (-1, 75), a 100+ cell walk back to the attack).
        landing = getattr(self, "_recent_since_teleport", None)
        if landing is not None and landing[0] == self._floor_key:
            recent = recent[-landing[1]:] if landing[1] > 0 else []
        for position in reversed(recent):
            if position != origin:
                return (
                    position.y - origin.y,
                    position.x - origin.x,
                )
        return None




    @claims(ClaimOwner.ESCAPE)
    def _blocking_escape_melee_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        goal: Callable[[GridState], bool],
    ) -> str | None:
        """Bump a weak adjacent blocker when it is the door to an escape route."""
        player = snapshot.player
        hostiles = self._physical_hostiles(snapshot)
        candidates = [
            monster for monster in hostiles
            if monster.distance <= 1
            and monster.max_ranged_damage <= 0
            and self._escape_blocker_is_easy_kill(snapshot, hostiles, monster)
        ]
        best: tuple[int, MonsterState] | None = None
        for monster in candidates:
            queue: deque[tuple[Position, int]] = deque([(monster.position, 0)])
            seen = {player.position, monster.position}
            distance_to_goal: int | None = None
            while queue:
                position, distance = queue.popleft()
                cell = snapshot.grid_at(position)
                if cell is not None and goal(cell):
                    distance_to_goal = distance
                    break
                for dy, dx in NEIGHBOR_OFFSETS:
                    neighbor = Position(position.y + dy, position.x + dx)
                    if neighbor in seen:
                        continue
                    cell = snapshot.grid_at(neighbor)
                    if cell is None or not cell.passable:
                        continue
                    if cell.has_monster and neighbor != monster.position:
                        occupant = next(
                            (
                                hostile
                                for hostile in hostiles
                                if hostile.position == neighbor
                            ),
                            None,
                        )
                        if (
                            occupant is None
                            or occupant.max_ranged_damage > 0
                            or not self._escape_blocker_is_easy_kill(
                                snapshot, hostiles, occupant
                            )
                        ):
                            continue
                    seen.add(neighbor)
                    queue.append((neighbor, distance + 1))
            if distance_to_goal is not None and (
                best is None or distance_to_goal < best[0]
            ):
                best = (distance_to_goal, monster)
        if best is None:
            return None
        return self._direction_key(player.position, best[1].position)

    def _escape_blocker_is_easy_kill(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        monster: MonsterState,
    ) -> bool:
        """Use the combat projection, not monster size, to approve a bump."""
        weapon = next(
            (
                item for item in snapshot.equipment
                if item.slot == "main_hand"
                and (item.is_melee_weapon or item.is_digging_tool)
            ),
            None,
        )
        if weapon is None or snapshot.player.main_hand_blows <= 0:
            return False
        damage = self._main_hand_dps(snapshot, weapon)
        if damage <= 0:
            return False
        turns = max(1, ceil(monster.hp / damage))
        incoming = self.threat_prediction(
            snapshot, hostiles, turns=turns
        )["operational_total"]
        return incoming < snapshot.player.hp

    def _summoner_retreat_route(
        self,
        snapshot: Snapshot,
        summoners: list[MonsterState],
        hostiles: list[MonsterState],
    ) -> tuple[Position | None, Position | None]:
        """Return (covered cell to retreat to, first step toward it).

        The destination is the cell this search actually chose, so an owner can
        commit to it across decisions.  The flee fallback has no destination: it
        is a direction away from the hostiles, not a place.
        """
        origin = snapshot.player.position
        origin_distance = min(origin.distance_to(monster.position) for monster in summoners)
        seen = {origin}
        queue: deque[tuple[Position, Position | None, int]] = deque([(origin, None, 0)])
        candidates: list[tuple[int, int, int, Position, Position]] = []

        while queue:
            position, first_step, path_distance = queue.popleft()
            if position != origin and first_step is not None:
                openness = self._open_neighbor_count(snapshot, position)
                summoner_distance = min(
                    position.distance_to(monster.position) for monster in summoners
                )
                if (
                    openness <= SUMMONER_CHOKE_NEIGHBORS - 1
                    and summoner_distance >= origin_distance
                ):
                    candidates.append(
                        (
                            path_distance,
                            openness,
                            -summoner_distance,
                            first_step,
                            position,
                        )
                    )
            for neighbor in self._walkable_neighbors(snapshot, position):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(
                    (
                        neighbor,
                        neighbor if first_step is None else first_step,
                        path_distance + 1,
                    )
                )

        if candidates:
            chosen = min(candidates, key=lambda candidate: candidate[:3])
            return chosen[4], chosen[3]
        return None, self._flee_step(snapshot, hostiles)

    def _summoner_retreat_step(
        self,
        snapshot: Snapshot,
        summoners: list[MonsterState],
        hostiles: list[MonsterState],
    ) -> Position | None:
        return self._summoner_retreat_route(snapshot, summoners, hostiles)[1]


    def _material_melee_engagement(
        self, snapshot: Snapshot, monster: MonsterState
    ) -> bool:
        if monster.distance > HUNT_RANGE or monster.max_melee_damage <= 0:
            return False
        horizon = 3
        weapon = next(
            (
                item for item in snapshot.equipment
                if item.slot == "main_hand" and item.is_melee_weapon
            ),
            None,
        )
        if weapon is not None and snapshot.player.main_hand_blows > 0:
            melee_output = self._main_hand_dps(snapshot, weapon)
            if melee_output > 0:
                # A weak monster that dies in one or two player actions cannot
                # deliver three full turns of theoretical maximum melee. The
                # old fixed horizon classified a 4d6 Large brown snake as a
                # material threat to a full-HP level-seven warrior.
                horizon = min(horizon, max(1, ceil(monster.hp / melee_output)))
        actions = self._monster_actions(
            monster.speed, snapshot.player.speed, turns=horizon
        )
        return (
            monster.max_melee_damage * actions
            >= snapshot.player.hp * ENGAGEMENT_AVOID_DAMAGE_RATIO
        )

    # ------------------------------------------------------------- pathfinding

    def _walkable_neighbors(
        self,
        snapshot: Snapshot,
        pos: Position,
        *,
        allow_damaging: bool | None = None,
        goal: Callable[[GridState], bool] | None = None,
    ) -> list[Position]:
        floor = self._floor_t
        door = self._door_t
        rubble = self._rubble_t
        y = pos.y
        x = pos.x
        neighbors: list[Position] = []
        for dy, dx in NEIGHBOR_OFFSETS:
            ny = y + dy
            nx = x + dx
            key = (ny, nx)
            if key in floor:
                neighbor = Position(ny, nx)
                grid = snapshot.grids.get(neighbor)
                if self._on_town_border(snapshot, neighbor) and not (
                    grid is not None and grid.has_entrance
                ):
                    continue
                if (
                    allow_damaging is False
                    and self._is_avoidable_hazard_grid(grid)
                    and not (grid is not None and goal is not None and goal(grid))
                ):
                    continue
                neighbors.append(neighbor)
            elif key in door:
                neighbors.append(Position(ny, nx))
            elif (dy == 0 or dx == 0) and key in rubble:
                # Rubble is tunnelled from an orthogonally adjacent tile.
                neighbors.append(Position(ny, nx))
        if allow_damaging is None:
            safe = [
                neighbor
                for neighbor in neighbors
                if not self._is_avoidable_hazard_grid(
                    snapshot.grids.get(neighbor)
                )
            ]
            # Immediate movement selectors prefer every safe option, but retain
            # emergency/corridor progress when all available steps are harmful.
            return safe or neighbors
        return neighbors

    def _breakout_step(self, snapshot: Snapshot, avoid_key: str) -> Position | None:
        """A guaranteed-valid floor step (never a wall/door), avoiding the key
        that just failed. Prefers orthogonal, then least-visited."""
        origin = snapshot.player.position
        orthogonal: list[Position] = []
        diagonal: list[Position] = []
        for dy, dx in NEIGHBOR_OFFSETS:
            neighbor = Position(origin.y + dy, origin.x + dx)
            grid = snapshot.grids.get(neighbor)
            # Guaranteed-valid = plain passable floor (not a door: doors reject a
            # diagonal move and only open on an orthogonal step).
            if grid is None or grid.has_monster or not grid.passable or grid.is_door:
                continue
            if self._direction_key(origin, neighbor) == avoid_key:
                continue
            (orthogonal if (dy == 0 or dx == 0) else diagonal).append(neighbor)
        pool = orthogonal or diagonal
        if not pool:
            return None
        safe = [
            candidate
            for candidate in pool
            if not self._is_avoidable_hazard_grid(snapshot.grids.get(candidate))
        ]
        pool = safe or pool
        return min(pool, key=lambda p: self._visit_counts[p])










    def _retire_explore_goal(
        self, identity: ExplorationGoalIdentity
    ) -> None:
        self._release_claim_goal("explore-goal-retired", identity.position, owners=CLAIM_EXPLORE_GOAL_OWNERS)
        self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
        self._explore_goal_identity = None

    def _declare_explore_goal(self) -> None:
        """Record-only: the explore producer's committed goal cell."""
        identity = self._explore_goal_identity
        if identity is not None:
            self._declare_reach(identity.position)

    def _release_explore_walk(self, label: str) -> None:
        """Record-only (S2b.1b): the walk to the explore goal stops here.

        The oscillation branch of ``_decide`` stops walking because the walk
        circles, and probes or searches in place instead; the walk toward the
        committed goal ends on that board (the planner may pick the same goal
        again later: a new claim).  The goal itself is kept by the planner.
        """
        identity = getattr(self, "_explore_goal_identity", None)
        self._release_claim_goal(
            label,
            identity.position if identity is not None else None,
            owners=CLAIM_EXPLORE_GOAL_OWNERS,
        )

    def _route_to_explore_goal(
        self,
        snapshot: Snapshot,
        goal: Position,
        *,
        avoid: set[Position] | None = None,
    ) -> list[Position]:
        route = self._route_to_explore_goal_pass(
            snapshot, goal, allow_damaging=False, avoid=avoid
        )
        if route:
            return route
        return self._route_to_explore_goal_pass(
            snapshot, goal, allow_damaging=True, avoid=avoid
        )

    def _route_to_explore_goal_pass(
        self,
        snapshot: Snapshot,
        goal: Position,
        *,
        allow_damaging: bool,
        avoid: set[Position] | None,
    ) -> list[Position]:
        start = snapshot.player.position
        avoided = (avoid or set()) - {start, goal}
        queue: deque[Position] = deque([start])
        parent: dict[Position, Position | None] = {start: None}
        while queue:
            position = queue.popleft()
            if position == goal:
                break
            neighbors = self._walkable_neighbors(
                snapshot, position, allow_damaging=allow_damaging
            )
            if (
                position.distance_to(goal) == 1
                and (goal.y, goal.x) in self._remembered_floor_t
                and goal not in neighbors
            ):
                # Live monsters are excluded from the immediate floor index.
                # Permit only the committed goal as the final route step so
                # exploration approaches it and combat can engage.
                neighbors.append(goal)
            for neighbor in neighbors:
                if (
                    neighbor in parent
                    or neighbor in avoided
                    or neighbor in self._engagement_avoid_cells
                ):
                    continue
                parent[neighbor] = position
                queue.append(neighbor)
        if goal not in parent:
            return []
        path: list[Position] = []
        node: Position | None = goal
        while node is not None and node != start:
            path.append(node)
            node = parent[node]
        path.reverse()
        return path

    def _record_explore_goal(
        self,
        snapshot: Snapshot,
        kind: ExplorationGoalKind,
        position: Position,
    ) -> None:
        self._explore_goal_identity = ExplorationGoalIdentity(
            kind=kind,
            position=position,
            evidence_signature=self._explore_goal_signature(
                snapshot.grid_at(position)
            ),
        )
        self._explore_path_outcome = None

    def _clear_explore_path(self, outcome: ExplorationPathOutcome) -> None:
        self._explore_path = []
        self._explore_path_outcome = outcome


    def _remember_one_step_explore(
        self, snapshot: Snapshot, origin: Position, goal: Position
    ) -> None:
        self._pending_one_step_explore = (
            origin,
            goal,
            self._explore_goal_signature(snapshot.grid_at(goal)),
        )

    def _observe_one_step_explore(self, snapshot: Snapshot) -> None:
        for goal, retired_signature in list(
            self._unenterable_explore_goals.items()
        ):
            signature = self._explore_goal_signature(snapshot.grid_at(goal))
            if signature != retired_signature:
                del self._unenterable_explore_goals[goal]
                self._one_step_explore_failures.pop(goal, None)
                self._one_step_explore_signatures.pop(goal, None)

        pending = self._pending_one_step_explore
        self._pending_one_step_explore = None
        if pending is None:
            return
        origin, goal, attempted_signature = pending
        if snapshot.player.position == goal:
            self._explore_path_outcome = ExplorationPathOutcome.SUCCESS
            self._one_step_explore_failures.pop(goal, None)
            self._one_step_explore_signatures.pop(goal, None)
            return
        signature = self._explore_goal_signature(snapshot.grid_at(goal))
        if signature != attempted_signature:
            self._one_step_explore_failures.pop(goal, None)
            self._one_step_explore_signatures.pop(goal, None)
            return
        if self._one_step_explore_signatures.get(goal) != signature:
            self._one_step_explore_failures[goal] = set()
            self._one_step_explore_signatures[goal] = signature
        failures = self._one_step_explore_failures.setdefault(goal, set())
        failures.add(origin)
        if len(failures) >= 3:
            self._unenterable_explore_goals[goal] = signature
            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
            if (
                self._explore_goal_identity is not None
                and self._explore_goal_identity.position == goal
            ):
                self._explore_goal_identity = None




    def _is_damaging_grid(self, grid: GridState | None) -> bool:
        return (
            grid is not None
            and grid.terrain_id >= 0
            and grid.terrain_id in self._damaging_terrain_ids
        )

    def _is_avoidable_hazard_grid(self, grid: GridState | None) -> bool:
        """A visible hazard excluded by the primary navigation pass."""
        if grid is not None and self._map_predicate_snapshot is not None:
            if grid.position in self._hazard_cache:
                return self._hazard_cache[grid.position]
        result = self._is_damaging_grid(grid) or (
            grid is not None and grid.trap
        )
        if grid is not None and self._map_predicate_snapshot is not None:
            self._hazard_cache[grid.position] = result
        return result

    def _is_step_open(
        self,
        snapshot: Snapshot,
        start: Position,
        pos: Position,
        *,
        allow_damaging: bool = True,
    ) -> bool:
        grid = snapshot.grids.get(pos)
        if grid is None or grid.has_monster:
            return False
        if not allow_damaging and self._is_avoidable_hazard_grid(grid):
            return False
        if grid.is_door:
            return grid.passable or grid.is_closed_door
        # Rubble is only tunnelled from an orthogonally adjacent tile.
        if grid.is_rubble:
            return (pos.y == start.y or pos.x == start.x) and (
                (grid.position.y, grid.position.x) not in self._blocked_rubble
            )
        return grid.passable



    def _record_wall_search(self, position: Position) -> None:
        walls = self._undersearched_walls(position)
        if not walls:
            return
        self._search_counts[(position.y, position.x)] += 1
        for key in walls:
            self._wall_search_counts[key] += 1




    def _is_frontier(self, snapshot: Snapshot, grid: GridState) -> bool:
        # A fully-remembered static town (Outpost map loaded) has nothing left
        # to explore: without this, unlit night WALL tiles are absent from the
        # emitted map, so every walkable tile borders an 'unknown' wall and reads
        # as a frontier — the bot then 'explore's the town aimlessly instead of
        # shopping/recalling.
        if self._town_map_active(snapshot):
            return False
        # A closed door hides new ground behind it — unless we've given up trying
        # to open it, in which case it is effectively a wall.
        if grid.is_closed_door:
            return (grid.position.y, grid.position.x) not in self._blocked_doors
        # Rubble caps a passage (often a dead-end); tunnelling it opens the way, so
        # treat it as a frontier worth reaching until we give up digging it.
        if grid.is_rubble:
            return (grid.position.y, grid.position.x) not in self._blocked_rubble
        if not grid.passable:
            return False
        # A floor tile we keep standing on that never stops being a frontier has an
        # unrevealable neighbour (dark-room flicker) — stop chasing it so we move on
        # to real frontiers instead of oscillating in place.
        if self._visit_counts[grid.position] >= FRONTIER_EXHAUST_VISITS:
            self._probed_frontiers.add(grid.position)
            return False
        if grid.position in self._probed_frontiers:
            return False
        # A floor tile borders unexplored ground if a neighbour is not a known
        # tile. Crucially, a tile beyond the *map edge* (out of bounds) is void,
        # not frontier — otherwise the bot circles an open town/wilderness
        # perimeter forever.
        marked = self._marked_t
        blocked = self._blocked_unknown
        height = snapshot.height
        width = snapshot.width
        bounded = width > 0 and height > 0
        y = grid.position.y
        x = grid.position.x
        for dy, dx in NEIGHBOR_OFFSETS:
            ny = y + dy
            nx = x + dx
            key = (ny, nx)
            # An unknown neighbour marks unexplored ground — unless we have already
            # probed it to the limit and found a wall (blocked), in which case it
            # is not really a frontier.
            if key not in marked and key not in blocked:
                if not bounded or (0 <= ny < height and 0 <= nx < width):
                    return True
        return False

    def _is_remembered_frontier(self, snapshot: Snapshot, position: Position) -> bool:
        """Frontier test that also works after a reachable tile leaves view."""
        grid = snapshot.grids.get(position)
        if grid is not None:
            return self._is_frontier(snapshot, grid)
        if self._town_map_active(snapshot):
            return False

        key = (position.y, position.x)
        if key in self._door_t or key in self._rubble_t:
            return True
        if key not in self._floor_t:
            return False
        if self._visit_counts[position] >= FRONTIER_EXHAUST_VISITS:
            self._probed_frontiers.add(position)
            return False
        if position in self._probed_frontiers:
            return False

        bounded = snapshot.width > 0 and snapshot.height > 0
        for dy, dx in NEIGHBOR_OFFSETS:
            ny = position.y + dy
            nx = position.x + dx
            neighbor = (ny, nx)
            if neighbor in self._marked_t or neighbor in self._blocked_unknown:
                continue
            if not bounded or (0 <= ny < snapshot.height and 0 <= nx < snapshot.width):
                return True
        return False


    def _least_visited_neighbor(self, snapshot: Snapshot) -> Position | None:
        candidates = [
            candidate
            for candidate in self._walkable_neighbors(
                snapshot, snapshot.player.position
            )
            if candidate not in self._engagement_avoid_cells
            and (
                not snapshot.in_town
                or (
                    (grid := snapshot.grid_at(candidate)) is not None
                    and grid.store_number < 0
                    and grid.building_type < 0
                )
            )
        ]
        if not candidates:
            return None
        # The square we last stood on that is not this one.  ``_recent`` also
        # records stationary decisions (searches), so ``_recent[-2]`` is often
        # this very square and cannot name where we came from.
        here = snapshot.player.position
        previous = next(
            (position for position in reversed(self._recent) if position != here),
            None,
        )

        def score(pos: Position) -> tuple[int, int, int]:
            # In town, never wander onto the border ring (it exits into the open
            # wilderness); then never bounce straight back while another
            # neighbour exists, then prefer least-visited.  The border penalty is
            # first, so an edge tile is chosen only if every neighbour is an edge
            # (which cannot happen in the interior).  Bouncing back ranks above
            # visits: a dead-end square is always the least visited one, so
            # visits alone walked '8'/'2' between a corridor's last two squares
            # (Castle 20F, 2026-10-02 13:03:47, decisions 3580-3589).
            border = 1 if self._on_town_border(snapshot, pos) else 0
            return (border, 1 if pos == previous else 0, self._visit_counts[pos])

        return min(candidates, key=score)

    # --------------------------------------------------------------- utilities
    # ------------------------------------------------------- warning grids
    def _warning_supplies_exhausted(self, snapshot: Snapshot) -> bool:
        """物資が全て尽きている (user spec, verbatim), scoped by the user's
        ruling 「移動に関するルールなのでテレポート／ショート・テレポート／
        帰還の巻物に限定する」: this is a movement rule, so only the movement
        consumables count — the relocation reads (Teleport, Teleport Level,
        Phase Door) and the floor-escape read (Word of Recall).  Healing and
        status-cure potions are deliberately NOT part of the ledger.  Every
        finder requires ``aware`` — an unidentified copy cannot be
        deliberately read, so it is not a supply; food and stairs are not
        consumable supplies either."""
        return (
            self._find_teleport_scroll(snapshot) is None
            and self._find_phase_scroll(snapshot) is None
            and self._find_recall_scroll(snapshot) is None
        )

    def _claim_engagement_avoid_cells(
        self, cells: Iterable[Position]
    ) -> None:
        """Record an engagement/status-threat avoidance claim with ownership.

        The engagement owner's claims are tracked separately so the warning
        owner's exhaustion withdrawal can never remove them from the shared
        routing set."""
        owned = set(cells)
        self._engagement_owned_avoid_cells |= owned
        self._engagement_avoid_cells |= owned


    def _warning_prompt_response_key(self, snapshot: Snapshot) -> str | None:
        """Answer a TR_WARNING entry prompt reported by this snapshot.

        Snapshots are emitted only from the command loop
        (player-processor.cpp:312), so by the time the prompt's message is
        visible the blocking input_check has already been dismissed — by the
        CLI's stall nudge Escape (input_check treats Escape as "no"), or by
        a key from the walk's own composed tail.  input_check accepts only
        y/n/Escape; every other queued key rings the bell and the prompt
        keeps waiting, so which of those outcomes happened depends entirely
        on what was queued — suffix ownership (see _step_toward) is the
        safety-critical invariant, not any claimed harmlessness of stray
        keys.  This handler makes the disposition DELIBERATE:

        * player back on the walk's origin — the entry was refused; latch
          the grid and let routing choose another action.  The executor
          answers every live warning inline.  At the ordinary command loop,
          'n' invokes repeat_check and replays the warning-causing command.
          Therefore the policy must never post 'n' for the stale message
          retained in the snapshot buffer.
        * player standing on the walk's target — the crossing happened.  If
          it was the sanctioned forced walk, the message is just its
          record.  Otherwise a composed tail answered the prompt the caller
          never anticipated: latch the grid so the unsanctioned crossing
          happens at most once per floor, and let the decision continue.
        """
        self._warning_prompt_stops_decision = False
        if not any(
            home_page_message_body(message).startswith(
                WARNING_PROMPT_MESSAGE_PREFIXES
            )
            for message in snapshot.messages
        ):
            return None
        self._warning_prompt_stops_decision = True
        pending = self._warning_step_pending
        self._warning_step_pending = None
        if pending is not None:
            sequence, floor_key, origin, target, sanctioned = pending
            attributable = (
                sequence == self._decision_sequence - 1
                and floor_key == snapshot.floor_key
            )
            if attributable and snapshot.player.position == target:
                self._warning_prompt_stops_decision = False
                if not sanctioned:
                    # An unsanctioned crossing: the warning prompt was
                    # answered by a queued tail key, not by the exhausted-
                    # supplies forced walk.  Record the grid so it is
                    # avoided from now on; the crossing itself cannot be
                    # undone, so the decision proceeds normally.
                    self._latch_warning_refusal(target)
                return None
            if attributable and snapshot.player.position == origin:
                self._latch_warning_refusal(target)
                self._warning_prompt_stops_decision = False
                return None
        # With no attributable step there is no target cell to record, but
        # the already-dismissed prompt must not suppress every remaining rung.
        self._warning_prompt_stops_decision = False
        return None


    @claims(ClaimOwner.COMBAT)
    def _direction_key(self, origin: Position, target: Position) -> str:
        dy = max(-1, min(1, target.y - origin.y))
        dx = max(-1, min(1, target.x - origin.x))
        return DIRECTION_KEYS[(dy, dx)]



# Backwards-compatible alias for existing callers.
ConservativePolicy = HengbotPolicy
