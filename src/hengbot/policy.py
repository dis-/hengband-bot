from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field, replace
from heapq import heappop, heappush
from itertools import count
from math import ceil
import json
import re
from enum import Enum
from typing import Callable, Iterable, Literal
from pathlib import Path

from hengbot.latch_onset_capture import (
    CAPTURE_DECISIONS_AFTER_ONSET,
    assignment_provenance,
    checkpoint as latch_capture_checkpoint,
    decision_record as latch_capture_decision_record,
    write_window as write_latch_capture_window,
)

from hengbot.town_maps import TownMap
from hengbot.baseitem_knowledge import item_base_cost
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
from hengbot.equipment_mutation import EquipmentMutationExecutor, EquipmentMutationResult
from hengbot.policy_types import (
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
    AMMO_CARRY_STACK_LIMIT,
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
    CARDINAL_OFFSETS,
    CHARACTER_DUMP_MACRO,
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
    EMERGENCY_POTION_CARRY_TARGET,
    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
    EQUIPMENT_TRANSACTION_FINAL_STOP_REASONS,
    EAT_KEY,
    ExplorationPathOutcome,
    FOOD_MIN_SVAL,
    FOOD_TYPE_MANA,
    HEAVY_CURSE_TAG,
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
    IDENTIFY_PRESSURE_FREE_SLOTS,
    LEAVE_STORE_KEY,
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
    NEIGHBOR_OFFSETS,
    PACK_CAPACITY,
    PLAYER_CLASS_BERSERKER,
    PROBE_LIMIT,
    RANGED_MAX_DISTANCE,
    READ_KEY,
    RECALL_MIN_DEPTH,
    REFILL_KEY,
    SEARCH_KEY,
    SEARCH_LIMIT,
    SELL_KEY,
    STAFF_IDENTIFY_MIN_SUCCESS,
    STORE_RESTOCK_WAIT_TURNS,
    STORE_STUCK_LIMIT,
    STUCK_ESCAPE_LIMIT,
    TERMINAL_NUDGE_LIMIT,
    TORCH_THROW_TARGET,
    TOWN_TRAVEL_STORE_SYMBOLS,
    TOWN_STOP_PASS_LIMIT,
    TOWN_TRAVEL_STALL_LIMIT,
    TOWN_TRAVEL_TURN_STALL_LIMIT,
    STAIR_OBSERVATION_WAIT_LIMIT,
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
from hengbot.town_arbiter import TownArbiterMixin, TownTurnArbiter
from hengbot.policy_calibration import CalibrationMixin
from hengbot.policy_identification import IdentificationMixin
from hengbot.policy_fundraising import FundraisingMixin
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
TOWN_TRAVEL_MIN_DISTANCE = 3
# Consecutive travel issues without getting closer before giving the goal back
# to BFS walking (an unknown approach makes the game reject the route).
HOME_PLAN_OWNED_PROCESSING_REASONS = {
    "home:processing-complete",
}
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


# それならば一旦多少の非効率は許容する。訪問回数の最大値を300回まで緩和することを許可するのでまずは処理を
# 完遂させること。効率化はその後。
# Cash retained after buying every departure-blocking shortage on a cross-town
# shopping expedition, covering the user-specified round trip.
CROSS_TOWN_SHOPPING_RESERVE = 1000


# R300 costs about 300 player turns at roughly 10 game turns per rest.
# Use that measured game-turn cost when crediting one rest command; the stock
# turnover interval is a separate clock and is not a valid charge clamp.
STORE_RESTOCK_REST_GAME_TURNS = 3000
RESTOCK_WAIT_MACRO = "R300\r"
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
STORE_RETRY_TURNS = 5000
# Oberon and the Serpent are factual game constants: fixed WIN quests that are
# TAKEN from birth and are never completable by the bot's fixed-quest machinery.
# This is executor capability, not strategy approval or a tuning threshold.
# These quest offers are unconditional once their quest state is exported.
# Other fixed quests are conditional chains and only become candidates when a
# live town building actually advertises them.
# Building 0 is the Outpost inn/castle.  The ordinary inns in Telmora,
# Morivant, and Angwil are building 4.  Zul's tavern does not offer town
# teleportation, so it is intentionally absent.
TOWN_TELEPORT_BUILDING_TYPES = {0: 0, 1: 4, 2: 4, 3: 4}
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
ENTER_DUNGEON_MACRO = ">\ry"
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
STUCK_FAMILY_REASONS = frozenset(
    {
        "stuck:wander",
        "stuck:seek-stairs",
        "search",
        "seek-secret-wall",
        "breakout:least-visited",
        "breakout:seek-frontier",
        "breakout:dig-to-stairs",
        "probe",
        # Leaving a fundraising floor toward up-stairs it cannot reach loops the
        # same way (a walled-off ascent), so those reasons count too.
        "fundraise:seek-upstairs",
        "fundraise:seek-upstairs-explore",
        "fundraise:seek-upstairs-wander",
        "fundraise:probe",
        "fundraise:search",
        "paralyzer-guard:approach-range",
    }
)
# Floor upkeep that a stuck bot still does between searches (relight, heal, eat).
# These must neither grow the stuck streak nor RESET it — otherwise a relight
# every few turns keeps the streak pinned near zero and the escape never fires.
# Only genuine progress (exploring a frontier, fighting, descending) resets it.
STUCK_NEUTRAL_REASONS = frozenset(
    {"rest", "refill-light", "wield-light", "eat", "item:eat"}
)
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
TOWN_WANDER_REASONS = frozenset({"stuck:wander", "breakout:least-visited"})
TOWN_WANDER_LIMIT = 60

# Generic town-repetition detector (user directive: auto-detect and repair this
# CLASS). Every observed shape — Home-door bounce, store-to-store travel
# ping-pong — is a short cycle of (reason, position) signatures with no
# progress, and each one evaded the cell-based loop guard (store snapshots
# reset it; travel keeps the position changing). A window of town decisions
# whose signatures collapse to a handful of distinct values while gold, pack
# and equipment all stay unchanged IS such a cycle, whatever subsystem drives
# it. Waits are excluded (deliberate stationary states), and any progress
# resets the window.
TOWN_CYCLE_WINDOW = 48
TOWN_CYCLE_MAX_DISTINCT = 8
# Native town travel is comparatively slow, so the generic 48-decision window
# can represent many minutes.  A route that emits at least eight travel rows
# while collapsing to three cells is not a legitimate cross-town traverse.
TOWN_FAST_TRAVEL_WINDOW = 12
TOWN_FAST_TRAVEL_MIN_ROWS = 8
TOWN_FAST_TRAVEL_MAX_POSITIONS = 3
# d309c2a lowered this fallback only to beat cli.py's 40-decision cell guard in
# town.  1e46bb5 removed that guard from town entirely, so that race no longer
# exists and the tighter bound only adds false positives: on a first visit,
# native travel may reject an unknown approach and leave a long per-tile walking
# leg (roughly one recorded locomotion decision per tile) while the progress
# marker remains frozen until the first transaction.  The original 96-decision
# bound is safe for every known legitimate shape: Home scans are page-bounded,
# and purchases reset the marker per transaction.
TOWN_NO_PROGRESS_LIMIT = 96
TOWN_CYCLE_BREAK_LIMIT = 2  # second cycle in one town visit -> visible stop
TOWN_CYCLE_IGNORED_REASONS = frozenset(
    {
        "town:wait-recall",
        "return:wait-recall",
        "town:cycle-break",
        # This long locomotion leg is independently bounded by both native-
        # travel progress leashes.  Counting its duplicate input-latency rows
        # as transaction/wander no-progress falsely blocks a productive walk
        # across town before it can reach the entrance.
        "town:travel-entrance",
    }
)
STORE_RESTOCK_REASON_NAMES = {
    STORE_HOME: "home",
    STORE_GENERAL: "general",
    STORE_WEAPON: "weapon",
    STORE_TEMPLE: "temple",
    STORE_ALCHEMIST: "alchemist",
    STORE_MAGIC: "magic",
    STORE_BLACK: "black-market",
    STORE_ARMOURY: "armoury",
}
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
EMPTY_DIVE_LIMIT = 3  # consecutive over-extended dives before switching dungeons
NO_DEPTH_PROGRESS_DIVE_LIMIT = 5

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
OVEREXTEND_LOOT_MAX = 4  # "almost nothing": at most this many pickups on the dive
OVEREXTEND_EMERGENCY_MIN = 2  # ...paired with at least this many emergency escapes
PICKUP_REASONS = frozenset({"pickup", "victory:pickup", "conquest:pickup"})
# Bailing out under fire: teleport/phase away, recall out, or run for the stairs.
# Being forced into these repeatedly is the signature of a too-deep floor.
EMERGENCY_ESCAPE_REASONS = frozenset(
    {
        "emergency:teleport",
        "emergency:phase",
        "emergency:recall",
        "emergency:stairs",
        "emergency:seek-upstairs",
    }
)

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
MOVE_REASONS = frozenset(
    {
        "explore",
        "seek-downstairs",
        "approach-descent",
        "breakout:seek-frontier",
        "clear-descent",
        "hunt",
        "town:kill-mob-approach",
        "stuck:seek-stairs",
        "seek-secret-wall",
        "stuck:wander",
        "breakout",
        "pickup",
        "probe",
        "summoner:retreat",
        "return:explore",
        "return:flee",
        "return:seek-upstairs",
        "return:wander",
        "livelock:seek-upstairs",
        "survival:seek-exit",
        "fundraise:probe",
        "fundraise:seek-upstairs",
        "fundraise:seek-upstairs-explore",
        "fundraise:seek-upstairs-wander",
        "fundraise:seek-loot",
        "fundraise:trigger-autodestroy",
        "paralyzer-guard:approach-range",
        "seek-loot",
        "trigger-autodestroy",
        "victory:trigger-autodestroy",
        "shop:approach",
    }
)
TOWN_CLAIM_ADVANCING_MOVE_REASONS = frozenset(
    reason
    for reason in MOVE_REASONS
    if reason != "stuck:wander" and not reason.startswith("breakout")
)

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
INSCRIBE_KEY = "{"
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
BUY_CONFIRM_SUFFIX = "\r"
# Live economy records show that stacked purchases consume the quantity Return
# and one DEFAULT_Y confirmation Return; no intervening -more- is present.
STACKED_BUY_CONFIRM_SUFFIX = "1\r\r"
# *Identify* always opens screen_object(); equipment with many attributes can
# add several ``-- more --`` pages before the final continue prompt.  Escape
# closes each page and is harmless after control returns to the command loop.
SELL_ATTEMPT_LIMIT = 3
SELL_CONFIRM_SUFFIX = "\r"
# Mirrors store/service-checker.cpp's per-store tval switches.  The policy's
# sale paths only need these ordinary, unconditional cases; the Temple's
# blessed-weapon/figurine exceptions and the General/Magic special svals are
# deliberately not claimed from tval alone.
STORE_ACCEPTED_TVALS = {
    STORE_GENERAL: frozenset(
        {
            TVAL_WHISTLE, TVAL_FOOD, TVAL_LITE, TVAL_FLASK, TVAL_SPIKE,
            TVAL_SHOT, TVAL_ARROW, TVAL_BOLT, TVAL_DIGGING, TVAL_CLOAK,
            TVAL_BOTTLE, TVAL_FIGURINE, TVAL_STATUE, TVAL_CAPTURE, TVAL_CARD,
        }
    ),
    STORE_ARMOURY: frozenset(
        {
            TVAL_BOOTS, TVAL_GLOVES, TVAL_CROWN, TVAL_HELM, TVAL_SHIELD,
            TVAL_CLOAK, TVAL_SOFT_ARMOR, TVAL_HARD_ARMOR, TVAL_DRAG_ARMOR,
        }
    ),
    STORE_WEAPON: frozenset(
        {
            TVAL_SHOT, TVAL_ARROW, TVAL_BOLT, TVAL_BOW, TVAL_DIGGING,
            TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD, TVAL_HISSATSU_BOOK,
        }
    ),
    STORE_TEMPLE: frozenset(
        {TVAL_LIFE_BOOK, TVAL_CRUSADE_BOOK, TVAL_SCROLL, TVAL_POTION, TVAL_HAFTED}
    ),
    STORE_ALCHEMIST: frozenset({TVAL_SCROLL, TVAL_POTION}),
    STORE_MAGIC: frozenset(
        (SPELLBOOK_TVALS - {TVAL_LIFE_BOOK, TVAL_CRUSADE_BOOK, TVAL_HISSATSU_BOOK})
        | {TVAL_AMULET, TVAL_RING, TVAL_STAFF, TVAL_WAND, TVAL_ROD,
           TVAL_SCROLL, TVAL_POTION, TVAL_FIGURINE}
    ),
}
# Fuel flasks to stock for the lantern. We only walk to the shop if we have at
# least a little gold; true affordability is re-checked against the live price in
# the store (and if we can't afford it there we give up rather than loop).
LANTERN_MIN_GOLD = 1
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
SHOP_APPROACH_STUCK_LIMIT = 12
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
FOOD_TYPE_RATION = 0

# Return to town before supplies become fatal, or as soon as every normal pack
# slot is occupied. INVEN_PACK_SLOTS contains slots 0..22; slot 23 is only the
# temporary overflow slot and is not emitted in bot snapshots.
# Home identification works in batches but keeps enough space for purchases,
# swapped-out equipment, and an emergency floor pickup while town work continues.
HOME_BATCH_RESERVED_SLOTS = 3
# Rations to keep stocked; the General Store sells them, and a town return that
# restocks nothing just bounces straight back down and returns again.
# MANA races may eat their identification workhorse, but ordinary hunger must
# leave enough charges for the staff to remain functional. Weakness/fainting
# overrides this reserve because survival is the device's final purpose.
# Five slots is the normal loot-space target.  Four remains a usable terminal
# fallback when every safe town route for freeing another slot is exhausted.
MIN_TERMINAL_FREE_PACK_SLOTS = 4
TELEPORT_SCROLL_TARGET = 3
# Deep runs (10F+) escape far more often, so carry a big teleport buffer and only
# head back to restock once it is drawn down to the low reserve.
TELEPORT_SCROLL_DEEP_TARGET = 15
TELEPORT_RETURN_THRESHOLD = 3
# Once the character has reached this dungeon depth, returning to the dungeon
# from town uses Word of Recall (which lands at the deepest level reached) rather
# than walking to the wilderness entrance and re-descending from level 1.
RECALL_RETURN_THRESHOLD = 3
RECALL_ISSUE_CONFIRM_TURNS = 10
# Below this floor every ledger item is a convenience: if its suppliers are
# exhausted (or the item is unaffordable), walking out is safer than bouncing.
WALK_OUT_MAX_DEPTH = RECALL_MIN_DEPTH - 1
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
IDENTIFY_PURCHASE_MAX = 5
MINING_RUNS_PER_SET = 5
# User-approved standing float: it enables the strict spare-scroll barren-floor
# clause and is consumed only by incidental losses such as fire, acid, or theft.
DETECTION_SCROLL_BUFFER = 5
# Mining has substantial fixed overhead: town processing, two wilderness crossings
# for shallow runs, and one Treasure Detection scroll per fresh floor.  Build a
# useful reserve in one batch instead of restarting fundraising after every dive.
# Outpost base prices are about 20g for the General Store's cheapest Shovel and
# 15g for one Alchemist Treasure Detection scroll.  Keep a deliberately round
# 100g reserve to cover charisma/store-price variation and a useful margin.
# When either missing component is visible in the live store snapshot, its
# observed price replaces that component's base price for the reserve decision.
INN_BUILDING_TYPE = 0
HUNTER_OFFICE_BUILDING_TYPE = 13
RUMOR_KEY = "u"
RUMOR_EXIT_SUFFIX = "\r\r\x1b"
# Unlocking destinations can take many medium ("u") rumors. Keep each visit
# bounded so PostMessage input finishes well below the CLI's stalled-send
# diagnostic, then re-read exported progress before spending more gold.
RUMOR_COST = 10
RUMOR_READ_KEY = RUMOR_KEY + "\r"  # pick the rumor action, dismiss its -more-
RUMOR_READS_PER_VISIT = 40
# Gold kept in reserve so a rumor batch never spends the character dry; the batch
# size adapts to whatever is affordable above it. Below this, top up by mining.
RUMOR_GOLD_RESERVE = 300
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


def _new_town_turn_arbiter() -> TownTurnArbiter:
    return TownTurnArbiter({
        "store-router": (("TOWN_TRAVEL_STALL_LIMIT", "SHOP_APPROACH_STUCK_LIMIT"), min(TOWN_TRAVEL_STALL_LIMIT, SHOP_APPROACH_STUCK_LIMIT)),
        "shop-buy": (("STORE_STUCK_LIMIT", "STORE_RETRY_TURNS"), STORE_STUCK_LIMIT),
        "shop-sell": (("SELL_ATTEMPT_LIMIT",), SELL_ATTEMPT_LIMIT),
        "home-visit": (("CALIBRATION_HOME_VISIT_LIMIT", "TOWN_STOP_PASS_LIMIT"), CALIBRATION_HOME_VISIT_LIMIT),
        "home-errand": (("TOWN_STOP_PASS_LIMIT",), TOWN_STOP_PASS_LIMIT),
        "home-scan": (("CALIBRATION_HOME_VISIT_LIMIT",), CALIBRATION_HOME_VISIT_LIMIT),
        "equipment-txn": (("EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT",), EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT),
        "equipment-opt": (("STORE_STUCK_LIMIT",), STORE_STUCK_LIMIT),
        "calibration": (("STORE_STUCK_LIMIT",), STORE_STUCK_LIMIT),
        "identification": (("IDENTIFY_FAIL_LIMIT", "IDENTIFY_PURCHASE_MAX"), IDENTIFY_FAIL_LIMIT),
        "town-plan": (("TOWN_STOP_PASS_LIMIT",), TOWN_STOP_PASS_LIMIT),
        "fundraising": (("MINING_STALL_LIMIT",), MINING_STALL_LIMIT),
        "curse-enchant": (("STORE_STUCK_LIMIT",), STORE_STUCK_LIMIT),
        "cross-town": (("TOWN_TRAVEL_STALL_LIMIT",), TOWN_TRAVEL_STALL_LIMIT),
        "survival": (("STORE_STUCK_LIMIT",), STORE_STUCK_LIMIT),
        "departure": (("TOWN_TRAVEL_STALL_LIMIT",), TOWN_TRAVEL_STALL_LIMIT),
        "detectors": (("TOWN_CYCLE_BREAK_LIMIT",), TOWN_CYCLE_BREAK_LIMIT),
        "rumor": (("TOWN_STOP_PASS_LIMIT",), TOWN_STOP_PASS_LIMIT),
        "quest-request": (("TOWN_STOP_PASS_LIMIT",), TOWN_STOP_PASS_LIMIT),
        "misc": (("TOWN_STOP_PASS_LIMIT",), TOWN_STOP_PASS_LIMIT),
    })


from hengbot.policy_navigation import NavigationMixin
from hengbot.policy_combat import CombatMixin
from hengbot.policy_quest import QuestMixin
from hengbot.policy_equipment import EquipmentMixin
from .policy_home import HomeMixin


class HengbotPolicy(HomeMixin, EquipmentMixin, QuestMixin, PolicyHelpersMixin, CombatMixin, NavigationMixin, SupplyMixin, FundraisingMixin, IdentificationMixin, CalibrationMixin, TownArbiterMixin):
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
        self._q2_blue_recovery_pickup_prepared: tuple[
            Position, tuple[int, tuple[int, ...]]
        ] | None = None
        self._q2_blue_recovery_pickup_posted: tuple[
            Position, tuple[int, tuple[int, ...]]
        ] | None = None
        self._q2_blue_recovery_witnessed = False
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
        self._home_history_inflight: tuple[str, tuple[str, int, int], int, int] | None = None
        self._saw_dungeon_recall = False
        self._dive_dungeon: int | None = None  # dungeon id of the dive in progress
        self._dive_start_recall_depth: int | None = None
        self._dive_loot = 0  # items grabbed on the current dive
        self._dive_emergencies = 0  # emergency escapes forced on the current dive
        self._target_empty_dives = 0  # consecutive over-extended dives of the target
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
        self._equipment_departure_cache_token: int | None = None
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
        self._home_visit = HomeVisitExecutor(CALIBRATION_HOME_VISIT_LIMIT)
        self._pending_home_visit_report: str | None = None
        self._home_route_refusal: dict[str, object] | None = None
        self._home_route_refusal_sequence: int | None = None
        self._town_was_in_town = False
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
            tuple[str, int, int], int, int, int
        ] | None = None
        # Same target and shortage after a registered, money-spending buy is a
        # distinct defect from a transport failure at unchanged gold.
        self._last_buy_progress_sig: tuple[str, int, int] | None = None
        self._store_buy_no_progress_count = 0
        self._descent_blocked = False
        self._descent_block_countdown = 0
        self._returning_to_town = False
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
        self._unseen_wait_remaining = 0
        self._unseen_wait_intercepted = False
        self._unseen_attack_evidence: str | None = None

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
        # store_type -> the game turn it was latched at (see STORE_RETRY_TURNS).
        self._town_store_attempted: dict[int, int] = {}
        self._home_latch_active: dict[str, object] | None = None
        self._home_latch_history: list[dict[str, object]] = []
        self._home_gate_telemetry: dict[str, object] = {}
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
        # Successful sales are retained for the same town visit. Buying the
        # same tval/sval item back is semantic churn, not shopping progress.
        self._town_visit_sale_signatures: set[tuple[int, int]] = set()
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
        self._mining_runs_completed = 0
        self._planned_mining_runs: int | None = None
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
        ] | None = None
        self._home_atomic_withdraw_procurement_class: tuple[int, int] | None = None
        self._home_atomic_withdraw_index: int | None = None
        self._home_atomic_withdraw_posted_turn: int | None = None
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
        self._home_candidate_waiting = True
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
        self._retried_home_identification_items: set[tuple[str, int, int]] = set()
        # knowledge-self.cpp:214 and bot-json-output.cpp:861 traverse the same
        # Home stock array in the same order.  Addressing is derived from this
        # exact ~9 order, never from an in-store item observation.
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
        # Consumables are deliberately absent from OwnedEquipmentCatalog.  Keep
        # the one Home consumable whose exact stock matters in the complete
        # duplicate-preserving knowledge catalogue.
        self._home_star_remove_curse_count: int | None = None
        self._home_knowledge_scan_requested = False
        self._home_knowledge_scan_inflight = False
        self._home_knowledge_scan_retries_remaining = 1
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
        # P1 worn-independent character constants (SOL-ROADMAP-optimizer-purity
        # stage P1).  The constants are OBSERVED by the execution-layer
        # unequipped calibration phase and cached; the selector only consumes
        # them and never triggers the phase itself.
        self._character_calibration: CharacterCalibration | None = None
        self._character_calibration_path: Path | None = None
        self._character_calibration_loaded = False
        self._confirmed_loadout: ConfirmedLoadoutRecord | None = None
        self._confirmed_loadout_path: Path | None = None
        self._confirmed_loadout_loaded = False
        self._equipment_optimizer_input_key: str | None = None
        self._equipment_optimizer_knowledge_key: str | None = None
        # Calibration phase state machine: None | "deposit" | "strip" |
        # "capture" | "restore-equip" | "restore-supplies".
        self._calibration_phase: str | None = None
        # The observation phase to continue after an interruption has been
        # handled and the originally worn equipment has been restored.
        self._calibration_suspended_phase: str | None = None
        self._calibration_worn_before: tuple[tuple[str, str], ...] = ()
        self._calibration_restore_signatures: list[tuple[str, int, int]] = []
        self._calibration_restore_seen_pages: set[tuple[str, ...]] = set()
        self._calibration_session_target: str | None = None
        self._calibration_aborts_this_visit = 0
        self._calibration_blocked_this_visit = False
        self._calibration_last_abort: str | None = None
        self._calibration_entry_refusal: tuple[int, str | None] | None = None
        # True from the moment a calibration strip session is installed until
        # every recorded identity is observed worn again.  While set, town
        # departure is impossible: no
        # escape valve may let a calibration-stripped character dive naked.
        self._calibration_stripped_unrestored = False
        self._calibration_redress_loaded = False
        self._calibration_redress_attempts: dict[tuple[str, str], int] = {}
        self._calibration_redress_abandonment: str | None = None
        # Mutation observation (sorted ids) from `C` character snapshots: the
        # calibration phase's naked dump records it at capture, and the
        # pre-existing periodic status dump (cli DUMP_INTERVAL_SECONDS)
        # refreshes it autonomously during normal play — the observation-based
        # bound for the mutation invalidation trigger.
        self._mutation_signature: tuple[int, ...] | None = None
        # Naked `C` acquisition latches for the capture step.  prepared is set
        # when the macro is offered, converted to requested/inflight only by
        # confirm_key_posted (a suppressed or replaced key must not consume
        # the request); the response records _calibration_naked_flags.
        self._calibration_naked_dump_prepared = False
        self._calibration_naked_dump_requested = False
        self._calibration_naked_dump_inflight = False
        self._calibration_naked_flags: frozenset[int] | None = None
        self._equipment_transaction_session: EquipmentTransactionSession | None = None
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
        self._priority_body_rearm_attempted_ids: set[str] = set()
        self._equipment_transaction_last_failure: dict[str, object] | None = None
        self._equipment_transaction_prepared_key: str | None = None
        self._equipment_transaction_prepared_catalog_update: tuple[
            str, object, tuple[object, ...]
        ] | None = None
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
        self._calibration_home_rearm_eligible = False
        self._calibration_home_rearm_queue: tuple[tuple, ...] | None = None
        # Full-pack disposal verification: signatures of items the game would not
        # destroy (so we stop re-selecting them and forever looping), plus a watch
        # on the last attempt to detect that the pack did not change afterwards.
        self._undestroyable_sigs: set[tuple[str, int, int]] = set()
        self._destroy_watch: tuple[tuple[str, int, int], int, int] | None = None
        self._destroy_fail_streak = 0
        self.last_reason = ""
        self.prompt_owner_handoff: str | None = None

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

    def _refresh_town_facts(self, snapshot: Snapshot) -> None:
        """Incrementally retain store/building facts for this floor visit."""
        if snapshot is self._town_fact_snapshot:
            return
        self._town_fact_snapshot = snapshot
        in_town = getattr(snapshot, "in_town", False)
        if not in_town:
            self._town_visit_entrances.clear()
        region = self._grid_region(snapshot)
        if self._town_fact_region != region:
            self._town_fact_region = region
            self._town_store_positions = {}
            self._town_emitted_entrances = set()
            self._town_entrance_cache = None
            emitted = getattr(snapshot, "grids", {}).items()
        else:
            grids = getattr(snapshot, "grids", {})
            emitted = (
                (Position(y, x), grids[Position(y, x)])
                for y, x in self._emitted_t
                if Position(y, x) in grids
            )
        changed = False
        for position, grid in emitted:
            for positions in self._town_store_positions.values():
                if position in positions:
                    positions.discard(position)
                    changed = True
            if grid.store_number >= 0:
                self._town_store_positions.setdefault(grid.store_number, set()).add(position)
                changed = True
            was_entrance = position in self._town_emitted_entrances
            # Preserve 4f41982 exactly: older/synthetic GridState producers may
            # use None for a non-store even though current parsed snapshots use
            # -1. Entrance-cache work must not alter that routing predicate.
            is_entrance = grid.store_number is not None or grid.building_special >= 0
            if is_entrance:
                self._town_emitted_entrances.add(position)
            else:
                self._town_emitted_entrances.discard(position)
            if in_town and (
                grid.store_number >= 0
                or grid.building_special >= 0
                or grid.has_quest_enter
                or grid.has_quest_exit
            ):
                self._town_visit_entrances.add(position)
            changed = changed or was_entrance != is_entrance
        if changed:
            self._town_entrance_cache = None

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

    def choose_key(self, snapshot: Snapshot) -> str:
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
        )
        if not hasattr(self, "_town_supplier_stock"):
            self._town_supplier_stock = {}
        if not hasattr(self, "_town_supplier_stock_observations"):
            self._town_supplier_stock_observations = {}
        if not hasattr(self, "_town_visit_sale_signatures"):
            self._town_visit_sale_signatures = set()
        if not hasattr(self, "_calibration_entry_refusal"):
            self._calibration_entry_refusal = None
        if not hasattr(self, "_equipment_transaction_route_abandonment"):
            self._equipment_transaction_route_abandonment = None
        if not hasattr(self, "_equipment_transaction_route_terminal_pending"):
            self._equipment_transaction_route_terminal_pending = False
        if not hasattr(self, "_equipment_transaction_route_terminal"):
            self._equipment_transaction_route_terminal = None
        if not hasattr(self, "_home_gate_telemetry"):
            self._home_gate_telemetry = {}
        if not hasattr(self, "_home_procurement_withdraw_failure"):
            self._home_procurement_withdraw_failure = None
        if not hasattr(self, "_home_atomic_withdraw_procurement_class"):
            self._home_atomic_withdraw_procurement_class = None
        if not hasattr(self, "_home_latch_active"):
            self._home_latch_active = None
        if not hasattr(self, "_home_latch_history"):
            self._home_latch_history = []
        if not hasattr(self, "_equipment_fresh_search_target_ids"):
            self._equipment_fresh_search_target_ids = frozenset()
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
                )
                self.decision_attribution = arbiter.decision_owner_for_reason(
                    decided_reason
                )
                return key
        self._last_policy_progress_core = current_progress_core
        home_capture = self._home_entry_capture
        if home_capture is not None:
            key = home_capture.choose_key(self, snapshot)
        else:
            key = self._choose_key_with_latch_capture(snapshot)
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
        key = self._refuse_no_progress_cycle(snapshot, key)
        key = self._town_procurement_decision(snapshot, key)
        if (
            self._town_blocked_reason
            == "town:blocked:home-withdraw-failed-stock-present"
        ):
            key = WAIT_KEY
            self.last_reason = self._town_blocked_reason
        if self._withdrawal_unfulfilled_defect:
            self._record_shop_selector_diagnostics(snapshot, key)
        key = self._forbid_wait_while_damaged(snapshot, key)
        vector = self._town_arbiter_progress_vector(snapshot, self.last_reason)
        if (
            bool(snapshot.in_town or snapshot.store is not None)
            and not arbiter.may_select(self.last_reason, vector)
        ):
            retired_owner = arbiter.owner_for_reason(self.last_reason)
            self._arbiter_close_store_visit(retired_owner, "arbiter-retired-claim")
            supplier = self._departure_supplier_counterfactual(snapshot)
            step = (
                self._shopping_approach_step(snapshot, supplier)
                if (
                    supplier is not None
                    and snapshot.store is None
                    and retired_owner != "store-router"
                    and arbiter.may_select("shop:approach", vector)
                )
                else None
            )
            if step is not None:
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
        terminal = self._town_arbiter_terminal_result(key)
        arbiter.observe(
            in_town=bool(snapshot.in_town or snapshot.store is not None),
            reason=self.last_reason,
            progress_vector=vector,
            terminal=terminal,
            close_visit=self._arbiter_close_store_visit,
        )
        self.decision_attribution = arbiter.decision_owner_for_reason(self.last_reason)
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
            self._shopping_approach_goal = None
            self._town_travel_state = None
            self._town_travel_fallback = None
        return key

    def _town_arbiter_terminal_result(self, key: str) -> bool:
        """Classify visible stops without treating their emission as progress."""
        reason = self.last_reason or ""
        return key == WAIT_KEY and (
            reason.startswith("town:blocked:")
            or "terminal" in reason
            or reason.endswith(":unsatisfiable")
            or reason in {"policy:no-action", "stuck:wander"}
        )

    def _arbiter_close_store_visit(self, owner: str, outcome: str) -> None:
        """Close only a visit resource owned by the yielding token family."""
        visit = self._store_visit
        if visit is None:
            return
        aliases = {
            "store-router": {"store-router"},
            "shop-buy": {"shop-handler", "shop-one-shot"},
            "shop-sell": {"shop-handler", "shop-one-shot"},
            "home-visit": {"home-one-shot"},
            "equipment-txn": {"equipment-transaction"},
        }
        if visit.owner == owner or visit.owner in aliases.get(owner, set()):
            self._close_store_visit(outcome)

    def _store_visit_arbiter_owner(self, visit: StoreVisit) -> str:
        if (
            visit.owner in {"shop-handler", "shop-one-shot", "home-one-shot"}
            and not visit.operation_posted
            and visit.phase in {StoreVisitPhase.APPROACHING, StoreVisitPhase.ENTERING}
        ):
            return "store-router"
        aliases = {
            "shop-handler": "shop-buy",
            "shop-one-shot": "shop-buy",
            "home-one-shot": "home-visit",
            "equipment-transaction": "equipment-txn",
            "town-errand": "town-plan",
        }
        return aliases.get(visit.owner, visit.owner)

    def _town_arbiter_progress_vector(
        self, snapshot: Snapshot, reason: str | None = None
    ) -> tuple[object, ...]:
        """Read durable facts plus the registered locomotion owner's distance."""
        departure = getattr(self, "_departure_block", {}) or {}
        core = self._owner_progress_core(snapshot)
        durable_core = replace(
            core,
            position=Position(0, 0),
            turn=0,
            decision_sequence=0,
        )
        home_blocked = (
            STORE_HOME in self._town_visit_ledger.blocked_stores
            or STORE_HOME in self._town_visit_ledger.nonhome_attempted_without_effect
            or self._store_entry_failed_owner == STORE_HOME
        )
        durable = (
            durable_core,
            self._town_progress_fingerprint(snapshot),
            tuple(sorted((str(key), repr(value)) for key, value in departure.items())),
            bool(self._home_knowledge_current),
            bool(home_blocked),
            getattr(self, "_town_blocked_reason", None),
            getattr(self, "_descent_refusal_reason", None),
            bool(getattr(self, "_descent_blocked", False)),
        )
        arbiter = getattr(self, "_town_turn_arbiter", None)
        owner = (
            arbiter.owner_for_reason(reason or self.last_reason)
            if arbiter is not None
            else "unregistered"
        )
        goal: Position | None = None
        if owner == "store-router" or (
            owner == "equipment-txn"
            and (reason or self.last_reason) == "equipment-transaction:approach-home"
        ):
            goal = self._shopping_approach_goal
        elif owner == "departure":
            goal = self._descent_target_goal
            if goal is None:
                upward = (reason or self.last_reason or "").startswith(
                    ("return:", "recall", "town:recall")
                )
                candidates = (
                    self._remembered_upstairs if upward
                    else self._remembered_downstairs
                )
                if candidates:
                    goal = min(
                        candidates,
                        key=lambda pos: snapshot.player.position.distance_to(pos),
                    )
                elif snapshot.in_town and self._town_map_active(snapshot):
                    goal = self._town_map_descent_entrance(snapshot)
        elif owner == "quest-request" and "approach" in (reason or self.last_reason or ""):
            quest_id = self._fixed_quest_target(snapshot)
            if quest_id is not None:
                positions = self._fixed_quest_entrance_positions(snapshot, quest_id)
                if not positions:
                    positions = self._fixed_quest_building_positions(snapshot, quest_id)
                if positions:
                    goal = min(
                        positions,
                        key=lambda pos: snapshot.player.position.distance_to(pos),
                    )
            if goal is None and self._town_map_active(snapshot):
                positions = tuple(
                    position
                    for entries in self._town_map.quest_entrances.values()
                    for position in entries
                )
                if positions:
                    goal = min(
                        positions,
                        key=lambda pos: snapshot.player.position.distance_to(pos),
                    )
        elif owner == "misc" and (reason or self.last_reason or "").startswith("explore"):
            # Deliberate G1 explorer position-as-progress exception: the restored open-town explorer pin requires it.
            path = getattr(self, "_explore_path", None)
            if path:
                goal = path[-1]
            else:
                identity = getattr(self, "_explore_goal_identity", None)
                if identity is not None:
                    goal = identity.position
                else:
                    pending = getattr(self, "_pending_one_step_explore", None)
                    if pending is not None:
                        goal = pending[1]
        if goal is None:
            return durable
        if owner == "misc":
            return durable + (
                ("locomotion", owner, snapshot.floor_key, snapshot.player.position),
            )
        distance = (
            abs(snapshot.player.position.y - goal.y)
            + abs(snapshot.player.position.x - goal.x)
        )
        return durable + (("locomotion", owner, snapshot.floor_key, distance),)

    # Closed list: additions are policy changes and require a dedicated pin.
    TOWN_PROGRESS_ALLOW_SET = frozenset({
        "emergency-lethal-danger",
        "weak-fainting-survival-absorb",
        "recall-entry-invariant",
        "nearby-threat-defer",
        "reserve-already-satisfied",
    })

    def _town_result_makes_progress(self, snapshot: Snapshot, key: str) -> bool:
        """Positively classify a town result by its effect, never its label."""
        if (
            key == LEAVE_STORE_KEY
            and (self.last_reason or "").startswith("home-errand:filed:")
        ):
            return True
        if (
            key == LEAVE_STORE_KEY
            and snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._home_entry_operation_posted
        ):
            return True
        if (
            self._home_entry_operation_posted
            and key not in {"", WAIT_KEY, LEAVE_STORE_KEY}
        ):
            return True
        if (
            self._store_visit is not None
            and self._store_visit.operation_posted
            and (self.last_reason or "").startswith("shop:one-shot-")
        ):
            # Outside composition intentionally returns WAIT while the bound
            # purchase tail waits for the re-entered store page.  The posted
            # operation, not the transport key, is the progress effect.
            return True
        if key in {"", WAIT_KEY, LEAVE_STORE_KEY}:
            if key == WAIT_KEY and (self.last_reason or "").startswith(
                "equipment-transaction:"
            ):
                fingerprint = self._town_progress_fingerprint(snapshot)
                if fingerprint in self._town_progress_history():
                    self._town_progress_invariant_defect = {
                        "marker": "TOWN_OSCILLATION_DEFECT",
                        "winning_rung": self.last_reason or "",
                        "repeated_fingerprint": repr(fingerprint),
                        "gold": snapshot.player.gold,
                    }
                    self._record_shop_selector_diagnostics(snapshot, key)
            return False
        if key and key.startswith((BUY_KEY, SELL_KEY, "{")):
            # Store purchase/sale and inscription producers have closed command
            # prefixes and directly mutate gold or inventory.
            return True
        if key and key.startswith("~") and (self.last_reason or "").startswith(
            "home:request-knowledge-scan"
        ):
            return True
        direction = next(
            (delta for delta, direction_key in DIRECTION_KEYS.items()
             if direction_key == key),
            None,
        )
        if direction is not None and (self.last_reason or "").endswith("home:scan-step-off") and not self._equipment_catalog.home_scan_complete:
            return True
        goal = self._shopping_approach_goal
        if direction is not None:
            if goal is not None:
                before = snapshot.player.position.distance_to(goal)
                after = Position(
                    snapshot.player.position.y + direction[0],
                    snapshot.player.position.x + direction[1],
                ).distance_to(goal)
                if after < before:
                    return True
            fingerprint = self._town_progress_fingerprint(snapshot)
            if fingerprint in self._town_progress_history():
                # Movement without a closer claim goal revisits the same town
                # goal state even when it reaches a fresh map position.
                return False
            # Town movement is not goal progress.  Only an approach with a
            # measured supplier/landmark goal or an established reachable
            # movement owner can advance a live claim.  Wander and breakout
            # labels are deliberately absent from this town-only contract.
            reason = self.last_reason or ""
            return (
                reason in TOWN_CLAIM_ADVANCING_MOVE_REASONS
                or "step-off" in reason
                or reason.startswith("shop:")
                or reason.startswith(
                    "town-progress-invariant:boxed-breakout-travel"
                )
            )
        # Keep this positive and closed.  Native store travel and dungeon entry
        # have explicit contracts that advance position/depth; an unknown macro
        # is not progress merely because it contains command characters.
        store_type = self._shopping_approach_store_type
        if (
            goal is not None
            and store_type is not None
            and 0 <= store_type < len(TOWN_TRAVEL_STORE_SYMBOLS)
            and key == f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[store_type]}."
        ):
            return True
        if key in {DOWN_STAIRS_KEY, ENTER_DUNGEON_MACRO}:
            return True
        if key not in {RESTOCK_WAIT_MACRO, "l", "s", "\x1b\x1b"}:
            # At this point direction, WAIT, leave, and the closed noop-macro
            # axis have all been rejected.  Remaining policy command macros
            # are inventory/equipment/Home actions that mutate goal state.
            # Their command shape alone is not evidence of progress: a
            # completed takeoff/restore cycle returns to the same measured
            # state even though every individual macro looked mutating.
            fingerprint = self._town_progress_fingerprint(snapshot)
            if fingerprint in self._town_progress_history():
                self._town_progress_invariant_defect = {
                    "marker": "TOWN_OSCILLATION_DEFECT",
                    "winning_rung": self.last_reason or "",
                    "repeated_fingerprint": repr(fingerprint),
                    "gold": snapshot.player.gold,
                }
                self._record_shop_selector_diagnostics(snapshot, key)
                return False
            return True
        return False

    def _town_progress_fingerprint(self, snapshot: Snapshot) -> tuple[object, ...]:
        """Measured town progress fields used by the result arbitration seam."""
        return (
            snapshot.floor_key,
            snapshot.player.gold,
            snapshot.player.food_state,
            snapshot.player.food_type,
            snapshot.player.exp,
            snapshot.dungeon_level,
            tuple(sorted(
                (self._town_progress_item_state(item) for item in snapshot.inventory),
                key=repr,
            )),
            tuple(sorted(
                (self._town_progress_item_state(item) for item in snapshot.equipment),
                key=repr,
            )),
            tuple(getattr(self._town_errand_plan, "completed_this_visit", ()) or ()),
            tuple(getattr(self._town_errand_plan, "blocked_this_visit", ()) or ()),
            self._equipment_catalog.home_scan_complete,
            self._home_knowledge_current,
            self._home_pending_item,
            tuple(self._home_pending_batch),
            self._home_atomic_withdraw_pending,
            self._home_atomic_deposit_pending,
            tuple(getattr(self._equipment_optimization_preparation, "blockers", ())),
            self._equipment_transaction_session is not None,
            tuple(sorted(self._equipment_transaction_failed_items)),
        )

    def _town_progress_history(self) -> deque[tuple[object, ...]]:
        """Return the window, lazily upgrading restored pre-R6 policies."""
        history = getattr(self, "_town_progress_fingerprint_history", None)
        if history is None:
            history = deque(maxlen=TOWN_CYCLE_WINDOW)
            self._town_progress_fingerprint_history = history
        return history

    def _town_begin_progress_decision(self, snapshot: Snapshot) -> None:
        """Move the prior decision into the window, leaving current state fresh."""
        history = self._town_progress_history()
        if not snapshot.in_town:
            history.clear()
            self._town_progress_last_fingerprint = None
            return
        previous = getattr(self, "_town_progress_last_fingerprint", None)
        if previous is not None:
            history.append(previous)
        self._town_progress_last_fingerprint = self._town_progress_fingerprint(snapshot)

    def _town_progress_allow_members(self, snapshot: Snapshot) -> frozenset[str]:
        """Return only members of the reviewed procurement preemptor set."""
        reason = self.last_reason or ""
        allowed: set[str] = set()
        if reason.startswith(("emergency:", "unseen-recall:", "guardian:")):
            allowed.add("emergency-lethal-danger")
        if reason in {
            "survival:mana-absorb", "town:eat-before-travel", "survival:eat"
        } and snapshot.player.food_state in {"weak", "fainting"}:
            allowed.add("weak-fainting-survival-absorb")
        if reason.startswith(("town:repetition-depart", "recall-entry:")):
            allowed.add("recall-entry-invariant")
        if any(
            monster.distance <= 4
            for monster in getattr(snapshot, "visible_monsters", ())
        ):
            allowed.add("nearby-threat-defer")

        observation = self._shop_observation
        if observation is not None:
            observed = replace(snapshot, store=observation[0])
            wanted = self._next_purchase_unreserved(observed)
            if wanted is not None:
                quantity = self._purchase_quantity(observed, wanted)
                reserve = self._fundraising_kit_reserve(observed)
                if (
                    reserve > 0
                    and snapshot.player.gold - wanted.price * quantity < reserve
                ):
                    allowed.add("reserve-already-satisfied")
        assert allowed <= self.TOWN_PROGRESS_ALLOW_SET
        return frozenset(allowed)

    def _town_procurement_progress_key(
        self, snapshot: Snapshot
    ) -> tuple[str, str] | None:
        """Compose the next step of an available approach->enter->buy route."""
        home_scan_pending = (
            not self._equipment_catalog.home_scan_complete
            and self._home_available_for_probe(snapshot)
            and (
                "home-scan-incomplete" in getattr(
                    self._equipment_optimization_preparation, "blockers", ()
                )
                or (snapshot.player.food_type == FOOD_TYPE_MANA and snapshot.player.hungry)
            )
        )
        here = snapshot.grid_at(snapshot.player.position)
        if (
            home_scan_pending
            and snapshot.store is None
            and here is not None
            and here.store_number >= 0
            and self._store_leave_inflight is None
            and self._store_entry_posted_owner is None
            and self._store_entry_wait_owner is None
        ):
            reason = "home:scan-step-off"
            key = self._town_entrance_step_off_key(snapshot, reason)
            return key, self.last_reason or reason

        # An observed ordinary-shop shelf is paired with current gold at this
        # boundary.  It is the strongest counterfactual and composes first.
        transaction = self._atomic_shop_transaction_key(snapshot)
        if transaction is not None:
            return transaction, self.last_reason

        # A21 remains Home-first.  Calling its established producer here makes
        # the A26 generic-food route unable to preempt a MANA acquisition.
        if snapshot.player.food_type == FOOD_TYPE_MANA and snapshot.player.hungry:
            mana = self._mana_food_survival_override_key(snapshot)
            if mana is not None and self._town_result_makes_progress(snapshot, mana):
                return mana, self.last_reason

        # A27 bookkeeping belongs to candidate availability: stale terminal
        # ownership and an inert visit cannot make a released supplier appear
        # unreachable.  Posted operations remain authoritative.
        if self._town_blocked_reason in {
            "restock-store-unreachable",
        }:
            self._town_blocked_reason = None
            visit = self._store_visit
            if visit is not None and not visit.operation_posted:
                self._close_store_visit("town-progress-invariant-reroute")

        supplier = None
        for store_type, known_stock in getattr(
            self, "_town_supplier_stock", {}
        ).items():
            if store_type == STORE_HOME:
                continue
            stock_snapshot = replace(snapshot, store=known_stock)
            wanted = self._next_purchase_unreserved(stock_snapshot)
            if (
                wanted is None
                or not self._town_blocked_purchase_is_composable(stock_snapshot)
            ):
                continue
            quantity = self._purchase_quantity(stock_snapshot, wanted)
            reserve = self._fundraising_kit_reserve(stock_snapshot)
            if snapshot.player.gold - wanted.price * quantity >= reserve:
                supplier = store_type
                break
        if supplier is None:
            return None
        step = self._shopping_approach_step(snapshot, supplier)
        if step is None:
            return None
        reason = "town-progress-invariant:approach"
        key = self._shopping_approach_key(snapshot, step, reason)
        return key, self.last_reason or reason

    def _town_observed_purchase_is_composable(self, snapshot: Snapshot) -> bool:
        """Whether this ordinary-store page can fund a wanted purchase now."""
        if snapshot.store is None or snapshot.store.store_type == STORE_HOME:
            return False
        wanted = self._next_purchase_unreserved(snapshot)
        if wanted is None:
            return False
        quantity = self._purchase_quantity(snapshot, wanted)
        reserve = self._fundraising_kit_reserve(snapshot)
        return snapshot.player.gold - wanted.price * quantity >= reserve

    def _town_blocked_purchase_is_composable(self, snapshot: Snapshot) -> bool:
        """Whether the blocked store handler will stage its selected purchase."""
        store = snapshot.store
        if store is None or store.store_type == STORE_HOME:
            return False
        attempted_at = self._town_store_attempted.pop(store.store_type, None)
        try:
            departure_families = {
                need.category.split(":", 1)[0]
                for need in self._departure_blocking_town_needs(snapshot)
                if need.store_type == store.store_type
            }
        finally:
            if attempted_at is not None:
                self._set_town_store_attempted(store.store_type, attempted_at, "shop-exit-attempt")
        purchase = self._next_purchase(snapshot)
        purchase_families = {
            category.split(":", 1)[0]
            for category in (
                self._cross_town_item_categories(purchase)
                if purchase is not None
                else ()
            )
        }
        family_aliases = {
            "fundraising-oil": "oil",
            "fundraising-light": "light",
            "mining-digger": "digger",
        }
        departure_families = {
            family_aliases.get(family, family) for family in departure_families
        }
        purchase_families = {
            family_aliases.get(family, family) for family in purchase_families
        }
        if departure_families:
            return bool(departure_families.intersection(purchase_families))
        return purchase is not None and purchase.tval in {TVAL_WAND, TVAL_STAFF}

    def _town_procurement_decision(
        self, snapshot: Snapshot, key: str, *, enforce: bool = True
    ) -> str:
        """Enforce composable progress at the one downstream town-result seam."""
        proposed_reason = self.last_reason or ""
        self._town_begin_progress_decision(snapshot)
        result_makes_progress = self._town_result_makes_progress(snapshot, key)
        if not snapshot.in_town or result_makes_progress:
            return key
        claims_active = self._town_claims_active(snapshot)
        movement_key = key in DIRECTION_KEYS.values()
        allow_members = self._town_progress_allow_members(snapshot)
        if allow_members:
            return key

        # Durable session ownership survives reason relabelling and blockers.
        if self._equipment_transaction_owns_town_relocation(snapshot):
            return key

        # The outside half of an already-posted Home take owns the decision
        # until inventory confirms it or its existing confirmation bound
        # expires.  A posted shop visit must not relabel that await as a buy.
        if (
            proposed_reason == "home:atomic-withdraw-await-confirmation"
            and self._home_atomic_withdraw_pending is not None
        ):
            return key
        if proposed_reason == "breakout:least-visited":
            self._boxed_town_breakout_key(snapshot)
            committed = self._commit_boxed_town_breakout_key(snapshot)
            if committed is not None:
                self.last_reason = "town-progress-invariant:boxed-breakout-travel"
                return committed

        # Observing a wanted, affordable shelf is the entry phase of the
        # existing atomic contract.  Leaving is only its transport step: it is
        # a defect until the saved page is composed on the adjacent outside
        # snapshot.  A non-supplier store may still be left normally so the
        # router can advance toward another supplier.
        if proposed_reason == "shop:observe-and-leave":
            if not self._town_observed_purchase_is_composable(snapshot):
                return key
            self.last_reason = "town-progress-invariant:continue-observed-shop"
            self._town_progress_invariant_defect = {
                "marker": "TOWN_PROGRESS_INVARIANT_DEFECT",
                "winning_rung": proposed_reason,
                "progress_action": self.last_reason,
                "gold": snapshot.player.gold,
                "allow_set": (),
            }
            self._record_shop_selector_diagnostics(snapshot, key)
            return key

        visit = self._store_visit
        if visit is not None and visit.operation_posted:
            if visit.store_type == STORE_HOME:
                return key
            progress_reason = "shop:one-shot-buy"
            self._town_progress_invariant_defect = {
                "marker": "TOWN_PROGRESS_INVARIANT_DEFECT",
                "winning_rung": proposed_reason,
                "progress_action": progress_reason,
                "gold": snapshot.player.gold,
                "allow_set": (),
            }
            if enforce:
                self.last_reason = (
                    "town-progress-invariant:defect:"
                    f"{proposed_reason}=>{progress_reason}"
                )
            return key

        progress = self._town_procurement_progress_key(snapshot)
        if progress is None:
            liveness_candidate = (
                proposed_reason == "stuck:wander"
                or proposed_reason.startswith("novel:")
            )
            if enforce and movement_key and liveness_candidate and (
                claims_active or getattr(self, "_town_liveness_claim_retired", False)
            ):
                blocked_reason = (
                    "retired-equipment-transaction-failed"
                    if getattr(self, "_town_liveness_claim_retired", False)
                    else "no-actionable-claim-owner"
                )
                self.last_reason = f"town:blocked:{blocked_reason}"
                self._town_liveness_invariant_defect = {
                    "marker": "TOWN_LIVENESS_INVARIANT_DEFECT",
                    "winning_rung": proposed_reason,
                    "resolution": self.last_reason,
                    "claim_retired": getattr(
                        self, "_town_liveness_claim_retired", False
                    ),
                }
                self._town_progress_invariant_defect = dict(
                    self._town_liveness_invariant_defect
                )
                self._record_shop_selector_diagnostics(snapshot, WAIT_KEY)
                return WAIT_KEY
            self.last_reason = proposed_reason
            return key
        progress_key, progress_reason = progress
        if progress_key == key and progress_reason == proposed_reason:
            self.last_reason = proposed_reason
            return key
        if not self._town_result_makes_progress(snapshot, progress_key):
            self.last_reason = proposed_reason
            return key
        self._town_progress_invariant_defect = {
            "marker": "TOWN_PROGRESS_INVARIANT_DEFECT",
            "winning_rung": proposed_reason,
            "progress_action": progress_reason,
            "gold": snapshot.player.gold,
            "allow_set": (),
        }
        if not enforce:
            self.last_reason = proposed_reason
            return key
        self.last_reason = (
            f"town-progress-invariant:defect:{proposed_reason}=>{progress_reason}"
        )
        self._record_shop_selector_diagnostics(snapshot, progress_key)
        return progress_key


    def _boxed_town_breakout_key(self, snapshot: Snapshot) -> str | None:
        """Probe a distinct-landmark escape without opening a store visit."""
        route = self._boxed_town_breakout_route(snapshot)
        if route is None:
            here = snapshot.grid_at(snapshot.player.position)
            return WAIT_KEY if here is not None and here.store_number >= 0 else None
        store_type, goal, step = route
        if (
            self._has_light_equipped(snapshot)
            and goal in snapshot.grids
            and snapshot.player.position.distance_to(goal) >= TOWN_TRAVEL_MIN_DISTANCE
            and self._town_travel_fallback != goal
        ):
            return f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[store_type]}."
        return self._direction_key(snapshot.player.position, step)

    def _boxed_town_breakout_route(
        self, snapshot: Snapshot
    ) -> tuple[int, Position, Position] | None:
        """Return the first visible alternate-store route using derived map facts only."""
        here = snapshot.grid_at(snapshot.player.position)
        current_store = here.store_number if here is not None else -1
        for store_type in (STORE_HOME, STORE_MAGIC, STORE_ALCHEMIST, STORE_GENERAL):
            if store_type == current_store:
                continue
            route = self._nearest_goal_and_step(
                snapshot, lambda grid, wanted=store_type: grid.store_number == wanted
            )
            if route is None and self._town_map_active(snapshot):
                goal = self._town_map.store_position(store_type)
                step = self._town_map_goal_step(snapshot, goal)
                route = (goal, step) if step is not None else None
            if route is None:
                visible_goals = [
                    grid.position
                    for grid in snapshot.grids.values()
                    if grid.store_number == store_type
                ]
                if visible_goals:
                    goal = min(
                        visible_goals,
                        key=lambda pos: snapshot.player.position.distance_to(pos),
                    )
                    if (
                        snapshot.player.position.distance_to(goal)
                        >= TOWN_TRAVEL_MIN_DISTANCE
                    ):
                        route = (goal, goal)
            if route is None:
                continue
            goal, step = route
            if step != snapshot.player.position:
                return store_type, goal, step
        return None

    def _commit_boxed_town_breakout_key(self, snapshot: Snapshot) -> str | None:
        """Open and compose the store visit only after the breakout probe wins."""
        here = snapshot.grid_at(snapshot.player.position)
        current_store = here.store_number if here is not None else -1
        for store_type in (STORE_HOME, STORE_MAGIC, STORE_ALCHEMIST, STORE_GENERAL):
            if store_type == current_store:
                continue
            step = self._shopping_approach_step(snapshot, store_type)
            if step is None:
                continue
            key = self._shopping_approach_key(
                snapshot, step, "town-progress-invariant:boxed-breakout-travel"
            )
            if key not in {"", WAIT_KEY}:
                return key
        return None











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

    def _choose_key(self, snapshot: Snapshot) -> str:
        self._read_binding = None
        self.read_telemetry = {}
        self._store_entry_wait_owner = None
        self._store_entry_wait_key = None
        self._store_entry_failed_owner = None
        self._decision_sequence += 1
        self._equipment_departure_cache_token = None
        self._escape_state.begin_decision(snapshot, self._decision_sequence)
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
        if posted_entry_owner is not None:
            observed_failed_entry = snapshot.store is None and any(
                "The doors are locked." in message
                or "ドアに鍵がかかっている" in message
                for message in snapshot.messages
            )
            # Failure requires positive message evidence; a lagged store=None
            # is not evidence.  Termination is nevertheless total: both
            # branches discharge the one-shot owner in this decision.  The
            # refusal branch lets routing step off below; the in-flight branch
            # returns an empty, unsent decision now and normal routing owns the
            # next snapshot.  Neither branch retains a wait or emits a filler.
            self._store_entry_posted_owner = None
            if observed_failed_entry:
                self._store_entry_failed_owner = posted_entry_owner
            else:
                state = self._town_travel_state
                if (
                    state is not None
                    and (self._store_entry_wait_key or "").startswith("\x1b`")
                    and state.last_turn == snapshot.turn
                    and snapshot.player.position.distance_to(state.goal)
                    >= state.best_distance
                ):
                    # Native travel emits no player-turn snapshot while it is
                    # running.  An unchanged snapshot after this posted macro
                    # therefore arrives only after the CLI's Escape recovered
                    # a selector/command that made no progress.  Fail over now;
                    # reissuing the same symbol can only repeat that modal wait.
                    self._town_travel_fallback = state.goal
                    self._town_travel_state = None
                if self._store_visit is not None:
                    self._store_visit.transition(StoreVisitPhase.APPROACHING)
                self.last_reason = "store:entry-await-observation"
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
            after_count = self._inventory_signature_count(snapshot, signature)
            if getattr(self, "_home_visit", None) is not None:
                self._home_visit.observe_outside(
                    effect_observed=after_count >= before_count + quantity
                )
            if (
                self._home_errand.request is not None
                and self._home_errand.request.signature == signature
            ):
                self._home_errand.observe_outside(after_count)
            self._home_atomic_withdraw_pending = None
            self._home_atomic_withdraw_procurement_class = None
            self._home_atomic_withdraw_posted_turn = None
            self._home_entry_operation_posted = False
            if after_count >= before_count + quantity:
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
                if self._calibration_restore_signatures:
                    # Each successful one-shot take is fresh progress and the
                    # remaining physical slots are a new Home operation, not a
                    # repeated failed need.  Release the per-stop ledger so a
                    # multi-item restore cannot abandon its tail.
                    self._rearm_town_store_for_new_work(
                        STORE_HOME, release_visit_bound=True
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
        # Shop one-shots complete (or become retryable) only from the following
        # outside inventory/gold observation.  No in-store confirmation phase
        # owns a key.
        if (
            snapshot.store is None
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
                self._town_visit_purchases.add(watched_signature)
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
            snapshot.store is None
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
            if confirmed or wait_count + 1 >= STORE_STUCK_LIMIT:
                pending_store = int(pending["store_type"])
                self._batch_sell_key(
                    replace(snapshot, store=StoreState(pending_store, []))
                )
            else:
                pending["wait_count"] = wait_count + 1
        self._refresh_carried_equipment_catalog(snapshot)
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            fresh_home_entry = not self._last_snapshot_was_store
            if fresh_home_entry:
                # A fresh page is positive reachability evidence independent
                # of the later leave which may raise Home's T3 latch. Arm it
                # only for a restore queue not previously seen at a fresh
                # entry.  During restore-supplies the queue is monotonically
                # non-increasing, so distinct queue signatures (and therefore
                # releases) are bounded by its initial cardinality.  A leave
                # cannot change the queue or manufacture another entry edge.
                restore_queue = tuple(self._calibration_restore_signatures)
                if (
                    self._calibration_phase == "restore-supplies"
                    and restore_queue
                    and restore_queue != self._calibration_home_rearm_queue
                ):
                    self._calibration_home_rearm_eligible = True
                    self._calibration_home_rearm_queue = restore_queue
                self._home_knowledge_scan_requested = False
                self._home_knowledge_scan_inflight = False
                self._home_knowledge_scan_retries_remaining = 1
                self._home_knowledge_scan_leave_turn = None
        if self._equipment_transaction_session is not None:
            session = self._equipment_transaction_session
            pending = session.pending_action
            advanced = session.observe(observe_equipment_transactions(snapshot))
            if advanced and pending is not None:
                if (
                    pending.kind == "takeoff"
                    and pending.target_slot is not None
                    and not self._calibration_session_owned()
                ):
                    self._equipment_transaction_owned_items.append(
                        (pending.item_identity, pending.target_slot)
                    )
                elif pending.kind in {"equip", "reposition"}:
                    self._release_equipment_transaction_owned_item(
                        pending.item_identity
                    )
                elif pending.kind == "deposit":
                    self._release_equipment_transaction_owned_item(
                        pending.item_identity
                    )
            if self._equipment_transaction_session.complete:
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
        self._calibration_observe(snapshot)
        self._observe(snapshot, observation=latest_snapshot)
        self._nav_ledger.begin_decision()
        self.escape_ladder_telemetry = None
        self.town_teleport_refusal = None
        self._fruitless_disengage_spent_this_decision = False
        if self._home_errand.state == HomeErrandState.STOPPED:
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
            and self._store_leave_inflight is None
            and self._store_entry_posted_owner is None
        ):
            if self._home_errand.needs_knowledge:
                self.last_reason = self._home_errand.reason("request-knowledge")
            else:
                self.last_reason = "home:request-knowledge-scan"
            return "~9\x1b\x1b"
        if self._home_knowledge_scan_inflight:
            # An ordinary board snapshot after the request means the response
            # did not arrive (the CLI's bounded prompt recovery has returned to
            # the command loop). Permit one more posted request during this
            # Home visit, then let the existing page scan proceed unchanged.
            self._home_knowledge_scan_inflight = False
            if self._home_knowledge_scan_retries_remaining:
                self._home_knowledge_scan_retries_remaining -= 1
                self._home_knowledge_scan_requested = False
            else:
                self._home_errand.observe_scan_refused(
                    "knowledge-response-missing"
                )
        leaving_home = (
            self._store_leave_inflight is not None
            and self._store_leave_inflight[2] == STORE_HOME
        )
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
            signature, count_before, posted_turn, unchanged_pages = pending_deposit
            if snapshot.turn > posted_turn:
                deposit_observed = (
                    self._inventory_signature_count(snapshot, signature)
                    < count_before
                )
                if deposit_observed:
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
                    self._home_atomic_deposit_pending = None
                    self._home_rejected_deposits.add(signature)
                    self.last_reason = "home:deposit-unobserved-rescan"
                else:
                    self._home_atomic_deposit_pending = (
                        signature, count_before, posted_turn, unchanged_pages + 1
                    )
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
        pending_home_transaction = (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._equipment_transaction_session is not None
            and self._equipment_transaction_session.pending_action is not None
            and not self._home_entry_operation_posted
            and self._store_leave_inflight is None
        )
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
            )
        elif snapshot.store is not None and self._store_visit is None:
            self._store_visit = StoreVisit(
                owner="shop-handler", purpose="recovered-shopping",
                store_type=snapshot.store.store_type,
                phase=StoreVisitPhase.OPERATING,
                visit_origin="shop-handler-recovery",
                opened_sequence=self._decision_sequence,
            )
        unintended_store_context = (
            snapshot.store is not None and self._store_visit is None
        )
        if unintended_store_context:
            if (
                snapshot.store.store_type == STORE_HOME
                and self._home_knowledge_current
                and self._home_scan_item_count == 0
                and self._home_atomic_deposit_pending is None
                and not self._calibration_active()
                and self._equipment_transaction_session is None
            ):
                self._report_town_stop_pass(
                    snapshot, STORE_HOME, goal_satisfied=True,
                )
                self.last_reason = "town:blocked:home-known-empty-withdrawal"
            else:
                self.last_reason = (
                    "home:store-context-exit"
                    if snapshot.store.store_type == STORE_HOME
                    else "shop:store-context-exit"
                )
            key = LEAVE_STORE_KEY
        elif (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and (
                staged_home_operation :=
                self._release_staged_store_operation(snapshot)
            )
            is not None
        ):
            # Home has an earlier store-context owner than ordinary shops.
            # Release through the same StoreVisit fields at that seam so its
            # legacy leave-after-one-operation branch cannot steal the fresh
            # page that authorizes this two-stage tail.
            key = staged_home_operation
            self.last_reason = (
                "home:atomic-withdraw"
                if key.lstrip().startswith(BUY_KEY)
                else "home:atomic-deposit"
            )
        elif pending_home_transaction:
            # Observation above already accounts for the posted action.  This
            # narrow path may only confirm/expire it; it cannot select or post
            # another Home item operation.
            key = self._equipment_transaction_home_key(snapshot)
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
            key = self._equipment_transaction_home_key(snapshot)
        elif (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and self._home_entry_operation_posted
        ):
            # The combined command already completed this entry's sole input
            # operation.  Leave immediately; confirmation comes from the next
            # ordinary outside snapshot, never from waiting or retrying inside.
            self.last_reason = "home:leave-after-one-operation"
            key = LEAVE_STORE_KEY
        elif self._store_leave_inflight is not None:
            leave_generation, leave_turn, leave_store = self._store_leave_inflight
            if snapshot.store is None:
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
                    key = self._atomic_shop_transaction_key(snapshot)
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
                        self._home_knowledge_current
                        and self._home_scan_item_count == 0
                        and self._home_atomic_deposit_pending is None
                        and not self._calibration_active()
                        and self._equipment_transaction_session is None
                    ):
                        self._report_town_stop_pass(
                            snapshot, STORE_HOME, goal_satisfied=True,
                        )
                        self.last_reason = "town:blocked:home-known-empty-withdrawal"
                    else:
                        self.last_reason = "home:store-context-exit"
                    key = LEAVE_STORE_KEY
                else:
                    key = self._decide(snapshot)
            elif (
                self._decision_sequence <= leave_generation
                or getattr(snapshot, "turn", 0) < leave_turn
            ):
                self.last_reason = "shop:await-leave-generation"
                key = "\r"
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
            rearm = self._home_rearm_key(snapshot)
            if rearm is not None:
                key = rearm
            elif (
                not self._calibration_active()
                and self._home_atomic_deposit_pending is None
                and self._equipment_transaction_session is None
                and (
                    standing_digger := self._queue_standing_home_digger(snapshot)
                ) is not None
            ):
                # The open page is authoritative Home-stock evidence even when
                # entry ownership was recovered after a restart or lagged post.
                # Selection is bound here; the outside decision composes it.
                key = standing_digger
            elif (
                self._home_knowledge_current
                and self._home_scan_item_count == 0
                and self._home_atomic_deposit_pending is None
                and not self._calibration_active()
                and self._equipment_transaction_session is None
            ):
                self._report_town_stop_pass(
                    snapshot, STORE_HOME, goal_satisfied=True,
                )
                self.last_reason = "town:blocked:home-known-empty-withdrawal"
                key = LEAVE_STORE_KEY
            elif (
                not self._calibration_active()
                and self._home_atomic_deposit_pending is None
                and self._equipment_transaction_session is None
                and self._open_home_page_is_complete(snapshot)
                and (
                    not self._equipment_catalog.home_scan_complete
                    or not self._home_knowledge_current
                    or self._home_knowledge_invalidated
                )
            ):
                self.consume_home_knowledge(tuple(
                    self._inventory_item_from_store_item(item)
                    for item in snapshot.store.items
                ))
                self._home_scan_source = "observed-home-page"
                self.last_reason = "home:scan-complete-from-open-page"
                key = LEAVE_STORE_KEY
            elif (
                not self._calibration_active()
                and self._home_atomic_deposit_pending is None
                and self._equipment_transaction_session is None
                and (
                    pending_withdrawals := {
                        *(
                            (self._home_pending_item,)
                            if self._home_pending_item is not None
                            else ()
                        ),
                        *self._home_pending_batch,
                        *(
                            (self._home_atomic_withdraw_pending[0],)
                            if self._home_atomic_withdraw_pending is not None
                            else ()
                        ),
                    }
                )
                and pending_withdrawals.intersection(
                    {
                        self._item_signature(item)
                        for item in (
                            snapshot.store.items
                            if self._open_home_page_is_complete(snapshot)
                            else (
                                *snapshot.store.items,
                                *self._home_knowledge_items,
                            )
                        )
                    }
                )
            ):
                # Ordinary withdrawals are composed only from the adjacent
                # outside snapshot.  This hand-off is not a failed stop pass.
                self._shopping_approach_store_type = STORE_HOME
                self.last_reason = "home:leave-for-pending-withdraw"
                key = LEAVE_STORE_KEY
            elif (
                not self._calibration_active()
                and self._home_atomic_deposit_pending is None
                and self._equipment_transaction_session is None
                and (
                    not self._equipment_catalog.home_scan_complete
                    or not self._home_knowledge_current
                    or self._home_knowledge_invalidated
                )
            ):
                # A visible page of a multi-page (or metadata-poor) Home is
                # useful evidence, but it cannot replace the complete ~9 list.
                # Leave without latching the Home stop so the scan can continue.
                self.last_reason = "home:scan-incomplete-open-page"
                key = LEAVE_STORE_KEY
            elif (
                not self._calibration_active()
                and self._home_atomic_deposit_pending is None
                and self._equipment_transaction_session is None
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
            else:
                self.last_reason = "home:store-context-exit"
                self._post_owner_expectation(
                    snapshot, self.last_reason, "store_type"
                )
                key = LEAVE_STORE_KEY
        else:
            key = self._decide(snapshot)
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and not self._home_entry_operation_posted
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
        self._remember_swarm_distances(snapshot)
        key = self._flee_sustain_key(snapshot, key)
        key = self._periodic_game_save_key(snapshot, key)
        key = self._periodic_character_dump_key(snapshot, key)
        if key is None:
            if snapshot.store is not None:
                self.last_reason = "policy:none-store-exit"
                key = LEAVE_STORE_KEY
            else:
                self.last_reason = "policy:none-wait"
                key = WAIT_KEY
        if snapshot.store is not None and key == WAIT_KEY:
            # Hengband's store command loop rejects the normal rest command.
            # Carriage return is an explicit no-op in the store command loop.
            key = "\r"
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and key == LEAVE_STORE_KEY
            and self.last_reason != "home:processing-complete"
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
                operation_completed=self._home_entry_operation_posted,
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
        self._remember_stair_command(
            snapshot, key, observation=latest_snapshot
        )
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


    def _town_entrance_step_off_key(
        self, snapshot: Snapshot, prior_reason: str | None
    ) -> str:
        """Select the established safe, least-visited exit from an entrance."""
        origin = snapshot.player.position
        candidates: list[Position] = []
        for dy, dx in NEIGHBOR_OFFSETS:
            candidate = Position(origin.y + dy, origin.x + dx)
            grid = snapshot.grids.get(candidate)
            if (
                grid is None
                or not grid.passable
                or grid.has_monster
                or grid.is_door
                or grid.has_entrance
                or grid.store_number >= 0
                or grid.building_special >= 0
                or grid.has_quest_enter
                or grid.has_quest_exit
                or candidate in self._warning_refused_cells
                or candidate in self._engagement_owned_avoid_cells
                or self._is_avoidable_hazard_grid(grid)
                or self._on_town_border(snapshot, candidate)
            ):
                continue
            candidates.append(candidate)
        if not candidates:
            if prior_reason == "equipment-transaction:abandon-blocked":
                # Escape is inert at the outside command loop and, unlike stay,
                # cannot enter the store beneath the player.  Preserve the
                # restoration owner's durable progress marker for harness/CLI
                # visibility when the emitter discloses no safe step-off cell.
                return LEAVE_STORE_KEY
            self.last_reason = "livelock:exhausted"
            return WAIT_KEY
        step = min(candidates, key=lambda position: self._visit_counts[position])
        key = self._step_toward(snapshot, step)
        if not (
            (prior_reason or "").startswith("town:blocked:")
            or prior_reason == "equipment-transaction:abandon-blocked"
        ):
            self.last_reason = f"town:entrance-step-off:{prior_reason or 'wait'}"
        return key

    def observe_character_snapshot(self, character) -> None:
        """Consume a `C` character snapshot (naked capture or periodic dump).

        Always refreshes the mutation signature from ``mutations`` — the
        pre-existing periodic status dump (cli DUMP_INTERVAL_SECONDS) makes
        this the autonomous, observation-bounded post-calibration trigger for
        the mutation invalidation.  While the calibration capture step's
        naked dump is in flight, the ``characteristics`` table is additionally
        recorded as the worn-independent intrinsic TR flag set.
        """
        if not isinstance(character, dict):
            return
        mutations = character.get("mutations")
        if mutations is not None:
            try:
                self._mutation_signature = tuple(
                    sorted(int(value) for value in mutations)
                )
            except (TypeError, ValueError):
                pass
        if (
            self._calibration_naked_dump_inflight
            and self._calibration_phase == "capture"
        ):
            self._calibration_naked_flags = character_intrinsic_flags(
                character.get("characteristics")
            )
            self._calibration_naked_dump_inflight = False



    @staticmethod
    def _inventory_item_from_store_item(item: StoreItem) -> InventoryItem:
        """Project an observed Home ware onto the canonical ~9 item contract."""
        return InventoryItem(
            slot=item.letter,
            name=item.name,
            count=item.count,
            tval=item.tval,
            sval=item.sval,
            aware=item.aware,
            known=item.known,
            fully_known=item.fully_known,
            charges=item.charges,
            pval=item.pval,
            is_equipment=item.is_equipment,
            is_ego=item.is_ego,
            is_artifact=item.is_artifact,
            is_cursed=item.is_cursed,
            inscription=item.inscription,
            is_broken=item.is_broken,
            to_h=item.to_h,
            to_d=item.to_d,
            to_a=item.to_a,
            ac=item.ac,
            damage_dice_num=item.damage_dice_num,
            damage_dice_sides=item.damage_dice_sides,
            known_flags=item.known_flags,
            pseudo_feeling=item.pseudo_feeling,
            weight=item.weight,
            weapon_proficiency=item.weapon_proficiency,
        )


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

    def request_character_dump(self) -> None:
        """Latch a CLI timer request until an ordinary quiet filler decision."""
        self._periodic_dump_requested = True

    def request_game_save(self) -> None:
        """Latch a CLI timer request until an ordinary quiet filler decision."""
        self._periodic_save_requested = True


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
        return "\x13"

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
                else "scavenge"
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



    def _release_stale_town_block(self, snapshot: Snapshot) -> None:
        """Release snapshot-local verdicts; declared drive terminals persist."""
        del snapshot
        latch = self._cross_decision_latches["_town_blocked_reason"]
        reason = self._town_blocked_reason
        if (
            reason not in {*latch.permanent_values, *latch.retained_values}
            and not any(
                (reason or "").startswith(prefix)
                for prefix in latch.retained_prefixes
            )
        ):
            self._town_blocked_reason = None

    def _release_invalid_store_visit(self, snapshot: Snapshot) -> None:
        """Release a visit whose lifecycle has no remaining work."""
        visit = self._store_visit
        if (
            visit is not None
            and visit.operation_posted
            and not visit.operation_released
            and snapshot.store is None
            and visit.posted_sequence is not None
            and self._decision_sequence - visit.posted_sequence
            >= STORE_STUCK_LIMIT
        ):
            self._close_store_visit("posted-entry-unobserved")
            visit = None
        plan = self._town_errand_plan
        required_store = None
        released_stores: set[int] = set()
        if plan is not None:
            released_stores = set(plan.completed_this_visit) | set(
                plan.blocked_this_visit
            )
            if plan.index < len(plan.stops):
                candidate = plan.stops[plan.index]
                if plan.need_categories.get(candidate):
                    required_store = candidate
        if visit is not None and (
            visit.phase == StoreVisitPhase.CLOSED
            or visit.operation_effect_observed
            or not snapshot.in_town
            or (
                visit.owner == "town-errand"
                and visit.phase
                in (StoreVisitPhase.APPROACHING, StoreVisitPhase.ENTERING)
                and not visit.operation_posted
                and visit.store_type in released_stores
                and required_store is not None
                and visit.store_type != required_store
            )
        ):
            outcome = (
                "required-stop-changed"
                if visit.store_type in released_stores
                and required_store is not None
                and visit.store_type != required_store
                else self._store_visit.outcome or "completed"
            )
            self._close_store_visit(outcome)


    def _release_invalid_choke_plan(self, snapshot: Snapshot) -> None:
        """Release an active engagement when its defining floor no longer exists."""
        plan = self._choke_engagement_plan
        if (
            plan is not None
            and plan.phase in {"reposition", "validate", "hold"}
            and plan.floor != snapshot.floor_key
        ):
            self._release_choke_plan("floor-change")

    def _decide(self, snapshot: Snapshot) -> str:
        self._evaluate_cross_decision_latches(snapshot)

        # A TR_WARNING prompt reported by this snapshot is disposed of before
        # any other purpose is pursued: a refused movement is latched so it is
        # not re-chosen (the loop this handler removes), and an unsanctioned
        # tail-answered crossing is latched even when the walk opened a store
        # screen (the handler posts nothing in that case).
        warning_response = self._warning_prompt_response_key(snapshot)
        if warning_response is not None:
            return warning_response

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
            return self._equipment_transaction_town_owner_key(snapshot) or WAIT_KEY

        if snapshot.in_town and self._equipment_transaction_route_terminal is not None:
            self.last_reason = self._equipment_transaction_route_terminal
            return LEAVE_STORE_KEY if snapshot.store is not None else WAIT_KEY

        if (
            snapshot.store is None
            and self._store_visit is not None
            and self._store_visit.operation_posted
            and (
                self._store_visit.store_type != STORE_HOME
                or self._store_visit.phase == StoreVisitPhase.ENTERING
            )
        ):
            # A player-turn at the entrance can be emitted after the leading
            # stay key but before the queued store UI consumes the transaction.
            # The posted macro owns that page just as it owns an intermediate
            # store page; only observed completion or visit closure releases it.
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
            if snapshot.store.store_type != STORE_HOME:
                self._town_supplier_stock[snapshot.store.store_type] = snapshot.store
                self._town_supplier_stock_observations[snapshot.store.store_type] = (
                    self._effective_town_id(snapshot),
                    snapshot.turn,
                )
                self._observe_restock_supplier_page(snapshot)
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
                return staged_operation
            if (
                (self._store_visit is not None and self._store_visit.operation_posted)
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
            # Observation visit: never select or answer an item prompt here.
            self._shop_observation = (snapshot.store, self._decision_sequence)
            self.last_reason = "shop:observe-and-leave"
            key = LEAVE_STORE_KEY
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
        summoner_ranged = self._summoner_ranged_kill_key(
            snapshot, emergency_hostiles
        )
        if summoner_ranged is not None:
            return summoner_ranged
        emergency = self._emergency_item(snapshot, emergency_hostiles)
        if emergency is not None:
            if self._choke_plan_active(snapshot):
                self._release_choke_plan("hp-emergency")
            if self.last_reason.startswith(
                ("emergency:", "unseen-recall:", "guardian:")
            ):
                # Survival may always pre-empt a lower-priority owner.
                self._escape_state.enter("emergency", self.last_reason)
            return emergency
        if self._escape_state.owner == "emergency":
            # The emergency ladder is exempt from sibling hysteresis: the
            # established post-teleport handoff must happen immediately.
            self._escape_state.release()

        mana_survival = self._mana_food_survival_override_key(snapshot)
        if mana_survival is not None:
            return mana_survival

        paralyzer_prevention = self._paralyzer_prevention_key(
            snapshot, paralyzers, physical_adjacent
        )
        if paralyzer_prevention is not None:
            return paralyzer_prevention

        unseen_intercept = self._unseen_retreat_intercept_key(
            snapshot, physical_hostiles, physical_adjacent
        )
        unseen_action = unseen_intercept
        if unseen_action is None:
            unseen_action = self._unseen_retreat_key(
                snapshot, physical_hostiles
            )
        detected_preparation = None
        if unseen_action is None:
            detected_preparation = self._detected_threat_preparation_key(
                snapshot, physical_hostiles
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
                else self._return_to_town_key(snapshot, strategic_hostiles)
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
        dark_locomotion = self._dark_locomotion_key(snapshot)
        if dark_locomotion is not None:
            return dark_locomotion

        opening_q34 = self._opening_q34_town_key(snapshot, strategic_hostiles)
        if opening_q34 is not None:
            return opening_q34

        # A calibration-stripped character gets dressed before ANY other town
        # activity: one wear key per decision, unconditionally — under threat,
        # at any HP, with temporary statuses active.  Only the emergency and
        # threat-response owners above may preempt it.
        redress = self._calibration_redress_key(snapshot)
        if redress is not None:
            return redress

        if (
            self._breakout_dig_floor is not None
            and (
                snapshot.floor_key != self._breakout_dig_floor
                or self._dig_to_known_downstairs_key(snapshot) is None
            )
        ):
            restore = self._breakout_restore_weapon_key(snapshot)
            if restore is not None:
                return restore

        if profile is not None:
            # Approved-floor survival remains above the navigator. Keeping this
            # scoped to the quest branch preserves byte-for-byte dispatch order
            # on every non-quest floor.
            survival = self._survival_gate_key(snapshot, physical_hostiles)
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
                chest = self._chest_processing_key(
                    snapshot,
                    physical_hostiles,
                    allowed_positions={Q34_WOODEN_CHEST_POSITION}
                    if profile.quest_id == 34
                    else None,
                )
                if chest is not None:
                    return chest
            return navigator.decide(
                self, snapshot, strategic_hostiles, strategic_adjacent
            )

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
        town_kill = self._town_kill_mob_key(snapshot)
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
        breakthrough = self._breeder_breakthrough_key(
            snapshot, strategic_hostiles
        )
        if breakthrough is not None:
            if self._choke_plan_active(snapshot):
                self._release_choke_plan("breeder-breakthrough")
            return breakthrough

        choke_plan = self._choke_engagement_key(
            snapshot, physical_hostiles, physical_adjacent
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
            ranged = self._ranged_attack_key(
                snapshot, breeders, breeder_adjacent
            )
            if ranged is not None:
                return ranged

        # A fruitless breeder engagement latches this floor visit. Keep this
        # ahead of ordinary combat so the same cluster cannot pull us back in.
        disengage = None
        if not self._productive_choke_hold(snapshot):
            disengage = self._fruitless_disengage_key(
                snapshot, strategic_hostiles
            )
        if disengage is not None:
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
            escape = self._breeder_breakthrough_escape_key(snapshot)
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
        swarm_combat = self._melee_swarm_combat_key(
            snapshot, mining_hostiles, mining_adjacent
        )
        if swarm_combat is not None:
            return swarm_combat

        # 1. Survival: flee when hurt, swarmed, or too afraid to fight back.
        status_threats = self._unresisted_melee_status_threats(
            snapshot, physical_hostiles
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
            step = self._flee_step(snapshot, status_threats)
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
                    blocker := self._blocking_escape_melee_key(
                        snapshot, physical_hostiles, self._is_upstairs_target
                    )
                )
                is not None
            ):
                # A declared walk-out must keep moving toward its known exit at
                # low HP too. One projected-easy corridor kill is safer than the
                # generic flee rung retreating back into the floor.
                self.last_reason = "combat:disengage-clear-path"
                return blocker
            step = self._flee_step(snapshot, strategic_hostiles)
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
                return self._direction_key(
                    player.position, self._weakest(strategic_adjacent).position
                )
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
                return UP_STAIRS_KEY
            step = self._summoner_retreat_step(
                snapshot, corridor_threats, strategic_hostiles
            )
            if step is not None:
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
            self.last_reason = "melee"
            return self._direction_key(
                player.position, self._weakest(combat_adjacent).position
            )

        # 2r. Ranged attack: fire matching ammo (or throw a spare oil flask) at a
        # ray-aligned hostile before it closes. Fear blocks melee but NOT firing,
        # so an afraid archer still fights back while it retreats.
        ranged = self._ranged_attack_key(
            snapshot, combat_hostiles, combat_adjacent
        )
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
            step = self._flee_step(snapshot, strategic_hostiles)
            if step is not None:
                # This is the same navigation veto as the projected-melee gate
                # below.  Without persisting the abandoned square, generic
                # secret-wall exploration can immediately reverse this retreat
                # and alternate with it forever.
                self._claim_engagement_avoid_cells((snapshot.player.position,))
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
                self.last_reason = "threat:reposition"
                return self._step_toward(snapshot, step)
            scroll = self._escape_scroll(snapshot)
            if scroll is not None:
                self.last_reason = "threat:scroll"
                return self._read_key(snapshot, scroll)
            self.last_reason = "threat:wait"
            return WAIT_KEY

        if quest_targets:
            step = self._hunt_step(snapshot, quest_targets, allow_cooling=False)
            if step is not None:
                self.last_reason = "hunt:quest-target"
                return self._step_toward(snapshot, step)

        # 2s. Survival gate (R1): starvation safety is mode- and objective-
        # independent. It runs ABOVE fundraising/quests/descent because every
        # one of those returns keys on its own and would otherwise starve this
        # step of decisions — which is exactly how a mining run walked a
        # character to food_state "weak" with an empty pack (2026-07-17).
        survival = self._survival_gate_key(snapshot, physical_hostiles)
        if survival is not None:
            return survival

        mana_food_loot = self._mana_food_loot_key(
            snapshot, strategic_hostiles
        )
        if mana_food_loot is not None:
            return mana_food_loot

        quest_floor_recovery = self._kill_quest_floor_recovery_key(snapshot)
        if quest_floor_recovery is not None:
            return quest_floor_recovery

        home_disposal = self._home_disposal_processing_key(snapshot)
        if home_disposal is not None:
            return home_disposal

        cancel_unsafe_recall = self._town_cancel_unsafe_recall_key(snapshot)
        if cancel_unsafe_recall is not None:
            return cancel_unsafe_recall
        if (
            self._startup_town_recall
            and snapshot.in_town
            and snapshot.player.recalling
        ):
            # A policy process may attach after Hengband has already accepted a
            # town recall.  Once the explicit hard-safety checks above have
            # passed, do not run the fresh process's incomplete Home/catalog
            # state through the ordinary departure planner: it can only invent
            # soft blockers and cancel an engine-owned action.  Store tiles are
            # still stepped off so the pending recall can complete normally.
            here = snapshot.grid_at(snapshot.player.position)
            if here is not None and here.is_store:
                neighbors = self._walkable_neighbors(
                    snapshot, snapshot.player.position
                )
                if neighbors:
                    self.last_reason = "town:wait-recall-step-off"
                    return self._step_toward(snapshot, neighbors[0])
            self.last_reason = "town:wait-recall"
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
                shelter = self._nearest_goal_step(snapshot, lambda grid: grid.is_store)
                if shelter is not None:
                    self.last_reason = "town:seek-shelter"
                    return self._step_toward(snapshot, shelter)
            if (
                player.hp < player.max_hp
                or player.mp < player.max_mp
                or not self._temporary_status_clear(snapshot)
            ) and player.food_state in {"normal", "full", "gorged"}:
                self.last_reason = "town:recover"
                return REST_MACRO

        victory_loot = self._victory_loot_key(snapshot)
        if victory_loot is not None:
            return victory_loot

        conquest_loot = self._conquest_loot_key(snapshot)
        if conquest_loot is not None:
            return conquest_loot

        fixed_quest = self._fixed_quest_key(snapshot, strategic_hostiles)
        if fixed_quest is not None:
            return fixed_quest

        stat_restore = self._stat_restore_quaff_key(
            snapshot, physical_hostiles
        )
        if stat_restore is not None:
            return stat_restore

        stat_gain = self._stat_gain_quaff_key(snapshot, physical_hostiles)
        if stat_gain is not None:
            return stat_gain

        bounty = self._bounty_cashout_key(snapshot)
        if bounty is not None:
            return bounty

        fundraising = self._fundraising_key(snapshot, strategic_hostiles)
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
        chest = self._chest_processing_key(snapshot, physical_hostiles)
        if chest is not None:
            return chest

        # A routine supply return can afford a short sweep for already-seen safe
        # loot. Hunger, darkness, a full pack, and emergency returns never detour.
        return_starting = (
            not snapshot.in_town and self._should_start_town_return(snapshot)
        )
        if (
            (return_starting or self._returning_to_town)
            and not player.recalling
            and not self._emergency_return_active
            and self._last_return_trigger in RETURN_LOOT_SWEEP_TRIGGERS
        ):
            return_loot = self._normal_loot_key(
                snapshot,
                strategic_hostiles,
                max_path_distance=RETURN_LOOT_SWEEP_MAX_DISTANCE,
                seek_reason="return:seek-loot",
            )
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
        livelock = self._navigation_livelock_key(snapshot)
        if livelock is not None:
            return livelock

        # A fled breeder floor turns the ordinary return into a persistent
        # walk-out, but it remains a navigation owner: survival/combat above
        # and the livelock escape immediately above must retain priority.
        if (
            self._breeder_walkout_active(snapshot)
            and self._escape_state.owner in {None, "return"}
        ):
            self._returning_to_town = True
            walkout = self._return_to_town_key(
                snapshot,
                strategic_hostiles,
                allow_recall=(
                    self._fundraising_mode != "mine"
                    and self._active_quest_id(snapshot) is None
                ),
            )
            if walkout is not None:
                self._escape_state.enter("return", self.last_reason)
                return walkout

        # Low supplies and a full pack are expedition-ending conditions. Once
        # triggered, keep heading upward even if using an item opens a pack slot.
        town_return = (
            None
            if self._escape_state.owner not in {None, "return"}
            else self._return_to_town_key(snapshot, strategic_hostiles)
        )
        if town_return is not None:
            self._escape_state.enter("return", self.last_reason)
            return town_return

        # Identification can consume the same scarce gold as the mining setup.
        # While fundraising, finish Treasure Detection scrolls and a digging
        # tool first; retain any pending identification request for afterwards.
        if not (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and not self._fundraising_supplies_ready(snapshot)
        ):
            equipped_identification = self._town_equipped_identification_key(snapshot)
            if equipped_identification is not None:
                return equipped_identification

            item_processing = self._town_item_processing_key(snapshot)
            if item_processing is not None:
                return item_processing

            device_processing = self._town_device_processing_key(snapshot)
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

        restore_weapon = self._town_restore_weapon_key(snapshot)
        if restore_weapon is not None:
            return restore_weapon

        mark_heavy_curse = self._heavy_curse_inscription_key(snapshot)
        if mark_heavy_curse is not None:
            return mark_heavy_curse

        remove_curse = self._town_remove_curse_key(snapshot)
        if remove_curse is not None:
            return remove_curse

        enchant_launcher = self._town_enchant_launcher_key(snapshot)
        if enchant_launcher is not None:
            return enchant_launcher

        suppress_random_teleport = self._town_random_teleport_suppression_key(
            snapshot
        )
        if suppress_random_teleport is not None:
            return suppress_random_teleport

        # The unequipped calibration phase owns the character before the
        # optimizer may run: it strips at Home, observes the constants, and the
        # optimizer (unblocked by the capture) dresses the character back.
        calibration_key = self._calibration_town_key(snapshot)
        if calibration_key is not None:
            return calibration_key

        # Equipment changes have one owner: after Home identification and the
        # complete-page scan, execute the globally optimized loadout transaction.
        # Legacy per-item weapon trials and jewellery upgrades must not race this
        # plan or repeatedly withdraw and re-deposit candidates.
        equipment_transaction = self._equipment_transaction_town_key(snapshot)
        if equipment_transaction is not None:
            return equipment_transaction

        if not self._emergency_return_active:
            loot = self._normal_loot_key(snapshot, strategic_hostiles)
            if loot is not None:
                return loot

        # Keep a light lit before any town errand can approach a store or the
        # dungeon entrance: native town travel is rejected at night unless a
        # light is equipped. Skip equipment changes while confused, and while
        # the calibration phase deliberately holds the character stripped.
        if not player.confused and not self._calibration_active():
            restore_lantern = self._empty_lantern_to_restore(snapshot)
            if restore_lantern is not None:
                self.last_reason = "restore-lantern"
                return self._equipment_wield(
                    snapshot, "light-loadout", restore_lantern, "light"
                )
            wield = self._light_to_wield(snapshot)
            if wield is not None:
                self.last_reason = "wield-light"
                return self._equipment_wield(
                    snapshot, "light-loadout", wield, "light"
                )
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
                self._town_errand_plan = None
        if self._town_cycle_pending:
            town_cycle_repair = self._town_special_key(snapshot)
            if town_cycle_repair is not None:
                return town_cycle_repair

        # 2a. Before diving: while in town with money and no lantern, walk to the
        #     General Store to buy one. A brass lantern lights radius 2 vs a torch's
        #     radius 1 — seeing the dark is what the Half-Troll lacked when it died.
        if snapshot.in_town:
            claims_active = self._town_claims_active(snapshot)
            if not claims_active:
                # The former router performed terminal bookkeeping before it
                # returned None. Preserve those latch releases and pending-disposal
                # handoffs without letting the errand plan own this departure turn.
                self._town_terminal_transitions(snapshot)
            if claims_active:
                step = self._shopping_approach_step(snapshot)
                if step is not None:
                    self.last_reason = "shop:approach"
                    return self._shopping_approach_key(snapshot, step, "shop:travel")

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
            overflow_destroy = self._town_overflow_destroy_key(snapshot)
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
                fundraising = self._fundraising_key(
                    snapshot, strategic_hostiles
                )
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
                return self._released_restock_store_key(
                    snapshot, recall_stores
                )
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
            # Note: resting burns many turns (= food). Skip it when hungry so we
            # don't starve — bot-test died of starvation partly from over-resting.
            self._rest_count += 1
            self.last_reason = "rest"
            return REST_MACRO

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
            step = self._flee_step(snapshot, strategic_hostiles)
            if step is not None:
                # Treat the retreat as a navigation veto, not a one-turn move.
                # A committed explore path otherwise walks straight back here.
                self._claim_engagement_avoid_cells((snapshot.player.position,))
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
                self.last_reason = "threat:avoid-engagement"
                return self._step_toward(snapshot, step)

        # 6. Head for a known downstairs / dungeon entrance: path straight there
        #    if reachable, otherwise explore toward it (the entrance may be known
        #    but its approach still unmapped — e.g. the town's wilderness gate).
        #    A single BFS covers both, so the huge full-map scan runs only once.
        step = self._descent_step(snapshot)
        if step is not None:
            # A visible monster can temporarily split the only known route to
            # the stairs. Chasing a fallback frontier makes the monster vanish
            # from sight, after which we turn back toward the stairs forever.
            # Clear an easy blocker instead of bouncing at the visibility edge.
            if self.last_reason == "approach-descent" and strategic_hostiles:
                clear_step = self._hunt_step(snapshot, strategic_hostiles)
                if clear_step is not None:
                    self.last_reason = "clear-descent"
                    return self._step_toward(snapshot, clear_step)
            travel = self._entrance_travel_key(snapshot, self._descent_target_goal)
            if travel is not None:
                return travel
            return self._step_toward(snapshot, step)

        # 7. Eat when hungry and it is safe to do so.
        if player.hungry and not physical_hostiles:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "eat"
                return EAT_KEY + food.slot

        # 7. Opportunistic hunt for easy XP while no downstairs is in sight.
        step = self._hunt_step(snapshot, strategic_hostiles)
        if step is not None:
            self.last_reason = "hunt"
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
                restore = self._breakout_restore_weapon_key(snapshot)
                if restore is not None:
                    return restore
            recall = self._find_recall_scroll(snapshot)
            if recall is not None and self._can_read_scrolls(snapshot):
                self._stuck_escape_streak = 0
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
            step = self._probe_unknown_step(snapshot)
            if step is not None:
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
                self.last_reason = "search"
                return SEARCH_KEY
            # Once local probes and searches are exhausted, resume the committed
            # exploration planner. It can route across remembered, off-screen
            # floor to an older reachable frontier; choosing a local least-visited
            # neighbour first traps us in a fully-known room forever.
            step = self._explore_step(snapshot)
            if step is not None:
                # A valid committed route means the oscillation was escaped. Drop
                # the stale stationary/search history now; otherwise it remains
                # "oscillating" for several more decisions and searches at every
                # waypoint until the recall escape threshold is reached.
                self._recent.clear()
                self._stuck_escape_streak = 0
                self.last_reason = "breakout:seek-frontier"
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
        immobile_breeder_giveup = self._immobile_breeder_giveup_key(snapshot)
        if immobile_breeder_giveup is not None:
            return immobile_breeder_giveup

        # 9. Explore toward the unknown (door- and edge-aware).
        step = self._explore_step(snapshot)
        if step is not None:
            self.last_reason = "explore"
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
            step = self._probe_unknown_step(snapshot)
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
            step = self._secret_wall_search_step(snapshot)
            if step is not None:
                self.last_reason = "seek-secret-wall"
                return self._step_toward(snapshot, step)

        # 9. Nothing to explore: take any known stairs to reach a fresh floor.
        quest_regen = self._start_kill_quest_regeneration(snapshot)
        if quest_regen is not None:
            return quest_regen
        floor_exit_locked = self._floor_navigation_exit_locked(snapshot)
        allow_descent = not self._descent_is_blocked(snapshot)
        step = self._nearest_goal_step(
            snapshot,
            lambda g: not floor_exit_locked
            and (
                self._is_upstairs_target(g)
                or (allow_descent and self._is_descent_target(snapshot, g))
            ),
        )
        if step is not None:
            self.last_reason = "stuck:seek-stairs"
            return self._step_toward(snapshot, step)
        if not floor_exit_locked and here is not None and self._is_upstairs_target(here):
            self._defer_descent(snapshot)
            self.last_reason = "stuck:ascend"
            return UP_STAIRS_KEY

        # 10. Last resort: keep moving so we never freeze forever. (A floor with
        #     walled-off stairs is escaped by the stuck:recall-escape check above,
        #     before the search/explore cluster; this only runs until the streak
        #     builds up.)
        step = self._least_visited_neighbor(snapshot)
        if step is not None:
            self.last_reason = "stuck:wander"
            return self._step_toward(snapshot, step)

        self.last_reason = "wait"
        return WAIT_KEY

    # -------------------------------------------------------------- observers


    def _is_upstairs_target(self, grid: GridState) -> bool:
        return grid.has_up_stairs and (
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

    def _observe(
        self, snapshot: Snapshot, *, observation: Snapshot | None = None
    ) -> None:
        # The threat memo exists only for repeat lookups within ONE decision
        # (gates + telemetry); a new decision must never see the old entries.
        self._threat_prediction_memo.clear()
        self._observe_remove_curse(snapshot)
        self._observe_launcher_enchant(snapshot)
        self._observe_departure_prices(snapshot)
        previous_floor = self._floor_key
        if self._breeder_fled_floor is not None and (
            snapshot.in_town
            or snapshot.floor_key[0] != self._breeder_fled_floor[0]
        ):
            self._breeder_fled_floor = None
        if self._emergency_recall_sanctioned:
            if previous_floor is not None and previous_floor != snapshot.floor_key:
                self._emergency_recall_sanctioned = False
            elif (
                self._town_blocked_reason != "repetition"
                and not snapshot.player.recalling
            ):
                self._emergency_recall_sanctioned = False
        if snapshot.in_town and not self._town_was_in_town:
            self._town_visit_ledger = TownVisitLedger()
            if (
                getattr(self, "_home_visit", None) is not None
                and not self._home_visit.active
            ):
                self._home_visit.reset_epoch()
            self._unknown_lantern_departure_refilled = False
            self._abandoned_quest_carry_requirements.clear()
            self._calibration_aborts_this_visit = 0
            self._calibration_blocked_this_visit = False
            self._calibration_last_abort = None
        self._town_was_in_town = snapshot.in_town
        if previous_floor is None and snapshot.in_town and snapshot.player.recalling:
            self._startup_town_recall = True
        current_town_id = (
            self._effective_town_id(snapshot) if snapshot.in_town else None
        )
        town_changed = (
            current_town_id is not None
            and self._observed_town_id is not None
            and current_town_id != self._observed_town_id
        )
        if town_changed:
            self._town_supplier_stock_observations.clear()
        self._observed_town_id = current_town_id
        self._observe_stair_command(snapshot, observation=observation)
        if not snapshot.in_town and snapshot.player.recalling:
            self._saw_dungeon_recall = True
            self._emergency_return_active = False
        if (
            snapshot.in_town
            and previous_floor is not None
            and previous_floor[1] > 0
            and previous_floor != snapshot.floor_key
            and self._saw_dungeon_recall
        ):
            self._home_disposal_pass = self._home_disposal.note_dungeon_recall()
            self._home_disposal_seen_pages.clear()
            self._home_disposal_candidates.clear()
            self._saw_dungeon_recall = False
            self._town_errand_plan = None
            self._town_store_attempted.pop(STORE_HOME, None)
        if snapshot.in_town:
            self._home_disposal.reload_decisions()
        if previous_floor is not None and previous_floor != snapshot.floor_key:
            self._quest_strategy_visible_targets.clear()
            self._quest_strategy_cleared_targets.clear()
            self._quest_strategy_pending_recovery.clear()
            self._quest_strategy_recovery_claims.clear()
            self._quest_strategy_recovery_pickup_prepared = None
            self._quest_strategy_recovery_pickup_prepared_key = None
            self._quest_strategy_recovery_pickup_posted = None
            self._quest_strategy_initial_hold_turns.clear()
            self._quest_strategy_surveyed_placements.clear()
            self._quest_strategy_sweep_rounds.clear()
            self._quest_strategy_opening_phase.clear()
            self._quest_strategy_hold_positions.clear()
            self._quest_strategy_post_wave_light_attempted.clear()
            if (
                self._quest_regen_phase == "ascend"
                and self._quest_regen_id is not None
                and snapshot.floor_key[0] == previous_floor[0]
                and snapshot.floor_key[1] == previous_floor[1] - 1
            ):
                self._quest_regen_phase = "descend"
            self._fruitless_disengage_floor = None
            self._fruitless_disengage_decisions = 0
            if snapshot.floor_key[2] in FIXED_QUEST_ALLOWLIST:
                self._fixed_quest_speed_floor = snapshot.floor_key
                self._fixed_quest_speed_attempted = False
            else:
                self._fixed_quest_speed_floor = None
                self._fixed_quest_speed_attempted = False
            # Surface-travel bookkeeping is per-visit: positions repeat across
            # town visits (static map), so a stale no-progress latch from the
            # previous visit would suppress native travel forever.
            self._town_travel_state = None
            self._town_travel_fallback = None
            self._town_hunt_target = None
            self._town_signature_history.clear()
            self._town_progress_marker = None
            self._town_no_progress_count = 0
            self._town_cycle_pending = False
            self._town_cycle_breaks = 0
            self._town_restock_suppressed = False
            self._town_suppression_claim_stores.clear()
            self._town_errand_plan = None
            self._terminal_pack_space_signature = None
            self._town_restock_wait_until = None
            self._town_restock_waiting_for = ()
            self._town_restock_rechecked.clear()
            self._town_restock_waited_turns = 0
            self._town_restock_last_wait_turn = None
        elif town_changed:
            # Inn travel keeps the surface floor key at (0, 0, 0), but it is a
            # new town visit with different stores and routes.  Carrying the
            # previous town's cycle debt made the first ordinary shopping pass
            # in the destination look like a second repetition offense.
            self._town_travel_state = None
            self._town_travel_fallback = None
            self._town_hunt_target = None
            self._town_signature_history.clear()
            self._town_progress_marker = None
            self._town_no_progress_count = 0
            self._town_wander_streak = 0
            self._town_cycle_pending = False
            self._town_cycle_breaks = 0
            self._town_blocked_reason = None
            self._town_restock_suppressed = False
            self._town_suppression_claim_stores.clear()
            self._town_errand_plan = None
            self._terminal_pack_space_signature = None
            self._town_restock_wait_until = None
            self._town_restock_waiting_for = ()
            self._town_restock_rechecked.clear()
            self._town_restock_waited_turns = 0
            self._town_restock_last_wait_turn = None
            self._town_store_attempted.clear()
            self._shopping_stuck = False
            self._shop_approach_stuck_count = 0
            self._shopping_abandoned = False
        # Count consecutive "stuck" turns on a dungeon floor — searching, probing,
        # breaking out or wandering, but never actually exploring a frontier or
        # fighting (reset by any such progress, or by reaching town) — so a
        # walled-off level triggers a Word-of-Recall escape instead of trapping
        # the bot forever.
        if not snapshot.in_town and self.last_reason in STUCK_FAMILY_REASONS:
            self._stuck_escape_streak += 1
        elif self.last_reason in STUCK_NEUTRAL_REASONS and not snapshot.in_town:
            pass  # upkeep between searches — hold the streak, do not reset it
        else:
            self._stuck_escape_streak = 0
        # Town circuit breaker (see TOWN_WANDER_LIMIT): count the mirror-image
        # streak for town. Any other reason, or leaving town, resets it — the
        # latch below only fires on a genuinely unbroken run of dead-end turns.
        if snapshot.in_town and self.last_reason in TOWN_WANDER_REASONS:
            self._town_wander_streak += 1
        else:
            self._town_wander_streak = 0
        # Generic town-repetition detector (see TOWN_CYCLE_WINDOW): record the
        # previous decision's signature; any real progress (gold, pack or
        # equipment change) resets the window.
        if snapshot.in_town:
            plan = self._town_errand_plan
            marker = (
                snapshot.player.gold,
                len(snapshot.inventory),
                len(snapshot.equipment),
                self._identification_need,
                self._equipment_catalog.home_scan_complete,
                tuple(plan.completed_this_visit) if plan is not None else (),
                tuple(plan.blocked_this_visit) if plan is not None else (),
            )
            if marker != self._town_progress_marker:
                had_marker = self._town_progress_marker is not None
                self._town_progress_marker = marker
                self._town_signature_history.clear()
                self._town_no_progress_count = 0
                self._town_visit_ledger.passes_since_progress = 0
                if had_marker:
                    # Completing an identification/home-scan/errand stage is
                    # real workflow progress even when gold and pack counts do
                    # not change. Do not carry an earlier entrance-wait offense
                    # across that boundary and mislabel the next store visit as
                    # a second town cycle.
                    self._town_cycle_pending = False
                    self._town_cycle_breaks = 0
            if (
                self.last_reason
                and not any(
                    self.last_reason == ignored
                    or self.last_reason.startswith(f"{ignored}:")
                    for ignored in TOWN_CYCLE_IGNORED_REASONS
                )
                and self.last_reason not in HOME_PLAN_OWNED_PROCESSING_REASONS
            ):
                position = snapshot.player.position
                self._town_signature_history.append(
                    (self.last_reason, position.y, position.x)
                )
                self._town_no_progress_count += 1
                self._town_visit_ledger.passes_since_progress += 1
                if (
                    self._town_cycle_detected()
                    or self._town_no_progress_count >= TOWN_NO_PROGRESS_LIMIT
                ):
                    self._town_cycle_pending = True
                    self._town_signature_history.clear()
                    self._town_no_progress_count = 0
        else:
            self._town_signature_history.clear()
            self._town_progress_marker = None
            self._town_no_progress_count = 0
        if (
            snapshot.in_town
            and self._town_wander_streak >= TOWN_WANDER_LIMIT
            and not self._town_cycle_pending
        ):
            # A long but spatially varied wander will not satisfy the generic
            # repeated-signature detector.  Feed it into the same bounded
            # repair path anyway: the first offense suppresses errands and
            # forces departure, while a second offense stops visibly.
            self._town_cycle_pending = True
        # Track how long we have been stuck in town wielding only a pickaxe: the pre-recall
        # weapon check blocks a dive until we re-arm, and this backstop lets us dive anyway
        # if we simply own no combat weapon. Only in-town decisions count — a digger worn
        # for legitimate mining (in the dungeon) must not trip it.
        if snapshot.in_town and self._equipped_digging_tool(snapshot) is not None:
            self._weapon_block_streak += 1
        else:
            self._weapon_block_streak = 0
        if not snapshot.in_town:
            # Away from town, clear the "Home is full" latch so the next visit
            # re-checks (the bot may have withdrawn items or a later Home differs).
            self._home_deposit_abandoned = False
            self._home_rejected_deposits.clear()
            self._device_identify_watch = None
            self._device_identify_fail_streak = 0
        if snapshot.in_town:
            self._unidentifiable_sigs.clear()
            self._identify_watch = None
            self._identify_fail_streak = 0
            # A store latched into _town_store_attempted (nothing to buy/sell on
            # that visit) would otherwise stay skipped for the rest of an
            # abnormally long town stay, even though real time (game turns) has
            # passed and it may have restocked. Expire each latch on its own
            # schedule so supplies bought there are periodically re-checked
            # instead of draining unnoticed forever (see STORE_RETRY_TURNS).
            expired_stores = [
                store_type
                for store_type, latched_at in self._town_store_attempted.items()
                if snapshot.turn - latched_at >= STORE_RETRY_TURNS
            ]
            for store_type in expired_stores:
                del self._town_store_attempted[store_type]
                if store_type == STORE_HOME:
                    self._home_latch_active = None
        if (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and snapshot.player.level >= 2
        ):
            # A process restart loses the in-memory deepest-floor watermark.
            # A developed strict-mode character must not regress to the depth-1
            # shopping plan and enter without the depth-2 lantern/escape kit.
            self._deepest_level = max(self._deepest_level, 1)
        # recall_depth is the save-backed deepest level reached in the recall
        # target dungeon (where Word of Recall lands). Unlike the in-memory
        # watermark it survives a restart, so seed from it — otherwise a resumed
        # bot forgets it has been to 5F+ and walks in from the entrance instead of
        # recalling, re-descending the very floors recall exists to skip.
        self._deepest_level = max(self._deepest_level, snapshot.recall_depth)
        if snapshot.dungeon_level > 0:
            self._deepest_level = max(self._deepest_level, snapshot.dungeon_level)

        if snapshot.angband_recall_unlocked:
            self._target_dungeon_id = DUNGEON_ANGBAND
            self._rumor_unlock_pending = False
        elif (
            (quest_14 := snapshot.quests.get(14)) is not None
            and quest_14.status in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}
        ):
            self._rumor_unlock_pending = True
        if (
            self._town_travel_rumor_pending is not None
            and snapshot.visited_town_ids is not None
            and self._town_travel_rumor_pending in snapshot.visited_town_ids
        ):
            self._town_travel_rumor_pending = None

        # --- Over-extension: recall into a level-appropriate dungeon when the main
        # one is too deep to loot. On each dive of the recall target, track both the
        # loot grabbed and the emergency escapes forced; a dive that came back with
        # almost nothing AND had to bail out repeatedly (see OVEREXTEND_* limits) is
        # judged over-extended. A run of them means the dungeon is beyond the
        # character's ability, so switch to a shallower already-unlocked dungeon
        # whose landing depth satisfies the required abilities. ---
        prev_dungeon = previous_floor[0] if previous_floor else 0
        if not snapshot.in_town:
            if prev_dungeon == 0:  # descended from town: a fresh dive begins
                self._dive_dungeon = snapshot.floor_key[0]
                self._dive_start_recall_depth = snapshot.dungeon_recall_depths.get(
                    self._dive_dungeon,
                    snapshot.recall_depth
                    if snapshot.recall_dungeon_id == self._dive_dungeon
                    else snapshot.dungeon_level,
                )
                self._dive_loot = 0
                self._dive_emergencies = 0
            if self.last_reason in PICKUP_REASONS:
                self._dive_loot += 1
            elif self.last_reason in EMERGENCY_ESCAPE_REASONS:
                self._dive_emergencies += 1
        elif prev_dungeon != 0 and self._dive_dungeon is not None:
            # A dive just ended. Judge only normal dives of the recall target —
            # fundraising mining of the Yeek Cave is a separate mode, not a dive.
            if (
                self._dive_dungeon == self._target_dungeon_id
                and self._fundraising_mode not in {"prepare", "mine", "scavenge"}
            ):
                start_depth = self._dive_start_recall_depth or 0
                end_depth = snapshot.dungeon_recall_depths.get(
                    self._dive_dungeon,
                    snapshot.recall_depth
                    if snapshot.recall_dungeon_id == self._dive_dungeon
                    else start_depth,
                )
                dungeon_info = self._dungeon_knowledge.get(self._dive_dungeon)
                can_descend_further = (
                    dungeon_info is not None
                    and dungeon_info.max_depth > 0
                    and start_depth < dungeon_info.max_depth
                )
                if end_depth > start_depth:
                    self._no_depth_progress_dives = 0
                elif can_descend_further:
                    self._no_depth_progress_dives += 1
                if self._dive_loot > OVEREXTEND_LOOT_MAX:
                    # A real haul proves the character can handle this depth.
                    self._target_empty_dives = 0
                elif self._dive_emergencies >= OVEREXTEND_EMERGENCY_MIN:
                    # Unproductive AND forced to bail out repeatedly = over-extended.
                    self._target_empty_dives += 1
                elif self._last_return_trigger == "guardian-kit-insufficient":
                    # A guardian we cannot yet beat recalls us straight back with
                    # no real dive. Uncounted, it flip-flops town<->guardian
                    # forever, burning ~2 recall scrolls a round trip until the
                    # character is stranded at depth with zero escape scrolls
                    # (live: Labyrinth, recall 9 -> 0). Count it as over-extension
                    # so the approved empty-dive valve releases the conquest latch
                    # and switches to a productive dungeon; the latch may
                    # re-select the guardian later once the kit can beat it.
                    self._target_empty_dives += 1
                # else: unproductive but no real danger (found nothing, or a single
                # scare) — HOLD the streak. Weak evidence must not ADVANCE the count,
                # but a lone quiet dive between genuinely bad ones must not RESET it
                # to zero either, or the switch could never accumulate. Only a
                # profitable dive clears the suspicion.
            self._dive_dungeon = None
            self._dive_start_recall_depth = None
        conquered_now = set(snapshot.conquered_dungeon_ids)
        first_observation = previous_floor is None
        if first_observation:
            # A resumed process sees historical conquests as its baseline.
            self._conquered_seen |= conquered_now
            if snapshot.yeek_cave_conquered:
                self._yeek_conquest_processed = True
        newly_conquered = conquered_now - self._conquered_seen
        if newly_conquered:
            # A guardian clear ends the current over-extension diversion. Let
            # ordinary target selection choose the next conquest/default dive.
            self._alternate_dungeon = None
            self._last_overextended_depth = 0
        if snapshot.in_town and self._target_empty_dives >= EMPTY_DIVE_LIMIT:
            self._last_overextended_depth = snapshot.recall_depth
            alt = self._pick_alternate_dungeon(snapshot)
            if alt is not None:
                self._alternate_dungeon = alt
                # The safety valve must demote even a latched conquest target.
                # It may be selected again after the existing alternate period,
                # but must not immediately override the alternate below.
                self._conquest_committed = None
            self._target_empty_dives = 0
        if (
            snapshot.in_town
            and self._alternate_dungeon is None
            and self._no_depth_progress_dives >= NO_DEPTH_PROGRESS_DIVE_LIMIT
        ):
            # Five complete expeditions without increasing the saved Recall
            # depth is a lack of strategic progress even when they recovered
            # miscellaneous loot.  Farm the deepest already-unlocked safe
            # alternative below the blocked landing depth instead of repeating
            # the same Angband floor indefinitely.
            blocked_depth = max(1, snapshot.recall_depth)
            self._last_overextended_depth = blocked_depth
            alt = self._pick_alternate_dungeon(
                snapshot,
                max_entry_depth=max(1, blocked_depth - 1),
                prefer_deepest=True,
            )
            if alt is not None:
                self._alternate_dungeon = alt
                self._conquest_committed = None
            self._no_depth_progress_dives = 0
        # A switched target overrides the ordinary selection until its lifecycle
        # ends through conquest, loadout-fallback completion, or replacement.
        if self._alternate_dungeon is not None:
            if self._alternate_dungeon in snapshot.entered_dungeon_ids:
                self._target_dungeon_id = self._alternate_dungeon

        # HIGHEST PRIORITY target: clear an unconquered dungeon whose bottom is within
        # our resistance limit, for the final guardian's gear. It normally overrides
        # Angband, but the over-extension safety valve temporarily demotes it while
        # the existing alternate lifecycle is active.
        conquest = (
            self._conquest_target(snapshot)
            if self._alternate_dungeon is None
            else None
        )
        if conquest is not None:
            self._target_dungeon_id = conquest
            # Fundraising is only superseded when the conquest expedition can
            # actually leave town.  In particular, poverty plus a supply gap is
            # still a fundraising problem even when the guardian fight itself is
            # viable.  Remember successful clears by target so observe cannot
            # repeatedly undo a mode re-established by decide.
            if (
                snapshot.in_town
                and conquest != self._fundraising_cleared_for_conquest
                and self._conquest_departure_ready(snapshot)
            ):
                self._fundraising_mode = None
                self._planned_mining_runs = None
                self._fundraising_cleared_for_conquest = conquest

        # Fresh conquest: the char just killed a dungeon's final guardian while
        # standing in it. Latch it so the loot phase grabs the drop before recalling
        # out (the user flagged the Yeek Cave reward being left behind). Cleared on
        # reaching town.
        current_dungeon = snapshot.floor_key[0]
        if (
            not snapshot.in_town
            and current_dungeon != DUNGEON_YEEK_CAVE
            and current_dungeon in newly_conquered
        ):
            self._victory_loot_dungeon = current_dungeon
        self._conquered_seen |= conquered_now
        if snapshot.in_town:
            self._victory_loot_dungeon = None

        self._track_idle_items(snapshot, previous_floor)

        if not snapshot.in_town:
            self._startup_town_recall = False
            # Left town for the dungeon: re-arm the pre-dive character dump so the
            # next town departure writes a fresh sheet, and clear the shopping-stuck
            # latch so a fresh town visit re-tries the stores.
            self._char_dump_done_this_visit = False
            self._shopping_stuck = False
            self._shop_approach_stuck_count = 0
            self._home_processing_seen_pages.clear()
            self._home_digger_seen_pages.clear()
            self._home_pending_batch.clear()
            getattr(self, "_home_pending_quantities", {}).clear()
            self._home_procurement_batch_active = False
            self._home_batch_review_items.clear()
            self._home_active_from_batch = False
            self._home_atomic_withdraw_pending = None
            self._home_identify_staff_sale_pending = False
            self._home_identify_staff_sold_this_magic_visit = False
            self._home_digger_withdraw_pending = False
            self._equipment_transaction_failed_items.clear()
            self._equipment_retired_worn_item_ids = frozenset()
            getattr(self, "_priority_body_rearm_attempted_ids", set()).clear()
            self._equipment_quarantine_second_chance_ids.clear()
            self._equipment_quarantine_burned_ids.clear()

        if (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and DUNGEON_YEEK_CAVE in newly_conquered
            and self._fundraising_mode is None
            and not self._yeek_conquest_processed
        ):
            self._yeek_victory_loot = True

        returned_from_fundraising = (
            snapshot.in_town
            and previous_floor is not None
            and previous_floor[0] == DUNGEON_YEEK_CAVE
            and previous_floor[1] == 1
            and self._fundraising_mode in {"mine", "scavenge"}
        )
        if returned_from_fundraising:
            if self._fundraising_mode == "mine":
                self._mining_runs_completed += 1
            else:
                self._sell_scavenged_consumables = True
            self._mining_scroll_used_floor = None
            self._mining_detection_centers.clear()
            self._town_store_attempted.clear()
            # A completed mining trip is the user-approved retry boundary for
            # postponed Home identification: gear parked in _processed_home_items
            # is only *temporarily* skipped, so re-arm it and force the equipment
            # optimizer to re-plan against a fresh Home scan. The deferred
            # Home/device sets are re-armed by the fresh-town reset just below (it
            # always fires on this dungeon->town floor change); _processed_home_
            # items has no other clear site, so it is cleared here. It is
            # intentionally NOT cleared in the generic fresh-town reset: a quick
            # restock stop between unrelated dives must not force re-withdrawing
            # and re-examining every stored item, and the mining trip is the only
            # boundary the user approved for the identification retry. The
            # identification fundraising driver guarantees this boundary arrives
            # whenever a Home-identification deadlock is what blocks departure.
            self._processed_home_items.clear()
            self._equipment_optimization_signature = None
            self._equipment_optimization_preparation = None

        if snapshot.in_town:
            self._returning_to_town = False
            if snapshot.floor_key != self._floor_key:
                # A fresh town visit retries the store: an earlier give-up (e.g.
                # an unaffordable lantern) must not block buying the rations this
                # return trip is for. The in-store bail-outs re-bound any retry.
                # Destruction failures are likewise scoped to one expedition;
                # preserving the watch during the visit lets unchanged attempts
                # reach their retry limit instead of being resent forever.
                self._undestroyable_sigs.clear()
                self._destroy_watch = None
                self._destroy_fail_streak = 0
                self._shopping_abandoned = False
                self._town_store_attempted.clear()
                self._digger_home_withdraw_failures = 0
                self._digger_fallback_bought_this_visit = False
                self._home_procurement_withdraw_failure = None
                self._unsellable_items.clear()
                self._store_sale_refused.clear()
                self._store_sell_attempt = None
                self._batch_sell_pending = None
                self._home_candidate_waiting = True
                self._deferred_home_items.clear()
                getattr(self, "_deferred_home_item_sites", {}).clear()
                getattr(self, "_home_pending_quantities", {}).clear()
                self._home_procurement_batch_active = False
                self._town_unidentifiable_carried_sigs.clear()
                self._town_supplier_stock_observations.clear()
                self._deferred_device_items.clear()
                self._retried_home_identification_items.clear()

            if snapshot.yeek_cave_conquered and self._yeek_victory_loot:
                self._yeek_victory_loot = False
                self._yeek_conquest_processed = True

        if snapshot.floor_key != self._floor_key:
            # Bind before clearing per-floor policy state: on a real transition
            # the ledger still references the old counters and must flush them
            # before it creates the fresh current-floor state.
            self._exploration_ledger.bind(snapshot)
            self._emergency_return_active = False
            self._q2_reconnect_recovery_floor = (
                snapshot.floor_key
                if previous_floor is None and snapshot.floor_key[2] == 2
                else None
            )
            self._equipment_optimization_timed_out_this_visit = False
            self._pending_recall_dungeon_id = None
            self._town_recall_issue_watch = None
            self._town_visit_purchases.clear()
            self._town_visit_sale_signatures.clear()
            self.town_visit_report = None
            self._quest_light_attempted.clear()
            self._q2_phase_light_attempted.clear()
            self._q2_phase_visited_goals.clear()
            self._q2_phase_route_targets.clear()
            self._q2_phase_last_move = None
            self._q2_phase_step_failures.clear()
            self._q2_phase_blocked_steps.clear()
            self._q2_speed_attempted.clear()
            self._q2_surveyed_placements.clear()
            self._q2_residual_surveyed_races.clear()
            self._q2_final_patrol_visited.clear()
            self._q2_final_patrol_target = None
            self._q2_breeder_last_seen = None
            self._q2_breeder_last_seen_floor = None
            self._q2_cleared_races.clear()
            self._q2_breach_attempts = 0
            self._q2_breach_complete = False
            self._q2_blue_recovery_complete = False
            self._q2_blue_recovery_pickup_prepared = None
            self._q2_blue_recovery_pickup_posted = None
            self._q2_blue_recovery_witnessed = False
            self._launcher_enchant_attempted.clear()
            self._launcher_enchant_watch = None
            self._visit_counts.clear()
            self._recent.clear()
            self._osc_positions.clear()
            self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
            self._pending_one_step_explore = None
            self._one_step_explore_failures.clear()
            self._one_step_explore_signatures.clear()
            self._unenterable_explore_goals.clear()
            self._window_edge_goals.clear()
            self._window_edge_fallback_pending = False
            self._engagement_avoid_cells.clear()
            self._engagement_owned_avoid_cells.clear()
            self._warning_refused_cells.clear()
            self._warning_step_pending = None
            self._probe_counts.clear()
            self._dark_goal_counts.clear()
            self._clear_dark_route()
            self._floor_trap_disarm_attempts.clear()
            self._door_attempts.clear()
            self._blocked_doors.clear()
            self._blocked_unknown.clear()
            self._dig_attempts.clear()
            self._blocked_rubble.clear()
            self._search_counts.clear()
            self._wall_search_counts.clear()
            self._visit_counts = self._exploration_ledger.visit_counts
            self._probed_frontiers = self._exploration_ledger.probed_frontiers
            self._search_counts = self._exploration_ledger.search_counts
            self._wall_search_counts = self._exploration_ledger.wall_search_counts
            self._blocked_unknown = self._exploration_ledger.blocked_unknown
            self._fruitless_disengage_marked_high = (
                self._exploration_ledger.marked_high
            )
            self._escape_state.release()
            self._remembered_floor_t.clear()
            self._remembered_door_t.clear()
            self._remembered_rubble_t.clear()
            self._remembered_wall_t.clear()
            self._remembered_known_t.clear()
            self._remembered_marked_t.clear()
            self._remembered_downstairs.clear()
            self._remembered_upstairs.clear()
            self._remembered_entrances.clear()
            self._pending_stair_command = None
            self._stair_rejection_strikes.clear()
            self._unverified_stairs.clear()
            self._known_treasure.clear()
            self._treasure_target = None
            self._mining_mark_bumps.clear()
            self._mining_unmarkable_grids.clear()
            self._mining_detection_centers.clear()
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_navigation_visits.clear()
            self._mining_oscillation_retargets = 0
            self._mining_sweep_done = False
            self._mining_viability_pending_floor = None
            self._mining_sweep_steps = 0
            self._mining_sweep_no_progress = 0
            self._mining_sweep_revealed_grids = 0
            self._mining_sweep_goal = None
            self._mining_sweep_goal_distance = None
            self._mining_sweep_escape_pairs.clear()
            self._mining_swept_dead_targets.clear()
            self._mining_grids_at_sweep_done = 0
            self._mining_dropped_veins.clear()
            self._mining_veins_collected = 0
            self._mining_veins_dropped = 0
            self._mining_target_distance = None
            self._mining_target_revealed_grids = 0
            self._mining_target_collected = 0
            self._chest_position = None
            self._chest_phase_counts = {}
            self._chest_drop_origin = None
            self._chest_collecting = False
            self._chest_preopen_objects = None
            self._processed_chest_positions.clear()
            self._known_loot.clear()
            self._loot_target = None
            self._deferred_loot.clear()
            self._loot_defer_blocker = None
            self._remembered_paralyzers.clear()
            self._pending_loot_pickup = None
            self._multiplier_target = None
            self._multiplier_target_grace = 0
            if (
                self._choke_engagement_plan is not None
                and self._choke_engagement_plan.floor != snapshot.floor_key
            ):
                self._release_choke_plan("floor-change")
            self._clear_unseen_retreat()
            self._breeder_breakthrough_floor = None
            self._breeder_engagement_start_count = None
            self._breeder_engagement_start_turn = None
            self._breeder_kills = 0
            self._breeder_previous_exp = None
            self._breeder_previous_indices.clear()
            # A blocked-town/fundraising reason latches a permanent WAIT (which
            # then trips the loop-detector and stops the bot). Several of those
            # conditions are transient (a shop temporarily out of food, the inn
            # not yet in view, home briefly full); clear the latch on any floor
            # change so a fresh visit re-attempts instead of ending the run.
            self._town_blocked_reason = None
            self._floor_key = snapshot.floor_key
            self._last_position = None
            self._rest_count = 0
            self._last_hp = None  # HP is not comparable across floors
            # R1: navigation progress accounting is per floor visit.
            self._nav_ledger.reset()
            self._nav_stall_count = 0
            self._nav_exhausted = False
            self._nav_escape_steps = 0
            self._nav_known_high = 0
            self._nav_progress_marker = None
            self._oscillation_outcome_marker = None
            self._choke_outcome_floor = snapshot.floor_key
            self._choke_outcome_budgets.clear()
            self._breeder_choke_attempt_ended_floor = None

        if self._descent_block_countdown > 0:
            self._descent_block_countdown -= 1

        # Attribute an HP drop only when the game names a hidden monster's blow.
        hp = snapshot.player.hp
        self._took_damage = self._last_hp is not None and hp < self._last_hp
        self._unseen_attack_evidence = next(
            (
                message
                for message in snapshot.messages
                if self._took_damage and self._is_unseen_attack_message(message)
            ),
            None,
        )
        self._took_curse_damage = self._took_damage and any(
            " drains HP from you!" in message
            or " drains life from you!" in message
            or "あなたの体力を吸収した" in message
            for message in snapshot.messages
        )
        self._took_trap_or_terrain_damage = self._took_damage and any(
            message in {
                "トラップが作動してしまいました！",
                "トラップを作動させてしまった！",
                "You set off a trap!",
                "熱で火傷した！",
                "The heat burns you!",
                "冷気に覆われた！",
                "The cold engulfs you!",
                "電撃を受けた！",
                "The electricity shocks you!",
                "酸が飛び散った！",
                "The acid melts you!",
                "毒気を吸い込んだ！",
                "The gas poisons you!",
                "溺れている！",
                "You are drowning!",
            }
            or "を作動させてしまった！" in message
            or message.startswith("You set off the ")
            or "で火傷した！" in message
            or " burns you!" in message
            or "に凍えた！" in message
            or " frostbites you!" in message
            or "に感電した！" in message
            or " shocks you!" in message
            or "に溶かされた！" in message
            or " melts you!" in message
            or "に毒された！" in message
            or " poisons you!" in message
            for message in snapshot.messages
        )
        self._last_damage_amount = (
            self._last_hp - hp if self._took_damage and self._last_hp is not None else 0
        )
        self._last_hp = hp

        position = snapshot.player.position
        self._observe_one_step_explore(snapshot)
        self._position_changed = (
            self._last_position is not None and position != self._last_position
        )
        if position != self._last_position:
            self._visit_counts[position] += 1
            self._last_position = position
        self._recent.append(position)

        if self._pending_loot_pickup is not None:
            pickup_floor, pickup_position, pickup_count = self._pending_loot_pickup
            if pickup_floor == snapshot.floor_key:
                pickup_grid = snapshot.grid_at(pickup_position)
                if pickup_grid is not None and pickup_grid.object_count >= pickup_count:
                    self._deferred_loot.add(pickup_position)
                    if self._loot_target == pickup_position:
                        self._loot_target = None
            self._pending_loot_pickup = None

        treasure_before_observation = set(self._known_treasure)
        for grid in snapshot.grids.values():
            if grid.has_gold:
                self._known_treasure.add(grid.position)
            elif (
                grid.position in self._known_treasure
                and position.distance_to(grid.position) <= 1
            ):
                # Gold gone with us standing next to it: we mined/picked it.
                self._known_treasure.discard(grid.position)
                self._mining_dropped_veins.discard(grid.position)
                self._mining_veins_collected += 1
                if self._treasure_target == grid.position:
                    self._treasure_target = None
            # CAVE_UNSAFE means trap detection has not covered this grid.  The
            # bot already traverses such grids during ordinary exploration, so
            # it must not make otherwise reachable floor loot invisible.
            if grid.object_count > 0:
                self._known_loot.add(grid.position)
            elif grid.position in self._known_loot and (
                position.distance_to(grid.position) <= 1
            ):
                self._known_loot.discard(grid.position)
                self._deferred_loot.discard(grid.position)
                if (
                    self._loot_defer_blocker == "navigation-ledger:loot"
                    and not self._deferred_loot
                ):
                    self._loot_defer_blocker = None
                if (
                    self._loot_defer_blocker == "paralyzer-ring"
                    and not (self._deferred_loot & self._paralyzer_avoid_cells)
                ):
                    self._loot_defer_blocker = None
                if self._loot_target == grid.position:
                    self._loot_target = None
        if self._known_treasure - treasure_before_observation:
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_oscillation_retargets = 0

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
        if launcher is None:
            return 0
        return sum(
            it.count for it in snapshot.inventory if it.tval == launcher.ammo_tval
        )






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

    def _find_light_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: (
                self._is_spare_lantern(snapshot, it)
                or (it.is_torch and it.count > TORCH_THROW_TARGET)
            )
            and self._retention_surplus(snapshot, it) > 0
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )


    def _verified_destroy_key(self, snapshot: Snapshot, finder, reason: str) -> str | None:
        """Destroy a selected item while detecting refused or stalled attempts."""
        disposable = finder(snapshot)
        while disposable is not None:
            if not self._entire_stack_is_surplus(snapshot, disposable):
                return None
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
                    disposable = finder(snapshot)
                    continue
            else:
                self._destroy_watch = watch
                self._destroy_fail_streak = 0
            self.last_reason = reason
            return self._destroy_item_key(disposable)
        self._destroy_watch = None
        self._destroy_fail_streak = 0
        return None

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

    def _cheapest_exchange_item(self, snapshot: Snapshot) -> InventoryItem | None:
        candidates = [
            item
            for item in snapshot.inventory
            if not item.is_recall_scroll
            and self._entire_stack_is_surplus(snapshot, item)
            and item_base_cost(item, self._baseitem_costs) is not None
            and self._item_signature(item) not in self._undestroyable_sigs
        ]
        return min(
            candidates,
            key=lambda item: (item_base_cost(item, self._baseitem_costs), item.slot),
            default=None,
        )


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

    def _find_light(self, snapshot: Snapshot) -> InventoryItem | None:
        light = max(
            (item for item in snapshot.inventory if self._is_usable_light(item)),
            key=self._light_rank,
            default=None,
        )
        if light is not None:
            return light
        # Dungeon-found lights are unidentified, so their fuel is hidden (reads
        # as 0). With nothing else to light the way, wielding one is strictly
        # better than walking in the dark — the exact failure mode that killed
        # the torch-carrying Half-Troll.
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
            return self._find_light(snapshot)
        candidate = self._find_light(snapshot)
        if candidate is None:
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
            and item.known
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
        self._dark_route_goal = None
        self._dark_route_expected = None



    def _darkness_torch(self, snapshot: Snapshot) -> InventoryItem | None:
        return max(
            (
                item
                for item in snapshot.inventory
                if item.is_light
                and item.sval == SV_LITE_TORCH
                and item.known
                and item.fuel > 0
            ),
            key=lambda item: item.fuel,
            default=None,
        )

    def _darkness_recovery_key(self, snapshot: Snapshot) -> str | None:
        if not self._is_dark(snapshot):
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

    @staticmethod
    def _store_item_is_supply(item: StoreItem, kind: str) -> bool:
        if kind == "recall":
            return item.is_recall_scroll
        if kind == "teleport":
            return item.is_teleport_scroll
        if kind == "cure":
            return item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL
        if kind == "oil":
            return item.is_oil
        if kind == "food":
            return item.tval == TVAL_FOOD and item.sval >= FOOD_MIN_SVAL
        return False





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
        return any(it.is_digging_tool for it in snapshot.inventory) or any(
            it.is_digging_tool for it in snapshot.equipment
        )

    @staticmethod
    def _digging_tool_count(snapshot: Snapshot) -> int:
        return sum(it.count for it in snapshot.inventory if it.is_digging_tool) + sum(
            1 for it in snapshot.equipment if it.is_digging_tool
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
        """Reject recall when its landing floor violates mandatory depth gates."""
        depth = self._dungeon_entry_depth(snapshot, dungeon_id, via_recall=True)
        return not self._missing_required_abilities(snapshot, depth)

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



    # ---- P1 unequipped calibration phase (execution layer) -----------------
    #
    # Reachable exit from every phase state (roadmap P1 requirement 6):
    #   deposit  -> strip (pack drained / enough free slots), or abort
    #   strip    -> capture (session complete), or abort (session abandoned /
    #               precondition break)
    #   capture  -> done (constants cached) or abort (structural / break)
    #   restore-equip    -> restore-supplies / None (session complete), or a
    #               fresh abort attempt rebuilds it (bounded by the abort
    #               counter); when the counter latches the visit blocked, the
    #               phase clears and the pre-existing town-blocked machinery
    #               owns the state.
    #   restore-supplies -> None (queue drained, item deferred, or Home proved
    #               blocked for this visit by T3).
    # An abort always attempts to re-wear what was taken off; the departure
    # gates stay closed while a phase or the restore queue is live. If Home
    # itself becomes T3-blocked, departure stays closed because no full
    # catalog result exists; the ordinary town terminal exposes that refusal.

    def _current_pinned_identities(
        self, snapshot: Snapshot
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (item.slot, equipment_identity(item))
                for item in snapshot.equipment
                if item.is_equipment and item.is_cursed
            )
        )

    def _outstanding_equipment_work(self) -> bool:
        """Return whether equipment work still owns a route to Home.

        This scope describes work that remains, not why optimization is stuck.
        In particular, optimizer success can open the transaction that applies
        its result; that success must not revoke the Home allowance the new
        session needs to execute.
        """
        preparation = self._equipment_optimization_preparation
        blockers = getattr(preparation, "blockers", ())
        optimization_already_applied = self._optimization_already_applied(preparation)
        return bool(
            (blockers and not optimization_already_applied)
            or self._equipment_transaction_session is not None
            or self._home_pending_item is not None
            or self._home_pending_batch
            or self._home_atomic_withdraw_pending is not None
            or self._home_atomic_deposit_pending is not None
            or self._calibration_restore_signatures
        )

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
        """Bounded diagnostics for calibration's current town refusal."""
        blocker = None
        if not snapshot.in_town:
            blocker = "not-in-town"
        elif snapshot.store is not None:
            blocker = "inside-store"
        elif snapshot.player.class_id != PLAYER_CLASS_WARRIOR:
            blocker = "not-warrior"
        elif self._calibration_phase is not None:
            if STORE_HOME in self._town_visit_ledger.blocked_stores:
                blocker = "home-visit-blocked"
        elif self._calibration_blocked_this_visit:
            blocker = "visit-blocked"
        elif self._calibration_restore_signatures:
            blocker = "restore-queue-without-phase"
        elif not self._equipment_catalog.home_scan_complete:
            blocker = "home-scan-incomplete"
        elif self._validated_character_calibration(snapshot) is not None:
            blocker = "calibration-valid"
        elif any(monster.hostile for monster in snapshot.visible_monsters):
            blocker = "calibration-preconditions"
        elif not self._home_available(snapshot):
            blocker = "home-unavailable"
        elif self._equipment_transaction_session is not None:
            blocker = "equipment-transaction-active"
        elif self._identification_need_actionable(snapshot):
            blocker = "identification-active"
        elif self._home_pending_item is not None:
            blocker = "home-item-pending"
        elif self._home_pending_batch:
            blocker = "home-batch-pending"
        elif self._home_atomic_withdraw_pending is not None:
            blocker = "home-withdraw-inflight"
        recorded = getattr(self, "_calibration_entry_refusal", None)
        if recorded is not None and recorded[0] == self._decision_sequence:
            blocker = recorded[1]
        state: dict[str, object] = {
            "phase": (
                self._calibration_phase or self._calibration_suspended_phase
            ),
            "entry_blocker": blocker,
        }
        if self._calibration_last_abort is not None:
            state["last_abort"] = self._calibration_last_abort
        return state

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
        self._equipment_transaction_session = session
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
                self.calibration_entry_state(snapshot)
                if snapshot is not None
                else {
                    "phase": self._calibration_phase,
                    "entry_blocker": None,
                }
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
        if key == PICKUP_KEY and getattr(
            self, "_q2_blue_recovery_pickup_prepared", None
        ):
            self._q2_blue_recovery_pickup_posted = (
                self._q2_blue_recovery_pickup_prepared
            )
            self._q2_blue_recovery_pickup_prepared = None
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
            if key != self._equipment_transaction_prepared_key:
                return True
        if key == "~9\x1b\x1b":
            self._home_knowledge_scan_requested = True
            self._home_knowledge_scan_inflight = True
            return True
        if key == CHARACTER_DUMP_MACRO and self._calibration_naked_dump_prepared:
            self._calibration_naked_dump_prepared = False
            self._calibration_naked_dump_requested = True
            self._calibration_naked_dump_inflight = True
            return True
        if key != self._equipment_transaction_prepared_key:
            return mutation_committed
        session = self._equipment_transaction_session
        committed = session is not None and session.confirm_posted(key)
        if committed and self._equipment_transaction_prepared_catalog_update is not None:
            kind, item, intent = self._equipment_transaction_prepared_catalog_update
            if kind == "deposit":
                self._equipment_catalog.record_home_deposit(item, intent=intent)
        self._equipment_transaction_prepared_key = None
        self._equipment_transaction_prepared_catalog_update = None
        return committed or mutation_committed

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
        self._abandon_blocked_equipment_transaction(snapshot)
        self.last_reason = "equipment-transaction:confirmation-stall-bound"
        return True



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

    def _town_departure_ready(
        self, snapshot: Snapshot, ignore_free_slots: bool = False
    ) -> bool:
        if snapshot.player.class_id < 0:
            return True
        return all(
            self._town_departure_conjuncts(
                snapshot, ignore_free_slots=ignore_free_slots
            ).values()
        )

    def _town_departure_conjuncts(
        self, snapshot: Snapshot, *, ignore_free_slots: bool = False
    ) -> dict[str, bool]:
        """Evaluate and name every leaf of the ordinary town departure gate."""
        player = snapshot.player
        free_slots_ok = (
            ignore_free_slots
            or self._town_pack_space_ready(snapshot)
        )

        home_required = self._home_available(snapshot)
        return {
            "recall_departure_ready": self._recall_departure_ready(snapshot),
            # A calibration-stripped character must be re-dressed (by the
            # restore session or a completed optimizer transaction) before ANY
            # departure path — including every pre-existing escape valve
            # deeper in this conjunction — can open.
            "calibration_loadout_restored": not self._calibration_stripped_unrestored,
            "food_ready": (
                self._fundraising_food_ready(snapshot)
                if self._fundraising_mode in {"prepare", "mine", "scavenge"}
                else self._food_ready(snapshot)
            ),
            "light_ready": self._light_ready(snapshot),
            "quest_carry_ready": (
                self._fundraising_mode in {"mine", "scavenge"}
                or (strategy := self._carry_procurement_strategy(snapshot)) is None
                or all(
                    bool(status["ready"])
                    or name in self._abandoned_quest_carry_requirements
                    for name, status in self._quest_carry_status(
                        snapshot, strategy.required_force
                    ).items()
                )
            ),
            "teleport_ready": self._teleport_ready(snapshot),
            "cure_critical_ready": self._cure_critical_ready(snapshot),
            "identify_staff_ready": self._identify_staff_ready(snapshot),
            "teleport_items_safe": not any(
                self._blocks_teleport(item)
                for item in (*snapshot.inventory, *snapshot.equipment)
            ),
            "free_pack_slots_ready": free_slots_ok,
            "inventory_weight_ready": not self._inventory_overweight(snapshot),
            "hp_full": player.hp >= player.max_hp,
            "mp_full": player.mp >= player.max_mp,
            "temporary_status_clear": self._temporary_status_clear(snapshot),
            "organization_complete": (
                self._find_town_organization_surplus(snapshot) is None
            ),
            "equipment_departure_ready": self._equipment_departure_ready(snapshot),
            "home_candidate_resolved": (
                not home_required or not self._home_candidate_waiting
            ),
            # A bounded Home pass can end with the page catalog still
            # incomplete. Once Home is blocked, defer unroutable catalog work.
            "home_catalog_ready": not home_required or (
                self._equipment_catalog.home_scan_complete
                or not self._home_catalog_routable(snapshot)
            ),
            "home_pending_item_clear": (
                not home_required or self._home_pending_item is None
            ),
            "home_pending_batch_clear": (
                not home_required or not self._home_pending_batch
            ),
            "home_batch_review_clear": (
                not home_required or not self._home_batch_review_items
            ),
            "home_atomic_withdraw_clear": (
                self._home_atomic_withdraw_pending is None
            ),
            "digger_withdrawal_resolved": (
                not self._home_digger_withdraw_pending
                or self._digger_fallback_bought_this_visit
            ),
            "identification_need_clear": (
                not home_required or self._identification_need is None
            ),
            # Never depart mid-calibration or with its supplies still at Home.
            "calibration_phase_complete": (
                not home_required or not self._calibration_active()
            ),
            "calibration_restore_complete": (
                not home_required or not self._calibration_restore_signatures
            ),
        }

    def _town_pack_space_ready(self, snapshot: Snapshot) -> bool:
        """Accept four slots only after the town pipeline exhausted this pack."""
        free_slots = PACK_CAPACITY - len(snapshot.inventory)
        if free_slots >= MIN_FREE_PACK_SLOTS:
            return True
        if not snapshot.in_town or free_slots < MIN_TERMINAL_FREE_PACK_SLOTS:
            return False
        return self._terminal_pack_space_signature == self._town_pack_space_signature(
            snapshot
        )

    def _recall_town_departure_conjuncts(self, snapshot: Snapshot) -> dict[str, bool]:
        """Return the complete leaf set consumed by a town recall decision."""
        values = self._town_departure_conjuncts(snapshot)
        values.update(
            {
                "combat_weapon_ready": self._combat_weapon_ready(snapshot),
                "departure_home_pending_item_clear": self._home_pending_item is None,
                "departure_home_pending_batch_clear": not self._home_pending_batch,
                "departure_home_batch_review_clear": not self._home_batch_review_items,
                "departure_home_atomic_withdraw_clear": (
                    self._home_atomic_withdraw_pending is None
                ),
                "departure_identification_need_clear": (
                    self._identification_need is None
                ),
            }
        )
        return values

    @staticmethod
    def _town_pack_space_signature(
        snapshot: Snapshot,
    ) -> tuple[tuple[object, ...], ...]:
        """Return the exact inventory state certified by the terminal fallback."""
        return tuple(
            (item.slot, item.name, item.tval, item.sval, item.count)
            for item in snapshot.inventory
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
        if (
            STORE_HOME in self._town_visit_ledger.blocked_stores
            and (preparation is None or preparation.result is None)
        ):
            return "equipment-home-unavailable"
        if (
            preparation is not None
            and "optimization-timeout" in preparation.blockers
            and not self._equipment_departure_ready(snapshot)
        ):
            return "equipment-optimization-timeout"
        if (
            preparation is None
            or self._next_required_store_type(snapshot) is not None
        ):
            return None
        if "calibration-required" in preparation.blockers:
            return "equipment-calibration-required"
        if "no-valid-loadout" in preparation.blockers:
            return "equipment-no-valid-loadout"
        if "incomplete-equipment-catalog" in preparation.blockers:
            return "equipment-incomplete-catalog"
        return None

    def _activate_safe_recall_fallback(self, snapshot: Snapshot) -> int | None:
        """Select the shallowest entered dungeon when the current recall is unsafe."""
        alternate = self._pick_alternate_dungeon(
            snapshot,
            max_entry_depth=max(1, snapshot.recall_depth - 1),
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
        if self._calibration_active():
            return False
        preparation = self._equipment_optimization_preparation
        if preparation is None:
            return False
        result = getattr(preparation, "result", None)
        best = getattr(result, "best", None)
        return getattr(best, "loadout", None) is not None










    def _release_staged_store_operation(self, snapshot: Snapshot) -> str | None:
        """Release the one bound tail after its matching store page is fresh."""
        visit = self._store_visit
        if (
            snapshot.store is None
            or visit is None
            or not visit.operation_posted
            or visit.operation_released
            or visit.operation_key is None
            or snapshot.store.store_type != visit.store_type
            or visit.posted_turn is None
            or snapshot.turn < visit.posted_turn
        ):
            return None
        visit.transition(StoreVisitPhase.OPERATING)
        visit.operation_released = True
        return visit.operation_key


    def _is_surplus_digging_tool(self, snapshot: Snapshot, item: InventoryItem) -> bool:
        """Keep the best two carried tools; permit excess deposit/disposal."""
        if not item.is_digging_tool:
            return False
        equipped_count = sum(
            1 for equipped in snapshot.equipment if equipped.is_digging_tool
        )
        pack_diggers = [it for it in snapshot.inventory if it.is_digging_tool]
        pack_capacity = max(0, 2 - equipped_count)
        if len(pack_diggers) <= pack_capacity:
            return False
        keep_slots = {
            candidate.slot
            for candidate in sorted(
                pack_diggers,
                key=self._digging_tool_sale_quality,
                reverse=True,
            )[:pack_capacity]
        }
        return item.slot not in keep_slots

    @staticmethod
    def _digging_tool_sale_quality(item: InventoryItem) -> tuple[int, int, int, int]:
        return (
            item.pval,
            int(item.is_artifact),
            int(item.is_ego),
            item.sval,
        )

    def _sale_retains_digging_tool(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> bool:
        if not item.is_digging_tool:
            return False
        quality = self._digging_tool_sale_quality(item)
        available = [
            *[it for it in snapshot.inventory if it.is_digging_tool],
            *[it for it in snapshot.equipment if it.is_digging_tool],
            *[
                owned.item
                for owned in self._equipment_catalog.items
                if owned.origin == "home"
                and owned.item.is_digging_tool
                and self._item_signature(owned.item) not in self._deferred_home_items
            ],
        ]
        better_count = sum(
            candidate.count
            for candidate in available
            if self._digging_tool_sale_quality(candidate) > quality
        )
        return better_count < 2


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

    def _find_book_sale(
        self, snapshot: Snapshot, store_type: int | None = None
    ) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda item: self._book_sale_store_type(item) is not None
            and (store_type is None or self._book_sale_store_type(item) == store_type)
            and (item.name, item.tval, item.sval) not in self._unsellable_items,
        )

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
            and not self._survival_essential(item)
            and not self._is_useful_device(item)
            and not self._has_town_economic_path(item)
            and self._item_signature(item) not in self._undestroyable_sigs,
        )

    def _town_overflow_destroy_key(self, snapshot: Snapshot) -> str | None:
        """Free town pack space without creating floor-item pickup loops."""
        return self._verified_destroy_key(
            snapshot,
            self._overflow_disposal_item,
            "town:destroy-overflow",
        )

    @staticmethod
    def _item_signature(item: InventoryItem | StoreItem) -> tuple[str, int, int]:
        return (item.name, item.tval, item.sval)

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

    def validate_read_key(self, snapshot: Snapshot, key: str) -> str:
        """Rebind a composed read to its intended scroll in the acting snapshot."""
        if not key.startswith(READ_KEY) or len(key) < 2 or self._read_binding is None:
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


    def _town_device_processing_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town:
            return None
        target = self._first_item(
            snapshot,
            lambda item: self._normal_identification_flow_candidate(item)
            and not item.is_equipment
            and self._item_signature(item) not in self._deferred_device_items,
        )
        if target is None:
            return None
        source = self._find_identification_source(
            snapshot, full=False, reliable_only=True
        )
        if source is None:
            self._request_identification("normal")
            self._device_identification_candidate = self._item_signature(target)
            return None
        # Verify the identify lands: if the same device is still unknown and the
        # unknown-device count has not moved, the staff/scroll use did not take
        # (a stalled prompt) — defer it after a few tries rather than looping.
        unknown_devices = sum(
            1
            for it in snapshot.inventory
            if self._normal_identification_flow_candidate(it)
            and not it.is_equipment
        )
        watch = (self._item_signature(target), unknown_devices)
        if watch == self._device_identify_watch:
            self._device_identify_fail_streak += 1
            if self._device_identify_fail_streak >= IDENTIFY_FAIL_LIMIT:
                self._deferred_device_items.add(self._item_signature(target))
                self._device_identify_watch = None
                self._device_identify_fail_streak = 0
                return None
        else:
            self._device_identify_watch = watch
            self._device_identify_fail_streak = 0
        command, item = source
        self._identification_need = None
        self._device_identification_candidate = None
        self.last_reason = "identify:device"
        if command == READ_KEY:
            return self._read_key(snapshot, item, target.slot)
        return command + item.slot + target.slot

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


    def _find_device_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        reserve_slot = self._device_food_reserve_slot(snapshot)
        if self._home_identify_staff_sale_pending:
            # Home compaction destroys the withdrawn object's slot identity, but
            # it must not destroy any of the ordinary sale obligations.  Reuse
            # the single surplus selector, including same-visit retention.
            return self._find_surplus_identify_staff(
                snapshot, pending_home_sale=True
            )
        surplus_identify_staff = self._find_surplus_identify_staff(snapshot)
        surplus_slot = (
            surplus_identify_staff.slot
            if surplus_identify_staff is not None
            else None
        )
        return self._first_item(
            snapshot,
            lambda item: self._retention_surplus(snapshot, item) > 0
            and item.known
            and (
                item.slot == surplus_slot
                or
                (item.tval in {TVAL_WAND, TVAL_STAFF} and not self._is_useful_device(item))
                # A Rod of Light is redundant beside the lantern; sell it too. Only
                # this sval is listed, so useful rods (e.g. Identify) are kept.
                or (item.tval == TVAL_ROD and item.sval == SV_ROD_LITE)
            )
            and (item.slot != reserve_slot or item.slot == surplus_slot)
            and (item.name, item.tval, item.sval) not in self._unsellable_items,
        )

    def _request_identification(self, kind: str) -> None:
        if kind == "normal" and self._identification_need != kind:
            # Basic Identify is ordinary Alchemist stock. Re-arm both the coarse
            # attempted latch and the bounded errand plan for newly requested
            # normal-tier work. *Identify* is not sold there, so a full-tier
            # escalation must preserve the exhausted-store latch.
            self._rearm_town_store_for_new_work(STORE_ALCHEMIST)
        self._identification_need = kind





    def _town_item_processing_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town:
            return None
        self._activate_home_batch_item()
        if self._home_pending_item is None:
            target = self._first_item(
                snapshot,
                # The optimizer catalogs every carried equipment item, not only
                # jewellery. Select from that same domain dynamically: prime()'s
                # startup batch cannot see an ego weapon acquired later in the
                # run, which caused the 2026-07-20 incomplete-catalog deadlock.
                lambda item: item.is_equipment
                and self._item_signature(item) not in self._deferred_home_items
                and self._item_signature(item) not in self._unidentifiable_sigs
                and self._item_signature(item)
                not in self._town_unidentifiable_carried_sigs
                and self._identification_flow_candidate(item),
            )
            if target is None:
                return None
            full = target.known
            key = self._carried_identify_command(snapshot, target, full=full)
            if key is None:
                if (
                    self._item_signature(target) in self._unidentifiable_sigs
                    or self._item_signature(target)
                    in self._town_unidentifiable_carried_sigs
                ):
                    return None
                signature = self._item_signature(target)
                if full and STORE_ALCHEMIST in self._town_store_attempted:
                    self._defer_full_identification(signature)
                else:
                    self._identification_candidate = signature
                    self._request_identification("full" if full else "normal")
                return None
            self._identification_need = None
            self._identification_candidate = None
            self.last_reason = "identify:full" if full else "identify:normal"
            return key
        if self._home_withdrawal_queued:
            # The in-store chooser has selected a Home identity, but the atomic
            # composer has not withdrawn it yet.  Surface item processing runs
            # before the Home approach owner, and an already-carried stack may
            # have the same name/tval/sval signature as the stored stack.  Do
            # not mistake that pre-existing stack for withdrawal success.  A
            # posted atomic command clears this queued state before the newly
            # observed inventory may be processed.
            return None
        target = self._pending_inventory_item(snapshot)
        if target is None:
            # The Home command can be rejected (for example by a prompt timing
            # mismatch). Do not alternate forever between leaving and re-entering
            # the store: defer this candidate for the current town visit and let
            # higher-priority resupply/fundraising continue.
            self._defer_home_item(
                self._home_pending_item, "town-item-processing-missing-pending"
            )
            self._release_identification_source_reservation(self._home_pending_item)
            self._home_pending_item = None
            self._home_pending_slot = None
            self._home_active_from_batch = False
            self._identification_need = None
            self._identification_candidate = None
            self._home_candidate_waiting = not self._home_pending_batch
            self._town_blocked_reason = None
            self.last_reason = "home:withdraw-failed-deferred"
            if self._home_pending_batch:
                return self._town_item_processing_key(snapshot)
            return None
        if (
            self._home_atomic_withdraw_pending is not None
            and self._home_atomic_withdraw_pending[0] == self._home_pending_item
        ):
            self._home_atomic_withdraw_pending = None

        if not target.known and target.pseudo_feeling != "average":
            key = self._carried_identify_command(
                snapshot,
                target,
                full=False,
                reservation_target=self._home_pending_item,
            )
            if key is None:
                self._request_identification("normal")
                return None
            self._identification_need = None
            if self._identification_source_reservation is not None:
                self._identification_source_reservation["state"] = "identifying"
            self.last_reason = "identify:normal"
            return key

        if target.known and self._identification_flow_candidate(target):
            source = self._find_identification_source(
                snapshot,
                full=True,
                reservation_target=self._home_pending_item,
            )
            if source is None:
                signature = self._item_signature(target)
                if STORE_ALCHEMIST in self._town_store_attempted:
                    self._defer_full_identification(signature)
                else:
                    self._request_identification("full")
                return None
            command, item = source
            self._identification_need = None
            if self._identification_source_reservation is not None:
                self._identification_source_reservation["state"] = "identifying"
            self.last_reason = "identify:full"
            if command == READ_KEY:
                return self._read_key(
                    snapshot, item, target.slot + FULL_IDENTIFY_DISMISS_SUFFIX
                )
            return command + item.slot + target.slot + FULL_IDENTIFY_DISMISS_SUFFIX

        target_signature = self._item_signature(target)
        self._release_identification_source_reservation(self._home_pending_item)
        self._processed_home_items.add(target_signature)
        if self._home_active_from_batch:
            self._home_pending_item = None
            self._home_pending_slot = None
            self._home_active_from_batch = False
            self._identification_need = None
            self._identification_candidate = None
            self._home_candidate_waiting = False
            if self._home_pending_batch:
                return self._town_item_processing_key(snapshot)
            self.last_reason = "identify:batch-complete"
            return None

        self._home_pending_item = None
        self._home_pending_slot = None
        self._home_active_from_batch = False
        self._identification_need = None
        self._identification_candidate = None
        self._home_candidate_waiting = not self._home_pending_batch
        if self._home_pending_batch:
            self.last_reason = "home:process-next-batch-item"
            return WAIT_KEY
        self.last_reason = "identify:complete"
        return None

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

    @staticmethod
    def _carried_restore_potion(
        snapshot: Snapshot, stat: str
    ) -> InventoryItem | None:
        sval = RESTORE_POTION_SVAL_BY_STAT.get(stat)
        if sval is None:
            return None
        # Only an AWARE potion has an emitted sval (fair-play redacts the unknown);
        # an unidentified restore potion is not yet actionable.
        return next(
            (
                item
                for item in snapshot.inventory
                if item.is_potion and item.aware and item.sval == sval
            ),
            None,
        )

    def _needs_stat_restore(self, snapshot: Snapshot) -> bool:
        # A stat is drained (cur < max, shown on the character screen) and we have
        # no restore potion in the pack for it — a reason to visit the Alchemist.
        return any(
            self._carried_restore_potion(snapshot, stat) is None
            for stat in snapshot.player.drained_stats
        )

    def _restore_potion_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None:
            return None
        gold = snapshot.player.gold
        for stat in snapshot.player.drained_stats:
            if self._carried_restore_potion(snapshot, stat) is not None:
                continue  # already carry one to quaff; do not buy a second
            sval = RESTORE_POTION_SVAL_BY_STAT.get(stat)
            item = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_POTION and it.sval == sval and it.price <= gold
                ),
                None,
            )
            if item is not None:
                return item
        return None

    def _stat_restore_quaff_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        # Undo a drained ability by quaffing its restore potion. Only when safe
        # (no hostiles) and able to act (not confused/blind); the character screen
        # is what reveals the drain, so this uses no hidden information.
        player = snapshot.player
        if hostiles or player.confused or player.blind:
            return None
        for stat in player.drained_stats:
            potion = self._carried_restore_potion(snapshot, stat)
            if potion is not None:
                self.last_reason = f"restore:quaff-{stat}"
                return QUAFF_KEY + potion.slot
        return None

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
            return QUAFF_KEY + potion.slot
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
        disposable = disposable_dominated_item_ids(catalog, protected)
        return any(
            owned.id in disposable
            and owned.origin == "home"
            and equipment_identity(owned.item) == candidate_identity
            for owned in catalog
        )


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

    @staticmethod
    def _dominated_disposal_store(item: InventoryItem | StoreItem) -> int | None:
        for store_type in (STORE_WEAPON, STORE_ARMOURY, STORE_MAGIC, STORE_GENERAL, STORE_TEMPLE):
            if item.tval in STORE_ACCEPTED_TVALS[store_type]:
                return store_type
        return None

    def _town_destroy_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or not self._destroy_pending:
            return None
        target = self._pending_disposal(snapshot)
        if target is None:
            self._clear_pending_disposal()
            self.last_reason = "equipment:destroy-complete"
            return None
        if self._destroy_attempts >= STORE_STUCK_LIMIT:
            self._town_blocked_reason = "dominated-item-destroy-failed"
            self.last_reason = "town:blocked:dominated-item-destroy-failed"
            return WAIT_KEY
        self._destroy_attempts += 1
        self.last_reason = "equipment:destroy-unsellable-dominated"
        return self._destroy_item_key(target)


    def _find_low_level_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        sell_unknown = self._deepest_level < 20 or self._sell_scavenged_consumables
        return self._first_item(
            snapshot,
            lambda it: self._retention_surplus(snapshot, it) > 0 and (
                (
                    sell_unknown
                    and (it.is_potion or it.is_scroll)
                    and not it.aware
                )
                or (it.is_potion and it.aware and it.sval in DISPOSABLE_POTION_SVALS)
                or (it.is_scroll and it.aware and it.sval in DISPOSABLE_SCROLL_SVALS)
                or (it.known and it.is_ego and it.is_cursed and not it.is_artifact)
            )
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )


    def _effective_mining_run_target(self) -> int:
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
        self._fundraising_mode = "mine"
        return True




    def _retry_after_store_restock(
        self, snapshot: Snapshot, store_types: tuple[int, ...]
    ) -> int | None:
        """Wait for stock turnover, then make the relevant shops eligible again."""
        if self._town_restock_last_wait_turn is not None:
            self._town_restock_waited_turns += max(
                0,
                min(
                    STORE_RESTOCK_REST_GAME_TURNS,
                    snapshot.turn - self._town_restock_last_wait_turn,
                ),
            )
            self._town_restock_last_wait_turn = None
        if self._town_restock_suppressed:
            return None
        if self._town_restock_wait_until is None:
            for store_type in store_types:
                remembered = getattr(self, "_town_supplier_stock", {}).get(
                    store_type
                )
                if remembered is None:
                    continue
                purchase = self._next_purchase(replace(snapshot, store=remembered))
                if purchase is not None and purchase.price <= snapshot.player.gold:
                    self._town_store_attempted.pop(store_type, None)
                    return store_type
        self._town_restock_waiting_for = store_types
        if self._town_restock_wait_until is None:
            self._town_restock_wait_until = snapshot.turn + STORE_RESTOCK_WAIT_TURNS
            return None
        if snapshot.turn < self._town_restock_wait_until:
            return None
        self._town_restock_wait_until = None
        for store_type in store_types:
            self._town_store_attempted.pop(store_type, None)
        return store_types[0]

    def _observe_restock_supplier_page(self, snapshot: Snapshot) -> None:
        """Record a recheck only from an observed, unaffordable supplier page."""
        store = snapshot.store
        waiting_for = self._town_restock_waiting_for
        if not waiting_for or store is None or store.store_type not in waiting_for:
            return
        if set(waiting_for) == {STORE_TEMPLE, STORE_ALCHEMIST}:
            affordable = any(
                item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_WORD_OF_RECALL
                and item.price <= snapshot.player.gold
                for item in store.items
            )
            if not affordable:
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

    def _released_restock_store_key(
        self, snapshot: Snapshot, store_types: tuple[int, ...]
    ) -> str:
        """Route to a supplier made eligible by completed stock turnover."""
        food_store = (
            STORE_MAGIC
            if snapshot.player.food_type == FOOD_TYPE_MANA
            else STORE_GENERAL
        )
        released_store_types = (
            (food_store,) if not self._food_ready(snapshot) else store_types
        )
        # Every released restock supplier must get a fresh route decision.  A
        # prior terminal otherwise short-circuits _shopping_approach_step, and
        # an inert approach to another store can retain visit ownership before
        # the known town map is consulted.  Posted operations remain
        # authoritative and are deliberately not released here.
        if self._town_blocked_reason in {
            "restock-store-unreachable",
        }:
            self._town_blocked_reason = None
        visit = self._store_visit
        if (
            visit is not None
            and visit.store_type not in released_store_types
            and visit.phase == StoreVisitPhase.APPROACHING
            and not visit.operation_posted
        ):
            self._close_store_visit("restock-reroute")
        # A completed recall-stock cycle is progress evidence, not permission
        # to starve behind the same owner.  Home has already had its normal
        # first pass before terminal restock handling.  If food is still a
        # departure shortage, release its supplier before retrying recall.
        if not self._food_ready(snapshot):
            self._town_store_attempted.pop(food_store, None)
            step = self._shopping_approach_step(snapshot, food_store)
            if step is not None:
                self.last_reason = "shop:approach"
                return self._shopping_approach_key(snapshot, step, "shop:travel")
            self._town_blocked_reason = "restock-store-unreachable"
            return self._town_blocked_key(snapshot)
        step = self._shopping_approach_step(snapshot)
        if step is not None and self._shopping_approach_store_type in store_types:
            self.last_reason = "shop:approach"
            return self._shopping_approach_key(snapshot, step, "shop:travel")
        # Another live errand can precede the released suppliers in the town
        # plan.  A restock release says nothing about that errand's route, so
        # check each released supplier itself before declaring all of them
        # unreachable.
        for store_type in self._order_town_stops(snapshot, list(store_types)):
            step = self._shopping_approach_step(snapshot, store_type)
            if step is not None:
                self.last_reason = "shop:approach"
                return self._shopping_approach_key(snapshot, step, "shop:travel")
        # Recall stock still owns departure. If the released supplier cannot be
        # routed, use the existing visible town terminal instead of descending
        # or silently arming the same wait again.
        self._town_blocked_reason = "restock-store-unreachable"
        return self._town_blocked_key(snapshot)

    def _recall_restock_key(self, snapshot: Snapshot) -> str:
        """Bound recall waiting to one observed stock-turnover cycle."""
        recall_stores = (STORE_TEMPLE, STORE_ALCHEMIST)
        if (
            self._town_restock_wait_until is None
            and all(store in self._town_restock_rechecked for store in recall_stores)
        ):
            self._town_restock_waiting_for = ()
            recall = self._supply_ledger(
                snapshot, self._planned_depth()
            )["recall"]
            if recall.obtainable:
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
                        self._town_store_attempted.pop(store_type, None)
                return self._released_restock_store_key(
                    snapshot, recall_stores
                )
            if not self._food_ready(snapshot):
                return self._released_restock_store_key(snapshot, recall_stores)
            self._town_blocked_reason = "restocked-recall-unavailable"
            return self._town_blocked_key(snapshot)
        released_store = self._retry_after_store_restock(snapshot, recall_stores)
        if released_store is not None:
            return self._released_restock_store_key(snapshot, recall_stores)
        wait_cap = (
            STORE_RESTOCK_WAIT_TURNS * max(1, len(recall_stores)) * 2
        )
        if self._town_restock_waited_turns >= wait_cap:
            self._town_blocked_reason = "restock-wait-exhausted"
            return self._town_blocked_key(snapshot)
        self.last_reason = self._restock_wait_reason(snapshot)
        self._town_restock_last_wait_turn = snapshot.turn
        return RESTOCK_WAIT_MACRO

    def _town_need_candidates(self, snapshot: Snapshot) -> list[TownNeed]:
        """Mechanically evaluate the predicates backing the town need registry."""
        needs: list[TownNeed] = []
        fundraising_active = (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and snapshot.player.gold < FUNDRAISING_GOLD_TARGET
            and not self._opening_q34_active(snapshot)
        )
        star_reserve_surplus = (
            snapshot.player.gold >= FUNDRAISING_GOLD_TARGET
            and not self._recall_departure_shortage(snapshot)
        )

        def add(store_type: int, category: str, ordering_class: str = "normal") -> None:
            needs.append(TownNeed(store_type, category, ordering_class))

        if self._calibration_active():
            # The unequipped calibration phase owns the town while it runs.
            # The only legitimate errand is Home: deposits going in, the pack
            # restore coming out.  Every other need is suppressed — in
            # particular a supply purchase would feed the deposit loop its own
            # replacements (deposit -> shortage -> buy -> deposit ...).
            if (
                self._calibration_phase in {"deposit", "restore-supplies"}
                and self._home_available(snapshot)
                and STORE_HOME not in self._town_store_attempted
            ):
                add(
                    STORE_HOME,
                    "calibration-restore"
                    if self._calibration_phase == "restore-supplies"
                    else "deposit",
                    "home-first",
                )
            return needs

        if (
            self._home_disposal_pass
            and snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
        ):
            # An opportunistic scan may share an already-owned Home visit, but
            # it is not executable Home work and must never create a visit by
            # itself.  With no surface need, the errand plan advances to real
            # work/departure instead of entering, scanning, and leaving.
            add(STORE_HOME, "idle-consumable-scan", "home-first")
        if self._home_disposal_pending is not None:
            signature, decision = self._home_disposal_pending
            target = self._home_disposal_inventory_item(snapshot)
            if decision == "sell" and target is not None:
                if not target.known and self._find_identification_source(
                    snapshot, full=False, reliable_only=True
                ) is None:
                    add(STORE_ALCHEMIST, "home-disposal-identify")
                else:
                    add(self._home_disposal_store(signature), "home-disposal-sale")

        if snapshot.player.class_id < 0:
            if not self._shopping_abandoned and snapshot.player.gold >= LANTERN_MIN_GOLD:
                if not self._owns_lantern(snapshot):
                    add(STORE_GENERAL, "birth-supplies")
                if self._needs_food_restock(snapshot):
                    add(
                        STORE_MAGIC
                        if snapshot.player.food_type == FOOD_TYPE_MANA
                        else STORE_GENERAL,
                        "birth-supplies",
                    )
            return needs

        # The approved fresh-character route is intentionally tiny: acquire
        # Q34's complete throwing-torch stock, then let _fixed_quest_key accept
        # it on the next decision.  In particular, do not let low-gold
        # fundraising turn its own missing digger/detection kit into an earlier
        # Home or Alchemist stop; that created a circular readiness lock where
        # Q34 waited for torches while fundraising hid their procurement need.
        if self._opening_q34_active(snapshot):
            equipped_weapon = next(
                (item for item in snapshot.equipment if item.slot == "main_hand"),
                None,
            )
            if (
                equipped_weapon is None
                and not self._pack_has_safe_melee_weapon(snapshot)
            ):
                add(STORE_HOME, "combat-weapon", "home-first")
                return needs
        if self._opening_q34_torch_shortage(snapshot) > 0:
            add(STORE_GENERAL, "quest-throwing-items", "opening-quest")
            return needs

        self._begin_pack_dominated_launcher_disposal(snapshot)
        if (
            self._pending_disposal_item is not None
            and (target := self._pending_disposal(snapshot)) is not None
        ):
            disposal_store = self._dominated_disposal_store(target)
            if disposal_store is not None and disposal_store not in self._disposal_store_attempts:
                add(disposal_store, "disposal")
        if self._pending_disposal_item is not None:
            return needs

        equipped_weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        blocked_weapon_in_pack = any(
            item.is_melee_weapon and self._blocks_teleport(item)
            for item in snapshot.inventory
        )
        safe_weapon_equipped = (
            equipped_weapon is not None
            and equipped_weapon.is_melee_weapon
            and not self._blocks_teleport(equipped_weapon)
        )
        if (
            (
                self._no_teleport_rearm_pending
                or (equipped_weapon is not None and self._blocks_teleport(equipped_weapon))
                or (blocked_weapon_in_pack and not safe_weapon_equipped)
            )
            and not self._pack_has_safe_melee_weapon(snapshot)
        ):
            add(STORE_HOME, "safe-weapon", "home-first")
        if (
            self._equipped_digging_tool(snapshot) is not None
            and not self._pack_has_safe_melee_weapon(snapshot)
            and not self._combat_weapon_ready(snapshot)
        ):
            add(STORE_HOME, "combat-weapon", "home-first")
        book_sale = self._find_book_sale(snapshot)
        if book_sale is not None:
            add(self._book_sale_store_type(book_sale), "book-sale")
        organization = self._find_town_organization_surplus(snapshot)
        organization_store = (
            self._town_organization_sale_store(snapshot, organization)
            if organization is not None
            else None
        )
        if organization_store is not None:
            add(organization_store, "organization-sale")
        elif (
            organization is not None
            and self._identification_need is None
            and self._town_organization_home_routable(snapshot, organization)
        ):
            # Required organization remains routable during fundraising; this
            # is the existing Home deposit need and deposit machinery.
            add(STORE_HOME, "deposit", "home-first")
        if (
            self._home_available(snapshot)
            and self._inventory_overweight(snapshot)
            and self._find_home_deposit(snapshot) is not None
        ):
            add(STORE_HOME, "weight-overload", "home-first")
        elif (
            self._identification_need is None
            and self._home_available(snapshot)
            and STORE_HOME not in self._town_store_attempted
            and not fundraising_active
            and self._find_home_deposit(snapshot) is not None
        ):
            add(STORE_HOME, "deposit", "home-first")
        procurement_probe = getattr(self, "_home_procurement_probe", None)
        if procurement_probe is not None and (
            (
                procurement_probe[0] == TVAL_FOOD
                and procurement_probe[1] >= FOOD_MIN_SVAL
                and self._food_ready(snapshot)
            )
            or (
                procurement_probe[0] in {TVAL_WAND, TVAL_STAFF}
                and self._count_mana_food_devices(snapshot) > 0
            )
            or any(
                self._procurement_class_matches(item, procurement_probe)
                for item in snapshot.inventory
            )
        ):
            self._home_procurement_probe = None
            procurement_probe = None
        if (
            procurement_probe is not None
            and self._home_available(snapshot)
            and STORE_HOME not in self._town_store_attempted
        ):
            add(STORE_HOME, "procurement-home-first", "home-first")
        if self._needs_stat_restore(snapshot) and STORE_ALCHEMIST not in self._town_store_attempted:
            add(STORE_ALCHEMIST, "stat-restore")
        low_level_sale = self._find_low_level_sale(snapshot)
        if low_level_sale is not None:
            add(STORE_ALCHEMIST, "low-level-sale")
        elif (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and self._first_item(
                snapshot,
                lambda item: item.tval == TVAL_FOOD
                and self._retention_surplus(snapshot, item) > 0
                and self._item_signature(item) not in self._unsellable_items,
            )
            is not None
        ):
            add(STORE_GENERAL, "mana-food-sale")
        unknown_device = self._first_item(
            snapshot,
            lambda item: item.tval in {TVAL_WAND, TVAL_STAFF}
            and not item.known
            and self._item_signature(item) not in self._deferred_device_items,
        )
        device_processing_actionable = (
            unknown_device is not None
            and self._find_identification_source(
                snapshot, full=False, reliable_only=True
            ) is not None
        )
        if (
            not device_processing_actionable
            and self._find_device_sale(snapshot) is not None
            and STORE_MAGIC not in self._town_store_attempted
        ):
            add(STORE_MAGIC, "device-sale")
        if self._find_weapon_sale(snapshot) is not None and STORE_WEAPON not in self._town_store_attempted:
            add(STORE_WEAPON, "weapon-sale")
        if self._find_light_sale(snapshot) is not None and STORE_GENERAL not in self._town_store_attempted:
            add(STORE_GENERAL, "light-sale")

        if fundraising_active:
            if (
                self._digger_buy_fallback_available(snapshot)
                and STORE_GENERAL not in self._town_store_attempted
            ):
                add(STORE_GENERAL, "fundraising-digger")
            if not self._fundraising_kit_secured(snapshot):
                if STORE_HOME not in self._town_store_attempted:
                    add(STORE_HOME, "fundraising-kit", "home-first")
                if (
                    not self._has_withdrawable_digging_tool(snapshot)
                    or self._digger_buy_fallback_available(snapshot)
                ):
                    if STORE_GENERAL not in self._town_store_attempted:
                        add(STORE_GENERAL, "fundraising-digger")
                if not self._has_withdrawable_treasure_detection(snapshot):
                    if STORE_ALCHEMIST not in self._town_store_attempted:
                        add(STORE_ALCHEMIST, "fundraising-detection")
            if not self._fundraising_food_ready(snapshot):
                food_store = STORE_MAGIC if snapshot.player.food_type == FOOD_TYPE_MANA else STORE_GENERAL
                if food_store not in self._town_store_attempted:
                    add(food_store, "fundraising-food")
            if self._planned_mining_runs is None:
                remaining_cap = max(0, MINING_RUNS_PER_SET - self._mining_runs_completed)
                additional_runs = min(
                    remaining_cap,
                    self._count_treasure_detection_scrolls(snapshot),
                )
                planned_runs = self._mining_runs_completed + max(0, additional_runs)
            else:
                planned_runs = self._planned_mining_runs
            scrolls_needed = max(0, planned_runs - self._mining_runs_completed)
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                if STORE_HOME not in self._town_store_attempted:
                    add(STORE_HOME, "stored-detection", "home-first")
                if STORE_ALCHEMIST not in self._town_store_attempted:
                    add(STORE_ALCHEMIST, "mining-detection")
            if (
                self._fundraising_mode != "scavenge"
                and self._digging_tool_count(snapshot) < 2
                and self._count_treasure_detection_scrolls(snapshot) > 0
            ):
                if (
                    STORE_HOME not in self._town_store_attempted
                    and any(
                        owned.origin == "home" and owned.item.is_digging_tool
                        for owned in self._equipment_catalog.items
                    )
                ):
                    add(STORE_HOME, "stored-digger", "home-first")
                if (
                    STORE_GENERAL not in self._town_store_attempted
                    and (
                        self._withdrawable_digging_tool_count(snapshot) < 2
                        or self._digger_buy_fallback_available(snapshot)
                    )
                ):
                    add(STORE_GENERAL, "mining-digger")
            if not self._fundraising_light_ready(snapshot):
                if STORE_GENERAL not in self._town_store_attempted:
                    add(STORE_GENERAL, "fundraising-light")
            if (
                self._owns_lantern(snapshot)
                and self._oil_below_departure_target(snapshot)
                and STORE_GENERAL not in self._town_store_attempted
            ):
                add(STORE_GENERAL, "fundraising-oil")
            mandatory_supplies_ready = (
                self._fundraising_kit_secured(snapshot)
                and self._count_treasure_detection_scrolls(snapshot) >= scrolls_needed
                and self._fundraising_food_ready(snapshot)
                and self._fundraising_light_ready(snapshot)
                and not (
                    self._owns_lantern(snapshot)
                    and self._oil_below_departure_target(snapshot)
                )
            )
            if mandatory_supplies_ready:
                if (
                    self._equipped_launcher(snapshot) is not None
                    and self._count_matching_ammo(snapshot) < AMMO_CARRY_TARGET
                    and STORE_WEAPON not in self._town_store_attempted
                ):
                    add(STORE_WEAPON, "ammo")
                if (
                    self._fundraising_mode in {"prepare", "mine", "scavenge"}
                    and self._planned_depth() <= TORCH_THROW_MAX_DEPTH
                    and self._matching_ammo(snapshot) is None
                    and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
                    and STORE_GENERAL not in self._town_store_attempted
                ):
                    add(STORE_GENERAL, "throwing-torches")
            return needs

        bindable_home_identification = any(
            owned.origin == "home"
            and owned.identification_incomplete
            and self._item_signature(owned.item) not in self._deferred_home_items
            for owned in self._equipment_catalog.items
        )
        home_identification_unsatisfiable = (
            self._equipment_catalog.home_scan_complete
            and self._home_knowledge_current
            and self._identification_candidate is None
            and not bindable_home_identification
        )
        home_identification_claim = (
            self._home_errand.active
            or (
                self._identification_candidate is None
                and not home_identification_unsatisfiable
            )
            or any(
                owned.origin == "home"
                and self._item_signature(owned.item)
                == self._identification_candidate
                and self._item_signature(owned.item)
                not in self._deferred_home_items
                for owned in self._equipment_catalog.items
            )
        )
        if self._identification_need is not None:
            source = self._find_identification_source(
                snapshot,
                full=self._identification_need == "full",
                reliable_only=self._identification_requires_reliable_source(snapshot),
            )
            if source is None and STORE_ALCHEMIST not in self._town_store_attempted:
                add(STORE_ALCHEMIST, "identification-source", "before-withdrawal")
            elif (
                self._home_candidate_waiting
                and home_identification_claim
                and self._home_available(snapshot)
            ):
                add(
                    STORE_HOME,
                    "identification-withdrawal",
                    "post-alchemist-home",
                )
        elif (
            self._home_candidate_waiting
            and home_identification_claim
            and self._home_available(snapshot)
        ):
            add(
                STORE_HOME,
                "identification-withdrawal",
                "post-alchemist-home",
            )

        supply_categories = {
            "recall": "recall", "food": "food", "oil": "oil",
            "teleport": "teleport", "cure": "cure-critical",
        }
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        for status in self._ledger_departure_shortages(ledger):
            for store_type in status.stores:
                remembered = self._town_supplier_stock.get(store_type)
                remembered_affordable = bool(
                    remembered is not None
                    and any(
                        item.price <= snapshot.player.gold
                        and self._store_item_is_supply(item, status.kind)
                        for item in remembered.items
                    )
                )
                if (
                    store_type not in self._town_store_attempted
                    or store_type == STORE_HOME
                    or remembered_affordable
                ):
                    add(store_type, supply_categories[status.kind])
        if self._identification_need is not None:
            # Identification remains primary, while the supply ledger retains
            # its independent departure claims.
            return needs
        quest_strategy = self._carry_procurement_strategy(snapshot)
        if quest_strategy is not None:
            force = quest_strategy.required_force
            carry_status = self._quest_carry_status(snapshot, force)
            missing_carries = {
                name for name, status in carry_status.items()
                if (
                    not bool(status["ready"])
                    and name not in self._abandoned_quest_carry_requirements
                )
            }
            if "throwing_items.lit_torch" in missing_carries:
                home_torch = self._home_procurement_candidate(
                    (TVAL_LITE, SV_LITE_TORCH)
                )
                if home_torch is not None:
                    if self._home_pending_item is None:
                        self._home_pending_item = self._item_signature(home_torch)
                        torch_status = carry_status["throwing_items.lit_torch"]
                        self._home_pending_quantity = max(
                            1,
                            int(torch_status["required"]) - int(torch_status["measured"]),
                        )
                    add(STORE_HOME, "quest-throwing-items", "home-first")
                if (
                    STORE_GENERAL not in self._town_store_attempted
                    or self._quest_carry_remembered_affordable(
                        snapshot,
                        quest_strategy,
                        "throwing_items.lit_torch",
                        STORE_GENERAL,
                    )
                ):
                    add(STORE_GENERAL, "quest-throwing-items")
            self._abandon_unobtainable_quest_carries(snapshot, quest_strategy)
            home_launcher = self._preferred_home_quest_launcher(
                snapshot, quest_strategy
            )
            if "launcher" in missing_carries and home_launcher is not None:
                add(STORE_HOME, "quest-launcher", "home-first")
            if missing_carries & {
                "throwing_items.shot",
                "throwing_items.arrow",
                "throwing_items.bolt",
                "throwing_items.launcher_ammo",
            } or ("launcher" in missing_carries and home_launcher is None):
                remembered_affordable = any(
                    self._quest_carry_remembered_affordable(
                        snapshot, quest_strategy, name, STORE_WEAPON
                    )
                    for name in missing_carries
                    if STORE_WEAPON in self._quest_carry_suppliers(name)
                )
                if (
                    STORE_WEAPON not in self._town_store_attempted
                    or remembered_affordable
                ):
                    add(STORE_WEAPON, "quest-ranged-kit")
            if any(name.startswith("required_scrolls.") for name in missing_carries):
                if (
                    STORE_ALCHEMIST not in self._town_store_attempted
                    or any(
                        self._quest_carry_remembered_affordable(
                            snapshot, quest_strategy, name, STORE_ALCHEMIST
                        )
                        for name in missing_carries
                        if name.startswith("required_scrolls.")
                    )
                ):
                    add(STORE_ALCHEMIST, "quest-scrolls")
            if "utility_tools.wall_breach" in missing_carries:
                # Stone-to-Mud is not in the normal Magic-shop table.  It can
                # appear in the Black Market's random stock, so inspect that
                # store once before checking the General Store for an eligible
                # +3 digger.  Neither random stock is waited on indefinitely.
                if (
                    STORE_BLACK not in self._town_store_attempted
                    or self._quest_carry_remembered_affordable(
                        snapshot,
                        quest_strategy,
                        "utility_tools.wall_breach",
                        STORE_BLACK,
                    )
                ):
                    add(STORE_BLACK, "quest-wall-breach")
                elif (
                    STORE_GENERAL not in self._town_store_attempted
                    or self._quest_carry_remembered_affordable(
                        snapshot,
                        quest_strategy,
                        "utility_tools.wall_breach",
                        STORE_GENERAL,
                    )
                ):
                    add(STORE_GENERAL, "quest-wall-breach")
            if (
                self._exact_potion_count(snapshot, SV_POTION_SPEED)
                < int(force.get("speed_potions", 0))
                and STORE_BLACK not in self._town_store_attempted
            ):
                add(STORE_BLACK, "quest-speed")
            healing = self._exact_potion_count(snapshot, SV_POTION_HEALING)
            if healing < int(force.get("heal_potions", 0)):
                if STORE_TEMPLE not in self._town_store_attempted:
                    add(STORE_TEMPLE, "quest-healing")
                if STORE_BLACK not in self._town_store_attempted:
                    add(STORE_BLACK, "quest-healing")
        if not self._light_ready(snapshot):
            if STORE_GENERAL in self._town_store_attempted:
                return needs
            add(STORE_GENERAL, "light")
        if not self._identify_staff_ready(snapshot):
            if STORE_MAGIC in self._town_store_attempted:
                return needs
            add(STORE_MAGIC, "identify-staff")
        # Ammo is an optional supply: restock when low, but never block the
        # visit on it (the Weapon Smith always stocks SHOT/ARROW/BOLT).
        if (
            self._equipped_launcher(snapshot) is not None
            and self._count_matching_ammo(snapshot) < AMMO_CARRY_TARGET
            and STORE_WEAPON not in self._town_store_attempted
        ):
            add(STORE_WEAPON, "ammo")
        # Throwing torches for the early floors (user directive). Routed only
        # for fundraising trips (the shallow 1-10F fighting happens there);
        # ordinary visits still buy torches opportunistically when the General
        # Store is entered for another errand. Never blocks the visit.
        if (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and self._planned_depth() <= TORCH_THROW_MAX_DEPTH
            and self._matching_ammo(snapshot) is None
            and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
            and STORE_GENERAL not in self._town_store_attempted
        ):
            add(STORE_GENERAL, "throwing-torches")
        if (
            self._has_normal_remove_curse_target(snapshot)
            and self._find_remove_curse_scroll(snapshot) is None
        ):
            if STORE_TEMPLE in self._town_store_attempted:
                return needs
            add(STORE_TEMPLE, "remove-curse")
        carried_star_reserve = self._carried_star_remove_curse_count(snapshot) > 0
        if (
            self._has_unremovable_curse_target(snapshot)
            # A fresh policy must inspect Home before considering a new shop
            # purchase; otherwise it can buy while the reserve already sits on
            # an unobserved Home page.
            and self._home_star_remove_curse_count != 0
            and not carried_star_reserve
            and not self._recall_departure_shortage(snapshot)
        ):
            add(STORE_HOME, "home-star-remove-curse-use", "home-first")
        if (
            star_reserve_surplus
            and self._star_remove_curse_shelf_seen
            and self._home_star_remove_curse_count is None
            and not carried_star_reserve
        ):
            add(STORE_HOME, "home-star-remove-curse-check", "home-first")
        if (
            star_reserve_surplus
            and self._star_remove_curse_shelf_seen
            and self._home_star_remove_curse_count == 0
            and not carried_star_reserve
            and not self._star_remove_curse_reserve_deposit_pending
        ):
            add(STORE_TEMPLE, "home-star-remove-curse-stock")
        # A latched heavy curse never creates a speculative Temple trip.  Keep
        # the stop only when the live shelf proves that an affordable *Remove
        # Curse* is available; this makes the attempt opportunistic and gives
        # neither departure nor the restock waiter a missing-stock obligation.
        if self._affordable_star_remove_curse(snapshot) is not None:
            add(STORE_TEMPLE, "star-remove-curse")
        if (
            self._launcher_enchant_needed_svals(snapshot)
            and self._town_departure_ready(snapshot)
            and snapshot.player.gold > FUNDRAISING_START_GOLD
            and STORE_ALCHEMIST not in self._town_store_attempted
        ):
            add(STORE_ALCHEMIST, "launcher-enchant")
        if (
            snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and not (
                self._home_knowledge_current
                and self._home_scan_item_count == 0
            )
            and (
                (
                    not self._equipment_catalog.home_scan_complete
                    and self._home_catalog_routable(snapshot)
                )
                or self._has_actionable_incomplete_home_item(snapshot)
                or self._has_selected_home_random_teleport_suppression(snapshot)
            )
        ):
            add(STORE_HOME, "equipment-catalog", "home-first")
        if STORE_BLACK not in self._town_store_attempted:
            add(STORE_BLACK, "black-market")
        return needs

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

    def _town_need_registry(self) -> tuple[NeedSpec, ...]:
        """Build the single ordered producer/satisfaction registry once."""
        cached = getattr(self, "_town_need_specs", None)
        if cached is not None:
            return cached
        entries = (
            ("idle-consumable-scan", "home-first", 1, False),  # Idle Home scans are opportunistic.
            ("home-disposal-identify", "normal", 1, False),  # Disposal identification is opportunistic.
            ("home-disposal-sale", "normal", 1, False),  # Disposal sales are opportunistic.
            ("birth-supplies", "normal", 2, True),  # Birth supplies are required before the opening departure.
            ("quest-throwing-items", "opening-quest", 1, True),  # Opening Q34 stock gates quest acceptance.
            ("quest-throwing-items", "home-first", 1, True),  # Stored required throwing stock gates departure.
            ("disposal", "normal", 1, False),  # Dominated-item disposal is opportunistic.
            ("safe-weapon", "home-first", 1, True),  # A teleport-safe weapon is a departure safety gate.
            ("combat-weapon", "home-first", 1, True),  # Combat weapon readiness gates departure.
            ("book-sale", "normal", 1, False),  # Book sales are opportunistic.
            ("organization-sale", "normal", 1, True),  # Recognized surplus gates departure.
            ("weight-overload", "home-first", 1, True),  # Overweight inventory blocks departure.
            ("deposit", "home-first", 1, False),  # Non-mandatory Home deposits are convenience work.
            ("stat-restore", "normal", 1, True),  # Drained stats make departure unsafe.
            ("low-level-sale", "normal", 1, False),  # Low-level sales are opportunistic.
            ("mana-food-sale", "normal", 1, False),  # Surplus food sales are opportunistic.
            ("device-sale", "normal", 1, False),  # Device sales are opportunistic.
            ("weapon-sale", "normal", 1, False),  # Inferior weapon sales are opportunistic.
            ("light-sale", "normal", 1, False),  # Surplus light sales are opportunistic.
            ("fundraising-kit", "home-first", 1, True),  # The mining kit gates a fundraising run.
            ("fundraising-digger", "normal", 1, True),  # A digger gates a fundraising run.
            ("fundraising-detection", "normal", 1, True),  # Detection gates a fundraising run.
            ("fundraising-food", "normal", 1, True),  # Food gates a fundraising run.
            ("stored-detection", "home-first", 1, True),  # Stored detection gates a fundraising run.
            ("mining-detection", "normal", 1, True),  # Purchased detection gates a fundraising run.
            ("stored-digger", "home-first", 1, True),  # A stored digger gates a fundraising run.
            ("mining-digger", "normal", 1, True),  # A purchased digger gates a fundraising run.
            ("fundraising-light", "normal", 1, True),  # Light gates a fundraising run.
            ("fundraising-oil", "normal", 1, True),  # Oil gates a fundraising run.
            ("identification-source", "before-withdrawal", 1, True),  # Identification is consumed by departure readiness.
            ("identification-withdrawal", "post-alchemist-home", 1, True),  # The identification handoff gates departure.
            ("recall", "normal", 2, True),  # Recall supply feeds the departure ledger.
            ("teleport", "normal", 1, True),  # Teleport supply feeds the departure ledger.
            ("cure-critical", "normal", 2, True),  # Critical cures feed the departure ledger.
            ("oil", "normal", 1, True),  # Oil supply feeds the departure ledger.
            ("food", "normal", 2, True),  # Food supply feeds the departure ledger.
            ("quest-throwing-items", "normal", 1, True),  # Required throwing stock gates the quest departure.
            ("quest-launcher", "home-first", 1, True),  # A required launcher gates the quest departure.
            ("quest-ranged-kit", "normal", 1, True),  # Required ranged gear gates the quest departure.
            ("quest-scrolls", "normal", 1, True),  # Required scrolls gate the quest departure.
            ("quest-wall-breach", "normal", 1, True),  # Required wall breach gates the quest departure.
            ("quest-speed", "normal", 1, True),  # Required speed potions gate the quest departure.
            ("quest-healing", "normal", 2, True),  # Required healing potions gate the quest departure.
            ("light", "normal", 1, True),  # Expedition light gates departure.
            ("identify-staff", "normal", 1, True),  # Identification capacity gates departure.
            ("ammo", "normal", 1, False),  # Ordinary ammo restocking is optional.
            ("throwing-torches", "normal", 1, False),  # Non-quest throwing torches are optional.
            ("remove-curse", "normal", 1, True),  # An actionable carried curse makes departure unsafe.
            ("home-star-remove-curse-use", "home-first", 1, True),
            ("home-star-remove-curse-check", "home-first", 1, False),
            ("home-star-remove-curse-stock", "normal", 1, False),
            ("star-remove-curse", "normal", 1, False),  # Shelf-proven heavy-curse service is opportunistic.
            ("launcher-enchant", "normal", 1, False),  # Launcher enchanting is an optimization.
            ("equipment-catalog", "home-first", 1, False),  # Catalog completion yields to a ready departure.
            ("equipment-work", "home-first", 1, True),
            ("equipment-transaction", "home-first", 1, True),
            ("calibration-restore", "home-first", 1, True),
            ("black-market", "normal", 1, False),  # Black Market browsing is opportunistic.
        )
        specs: list[NeedSpec] = []
        for category, ordering_class, count, departure_blocking in entries:
            for occurrence in range(count):
                lookup = (
                    lambda snapshot, category=category,
                    ordering_class=ordering_class, occurrence=occurrence:
                    self._candidate_need(
                        snapshot, category, ordering_class, occurrence
                    )
                )
                produces = lambda snapshot, lookup=lookup: lookup(snapshot) is not None
                specs.append(
                    NeedSpec(
                        category=category,
                        store_type=lambda snapshot, lookup=lookup: (
                            lookup(snapshot).store_type  # type: ignore[union-attr]
                        ),
                        ordering_class=ordering_class,
                        produces=produces,
                        satisfied=lambda snapshot, produces=produces: not produces(snapshot),
                        departure_blocking=departure_blocking,
                    )
                )
        self._town_need_specs = tuple(specs)
        return self._town_need_specs

    def _town_claims_active(self, snapshot: Snapshot) -> bool:
        """Record live route owners from the same registry used by projection."""
        self._retire_actionless_equipment_failure(snapshot)
        self._refresh_nonhome_effect_refusals(snapshot)
        claims: list[str] = []
        departure_ready: bool | None = None
        specs = {spec.category: spec for spec in self._town_need_registry()}
        for need in self._enumerate_live_store_claims(snapshot):
            spec = specs.get(need.category)
            equipment_owner = need.category in {
                "equipment-work", "equipment-transaction"
            }
            home_visit_budget_exhausted = (
                need.store_type == STORE_HOME
                and getattr(self, "_home_visit", None) is not None
                and self._home_visit.attempts_used
                >= self._home_visit.attempt_limit
            )
            if (
                need.store_type
                in self._town_visit_ledger.nonhome_attempted_without_effect
                or (
                    need.store_type == STORE_HOME
                    and (
                        home_visit_budget_exhausted
                        or self._town_store_blocked_under_applicable_bound(
                            need.store_type
                        )
                        or self._town_visit_ledger.approach_fails[need.store_type]
                        >= self._town_store_visit_limit(need.store_type)
                        or (
                            spec is not None
                            and self._town_visit_ledger.need_attempts.get(
                                need.category, 0
                            ) >= spec.budget
                            and not equipment_owner
                            and not self._outstanding_equipment_work()
                        )
                    )
                )
            ):
                if (
                    need.store_type == STORE_HOME
                    and need.category == "weight-overload"
                    and self._inventory_overweight(snapshot)
                    and self._town_visit_ledger.approach_fails[STORE_HOME]
                    >= self._town_store_visit_limit(STORE_HOME)
                ):
                    # Claim retirement is still the town-liveness outcome, but
                    # an overweight character has no alternate supplier.  Hand
                    # the exhausted route directly to a diagnostic terminal.
                    self._town_blocked_reason = "overweight-home-unreachable"
                if (
                    home_visit_budget_exhausted
                    and need.category == "calibration-restore"
                ):
                    self._town_liveness_claim_retired = True
                continue
            if spec is not None and not spec.departure_blocking:
                if departure_ready is None:
                    departure_ready = self._town_departure_ready(snapshot)
                if departure_ready:
                    continue
            if need.category not in claims:
                claims.append(need.category)
        self._town_claim_categories = claims
        return bool(claims)

    def _retire_actionless_equipment_failure(self, snapshot: Snapshot) -> bool:
        """Release a failed optimizer latch that has no in-town clearing owner."""
        if (self.last_reason or "").startswith("equipment-transaction:"):
            return False
        preparation = self._equipment_optimization_preparation
        if not self._equipment_failure_unexecutable_this_visit(
            snapshot, preparation, require_confirmed=False
        ):
            return False
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


    def _enumerate_town_needs(self, snapshot: Snapshot) -> list[TownNeed]:
        """Return every currently true town errand from the shared registry."""
        needs: list[TownNeed] = []
        self._town_need_evaluation_snapshot = snapshot
        self._town_need_evaluation_candidates = self._town_need_candidates(snapshot)
        try:
            for spec in self._town_need_registry():
                if spec.produces(snapshot):
                    needs.append(
                        TownNeed(
                            spec.resolve_store_type(snapshot),
                            spec.category,
                            spec.ordering_class,
                        )
                    )
        finally:
            self._town_need_evaluation_snapshot = None
            self._town_need_evaluation_candidates = None
        if (
            self._home_knowledge_current
            and self._home_scan_item_count == 0
            and not self._calibration_active()
            and self._equipment_transaction_session is None
        ):
            needs = [
                need
                for need in needs
                if need.store_type != STORE_HOME
                or need.category in {"deposit", "weight-overload"}
            ]
        return needs

    def _enumerate_live_store_claims(self, snapshot: Snapshot) -> list[TownNeed]:
        """Enumerate every live owner of a store route for this decision.

        The generic need registry explicitly owns catalogue scans, queued Home
        identities, identification errands, procurement shortages, disposal,
        fundraising, curse service, sales, and optional shopping.  The two
        state-machine owners below are not NeedSpec predicates: calibration /
        optimizer work owns Home while its hard route bound remains, and an
        executable equipment transaction owns the context it was bound to.
        This is the sole input to the town-plan projection.
        """
        claims = list(self._enumerate_town_needs(snapshot))
        # Withdrawal requesters must file an exact executor request before the
        # router may act.  The legacy terminal posts this same owner expectation,
        # so an unchanged progress core suppresses the claim instead of rebuilding
        # the just-failed Home approach.
        departure_categories = {
            need.category for need in self._departure_blocking_town_needs(snapshot)
        }
        claims = [
            claim for claim in claims
            if self._owner_may_select(
                snapshot, f"home-withdrawal:{claim.category}"
            )
            # E3: an expectation refusal cannot silently erase a failing gate
            # conjunct while its supplier remains reachable.  Keep that claim
            # routable; if it later proves exhausted, the ordinary visible
            # departure-unsatisfiable terminal owns the outcome.
            or (
                claim.category in departure_categories
                and self._town_need_supplier_reachable(snapshot, claim)
            )
        ]
        if self._opening_q34_active(snapshot):
            # Q34's opening owns town until the quest clears.  Candidate
            # generation is not the claim boundary: NeedSpecs can remain true
            # outside _town_need_candidates, and the equipment state machines
            # below are independent producers.  Admit only the opening's two
            # errands here, at the final producer consumed by town routing.
            return [
                claim
                for claim in claims
                if claim.category in {"combat-weapon", "quest-throwing-items"}
            ]
        post_alchemist_home = any(
            claim.ordering_class == "post-alchemist-home"
            or claim.category == "identification-source"
            for claim in claims
        )
        if (
            self._equipment_work_home_route_available()
            and self._home_owner_goal_pending(snapshot)
            and self._owner_may_select(snapshot, "home-withdrawal:equipment-work")
            and not any(claim.category == "equipment-work" for claim in claims)
        ):
            claims.append(TownNeed(
                STORE_HOME,
                "equipment-work",
                "post-alchemist-home" if post_alchemist_home else "home-first",
            ))
        session = self._equipment_transaction_session
        if (
            session is not None
            and session.executable
            and session.required_context is not None
            and not any(claim.category == "equipment-transaction" for claim in claims)
        ):
            claims.append(TownNeed(
                STORE_HOME,
                "equipment-transaction",
                "home-first",
            ))
        return claims

    def _departure_blocking_town_needs(self, snapshot: Snapshot) -> list[TownNeed]:
        """Return live errands whose NeedSpec says they gate departure."""
        needs: list[TownNeed] = []
        self._town_need_evaluation_snapshot = snapshot
        self._town_need_evaluation_candidates = self._town_need_candidates(snapshot)
        try:
            for spec in self._town_need_registry():
                if spec.departure_blocking and spec.produces(snapshot):
                    needs.append(
                        TownNeed(
                            spec.resolve_store_type(snapshot),
                            spec.category,
                            spec.ordering_class,
                        )
                    )
        finally:
            self._town_need_evaluation_snapshot = None
            self._town_need_evaluation_candidates = None
        if self._calibration_phase == "deposit" and self._home_available(snapshot):
            needs.append(TownNeed(
                STORE_HOME, "calibration-deposit", "home-first"
            ))
        return needs

    def _town_need_supplier_reachable(
        self, snapshot: Snapshot, need: TownNeed
    ) -> bool:
        """Whether a need's supplier has a live or remembered town route."""
        store = getattr(snapshot, "store", None)
        if store is not None and store.store_type == need.store_type:
            return True
        if any(
            grid.store_number == need.store_type
            for grid in getattr(snapshot, "grids", {}).values()
        ):
            return True
        if not hasattr(snapshot, "town_id"):
            return False
        store_position = getattr(self._town_map, "store_position", None)
        return bool(
            self._town_map_active(snapshot)
            and callable(store_position)
            and store_position(need.store_type) is not None
        )

    def _departure_supplier_counterfactual(
        self, snapshot: Snapshot
    ) -> int | None:
        """Return a reachable, obtainable supplier for a failing town gate."""
        candidates = list(self._departure_blocking_town_needs(snapshot))
        candidates.extend(
            claim
            for claim in self._enumerate_live_store_claims(snapshot)
            if claim.category in {"equipment-work", "equipment-transaction"}
        )
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        supply_categories = {
            "recall": "recall", "food": "food", "oil": "oil",
            "teleport": "teleport", "cure": "cure-critical",
        }
        for status in self._ledger_departure_shortages(ledger):
            if not status.obtainable:
                continue
            candidates.extend(
                TownNeed(store, supply_categories[status.kind], "normal")
                for store in status.stores
            )
        for need in candidates:
            if not self._town_need_supplier_reachable(snapshot, need):
                continue
            page = self._town_supplier_stock.get(need.store_type)
            remembered_affordable = bool(
                page is not None
                and any(item.price <= snapshot.player.gold for item in page.items)
            )
            if (
                need.store_type not in self._town_store_attempted
                or need.store_type == STORE_HOME
                or remembered_affordable
            ):
                self._rearm_town_store_for_new_work(
                    need.store_type, release_visit_bound=True
                )
                return need.store_type
        return None

    def _order_town_stops(
        self, snapshot: Snapshot, stores: list[int], start: Position | None = None
    ) -> list[int]:
        """Nearest-neighbour order; numeric store order is the mapless fallback."""
        remaining = list(dict.fromkeys(stores))
        ordered: list[int] = []
        position = start or snapshot.player.position
        while remaining:
            if self._town_map_active(snapshot):
                store_type = min(
                    remaining,
                    key=lambda value: (
                        position.distance_to(self._town_map.store_position(value))
                        if self._town_map.store_position(value) is not None
                        else 10**9,
                        value,
                    ),
                )
                target = self._town_map.store_position(store_type)
                if target is not None:
                    position = target
            else:
                # Stable mapless circuit, chosen to retain the historical
                # high-value/service ordering while still batching by building.
                canonical = (
                    STORE_ARMOURY,
                    STORE_MAGIC,
                    STORE_WEAPON,
                    STORE_TEMPLE,
                    STORE_GENERAL,
                    STORE_ALCHEMIST,
                    STORE_BLACK,
                    STORE_HOME,
                )
                rank = {value: index for index, value in enumerate(canonical)}
                store_type = min(remaining, key=lambda value: (rank.get(value, 99), value))
            remaining.remove(store_type)
            ordered.append(store_type)
        return ordered

    @staticmethod
    def _town_need_phase(need: TownNeed) -> int:
        """Order mandatory town work before convenience and speculative buys."""
        if need.category in {
            "black-market",
            "ammo",
            "throwing-torches",
            "launcher-enchant",
        }:
            return 2
        return 0

    def _town_need_effective_phase(
        self, snapshot: Snapshot, need: TownNeed
    ) -> int:
        """Put concretely affordable curse service ahead of ordinary errands."""
        if (
            need.category == "remove-curse"
            and self._normal_remove_curse_actionable_this_visit(snapshot)
        ):
            return -1
        if need.category == "identification-source":
            return -1
        if (
            need.category == "oil"
            and self._identification_need is not None
            and self._owns_lantern(snapshot)
        ):
            return -2
        return self._town_need_phase(need)

    def _order_town_needs(
        self,
        snapshot: Snapshot,
        needs: list[TownNeed],
        stores: list[int],
        start: Position,
    ) -> list[int]:
        """Order stores by need phase, then minimize travel inside each phase."""
        needed_store_types = {need.store_type for need in needs}
        unique_stores = [
            store_type
            for store_type in dict.fromkeys(stores)
            if store_type in needed_store_types
        ]
        phase_by_store = {
            store_type: min(
                self._town_need_effective_phase(snapshot, need)
                for need in needs
                if need.store_type == store_type
            )
            for store_type in unique_stores
        }
        ordered: list[int] = []
        current = start
        for phase in sorted(set(phase_by_store.values())):
            phase_order = self._order_town_stops(
                snapshot,
                [
                    store_type
                    for store_type in unique_stores
                    if phase_by_store[store_type] == phase
                ],
                current,
            )
            ordered.extend(phase_order)
            if phase_order and self._town_map_active(snapshot):
                current = self._town_map.store_position(phase_order[-1]) or current
        return ordered

    def _build_town_errand_plan(
        self, snapshot: Snapshot, needs: list[TownNeed]
    ) -> TownErrandPlan | None:
        leading_home = any(
            need.store_type == STORE_HOME and need.ordering_class != "post-alchemist-home"
            for need in needs
        )
        post_home = any(need.ordering_class == "post-alchemist-home" for need in needs)
        stores = {need.store_type for need in needs if need.store_type != STORE_HOME}
        stops: list[int] = [STORE_HOME] if leading_home else []
        start = self._town_map.store_position(STORE_HOME) if leading_home and self._town_map_active(snapshot) else snapshot.player.position
        ordered = self._order_town_needs(snapshot, needs, list(stores), start)
        if post_home and STORE_ALCHEMIST in ordered:
            alchemist_index = ordered.index(STORE_ALCHEMIST)
            ordered.insert(alchemist_index + 1, STORE_HOME)
        elif post_home:
            ordered.append(STORE_HOME)
        stops.extend(ordered)
        return (
            TownErrandPlan(
                stops,
                need_categories={
                    store_type: tuple(
                        need.category
                        for need in needs
                        if need.store_type == store_type
                    )
                    for store_type in dict.fromkeys(stops)
                },
            )
            if stops
            else None
        )

    def _next_required_store_type(self, snapshot: Snapshot) -> int | None:
        self._town_plan_projection_telemetry = {
            "evaluated": False,
            "plan_rebuilt": False,
            "rebuilt_stops": [],
        }
        departure_ready: bool | None = None

        def town_departure_ready() -> bool:
            nonlocal departure_ready
            if departure_ready is None:
                departure_ready = self._town_departure_ready(snapshot)
            return departure_ready

        # An inscription is only the entry half of a two-stage sale.  Keep the
        # store that owns its pending tail ahead of freshly rebuilt purchase,
        # Home, and fundraising claims until the tagged item is observed and
        # the sale is composed.  Otherwise an unaffordable purchase can route
        # away from the sale that would fund it, leaving the batch owner alive
        # but permanently uncomposable.
        pending_sale = self._batch_sell_pending
        if (
            snapshot.in_town
            and pending_sale is not None
            and pending_sale.get("phase") in {"await-inscription", "await-sale"}
        ):
            return int(pending_sale["store_type"])

        # The queued take is an address-bearing continuation of the current
        # Home visit, not a need that may be reprioritized out of a rebuilt
        # fundraising plan (notably scavenge's [Alchemist, General] plan).
        # Keep Home first until the take posts, confirms, or its bounded
        # failure path visibly abandons it to the purchase fallback.
        if snapshot.in_town and (
            self._home_digger_withdraw_pending
            or (
                self._home_withdrawal_queued
                and self._home_pending_item is not None
            )
            or (
                getattr(self, "_home_procurement_batch_active", False)
                and self._home_pending_batch
            )
        ):
            # The departure latch is itself an authoritative Home claim.  A
            # failed/recovered boundary can lose the page-relative item
            # address before the next open Home observation recreates it; do
            # not let that transient absence strand the route behind another
            # store.  ``queued`` describes a selected address awaiting post,
            # so it must not survive once that address is gone.
            if self._home_pending_item is None and not self._home_pending_batch:
                self._home_withdrawal_queued = False
            return STORE_HOME

        if (
            snapshot.in_town
            and snapshot.player.hungry
            and self._find_edible(snapshot) is None
        ):
            food_store = (
                STORE_MAGIC
                if snapshot.player.food_type == FOOD_TYPE_MANA
                else STORE_GENERAL
            )
            return (
                None
                if food_store in self._town_store_attempted
                else food_store
            )
        opening_q34 = self._opening_q34_active(snapshot)
        opening_torch_shortage = self._opening_q34_torch_shortage(snapshot)
        if opening_q34 and opening_torch_shortage > 0 and self._fundraising_mode in {
            "prepare", "mine", "scavenge"
        }:
            # prime() can reconstruct fundraising from the scrolls left by an
            # interrupted bad opening.  Cancel that stale owner and rebuild the
            # route so resume repairs the same character instead of repeating
            # Home -> Alchemist -> Yeek Cave.
            self._fundraising_mode = None
            self._planned_mining_runs = None
            self._town_store_attempted.clear()
            self._town_restock_suppressed = False
            self._town_errand_plan = None
        if self._town_restock_suppressed:
            self._town_errand_plan = None
            return None
        if (
            opening_q34
            and opening_torch_shortage > 0
            and STORE_GENERAL in self._town_store_attempted
        ):
            self._town_restock_rechecked.discard(STORE_GENERAL)
            return self._retry_after_store_restock(snapshot, (STORE_GENERAL,))
        if (
            snapshot.store is not None
            and self._town_errand_plan is not None
            and self._town_errand_plan.index < len(self._town_errand_plan.stops)
            and self._town_errand_plan.stops[self._town_errand_plan.index]
            == snapshot.store.store_type
        ):
            return snapshot.store.store_type
        if (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and snapshot.player.gold < FUNDRAISING_START_GOLD
            and self._fundraising_mode is None
            and (not opening_q34 or opening_torch_shortage == 0)
        ):
            self._start_fundraising(snapshot)
        self._refresh_nonhome_effect_refusals(snapshot)
        ledger_blocked = {
            store
            for store in self._town_visit_ledger.blocked_stores
            if store == STORE_HOME
            and self._town_store_blocked_under_applicable_bound(store)
        } | {
            store
            for store, failures in self._town_visit_ledger.approach_fails.items()
            if store == STORE_HOME
            and failures >= self._town_store_visit_limit(store)
        }
        identification_home_target = any(
            owned.origin == "home"
            and self._item_signature(owned.item) == self._identification_candidate
            for owned in self._equipment_catalog.items
        )
        if (
            self._identification_need is not None
            and self._identification_need != "full"
            and self._town_blocked_reason != "repetition"
            and not self._identification_need_actionable(snapshot)
        ):
            # Retire an uncomposable identify owner before independent supply
            # claims rebuild the plan; a fresh visit/source naturally revives
            # the ordinary producer without a permanent latch.
            if identification_home_target and STORE_HOME not in ledger_blocked:
                self._rearm_town_store_for_new_work(STORE_HOME)
                return STORE_HOME
            else:
                self._town_terminal_transitions(snapshot)
        live_needs = self._enumerate_live_store_claims(snapshot)
        if self._town_blocked_reason == "repetition":
            blocking = {
                need.category
                for need in self._departure_blocking_town_needs(snapshot)
            }
            # Equipment state machines are themselves departure owners and are
            # deliberately not represented by the generic NeedSpec table.
            blocking.update({"equipment-work", "equipment-transaction"})
            live_needs = [
                need for need in live_needs if need.category in blocking
            ]
        needs = [
            need
            for need in live_needs
            if need.store_type not in ledger_blocked
            and need.store_type
            not in self._town_visit_ledger.nonhome_attempted_without_effect
        ]
        warned = set(self._town_visit_ledger.drift_warnings)
        live_pairs = {(need.store_type, need.category) for need in needs}
        for store_type, category in live_pairs:
            warning = (
                f"drift:{STORE_RESTOCK_REASON_NAMES.get(store_type, store_type)}"
                f":{category}"
            )
            if (
                (store_type, category) in self._town_visit_ledger.satisfied_needs
                and warning not in warned
            ):
                self._town_visit_ledger.drift_warnings.append(warning)
                warned.add(warning)
        self._town_visit_ledger.satisfied_needs.intersection_update(live_pairs)
        previous_plan = self._town_errand_plan
        # The plan is a disposable ordering view over this decision's claims.
        # A live claim supersedes a completed/attempted route snapshot; only the
        # ledger's unchanged hard bounds can suppress it.
        plan = self._build_town_errand_plan(snapshot, needs)
        self._town_errand_plan = plan
        self._town_plan_projection_telemetry = {
            "evaluated": True,
            "plan_rebuilt": True,
            "rebuilt_stops": list(plan.stops) if plan is not None else [],
        }
        if plan is not None:
            previous_exhausted = (
                previous_plan is None
                or previous_plan.index >= len(previous_plan.stops)
            )
            for store_type in plan.stops:
                prior_categories = (
                    set(previous_plan.need_categories.get(store_type, ()))
                    if previous_plan is not None else set()
                )
                live_categories = set(plan.need_categories.get(store_type, ()))
                post_alchemist_home = (
                    store_type == STORE_HOME
                    and any(
                        need.store_type == STORE_HOME
                        and need.ordering_class == "post-alchemist-home"
                        for need in needs
                    )
                    and STORE_ALCHEMIST in self._town_store_attempted
                )
                if (
                    previous_exhausted
                    or live_categories - prior_categories
                    or post_alchemist_home
                ):
                    self._town_store_attempted.pop(store_type, None)
                    if self._store_entry_failed_owner == store_type:
                        self._store_entry_failed_owner = None
                if store_type not in self._town_store_attempted:
                    return store_type
            return None
        plan = self._town_errand_plan
        post_alchemist_home_needed = any(
            need.ordering_class == "post-alchemist-home"
            or need.category == "identification-source"
            for need in needs
        )
        warned = set(self._town_visit_ledger.drift_warnings)
        for need in needs:
            satisfied = (need.store_type, need.category)
            warning = (
                f"drift:{STORE_RESTOCK_REASON_NAMES.get(need.store_type, need.store_type)}"
                f":{need.category}"
            )
            if (
                satisfied in self._town_visit_ledger.satisfied_needs
                and warning not in warned
            ):
                self._town_visit_ledger.drift_warnings.append(warning)
                warned.add(warning)
        if (
            self._equipment_transaction_session is not None
            and self._equipment_transaction_session.executable
            and self._equipment_transaction_session.required_context is not None
            and STORE_HOME not in self._town_store_attempted
        ):
            needs.append(TownNeed(STORE_HOME, "equipment-transaction", "home-first"))
        needed_stores = {need.store_type for need in needs}
        if plan is None:
            plan = self._build_town_errand_plan(snapshot, needs)
            self._town_errand_plan = plan
        elif plan.index >= len(plan.stops):
            # A completed plan is only a snapshot of the needs visible when it
            # was built. Completing an identification errand can expose the
            # ordinary supply shortages that it previously owned exclusively.
            # Rebuild for newly actionable stores instead of falling into the
            # legacy terminal router, whose first shortage can monopolize town
            # with an endless one-store restock cycle.
            completed = (
                set(plan.completed_this_visit)
                | set(plan.blocked_this_visit)
                | ledger_blocked
            )
            self._town_plan_projection_telemetry = {
                "evaluated": True,
                "home_attempted": STORE_HOME in self._town_store_attempted,
                "home_attempted_entry": self._town_store_attempted.get(STORE_HOME),
                "plan_completed_this_visit": list(plan.completed_this_visit),
                "plan_blocked_this_visit": list(plan.blocked_this_visit),
                "ledger_blocked": sorted(ledger_blocked),
                "plan_rebuilt": False,
                "rebuilt_stops": [],
            }
            remaining_needs = [
                need for need in needs
                if need.store_type not in completed
                or (
                    need.store_type == STORE_HOME
                    and need.ordering_class == "post-alchemist-home"
                    and STORE_HOME not in plan.blocked_this_visit
                )
            ]
            if any(
                need.store_type not in self._town_store_attempted
                or (
                    need.store_type == STORE_HOME
                    and need.ordering_class == "post-alchemist-home"
                    and STORE_HOME not in plan.blocked_this_visit
                )
                for need in remaining_needs
            ):
                # Home before and Home after an identification purchase are two
                # distinct phases of one transaction.  The first visit records
                # Home as completed/attempted when it discovers an item needing
                # an Alchemist source.  Once that source is carried, explicitly
                # re-arm the post-Alchemist withdrawal instead of treating the
                # earlier catalog pass as satisfying it too.
                if any(
                    need.store_type == STORE_HOME
                    and need.ordering_class == "post-alchemist-home"
                    for need in remaining_needs
                ):
                    self._rearm_town_store_for_new_work(STORE_HOME)
                plan = self._build_town_errand_plan(snapshot, remaining_needs)
                self._town_errand_plan = plan
                self._town_plan_projection_telemetry["plan_rebuilt"] = True
                self._town_plan_projection_telemetry["rebuilt_stops"] = (
                    list(plan.stops) if plan is not None else []
                )
        elif plan.index < len(plan.stops):
            pending = set(plan.stops[plan.index + 1 :])
            finished = (
                set(plan.completed_this_visit)
                | set(plan.blocked_this_visit)
                | ledger_blocked
            )
            additions = needed_stores - pending - finished - {plan.stops[plan.index]}
            if additions:
                current_store = plan.stops[plan.index]
                current_position = (
                    self._town_map.store_position(current_store)
                    if self._town_map_active(snapshot)
                    else snapshot.player.position
                )
                old_remaining = plan.stops[plan.index + 1 :]
                reordered = self._order_town_needs(
                    snapshot,
                    needs,
                    old_remaining + sorted(additions),
                    current_position,
                )
                plan.stops[plan.index + 1 :] = reordered
                plan.inserted_this_visit.extend(sorted(additions))

        if plan is not None:
            for store_type in needed_stores:
                plan.need_categories[store_type] = tuple(
                    need.category
                    for need in needs
                    if need.store_type == store_type
                )

        while plan is not None and plan.index < len(plan.stops):
            store_type = plan.stops[plan.index]
            if store_type not in needed_stores:
                plan.index += 1
                continue
            if store_type in self._town_store_attempted:
                if (
                    store_type == STORE_HOME
                    and post_alchemist_home_needed
                    and STORE_HOME not in plan.blocked_this_visit
                ):
                    # A plan built up-front can already contain Home twice
                    # (catalog first, withdrawal after Alchemist).  Release the
                    # first visit's latch only for that explicit second phase.
                    self._rearm_town_store_for_new_work(STORE_HOME)
                    return STORE_HOME
                plan.skipped_latched.append(store_type)
                plan.index += 1
                continue
            return store_type

        if opening_q34 and opening_torch_shortage > 0:
            # The fresh-character route has exactly one owner until all Q34
            # throwing torches are carried.  If the General Store did not have
            # enough stock, wait for its next turnover and retry that same shop;
            # falling through to the ordinary terminal router starts unrelated
            # Home/Alchemist/Magic errands and destroys the opening route.
            if STORE_GENERAL not in self._town_store_attempted:
                return STORE_GENERAL
            # Mandatory opening stock is different from an optional restock
            # attempt: keep permitting one genuine General Store re-check per
            # completed turnover until the force requirement is satisfied.
            self._town_restock_rechecked.discard(STORE_GENERAL)
            return self._retry_after_store_restock(snapshot, (STORE_GENERAL,))

        if live_needs and all(
            need.store_type != STORE_HOME
            and need.store_type
            in self._town_visit_ledger.nonhome_attempted_without_effect
            for need in live_needs
        ):
            supplier = self._departure_supplier_counterfactual(snapshot)
            if supplier is not None:
                return supplier
            self._town_blocked_reason = "departure-unsatisfiable"
            return None

        self._town_terminal_transitions(snapshot)
        refreshed_needs = self._enumerate_town_needs(snapshot)
        if refreshed_needs:
            refreshed_plan = self._build_town_errand_plan(snapshot, refreshed_needs)
            if refreshed_plan is not None:
                exhausted_stores = (
                    (
                        set(plan.completed_this_visit)
                        | set(plan.blocked_this_visit)
                    )
                    if plan is not None
                    else set()
                ) | ledger_blocked
                for store_type in refreshed_plan.stops:
                    restock_recheck = (
                        store_type in self._town_restock_rechecked
                        and store_type not in self._town_store_attempted
                    )
                    if (
                        (
                            store_type not in exhausted_stores
                            or restock_recheck
                        )
                        and store_type not in self._town_store_attempted
                    ):
                        if (
                            restock_recheck
                            and self._town_restock_waiting_for
                            and all(
                                waiting in self._town_restock_rechecked
                                for waiting in self._town_restock_waiting_for
                            )
                        ):
                            self._town_restock_waiting_for = ()
                        return store_type
        if live_needs and all(
            need.store_type != STORE_HOME
            and need.store_type
            in self._town_visit_ledger.nonhome_attempted_without_effect
            for need in live_needs
        ):
            if self._departure_supplier_counterfactual(snapshot) is None:
                self._town_blocked_reason = "departure-unsatisfiable"
        return None

    @staticmethod
    def _town_workflow_progress_state(snapshot: Snapshot) -> tuple[object, ...]:
        """Project state changes that demonstrate town-workflow progress."""
        def item_state(item: object) -> tuple[object, ...]:
            return tuple(
                getattr(item, field, None)
                for field in (
                    "slot", "tval", "sval", "name", "count", "charges",
                    "inscription", "known", "fully_known", "is_equipment",
                )
            )

        store = snapshot.store
        store_state = None if store is None else (
            store.store_type,
            getattr(store, "stock_num", None),
            getattr(store, "page_top", None),
            tuple(item_state(item) for item in store.items),
        )
        return (
            store_state,
            tuple(item_state(item) for item in snapshot.inventory),
            tuple(item_state(item) for item in snapshot.equipment),
            snapshot.player.gold,
        )

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

    def _release_blocked_store_latches(self, store_type: int) -> None:
        """Release flow state that a blocked store can no longer service."""
        if store_type == STORE_HOME:
            self._release_identification_source_reservation()
            self._home_candidate_waiting = False
            self._home_pending_item = None
            self._home_pending_batch.clear()
            self._home_atomic_withdraw_pending = None
            self._home_random_teleport_withdrawal = None

    def _report_town_stop_pass(
        self,
        snapshot: Snapshot,
        store_type: int,
        *,
        goal_satisfied: bool,
        operation_completed: bool = False,
    ) -> None:
        """Report one handler pass to the plan that owns this town objective."""
        self._town_visit_ledger.store_visits[store_type] += 1
        store_needs = [
            need
            for need in self._enumerate_town_needs(snapshot)
            if need.store_type == store_type
        ]
        plan = self._town_errand_plan
        owned_categories = (
            plan.need_categories.get(store_type, ())
            if plan is not None
            else tuple(need.category for need in store_needs)
        )
        if (
            store_type == STORE_HOME
            and self._home_knowledge_current
            and self._home_scan_item_count == 0
            and not self._calibration_active()
            and self._equipment_transaction_session is None
        ):
            # Reconcile a plan built before the knowledge response.  Categories
            # whose only fulfillment was an empty-Home withdrawal no longer own
            # this stop; live deposit categories remain visible in store_needs.
            owned_categories = tuple(need.category for need in store_needs)
            if plan is not None and STORE_HOME not in plan.blocked_this_visit:
                plan.blocked_this_visit.append(STORE_HOME)
            self._town_blocked_reason = "home-known-empty-withdrawal"
        if not owned_categories:
            owned_categories = tuple(need.category for need in store_needs)
        registry_satisfied = True
        if owned_categories:
            self._town_need_evaluation_snapshot = snapshot
            self._town_need_evaluation_candidates = self._town_need_candidates(
                snapshot
            )
            try:
                registry_satisfied = all(
                    spec.satisfied(snapshot)
                    for spec in self._town_need_registry()
                    if spec.category in set(owned_categories)
                    and (
                        not spec.produces(snapshot)
                        or spec.resolve_store_type(snapshot) == store_type
                    )
                )
            finally:
                self._town_need_evaluation_snapshot = None
                self._town_need_evaluation_candidates = None
        goal_satisfied = goal_satisfied and registry_satisfied
        for category in owned_categories:
            self._town_visit_ledger.need_attempts[category] = (
                self._town_visit_ledger.need_attempts.get(category, 0) + 1
            )
        if goal_satisfied:
            self._town_visit_ledger.satisfied_needs.update(
                (store_type, category) for category in owned_categories
            )
        if (
            plan is None
            or plan.index >= len(plan.stops)
            or plan.stops[plan.index] != store_type
        ):
            return
        if goal_satisfied:
            plan.completed_this_visit.append(store_type)
            plan.current_stop_passes = 0
            plan.index += 1
            return
        if store_type != STORE_HOME:
            if self._wanted_purchase_is_home_first_refused(snapshot, store_type):
                return
            if operation_completed:
                plan.current_stop_passes = 0
                return
            self._town_visit_ledger.pending_nonhome_effect_observation.add(
                store_type
            )
            plan.blocked_this_visit.append(store_type)
            plan.current_stop_passes = 0
            plan.index += 1
            self._set_town_store_attempted(store_type, snapshot.turn, "plan-stop-satisfied")
            return
        limit = self._town_store_visit_limit(store_type)
        # During calibration, one completed Home entry is the unit of work:
        # an atomic deposit/withdrawal still consumes an entry when its owner
        # remains live.  The same ledger counter therefore enforces the user's
        # visit ceiling without weakening the existing blocked-store terminal.
        plan.current_stop_passes += 1
        self._town_visit_ledger.unsatisfied_passes[store_type] += 1
        self._observe_withdrawal_unsatisfied_pass(snapshot)
        if (
            self._town_visit_ledger.unsatisfied_passes[store_type]
            < limit
        ):
            if operation_completed:
                plan.current_stop_passes = 0
            return
        plan.blocked_this_visit.append(store_type)
        self._town_visit_ledger.blocked_stores.add(store_type)
        # A ledger block's authority is the bound that installed it.  Passes
        # remain cumulative, but a later owner with a different applicable
        # bound is denied only when its own bound is exhausted.
        self._town_visit_ledger.blocked_store_limits[store_type] = limit
        self._release_blocked_store_latches(store_type)
        plan.current_stop_passes = 0
        plan.index += 1
        self._set_town_store_attempted(store_type, snapshot.turn, "plan-stop-advanced")
        if (
            store_type == STORE_HOME
            and self._equipment_transaction_session is not None
            and self._equipment_transaction_session.required_context == "home"
        ):
            self._abandon_blocked_equipment_transaction(snapshot)


    def _rearm_town_store_for_new_work(
        self, store_type: int, *, release_visit_bound: bool = False
    ) -> None:
        """Release a completed stop when the current stop creates new work there."""
        home_visit = getattr(self, "_home_visit", None)
        if (
            store_type == STORE_HOME
            and home_visit is not None
            and home_visit.attempts_used >= home_visit.attempt_limit
        ):
            return
        self._town_store_attempted.pop(store_type, None)
        if release_visit_bound:
            self._town_visit_ledger.blocked_stores.discard(store_type)
            self._town_visit_ledger.blocked_store_limits.pop(store_type, None)
            self._town_visit_ledger.approach_fails.pop(store_type, None)
        if (
            release_visit_bound
            and store_type == STORE_HOME
            and self._calibration_restore_signatures
        ):
            self._town_visit_ledger.need_attempts.pop(
                "calibration-restore", None
            )
        plan = self._town_errand_plan
        if plan is None:
            return
        plan.completed_this_visit[:] = [
            store for store in plan.completed_this_visit if store != store_type
        ]
        plan.blocked_this_visit[:] = [
            store for store in plan.blocked_this_visit if store != store_type
        ]
        plan.skipped_latched[:] = [
            store for store in plan.skipped_latched if store != store_type
        ]

    def _town_store_visit_limit(self, store_type: int) -> int:
        """Return the user-authorised visit-local terminal ceiling for Home.

        The authorised 300 Home visits cover outstanding equipment work,
        including applying an optimizer result after the optimizer succeeds.
        Mixed Home work within that interval is part of completing the work;
        Later Home work retains the ordinary hard terminal. Non-Home routing is
        state-based and must never ask for a visit limit.
        """
        if store_type != STORE_HOME:
            raise ValueError("non-Home stores have no visit-count limit")
        if store_type == STORE_HOME and self._outstanding_equipment_work():
            return CALIBRATION_HOME_VISIT_LIMIT
        return TOWN_STOP_PASS_LIMIT

    def _town_store_blocked_under_applicable_bound(self, store_type: int) -> bool:
        """Return whether the recorded block has authority over current work."""
        if store_type != STORE_HOME:
            return False
        if store_type not in self._town_visit_ledger.blocked_stores:
            return False
        authority = self._town_visit_ledger.blocked_store_limits.get(store_type)
        return authority is None or authority == self._town_store_visit_limit(store_type)



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
            for stat, sval in RESTORE_POTION_SVAL_BY_STAT.items():
                if item.tval == TVAL_POTION and item.sval == sval:
                    self._remember_departure_price(
                        f"stat-restore:{stat}", item.price
                    )
        self._observe_cross_town_shelf(snapshot)

    @staticmethod
    def _cross_town_item_categories(item: StoreItem) -> tuple[str, ...]:
        """Return expedition shortage categories concretely supplied by a ware."""
        categories: list[str] = []
        if item.is_recall_scroll:
            categories.append("recall")
        if item.is_teleport_scroll:
            categories.append("teleport")
        if item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
            categories.append("cure-critical")
        if item.is_oil:
            categories.append("oil")
        if item.tval == TVAL_FOOD and item.sval >= FOOD_MIN_SVAL:
            categories.append("food")
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
            categories.append("identification-source:normal")
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
            categories.append("identification-source:full")
        if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY:
            categories.append("identify-staff")
        if item.tval == TVAL_LITE and item.sval in {
            SV_LITE_TORCH,
            SV_LITE_LANTERN,
        }:
            categories.append("light")
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_REMOVE_CURSE:
            categories.append("remove-curse")
        for stat, sval in RESTORE_POTION_SVAL_BY_STAT.items():
            if item.tval == TVAL_POTION and item.sval == sval:
                categories.append(f"stat-restore:{stat}")
        return tuple(categories)

    def _observe_cross_town_shelf(self, snapshot: Snapshot) -> None:
        """Record positive or negative shelf facts for live local suppliers."""
        store = snapshot.store
        if store is None:
            return
        offered: dict[str, list[tuple[int, int]]] = {}
        for item in store.items:
            for category in self._cross_town_item_categories(item):
                offered.setdefault(category, []).append(
                    (
                        item.price,
                        max(1, item.pval)
                        if category == "identify-staff"
                        else max(1, item.count),
                    )
                )
        observed_categories = set(offered)
        observed_categories.update(
            category
            for category in (
                "recall",
                "teleport",
                "cure-critical",
                "oil",
                "food",
                "identification-source:normal",
                "identification-source:full",
                "identify-staff",
                "light",
                "remove-curse",
                *(f"stat-restore:{stat}" for stat in RESTORE_POTION_SVAL_BY_STAT),
            )
            if store.store_type in self._cross_town_supplier_types(snapshot, category)
        )
        for category in observed_categories:
            self._town_visit_ledger.shelf_observations[
                (store.store_type, category)
            ] = tuple(offered.get(category, ()))

    def _cross_town_supplier_types(
        self, snapshot: Snapshot, category: str
    ) -> tuple[int, ...]:
        """Return every local store eligible to supply an expedition shortage."""
        supply_kind = {
            "recall": "recall",
            "teleport": "teleport",
            "cure-critical": "cure",
            "oil": "oil",
            "food": "food",
        }.get(category)
        if supply_kind is not None:
            ledger = self._supply_ledger(snapshot, self._planned_depth())
            return tuple(
                dict.fromkeys(
                    store_type
                    for status in ledger.values()
                    if status.kind == supply_kind
                    for store_type in status.stores
                )
            )
        if category.startswith("identification-source:"):
            return (STORE_ALCHEMIST,)
        if category == "identify-staff":
            return (STORE_MAGIC,)
        if category == "light":
            return (STORE_GENERAL,)
        if category == "remove-curse":
            return (STORE_TEMPLE,)
        if category.startswith("stat-restore:"):
            return (STORE_ALCHEMIST,)
        return ()

    def _cross_town_shortages(
        self, snapshot: Snapshot
    ) -> list[tuple[str, int]]:
        """Return shop-purchasable departure shortages, including latched ones."""
        shortages: list[tuple[str, int]] = []
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        category = {
            "recall": "recall",
            "teleport": "teleport",
            "cure": "cure-critical",
            "oil": "oil",
            "food": "food",
        }
        for status in ledger.values():
            missing = max(0, status.required_departure - status.count)
            if missing:
                shortages.append((category[status.kind], missing))
        if self._identification_need is not None:
            shortages.append(
                (
                    "identification-source:full"
                    if self._identification_need == "full"
                    else "identification-source:normal",
                    1,
                )
            )
        identify_charges = sum(
            item.charges
            for item in snapshot.inventory
            if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
        )
        if not self._identify_staff_ready(snapshot):
            shortages.append(
                ("identify-staff", max(1, STAFF_IDENTIFY_MIN_CHARGES - identify_charges))
            )
        if not self._light_ready(snapshot):
            shortages.append(("light", 1))
        if self._has_normal_remove_curse_target(snapshot) and self._find_remove_curse_scroll(snapshot) is None:
            shortages.append(("remove-curse", 1))
        for stat in snapshot.player.drained_stats:
            if self._carried_restore_potion(snapshot, stat) is None:
                shortages.append((f"stat-restore:{stat}", 1))
        return shortages

    def _cross_town_unobtainable_categories(
        self, snapshot: Snapshot, shortages: list[tuple[str, int]]
    ) -> tuple[str, ...]:
        """Require shelf evidence from every local supplier before escalation."""
        unobtainable: list[str] = []
        for category, _quantity in shortages:
            suppliers = set(self._cross_town_supplier_types(snapshot, category))
            evidence = [
                self._town_visit_ledger.shelf_observations.get(
                    (store_type, category)
                )
                for store_type in suppliers
            ]
            if suppliers and all(observation is not None for observation in evidence):
                # An empty tuple proves an observed stock-out. Non-empty
                # evidence proves local failure only when every matching ware
                # costs more than the player's current gold. In particular, an
                # affordable visible ware vetoes attempts, drift and latches.
                if all(
                    not observation
                    or all(price > snapshot.player.gold for price, _units in observation)
                    for observation in evidence
                ):
                    unobtainable.append(category)
        return tuple(dict.fromkeys(unobtainable))

    def _cross_town_candidate_order(self, snapshot: Snapshot) -> tuple[int, ...]:
        current = self._effective_town_id(snapshot)
        if snapshot.visited_town_ids is None:
            return ()
        return tuple(
            town_id
            for town_id in sorted(set(snapshot.visited_town_ids))
            if town_id != current and town_id in TOWN_TELEPORT_BUILDING_TYPES
        )

    def cross_town_shopping_state(self) -> dict[str, object]:
        expedition = self._cross_town_shopping
        if expedition is None:
            return dict(self._cross_town_shopping_funds)
        return {
            "trigger_town_id": expedition.trigger_town_id,
            "blocking_categories": list(expedition.blocking_categories),
            "shortage_costs": dict(expedition.shortage_costs),
            "reserve": expedition.reserve,
            "required_gold": expedition.required_gold,
            "candidate_order": list(expedition.candidate_order),
            "tried_towns": list(expedition.tried_towns),
            "target_town_id": expedition.target_town_id,
        }

    def _cross_town_shopping_key(self, snapshot: Snapshot) -> str | None:
        shortages = self._cross_town_shortages(snapshot)
        unobtainable = self._cross_town_unobtainable_categories(
            snapshot, shortages
        )
        expedition = self._cross_town_shopping
        if expedition is None:
            if not unobtainable:
                return None
            costs: dict[str, int] = {}
            for category, quantity in shortages:
                observed = self._observed_departure_prices.get(category)
                if observed is None:
                    self._cross_town_shopping_funds = {
                        "trigger_town_id": self._effective_town_id(snapshot),
                        "blocking_categories": list(unobtainable),
                        "missing_price_for": category,
                        "funds_sufficient": None,
                        "candidate_order": list(
                            self._cross_town_candidate_order(snapshot)
                        ),
                        "tried_towns": [],
                    }
                    return None
                price, units = observed
                costs[category] = ceil(quantity / units) * price
            candidates = self._cross_town_candidate_order(snapshot)
            if not candidates:
                return None
            required_gold = sum(costs.values()) + CROSS_TOWN_SHOPPING_RESERVE
            self._cross_town_shopping_funds = {
                "trigger_town_id": self._effective_town_id(snapshot),
                "blocking_categories": list(unobtainable),
                "shortage_costs": dict(costs),
                "reserve": CROSS_TOWN_SHOPPING_RESERVE,
                "required_gold": required_gold,
                "gold": snapshot.player.gold,
                "funds_sufficient": snapshot.player.gold >= required_gold,
                "candidate_order": list(candidates),
                "tried_towns": [],
            }
            if snapshot.player.gold < required_gold:
                # This is intentionally the ordinary fundraising owner and
                # target; the existing mining kit/departure/walk-in rules apply.
                self._planned_mining_runs = None
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                self.last_reason = "town:cross-town-shopping-needs-funds"
                return WAIT_KEY
            expedition = CrossTownShoppingExpedition(
                trigger_town_id=self._effective_town_id(snapshot),
                blocking_categories=unobtainable,
                shortage_costs=costs,
                reserve=CROSS_TOWN_SHOPPING_RESERVE,
                required_gold=required_gold,
                candidate_order=candidates,
            )
            self._cross_town_shopping = expedition

        current = self._effective_town_id(snapshot)
        if (
            expedition.target_town_id is not None
            and current == expedition.target_town_id
        ):
            if current not in expedition.tried_towns:
                expedition.tried_towns.append(current)
            expedition.target_town_id = None
        for next_town in expedition.candidate_order:
            if next_town in expedition.tried_towns or next_town == current:
                continue
            expedition.target_town_id = next_town
            key = self._town_teleport_key(snapshot, next_town)
            if key is not None:
                self.last_reason = f"town:cross-town-shopping:travel-{next_town}"
                return key
            # A refused or unroutable trip is terminal for this visit.  Do not
            # approach another Inn destination on the following decision.
            expedition.tried_towns.extend(
                town_id for town_id in expedition.candidate_order
                if town_id not in expedition.tried_towns
            )
            expedition.target_town_id = None
            return None
        return None

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



    def _town_terminal_transitions(self, snapshot: Snapshot) -> None:
        """Apply ordered state changes only after the plan walk is exhausted."""
        if self._town_restock_suppressed or snapshot.player.class_id < 0:
            return
        if self._fundraising_mode in {"prepare", "mine", "scavenge"} and snapshot.player.gold >= FUNDRAISING_GOLD_TARGET:
            self._fundraising_mode = None
            self._planned_mining_runs = None
            self._town_store_attempted.clear()
        if self._pending_disposal_item is not None:
            target = self._pending_disposal(snapshot)
            if target is None:
                self._clear_pending_disposal()
            else:
                store_type = self._dominated_disposal_store(target)
                if store_type is None or store_type in self._disposal_store_attempts:
                    self._destroy_pending = True
            return
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            if not self._fundraising_food_ready(snapshot):
                store_type = STORE_MAGIC if snapshot.player.food_type == FOOD_TYPE_MANA else STORE_GENERAL
                if store_type in self._town_store_attempted:
                    self._fundraising_mode = "scavenge"
                    self._scavenge_entry_gold = snapshot.player.gold
                    self._town_blocked_reason = None
                    return
            if self._planned_mining_runs is None:
                self._activate_partial_mining_plan(snapshot)
            detection_low = self._count_treasure_detection_scrolls(snapshot) < self._mining_detection_scroll_target(snapshot)
            if detection_low and STORE_HOME in self._town_store_attempted and STORE_ALCHEMIST in self._town_store_attempted:
                if self._activate_partial_mining_plan(snapshot) or self._try_normal_expedition_after_detection_stockout(snapshot):
                    return
                self._fundraising_mode = "scavenge"
                self._scavenge_entry_gold = snapshot.player.gold
            if self._fundraising_mode != "scavenge" and not self._has_digging_tool(snapshot) and STORE_HOME in self._town_store_attempted and STORE_GENERAL in self._town_store_attempted:
                self._fundraising_mode = "scavenge"
                self._scavenge_entry_gold = snapshot.player.gold
            if not self._fundraising_light_ready(snapshot) and STORE_GENERAL in self._town_store_attempted:
                self._retry_after_store_restock(snapshot, (STORE_GENERAL,))
            return
        if self._identification_need is not None:
            plan = self._town_errand_plan
            exhausted = set(plan.completed_this_visit) | set(plan.blocked_this_visit) if plan is not None else set()
            if STORE_ALCHEMIST not in self._town_store_attempted and STORE_ALCHEMIST not in exhausted:
                return
            source_obtainability = self._identification_source_obtainability(
                snapshot, full=self._identification_need == "full"
            )
            if source_obtainability != "unavailable":
                if self._find_identification_source(
                    snapshot,
                    full=self._identification_need == "full",
                    reliable_only=self._identification_requires_reliable_source(snapshot),
                ) is None:
                    self._retain_identification_source_owner()
                return
            if self._identification_need == "full":
                if self._conquest_target(snapshot) is not None:
                    self._defer_identification_for_conquest(snapshot)
                    if snapshot.player.gold < FUNDRAISING_START_GOLD:
                        self._start_fundraising(snapshot)
                    return
                if self._start_fundraising(snapshot):
                    return
                if STORE_ALCHEMIST in self._town_restock_rechecked:
                    self._defer_identification_for_conquest(snapshot)
                    self._town_restock_wait_until = None
                    self._town_restock_waiting_for = ()
                    return
                self._retry_after_store_restock(snapshot, (STORE_ALCHEMIST,))
                return
            pending = self._pending_inventory_item(snapshot)
            candidate = (
                self._item_signature(pending)
                if pending is not None
                else self._identification_candidate
            )
            candidate_origins = {
                owned.origin
                for owned in self._equipment_catalog.items
                if candidate is not None
                and self._item_signature(owned.item) == candidate
            }
            if candidate is not None and candidate_origins & {"pack", "equipped"}:
                self._town_unidentifiable_carried_sigs.add(candidate)
                self._equipment_optimization_signature = None
                self._equipment_optimization_preparation = None
            elif candidate is not None and "home" in candidate_origins:
                self._defer_home_item(candidate, "full-identify-expedition-capacity")
            elif self._device_identification_candidate is not None:
                self._deferred_device_items.add(self._device_identification_candidate)
            self._home_pending_item = None
            self._home_pending_slot = None
            self._identification_need = None
            self._identification_candidate = None
            self._device_identification_candidate = None
            self._home_candidate_waiting = True
            if self._home_available(snapshot) and not self._equipment_catalog.home_scan_complete:
                self._rearm_town_store_for_new_work(STORE_HOME)
            return
        recall = self._supply_ledger(snapshot, self._planned_depth())["recall"]
        recall_stores = (STORE_TEMPLE, STORE_ALCHEMIST)
        if (not self._recall_ready(snapshot) or not self._recall_departure_ready(snapshot)) and all(store in self._town_store_attempted for store in recall_stores):
            if recall.count == 0:
                if (
                    self._town_restock_wait_until is None
                    and all(
                        store in self._town_restock_rechecked
                        for store in recall_stores
                    )
                ):
                    if not self._food_ready(snapshot):
                        food_store = (
                            STORE_MAGIC
                            if snapshot.player.food_type == FOOD_TYPE_MANA
                            else STORE_GENERAL
                        )
                        self._town_store_attempted.pop(food_store, None)
                    else:
                        self._town_blocked_reason = (
                            "restocked-recall-unavailable"
                        )
                    return
                self._retry_after_store_restock(snapshot, recall_stores)
                return
            if not self._recall_departure_ready(snapshot):
                if self._start_fundraising(snapshot):
                    return
                self._retry_after_store_restock(snapshot, recall_stores)
                return
        shortages = (
            (not self._food_ready(snapshot), STORE_MAGIC if snapshot.player.food_type == FOOD_TYPE_MANA else STORE_GENERAL),
            (not self._light_ready(snapshot), STORE_GENERAL),
            (not self._teleport_ready(snapshot), STORE_ALCHEMIST),
            (not self._identify_staff_ready(snapshot), STORE_MAGIC),
        )
        for missing, store_type in shortages:
            if missing and store_type in self._town_store_attempted:
                if not self._start_fundraising(snapshot):
                    self._retry_after_store_restock(snapshot, (store_type,))
                return
        cure_stores = (STORE_TEMPLE, STORE_ALCHEMIST)
        if not self._cure_critical_ready(snapshot) and all(store in self._town_store_attempted for store in cure_stores):
            if not self._start_fundraising(snapshot):
                self._retry_after_store_restock(snapshot, cure_stores)
            return
        if self._retry_processed_home_identification(snapshot) or self._start_identification_fundraising(snapshot):
            return
        self._town_restock_wait_until = None

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
        self._fundraising_mode = "prepare"
        self._town_store_attempted.clear()
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
        self._town_errand_plan = None
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
        self._town_errand_plan = None
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











    def _set_town_store_attempted(
        self, store_type: int, turn: int, site_label: str, *, if_absent: bool = False
    ) -> None:
        """Set the existing latch and retain observation-only Home provenance."""
        if if_absent and store_type in self._town_store_attempted:
            return
        self._town_store_attempted[store_type] = turn
        if store_type == STORE_HOME:
            entry = {"turn": turn, "site": site_label}
            self._home_latch_active = entry
            self._home_latch_history = [*self._home_latch_history, entry][-8:]


    def _purchase_has_fresh_home_absence(
        self, snapshot: Snapshot, item: StoreItem
    ) -> ProcurementHomeGate:
        """Release a buy only for fresh absence or a statically Home-less town."""
        evaluated = self._evaluate_purchase_home_gate(snapshot, item)
        item_class = self._procurement_class(item)
        self._home_procurement_fallthrough_equivalence = (
            self._procurement_equivalence(item_class)
        )
        if not self._home_knowledge_current:
            self._home_procurement_probe = item_class
            if not self._current_town_has_home(snapshot):
                self._home_procurement_probe = None
                self._home_procurement_fallthrough = "town-without-home"
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE, "wrapper-town-without-home", wrapper_fallthrough="town-without-home")
            if not self._home_available(snapshot):
                self._home_procurement_probe = None
                self._record_purchase_home_refusal(
                    "town:blocked:procurement-home-unavailable"
                )
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "wrapper-home-unavailable")
            visit = self._store_visit
            transferred_visit = getattr(
                self._town_turn_arbiter, "_transferred_visit", None
            )
            if transferred_visit is not None:
                visit = transferred_visit
            filed = self._ensure_home_visit_request(snapshot)
            if (
                filed
                and visit is not None
                and visit.store_type != STORE_HOME
            ):
                self._home_procurement_probe = None
                self._record_purchase_home_refusal(
                    "shop:home-first-yields-to-current-visit"
                )
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "wrapper-yield-current-visit")
            approach = (
                self._shopping_approach_step(snapshot, STORE_HOME) if filed else None
            )
            if not filed or approach is None:
                self._home_procurement_probe = None
                self._record_purchase_home_refusal(
                    "town:blocked:procurement-home-unroutable"
                )
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "wrapper-home-unroutable")
            return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "wrapper-stale-knowledge-route-home")
        candidate = self._home_procurement_candidate(item_class)
        failure = getattr(self, "_home_procurement_withdraw_failure", None)
        viable_class_matches = self._home_procurement_viable_class_matches(
            item_class
        )
        viable_item = self._home_procurement_viable_item(item_class)
        if (
            viable_item is not None
            and self._procurement_missing_amount(snapshot, viable_item) <= 0
        ):
            self._home_procurement_probe = None
            self._home_procurement_fallthrough = "no-procurement-need"
            return self._record_home_gate(
                snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE,
                "wrapper-no-procurement-need",
                wrapper_fallthrough="no-procurement-need",
            )
        all_viable_deferred = viable_class_matches > 0 and candidate is None
        if all_viable_deferred or (
            failure is not None
            and failure.get("item_class") == self._procurement_equivalence(item_class)
            and viable_class_matches > 0
        ):
            self._home_procurement_probe = None
            self._record_purchase_home_refusal(
                "town:blocked:home-withdraw-failed-stock-present"
            )
            return self._record_home_gate(
                snapshot, item, ProcurementHomeGate.BLOCKED,
                "wrapper-withdraw-failed-stock-present",
            )
        if candidate is not None:
            missing = self._procurement_missing_amount(snapshot, candidate)
            if missing <= 0:
                self._home_procurement_probe = None
                self._home_procurement_fallthrough = "no-procurement-need"
                return self._record_home_gate(
                    snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE,
                    "wrapper-no-procurement-need",
                    wrapper_fallthrough="no-procurement-need",
                )
            identity = self._item_signature(candidate)
            self._home_procurement_probe = item_class
            self._home_pending_item = identity
            self._home_pending_quantity = min(
                candidate.count,
                max(1, missing),
            )
            if not hasattr(self, "_home_pending_quantities"):
                self._home_pending_quantities = {}
            self._home_pending_quantities[identity] = self._home_pending_quantity
            self._queue_home_procurement_batch(snapshot, candidate)
            self._home_withdrawal_queued = True
            return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "wrapper-candidate-home-first")
        self._home_procurement_probe = None
        self._home_procurement_fallthrough = "fresh-catalogue-absence"
        return self._record_home_gate(snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE, "wrapper-fresh-catalogue-absence", wrapper_fallthrough="fresh-catalogue-absence")

    def _record_purchase_home_refusal(self, reason: str) -> None:
        """Retain a probe result without publishing it as a decided stop."""
        self._shop_selector_diagnostics["composition_refusal"] = reason
        self._shop_selector_diagnostics["composition_refusal_sequence"] = (
            self._decision_sequence
        )

    def _publish_purchase_home_block(self) -> None:
        """Publish the current probe's terminal only at a decided WAIT."""
        reason = self._shop_selector_diagnostics.get("composition_refusal")
        sequence = self._shop_selector_diagnostics.get(
            "composition_refusal_sequence"
        )
        if sequence == self._decision_sequence and reason in {
            "town:blocked:home-withdraw-failed-stock-present",
            "town:blocked:procurement-home-unavailable",
            "town:blocked:procurement-home-unroutable",
        }:
            self.last_reason = reason
            if reason == "town:blocked:home-withdraw-failed-stock-present":
                self._town_blocked_reason = reason

    def _evaluate_purchase_home_gate(
        self, snapshot: Snapshot, item: StoreItem
    ) -> ProcurementHomeGate:
        """Evaluate Home-first purchase policy without changing policy state."""
        if not self._home_knowledge_current:
            if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
                town_has_home = True
                home_available = True
            else:
                visible_home = any(
                    grid.store_number == STORE_HOME for grid in snapshot.grids.values()
                )
                town_has_home = (
                    snapshot.town_id in TOWN_IDS_WITH_HOME
                    or snapshot.town_id not in {None, -1, ZUL_TOWN_ID}
                    or visible_home
                )
                home_available = bool(
                    visible_home or self._town_store_positions.get(STORE_HOME)
                )
            if not town_has_home:
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE, "evaluate-stale-town-without-home")
            if not home_available:
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "evaluate-stale-home-unavailable")
            visit = self._store_visit
            if visit is not None and visit.store_type != STORE_HOME:
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "evaluate-stale-current-visit")
            if self._town_blocked_reason is not None and (
                self._town_blocked_reason != "repetition"
            ):
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "evaluate-stale-town-blocked")
            if (
                STORE_HOME in self._town_store_attempted
                or STORE_HOME in self._town_visit_ledger.blocked_stores
                or self._town_visit_ledger.approach_fails[STORE_HOME]
                >= self._town_store_visit_limit(STORE_HOME)
            ):
                return self._record_home_gate(snapshot, item, ProcurementHomeGate.BLOCKED, "evaluate-stale-home-latched")
            step = self._nearest_goal_step(
                snapshot, lambda grid: grid.store_number == STORE_HOME
            )
            if step is None and self._town_map_active(snapshot):
                step = self._town_map_goal_step(
                    snapshot, self._town_map.store_position(STORE_HOME)
                )
            home_positions = self._town_store_positions.get(STORE_HOME)
            goal = (
                min(
                    home_positions,
                    key=lambda position: snapshot.player.position.distance_to(position),
                )
                if home_positions
                else None
            )
            if goal is None and self._town_map_active(snapshot):
                goal = self._town_map.store_position(STORE_HOME)
            if (
                step is None
                and goal is not None
                and snapshot.player.position.distance_to(goal) >= 3
            ):
                step = goal
            result = ProcurementHomeGate.HOME_FIRST if step is not None else ProcurementHomeGate.BLOCKED
            return self._record_home_gate(snapshot, item, result, "evaluate-stale-route-found" if step is not None else "evaluate-stale-route-missing")
        item_class = self._procurement_class(item)
        candidate = self._home_procurement_candidate(item_class)
        failure = getattr(self, "_home_procurement_withdraw_failure", None)
        viable_class_matches = self._home_procurement_viable_class_matches(
            item_class
        )
        viable_item = self._home_procurement_viable_item(item_class)
        if (
            viable_item is not None
            and self._procurement_missing_amount(snapshot, viable_item) <= 0
        ):
            return self._record_home_gate(
                snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE,
                "evaluate-no-procurement-need",
            )
        all_viable_deferred = viable_class_matches > 0 and candidate is None
        if all_viable_deferred or (
            failure is not None
            and failure.get("item_class") == self._procurement_equivalence(item_class)
            and viable_class_matches > 0
        ):
            return self._record_home_gate(
                snapshot, item, ProcurementHomeGate.BLOCKED,
                "evaluate-withdraw-failed-stock-present",
            )
        if candidate is not None:
            if self._procurement_missing_amount(snapshot, candidate) <= 0:
                return self._record_home_gate(
                    snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE,
                    "evaluate-no-procurement-need",
                )
            return self._record_home_gate(snapshot, item, ProcurementHomeGate.HOME_FIRST, "evaluate-candidate-home-first")
        return self._record_home_gate(snapshot, item, ProcurementHomeGate.ALLOW_PURCHASE, "evaluate-no-candidate")

    def _wanted_purchase_is_home_first_refused(
        self, snapshot: Snapshot, store_type: int
    ) -> bool:
        """Recognize an observed wanted purchase that Home-first would refuse."""
        observed_store = snapshot.store
        if observed_store is None:
            observation = self._shop_observation
            if observation is None:
                return False
            observed_store = observation[0]
        if observed_store.store_type != store_type:
            return False
        item = self._next_purchase(replace(snapshot, store=observed_store))
        return item is not None and self._evaluate_purchase_home_gate(
            snapshot, item
        ) is not ProcurementHomeGate.ALLOW_PURCHASE

    def _mana_survival_sale_candidate(
        self, snapshot: Snapshot, store_type: int
    ) -> InventoryItem | None:
        """Use only existing retention-safe, inscription-safe sale contracts."""
        if store_type == STORE_ALCHEMIST:
            return self._first_item(
                snapshot,
                lambda item: item.is_scroll
                and self._retention_surplus(snapshot, item) > 0
                and self._item_signature(item) not in self._unsellable_items,
            )
        if store_type == STORE_WEAPON:
            return self._first_item(
                snapshot,
                lambda item: item.is_ammo
                and self._retention_surplus(snapshot, item) > 0
                and self._item_signature(item) not in self._unsellable_items,
            )
        return None

    def _next_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        """Apply the cheap fundraising-kit reserve to the normal buy order."""
        item = self._next_purchase_unreserved(snapshot)
        if item is None or item.is_digging_tool or item.is_treasure_detection_scroll:
            return item
        if (
            self._opening_q34_torch_shortage(snapshot) > 0
            and item.tval == TVAL_LITE
            and item.sval == SV_LITE_TORCH
        ):
            # The fresh-character contract is Q34 first.  Reserving the entire
            # 100g mining-kit budget here made a 100g birth character visit the
            # correct store, reject every torch, and fall back to Home.
            return item
        reserve = self._fundraising_kit_reserve(snapshot)
        if reserve == 0:
            return item
        quantity = self._purchase_quantity(snapshot, item)
        if snapshot.player.gold - item.price * quantity < reserve:
            return None
        return item

    @staticmethod
    def _purchase_diagnostic_category(item: StoreItem) -> str:
        """Return a compact diagnostic label without participating in selection."""
        if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY:
            return "identify-staff"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
            return "identify"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
            return "star-identify"
        if item.is_recall_scroll:
            return "recall"
        if item.is_teleport_scroll:
            return "teleport"
        if item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
            return "cure-critical"
        if item.tval == TVAL_POTION and item.sval == SV_POTION_SPEED:
            return "speed"
        if item.tval == TVAL_POTION and item.sval == SV_POTION_HEALING:
            return "healing"
        if item.is_treasure_detection_scroll:
            return "treasure-detection"
        if item.is_digging_tool:
            return "digging-tool"
        if item.is_ammo:
            return "ammo"
        if item.is_lantern:
            return "lantern"
        if item.is_oil:
            return "oil"
        if item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH:
            return "torch"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_REMOVE_CURSE:
            return "remove-curse"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_REMOVE_CURSE:
            return "star-remove-curse"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_ENCHANT_WEAPON_TO_HIT:
            return "enchant-tohit"
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_ENCHANT_WEAPON_TO_DAM:
            return "enchant-todam"
        if item.tval == TVAL_FOOD:
            return "food"
        if item.tval in {TVAL_WAND, TVAL_STAFF}:
            return "device"
        return "other"

    @staticmethod
    def _shop_candidate_diagnostics(
        item: StoreItem, category: str
    ) -> dict[str, object]:
        candidate: dict[str, object] = {
            "category": category,
            "name": item.name,
            "letter": item.letter,
            "price": item.price,
            "count": item.count,
        }
        if item.tval in {TVAL_WAND, TVAL_STAFF}:
            candidate["charges"] = item.charges
        return candidate

    def _record_shop_selector_diagnostics(
        self, snapshot: Snapshot, key: str
    ) -> None:
        """Capture selector evidence after the action; gameplay never consumes it."""
        store = snapshot.store
        diagnostic_snapshot = snapshot
        if store is None and self._shop_observation is not None:
            store = self._shop_observation[0]
            diagnostic_snapshot = replace(snapshot, store=store)

        wanted_item = (
            self._next_purchase_unreserved(diagnostic_snapshot)
            if store is not None else None
        )
        wanted = None
        if wanted_item is not None:
            wanted = self._shop_candidate_diagnostics(
                wanted_item, self._purchase_diagnostic_category(wanted_item)
            )

        selected_item = None
        if (
            store is not None
            and store.store_type != STORE_HOME
            and key.startswith(BUY_KEY)
            and len(key) > 1
        ):
            selected_item = next(
                (item for item in store.items if item.letter == key[1]), None
            )

        considered_item = selected_item or wanted_item
        considered = None
        rejection_reason = (
            "observed-page-nothing-wanted"
            if store is not None else "no-store-page-observed"
        )
        if considered_item is not None:
            considered = self._shop_candidate_diagnostics(
                considered_item,
                self._purchase_diagnostic_category(considered_item),
            )
            if selected_item is not None:
                rejection_reason = "selected"
            elif wanted_item is not None:
                reserve = self._fundraising_kit_reserve(diagnostic_snapshot)
                quantity = self._purchase_quantity(diagnostic_snapshot, wanted_item)
                reserved = (
                    not wanted_item.is_digging_tool
                    and not wanted_item.is_treasure_detection_scroll
                    and not (
                        self._opening_q34_torch_shortage(snapshot) > 0
                        and wanted_item.tval == TVAL_LITE
                        and wanted_item.sval == SV_LITE_TORCH
                    )
                    and reserve > 0
                    and snapshot.player.gold
                    - wanted_item.price * quantity
                    < reserve
                )
                rejection_reason = "reserved" if reserved else "preempted"

        composition_refusal = self._shop_selector_diagnostics.get(
            "composition_refusal"
        )
        composition_refusal_sequence = self._shop_selector_diagnostics.get(
            "composition_refusal_sequence"
        )
        self._shop_selector_diagnostics = {
            "winning_rung": self.last_reason,
            "gold": snapshot.player.gold,
            "wanted_purchase": wanted,
            "considered_candidate": considered,
            "rejection_reason": rejection_reason,
        }
        if (
            composition_refusal is not None
            and composition_refusal_sequence == self._decision_sequence
        ):
            self._shop_selector_diagnostics["composition_refusal"] = (
                composition_refusal
            )
            self._shop_selector_diagnostics["composition_refusal_sequence"] = (
                composition_refusal_sequence
            )
        invariant_defect = getattr(
            self, "_town_progress_invariant_defect", {}
        )
        if invariant_defect:
            self._shop_selector_diagnostics["town_progress_invariant"] = dict(
                invariant_defect
            )
        withdrawal_defect = getattr(
            self, "_withdrawal_unfulfilled_defect", {}
        )
        if withdrawal_defect:
            self._shop_selector_diagnostics["withdrawal_unfulfilled"] = dict(
                withdrawal_defect
            )


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

    def _black_market_optional_purchase(
        self, snapshot: Snapshot
    ) -> StoreItem | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_BLACK:
            return None
        optional = [
            item
            for item in store.items
            if (
                (
                    item.tval == TVAL_POTION
                    and item.sval in {SV_POTION_SPEED, SV_POTION_HEALING}
                )
                or (
                    item.tval == TVAL_WAND
                    and item.sval == SV_WAND_STONE_TO_MUD
                    and item.charges > 0
                    and not self._has_charged_stone_to_mud(snapshot)
                )
            )
            and item.count > 0
            and item.price <= snapshot.player.gold
        ]
        if not optional:
            return None

        def held(item: StoreItem) -> int:
            if item.tval == TVAL_WAND:
                return int(self._has_charged_stone_to_mud(snapshot))
            return self._count_potion(snapshot, item.sval)

        def kind_rank(item: StoreItem) -> int:
            if item.tval == TVAL_WAND:
                return 2
            return int(item.sval != SV_POTION_SPEED)

        return min(optional, key=lambda item: (held(item), kind_rank(item)))

    def _live_purchase_need(
        self, snapshot: Snapshot, category: str,
    ) -> NeedSpec | None:
        return next(
            (
                need for need in self._town_need_registry()
                if need.category == category and need.produces(snapshot)
            ),
            None,
        )

    def _mandatory_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        """Select an affordable ware that closes a departure requirement."""
        store = snapshot.store
        if store is None:
            return None
        strategy = self._carry_procurement_strategy(snapshot)
        if strategy is not None:
            carry = self._quest_carry_purchase(snapshot, strategy)
            if carry is not None:
                return carry
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        if (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and ledger["food"].count < ledger["food"].required_departure
        ):
            mana_food = self._mana_food_purchase(snapshot)
            if mana_food is not None:
                return mana_food
        predicates = (
            ("recall", lambda item: item.is_recall_scroll),
            (
                "food",
                lambda item: snapshot.player.food_type != FOOD_TYPE_MANA
                and item.tval == TVAL_FOOD
                and item.sval >= FOOD_MIN_SVAL,
            ),
            ("light", lambda item: item.is_lantern),
            ("oil", lambda item: item.is_oil),
            ("teleport", lambda item: item.is_teleport_scroll),
            (
                "cure",
                lambda item: item.tval == TVAL_POTION
                and item.sval == SV_POTION_CURE_CRITICAL,
            ),
        )
        for kind, matches in predicates:
            if kind == "light":
                if self._planned_depth() < 2 or self._owns_lantern(snapshot):
                    continue
            else:
                status = ledger[kind]
                if status.count >= status.required_departure:
                    continue
            candidate = next(
                (
                    item
                    for item in store.items
                    if item.count > 0
                    and item.price <= snapshot.player.gold
                    and matches(item)
                ),
                None,
            )
            if candidate is not None:
                return candidate
        return None

    def _next_purchase_unreserved(self, snapshot: Snapshot) -> StoreItem | None:
        """The next thing to buy from the current store, or None when done."""
        store = snapshot.store
        if store is None:
            return None
        gold = snapshot.player.gold
        if snapshot.player.class_id < 0:
            if not self._owns_lantern(snapshot):
                lantern = next(
                    (it for it in store.items if it.is_lantern and it.price <= gold),
                    None,
                )
                if lantern is not None:
                    return lantern
            if self._oil_below_departure_target(snapshot):
                oil = next(
                    (it for it in store.items if it.is_oil and it.price <= gold),
                    None,
                )
                if oil is not None:
                    return oil
            if (
                snapshot.player.food_type == FOOD_TYPE_RATION
                and self._needs_food_restock(snapshot)
            ):
                food = next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_FOOD
                        and it.sval >= FOOD_MIN_SVAL
                        and it.price <= gold
                    ),
                    None,
                )
                if food is not None:
                    return food
            return None
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            if (
                not self._has_withdrawable_digging_tool(snapshot)
                or self._digger_buy_fallback_available(snapshot)
            ):
                digger = next(
                    (it for it in store.items if it.is_digging_tool and it.price <= gold),
                    None,
                )
                if digger is not None:
                    return digger
            if self._count_treasure_detection_scrolls(snapshot) < 1:
                detection = next(
                    (
                        it
                        for it in store.items
                        if it.is_treasure_detection_scroll and it.price <= gold
                    ),
                    None,
                )
                if detection is not None:
                    return detection
            if not self._food_ready(snapshot):
                food = None
                if snapshot.player.food_type == FOOD_TYPE_MANA:
                    food = self._mana_food_purchase(snapshot)
                elif snapshot.player.food_type == FOOD_TYPE_RATION:
                    food = next(
                        (
                            it
                            for it in store.items
                            if it.tval == TVAL_FOOD
                            and it.sval >= FOOD_MIN_SVAL
                            and it.price <= gold
                        ),
                        None,
                    )
                if food is not None:
                    return food
            scrolls_needed = (
                self._mining_detection_scroll_target(snapshot)
                + DETECTION_SCROLL_BUFFER
            )
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                detection_scroll = next(
                    (
                        it
                        for it in store.items
                        if it.is_treasure_detection_scroll and it.price <= gold
                    ),
                    None,
                )
                if detection_scroll is not None:
                    return detection_scroll
            if (
                not self._has_withdrawable_digging_tool(snapshot)
                or self._digger_buy_fallback_available(snapshot)
            ):
                digger = next(
                    (it for it in store.items if it.is_digging_tool and it.price <= gold),
                    None,
                )
                if digger is not None:
                    return digger
            if not self._fundraising_light_ready(snapshot):
                lantern = next(
                    (it for it in store.items if it.is_lantern and it.price <= gold),
                    None,
                )
                if lantern is not None:
                    return lantern
            if self._oil_below_departure_target(snapshot):
                oil = next(
                    (it for it in store.items if it.is_oil and it.price <= gold),
                    None,
                )
                if oil is not None:
                    return oil
            if (
                self._planned_depth() <= TORCH_THROW_MAX_DEPTH
                and self._matching_ammo(snapshot) is None
                and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
            ):
                # Shallow mining trips carry throwing torches (user directive);
                # this ranks BELOW the whole kit so it can never starve it.
                torch = next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_LITE
                        and it.sval == SV_LITE_TORCH
                        and it.price <= gold
                    ),
                    None,
                )
                if torch is not None:
                    return torch
            if (
                self._withdrawable_digging_tool_count(snapshot) < 2
                or self._digger_buy_fallback_available(snapshot)
            ):
                digger = next(
                    (
                        item
                        for item in store.items
                        if item.is_digging_tool and item.price <= gold
                    ),
                    None,
                )
                if digger is not None:
                    return digger
            return None

        mandatory = self._mandatory_purchase(snapshot)
        if mandatory is not None:
            return mandatory

        if self._identification_need is not None:
            full = self._identification_need == "full"
            if self._find_identification_source(
                snapshot,
                full=full,
                reliable_only=self._identification_requires_reliable_source(snapshot),
            ) is None:
                # No identify source in hand yet: buy one here if this store sells
                # it. If it does not, fall through rather than abandoning the trip.
                wanted_sval = SV_SCROLL_STAR_IDENTIFY if full else SV_SCROLL_IDENTIFY
                scroll = next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_SCROLL
                        and it.sval == wanted_sval
                        and it.price <= gold
                    ),
                    None,
                )
                if scroll is not None:
                    return scroll
            # We either already hold an identify source or this store does not
            # stock the scroll. Do NOT return here: fall through to the departure
            # supplies below so a single visit still buys the recall/teleport/cure
            # items the store sells. Returning early marked the Alchemist
            # 'attempted' after an identify errand, so the bot never bought the
            # teleport scrolls it also sells and stranded itself wandering town.

        restore = self._restore_potion_purchase(snapshot)
        if restore is not None:
            return restore
        strategy = self._carry_procurement_strategy(snapshot)
        if strategy is not None:
            force = strategy.required_force
            carry = self._quest_carry_purchase(snapshot, strategy)
            if carry is not None:
                return carry
            if self._exact_potion_count(snapshot, SV_POTION_SPEED) < int(force.get("speed_potions", 0)):
                speed = next((it for it in store.items if it.tval == TVAL_POTION
                              and it.sval == SV_POTION_SPEED and it.price <= gold), None)
                if speed is not None:
                    return speed
            healing = self._exact_potion_count(snapshot, SV_POTION_HEALING)
            if healing < int(force.get("heal_potions", 0)):
                heal = next((it for it in store.items if it.tval == TVAL_POTION
                             and it.sval == SV_POTION_HEALING
                             and it.price <= gold), None)
                if heal is not None:
                    return heal
        black_market_optional = self._black_market_optional_purchase(snapshot)
        if black_market_optional is not None:
            return black_market_optional
        if not self._recall_ready(snapshot):
            item = next(
                (it for it in store.items if it.is_recall_scroll and it.price <= gold),
                None,
            )
            if item is not None:
                return item
        if (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and not self._food_ready(snapshot)
        ):
            device = self._mana_food_purchase(snapshot)
            if device is not None:
                return device
        if (
            snapshot.player.food_type == FOOD_TYPE_RATION
            and self._needs_food_restock(snapshot)
        ):
            food = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_FOOD
                    and it.sval >= FOOD_MIN_SVAL
                    and it.price <= gold
                ),
                None,
            )
            if food is not None:
                return food
        if not self._owns_lantern(snapshot):
            lantern = next(
                (it for it in store.items if it.is_lantern and it.price <= gold),
                None,
            )
            if lantern is not None:
                return lantern
        if self._oil_below_departure_target(snapshot):
            oil = next(
                (it for it in store.items if it.is_oil and it.price <= gold),
                None,
            )
            if oil is not None:
                return oil
        if (
            self._planned_depth() <= TORCH_THROW_MAX_DEPTH
            and self._matching_ammo(snapshot) is None
            and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
        ):
            torch = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_LITE
                    and it.sval == SV_LITE_TORCH
                    and it.price <= gold
                ),
                None,
            )
            if torch is not None:
                return torch
        if not self._teleport_ready(snapshot):
            teleport = next(
                (it for it in store.items if it.is_teleport_scroll and it.price <= gold),
                None,
            )
            if teleport is not None:
                return teleport
        if not self._cure_critical_ready(snapshot):
            cure = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_POTION
                    and it.sval == SV_POTION_CURE_CRITICAL
                    and it.price <= gold
                ),
                None,
            )
            if cure is not None:
                return cure
        launcher = self._equipped_launcher(snapshot)
        if (
            launcher is not None
            and self._count_matching_ammo(snapshot) < AMMO_CARRY_TARGET
        ):
            ammo = next(
                (
                    it
                    for it in store.items
                    if it.tval == launcher.ammo_tval and it.price <= gold
                ),
                None,
            )
            if ammo is not None:
                return ammo
        if not self._identify_staff_ready(snapshot):
            identify = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_STAFF
                    and it.sval == SV_STAFF_IDENTIFY
                    and it.price <= gold
                ),
                None,
            )
            if identify is not None:
                return identify
        if (
            self._has_normal_remove_curse_target(snapshot)
            and self._find_remove_curse_scroll(snapshot) is None
        ):
            remove_curse = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_SCROLL
                    and it.sval in {SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE}
                    and it.price <= gold
                ),
                None,
            )
            if remove_curse is not None:
                return remove_curse
        star_remove_curse = self._affordable_star_remove_curse(snapshot)
        if star_remove_curse is not None:
            return star_remove_curse
        launcher_enchant = self._launcher_enchant_purchase(snapshot)
        if launcher_enchant is not None:
            return launcher_enchant
        return None

    def _purchase_quantity(self, snapshot: Snapshot, item: StoreItem) -> int:
        """Buy this ware's complete shortage in one transaction."""
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        strategy = (
            self._carry_procurement_strategy(snapshot)
            or self._quest_strategy_for_errand_or_floor(snapshot)
        )
        quest_needed = 0
        if strategy is not None:
            target = self._quest_carry_target_for_item(
                snapshot, item, strategy.required_force
            )
            if target is not None:
                _, current, required = target
                quest_needed = required - current
        if item.is_recall_scroll:
            needed = ledger["recall"].required_departure - ledger["recall"].count
        elif item.tval == TVAL_FOOD:
            needed = ledger["food"].required_departure - ledger["food"].count
        elif (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and item.tval in {TVAL_WAND, TVAL_STAFF}
        ):
            charge_needed = max(0, ledger["food"].required_departure - ledger["food"].count)
            device_needed = max(
                0, MANA_FOOD_DEVICE_TARGET - self._count_mana_food_devices(snapshot)
            )
            per_device = max(1, item.pval)
            needed = max(
                device_needed, (charge_needed + per_device - 1) // per_device
            )
        elif item.is_oil:
            needed = ledger["oil"].required_departure - ledger["oil"].count
        elif item.is_teleport_scroll:
            needed = ledger["teleport"].required_departure - ledger["teleport"].count
        elif item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
            needed = ledger["cure"].required_departure - ledger["cure"].count
        elif item.is_treasure_detection_scroll:
            target = (
                self._mining_detection_scroll_target(snapshot)
                + DETECTION_SCROLL_BUFFER
            )
            needed = target - self._count_treasure_detection_scrolls(snapshot)
        elif item.is_ammo:
            needed = AMMO_CARRY_TARGET - self._count_matching_ammo(snapshot)
        elif item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH:
            target = TORCH_THROW_TARGET
            if strategy is not None:
                target = max(target, int(
                    strategy.required_force.get("throwing_items", {}).get("lit_torch", 0)
                ))
            needed = target - self._count_throwing_torches(snapshot)
        elif item.tval == TVAL_SCROLL and item.sval in {
            SV_SCROLL_IDENTIFY,
            SV_SCROLL_STAR_IDENTIFY,
        }:
            # Cover every outstanding item of this tier in one purchase (capped,
            # so one unusually large Home batch cannot empty the wallet).
            full = item.sval == SV_SCROLL_STAR_IDENTIFY
            needed = min(
                IDENTIFY_PURCHASE_MAX,
                self._outstanding_identification_count(snapshot, full=full),
            )
        elif item.tval == TVAL_POTION and item.sval in {
            SV_POTION_SPEED,
            SV_POTION_HEALING,
        }:
            # Re-evaluate after every bottle so the two capped field stocks stay
            # balanced and the other type can use the remaining gold.
            needed = 1
        else:
            needed = 1
        needed = max(needed, quest_needed)
        affordable = snapshot.player.gold // item.price if item.price > 0 else item.count
        return max(1, min(item.count, affordable, max(1, needed)))




    @staticmethod
    def _store_accepts_sale(store_type: int, item: InventoryItem) -> bool:
        """Conservative tval gate mirroring Hengband's store_will_buy switch."""
        if store_type in {STORE_HOME, STORE_BLACK}:
            return True
        if (
            store_type == STORE_WEAPON
            and item.tval == TVAL_HAFTED
            and item.sval == SV_HAFTED_WIZSTAFF
        ):
            return False
        return item.tval in STORE_ACCEPTED_TVALS.get(store_type, frozenset())

    def _find_town_organization_surplus(
        self, snapshot: Snapshot
    ) -> InventoryItem | None:
        """Return surplus recognized by the existing sale/deposit authorities."""
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and not self._equipment_catalog.home_scan_complete
        ):
            # Complete the already-owned Home catalog/transaction pass before
            # organization changes pack letters or consumes its reserved slots.
            return None
        finder_candidates = (
            self._find_book_sale(snapshot),
            self._find_low_level_sale(snapshot),
            self._find_device_sale(snapshot),
            self._find_weapon_sale(snapshot),
            self._find_light_sale(snapshot),
        )
        candidates = [candidate for candidate in finder_candidates if candidate is not None]
        candidates.extend(
            item
            for item in snapshot.inventory
            if (
                self._home_deposit_candidate(item, snapshot)
                and not item.is_ammo
                and not item.is_torch
                # Ordinary convenience deposits keep their established
                # fundraising suppression. Organization owns this Home-only
                # case once every sale outlet has actually refused the item.
                and (
                    self._item_signature(item) in self._unsellable_items
                    or self._town_organization_sale_store(snapshot, item) is not None
                )
            )
            or self._is_surplus_digging_tool(snapshot, item)
        )
        return self._first_item(
            replace(snapshot, inventory=list(dict.fromkeys(candidates))),
            lambda item: not item.is_recall_scroll
            and self._entire_stack_is_surplus(snapshot, item)
            and not item.is_bounty
            and self._item_signature(item) not in self._home_rejected_deposits
            and (
                self._town_organization_sale_store(snapshot, item) is not None
                or self._town_organization_home_routable(snapshot, item)
            ),
        )

    def _town_organization_home_routable(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> bool:
        """Whether the existing Home deposit route can still take this surplus."""
        at_home = snapshot.store is not None and snapshot.store.store_type == STORE_HOME
        return (
            self._home_available(snapshot)
            and not self._home_deposit_abandoned
            and self._item_signature(item) not in self._home_rejected_deposits
            and (
                at_home
                or (
                    STORE_HOME not in self._town_store_attempted
                    and STORE_HOME not in self._town_visit_ledger.blocked_stores
                )
            )
        )

    def _town_organization_sale_store(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> int | None:
        if (
            self._item_signature(item) in self._unsellable_items
            or self._sale_retains_digging_tool(snapshot, item)
        ):
            return None
        for store_type in (
            STORE_WEAPON,
            STORE_ARMOURY,
            STORE_MAGIC,
            STORE_GENERAL,
            STORE_TEMPLE,
        ):
            if (
                self._store_accepts_sale(store_type, item)
                and self._town_need_supplier_reachable(
                    snapshot, TownNeed(store_type, "organization-sale", "")
                )
                and store_type not in self._store_sale_refused
                and store_type not in self._town_store_attempted
            ):
                return store_type
        return None

    def _store_sell_key(
        self,
        snapshot: Snapshot,
        item: InventoryItem,
        reason: str,
        *,
        rejected_reason: str = "shop:unsellable-leave",
    ) -> str:
        store = snapshot.store
        current = next(
            (
                candidate for candidate in snapshot.inventory
                if candidate.slot == item.slot
                and self._item_signature(candidate) == self._item_signature(item)
            ),
            None,
        )
        if current is None:
            # A sale candidate can outlive the inventory board that supplied
            # its letter after an earlier sale removes or reorders the pack.
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY
        item = current
        if self._sale_retains_digging_tool(snapshot, item):
            self._batch_sell_pending = None
            self.last_reason = "shop:retain-standing-digging-tool"
            return LEAVE_STORE_KEY
        if store is None or not self._store_accepts_sale(store.store_type, item):
            # 'd' can be rejected before opening an item prompt.  Never attach
            # Return/yes tail keys unless the C++ store tval gate says the prompt
            # exists; otherwise those keys execute raw in the store command loop.
            self._unsellable_items.add(self._item_signature(item))
            if store is not None:
                self._set_town_store_attempted(store.store_type, snapshot.turn, "sell-no-item")
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY
        if (
            self._item_signature(item) in self._unsellable_items
            or store.store_type in self._store_sale_refused
        ):
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY

        item_signature = self._item_signature(item)
        attempts = 1
        if self._store_sell_attempt is not None:
            previous_signature, previous_count, previous_attempts = (
                self._store_sell_attempt
            )
            if previous_signature == item_signature and item.count >= previous_count:
                attempts = previous_attempts + 1
        self._store_sell_attempt = (item_signature, item.count, attempts)

        pack_state = tuple(
            (it.slot, self._item_signature(it), it.count, it.charges)
            for it in snapshot.inventory
        )
        store_state = tuple(
            (it.letter, it.name, it.tval, it.sval, it.count, it.price)
            for it in store.items
        )
        sig = (
            snapshot.turn,
            store.store_type,
            pack_state,
            store_state,
            snapshot.player.gold,
        )
        if sig == self._last_sell_sig:
            self._store_sell_stuck_count += 1
        else:
            self._last_sell_sig = sig
            self._store_sell_stuck_count = 0
        # One already-emitted attempt followed by a byte-distinct snapshot whose
        # store/pack/gold state is unchanged proves the sale was rejected. Leave
        # now instead of
        # re-emitting the multi-key sell — a second emit lands its trailing keys
        # in the store command loop after the "no room" message ("そのコマンドは
        # 店の中では使えません"), the desync the user observed.
        if self._store_sell_stuck_count >= 1:
            self._unsellable_items.add(self._item_signature(item))
            self._set_town_store_attempted(store.store_type, snapshot.turn, "sell-stuck")
            # The store accepts this item's type (it passed _store_accepts_sale)
            # yet rejected the sale: it is FULL. Latch it so the withdraw/route
            # logic stops feeding more spares to a store with no room.
            self._store_sale_refused.add(store.store_type)
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY
        # Three cross-snapshot attempts are enough to prove that the prompt
        # chain is not completing; continuing risks leaking tail keys.
        if attempts >= SELL_ATTEMPT_LIMIT:
            self._unsellable_items.add(item_signature)
            self._set_town_store_attempted(store.store_type, snapshot.turn, "sell-attempt-limit")
            self._store_sale_refused.add(store.store_type)
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            self._store_sell_attempt = None
            self.last_reason = rejected_reason
            return LEAVE_STORE_KEY
        # Even specialized disposal paths use the same inscription-observed
        # transaction; this helper never composes an item-letter sale key.
        key = self._batch_sell_key(snapshot, [item])
        if key is None:
            self.last_reason = "shop:sale-requires-inscription-leave"
            return LEAVE_STORE_KEY
        return key

    def _current_store_sale_candidates(self, snapshot: Snapshot) -> list[InventoryItem]:
        """Enumerate sale finders in normal shop priority, without mutating policy."""
        store = snapshot.store
        if store is None:
            return []
        remaining = list(snapshot.inventory)
        result: list[InventoryItem] = []
        while remaining:
            view = replace(snapshot, inventory=remaining)
            sale = self._find_book_sale(view, store.store_type)
            if sale is None and store.store_type == STORE_ALCHEMIST:
                sale = self._find_low_level_sale(view)
            if sale is None and store.store_type == STORE_MAGIC:
                sale = self._find_device_sale(view)
            if sale is None and store.store_type == STORE_WEAPON:
                sale = self._find_weapon_sale(view)
            if sale is None and store.store_type == STORE_GENERAL:
                if snapshot.player.food_type == FOOD_TYPE_MANA:
                    sale = self._first_item(
                        view,
                        lambda item: item.tval == TVAL_FOOD
                        and self._retention_surplus(snapshot, item) > 0
                        and self._item_signature(item) not in self._unsellable_items,
                    )
                if sale is None:
                    sale = self._find_light_sale(view)
            if sale is None:
                break
            if not self._equipment_transaction_owns_item(sale):
                result.append(sale)
            remaining = [item for item in remaining if item.slot != sale.slot]
        if not result:
            organization = self._find_town_organization_surplus(snapshot)
            if (
                organization is not None
                and self._next_purchase(snapshot) is None
                and self._store_accepts_sale(store.store_type, organization)
                and store.store_type
                == self._town_organization_sale_store(snapshot, organization)
            ):
                if not self._equipment_transaction_owns_item(organization):
                    result.append(organization)
        return result

    def _batch_sell_key(
        self,
        snapshot: Snapshot,
        candidates: list[InventoryItem] | None = None,
    ) -> str | None:
        """Advance the mandatory inscription-bound sale transaction."""
        store = snapshot.store
        if store is None:
            return None

        pending = self._batch_sell_pending
        if pending is not None and pending["store_type"] == store.store_type:
            entries = pending["entries"]
            if pending["phase"] == "await-inscription":
                def observed_tagged(entry):
                    return next((
                        current for current in snapshot.inventory
                        if self._sale_item_identity(current) == entry["signature"]
                        and self._item_has_sale_tag(current, str(entry["tag"]))
                    ), None)
                observed = all(
                    observed_tagged(entry) is not None
                    for entry in entries
                )
                if not observed:
                    for entry in entries:
                        self._unsellable_items.add(entry["signature"])
                    self._store_sale_refused.add(store.store_type)
                    self._batch_sell_pending = None
                    self.last_reason = "shop:sale-inscription-unobserved-leave"
                    return LEAVE_STORE_KEY
                if any(
                    self._sale_retains_digging_tool(snapshot, observed_tagged(entry))
                    for entry in entries
                ):
                    self._batch_sell_pending = None
                    self.last_reason = "shop:retain-standing-digging-tool"
                    return LEAVE_STORE_KEY
                # Inscribing can merge identical pack items.  Compose each
                # prompt chain from the item in this observed snapshot, not
                # from the pre-inscription candidate cached in the plan.
                for entry in entries:
                    item = observed_tagged(entry)
                    if item is None:
                        continue
                    if not self._sale_tag_is_unique(
                        snapshot, item, str(entry["tag"])
                    ):
                        self._unsellable_items.add(entry["signature"])
                        self._store_sale_refused.add(store.store_type)
                        self._batch_sell_pending = None
                        self.last_reason = "shop:sale-inscription-ambiguous-leave"
                        return LEAVE_STORE_KEY
                    sale = self._batch_sale_entry(snapshot, item, entry["tag"])
                    if sale is None:
                        self._batch_sell_pending = None
                        return ""
                    entry.update(sale)
                pending["phase"] = "await-sale"
                self.last_reason = "shop:one-shot-sale-compose"
                return "".join(entry["sell"] for entry in entries)

            # Exactly one post-sale snapshot verifies every tagged item.  Any
            # survivor advances the ordinary attempt record and is then handled
            # by a fresh inscription-bound transaction if policy still wants it.
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
                if survivor is not None and survivor.count > expected:
                    attempts = 1
                    if self._store_sell_attempt is not None:
                        sig, previous_count, previous_attempts = self._store_sell_attempt
                        if sig == entry["signature"] and survivor.count >= previous_count:
                            attempts = previous_attempts + 1
                    self._store_sell_attempt = (entry["signature"], survivor.count, attempts)
            self._batch_sell_pending = None
            self._last_sell_sig = None
            self._store_sell_stuck_count = 0
            if confirmed and self._store_visit is not None:
                self._store_visit.operation_posted = False
                self._store_visit.operation_effect_observed = True
            if confirmed:
                self._town_visit_sale_signatures.update(
                    (int(entry["signature"][1]), int(entry["signature"][2]))
                    for entry in entries
                )
            elif not confirmed:
                self._close_store_visit("one-shot-sale-unconfirmed")
            # A completed batch can compact every following inventory slot.
            # Leave before starting another transaction from a snapshot that
            # may still reflect the pre-sale inventory layout.
            self.last_reason = "shop:one-shot-sale-observed"
            return LEAVE_STORE_KEY

        candidates = (
            self._current_store_sale_candidates(snapshot)
            if candidates is None
            else candidates
        )
        if not candidates:
            return None

        entries: list[dict[str, object]] = []
        inscribe_parts: list[str] = []
        for item in candidates[:1]:
            if self._sale_retains_digging_tool(snapshot, item):
                self.last_reason = "shop:retain-standing-digging-tool"
                return LEAVE_STORE_KEY
            digit = self._unique_sale_tag(snapshot, item)
            if digit is None:
                self._unsellable_items.add(self._item_signature(item))
                self._store_sale_refused.add(store.store_type)
                self._batch_sell_pending = None
                self.last_reason = "shop:sale-inscription-ambiguous-leave"
                return LEAVE_STORE_KEY
            exact_tag = f"@{digit}"
            has_exact_tag = self._item_has_sale_tag(item, digit)
            # Other @ inscriptions may be command bindings owned outside sale
            # policy.  Never overwrite them merely to make a batch possible.
            has_numeric_tag = any(
                self._item_has_sale_tag(item, value)
                for value in "0123456789"
            )
            if "@" in item.inscription and not has_exact_tag and not has_numeric_tag:
                continue
            if not has_exact_tag:
                inscribe_parts.append("{" + item.slot + exact_tag + "\r")
            sale = self._batch_sale_entry(snapshot, item, digit)
            if sale is None:
                self._batch_sell_pending = None
                return ""
            entries.append({
                "signature": self._sale_item_identity(item),
                "tag": digit,
                **sale,
            })
        if not entries:
            self.last_reason = "shop:sale-inscription-unavailable-leave"
            return LEAVE_STORE_KEY
        phase = "await-inscription" if inscribe_parts else "await-sale"
        self._batch_sell_pending = {
            "store_type": store.store_type,
            "phase": phase,
            "entries": entries,
            "before_gold": snapshot.player.gold,
            "wait_count": 0,
        }
        self.last_reason = (
            "shop:batch-inscribe"
            if inscribe_parts
            else "shop:one-shot-sale-compose"
        )
        return "".join(inscribe_parts) if inscribe_parts else "".join(
            entry["sell"] for entry in entries
        )

    def _sale_tag_is_unique(
        self, snapshot: Snapshot, intended: InventoryItem, tag: str
    ) -> bool:
        """Match Hengband's numeric-tag resolver over store-eligible pack items."""
        matches = [
            item for item in snapshot.inventory
            if self._store_accepts_sale(snapshot.store.store_type, item)
            and self._item_has_sale_tag(item, tag)
        ]
        return (
            len(matches) == 1
            and self._sale_item_identity(matches[0]) == self._sale_item_identity(intended)
        )


    @staticmethod
    def _sale_inscription_text(item: InventoryItem) -> str:
        """Return the inscription even when the emitter only decorates ``name``."""
        return item.inscription or item.name

    @classmethod
    def _item_has_sale_tag(cls, item: InventoryItem, tag: str) -> bool:
        return re.search(
            rf"@{re.escape(tag)}(?!\d)", cls._sale_inscription_text(item)
        ) is not None

    @staticmethod
    def _sale_item_identity(item: InventoryItem) -> tuple[str, int, int]:
        # Live snapshots currently expose inscription=None while appending the
        # inscription to the display name.  Inscribing must not change the
        # identity owned by the pending two-stage sale.
        name = re.sub(r"\s+\{[^{}]*\}\s*$", "", item.name)
        return (name, item.tval, item.sval)

    def _batch_sale_entry(
        self, snapshot: Snapshot, item: InventoryItem, tag: str
    ) -> dict[str, object] | None:
        """Classify one tagged sale from the snapshot being composed."""
        signature = self._sale_item_identity(item)
        item = next((
            current for current in snapshot.inventory
            if self._sale_item_identity(current) == signature
            and (
                current.inscription == item.inscription
                or (
                    not current.inscription
                    and self._item_has_sale_tag(current, tag)
                )
            )
        ), None)
        if item is None:
            self.last_reason = "shop:batch-sale-signature-unobserved"
            return None
        surplus = self._retention_surplus(snapshot, item)
        quantity = item.count if surplus <= 0 else min(item.count, surplus)
        amount = "99" if quantity == item.count else str(quantity)
        # The store always asks for the offered-price confirmation.  A stack
        # first asks for a quantity; a singleton does not.
        quantity_answer = "" if item.count == 1 else amount + "\r"
        return {
            "count": item.count,
            "quantity": quantity,
            "sell": SELL_KEY + tag + quantity_answer + "y",
        }

    def _shop(self, snapshot: Snapshot) -> str:
        store = snapshot.store
        self._observe_star_remove_curse_reserve_inflight(snapshot)
        if store is None:
            self.last_reason = "shop:invalid"
            return LEAVE_STORE_KEY
        if (
            store.store_type == STORE_TEMPLE
            and self._star_remove_curse_reserve_buy_inflight is not None
        ):
            self.last_reason = "shop:await-star-remove-curse-purchase"
            return LEAVE_STORE_KEY
        if (
            store.store_type == STORE_MAGIC
            and not self._last_snapshot_was_store
            and not self._home_identify_staff_sale_pending
        ):
            self._home_identify_staff_sold_this_magic_visit = False

        # A hungry character with no edible pack item has exactly one town job.
        # Do not sell gear or buy optional supplies while starvation advances.
        if snapshot.player.hungry and self._find_edible(snapshot) is None:
            if (
                snapshot.player.food_type == FOOD_TYPE_MANA
                and self._mana_survival_device_price is not None
                and snapshot.player.gold >= self._mana_survival_device_price
            ):
                self._town_store_attempted.pop(STORE_MAGIC, None)
            if (
                snapshot.player.food_type == FOOD_TYPE_MANA
                and self._mana_survival_device_price is not None
                and snapshot.player.gold < self._mana_survival_device_price
                and store.store_type in {STORE_ALCHEMIST, STORE_WEAPON}
            ):
                sale = self._mana_survival_sale_candidate(
                    snapshot, store.store_type
                )
                if sale is not None:
                    return self._store_sell_key(
                        snapshot, sale, "survival:mana-sell-to-afford"
                    )
            food_store = (
                STORE_MAGIC
                if snapshot.player.food_type == FOOD_TYPE_MANA
                else STORE_GENERAL
            )
            if store.store_type != food_store:
                self.last_reason = "survival:leave-wrong-store"
                return LEAVE_STORE_KEY
            if snapshot.player.food_type == FOOD_TYPE_MANA:
                self._home_procurement_fallthrough_equivalence = (
                    "device:is-wand-staff"
                )
                if not self._home_knowledge_current:
                    self._home_procurement_probe = (-1, -1)
                    if not self._current_town_has_home(snapshot):
                        self._home_procurement_probe = None
                        self._home_procurement_fallthrough = "town-without-home"
                    elif (
                        not self._home_available(snapshot)
                        or not self._ensure_home_visit_request(snapshot)
                        or self._shopping_approach_step(snapshot, STORE_HOME) is None
                    ):
                        self._home_procurement_probe = None
                        self.last_reason = "survival:mana-home-route-defect"
                        return LEAVE_STORE_KEY
                    else:
                        self.last_reason = "survival:mana-home-scan-before-purchase"
                        return LEAVE_STORE_KEY
                home_food = self._home_mana_food_candidate()
                if home_food is not None:
                    self._home_pending_item = self._item_signature(home_food)
                    self._home_pending_quantity = 1
                    self._home_procurement_probe = (-1, -1)
                    self.last_reason = "survival:mana-home-before-purchase"
                    return LEAVE_STORE_KEY
                food_item = self._mana_food_purchase(snapshot)
            elif snapshot.player.food_type == FOOD_TYPE_RATION:
                food_item = next(
                    (
                        it for it in store.items
                        if it.tval == TVAL_FOOD
                        and it.sval >= FOOD_MIN_SVAL
                        and it.price <= snapshot.player.gold
                    ),
                    None,
                )
                if food_item is not None:
                    home_gate = self._purchase_has_fresh_home_absence(
                        snapshot, food_item
                    )
                    if home_gate is ProcurementHomeGate.BLOCKED:
                        self._publish_purchase_home_block()
                        return WAIT_KEY
                    if home_gate is ProcurementHomeGate.HOME_FIRST:
                        self._rearm_town_store_for_new_work(
                            STORE_HOME, release_visit_bound=True
                        )
                        self.last_reason = "survival:ration-home-before-purchase"
                        return LEAVE_STORE_KEY
            else:
                food_item = None
            if food_item is not None:
                quantity = self._purchase_quantity(snapshot, food_item)
                suffix = (
                    f"{quantity}\r\r"
                    if food_item.count > 1
                    else BUY_CONFIRM_SUFFIX
                )
                self.last_reason = "survival:buy-food"
                return BUY_KEY + food_item.letter + suffix
            self._set_town_store_attempted(store.store_type, snapshot.turn, "survival-food-unavailable")
            if snapshot.player.food_type == FOOD_TYPE_MANA:
                prices = [
                    item.price for item in store.items
                    if item.tval in {TVAL_WAND, TVAL_STAFF}
                ]
                self._mana_survival_device_price = min(prices) if prices else None
                if self._mana_survival_device_price is not None:
                    for sale_store in (STORE_ALCHEMIST, STORE_WEAPON):
                        if self._mana_survival_sale_candidate(snapshot, sale_store):
                            self._town_store_attempted.pop(sale_store, None)
                            self.last_reason = "survival:mana-sell-to-afford"
                            return LEAVE_STORE_KEY
                self.last_reason = "town:blocked:survival-mana-no-charges"
                return WAIT_KEY
            self.last_reason = "survival:no-affordable-food"
            return LEAVE_STORE_KEY

        suppress_random_teleport = self._town_random_teleport_suppression_key(
            snapshot
        )
        if suppress_random_teleport is not None:
            return suppress_random_teleport

        if store.store_type == STORE_HOME:
            morivant_home_key = self._morivant_home_item_key(snapshot)
            if morivant_home_key is not None:
                return morivant_home_key
            reserve = next(
                (
                    item
                    for item in store.items
                    if item.tval == TVAL_SCROLL
                    and item.sval == SV_SCROLL_STAR_REMOVE_CURSE
                ),
                None,
            )
            if (
                reserve is not None
                and self._has_unremovable_curse_target(snapshot)
                and not self._recall_departure_shortage(snapshot)
            ):
                self._star_remove_curse_reserve_withdraw_pending = True
                self._home_pending_item = self._item_signature(reserve)
                self.last_reason = "home:queue-star-remove-curse-withdraw"
                return LEAVE_STORE_KEY
            # An active transaction session OWNS the Home visit: its town-side
            # dispatcher keeps walking back in while it has Home work, so a
            # disposal leave that preempts it just bounces the bot in and out of
            # Home (store snapshots reset the harness loop guard, so nothing
            # stops the bounce). Run the session first; when it completes or is
            # abandoned it returns None and the disposal leave proceeds.
            transaction_key = self._equipment_transaction_home_key(snapshot)
            if transaction_key is not None:
                return transaction_key
            quest_launcher = self._home_quest_launcher_key(snapshot)
            if quest_launcher is not None:
                return quest_launcher
            dominated_disposal = self._home_dominated_disposal_key(snapshot)
            if dominated_disposal is not None:
                return dominated_disposal
            disposal_key = self._home_disposal_home_key(snapshot)
            if disposal_key is not None:
                return disposal_key

        if (
            self._pending_disposal_item is not None
        ):
            target = self._pending_disposal(snapshot)
            if target is None:
                self._clear_pending_disposal()
                self.last_reason = "equipment:sale-complete"
                return LEAVE_STORE_KEY
            if store.store_type != self._dominated_disposal_store(target):
                return None
            key = self._store_sell_key(
                snapshot, target, "equipment:sell-dominated",
                rejected_reason="equipment:sale-refused",
            )
            if key == LEAVE_STORE_KEY:
                self._disposal_store_attempts.add(store.store_type)
            return key

        if self._home_disposal_pending is not None:
            signature, decision = self._home_disposal_pending
            target = self._home_disposal_inventory_item(snapshot)
            if (
                decision == "sell"
                and target is not None
                and target.known
                and store.store_type == self._home_disposal_store(signature)
            ):
                self._home_disposal_pending = None
                return self._store_sell_key(
                    snapshot, target, "home-disposal:sell-approved",
                    rejected_reason="home-disposal:sale-refused",
                )

        if store.store_type == STORE_HOME:
            rearm = self._home_rearm_key(snapshot)
            if rearm is not None:
                return rearm

            if self._home_atomic_withdraw_pending is not None:
                self.last_reason = "home:leave-after-one-operation"
                return LEAVE_STORE_KEY

            # Prefer owned Identify charges to buying another staff.  Once the
            # carried departure reserve is ready, drain legacy Home hoards one
            # staff at a time through the Magic shop.  Charged devices are not
            # Home-deposit candidates, so the withdrawn staff cannot bounce back.
            stored_identify = [
                item
                for item in store.items
                if item.tval == TVAL_STAFF
                and item.sval == SV_STAFF_IDENTIFY
                and item.charges > 0
            ]
            queued_withdrawals = set(self._home_pending_batch)
            queued_withdrawals.update(self._calibration_restore_signatures)
            if self._home_pending_item is not None:
                queued_withdrawals.add(self._home_pending_item)
            stored_identify = [
                item for item in stored_identify
                if self._item_signature(item) not in queued_withdrawals
            ]
            if (
                stored_identify
                and PACK_CAPACITY - len(snapshot.inventory)
                > max(HOME_BATCH_RESERVED_SLOTS, MIN_FREE_PACK_SLOTS)
            ):
                if not self._identify_staff_ready(snapshot):
                    candidate = max(
                        stored_identify,
                        key=lambda item: (
                            item.charges * max(1, item.count),
                            item.charges,
                            item.letter,
                        ),
                    )
                    reason = "home:withdraw-identify-staff-reserve"
                else:
                    candidate = min(
                        stored_identify,
                        key=lambda item: (
                            item.charges,
                            item.charges * max(1, item.count),
                            item.letter,
                        ),
                    )
                    self._home_identify_staff_sale_pending = True
                    self._rearm_town_store_for_new_work(STORE_MAGIC)
                    reason = "home:withdraw-surplus-identify-staff"
                signature = self._item_signature(candidate)
                self._home_pending_item = signature
                self._home_withdrawal_queued = True
                self.last_reason = reason.replace("withdraw", "queue-withdraw")
                return LEAVE_STORE_KEY

            additional_home_digger = next(
                (
                    item
                    for item in store.items
                    if item.is_digging_tool
                    and self._item_signature(item)
                    not in self._deferred_home_items
                ),
                None,
            )
            if (
                self._home_digger_withdraw_pending
                and self._has_digging_tool(snapshot)
                and (
                    self._digging_tool_count(snapshot) >= 2
                    or additional_home_digger is None
                )
            ):
                self._home_digger_withdraw_pending = False
                self.last_reason = "home:leave-with-digging-tool"
                return LEAVE_STORE_KEY

            # Resolve an equipment withdrawal before the fundraising fast-exit.
            # A failed quest-launcher command can leave _home_pending_item set
            # after its inflight retry is exhausted.  If mining supplies are
            # already complete, letting that branch leave first makes the town
            # planner request Home again forever without ever reaching this
            # cleanup.  Successful withdrawals also need to advance the Home
            # stop before the normal deposit pass can put the item back.
            if self._home_pending_item is not None:
                if self._pending_inventory_item(snapshot) is not None:
                    self._report_town_stop_pass(
                        snapshot, STORE_HOME, goal_satisfied=True
                    )
                    self.last_reason = "home:leave-with-item"
                    return LEAVE_STORE_KEY
                self._defer_home_item(
                    self._home_pending_item, "home-open-page-item-unavailable"
                )
                self._release_identification_source_reservation(
                    self._home_pending_item
                )
                self._home_pending_item = None
                self._home_pending_slot = None
                self._identification_need = None
                self._identification_candidate = None
                self._home_candidate_waiting = True
                self.last_reason = "home:withdraw-failed-deferred"
                return LEAVE_STORE_KEY

            standing_digger = self._queue_standing_home_digger(snapshot)
            if standing_digger is not None:
                return standing_digger

            # A partly identified ego/artifact/random-resistance item must not
            # ride into a deep mining floor where theft or inventory damage can
            # erase it before its hidden traits are known. Deposit it before the
            # mining-supply branch is allowed to leave Home.
            if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
                # Deep fundraising deliberately routes Home after a pack-full
                # return so loot and equipment candidates can be secured before
                # the next run.  The mining-kit fast-exit below used to preempt
                # the ordinary deposit owner even though the errand plan still
                # had a live Home deposit need, producing an endless
                # enter/leave/re-enter cycle.  Retention rules inside
                # _find_home_deposit preserve the digger and consumable kit.
                deposit = self._find_home_deposit(snapshot)
                if deposit is not None and self._home_entry_operation_posted:
                    return self._home_deposit_key(snapshot, deposit)
                required_scrolls = self._mining_detection_scroll_target(snapshot)
                scrolls_needed = required_scrolls + DETECTION_SCROLL_BUFFER
                scrolls_missing = max(
                    0,
                    scrolls_needed
                    - self._count_treasure_detection_scrolls(snapshot),
                )
                required_scrolls_missing = (
                    self._count_treasure_detection_scrolls(snapshot)
                    < required_scrolls
                )
                stored_scrolls = next(
                    (
                        item
                        for item in store.items
                        if item.is_treasure_detection_scroll
                    ),
                    None,
                )
                if scrolls_missing and stored_scrolls is not None:
                    self._home_digger_seen_pages.clear()
                    signature = self._item_signature(stored_scrolls)
                    quantity = min(scrolls_missing, stored_scrolls.count)
                    self._home_pending_item = signature
                    self._home_pending_quantity = quantity
                    self.last_reason = "home:queue-treasure-detection-withdraw"
                    return LEAVE_STORE_KEY

                withdrawable_digger_missing = (
                    self._digging_tool_count(snapshot) < 2
                    and any(
                        owned.origin == "home" and owned.item.is_digging_tool
                        for owned in self._equipment_catalog.items
                    )
                )
                if (
                    required_scrolls_missing
                    or not self._has_digging_tool(snapshot)
                    or withdrawable_digger_missing
                ):
                    page = tuple(
                        (item.letter, item.name, item.tval, item.sval)
                        for item in store.items
                    )
                    if page not in self._home_digger_seen_pages:
                        self._home_digger_seen_pages.add(page)
                        self.last_reason = (
                            "home:seek-treasure-detection-page"
                            if required_scrolls_missing
                            else "home:seek-digging-tool-page"
                        )
                        return " "
                    self._home_digger_seen_pages.clear()
                    self._home_digger_withdraw_pending = False
                    self._set_town_store_attempted(STORE_HOME, snapshot.turn, "digger-withdraw-complete")
                    self.last_reason = (
                        "home:no-treasure-detection"
                        if required_scrolls_missing
                        else "home:no-digging-tool"
                    )
                    return LEAVE_STORE_KEY

                self._home_digger_seen_pages.clear()
                catalog_work_pending = (
                    snapshot.player.class_id == PLAYER_CLASS_WARRIOR
                    and (
                        not self._equipment_catalog.home_scan_complete
                        or self._has_actionable_incomplete_home_item(snapshot)
                    )
                    and bool(self._equipment_catalog.items)
                )
                disposal_work_pending = self._home_disposal_pass
                if catalog_work_pending or disposal_work_pending:
                    # The town router entered Home to finish the equipment
                    # catalog or idle-consumable disposal pass. Mining supplies
                    # being complete does not satisfy either separate owner:
                    # fall through to the normal Home page processor instead of
                    # escaping and immediately routing back through the door
                    # forever.
                    pass
                else:
                    # This Home stop is complete for the current town visit.
                    # Without the latch, the errand plan keeps its pinned Home
                    # stop and walks straight back through the door after Escape.
                    self._report_town_stop_pass(
                        snapshot, STORE_HOME, goal_satisfied=True
                    )
                    self._set_town_store_attempted(STORE_HOME, snapshot.turn, "home-stop-complete")
                    self.last_reason = "home:leave-with-mining-supplies"
                    return LEAVE_STORE_KEY

            # High-level spellbooks are sale loot, not Home reserves. Older
            # runs could deposit them before the sale rule existed, so recover
            # them during the normal Home page scan and hand them to the
            # realm-appropriate shop routing. Leave immediately after a
            # withdrawal so the deposit pass cannot put the book straight back.
            if self._find_book_sale(snapshot) is not None:
                self.last_reason = "home:leave-with-book-sale"
                return LEAVE_STORE_KEY
            stored_book = next(
                (item for item in store.items if self._is_high_value_book(item)),
                None,
            )
            if stored_book is not None:
                self._home_pending_item = self._item_signature(stored_book)
                self.last_reason = "home:queue-book-sale-withdraw"
                return LEAVE_STORE_KEY

            deposit = self._find_home_deposit(snapshot)
            if deposit is not None and self._home_entry_operation_posted:
                return self._home_deposit_key(snapshot, deposit)

            if (
                self._equipped_weapon_high_grade(snapshot)
                # Stop pulling spares once the Weapon Smith is full this visit:
                # they could not be sold, and re-opening its sale route (below)
                # would only churn futile trips to a store with no room. This
                # also suppresses the route re-open, since the pop lives here.
                and STORE_WEAPON not in self._store_sale_refused
                # Never pull spares past the batch reserve: an unguarded pull
                # filled the pack to zero free every Home visit, and a full pack
                # blocks town departure (MIN_FREE_PACK_SLOTS).
                and PACK_CAPACITY - len(snapshot.inventory) > HOME_BATCH_RESERVED_SLOTS
            ):
                inferior = next(
                    (
                        it
                        for it in store.items
                        if self._weapon_is_inferior(it)
                        and self._can_add_item_without_overweight(snapshot, it)
                        # Do not withdraw a spare the Weapon Smith already refused
                        # (it would clog the pack with something no sale can clear).
                        and (it.name, it.tval, it.sval) not in self._unsellable_items
                    ),
                    None,
                )
                if inferior is not None:
                    # Pull a stored good/average spare weapon back out (no pending
                    # processing) so it can be sold at the Weapon Smith; the
                    # deposit filter keeps it from being re-stored on the way.
                    # Re-open the Weapon Smith sale route for this freshly withdrawn
                    # spare. Without it, a second Home visit that pulls a new batch
                    # after the smith was already visited leaves the pack clogged
                    # with unsold weapons (STORE_WEAPON stays latched until
                    # STORE_RETRY_TURNS) and town departure stalls until self-stop.
                    self._town_store_attempted.pop(STORE_WEAPON, None)
                    self._home_pending_item = self._item_signature(inferior)
                    self.last_reason = "home:queue-inferior-weapon-withdraw"
                    return LEAVE_STORE_KEY

            candidate = self._find_home_candidate(snapshot)
            if candidate is not None:
                needs_normal = (
                    not candidate.known
                    and candidate.pseudo_feeling != "average"
                )
                needs_full = (
                    candidate.known
                    and self._identification_flow_candidate(candidate)
                )
                if needs_normal and self._find_identification_source(
                    snapshot,
                    full=False,
                    reliable_only=True,
                    reservation_target=self._item_signature(candidate),
                ) is None:
                    signature = self._item_signature(candidate)
                    self._request_identification("normal")
                    self._identification_candidate = signature
                    self._reserve_next_identification_source(
                        snapshot, signature, full=False
                    )
                    self._home_candidate_waiting = True
                    self.last_reason = "home:need-identify"
                    return LEAVE_STORE_KEY
                if needs_full and self._find_identification_source(
                    snapshot,
                    full=True,
                    reservation_target=self._item_signature(candidate),
                ) is None:
                    signature = self._item_signature(candidate)
                    self._unbuyable_full_identify_sigs.add(signature)
                    self._request_identification("full")
                    self._identification_candidate = signature
                    self._reserve_next_identification_source(
                        snapshot, signature, full=True
                    )
                    self._home_candidate_waiting = True
                    self.last_reason = "home:need-full-identify"
                    return LEAVE_STORE_KEY

                free_slots = PACK_CAPACITY - len(snapshot.inventory)
                if free_slots <= HOME_BATCH_RESERVED_SLOTS:
                    # This candidate cannot be withdrawn until carried gear is
                    # identified/sold/deposited.  Keeping candidate_waiting set
                    # makes Home outrank those space-making errands and creates
                    # an enter/leave loop on the same full pack. Defer only this
                    # signature for the town visit and release its identify
                    # request so carried candidates can be processed first.
                    signature = self._item_signature(candidate)
                    self._defer_home_item(signature, "home-equipment-processing-deferred")
                    self._release_identification_source_reservation(signature)
                    if self._identification_candidate == signature:
                        self._identification_candidate = None
                    self._identification_need = None
                    self._home_candidate_waiting = False
                    self.last_reason = "home:defer-capacity"
                    return LEAVE_STORE_KEY

                signature = self._item_signature(candidate)
                self._home_pending_batch.append(signature)
                self._home_candidate_waiting = False
                self.last_reason = "home:queue-batch-withdraw"
                return LEAVE_STORE_KEY

            if (
                self._home_pending_batch
                and PACK_CAPACITY - len(snapshot.inventory)
                <= HOME_BATCH_RESERVED_SLOTS
            ):
                self._home_candidate_waiting = False
                self.last_reason = "home:leave-with-batch"
                return LEAVE_STORE_KEY

            page = tuple(
                (item.letter, item.name, item.tval, item.sval)
                for item in store.items
            )

            self._home_processing_seen_pages.clear()
            self._home_candidate_waiting = False
            self._report_town_stop_pass(
                snapshot,
                STORE_HOME,
                goal_satisfied=self._equipment_catalog.home_scan_complete,
            )
            self.last_reason = (
                "home:leave-with-batch"
                if self._home_pending_batch
                else "home:processing-complete"
            )
            return LEAVE_STORE_KEY

        batch_key = self._batch_sell_key(snapshot)
        if batch_key is not None:
            return batch_key

        organization = self._find_town_organization_surplus(snapshot)
        ordinary_sale = self._find_book_sale(snapshot, store.store_type)
        if ordinary_sale is None and store.store_type == STORE_ALCHEMIST:
            ordinary_sale = self._find_low_level_sale(snapshot)
        if ordinary_sale is None and store.store_type == STORE_MAGIC:
            ordinary_sale = self._find_device_sale(snapshot)
        if ordinary_sale is None and store.store_type == STORE_WEAPON:
            ordinary_sale = self._find_weapon_sale(snapshot)
        if ordinary_sale is None and store.store_type == STORE_GENERAL:
            ordinary_sale = self._find_light_sale(snapshot)
        if (
            organization is not None
            and ordinary_sale is None
            and self._next_purchase(snapshot) is None
            and self._store_accepts_sale(store.store_type, organization)
            and store.store_type
            == self._town_organization_sale_store(snapshot, organization)
        ):
            return self._store_sell_key(
                snapshot, organization, "shop:sell-town-surplus"
            )

        book_sale = self._find_book_sale(snapshot, store.store_type)
        if book_sale is not None:
            return self._store_sell_key(
                snapshot, book_sale, "shop:sell-high-value-book",
                rejected_reason="shop:unsellable-book-leave",
            )

        if store.store_type == STORE_ALCHEMIST:
            sale = self._find_low_level_sale(snapshot)
            if sale is not None:
                return self._store_sell_key(
                    snapshot, sale, "shop:sell-low-value-consumable"
                )

        if store.store_type == STORE_MAGIC:
            sale = self._find_device_sale(snapshot)
            if sale is not None:
                if (
                    self._home_identify_staff_sale_pending
                    and sale.tval == TVAL_STAFF
                    and sale.sval == SV_STAFF_IDENTIFY
                ):
                    self._home_identify_staff_sale_pending = False
                    self._home_identify_staff_sold_this_magic_visit = True
                    self._rearm_town_store_for_new_work(STORE_HOME)
                return self._store_sell_key(
                    snapshot, sale, "shop:sell-device",
                    rejected_reason="shop:unsellable-device-leave",
                )

        if store.store_type == STORE_WEAPON:
            sale = self._find_weapon_sale(snapshot)
            if sale is not None:
                reason = (
                    "shop:sell-no-teleport-weapon"
                    if self._blocks_teleport(sale)
                    else "shop:sell-inferior-weapon"
                )
                return self._store_sell_key(
                    snapshot, sale, reason,
                    rejected_reason="shop:unsellable-weapon-leave",
                )

        if store.store_type == STORE_GENERAL:
            if snapshot.player.food_type == FOOD_TYPE_MANA:
                sale = self._first_item(
                    snapshot,
                    lambda item: item.tval == TVAL_FOOD
                    and self._retention_surplus(snapshot, item) > 0
                    and self._item_signature(item) not in self._unsellable_items,
                )
                if sale is not None:
                    return self._store_sell_key(
                        snapshot, sale, "shop:sell-mana-race-food"
                    )
            sale = self._find_light_sale(snapshot)
            if sale is not None:
                reason = (
                    "shop:sell-surplus-torches"
                    if sale.is_torch
                    else "shop:sell-spare-lantern"
                )
                return self._store_sell_key(
                    snapshot, sale, reason,
                    rejected_reason="shop:unsellable-light-leave",
                )

        item = self._next_purchase(snapshot)
        if item is not None:
            if (item.tval, item.sval) in self._town_visit_sale_signatures:
                self.town_visit_report = (
                    f"town-visit:sell-rebuy-churn:{item.tval}:{item.sval}"
                )
                self.last_reason = "shop:sell-rebuy-churn-defect"
                return LEAVE_STORE_KEY
            home_gate = self._purchase_has_fresh_home_absence(snapshot, item)
            if home_gate is not ProcurementHomeGate.ALLOW_PURCHASE:
                if home_gate is ProcurementHomeGate.BLOCKED:
                    self._publish_purchase_home_block()
                    return WAIT_KEY
                self._rearm_town_store_for_new_work(
                    STORE_HOME, release_visit_bound=True
                )
                self.last_reason = "shop:home-first-before-purchase"
                return LEAVE_STORE_KEY
            signature = self._item_signature(item)
            # Bail out of a purchase that never takes effect. A registered buy
            # drops our gold (so the signature changes and the counter resets);
            # if we keep asking to buy the same item at the same gold, the macro
            # is not landing (e.g. an out-of-page letter, or a flushed prompt key)
            # and there is no loop-detector inside a store to save us.
            sig = (item.letter, snapshot.player.gold)
            if sig == self._last_buy_sig:
                self._store_stuck_count += 1
            else:
                self._last_buy_sig = sig
                self._store_stuck_count = 0
            if self._store_stuck_count >= STORE_STUCK_LIMIT:
                self._shopping_abandoned = True
                self._set_town_store_attempted(store.store_type, snapshot.turn, "buy-stuck-leave")
                self._store_stuck_count = 0
                self._last_buy_sig = None
                self.last_reason = "shop:stuck-leave"
                return LEAVE_STORE_KEY
            remaining = self._purchase_quantity(snapshot, item)
            progress_sig = (item.letter, remaining, snapshot.player.gold)
            if self._last_buy_progress_sig is not None:
                old_letter, old_remaining, old_gold = self._last_buy_progress_sig
                if (
                    item.letter == old_letter
                    and remaining == old_remaining
                    and snapshot.player.gold < old_gold
                ):
                    self._store_buy_no_progress_count += 1
                elif item.letter != old_letter or remaining != old_remaining:
                    self._store_buy_no_progress_count = 0
            self._last_buy_progress_sig = progress_sig
            if self._store_buy_no_progress_count >= STORE_STUCK_LIMIT:
                self._shopping_abandoned = True
                self._set_town_store_attempted(store.store_type, snapshot.turn, "buy-no-progress")
                self._store_buy_no_progress_count = 0
                self._last_buy_progress_sig = None
                self.last_reason = "shop:defective-target-leave"
                return LEAVE_STORE_KEY
            if item.is_lantern:
                self.last_reason = "shop:buy-lantern"
            elif item.is_oil:
                self.last_reason = "shop:buy-oil"
            elif item.is_recall_scroll:
                self.last_reason = "shop:buy-recall"
            elif item.is_teleport_scroll:
                self.last_reason = "shop:buy-teleport"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
                self.last_reason = "shop:buy-cure-critical"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_SPEED:
                self.last_reason = "shop:buy-speed"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_HEALING:
                self.last_reason = "shop:buy-healing"
            elif item.is_treasure_detection_scroll:
                self.last_reason = "shop:buy-treasure-detection"
            elif item.is_digging_tool:
                fallback_purchase = self._digger_buy_fallback_available(snapshot)
                self.last_reason = (
                    "shop:buy-digging-tool:home-withdraw-failed-fallback"
                    if fallback_purchase
                    else "shop:buy-digging-tool"
                )
            elif item.is_ammo:
                self.last_reason = "shop:buy-ammo"
            elif item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH:
                self.last_reason = "shop:buy-torch"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
                self.last_reason = "shop:buy-identify"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
                self.last_reason = "shop:buy-star-identify"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_REMOVE_CURSE:
                self.last_reason = "shop:buy-remove-curse"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_REMOVE_CURSE:
                if (
                    not self._has_unremovable_curse_target(snapshot)
                    and self._star_remove_curse_reserve_purchase_needed(snapshot)
                ):
                    self._star_remove_curse_reserve_deposit_pending = True
                    signature = self._item_signature(item)
                    self._star_remove_curse_reserve_buy_inflight = (
                        signature,
                        self._inventory_signature_count(snapshot, signature),
                    )
                self.last_reason = "shop:buy-star-remove-curse"
            elif (
                item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_ENCHANT_WEAPON_TO_HIT
            ):
                self.last_reason = "shop:buy-enchant-tohit"
            elif (
                item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_ENCHANT_WEAPON_TO_DAM
            ):
                self.last_reason = "shop:buy-enchant-todam"
            elif (
                snapshot.player.food_type == FOOD_TYPE_MANA
                and item.tval in {TVAL_WAND, TVAL_STAFF}
            ):
                self.last_reason = "shop:buy-device-food"
            else:
                self.last_reason = "shop:buy-food"
            quantity = remaining
            # Unlike a speculative sell, this purchase names a ware from the
            # current emitted store page and _next_purchase has rechecked its
            # price/quantity.  Thus 'p' has a live selectable precondition; the
            # remaining Returns are prompt defaults and a final confirmation,
            # not an unchecked tail after a possibly unsupported command.
            suffix = f"{quantity}\r\r" if item.count > 1 else BUY_CONFIRM_SUFFIX
            self._store_buy_inflight = (
                store.store_type,
                signature,
                self._inventory_signature_count(snapshot, signature),
                snapshot.player.gold,
                0,
                self._decision_sequence,
            )
            if item.is_digging_tool and fallback_purchase:
                self._digger_fallback_bought_this_visit = True
            return BUY_KEY + item.letter + suffix

        self._store_buy_inflight = None
        self._last_buy_sig = None
        self._last_buy_progress_sig = None
        self._store_buy_no_progress_count = 0
        self._last_sell_sig = None
        self._store_stuck_count = 0
        self._store_sell_stuck_count = 0
        self._set_town_store_attempted(store.store_type, snapshot.turn, "shop-observed-complete")
        if store.store_type == STORE_ALCHEMIST and self._find_low_level_sale(snapshot) is None:
            self._sell_scavenged_consumables = False
            if self._fundraising_mode == "scavenge" and snapshot.in_town:
                self._fundraising_mode = "prepare"
                # Re-check the latched stores only when the scavenge pass
                # actually raised gold — that is what could have changed their
                # verdict. A blanket clear with UNCHANGED gold re-routed the
                # bot into the same out-of-stock stores forever: the
                # Alchemist<->Magic travel ping-pong, invisible to the loop
                # guard because store snapshots reset it and travel keeps the
                # position moving.
                if snapshot.player.gold > self._scavenge_entry_gold:
                    self._town_store_attempted.clear()
        if (
            snapshot.player.class_id < 0
            and store.store_type == STORE_GENERAL
            and not self._owns_lantern(snapshot)
        ):
            self._shopping_abandoned = True
        self.last_reason = "shop:leave"
        return LEAVE_STORE_KEY

    def _shopping_approach_step(
        self, snapshot: Snapshot, store_type: int | None = None
    ) -> Position | None:
        equipment_home_route = (
            self._equipment_transaction_session is not None
            and self._equipment_transaction_session.required_context == "home"
            and not self._town_store_blocked_under_applicable_bound(STORE_HOME)
            and self._town_visit_ledger.unsatisfied_passes[STORE_HOME]
            < self._town_store_visit_limit(STORE_HOME)
        )
        if not snapshot.in_town or (
            self._town_blocked_reason is not None
            and self._town_blocked_reason != "repetition"
            and not equipment_home_route
        ):
            return None
        if self._shopping_stuck:
            # The failed store was recorded in _town_store_attempted when the
            # approach limit fired. This latch must not suppress the alternate
            # store (or the restock wait) selected on the following turn.
            self._shopping_stuck = False
        if store_type is None:
            store_type = self._next_required_store_type(snapshot)
        if store_type is None:
            self._shop_approach_stuck_count = 0
            return None
        plan = self._town_errand_plan
        home_categories = (
            set(plan.need_categories.get(STORE_HOME, ()))
            if plan is not None else set()
        )
        if (
            store_type == STORE_HOME
            and "identification-withdrawal" in home_categories
            and home_categories <= {"identification-withdrawal"}
            and (
                not self._home_errand.active
                or self._home_errand.request is None
            )
        ):
            # Keep the staged post-Alchemist stop in the disposable plan, but
            # do not turn it into movement until its requester has filed the
            # executor's exact withdrawal request.
            return None
        if store_type == STORE_HOME:
            if not self._ensure_home_visit_request(snapshot):
                self._set_town_store_attempted(STORE_HOME, snapshot.turn, "home-request-unavailable")
                self._shopping_approach_store_type = None
                self._shopping_approach_goal = None
                return None
        equipment_owner = (
            store_type == STORE_HOME
            and self._equipment_transaction_session is not None
        )
        arbiter = self._town_turn_arbiter
        if arbiter is None:
            arbiter = _new_town_turn_arbiter()
            self._town_turn_arbiter = arbiter
        requested_owner = (
            "equipment-transaction" if equipment_owner else "town-errand"
        )
        existing_visit = (
            arbiter.store_visit if hasattr(arbiter, "store_visit") else None
        )
        visit = arbiter.acquire_store_visit(
            store_type=store_type,
            owner=requested_owner,
            purpose=("equipment-work" if equipment_owner else "shopping"),
            opened_sequence=self._decision_sequence,
            close_visit=self._close_store_visit,
        )
        self._acquire_store_visit_attempt = {
            "acquire_store_visit_called": True,
            "requested_owner": requested_owner,
            "requested_store": store_type,
            "acquire_result": (
                "refused"
                if visit is None
                else "granted-existing"
                if visit is existing_visit
                else "granted-new"
            ),
        }
        if visit is None:
            return None
        if (
            store_type == STORE_HOME
            and self._town_visit_ledger.approach_fails[store_type]
            >= self._town_store_visit_limit(store_type)
        ):
            self._set_town_store_attempted(store_type, snapshot.turn, "approach-fails-limit")
            self._shop_approach_stuck_count = 0
            return None
        self._shopping_approach_store_type = store_type
        if self._town_map_active(snapshot):
            self._shopping_approach_goal = self._town_map.store_position(store_type)
        if self._shopping_approach_goal is None:
            visible_goals = [
                grid.position
                for grid in snapshot.grids.values()
                if grid.store_number == store_type
            ]
            if visible_goals:
                self._shopping_approach_goal = min(
                    visible_goals,
                    key=lambda pos: snapshot.player.position.distance_to(pos),
                )
        mandatory_home_rescan = (
            store_type == STORE_HOME
            and snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and not self._equipment_catalog.home_scan_complete
            and bool(self._equipment_catalog.items)
        )
        here = snapshot.grid_at(snapshot.player.position)
        entrance_step_off = getattr(self, "_store_entrance_step_off", None)
        if (
            entrance_step_off is not None
            and (
                snapshot.turn != entrance_step_off[1]
                or snapshot.player.position != entrance_step_off[2]
            )
        ):
            self._store_entrance_step_off = None
        if here is not None and here.store_number == store_type:
            pending_store_transaction = (
                self._town_visit_ledger.pending_store_transaction
            )
            if (
                pending_store_transaction is not None
                and pending_store_transaction[0] == store_type
                and self._town_visit_ledger.pending_store_context_waits
                < STORE_STUCK_LIMIT
            ):
                # A null surface page at the unchanged entrance does not prove
                # that the preceding store command failed or that the visit
                # ended.  Wait for the confirming store generation.  The
                # visit ledger grants only the existing bounded retry window;
                # after it expires the ordinary step-off/re-entry path remains
                # available for genuinely outstanding NeedSpec work.
                self._town_visit_ledger.pending_store_context_waits += 1
                return snapshot.player.position
            # A player-turn snapshot is emitted on the entrance before the
            # queued SPECIAL_KEY_STORE opens the UI. Do not mistake that for a
            # completed store visit and immediately step back off the entrance.
            # A native town-travel command can also finish on the entrance
            # without queuing SPECIAL_KEY_STORE, however. Wait for one snapshot,
            # then step off and back on if the store still did not open.
            if (
                not self._last_snapshot_was_store
                and not self.last_reason.endswith(":await-entry")
            ):
                return snapshot.player.position
            # Standing on the store entrance in town (we just left it) — stepping
            # on it is what re-enters, so hop to an adjacent tile first, then the
            # next approach walks back on and opens the store.
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                self._store_entrance_step_off = (
                    self._decision_sequence,
                    snapshot.turn,
                    snapshot.player.position,
                )
            return neighbors[0] if neighbors else None
        # NO _least_visited_neighbor oscillation-breakout here. Breaking out
        # toward the "least-visited" tile would march the bot to the town's edge
        # and across the border into the open wilderness (an out-of-depth Cyclops
        # killed a clvl-4 bot exactly this way). If the store is unreachable,
        # return None and let safer logic handle it rather than wandering outward.
        step = self._nearest_goal_step(snapshot, lambda g: g.store_number == store_type)
        if step is None and self._town_map_active(snapshot):
            # At night the store entrance is unlit, so it is absent from the emitted
            # grids and the flag-based scan above finds nothing. Route to the store's
            # remembered position from the static town map instead — the layout is
            # prior knowledge a returning player already has.
            step = self._town_map_goal_step(
                snapshot, self._town_map.store_position(store_type)
            )
        if (
            step is None
            and self._shopping_approach_goal is not None
            and snapshot.player.position.distance_to(self._shopping_approach_goal) >= 3
        ):
            # A freshly resumed bot can know the distant store landmark without
            # yet remembering the intervening floor. This synthetic step is
            # consumed by native store travel, not as a raw movement direction.
            step = self._shopping_approach_goal
        if step is None:
            self._shop_approach_stuck_count = 0
            return None
        # A few bounces on the way in are fine (the store is usually a tile or two
        # on), but a store approach that keeps oscillating WITHOUT arriving means the
        # entrance is effectively unreachable (blocked, or the static-map route and
        # the live grid disagree). After SHOP_APPROACH_STUCK_LIMIT such turns, give
        # up SHOPPING for this visit and let the recall dive with what we have —
        # before the loop guard fires. Never wander outward (we return the store
        # step until then, never a least-visited edge tile).
        if self._is_oscillating():
            self._shop_approach_stuck_count += 1
        else:
            self._shop_approach_stuck_count = 0
        if self._shop_approach_stuck_count >= SHOP_APPROACH_STUCK_LIMIT:
            equipment_work_at_home = (
                store_type == STORE_HOME and self._outstanding_equipment_work()
            )
            self._shop_approach_stuck_count = 0
            if equipment_work_at_home:
                # The equipment transaction charges every issued Home approach
                # to its existing pass ceiling. The detector therefore keeps
                # returning the known route step without maintaining a second
                # route bound. A None above still distinctly means that map
                # routing found no step at all.
                return step
            self._shopping_stuck = True
            self._set_town_store_attempted(store_type, snapshot.turn, "shopping-stuck")
            self._town_visit_ledger.approach_fails[store_type] += 1
            return None
        return step

    def _shopping_approach_key(
        self, snapshot: Snapshot, step: Position, travel_reason: str
    ) -> str:
        """Ride native town travel toward the store, walking only as fallback.

        In the original-keyset travel point selector, shifted number-row symbols
        are direct store landmarks; ``.`` selects the landmark. ``n`` first
        declines Hengband's "continue previous travel?" prompt after an
        interrupted route. When there is no such prompt, point selection simply
        ignores that non-direction key. Native travel advances without waiting
        for a bot snapshot after every tile, which removes most town round-trip
        cost; an interruption mid-route is re-issued as long as it made
        progress (see _town_travel_key)."""
        if (
            self._equipment_transaction_owns_town_relocation(snapshot)
            and self._shopping_approach_store_type != STORE_HOME
        ):
            # Every store route, including candidate probes and one-step
            # fallbacks, converges here.  Refusal is deliberately pure: only
            # the transaction executor may mutate or abandon its session.
            return WAIT_KEY
        entry_failed_here = (
            self._store_entry_failed_owner == self._shopping_approach_store_type
        )
        if not entry_failed_here:
            if self._shopping_approach_store_type == STORE_HOME:
                self._bind_catalogued_home_identification_withdrawal(snapshot)
            atomic_shop = self._atomic_shop_transaction_key(snapshot)
            if atomic_shop is not None:
                return atomic_shop
            atomic_withdrawal = self._atomic_home_withdraw_key(snapshot, step)
            if atomic_withdrawal is not None:
                return atomic_withdrawal
            atomic_deposit = self._atomic_home_deposit_key(snapshot, step)
            if atomic_deposit is not None:
                return atomic_deposit
            # This is one observed-uncomposable-stop rule with two entry
            # points: Home is observed through the ~9 knowledge scan and has
            # no _shop_observation, while ordinary shops must consume their
            # observed page inside _atomic_shop_transaction_key.
            if (
                self._shopping_approach_store_type == STORE_HOME
                and self._resolve_observed_uncomposable_stop(snapshot)
            ):
                return WAIT_KEY
        elif step == snapshot.player.position:
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            self.last_reason = "store:entry-failed-step-off"
            return self._step_toward(snapshot, neighbors[0]) if neighbors else ""
        here = snapshot.grid_at(snapshot.player.position)
        if (
            step == snapshot.player.position
            and here is not None
            and here.store_number == self._shopping_approach_store_type
        ):
            self.last_reason = f"{travel_reason}:await-entry"
            self._store_entry_wait_owner = self._shopping_approach_store_type
            self._store_entry_wait_key = WAIT_KEY
            return WAIT_KEY
        if not self._has_light_equipped(snapshot):
            return self._step_toward(snapshot, step)
        goal = self._shopping_approach_goal
        clear_traveler = self._town_clear_traveler_key(snapshot, goal)
        if clear_traveler is not None:
            return clear_traveler
        store_type = self._shopping_approach_store_type
        if goal is None or store_type is None:
            return self._step_toward(snapshot, step)
        # A leading Escape dismisses a lingering -more- or prompt before the
        # backtick opens native travel; at the command loop it is a harmless
        # no-op. Without it, the prompt can eat ` and leave (notably) % to open
        # the visuals screen instead of selecting a store travel point.
        travel = self._town_travel_key(
            snapshot,
            goal,
            f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[store_type]}.",
            travel_reason,
        )
        if travel is not None:
            if not self._owner_may_select(snapshot, travel_reason):
                self._town_travel_fallback = goal
                self._town_travel_state = None
                self.last_reason = "shop:approach"
                return self._step_toward(snapshot, step)
            self._post_owner_expectation(
                snapshot, travel_reason, "position", "store_type"
            )
            # Native travel runs to completion without an intermediate bot
            # snapshot and may therefore perform the final movement onto the
            # shop tile itself.  Own that possible entry exactly like the
            # disclosed one-step entrance path below: the next surface page is
            # the documented lagged observation, not permission to compose a
            # store command across the entry flush.
            self._store_entry_wait_owner = store_type
            self._store_entry_wait_key = travel
            return travel
        return self._step_toward(snapshot, step)

    def _resolve_observed_uncomposable_stop(self, snapshot: Snapshot) -> bool:
        """Advance an observed stop whose one-shot command cannot be composed."""
        store_type = self._shopping_approach_store_type
        plan = self._town_errand_plan
        if (
            store_type is None
            or snapshot.store is not None
            or plan is None
            or plan.index >= len(plan.stops)
            or plan.stops[plan.index] != store_type
        ):
            return False
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or here.store_number != store_type:
            return False
        if store_type == STORE_HOME:
            observed = bool(
                self._equipment_catalog.home_scan_complete
                and self._home_knowledge_current
                and self._home_candidate_waiting
                and self._home_pending_item is None
                and not self._home_pending_batch
                and self._equipment_transaction_session is None
            )
        else:
            observed = bool(
                self._shop_observation is not None
                and self._shop_observation[0].store_type == store_type
            )
        if not observed:
            return False
        if store_type != STORE_HOME and self._wanted_purchase_is_home_first_refused(
            snapshot, store_type
        ):
            # The supplier page was observed, but Home-first arbitration
            # refused to ask the shop for the selected item.  Preserve both
            # the page and plan stop so this pass cannot become durable
            # evidence that the supplier had no actionable stock.
            observation_generation = (
                self._shop_observation[1]
                if self._shop_observation is not None
                else self._decision_sequence
            )
            if observation_generation == self._decision_sequence:
                return True
            plan.current_stop_passes = 0
            plan.index += 1
            self._shop_observation = None
            self._close_store_visit("home-first-yield")
            return False
        plan.blocked_this_visit.append(store_type)
        plan.current_stop_passes = 0
        plan.index += 1
        self._set_town_store_attempted(store_type, snapshot.turn, "observed-operation-uncomposable")
        if store_type == STORE_HOME:
            self._release_blocked_store_latches(store_type)
        else:
            self._town_visit_ledger.nonhome_attempted_without_effect[
                store_type
            ] = self._town_observable_effect_state(snapshot)
            self._shop_observation = None
        self.last_reason = "shop:observed-operation-uncomposable"
        return True

    def _atomic_shop_transaction_key(self, snapshot: Snapshot) -> str | None:
        """Compose one transaction from the latest observed page, outside."""
        observation = self._shop_observation
        if (
            observation is None
            or snapshot.store is not None
            or observation[0].store_type == STORE_HOME
        ):
            return None
        # Bind the one-shot to the page that was actually observed, not the
        # mutable town-plan cursor.  The ordinary shop handler advances that
        # cursor while producing the observe-and-leave result; using it here
        # made the adjacent outside handoff reject the target store and travel
        # to the following stop without composing the purchase.
        store_type = observation[0].store_type
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or here.store_number != store_type:
            return None

        observed_store, generation = observation
        # Store item letters are relative to page zero.  Ordinary shops reset
        # to that page on every entry, so a non-zero observation is stale or
        # malformed and must never be used to compose an atomic transaction.
        if observed_store.page_top not in (None, 0):
            self._shop_observation = None
            self.last_reason = "shop:one-shot-page-not-zero"
            return None
        # Current inventory/gold are paired with exactly this latest page at
        # the composition boundary; no cached item candidate is trusted.
        reason_before_composition = self.last_reason
        inner = self._shop(replace(snapshot, store=observed_store))
        if inner.startswith((BUY_KEY, SELL_KEY)):
            operation_key = inner + LEAVE_STORE_KEY
            key = WAIT_KEY
            self._shop_observation = None
            self._town_visit_ledger.pending_store_transaction = (
                observed_store.store_type,
                self._decision_sequence,
            )
            self._town_visit_ledger.pending_store_context_waits = 0
            self.last_reason = (
                "shop:one-shot-buy"
                if inner.startswith(BUY_KEY)
                else "shop:one-shot-sell"
            )
            if self._store_visit is not None:
                self._store_visit.operation_posted = True
                self._store_visit.operation_key = operation_key
                self._store_visit.operation_released = False
                self._store_visit.composed_key = key
                self._store_visit.posted_sequence = generation
                self._store_visit.posted_turn = snapshot.turn
                self._store_entry_wait_owner = observed_store.store_type
                self._store_entry_wait_key = key
            self._shop_selector_diagnostics.pop("composition_refusal", None)
            self._shop_selector_diagnostics.pop(
                "composition_refusal_sequence", None
            )
            return key
        if inner.startswith("{"):
            # Inscription is an outside pack operation.  Retain this page while
            # the next outside snapshot re-resolves the newly tagged item.
            return inner
        composition_refusal = self.last_reason
        if self._shop_selector_diagnostics.get(
            "composition_refusal_sequence"
        ) == self._decision_sequence:
            composition_refusal = self._shop_selector_diagnostics.get(
                "composition_refusal"
            )
        star_remove_curse_shelf_seen = self._star_remove_curse_shelf_seen
        self._record_shop_selector_diagnostics(
            replace(snapshot, store=observed_store), inner
        )
        self._star_remove_curse_shelf_seen = star_remove_curse_shelf_seen
        self._shop_selector_diagnostics["composition_refusal"] = composition_refusal
        self._shop_selector_diagnostics["composition_refusal_sequence"] = (
            self._decision_sequence
        )
        if composition_refusal == "shop:home-first-yields-to-current-visit":
            # This supplier was observed, but stale Home knowledge owns the
            # purchase.  Retire only this pass so the next router decision can
            # file and approach the Home refresh instead of re-entering here.
            plan = self._town_errand_plan
            if (
                plan is not None
                and plan.index < len(plan.stops)
                and plan.stops[plan.index] == store_type
            ):
                plan.current_stop_passes = 0
                plan.index += 1
            self._shop_observation = None
            self._close_store_visit("home-first-yield")
            self.last_reason = reason_before_composition
            return None
        if composition_refusal == "town:blocked:home-withdraw-failed-stock-present":
            # This is the deliberate terminal produced by a refreshed Home
            # census, not an ordinary uncomposable supplier pass.  Keep the
            # observed page and publish the stop at the consumed WAIT boundary.
            self._town_visit_ledger.pending_store_transaction = None
            self._town_visit_ledger.pending_store_context_waits = 0
            self._publish_purchase_home_block()
            return WAIT_KEY
        # Decide the observed no-op while this page is still current, then
        # consume it exactly as the pre-composition contract did.  A later
        # pack/gold change must re-observe the shelf before using its letters.
        if self._resolve_observed_uncomposable_stop(snapshot):
            return WAIT_KEY
        if composition_refusal in {
            "town:blocked:procurement-home-unavailable",
            "town:blocked:procurement-home-unroutable",
        }:
            self.last_reason = reason_before_composition
        self._shop_observation = None
        return None

    def _town_travel_key(
        self, snapshot: Snapshot, goal: Position, macro: str, reason: str
    ) -> str | None:
        """Progress-based gate shared by every native-travel leg (stores, Home,
        the dungeon entrance). Travel is re-issued after an interruption (a
        monster, a nudge Escape) as long as it got CLOSER to the goal since the
        last issue; TOWN_TRAVEL_STALL_LIMIT issues with no progress latch a
        fallback to BFS walking for that goal (the game rejects travel over an
        unknown approach). The latch clears when the goal changes or the floor
        does. Near goals just walk — a travel round-trip costs more than the
        last couple of steps."""
        if goal not in snapshot.grids:
            # An undisclosed goal cannot support native travel.  The emitted
            # grid set is not, however, an authoritative projection of
            # point_target's live candidate vector; a disclosed goal may still
            # be rejected.  That failure is handled after the recovery nudge.
            return None
        position = snapshot.player.position
        distance = position.distance_to(goal)
        if distance < TOWN_TRAVEL_MIN_DISTANCE:
            return None
        if self._town_travel_fallback is not None:
            if self._town_travel_fallback == goal:
                return None
            self._town_travel_fallback = None
        state = self._town_travel_state
        if state is not None and state.goal == goal:
            if state.record(distance, snapshot.turn) == "fallback":
                self._town_travel_fallback = goal
                self._town_travel_state = None
                return None
        else:
            self._town_travel_state = TownTravelProgress(
                goal, distance, 0, 0, snapshot.turn
            )
        self.last_reason = reason
        return macro

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
            self._town_travel_state = None
            return None
        clear_traveler = self._town_clear_traveler_key(snapshot, goal)
        if clear_traveler is not None:
            return clear_traveler
        return self._town_travel_key(
            snapshot, goal, ENTRANCE_TRAVEL_MACRO, "town:travel-entrance"
        )

    def _town_clear_traveler_key(
        self, snapshot: Snapshot, goal: Position | None = None
    ) -> str | None:
        """Compatibility hook for travel callers; town combat is global now."""
        return self._town_kill_mob_key(snapshot)

    def _town_kill_mob_key(self, snapshot: Snapshot) -> str | None:
        """Approach and kill every visible town monster except the player's pets.

        A direction key merely swaps places with a friendly in Hengband's
        ``exe_movement``.  The alter command instead reaches ``do_cmd_attack``
        through ``exe_alter``; a normal Warrior then receives the friendly-fire
        confirmation, answered inline by the trailing ``y``.
        """
        if not snapshot.in_town or snapshot.dungeon_level != 0:
            self._town_hunt_target = None
            return None
        player = snapshot.player
        targets = sorted(
            (monster for monster in snapshot.visible_monsters if not monster.pet),
            key=lambda monster: monster.distance,
        )
        for target in targets:
            self._town_hunt_target = target.position
            if player.position.distance_to(target.position) <= 1:
                if target.friendly:
                    self.last_reason = "town:kill-mob-friendly"
                    return "+" + self._direction_key(player.position, target.position) + "y"
                # Preserve the ordinary adjacent-hostile melee path and reason.
                return None
            step = self._nearest_goal_step(
                snapshot,
                lambda grid, target=target: grid.position.distance_to(target.position) <= 1,
            )
            if step is not None:
                self.last_reason = "town:kill-mob-approach"
                return self._step_toward(snapshot, step)
        if self._town_hunt_target is not None:
            if player.position.distance_to(self._town_hunt_target) <= 1:
                self._town_hunt_target = None
                return None
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: grid.position.distance_to(
                    self._town_hunt_target
                ) <= 1,
            )
            if step is not None:
                self.last_reason = "town:kill-mob-approach"
                return self._step_toward(snapshot, step)
            self._town_hunt_target = None
        return None

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

        Pack, weapon, and deep-loadout readiness are already enforced by
        departure_ok before a recall is read.  Recheck them here only because
        genuinely new snapshot information may arrive while recall is active.
        Optional surplus Home deposits deliberately gate neither departure nor
        an active recall; they wait for the next town visit.
        """
        blockers: list[str] = []
        if PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS:
            blockers.append("pack-too-full")
        if (
            snapshot.player.class_id >= 0
            and not self._combat_weapon_ready(snapshot)
        ):
            blockers.append("weapon-not-ready")
        landing_depth = snapshot.dungeon_recall_depths.get(destination, 0)
        if landing_depth > 20 and not self._equipment_departure_ready(snapshot):
            blockers.append("deep-loadout-unconfirmed")
        return blockers

    def _town_cancel_unsafe_recall_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or not snapshot.player.recalling:
            return None
        pending_destination = (
            self._pending_recall_dungeon_id
            if self._pending_recall_dungeon_id is not None
            else snapshot.recall_dungeon_id
        )
        active_destination = self._active_dungeon_target()
        destination_changed = (
            pending_destination != active_destination
            and self._recall_selection_key(snapshot, active_destination) is not None
            and self._recall_destination_safe(snapshot, active_destination)
        )
        blocks_teleport = any(
            self._blocks_teleport(item)
            for item in (*snapshot.inventory, *snapshot.equipment)
        )
        unready_blockers = self._recall_unready_blockers(
            snapshot, pending_destination
        )
        if (
            self._startup_town_recall
            and not destination_changed
            and not blocks_teleport
        ):
            # On attach, catalog/deposit/pack readiness is reconstructed over
            # subsequent observations and is not grounds to cancel a recall
            # that Hengband already owns.  Wrong destination and NO_TELE are
            # observable hard hazards, so they retain normal cancellation.
            return None
        if (
            self._emergency_recall_sanctioned
            and not destination_changed
            and not blocks_teleport
        ):
            return None
        if not destination_changed and not blocks_teleport and not unready_blockers:
            return None
        recall = self._find_recall_scroll(snapshot)
        if recall is None:
            return None
        if destination_changed or blocks_teleport:
            self._emergency_recall_sanctioned = False
        if destination_changed:
            self._pending_recall_dungeon_id = None
            self.last_reason = "town:cancel-wrong-recall-destination"
        else:
            self.last_reason = (
                "town:cancel-unsafe-recall"
                if blocks_teleport
                else "town:cancel-unready-recall"
            )
        return self._read_key(snapshot, recall)


    @staticmethod
    def _has_cursed_equipment(snapshot: Snapshot) -> bool:
        return any(item.is_cursed for item in snapshot.equipment)

    def _has_normal_remove_curse_target(self, snapshot: Snapshot) -> bool:
        return any(
            item.is_cursed
            and not self._curse_unremovable(item)
            for item in snapshot.equipment
        )


    def _has_unremovable_curse_target(self, snapshot: Snapshot) -> bool:
        return any(
            item.is_cursed and self._curse_unremovable(item)
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
        if store is not None and store.store_type == STORE_TEMPLE:
            return any(
                item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_REMOVE_CURSE
                and item.price <= snapshot.player.gold
                for item in store.items
            )
        if (
            self._town_map_active(snapshot)
            and self._town_map.store_position(STORE_TEMPLE) is None
        ):
            return False
        observed = self._town_visit_ledger.shelf_observations.get(
            (STORE_TEMPLE, "remove-curse")
        )
        return bool(
            observed
            and any(price <= snapshot.player.gold for price, _units in observed)
        )


    @staticmethod
    def _carried_star_remove_curse_count(snapshot: Snapshot) -> int:
        return sum(
            item.count
            for item in snapshot.inventory
            if item.tval == TVAL_SCROLL
            and item.sval == SV_SCROLL_STAR_REMOVE_CURSE
        )

    def _star_remove_curse_reserve_purchase_needed(
        self, snapshot: Snapshot
    ) -> bool:
        return (
            snapshot.player.gold >= FUNDRAISING_GOLD_TARGET
            and not self._recall_departure_shortage(snapshot)
            and self._home_star_remove_curse_count == 0
            and self._carried_star_remove_curse_count(snapshot) == 0
            and not self._star_remove_curse_reserve_deposit_pending
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
                return None
            self._heavy_cursed_items.discard(self._item_signature(stale_tag))
            cleaned = stale_tag.inscription.replace(HEAVY_CURSE_TAG, "").strip()
            if not cleaned:
                self.last_reason = "equipment:clear-heavy-curse-tag"
                return UNINSCRIBE_KEY + "/" + slot_key
            self.last_reason = "equipment:remove-heavy-curse-tag"
            return INSCRIBE_KEY + "/" + slot_key + cleaned + "\r"

        signature = self._heavy_curse_inscription_pending
        if signature is None or not snapshot.in_town:
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
            return None
        if snapshot.store is not None:
            self.last_reason = "equipment:leave-store-to-mark-heavy-curse"
            return LEAVE_STORE_KEY
        slot_key = EQUIPMENT_SLOT_KEY.get(target.slot)
        if slot_key is None:
            return None
        self._heavy_curse_inscription_pending = None
        # The initial inscription opens in overwrite mode. Ctrl-E moves to its
        # end and switches to insert mode before the persistent marker is added.
        suffix = "\x05 " + HEAVY_CURSE_TAG
        self.last_reason = "equipment:mark-heavy-curse"
        return INSCRIBE_KEY + "/" + slot_key + suffix + "\r"

    def _find_remove_curse_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval in {SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE},
        )

    def _town_remove_curse_key(self, snapshot: Snapshot) -> str | None:
        """Read a Remove Curse scroll during town prep when a cursed item is worn,
        so it can be swapped/upgraded and its penalties lifted before diving."""
        if not snapshot.in_town or not self._has_cursed_equipment(snapshot):
            return None
        player = snapshot.player
        if player.blind or player.confused:
            return None
        cursed = next(
            (
                item for item in snapshot.equipment
                if item.is_cursed
                and not self._curse_unremovable(item)
            ),
            None,
        )
        star = self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval == SV_SCROLL_STAR_REMOVE_CURSE,
        )
        scroll = star or self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval == SV_SCROLL_REMOVE_CURSE,
        )
        if scroll is None:
            return None
        if cursed is None and scroll.sval != SV_SCROLL_STAR_REMOVE_CURSE:
            return None
        if cursed is None:
            cursed = next((item for item in snapshot.equipment if item.is_cursed), None)
        if cursed is None:
            return None
        self._remove_curse_watch = (
            self._item_signature(cursed),
            scroll.sval,
            sum(
                item.count for item in snapshot.inventory
                if item.is_scroll and item.aware and item.sval == scroll.sval
            ),
        )
        if scroll.sval == SV_SCROLL_STAR_REMOVE_CURSE:
            self._star_remove_curse_reserve_withdraw_pending = False
        self.last_reason = "town:remove-curse"
        return self._read_key(snapshot, scroll)



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

    def _town_random_teleport_suppression_key(
        self, snapshot: Snapshot
    ) -> str | None:
        """Suppress visible or still-hidden random teleport before equipping."""
        if not snapshot.in_town:
            return None

        # choose_key normally performs this synchronization before dispatch,
        # but keeping the action self-contained ensures its catalog predicate
        # is evaluated against this exact observation.
        self._refresh_carried_equipment_catalog(snapshot)
        preparation = self._prepare_equipment_optimization(snapshot)
        selected_ids = self._equipment_preparation_selected_ids(preparation)
        pending = tuple(
            owned
            for owned in self._equipment_catalog.items
            if self._needs_random_teleport_suppression(owned, selected_ids)
        )
        pack_owned = next(
            (owned for owned in pending if owned.origin == "pack"), None
        )
        equipped_owned = next(
            (owned for owned in pending if owned.origin == "equipped"), None
        )
        if pack_owned is not None or equipped_owned is not None:
            if snapshot.store is not None:
                self.last_reason = "equipment:leave-store-to-suppress-random-teleport"
                return LEAVE_STORE_KEY
            if pack_owned is not None:
                self.last_reason = "equipment:suppress-random-teleport"
                return INSCRIBE_KEY + pack_owned.item.slot + ".\r"
            slot_key = EQUIPMENT_SLOT_KEY.get(equipped_owned.equipped_slot)
            if slot_key is not None:
                self.last_reason = "equipment:suppress-equipped-random-teleport"
                return INSCRIBE_KEY + "/" + slot_key + ".\r"

        home_owned = next(
            (owned for owned in pending if owned.origin == "home"), None
        )
        if (
            home_owned is not None
            and snapshot.store is None
            and self._home_pending_item is None
            and self._item_signature(home_owned.item)
            not in self._deferred_home_items
            and self._town_pack_space_ready(snapshot)
        ):
            # The completed ~9 catalogue owns the identity and shelf ordinal.
            # Arm the ordinary derived-address withdrawal only outside; its
            # entrance path owns visit bounds, posting, page arithmetic, the
            # take command, and the exit.
            self._home_pending_item = self._item_signature(home_owned.item)
            self._home_random_teleport_withdrawal = self._home_pending_item
        return None


    def _town_cycle_detected(self) -> bool:
        """A full window of town decisions collapsing to a handful of distinct
        (reason, position) signatures with no progress is a repetition cycle,
        whatever subsystem drives it."""
        history = self._town_signature_history
        recent = list(history)[-TOWN_FAST_TRAVEL_WINDOW:]
        travel_rows = [row for row in recent if "travel" in row[0]]
        if (
            len(recent) == TOWN_FAST_TRAVEL_WINDOW
            and len(travel_rows) >= TOWN_FAST_TRAVEL_MIN_ROWS
            and len({(row[1], row[2]) for row in travel_rows})
            <= TOWN_FAST_TRAVEL_MAX_POSITIONS
        ):
            # A failed native-travel command is not repaired by clearing generic
            # shopping state.  Escalate this first observed fast cycle directly
            # to the existing visible town stop instead of waiting for a second
            # 48-decision cycle.
            self._town_cycle_breaks = max(
                self._town_cycle_breaks, TOWN_CYCLE_BREAK_LIMIT - 1
            )
            return True
        if len(history) < TOWN_CYCLE_WINDOW:
            return False
        return len(set(history)) <= TOWN_CYCLE_MAX_DISTINCT

    def _break_town_cycle(self, snapshot: Snapshot) -> None:
        """Cut every fuel line the known cycle shapes run on. Latching all the
        stores sends the errand router to its no-store path (the departure
        gates take over); the session/disposal/travel resets kill the other
        observed drivers. The latches expire on the normal STORE_RETRY_TURNS
        schedule, so a later town visit shops normally again."""
        # This repair starts a fresh observation epoch.  In particular, a
        # wander-limit detection may leave the generic no-progress count at 60;
        # carrying that debt forward makes 36 legitimate entrance-walk steps
        # look like a second cycle and stops the bot before it can depart.
        self._town_signature_history.clear()
        self._town_no_progress_count = 0
        self._town_wander_streak = 0
        ledger = self._supply_ledger(snapshot, self._planned_depth())
        shortages = (
            self._ledger_departure_shortages(ledger)
            if self._last_return_trigger in {
                "recall-low",
                "teleport-low",
                "cure-low",
                "next-depth-kit",
                "escape-kit-empty",
            }
            else []
        )
        preserved_stores = {
            store
            for status in shortages
            if status.obtainable
            for store in status.stores
        }
        attempted_stores = dict(self._town_store_attempted)
        self._town_store_attempted.clear()
        try:
            departure_needs = [
                need
                for need in self._departure_blocking_town_needs(snapshot)
                if self._town_need_supplier_reachable(snapshot, need)
            ]
        finally:
            self._town_store_attempted.update(attempted_stores)
        preserved_stores.update(need.store_type for need in departure_needs)
        for store_type in range(len(TOWN_TRAVEL_STORE_SYMBOLS) + 1):
            if store_type in preserved_stores:
                self._town_store_attempted.pop(store_type, None)
            else:
                self._set_town_store_attempted(
                    store_type,
                    snapshot.turn,
                    "repetition-preserve-exhausted-store",
                    if_absent=True,
                )
        self._abandon_blocked_equipment_transaction(snapshot)
        self._clear_pending_disposal()
        self._close_store_visit("abandoned-with-restore")
        self._shopping_stuck = True
        self._town_travel_state = None
        self._town_travel_fallback = None
        # A cycle can begin only after the ordinary departure route has already
        # spent/expired its navigation-ledger budget.  The repair is a fresh
        # observation epoch, so re-arm the entrance as well as clearing the
        # store/native-travel state; otherwise the forced repetition owner has
        # no selectable goal and can only WAIT forever.
        self._nav_ledger.reset()
        self._town_restock_wait_until = None
        # The ordinary fundraising router changes prepare -> scavenge after
        # the required shops are exhausted.  Suppression returns before that
        # router can run, so preserve the same transition here; otherwise the
        # departure gates keep hiding the entrance and the bot merely wanders.
        if (
            self._fundraising_mode is None
            and snapshot.player.gold < FUNDRAISING_START_GOLD
        ):
            self._fundraising_mode = "scavenge"
            self._scavenge_entry_gold = snapshot.player.gold
        elif self._fundraising_mode == "prepare" or (
            self._fundraising_mode == "mine"
            and not self._fundraising_departure_ready(snapshot)
        ):
            self._fundraising_mode = "scavenge"
            self._scavenge_entry_gold = snapshot.player.gold
        # After a cycle the goal is DEPARTURE, not errands: without this, a
        # restock-retry path starts a fresh in-town wait, un-latches the very
        # stores above when it expires, and the cycle resumes.
        self._town_restock_suppressed = not preserved_stores
        self._town_suppression_claim_stores.update(preserved_stores)
        self._town_errand_plan = (
            self._build_town_errand_plan(snapshot, departure_needs)
            if departure_needs
            else (
                TownErrandPlan(sorted(preserved_stores))
                if preserved_stores
                else None
            )
        )

    def _town_blocked_store_context(self, snapshot: Snapshot) -> bool:
        here = snapshot.grid_at(snapshot.player.position)
        return snapshot.store is not None or (
            self._last_snapshot_was_store
            and here is not None
            and here.is_store
        )

    def _town_blocked_entrance_has_composable_operation(
        self, snapshot: Snapshot
    ) -> bool:
        """Yield a blocked entrance when its owner can compose a Home take."""
        if snapshot.store is not None or not self._home_knowledge_current:
            return False
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or here.store_number != STORE_HOME or not self._home_page_size:
            return False
        if (
            self._shopping_approach_store_type != STORE_HOME
            or self._home_atomic_withdraw_pending is not None
        ):
            return False
        addressable = tuple(
            item
            for index, item in enumerate(self._home_knowledge_items)
            if index < self._home_knowledge_valid_before
        )
        session = self._equipment_transaction_session
        action = session.current_action if session is not None else None
        if action is not None and action.kind == "withdraw":
            return any(
                item.is_equipment
                and equipment_identity(item) == action.item_identity
                for item in addressable
            )
        requested = {
            *self._calibration_restore_signatures,
            *self._home_pending_batch,
            *(
                (self._home_pending_item,)
                if self._home_pending_item is not None
                else ()
            ),
            *(
                (self._home_errand.request.signature,)
                if self._home_errand.active and self._home_errand.request is not None
                else ()
            ),
        }
        return any(self._item_signature(item) in requested for item in addressable)

    def _town_blocked_key(self, snapshot: Snapshot) -> str | None:
        """Leave an open/interleaved store UI before handling a town block.

        A repeated town cycle is recoverable once its shopping fuel lines have
        been cut: own the route to the dungeon entrance until the character is
        out of town.  Treating that case like an unrecoverable block used to
        issue WAIT forever outside a store, so the CLI could only stop the bot.
        Other blocked reasons remain visible terminal waits.
        """
        self.last_reason = f"town:blocked:{self._town_blocked_reason}"
        if self._town_blocked_reason == "repetition" and snapshot.store is not None:
            store = snapshot.store
            if self._town_blocked_purchase_is_composable(snapshot):
                # Keep the ordinary two-visit one-shot contract: this page only
                # records the shelf, then the outside entrance page binds the
                # exact purchase before re-entry releases its command tail.
                self._shop_observation = (store, self._decision_sequence)
                self.last_reason = "shop:observe-and-leave"
            else:
                self._close_store_visit("repetition-block-abandoned")
            return LEAVE_STORE_KEY
        if (
            self._town_blocked_reason is not None
            and self._town_blocked_reason.startswith("equipment-transaction:")
        ):
            blocked_reason = self._town_blocked_reason
            blocked_owner = f"town:blocked:{blocked_reason}"
            if not self._owner_may_select(snapshot, blocked_owner):
                self._town_blocked_reason = None
                return None
            unobserved_withdrawal = blocked_reason.startswith(
                "equipment-transaction:withdraw-item-unobserved:"
            )
            self._abandon_blocked_equipment_transaction(snapshot)
            # Abandoning releases the failed executable plan, but this caller
            # is the terminal owner.  Preserve the cause so the next outside
            # snapshot cannot rebuild the same Home need and enter unowned.
            if unobserved_withdrawal:
                self._town_blocked_reason = blocked_reason
            if snapshot.store is not None:
                self._post_owner_expectation(
                    snapshot, blocked_owner, "store_type", "inventory", "equipment"
                )
                return LEAVE_STORE_KEY
            here = snapshot.grid_at(snapshot.player.position)
            if here is not None and here.is_store:
                neighbors = self._walkable_neighbors(
                    snapshot, snapshot.player.position
                )
                if neighbors:
                    self._post_owner_expectation(
                        snapshot, blocked_owner, "position", "inventory", "equipment"
                    )
                    return self._step_toward(snapshot, neighbors[0])
                self._post_owner_expectation(
                    snapshot, blocked_owner, "position", "inventory", "equipment"
                )
                return "2"
            self._post_owner_expectation(
                snapshot, blocked_owner, "inventory", "equipment", "gold"
            )
            return WAIT_KEY if unobserved_withdrawal else None
        if snapshot.store is None:
            here = snapshot.grid_at(snapshot.player.position)
            if here is not None and here.is_store:
                neighbors = self._walkable_neighbors(
                    snapshot, snapshot.player.position
                )
                if neighbors:
                    return self._step_toward(snapshot, neighbors[0])
                # Interleaved main-loop snapshots can omit surrounding town
                # cells immediately after leaving a store. Still step off the
                # door instead of sending another ESC into the town command loop.
                return "2"
        if self._town_blocked_store_context(snapshot):
            return LEAVE_STORE_KEY
        if self._town_blocked_reason == "repetition":
            clear_traveler = self._town_kill_mob_key(snapshot)
            if clear_traveler is not None:
                return clear_traveler
            required_store = self._next_required_store_type(snapshot)
            if (
                self._store_visit is not None
                and not self._store_visit.operation_posted
                and required_store is not None
                and self._store_visit.store_type != required_store
            ):
                # A captured outside snapshot can resume after the store-page
                # eject above.  Release the abandoned owner before asking the
                # approach router to bind the store that is required now.
                self._close_store_visit("repetition-block-abandoned")
            shopping_step = self._shopping_approach_step(snapshot)
            if shopping_step is not None:
                self.last_reason = "town:repetition-required-shopping"
                return self._shopping_approach_key(
                    snapshot,
                    shopping_step,
                    "town:repetition-required-shopping",
                )
            here = snapshot.grid_at(snapshot.player.position)
            if (
                here is not None
                and self._is_active_dungeon_entrance(here)
                and not self._descent_is_blocked(snapshot)
                and self._dungeon_entry_allowed(
                    snapshot,
                    via_recall=False,
                    destination_depth=self._dungeon_entry_depth(
                        snapshot, self._active_dungeon_target(), via_recall=False
                    ),
                )
            ):
                self.last_reason = "town:repetition-depart:enter"
                return ENTER_DUNGEON_MACRO
            step = self._descent_step(snapshot)
            if step is not None:
                travel = self._entrance_travel_key(
                    snapshot, self._descent_target_goal
                )
                # Every departure rung must yield when it cannot advance.
                # In particular, a rejected native-travel command or a
                # degenerate BFS step must not hide the recall rung below.
                if travel not in (None, WAIT_KEY):
                    return travel
                walk = self._step_toward(snapshot, step)
                if walk != WAIT_KEY:
                    self.last_reason = "town:repetition-depart"
                    return walk
            if not snapshot.player.recalling:
                recall = self._find_recall_scroll(snapshot)
                if recall is not None:
                    selection = ""
                    if snapshot.in_town:
                        recall_dest, recall_dungeon_id = (
                            self._town_recall_destination(snapshot)
                        )
                        if recall_dest is None:
                            return WAIT_KEY
                        if not self._dungeon_entry_allowed(
                            snapshot,
                            via_recall=True,
                            destination_depth=self._dungeon_entry_depth(
                                snapshot, recall_dungeon_id, via_recall=True
                            ),
                        ):
                            return WAIT_KEY
                        selection = self._recall_selection_key(
                            snapshot, recall_dungeon_id
                        )
                        if selection is None:
                            return WAIT_KEY
                    self.last_reason = "town:repetition-depart:recall"
                    self._emergency_recall_sanctioned = True
                    return self._read_key(snapshot, recall, selection)
        return WAIT_KEY

    def _town_recall_destination(
        self, snapshot: Snapshot
    ) -> tuple[str | None, int]:
        """Choose the voluntary town-recall destination without issuing it."""
        recall_dest = None
        recall_dungeon_id = self._target_dungeon_id
        if (
            self._target_dungeon_id == DUNGEON_ANGBAND
            and snapshot.angband_recall_unlocked
            and self._recall_destination_safe(snapshot, DUNGEON_ANGBAND)
        ):
            recall_dest = "angband"
        elif (
            self._target_dungeon_id not in (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE)
            and self._target_dungeon_id in snapshot.entered_dungeon_ids
            and self._recall_destination_safe(snapshot, self._target_dungeon_id)
        ):
            recall_dest = "alt-dungeon"
        elif (
            self._target_dungeon_id == DUNGEON_YEEK_CAVE
            and self._fundraising_mode not in {"mine", "scavenge"}
            and not self._taken_kill_quest_requires_walk_in(snapshot)
            and self._deepest_level >= RECALL_MIN_DEPTH
            and self._recall_destination_safe(snapshot, DUNGEON_YEEK_CAVE)
        ):
            recall_dest = "yeek-cave"
        return recall_dest, recall_dungeon_id

    def _town_special_key(self, snapshot: Snapshot) -> str | None:
        full_identify_trip = self._morivant_full_identify_key(snapshot)
        if full_identify_trip is not None:
            return full_identify_trip
        if not snapshot.in_town or snapshot.player.class_id < 0:
            return None
        if self._town_cycle_pending:
            # _observe caught a repetition cycle (see _town_cycle_detected).
            # First offense: cut every fuel line the known cycle shapes run on
            # (errand router latches, transaction session, disposal target,
            # travel state) and carry on. A second cycle in the same town
            # visit means the repair did not hold — stop visibly instead of
            # burning supplies for hours.
            self._town_cycle_pending = False
            self._town_cycle_breaks += 1
            if self._town_cycle_breaks >= TOWN_CYCLE_BREAK_LIMIT:
                # Re-apply the repair before the forced departure.  A second
                # detector can be raised by a different errand subsystem after
                # the first pass, so this closes any state it reopened.
                self._break_town_cycle(snapshot)
                self._town_blocked_reason = "repetition"
                return self._town_blocked_key(snapshot)
            self._break_town_cycle(snapshot)
            if (
                self._fundraising_mode in {"mine", "scavenge"}
                and not self._fundraising_light_ready(snapshot)
            ):
                self._town_blocked_reason = "departure-no-light"
                return self._town_blocked_key(snapshot)
            # Once ordinary town work has been suppressed there is no useful
            # router left to own the walk to an entrance. Leaving this unset
            # handed the next turn back to generic navigation, where a large
            # town could accumulate another full wander window before the
            # second detector finally forced departure. Preserve the visible
            # one-turn cycle-break marker, then let _town_blocked_key own every
            # following turn until the character leaves town. Fundraising is
            # deliberately excluded: its scavenge/mine mode owns a different
            # shallow-dungeon departure route.
            if self._town_restock_suppressed and self._fundraising_mode is None:
                self._town_blocked_reason = "repetition"
            self.last_reason = "town:cycle-break"
            return WAIT_KEY
        if self._town_blocked_reason is not None:
            return self._town_blocked_key(snapshot)

        if (
            self._fundraising_mode in {"prepare", "scavenge"}
            and self._fundraising_supplies_ready(snapshot)
        ):
            # Store-route suppression prevents another futile shopping cycle;
            # it must not freeze the activity mode after the complete mining
            # kit is already in the pack. Promotion itself neither clears nor
            # revisits a store latch, so it is safe while suppression remains.
            self._fundraising_mode = "mine"
            self._mining_runs_completed = 0
            # Promotion changes the dungeon activity, not the stock that was
            # just observed in town.  Clearing every visit latch here made the
            # current errand plan revisit the same empty/unaffordable shop
            # immediately, producing Alchemist -> entrance -> Alchemist trips.
            # Genuine stock turnover is re-armed by _retry_after_store_restock.

        if (
            not self._town_restock_suppressed
            and self._town_restock_wait_until is not None
            and snapshot.turn < self._town_restock_wait_until
        ):
            self.last_reason = self._restock_wait_reason(snapshot)
            return RESTOCK_WAIT_MACRO

        if (
            self._fundraising_mode == "mine"
            and self._mining_runs_completed >= self._effective_mining_run_target()
        ):
            self._fundraising_mode = None
            self._mining_runs_completed = 0
            self._planned_mining_runs = None
            self._town_store_attempted.clear()
            self._town_restock_suppressed = False
            self._town_errand_plan = None
            return None

        # A resumed bot does not retain the in-memory partial batch selected
        # after shop stock ran out. Reconstruct it from supplies already carried
        # before applying the departure gate.
        if self._fundraising_mode == "mine" and self._planned_mining_runs is None:
            self._activate_partial_mining_plan(snapshot)
        player = snapshot.player
        if (
            player.hp < player.max_hp
            or player.mp < player.max_mp
            or not self._temporary_status_clear(snapshot)
        ) and player.food_state in {"normal", "full", "gorged"}:
            self.last_reason = "town:recover"
            return REST_MACRO

        if self._fundraising_mode in {"mine", "scavenge"}:
            if not self._fundraising_departure_ready(snapshot):
                # Do not let this early fundraising wait starve the ordinary
                # town pack-pressure pipeline below.  Descent deliberately
                # rejects a completely full pack, so waiting here can only
                # become a cycle; falling through lets identification, safe
                # destruction, and the terminal overflow fallback free a slot.
                if len(snapshot.inventory) >= PACK_CAPACITY:
                    return None
                plan = self._town_errand_plan
                if plan is not None and plan.index >= len(plan.stops):
                    # Every planned shop owner has already run, so another wait
                    # cannot improve the departure kit.  Apply the same bounded
                    # fallback as the generic town-cycle detector immediately;
                    # waiting for its 30-decision window produced a visible
                    # departure-blocked loop outside the final shop.
                    self._break_town_cycle(snapshot)
                    self.last_reason = "fundraise:fallback-exhausted-plan"
                    return None
                # Once every store route has been abandoned, preferred food is
                # optional for a shallow scavenge dive.  A working light was
                # checked when the cycle was broken and remains a hard gate.
                if (
                    self._town_restock_suppressed
                    and self._fundraising_mode == "scavenge"
                    and self._fundraising_light_ready(snapshot)
                ):
                    return None
                here = snapshot.grid_at(snapshot.player.position)
                if here is not None and here.is_store:
                    neighbors = self._walkable_neighbors(
                        snapshot, snapshot.player.position
                    )
                    if neighbors:
                        self.last_reason = "fundraise:departure-blocked-step-off"
                        return self._step_toward(snapshot, neighbors[0])
                self.last_reason = "fundraise:departure-blocked"
                self.prompt_owner_handoff = "town:blocked:departure-no-light"
                return WAIT_KEY
            return None

        rumor_needed = (
            self._rumor_unlock_pending and not snapshot.angband_recall_unlocked
        ) or self._town_travel_rumor_pending is not None
        if rumor_needed:
            # Revealing a destination is a town prerequisite, not an expedition.
            # Do not require a complete dive loadout before reading the rumors
            # needed to make the inn's travel destination selectable.
            if (
                self._town_travel_rumor_pending is None
                and not self._town_departure_ready(snapshot)
            ):
                self.last_reason = "town:rumor-wait-supplies"
                return WAIT_KEY
            if player.gold < RUMOR_GOLD_RESERVE + RUMOR_COST:
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                self.last_reason = "town:rumor-needs-funds"
                return WAIT_KEY
            step = self._nearest_goal_step(
                snapshot, lambda grid: grid.building_type == INN_BUILDING_TYPE
            )
            if step is None and self._town_map_active(snapshot):
                # At night / far off, the inn is unlit and absent from the emitted
                # grids; route to its remembered position from the static town map
                # (unless we are already standing on it, where a path-to-self is
                # empty). Mirrors the store / Hunter's Office approach.
                inn_pos = self._town_map.building_position(INN_BUILDING_TYPE)
                if inn_pos is not None and player.position != inn_pos:
                    step = self._town_map_goal_step(snapshot, inn_pos)
            if step is not None:
                self.last_reason = "town:rumor"
                # _nearest_goal_step returns only the FIRST step of the path. The
                # rumor keys must ride along ONLY when that step lands on the inn
                # (walking onto it opens the building menu, which then consumes
                # them); while still approaching, send the bare move — otherwise
                # 'u'+exit leak into the town command loop and the inn is never
                # entered, so Angband recall never unlocks.
                target = snapshot.grids.get(step)
                if target is not None and target.building_type == INN_BUILDING_TYPE:
                    # Read a whole batch of rumors this one visit (menu stays open
                    # between reads), capped by what we can afford above the
                    # reserve, then leave. The next snapshot shows whether the
                    # Angband-unlock rumor came up (angband_recall_unlocked).
                    reads = min(
                        RUMOR_READS_PER_VISIT,
                        max(1, (player.gold - RUMOR_GOLD_RESERVE) // RUMOR_COST),
                    )
                    self.last_reason = "town:rumor-batch"
                    return self._step_toward(
                        snapshot,
                        step,
                        tail=RUMOR_READ_KEY * reads + LEAVE_STORE_KEY,
                    )
                return self._step_toward(snapshot, step)
            # Inn unreachable, or we are already standing on it. Do NOT latch a
            # sticky WAIT block — that froze the bot on the inn tile forever
            # (town "5-loop"). Fall through to the recall logic below so the run
            # continues (dive again) instead of waiting on an unreachable rumor.

        # Return to the dungeon by Word of Recall once we have depth to justify it:
        # to Angband once its recall is unlocked (Yeek Cave conquered), otherwise
        # back into a deep Yeek Cave run (recall lands at the deepest level, far
        # faster than re-walking from the entrance). Fundraising deliberately mines
        # level 1, so it keeps walking to the entrance instead.
        recall_dest, recall_dungeon_id = self._town_recall_destination(snapshot)
        # A completed scan with no pending Home or identification owner cannot
        # legitimately defer departure.  This also repairs old visit state
        # created before disposal completion released the latch at its source.
        self._release_stale_home_candidate_waiting(snapshot)
        # A consumed/moved item can leave the old in-memory pointer behind even
        # though there is no longer an errand capable of clearing it.  Do this
        # immediately before the departure gate so an inert latch cannot turn a
        # ready recall into generic town wandering.
        if (
            self._home_pending_item is not None
            and self._home_atomic_withdraw_pending is None
            and self._pending_inventory_item(snapshot) is None
            and not self._home_candidate_waiting
        ):
            self._home_pending_item = None
            self._home_pending_slot = None
            self._identification_candidate = None
            self._identification_need = None
        if (
            self._identification_need is not None
            and self._home_pending_item is None
            and not self._home_pending_batch
            and not self._home_batch_review_items
            and not self._home_candidate_waiting
        ):
            self._identification_need = None
            self._identification_candidate = None
        # Free pack space is a hard departure requirement. A full Home or an
        # unreachable shop must not become permission to Recall over-packed.
        # Combat readiness remains an independent hard gate as well.
        departure_conjuncts = self._recall_town_departure_conjuncts(snapshot)
        departure_ok = all(departure_conjuncts.values())
        if recall_dest is not None and not departure_ok:
            self._departure_block = self._departure_block_state(
                snapshot, departure_conjuncts
            )
        else:
            self._departure_block = {}
        self._departure_block_sequence = self._decision_sequence
        if (
            recall_dest is not None
            and not snapshot.player.recalling
            and self._find_recall_scroll(snapshot) is None
        ):
            # A zero-scroll visit cannot execute this recall objective.
            # Suppliers may both be latched after genuine stock failure;
            # wait for turnover instead of falling through to dungeon-style
            # town exploration while carrying an unreachable objective.
            return self._recall_restock_key(snapshot)
        if recall_dest is not None and departure_ok:
            self._cross_town_shopping = None
            recall_count = sum(
                item.count for item in snapshot.inventory if item.is_recall_scroll
            )
            issue_watch = self._town_recall_issue_watch
            if not snapshot.player.recalling and issue_watch is not None:
                watched_destination, issue_turn, pre_read_count = issue_watch
                if watched_destination != recall_dungeon_id:
                    self._town_recall_issue_watch = None
                    self._pending_recall_dungeon_id = None
                elif recall_count < pre_read_count or snapshot.turn <= issue_turn:
                    # A reduced stack proves that the read succeeded even when a
                    # stale/interleaved snapshot temporarily reports recalling
                    # as false.  An unchanged snapshot at the command turn is
                    # likewise not evidence of rejection.  Wait for the engine's
                    # next authoritative state instead of spending another scroll.
                    self.last_reason = "town:await-recall-confirmation"
                    return WAIT_KEY
                else:
                    # The turn advanced without consuming the scroll: the read
                    # was genuinely rejected, so allow one ordinary retry.
                    self._town_recall_issue_watch = None
                    self._pending_recall_dungeon_id = None
            if snapshot.player.recalling:
                here = snapshot.grid_at(snapshot.player.position)
                if here is not None and here.is_store:
                    neighbors = self._walkable_neighbors(
                        snapshot, snapshot.player.position
                    )
                    if neighbors:
                        self.last_reason = "town:wait-recall-step-off"
                        return self._step_toward(snapshot, neighbors[0])
                self.last_reason = "town:wait-recall"
                return WAIT_KEY
            if (
                not self._char_dump_done_this_visit
                and not snapshot.player.blind
                and not snapshot.player.confused
            ):
                # Snapshot the full character sheet just before committing to the
                # dive, so the human can review stats/resistances/equipment per dive.
                self._char_dump_done_this_visit = True
                self.last_reason = "town:character-dump"
                return CHARACTER_DUMP_MACRO
            if not snapshot.player.blind and not snapshot.player.confused:
                recall = self._find_recall_scroll(snapshot)
                if recall is not None:
                    destination_depth = self._dungeon_entry_depth(
                        snapshot, recall_dungeon_id, via_recall=True
                    )
                    if not self._dungeon_entry_allowed(
                        snapshot,
                        via_recall=True,
                        destination_depth=destination_depth,
                    ):
                        return WAIT_KEY
                    selection = self._recall_selection_key(
                        snapshot, recall_dungeon_id
                    )
                    if selection is None:
                        return None
                    self._pending_recall_dungeon_id = recall_dungeon_id
                    self._town_recall_issue_watch = (
                        recall_dungeon_id,
                        snapshot.turn,
                        recall_count,
                    )
                    self.last_reason = f"town:recall-to-{recall_dest}"
                    return self._read_key(snapshot, recall, selection)

        if recall_dest is not None and not departure_ok:
            blocker = self._terminal_equipment_blocker(snapshot)
            if blocker is not None:
                self._town_blocked_reason = blocker
                return self._town_blocked_key(snapshot)
            # The errand registry and its bounded store passes have no remaining
            # owner, yet some departure prerequisite is still false.  Expose
            # that otherwise-unclassified gate through the existing visible
            # terminal instead of handing town back to generic stuck:wander.
            if not self._town_claims_active(snapshot):
                expedition = self._cross_town_shopping_key(snapshot)
                if expedition is not None:
                    return expedition
                supplier = self._departure_supplier_counterfactual(snapshot)
                if supplier is not None:
                    self._town_blocked_reason = None
                    return None
                self._town_blocked_reason = "departure-unsatisfiable"
                return self._town_blocked_key(snapshot)
        # Destination safety is a departure assertion, not an errand-router
        # precondition.  Run it only after every town owner above has had the
        # opportunity to act; otherwise an unsafe deep recall can starve a live
        # supply plan before its next shop stop.  With no town claim left, make
        # the genuine no-destination state a visible terminal instead of an
        # unlatched WAIT that is reconsidered forever.
        if (
            self._target_dungeon_id == DUNGEON_ANGBAND
            and snapshot.angband_recall_unlocked
            and not self._recall_destination_safe(snapshot, DUNGEON_ANGBAND)
        ):
            if self._activate_safe_recall_fallback(snapshot) is not None:
                self.last_reason = "town:unsafe-recall-fallback"
                return WAIT_KEY
            if self._town_claims_active(snapshot):
                return None
            # Outstanding equipment work suppresses this departure terminal
            # only while its bounded Home route remains available. Once Home
            # is blocked or its ceiling is consumed, expose the exhausted work
            # as its own named terminal instead of falling through to a cycle.
            if self._equipment_work_home_route_available():
                return None
            if self._outstanding_equipment_work():
                self._town_blocked_reason = "equipment-work-home-route-exhausted"
                return self._town_blocked_key(snapshot)
            destination_depth = self._dungeon_entry_depth(
                snapshot, DUNGEON_ANGBAND, via_recall=True
            )
            if not self._destination_depth_allowed(snapshot, destination_depth):
                self._town_blocked_reason = self.last_reason
                return self._town_blocked_key(snapshot)
            self._town_blocked_reason = "no-safe-recall-destination"
            return self._town_blocked_key(snapshot)
        return None

    def _departure_block_state(
        self, snapshot: Snapshot, conjuncts: dict[str, bool] | None = None
    ) -> dict[str, object]:
        """Expose the exact enumeration consumed by the departure decision."""
        town_ledger = {
            "store_visits": dict(self._town_visit_ledger.store_visits),
            "need_attempts": dict(self._town_visit_ledger.need_attempts),
            "approach_fails": dict(self._town_visit_ledger.approach_fails),
            "unsatisfied_passes": dict(
                self._town_visit_ledger.unsatisfied_passes
            ),
            "blocked_stores": sorted(self._town_visit_ledger.blocked_stores),
            "passes_since_progress": self._town_visit_ledger.passes_since_progress,
            "drift_warnings": list(self._town_visit_ledger.drift_warnings),
        }
        town_claims = list(getattr(self, "_town_claim_categories", ()))
        values = dict(conjuncts or self._recall_town_departure_conjuncts(snapshot))
        selected_gate = "town_departure_ready"
        failures = [name for name, value in values.items() if not value]
        return {
            "failed": failures,
            "values": values,
            "gate": selected_gate,
            "ready": not failures,
            "diagnostics": {
                "free_pack_slots": PACK_CAPACITY - len(snapshot.inventory),
                "minimum_free_pack_slots": MIN_FREE_PACK_SLOTS,
            },
            "town_claims": town_claims,
            "town_ledger": town_ledger,
        }

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
            and item.known
            and not item.is_cursed
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





    def _restore_mining_combat_hand_key(
        self, snapshot: Snapshot, reason: str
    ) -> str | None:
        """Restore each combat hand displaced by the temporary mining loadout."""
        main_hand = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"),
            None,
        )
        for target_slot, remembered_name, remembered_identity, optimal_known in (
            (
                "main_hand",
                self._normal_weapon_name,
                self._normal_weapon_identity,
                self._normal_weapon_is_optimal,
            ),
            (
                "sub_hand",
                self._normal_sub_hand_name,
                self._normal_sub_hand_identity,
                self._normal_sub_hand_is_optimal,
            ),
        ):
            equipped = next(
                (item for item in snapshot.equipment if item.slot == target_slot),
                None,
            )
            if equipped is None or not equipped.is_digging_tool:
                continue
            if target_slot == "sub_hand" and optimal_known and remembered_name is None:
                if main_hand is not None and not main_hand.is_digging_tool:
                    self._digger_wield_attempts = 0
                    key = self._equipment_takeoff(
                        snapshot, "combat-loadout", EQUIPMENT_SLOT_KEY[target_slot]
                    )
                    if key is not None:
                        self.last_reason = reason
                    return key
                continue
            replacement = self._first_item(
                snapshot,
                lambda item: item.is_equipment
                and not item.is_digging_tool
                and item.known
                and not item.is_cursed
                and not item.is_broken
                and not self._blocks_teleport(item)
                and (
                    equipment_identity(item) == remembered_identity
                    if remembered_identity is not None
                    else item.name == remembered_name
                    if remembered_name is not None
                    else (
                        item.is_melee_weapon
                        if target_slot == "main_hand"
                        else item.tval == 34 or item.is_melee_weapon
                    )
                ),
            )
            if replacement is None:
                if (
                    target_slot == "sub_hand"
                    and main_hand is not None
                    and not main_hand.is_digging_tool
                ):
                    self._digger_wield_attempts = 0
                    key = self._equipment_takeoff(
                        snapshot, "combat-loadout", EQUIPMENT_SLOT_KEY[target_slot]
                    )
                    if key is not None:
                        self.last_reason = reason
                    return key
                continue
            self._digger_wield_attempts += 1
            if self._digger_wield_attempts >= DIGGER_WIELD_LIMIT:
                self._digger_wield_attempts = 0
                self.last_reason = f"{reason}:abandon-unconfirmed-equip"
                return None
            key = self._equipment_wield(
                snapshot, "combat-loadout", replacement, target_slot
            )
            if key is not None:
                self.last_reason = reason
            return key
        self._digger_wield_attempts = 0
        self._mining_combat_loadout_remembered = False
        return None

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

    def _victory_loot_key(self, snapshot: Snapshot) -> str | None:
        if not self._yeek_victory_loot or snapshot.floor_key[0] != DUNGEON_YEEK_CAVE:
            return None
        if len(snapshot.inventory) >= PACK_CAPACITY:
            triage = self._full_pack_loot_triage_key(snapshot)
            if triage is not None:
                return triage
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
            return self._step_toward(snapshot, step)
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




    @staticmethod
    def _strategy_force_for_snapshot(
        snapshot: Snapshot, profile: StrategyProfile
    ) -> dict[str, object]:
        force: dict[str, object] = dict(profile.required_force)
        tiers = force.get("defensive_tiers", ())
        if not isinstance(tiers, list):
            return force
        eligible = [
            tier for tier in tiers
            if isinstance(tier, dict)
            and snapshot.player.ac >= int(tier.get("min_ac", 0))
        ]
        if not eligible:
            return force
        tier = max(eligible, key=lambda item: int(item.get("min_ac", 0)))
        for name in ("min_hp", "heal_potions"):
            if name in tier:
                force[name] = int(tier[name])
        return force

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
        # the naked calibration yet, so use those observed combat results as a
        # conservative unbranded score instead of calling a real weapon 0 DPS.
        if dps is None and weapon is not None:
            blows = max(0, snapshot.player.main_hand_blows)
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
            damage = max(0.0, average_dice + snapshot.player.main_hand_to_d)
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


    def _telmora_q2_travel_key(
        self, snapshot: Snapshot, quest: QuestState
    ) -> str | None:
        """Use the inn service for the approved Q2 errand, never wilderness."""
        if snapshot.visited_town_ids is None or 1 not in snapshot.visited_town_ids:
            return None
        if (
            self._effective_town_id(snapshot) == 1
            and self._telmora_q2_errand
            and quest.status in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}
        ):
            key = self._town_teleport_key(snapshot, 0)
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
            key = self._town_teleport_key(snapshot, 1)
            if key is not None:
                self.last_reason = "fixedquest:q2-teleport"
            return key
        return None

    def _town_teleport_key(
        self, snapshot: Snapshot, destination_town_id: int
    ) -> str | None:
        current_town_id = self._effective_town_id(snapshot)
        required_gold = (
            TOWN_TELEPORT_COST
            if destination_town_id == 0
            else 2 * TOWN_TELEPORT_COST
        )
        if snapshot.player.gold < required_gold:
            self.town_teleport_refusal = {
                "current_town_id": current_town_id,
                "destination_town_id": destination_town_id,
                "gold": snapshot.player.gold,
                "required_gold": required_gold,
            }
            self.last_reason = "town:teleport-refused-fare"
            return None
        inn_type = TOWN_TELEPORT_BUILDING_TYPES.get(
            current_town_id
        )
        if inn_type is None:
            return None
        positions = frozenset(
            grid.position for grid in snapshot.grids.values()
            if grid.building_type == inn_type
        )
        if not positions and self._town_map_active(snapshot):
            position = self._town_map.building_position(inn_type)
            positions = frozenset({position}) if position is not None else frozenset()
        if snapshot.player.position in positions:
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                self.last_reason = "town:teleport-step-off"
                return self._step_toward(snapshot, neighbors[0])
            return None
        step = min(
            (candidate for candidate in (
                self._town_map_goal_step(snapshot, position) for position in positions
            ) if candidate is not None),
            key=lambda pos: snapshot.player.position.distance_to(pos),
            default=None,
        )
        if step is None:
            return None
        self.last_reason = "town:teleport"
        suffix = "m" + chr(ord("a") + destination_town_id) if step in positions else ""
        return self._step_toward(snapshot, step, tail=suffix)

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
                return self._step_toward(snapshot, neighbors[0])
            return None

        step = self._nearest_goal_step(
            snapshot,
            lambda grid: grid.building_type == HUNTER_OFFICE_BUILDING_TYPE,
        )
        if step is None and office_pos is not None:
            step = self._town_map_goal_step(snapshot, office_pos)
        if step is None:
            # Cannot route to the office right now — skip cashing out rather than
            # latching a sticky town block that strands the bot even after the
            # bounties are gone. The remains keep; other errands proceed.
            return None

        self.last_reason = "bounty:approach"
        grid = snapshot.grid_at(step)
        enters_office = (
            grid is not None
            and grid.building_type == HUNTER_OFFICE_BUILDING_TYPE
        ) or (office_pos is not None and step == office_pos)
        if enters_office:
            self.last_reason = "bounty:cashout"
            return self._step_toward(
                snapshot,
                step,
                tail="c" + ("y" * len(bounties)) + LEAVE_STORE_KEY,
            )
        return self._step_toward(snapshot, step)

    def _observe_navigation_commitments(self, snapshot: Snapshot) -> None:
        """Observe loot and exploration owners on every dungeon decision."""
        committed_loot = self._loot_target
        if committed_loot is None:
            committed_loot = min(
                self._known_loot - self._deferred_loot,
                key=lambda pos: (pos.y, pos.x),
                default=None,
            )
        if committed_loot is not None:
            self._nav_ledger.observe(
                "loot",
                committed_loot,
                snapshot.player.position.distance_to(committed_loot),
            )
            if self._nav_ledger.is_expired("loot", committed_loot):
                self._deferred_loot.add(committed_loot)
                self._loot_defer_blocker = "navigation-ledger:loot"
                if self._loot_target == committed_loot:
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
                self._deferred_loot.update(
                    loot for loot in self._known_loot
                    if loot.distance_to(monster.position) <= 1
                )


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
        while queue:
            position, first_step = queue.popleft()
            if position != start and position in targets:
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

    def _read_dungeon_recall_scroll_key(
        self, snapshot: Snapshot, recall: InventoryItem
    ) -> str:
        recall_count = sum(
            item.count for item in snapshot.inventory if item.is_recall_scroll
        )
        self._dungeon_recall_issue_watch = (
            snapshot.floor_key,
            snapshot.turn,
            recall_count,
        )
        self._post_owner_expectation(
            snapshot, "return:recall", "inventory", "recalling", "floor"
        )
        return self._read_key(snapshot, recall)

    def _dungeon_recall_confirmation_key(
        self, snapshot: Snapshot
    ) -> str | None:
        """Share the pending dungeon-recall read guard between all issuers."""
        issue_watch = self._dungeon_recall_issue_watch
        if snapshot.player.recalling or issue_watch is None:
            return None
        if not self._owner_may_select(
            snapshot, "return:await-recall-confirmation"
        ):
            self._dungeon_recall_issue_watch = None
            return None
        watched_floor, issue_turn, pre_read_count = issue_watch
        if watched_floor != snapshot.floor_key:
            self._dungeon_recall_issue_watch = None
            return None
        recall_count = sum(
            item.count for item in snapshot.inventory if item.is_recall_scroll
        )
        if snapshot.turn <= issue_turn or (
            recall_count < pre_read_count
            and snapshot.turn <= issue_turn + RECALL_ISSUE_CONFIRM_TURNS
        ):
            # Treat both the unchanged command-turn redraw and a consumed
            # scroll within the confirmation window as pending states. The
            # exported recalling flag can lag behind either, so reading again
            # can consume a second scroll.
            self.last_reason = "return:await-recall-confirmation"
            self._post_owner_expectation(
                snapshot,
                self.last_reason,
                "inventory",
                "recalling",
                "floor",
            )
            return WAIT_KEY
        # The turn advanced without consuming the scroll: the command was
        # genuinely rejected, so one ordinary retry is safe.
        self._dungeon_recall_issue_watch = None
        self._owner_expectations.release("return:recall")
        return None

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
        info = self._dungeon_knowledge.get(snapshot.floor_key[0])
        return bool(
            info is not None
            and info.guardian_id > 0
            and snapshot.floor_key[0] not in snapshot.conquered_dungeon_ids
            and snapshot.dungeon_level >= info.max_depth - 1
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





    def _should_start_town_return(self, snapshot: Snapshot) -> bool:
        # Records WHICH condition ends the run in self._last_return_trigger, so the
        # decision log shows why every dive returned (see the depth_safety telemetry).
        if snapshot.in_town:
            return False
        if self._guardian_descent_blocked(snapshot):
            self._last_return_trigger = "guardian-kit-insufficient"
            return True
        if len(snapshot.inventory) >= PACK_CAPACITY:
            self._last_return_trigger = "pack-full"
            return True
        # Hungry with nothing edible left ends ANY run — including mining and
        # scavenge dives, which the suppression below otherwise exempts from
        # every supply threshold. A fundraising character starved to death
        # behind that exemption (2026-07-17): income policy owns its economics,
        # never the character's survival.
        if snapshot.player.hungry and self._find_edible(snapshot) is None:
            self._last_return_trigger = "food-hungry"
            return True
        # Income dives own their completion/return policy in _fundraising_key.
        # Ordinary expedition supply thresholds must not bounce a freshly
        # launched scavenge or mining run straight back to town.
        if self._fundraising_mode in {"mine", "scavenge"}:
            return False
        ledger = self._supply_ledger(snapshot, snapshot.dungeon_level)
        if snapshot.player.class_id >= 0:
            if (
                self._deepest_floor_escape_kit_empty(snapshot)
                and (
                    ledger["teleport"].obtainable
                    or snapshot.dungeon_level > WALK_OUT_MAX_DEPTH
                )
            ):
                self._last_return_trigger = "escape-kit-empty"
                return True
            # A resistance gap at the CURRENT floor -- not the next one, which
            # _is_descent_target already gates before a descent is taken -- means
            # the character is standing somewhere its present gear no longer
            # covers: Word of Recall can land at the save-backed deepest floor
            # after a resistance-granting item was swapped/stashed, or an amulet
            # swap mid-dive can drop a required resistance. Nothing previously
            # caught an EXISTING gap, only a prospective one on the next stairs.
            # Leaving the depth (the return itself) clears this, so it cannot
            # flap. DEPTH_ABILITY_REQUIREMENTS only starts at 20F, so shallow
            # (and Yeek Cave mining, capped at 13F) floors never trigger it.
            if self._missing_required_abilities(snapshot, snapshot.dungeon_level):
                self._last_return_trigger = "resist-gap"
                return True
            ledger_shortages = self._ledger_return_shortages(
                ledger,
                snapshot.dungeon_level,
            )
            ledger_shortages = [
                status for status in ledger_shortages
                if status.kind in {"recall", "teleport", "cure"}
            ]
            if ledger_shortages:
                self._last_return_trigger = {
                    "recall": "recall-low",
                    "teleport": "teleport-low",
                    "cure": "cure-low",
                }[ledger_shortages[0].kind]
                return True
            if snapshot.dungeon_level >= 1:
                if not self._expedition_light_ready(snapshot):
                    self._last_return_trigger = "light-low"
                    return True
            equipped_light = next(
                (it for it in snapshot.equipment if it.is_light), None
            )
            if equipped_light is None:
                self._last_return_trigger = "no-light"
                return True
            if (
                equipped_light.known
                and equipped_light.sval <= SV_LITE_LANTERN
                and equipped_light.fuel <= 0
                and self._light_refill_item(snapshot) is None
            ):
                self._last_return_trigger = "light-empty"
                return True
            knows_downstairs = bool(self._remembered_downstairs) or any(
                grid.known and grid.has_down_stairs
                for grid in snapshot.grids.values()
            )
            if knows_downstairs and self._next_depth_supply_shortage(snapshot):
                self._last_return_trigger = "next-depth-kit"
                return True
        # Hunger-without-food already returned True above (it runs before the
        # fundraising exemption); with something edible carried, the survival
        # gate eats instead of ending the run. Note the trigger fires only at
        # the ACTUAL hungry bands (hungry/weak/fainting), not below Full —
        # "normal" is a wide band with ample margin to reach town, and bailing
        # there abandoned deep dives far too eagerly.
        return False

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

    def _return_to_town_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        *,
        allow_recall: bool = True,
    ) -> str | None:
        player = snapshot.player
        if snapshot.in_town:
            self._dungeon_recall_issue_watch = None
            return None
        active_fixed = self._active_fixed_quest_id(snapshot)
        if (
            self._quest_floor_exit_locked(snapshot)
            or active_fixed is not None and self._fixed_quest_is_once(active_fixed)
        ):
            # A quest exit is represented as up-stairs, but ordinary pack/light/
            # supply returns must never fail a one-shot quest. Survival escapes
            # run earlier and remain intentionally permitted.
            self._returning_to_town = False
            self._last_return_trigger = None
            return None
        if self._should_start_town_return(snapshot) or player.recalling:
            self._returning_to_town = True
        if not self._returning_to_town:
            return None

        here = snapshot.grid_at(player.position)
        if here is not None and self._is_upstairs_target(here):
            self.last_reason = "return:ascend"
            return UP_STAIRS_KEY

        pending_recall = self._dungeon_recall_confirmation_key(snapshot)
        if pending_recall is not None:
            return pending_recall

        if player.recalling:
            self.last_reason = "return:wait-recall"
            return WAIT_KEY

        # A previously latched return bypasses the ordinary light-upkeep block
        # later in _decide.  Refill here before trying to read Word of Recall:
        # Hengband rejects reading in darkness without consuming a turn, which
        # otherwise repeats READ_KEY + slot until the loop watchdog stops us.
        if not player.confused:
            darkness_recovery = self._darkness_recovery_key(snapshot)
            if darkness_recovery is not None:
                return darkness_recovery
        dark_locomotion = self._dark_locomotion_key(snapshot)
        if dark_locomotion is not None:
            return dark_locomotion

        recall = self._find_recall_scroll(snapshot)
        if (
            allow_recall
            and snapshot.dungeon_level > WALK_OUT_MAX_DEPTH
            and recall is not None
            and not player.blind
            and not player.confused
            and self._can_read_scrolls(snapshot)
            and self._owner_may_select(snapshot, "return:recall")
        ):
            self.last_reason = "return:recall"
            return self._read_dungeon_recall_scroll_key(snapshot, recall)

        upstairs_step = self._escape_state.read_once(
            snapshot,
            "return:upstairs-step",
            lambda: self._nearest_goal_step(snapshot, self._is_upstairs_target),
        )
        assert upstairs_step is None or isinstance(upstairs_step, Position)
        wall_owner = (
            self._escape_state.owner == "return"
            and self._escape_state.rung == "return:seek-secret-wall"
        )
        if wall_owner:
            if upstairs_step is None:
                self._escape_state.stable_decisions = 0
            else:
                self._escape_state.stable_decisions += 1
                if self._escape_state.stable_decisions >= 2:
                    self._escape_state.release()
                    self.last_reason = "return:seek-upstairs"
                    if self._escape_state.owner != "disengage":
                        self._escape_state.enter("return", self.last_reason)
                    return self._step_toward(snapshot, upstairs_step)

            # A temporary occupant can split a one-tile corridor in the
            # remembered movement graph for one decision. Once that hands the
            # exit search to the wall owner, keep consuming its existing search
            # budgets instead of letting a single clear redraw reverse course.
            if (
                not self._is_forgetting_maze(snapshot)
                and not player.blind
                and not player.confused
            ):
                if self._undersearched_walls(player.position):
                    self._record_wall_search(player.position)
                    self.last_reason = "return:search-upstairs"
                    return SEARCH_KEY
                step = self._secret_wall_search_step(snapshot)
                if step is not None:
                    self.last_reason = "return:seek-secret-wall"
                    return self._step_toward(snapshot, step)

            # No wall-search budget remains reachable. Release ownership so the
            # normal return rungs (including a currently valid stair path) can
            # make progress.
            self._escape_state.release()

        if upstairs_step is not None:
            self.last_reason = "return:seek-upstairs"
            if self._escape_state.owner != "disengage":
                self._escape_state.enter("return", self.last_reason)
            return self._step_toward(snapshot, upstairs_step)

        if self._is_oscillating():
            # The ordinary exploration owner has an oscillation breakout below,
            # but a latched return exits through this method first. Give walking
            # returns the same unknown probe/search escape instead of repeating
            # a four-cell frontier cycle forever.
            step = self._probe_unknown_step(snapshot)
            if step is not None:
                self._clear_explore_path(ExplorationPathOutcome.PAUSE)
                self.last_reason = "return:probe"
                return self._step_toward(snapshot, step)
            if (
                not self._is_forgetting_maze(snapshot)
                and not player.blind
                and not player.confused
                and self._undersearched_walls(player.position)
            ):
                self._record_wall_search(player.position)
                self._clear_explore_path(ExplorationPathOutcome.PAUSE)
                self.last_reason = "return:search-upstairs"
                return SEARCH_KEY
        else:
            step = self._explore_step(snapshot)
            if step is not None:
                self.last_reason = "return:explore"
                return self._step_toward(snapshot, step)

        # Returning without a recall scroll requires an up-stair, which may be
        # hidden behind a secret door. This cannot use the ordinary secret-wall
        # sweep below: the return owner exits earlier, and that sweep is disabled
        # whenever any down-stair is known. Search likely wall exits after all
        # reachable floor/frontier exploration is exhausted.
        if (
            not self._is_forgetting_maze(snapshot)
            and not player.blind
            and not player.confused
        ):
            if self._undersearched_walls(player.position):
                self._record_wall_search(player.position)
                self.last_reason = "return:search-upstairs"
                return SEARCH_KEY
            step = self._secret_wall_search_step(snapshot)
            if step is not None:
                self.last_reason = "return:seek-secret-wall"
                if self._escape_state.owner != "disengage":
                    self._escape_state.enter("return", self.last_reason)
                return self._step_toward(snapshot, step)

        step = self._least_visited_neighbor(snapshot)
        if step is not None:
            self.last_reason = "return:wander"
            return self._step_toward(snapshot, step)

        self.last_reason = "return:wait"
        return WAIT_KEY




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
    ) -> list[MonsterState]:
        """Find awake melee attackers that can soon confuse or paralyze us.

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
            if attacks > 0:
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


    def _detected_threat_preparation_key(
        self, snapshot: Snapshot, visible_hostiles: list[MonsterState]
    ) -> str | None:
        """Anticipate detected threats without treating them as attack targets."""
        detected = [
            monster
            for monster in self._perceived_hostiles(snapshot)
            if monster.perception == "detected"
        ]
        if not detected:
            return None

        # Keep the lower-certainty channel in the normal damage model, but do
        # not pass it to melee, ranged, line-of-fire, or blocker-clearing code.
        self.threat_prediction(snapshot, detected, turns=3)
        if visible_hostiles:
            return None
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
        if not breeders and len(melee_threats) < 2:
            return None
        if (
            self._open_neighbor_count(snapshot, snapshot.player.position)
            <= SUMMONER_CHOKE_NEIGHBORS - 1
        ):
            return None
        step = self._summoner_retreat_step(
            snapshot, breeders or melee_threats, detected
        )
        if step is None:
            return None
        self.last_reason = "detected:prepare-choke"
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

    def _missing_required_abilities(self, snapshot: Snapshot, depth: int) -> frozenset:
        missing = set(required_depth_gates(depth) - snapshot.player.abilities)
        if DESTRUCTION_GATE_LABEL in missing and self._has_destruction_method(snapshot):
            missing.discard(DESTRUCTION_GATE_LABEL)
        if SPEED_GATE_LABEL in missing and snapshot.player.speed >= SPEED_GATE_MINIMUM:
            # player.speed includes temporary boosts; a hasted check at the
            # stairs slightly over-trusts, which is acceptable for this gate.
            missing.discard(SPEED_GATE_LABEL)
        return frozenset(missing)




    def _clear_unseen_retreat(self) -> None:
        if self._escape_state.owner == "unseen":
            self._escape_state.release()
        self._unseen_retreat_floor = None
        self._unseen_retreat_direction = None
        self._unseen_retreat_target = None
        self._unseen_choke_position = None
        self._unseen_wait_remaining = 0
        self._unseen_wait_intercepted = False

    @staticmethod
    def _is_unseen_attack_message(message: str) -> bool:
        """Whether a direct monster blow names Hengband's hidden actor.

        The finite method text comes from monster-attack-describer.cpp:64-229.
        monster-attack-player.cpp:297-310 joins the actor to that text, while
        monster-describer.cpp:39-53,91 supplies 何か / it / something when the
        attacking monster is hidden.
        """
        message = re.sub(r" <x[1-9]\d*>$", "", message)
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
        for position in reversed(self._recent):
            if position != origin:
                return (
                    position.y - origin.y,
                    position.x - origin.x,
                )
        return None




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

    def _summoner_retreat_step(
        self,
        snapshot: Snapshot,
        summoners: list[MonsterState],
        hostiles: list[MonsterState],
    ) -> Position | None:
        origin = snapshot.player.position
        origin_distance = min(origin.distance_to(monster.position) for monster in summoners)
        seen = {origin}
        queue: deque[tuple[Position, Position | None, int]] = deque([(origin, None, 0)])
        candidates: list[tuple[int, int, int, Position]] = []

        while queue:
            position, first_step, path_distance = queue.popleft()
            if position != origin and first_step is not None:
                openness = self._open_neighbor_count(snapshot, position)
                summoner_distance = min(
                    position.distance_to(monster.position) for monster in summoners
                )
                if (
                    openness <= SUMMONER_CHOKE_NEIGHBORS
                    and summoner_distance >= origin_distance
                ):
                    candidates.append(
                        (path_distance, openness, -summoner_distance, first_step)
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
            return min(candidates, key=lambda candidate: candidate[:3])[3]
        return self._flee_step(snapshot, hostiles)


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


    def _town_entrance_cells(self, snapshot: Snapshot) -> set[Position]:
        """Known modal store/building cells that routes should avoid crossing."""
        if not snapshot.in_town:
            return set()
        self._refresh_town_facts(snapshot)
        if self._town_entrance_cache is not None:
            return set(self._town_entrance_cache)
        # _town_emitted_entrances preserves a legacy ``store_number is not None``
        # predicate and therefore includes ordinary parsed grids whose sentinel
        # is -1.  The visit set uses the real modal-cell predicates and retains
        # observed entrances after they leave the emitted window.
        entrances = set(self._town_visit_entrances)
        if self._town_map_active(snapshot):
            entrances.update(self._town_map.stores.values())
            entrances.update(self._town_map.buildings.values())
            for positions in self._town_map.quest_buildings.values():
                entrances.update(positions)
            for positions in self._town_map.quest_entrances.values():
                entrances.update(positions)
        self._town_entrance_cache = frozenset(entrances)
        return set(self._town_entrance_cache)


    def _town_map_goal_step(
        self,
        snapshot: Snapshot,
        target: Position | None,
        *,
        blocked: set[Position] | None = None,
        allow_entrance_fallback: bool = True,
    ) -> Position | None:
        """BFS to a specific static-town-map tile (store or dungeon entrance).

        Unlike _nearest_goal_step, the goal is matched by POSITION rather than by
        an emitted grid flag, so it still works at night: an unlit store/entrance
        tile is absent from snapshot.grids, yet the town map remembers where it
        is and merged it into the walkable set. Returns the first step, or None if
        already there / unreachable across the remembered walkable tiles.
        """
        if target is None:
            return None
        start = snapshot.player.position
        if start == target:
            return None
        blocked = blocked or set()
        entrance_cells = self._town_entrance_cells(snapshot)
        entrance_cells.discard(start)
        entrance_cells.discard(target)
        route_attempts = (blocked | entrance_cells, blocked)
        if not allow_entrance_fallback:
            route_attempts = route_attempts[:1]
        for route_blocked in route_attempts:
            seen = {start}
            queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
            while queue:
                pos, first_step = queue.popleft()
                if pos == target:
                    return first_step
                for neighbor in self._walkable_neighbors(snapshot, pos):
                    if neighbor in seen or neighbor in route_blocked:
                        continue
                    seen.add(neighbor)
                    queue.append(
                        (neighbor, neighbor if first_step is None else first_step)
                    )
        return None

    def _town_map_descent_entrance(self, snapshot: Snapshot) -> Position | None:
        """The town map's '>' entrance, but only when the bot would descend on
        foot: fundraising mines level 1, and a shallow run (deepest below the
        recall threshold) walks in. A deep run returns by Word of Recall from
        anywhere in town (see _town_special_key), so it needs no entrance route.
        """
        if not self._town_map_active(snapshot):
            return None
        if self._town_map.entrance is None:
            return None
        entrance = snapshot.grids.get(self._town_map.entrance)
        remembered_suppressed_entrance = (
            entrance is None
            and self._town_restock_suppressed
        )
        if not remembered_suppressed_entrance and (
            entrance is None or not self._is_active_dungeon_entrance(entrance)
        ):
            return None
        if self._town_restock_suppressed:
            # A deep character with no recall scroll loses its saved depth here,
            # but an L1 walk-in is the only remaining departure; do not turn it
            # into an unsupplied deep recall. This departure-only bypass also
            # skips _fundraising_departure_ready's kit/light/HP gate; light is
            # checked by _descent_is_blocked, and DESCEND_MIN_HP_RATIO remains
            # the final HP backstop before the entrance command is emitted.
            return self._town_map.entrance
        if (
            self._fundraising_mode in {"mine", "scavenge"}
            or self._deepest_level < RECALL_MIN_DEPTH
        ):
            return self._town_map.entrance
        return None





    def _retire_explore_goal(
        self, identity: ExplorationGoalIdentity
    ) -> None:
        self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
        self._explore_goal_identity = None

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


    def _effective_town_id(self, snapshot: Snapshot) -> int:
        """Recover a missing town id from exported, player-known landmarks."""
        if snapshot.town_id >= 0:
            return snapshot.town_id
        observed_buildings = {
            grid.building_type: grid.position
            for grid in snapshot.grids.values()
            if grid.known and grid.building_type >= 0
        }
        if not observed_buildings:
            # Preserve synthetic/legacy snapshots that predate town metadata.
            return 0 if 0 in self._town_maps else -1
        scored: list[tuple[int, int]] = []
        for town_id, town_map in self._town_maps.items():
            matches = sum(
                town_map.building_position(building_type) == position
                for building_type, position in observed_buildings.items()
            )
            if matches:
                scored.append((matches, town_id))
        if not scored:
            return 0 if 0 in self._town_maps else -1
        best_score = max(score for score, _town_id in scored)
        winners = [town_id for score, town_id in scored if score == best_score]
        return winners[0] if len(winners) == 1 else -1

    def _town_map_active(self, snapshot: Snapshot) -> bool:
        # The static Outpost layout is loaded AND matches this surface floor,
        # so the whole fixed town is effectively known (walls included).
        # Legacy/synthetic snapshots use -1 for an unknown town id; preserve
        # the historical single-map Outpost behavior for them.  Real new
        # snapshots select strictly by the emitter's town id.
        town_id = self._effective_town_id(snapshot)
        selected = self._town_maps.get(town_id)
        if selected is not None:
            self._town_map = selected
        return (
            selected is not None
            and snapshot.in_town
            and (snapshot.width or max((p.x for p in snapshot.grids), default=-1) + 1)
            == selected.width
            and (snapshot.height or max((p.y for p in snapshot.grids), default=-1) + 1)
            == selected.height
        )

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

    def _on_town_border(self, snapshot: Snapshot, pos: Position) -> bool:
        # A town is a fixed walled map; its passable border tiles are the roads
        # that lead OFF this tile into the adjacent open wilderness. Stepping onto
        # one leaves the safe town (a clvl-4 bot wandered out this way and a
        # Cyclops killed it), so town wandering must shun the outer ring.
        if not snapshot.in_town:
            return False
        if snapshot is self._map_predicate_snapshot:
            if pos in self._town_border_cache:
                return self._town_border_cache[pos]
        result = bool(
            snapshot.width > 0
            and snapshot.height > 0
            and (
            pos.y == 0
            or pos.x == 0
            or pos.y == snapshot.height - 1
            or pos.x == snapshot.width - 1
            )
        )
        if snapshot is self._map_predicate_snapshot:
            self._town_border_cache[pos] = result
        return result

    def _least_visited_neighbor(self, snapshot: Snapshot) -> Position | None:
        candidates = [
            candidate
            for candidate in self._walkable_neighbors(
                snapshot, snapshot.player.position
            )
            if candidate not in self._engagement_avoid_cells
        ]
        if not candidates:
            return None
        previous = self._recent[-2] if len(self._recent) >= 2 else None

        def score(pos: Position) -> tuple[int, int, int]:
            # In town, never wander onto the border ring (it exits into the open
            # wilderness); then prefer least-visited and avoid bouncing straight
            # back. The border penalty is first, so an edge tile is chosen only if
            # every neighbour is an edge (which cannot happen in the interior).
            border = 1 if self._on_town_border(snapshot, pos) else 0
            return (border, self._visit_counts[pos], 1 if pos == previous else 0)

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

    def _refresh_warning_avoidance(self, snapshot: Snapshot) -> None:
        """Keep warning-refused grids at lethal-danger navigation weight.

        Injected into (or withdrawn from) the shared avoid set once per
        decision so every BFS — loot, exploration, flee, hunt, stairs —
        prices them identically to a lethal-danger cell.  While supplies
        remain, a destination only reachable through one is simply
        unreachable by walking and the existing danger/escape machinery owns
        the situation; only the entirely-exhausted ledger withdraws the
        avoidance so the user-sanctioned forced walk can route through."""
        cells = self._warning_refused_cells
        if not cells:
            return
        if self._warning_supplies_exhausted(snapshot):
            # Withdraw ONLY the warning owner's contribution: a coordinate the
            # engagement/status-threat owner also claims stays avoided — the
            # forced-walk permission must never erase another owner's
            # lethal-danger weight.
            self._engagement_avoid_cells -= (
                cells - self._engagement_owned_avoid_cells
            )
        else:
            self._engagement_avoid_cells |= cells
            if any(step in cells for step in self._explore_path):
                # A committed exploration path replays without re-planning;
                # drop it rather than march the tail back into the grid.
                self._clear_explore_path(ExplorationPathOutcome.INVALIDATE)

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
          the grid and post 'n'.  At the ordinary original-keyset command
          loop 'n' has no keymap (pref-key.prf maps n/y only for the
          roguelike keyset) and falls into the illegal-command default —
          bounded and non-acting, while still being the correct answer in
          the rare case a prompt is genuinely pending.  Never a movement
          key chosen for another purpose.
        * player standing on the walk's target — the crossing happened.  If
          it was the sanctioned forced walk, the message is just its
          record.  Otherwise a composed tail answered the prompt the caller
          never anticipated: latch the grid so the unsanctioned crossing
          happens at most once per floor, and let the decision continue.
        """
        if not any(
            home_page_message_body(message).startswith(
                WARNING_PROMPT_MESSAGE_PREFIXES
            )
            for message in snapshot.messages
        ):
            return None
        pending = self._warning_step_pending
        self._warning_step_pending = None
        if pending is not None:
            sequence, floor_key, origin, target, sanctioned = pending
            attributable = (
                sequence == self._decision_sequence - 1
                and floor_key == snapshot.floor_key
            )
            if attributable and snapshot.player.position == target:
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
        if snapshot.store is not None:
            # The prompt was decided before this store screen opened; store
            # command sets give n/y real meanings, so post nothing here.
            return None
        self.last_reason = "warning:refuse"
        return "n"


    def _direction_key(self, origin: Position, target: Position) -> str:
        dy = max(-1, min(1, target.y - origin.y))
        dx = max(-1, min(1, target.x - origin.x))
        return DIRECTION_KEYS[(dy, dx)]



# Backwards-compatible alias for existing callers.
ConservativePolicy = HengbotPolicy
