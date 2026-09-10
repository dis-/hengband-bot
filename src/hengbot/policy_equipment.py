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
)
from hengbot.policy_constants import (
    AMMO_CARRY_STACK_LIMIT,
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
    UNIQUE_COMBAT_HP_RESERVE_RATIO,
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


class EquipmentMixin:
    def _equipment_transaction_owns_town_relocation(
        self, snapshot: Snapshot
    ) -> bool:
        """Whether this decision began with equipment locomotion ownership."""
        return bool(
            snapshot.in_town
            and (
                getattr(self, "_decision_context", None) is not None
                and self._decision_context.equipment_transaction_owned
            )
        )

    def _equipment_ownership_release_due(self, snapshot: Snapshot) -> None:
        """Release transaction ownership freshly satisfied by worn observations."""
        equipped = {
            (equipment_identity(item), item.slot) for item in snapshot.equipment
        }
        self._equipment_transaction_owned_items = [
            owned
            for owned in self._equipment_transaction_owned_items
            if owned not in equipped
        ]

    @staticmethod
    def _launcher_average_damage(item: InventoryItem | StoreItem | None) -> float:
        if item is None or item.sval not in LAUNCHER_PROPERTIES:
            return 0.0
        ammo_tval, _energy, multiplier = LAUNCHER_PROPERTIES[item.sval]
        return max(
            0.0,
            (STORE_AMMO_AVERAGE_DAMAGE[ammo_tval] + item.to_d) * multiplier,
        )

    def _equipment_optimization_depth(self, snapshot: Snapshot) -> int:
        """Return the depth classified from the optimized owned loadout."""
        return self._equipment_optimization_last_depth or 19

    def _withdrawable_digging_tool_count(self, snapshot: Snapshot) -> int:
        count = self._digging_tool_count(snapshot) + sum(
            owned.item.count
            for owned in self._equipment_catalog.items
            if owned.origin == "home" and owned.item.is_digging_tool
            and self._item_signature(owned.item) not in self._deferred_home_items
        )
        if (
            self._store_buy_inflight is not None
            and self._store_buy_inflight[1][1] == TVAL_DIGGING
        ):
            count += 1
        return count

    def _queue_standing_home_digger(self, snapshot: Snapshot) -> str | None:
        """Bind Home stock needed by the standing two-digger carry target."""
        store = snapshot.store
        if (
            store is None
            or store.store_type != STORE_HOME
            or self._digging_tool_count(snapshot) >= 2
        ):
            return None
        digger = max(
            (
                item
                for item in store.items
                if item.is_digging_tool
                and self._item_signature(item) not in self._deferred_home_items
            ),
            key=lambda item: item.sval,
            default=None,
        )
        if digger is None:
            return None
        self._home_digger_seen_pages.clear()
        self._home_pending_item = self._item_signature(digger)
        self._home_digger_withdraw_pending = True
        self._home_withdrawal_queued = True
        self.last_reason = "home:queue-digging-tool-withdraw"
        return LEAVE_STORE_KEY

    @staticmethod
    def _equipment_exclusion_telemetry(
        catalog: tuple,
        reasons_by_id: dict[str, list[str]],
    ) -> dict[str, object]:
        """Bounded, human-readable diagnostics for a search exclusion set."""
        display_cap = 25
        by_id = {item.id: item for item in catalog}
        details = [
            {
                "id": item_id,
                "name": getattr(by_id[item_id].item, "name", ""),
                "identity": equipment_identity(by_id[item_id].item),
                "reasons": reasons_by_id[item_id],
            }
            for item_id in sorted(reasons_by_id)
            if item_id in by_id
        ]
        return {
            "total": len(details),
            "display_cap": display_cap,
            "truncated": len(details) > display_cap,
            "items": details[:display_cap],
        }

    @staticmethod
    def _equipment_slot_candidate_counts(
        catalog: tuple, excluded_ids: frozenset[str]
    ) -> dict[str, int]:
        """Count candidates that enter enumeration, before its pruning steps."""
        counts: Counter[str] = Counter({
            slot: 0
            for slot in (
                *FIXED_SLOTS,
                SLOT_MAIN_HAND,
                SLOT_SUB_HAND,
                SLOT_MAIN_RING,
                SLOT_SUB_RING,
            )
        })
        for owned in catalog:
            if not owned.exploration_legal or owned.id in excluded_ids:
                continue
            item = owned.item
            slot = slot_for(item)
            if slot is not None:
                counts[slot] += 1
            elif item.tval in {21, 22, 23}:
                counts[SLOT_MAIN_HAND] += 1
                counts[SLOT_SUB_HAND] += 1
            elif item.tval == 34:
                counts[SLOT_SUB_HAND] += 1
            elif item.tval == 45:
                counts[SLOT_MAIN_RING] += 1
                counts[SLOT_SUB_RING] += 1
        return dict(sorted(counts.items()))

    def _prepare_equipment_optimization(
        self, snapshot: Snapshot, *, depth_override: int | None = None
    ) -> WarriorOptimizationPreparation | None:
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR or not snapshot.in_town:
            self._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ] = "stale-republished"
            return None
        if (
            self._equipment_transaction_session is not None
            and not self._equipment_transaction_session.complete
        ):
            self._equipment_optimization_telemetry["result_source"] = (
                "in-flight-session-return"
            )
            self._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ] = "current-inputs"
            return self._equipment_optimization_preparation
        # P1: the search consumes only calibrated worn-independent character
        # constants.  Without a valid calibration the optimizer fails closed;
        # the town execution layer owns running the calibration phase — the
        # selector itself never triggers it.
        calibration = self._validated_character_calibration(snapshot)
        if calibration is None:
            self._equipment_optimization_telemetry = {
                "result_source": "calibration-required-return",
                "search_telemetry_freshness": "current-inputs",
            }
            self._equipment_optimization_search_surviving_ids = frozenset()
            preparation = WarriorOptimizationPreparation(
                current_loadout(self._equipment_catalog.items),
                None,
                None,
                ("calibration-required",),
            )
            self._equipment_optimization_signature = None
            self._equipment_optimization_preparation = preparation
            return preparation
        live_current = current_loadout(self._equipment_catalog.items)
        retired_worn_item_ids = getattr(
            self, "_equipment_retired_worn_item_ids", frozenset()
        )
        if (
            retired_worn_item_ids
            and live_current.item_ids == retired_worn_item_ids
        ):
            prior = self._equipment_optimization_preparation
            result = getattr(prior, "result", None)
            best = getattr(result, "best", None)
            if best is not None and isinstance(
                getattr(best, "loadout", None), Loadout
            ):
                result = replace(result, best=replace(best, loadout=live_current))
                preparation = WarriorOptimizationPreparation(
                    live_current,
                    result,
                    EquipmentTransactionPlan((), (), 0),
                    (),
                )
                self._equipment_optimization_preparation = preparation
                self._equipment_optimization_signature = None
                self._set_equipment_transaction_session(None)
                return preparation
        optimization_depth = depth_override
        operational_catalog = tuple(
            item
            for item in self._equipment_catalog.items
            if operational_equipment_candidate(item)
        )
        eligible_catalog = tuple(
            item
            for item in operational_catalog
            if not (
                item.origin == "home"
                and self._item_signature(item.item) in self._deferred_home_items
            )
        )
        # A failed transaction remains quarantined for this town visit unless it
        # has become every owned source of a mandatory equipment flag.  Keeping
        # that last source suppressed would make departure (which clears the
        # visit quarantine) impossible, so release the failed sources of the
        # missing flag and let the normal transaction machinery make progress.
        # A release is a SECOND CHANCE: an id quarantined again after being
        # released is burned and never released again this visit, so the
        # candidate set shrinks monotonically instead of cycling.
        required_flags = {
            RESIST_FLAG_BY_ABILITY[ability]
            for ability in (
                required_depth_gates(optimization_depth)
                if optimization_depth is not None else ()
            )
            if ability in RESIST_FLAG_BY_ABILITY
        }
        released_failed_ids: set[str] = set()
        for required_flag in required_flags:
            if any(
                required_flag in item.flags
                and not self._equipment_memory_contains(
                    self._equipment_transaction_failed_items, item
                )
                for item in eligible_catalog
            ):
                continue
            released_failed_ids.update(
                item.id
                for item in eligible_catalog
                if required_flag in item.flags
                and self._equipment_memory_contains(
                    self._equipment_transaction_failed_items, item
                )
                and not self._equipment_memory_contains(
                    self._equipment_quarantine_burned_ids, item
                )
            )
        if released_failed_ids:
            for item in eligible_catalog:
                if item.id in released_failed_ids:
                    keys = self._equipment_memory_keys(item)
                    self._equipment_transaction_failed_items.difference_update(keys)
                    self._equipment_quarantine_second_chance_ids.update(keys)
        catalog = tuple(
            item
            for item in eligible_catalog
            if not self._equipment_memory_contains(
                self._equipment_transaction_failed_items, item
            )
        )
        # INVARIANT: no quarantine (a stall-failed item id, a deferred Home
        # signature, or both at once) may remove the LAST owned source of a
        # flag this optimization depth requires while an untried source
        # remains.  The 2026-08-02 20:06 stop proved the release valve above
        # cannot see an item the deferred filter already removed from
        # eligible_catalog: quarantining the only resist_chaos source produced
        # no-valid-loadout at depth 31 with no bot-reachable exit.  Readmit
        # ONE such source per missing flag to the optimizer's VIEW without
        # mutating either quarantine set — never the whole hidden equivalence
        # class, so a stall of the readmitted item burns it (see
        # _abandon_blocked_equipment_transaction) and the next pass advances
        # to a different source instead of repeating the same failed
        # withdrawal.  When every source has been burned the state is an
        # honest no-valid-loadout and the pre-existing depth fallback and
        # town-ledger exits own it.
        catalog_ids = {item.id for item in catalog}
        readmitted_ids: set[str] = set()
        for required_flag in required_flags:
            if any(required_flag in item.flags for item in catalog):
                continue
            candidates = sorted(
                item.id
                for item in operational_catalog
                if required_flag in item.flags
                and item.id not in catalog_ids
                and not self._equipment_memory_contains(
                    self._equipment_quarantine_burned_ids, item
                )
            )
            if candidates:
                readmitted_ids.add(candidates[0])
        if readmitted_ids:
            catalog += tuple(
                item
                for item in operational_catalog
                if item.id in readmitted_ids
            )
            for item in operational_catalog:
                if item.id in readmitted_ids:
                    self._equipment_quarantine_second_chance_ids.update(
                        self._equipment_memory_keys(item)
                    )
        self._equipment_quarantine_readmitted_ids = tuple(sorted(readmitted_ids))
        if optimization_depth is None:
            # Quarantine and deferred-routing state govern whether a selected
            # target can be applied; they must never choose a different target.
            catalog = operational_catalog
            self._equipment_quarantine_readmitted_ids = ()
        cached_blockers = getattr(
            self._equipment_optimization_preparation, "blockers", ()
        )
        has_destruction = self._has_destruction_method(snapshot)
        quest_strategy = (
            self._carry_procurement_strategy(snapshot)
            or self._quest_strategy_for_errand_or_floor(snapshot)
        )
        quest_force = getattr(quest_strategy, "required_force", {})
        required_launcher_ammo = (
            self._quest_launcher_ammo(snapshot, quest_force)
            if isinstance(quest_force, dict)
            else None
        )
        required_launcher_available = (
            not self._quest_uses_selected_launcher(quest_force)
            and
            required_launcher_ammo is not None
            and any(
                item.item.tval == TVAL_BOW
                and item.item.ammo_tval == required_launcher_ammo
                for item in catalog
            )
        )
        optimization_depth = max(1, depth_override) if depth_override is not None else None
        # Keep pack weapons that the ordinary town policy has already classified
        # as sale loot out of the optimizer's Home staging deposits.  Otherwise
        # the optimizer stores them, Home processing immediately withdraws them
        # for the Weapon Smith, and the next optimization stores them again.
        # This produced a live deposit/withdraw carousel without changing gold.
        restoration_owned = set(self._equipment_transaction_owned_items)
        preserve = frozenset(
            item.id
            for item in catalog
            if (
                item.origin == "equipped"
                and item.equipped_slot is not None
                and (equipment_identity(item.item), item.equipped_slot)
                in restoration_owned
            )
            or (
                item.origin == "pack"
                and (
                self._identification_flow_owns(item.item)
                # Abandonment quarantines the failed physical action for this
                # town visit.  Deposits are not target-loadout members, so the
                # selector's failed-target check cannot suppress a stale
                # deposit by itself.  Preserve that pack item explicitly or a
                # fresh plan recreates the same deposit immediately after the
                # old session releases ownership.
                or self._equipment_memory_contains(
                    self._equipment_transaction_failed_items, item
                )
                or self._retention_reservation(snapshot, item.item) > 0
                or (
                    item.item.is_digging_tool
                    and (
                        self._fundraising_mode in {"prepare", "mine", "scavenge"}
                        or not self._is_surplus_digging_tool(snapshot, item.item)
                    )
                )
                or (
                    self._equipped_weapon_high_grade(snapshot)
                    and self._weapon_is_inferior(item.item)
                )
                )
            )
        )
        # Quest replenishment is a pack-supply count target, not equipment
        # search input. Lit throwing torches happen to have an equipment tval;
        # exclude their reserved physical stacks from loadout candidacy while
        # retaining them in the catalog for transaction preservation.
        search_excluded = frozenset(
            item.id
            for item in catalog
            if (
                item.origin == "pack"
                and item.item.is_torch
                and self._retention_reservation(snapshot, item.item) > 0
            )
            or (
                required_launcher_available
                and item.item.tval == TVAL_BOW
                and item.item.ammo_tval != required_launcher_ammo
            )
        )
        if optimization_depth is None:
            # Supply/quest reservations are expedition plans, not owned-loadout
            # quality. They may preserve an item during planning but cannot
            # remove it from target selection.
            search_excluded = frozenset()
        search_catalog = tuple(
            replace(item, random_teleport_suppressed=True)
            if (
                item.evaluable
                and not item.item.fully_known
                and item_requires_full_identification(item.item)
            )
            else item
            for item in catalog
        )
        identification_exempt = frozenset(
            item.id
            for item in search_catalog
            if self._item_signature(item.item)
            in self._town_unidentifiable_carried_sigs
        )
        # The selector memo is the owned equipment multiset plus knowledge
        # completeness. Origin and worn slot are transport state, so strip them
        # from the normal projection; gold, pack occupancy, recall progress and
        # town intent never enter this key.
        signature = (
            tuple(sorted(
                (
                    (projection[0], *projection[3:])
                    for item in search_catalog
                    for projection in (optimizer_item_projection(item),)
                ),
                key=lambda projection: projection[0],
            )),
            tuple(sorted(identification_exempt)),
            self._equipment_catalog.home_scan_complete,
            # Worn state is an optimizer input even though moving an item
            # between equipment and pack does not change the owned multiset.
            # Keep it explicit instead of depending on origin-bearing catalogue
            # ids as an accidental cache invalidator.
            tuple(sorted(
                (item.slot, equipment_identity(item))
                for item in snapshot.equipment
                if item.is_equipment and item.tval not in AMMUNITION_TVALS
            )),
        )
        if (
            signature == self._equipment_optimization_signature
            and self._equipment_optimization_pack_items == len(snapshot.inventory)
        ):
            cached_best = getattr(
                getattr(self._equipment_optimization_preparation, "result", None),
                "best",
                None,
            )
            if (
                isinstance(getattr(cached_best, "loadout", None), Loadout)
                and isinstance(
                    getattr(getattr(cached_best, "metrics", None), "speed_bonus", None),
                    int,
                )
            ):
                cached_result = self._equipment_optimization_preparation.result
                self._equipment_optimization_last_depth = (
                    getattr(cached_result, "chosen_depth", None)
                    if getattr(cached_result, "chosen_depth", None) is not None
                    else self._effective_divable_depth(
                        snapshot,
                        cached_best.loadout,
                        calibration,
                        has_destruction=has_destruction,
                        speed_bonus=cached_best.metrics.speed_bonus,
                    )
                )
            self._equipment_optimization_telemetry["result_source"] = (
                "signature-cache-hit"
            )
            self._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ] = "current-inputs"
            return self._equipment_optimization_preparation
        if (
            depth_override is None
            and self._equipment_optimization_timed_out_this_visit
            and self._equipment_optimization_preparation is not None
            and isinstance(cached_blockers, (tuple, list, set, frozenset))
            and "optimization-timeout" in cached_blockers
        ):
            # The fast semantic signature changed, so the previous input key is
            # not evidence about this state. Avoid repeating the bounded search
            # but fail closed rather than re-publishing a stale key.
            self._equipment_optimizer_input_key = None
            self._equipment_optimization_telemetry["result_source"] = (
                "town-visit-timeout-return"
            )
            self._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ] = "stale-republished"
            return self._equipment_optimization_preparation
        if signature == self._equipment_optimization_signature:
            self._equipment_optimization_telemetry["result_source"] = (
                "signature-cache-hit"
            )
            self._equipment_optimization_telemetry[
                "search_telemetry_freshness"
            ] = "current-inputs"
            preparation = self._equipment_optimization_preparation
            if (
                preparation is not None
                and self._equipment_optimization_pack_items != len(snapshot.inventory)
                and preparation.result is not None
                and preparation.result.best is not None
                and preparation.transaction is not None
            ):
                transaction = plan_equipment_transactions(
                    catalog,
                    preparation.current,
                    preparation.result.best.loadout,
                    current_pack_items=len(snapshot.inventory),
                    home_scan_complete=self._equipment_catalog.home_scan_complete,
                    preserve_pack_item_ids=preserve,
                    retain_item_identities=self._transaction_retain_identities(
                        snapshot,
                        preparation.current,
                        preparation.result.best.loadout,
                    ),
                )
                preparation = replace(
                    preparation,
                    transaction=transaction,
                    blockers=transaction.blockers,
                )
                self._equipment_optimization_preparation = preparation
                self._set_equipment_transaction_session(
                    self._equipment_transaction_session_for_preparation(preparation)
                )
            self._equipment_optimization_pack_items = len(snapshot.inventory)
            if self._equipment_optimizer_knowledge_key is None:
                self._equipment_optimizer_knowledge_key = (
                    warrior_optimizer_knowledge_key(self._monrace_knowledge)
                )
            self._equipment_optimizer_input_key = warrior_optimizer_input_key(
                snapshot,
                search_catalog,
                self._monrace_knowledge,
                depth=optimization_depth,
                home_scan_complete=self._equipment_catalog.home_scan_complete,
                has_destruction=has_destruction,
                preserve_pack_item_ids=preserve,
                search_excluded_item_ids=search_excluded,
                identification_exempt_item_ids=identification_exempt,
                calibration=calibration,
                knowledge_key=self._equipment_optimizer_knowledge_key,
            )
            return self._equipment_optimization_preparation
        if self._equipment_optimizer_knowledge_key is None:
            self._equipment_optimizer_knowledge_key = warrior_optimizer_knowledge_key(
                self._monrace_knowledge
            )
        self._equipment_optimizer_input_key = warrior_optimizer_input_key(
            snapshot,
            search_catalog,
            self._monrace_knowledge,
            depth=optimization_depth,
            home_scan_complete=self._equipment_catalog.home_scan_complete,
            has_destruction=has_destruction,
            preserve_pack_item_ids=preserve,
            search_excluded_item_ids=search_excluded,
            identification_exempt_item_ids=identification_exempt,
            calibration=calibration,
            knowledge_key=self._equipment_optimizer_knowledge_key,
        )
        preserve_reasons: dict[str, list[str]] = {}
        search_excluded_reasons: dict[str, list[str]] = {}
        for owned in catalog:
            if owned.id in preserve:
                reasons: list[str] = []
                if self._identification_flow_owns(owned.item):
                    reasons.append("identification-flow")
                if self._retention_reservation(snapshot, owned.item) > 0:
                    reasons.append("retention-reservation")
                if (
                    owned.item.is_digging_tool
                    and self._fundraising_mode in {"prepare", "mine", "scavenge"}
                ):
                    reasons.append("digging-tool-in-fundraising")
                if (
                    self._equipped_weapon_high_grade(snapshot)
                    and self._weapon_is_inferior(owned.item)
                ):
                    reasons.append("inferior-weapon")
                preserve_reasons[owned.id] = reasons
            if owned.id in search_excluded:
                reasons = []
                if (
                    owned.origin == "pack"
                    and owned.item.is_torch
                    and self._retention_reservation(snapshot, owned.item) > 0
                ):
                    reasons.append("torch-retention-reservation")
                if (
                    required_launcher_available
                    and owned.item.tval == TVAL_BOW
                    and owned.item.ammo_tval != required_launcher_ammo
                ):
                    reasons.append("launcher-ammo-mismatch")
                search_excluded_reasons[owned.id] = reasons
        self._equipment_optimization_telemetry = {
            "result_source": "fresh-search",
            "search_telemetry_freshness": "current-inputs",
            "search_catalog_items": len(search_catalog),
            "search_catalog_origins": {
                origin: sum(item.origin == origin for item in search_catalog)
                for origin in ("equipped", "pack", "home")
            },
            "preserve_pack_items": self._equipment_exclusion_telemetry(
                catalog, preserve_reasons
            ),
            "search_excluded_items": self._equipment_exclusion_telemetry(
                catalog, search_excluded_reasons
            ),
            "search_slot_candidate_counts": self._equipment_slot_candidate_counts(
                search_catalog, search_excluded
            ),
        }
        self._equipment_optimization_search_surviving_ids = frozenset(
            item.id
            for item in search_catalog
            if item.exploration_legal and item.id not in search_excluded
        )
        # Score safe partial-ID candidates as they will exist after `{.}` is
        # applied. If one wins, the pending blocker below prevents transaction
        # creation until the town suppression step has changed the real item.
        preparation = prepare_warrior_optimization(
            snapshot,
            search_catalog,
            self._monrace_knowledge,
            depth=optimization_depth,
            home_scan_complete=self._equipment_catalog.home_scan_complete,
            # The AGENTS.md 50F+ gate: an identified *Destruction* scroll or a
            # charged staff in the pack (same detection as the descent gate).
            # A hard-coded False here rejected EVERY 50F+ loadout and blocked
            # departure even when the character already carried the scroll.
            has_destruction=has_destruction,
            preserve_pack_item_ids=preserve,
            search_excluded_item_ids=search_excluded,
            identification_exempt_item_ids=identification_exempt,
            loadout_report_path=self._loadout_report_path,
            evaluator_cache=self._warrior_evaluator_cache,
            calibration=calibration,
        )
        result = getattr(preparation, "result", None)
        if result is not None:
            # Observation-only mirror of warrior_optimization's search-factory
            # selection.  A coupling test patches the real factories and pins
            # these names to the factory that was actually called.
            incremental_search = (
                len(search_catalog) >= INCREMENTAL_SEARCH_CATALOG_THRESHOLD
            )
            search_seed_loadout = current_loadout(search_catalog)
            band_decisions = getattr(result, "band_decisions", ())
            if not isinstance(band_decisions, (tuple, list)):
                band_decisions = ()
            chosen_depth = getattr(result, "chosen_depth", None)
            if not isinstance(chosen_depth, int):
                chosen_depth = None
            self._equipment_optimization_telemetry.update({
                "search_strategy": (
                    "enumerate_single_slot_variants"
                    if incremental_search
                    else "enumerate_warrior_loadouts"
                ),
                "search_catalog_threshold": INCREMENTAL_SEARCH_CATALOG_THRESHOLD,
                "search_catalog_threshold_crossed": incremental_search,
                "search_seed": "current-loadout" if incremental_search else "catalog",
                "current_loadout_slots": len(search_seed_loadout.slots),
                "current_loadout_empty": not search_seed_loadout.slots,
                "band_descent": [
                    {
                        "band": decision.band,
                        "satisfying_set_existed": decision.satisfying_set_existed,
                        "melee": decision.melee,
                        "melee_free": decision.melee_free,
                        "refusal_reason": decision.refusal_reason,
                        "ratio": decision.ratio,
                    }
                    for decision in band_decisions
                ],
                "chosen_band": chosen_depth,
                "chosen_ratio": (
                    result.chosen_decision.ratio
                    if getattr(result, "chosen_decision", None) is not None
                    else None
                ),
            })
        best = getattr(result, "best", None)
        if (
            best is not None
            and isinstance(getattr(best, "loadout", None), Loadout)
            and isinstance(getattr(getattr(best, "metrics", None), "speed_bonus", None), int)
        ):
            self._equipment_optimization_last_depth = (
                chosen_depth
                if chosen_depth is not None
                else self._effective_divable_depth(
                    snapshot,
                    best.loadout,
                    calibration,
                    has_destruction=has_destruction,
                    speed_bonus=best.metrics.speed_bonus,
                )
            )
        loadout = getattr(best, "loadout", None)
        selected_ids = getattr(loadout, "item_ids", frozenset())
        if not isinstance(selected_ids, (set, frozenset)):
            selected_ids = frozenset()
        selected_ids = frozenset(selected_ids)
        if (
            isinstance(loadout, Loadout)
            and isinstance(preparation.current, Loadout)
            and preparation.transaction is not None
        ):
            transaction = plan_equipment_transactions(
                catalog,
                preparation.current,
                loadout,
                current_pack_items=len(snapshot.inventory),
                home_scan_complete=self._equipment_catalog.home_scan_complete,
                preserve_pack_item_ids=preserve,
                retain_item_identities=self._transaction_retain_identities(
                    snapshot, preparation.current, loadout
                ),
            )
            preparation = replace(
                preparation, transaction=transaction, blockers=transaction.blockers
            )
        if any(
            item.id in selected_ids
            and not item.item.fully_known
            and item_requires_full_identification(item.item)
            and self._needs_random_teleport_suppression(item, selected_ids)
            for item in catalog
        ):
            preparation = replace(
                preparation,
                transaction=None,
                blockers=("pending-random-teleport-suppression",),
            )
        elif any(
            item.id in selected_ids
            and self._equipment_memory_contains(
                self._equipment_transaction_failed_items, item
            )
            for item in catalog
        ):
            preparation = replace(
                preparation,
                transaction=None,
                blockers=("equipment-transaction-failed",),
            )
        self._equipment_optimization_signature = signature
        self._equipment_optimization_pack_items = len(snapshot.inventory)
        self._equipment_optimization_preparation = preparation
        preparation_blockers = getattr(preparation, "blockers", ())
        if (
            depth_override is None
            and
            isinstance(preparation_blockers, (tuple, list, set, frozenset))
            and "optimization-timeout" in preparation_blockers
        ):
            self._equipment_optimization_timed_out_this_visit = True
        self._set_equipment_transaction_session(
            self._equipment_transaction_session_for_preparation(preparation)
        )
        previous_target_ids = self._equipment_fresh_search_target_ids
        current_target_ids = frozenset(selected_ids)
        session = self._equipment_transaction_session
        self._equipment_optimization_telemetry["fresh_search_transition"] = {
            "target_loadout_id": (
                session.target_loadout_id if session is not None else None
            ),
            "item_ids": sorted(current_target_ids)[:10],
            "added_ids": sorted(current_target_ids - previous_target_ids)[:10],
            "removed_ids": sorted(previous_target_ids - current_target_ids)[:10],
            "trigger_reason": self.last_reason,
        }
        self._equipment_fresh_search_target_ids = current_target_ids
        return preparation

    @staticmethod
    def _equipment_transaction_session_for_preparation(
        preparation: WarriorOptimizationPreparation,
    ) -> EquipmentTransactionSession | None:
        """Create a full session, or a deposit-only session that frees pack space."""
        transaction = preparation.transaction
        if not isinstance(transaction, EquipmentTransactionPlan) or not transaction.actions:
            return None
        plan = transaction
        if not preparation.ready:
            blockers = tuple(preparation.blockers)
            if not blockers or not all(
                blocker.startswith("pack-space-required:") for blocker in blockers
            ):
                return None
            deposits = tuple(
                action
                for action in transaction.actions
                if action.phase == PHASE_HOME_PREPARE and action.kind == "deposit"
            )
            if not deposits:
                return None
            # The complete swap may still need temporary slots, but these first
            # actions only remove carried equipment.  Execute them independently;
            # their confirmed inventory delta invalidates and rebuilds the plan.
            plan = EquipmentTransactionPlan(
                deposits,
                (),
                max(0, transaction.peak_pack_items - len(deposits)),
            )
        return EquipmentTransactionSession(
            plan,
            max_unconfirmed_observations=EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
        )

    @staticmethod
    def _equipment_memory_keys(item: OwnedEquipment) -> frozenset[str]:
        """Keys for visit-scoped memory across pack/equipped origin changes."""
        return frozenset((
            item.id,
            f"identity:{equipment_identity(item.item)}",
        ))

    @staticmethod
    def _equipment_action_memory_keys(
        action: EquipmentTransaction,
    ) -> frozenset[str]:
        keys = {action.item_id}
        if action.item_identity:
            keys.add(f"identity:{action.item_identity}")
        return frozenset(keys)

    def _equipment_memory_contains(
        self, memory: set[str], item: OwnedEquipment
    ) -> bool:
        return not memory.isdisjoint(self._equipment_memory_keys(item))

    def _prepare_equipment_transaction_command(
        self,
        session: EquipmentTransactionSession,
        action: EquipmentTransaction,
        observation: EquipmentTransactionObservation,
        key: str,
        context_identity: tuple[object, ...],
    ) -> bool:
        if not session.prepare(
            action, observation, key, context_identity
        ):
            return False
        self._equipment_transaction_prepared_key = key
        return True

    def _abandon_blocked_equipment_transaction(
        self, snapshot: Snapshot | None = None
    ) -> None:
        session = self._equipment_transaction_session
        if self._store_visit is not None:
            target_store_type = (
                STORE_HOME
                if session is not None and session.required_context == "home"
                else self._store_visit.store_type
            )
            if self._store_visit.store_type != target_store_type:
                self._close_store_visit("equipment-transaction-foreign-visit")
            else:
                self._store_visit.outcome = "abandoned-with-restore"
        action = (
            None
            if session is None
            else session.pending_action or session.current_action
        )
        route_blocked = bool(
            action is not None
            and "home-route-unavailable" in getattr(session, "blockers", ())
        )
        owner_retired = bool(
            action is not None
            and "town-owner-retired" in getattr(session, "blockers", ())
        )
        if not route_blocked:
            # A non-route abandonment disproves the pending assertion that an
            # identical Home route failed twice without an observed change.
            self._equipment_transaction_route_terminal_pending = False
        if route_blocked and session is not None and snapshot is not None:
            route_abandonment = (
                session.target_loadout_id,
                "home-route-unavailable",
                (
                    snapshot.floor_key,
                    None if snapshot.store is None else snapshot.store.store_type,
                    snapshot.player.gold,
                    tuple(sorted(
                        (equipment_identity(item), item.count, item.slot)
                        for item in snapshot.inventory
                    )),
                    tuple(sorted(
                        (item.slot, equipment_identity(item))
                        for item in snapshot.equipment
                    )),
                ),
            )
            if route_abandonment == self._equipment_transaction_route_abandonment:
                self._equipment_transaction_route_terminal_pending = True
            else:
                self._equipment_transaction_route_abandonment = route_abandonment
                self._equipment_transaction_route_terminal_pending = False
        if action is not None:
            if route_blocked and snapshot is not None:
                # The ledger ceiling normally abandons an active Home session
                # when its last pass is charged.  This call is already inside
                # that abandonment seam, so hide the retiring session while
                # reporting to avoid recursively abandoning it.
                self._equipment_transaction_session = None
                try:
                    self._report_town_stop_pass(
                        snapshot, STORE_HOME, goal_satisfied=False
                    )
                finally:
                    self._equipment_transaction_session = session
            action_memory_keys = self._equipment_action_memory_keys(action)
            if not route_blocked and not owner_retired and not (
                action_memory_keys.isdisjoint(
                    self._equipment_quarantine_second_chance_ids
                )
            ):
                # The item already had its one release/readmission this visit
                # and its transaction failed again: consume the second chance.
                # Burned ids are excluded from both the release valve and the
                # last-source readmission, so every quarantine escape strictly
                # shrinks the remaining candidate set (monotonic exit).
                self._equipment_quarantine_burned_ids.update(action_memory_keys)
            if not route_blocked and not owner_retired:
                self._equipment_transaction_failed_items.update(action_memory_keys)
        self._discard_unposted_equipment_transaction_command()
        self._equipment_optimization_signature = None
        self._equipment_optimization_preparation = None
        self._town_blocked_reason = None
        if self._equipment_transaction_owned_items:
            # Restoration is reconstructed from physical observations every
            # time it is interrupted.  An old blocked session is evidence only
            # about that attempt; it must never latch restoration off while a
            # wearable owned item is still in the pack or known at Home.
            equipped = {
                (equipment_identity(item), item.slot)
                for item in (() if snapshot is None else snapshot.equipment)
            }
            self._equipment_transaction_owned_items = [
                owned
                for owned in self._equipment_transaction_owned_items
                if owned not in equipped
            ]
            pack_identities = {
                equipment_identity(item)
                for item in (() if snapshot is None else snapshot.inventory)
            }
            known_home_items = self._home_knowledge_items[
                :self._home_knowledge_valid_before
            ]
            home_identities = {
                equipment_identity(item) for item in known_home_items
            }
            restore_actions: list[EquipmentTransaction] = []
            missing: list[str] = []
            for identity, slot in self._equipment_transaction_owned_items:
                item_id = f"restore:{identity}"
                if identity in pack_identities or snapshot is None:
                    restore_actions.append(
                        EquipmentTransaction(
                            PHASE_EQUIP, "equip", item_id, slot, identity
                        )
                    )
                elif identity in home_identities:
                    restore_actions.extend((
                        EquipmentTransaction(
                            PHASE_HOME_PREPARE, "withdraw", item_id,
                            item_identity=identity,
                        ),
                        EquipmentTransaction(
                            PHASE_EQUIP, "equip", item_id, slot, identity
                        ),
                    ))
                else:
                    missing.append(identity)
            self._equipment_transaction_restore_remainder = tuple(missing)
            self._equipment_transaction_restore_terminal = None
            if not restore_actions:
                self._equipment_transaction_session = None
                if self._equipment_transaction_route_terminal_pending:
                    self._equipment_transaction_route_terminal_pending = False
                    self._equipment_transaction_route_terminal = (
                        "equipment-transaction:home-route-repeat-terminal"
                    )
                    self._town_visit_ledger.blocked_stores.add(STORE_HOME)
                if missing:
                    self._equipment_transaction_restore_terminal = (
                        "equipment-transaction:restore-blocked-terminal"
                    )
                return
            self._equipment_transaction_session = EquipmentTransactionSession(
                EquipmentTransactionPlan(tuple(restore_actions), (), 0),
                max_unconfirmed_observations=EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
            )
            self._equipment_transaction_restoring = True
            return
        self._equipment_transaction_session = None
        if self._equipment_transaction_route_terminal_pending:
            self._equipment_transaction_route_terminal_pending = False
            self._equipment_transaction_route_terminal = (
                "equipment-transaction:home-route-repeat-terminal"
            )
            self._town_visit_ledger.blocked_stores.add(STORE_HOME)

    def _equipment_transaction_owns_item(
        self, item: InventoryItem | StoreItem
    ) -> bool:
        """Return whether live transaction provenance protects this item."""
        identity = equipment_identity(item)
        return any(
            owned_identity == identity
            for owned_identity, _ in self._equipment_transaction_owned_items
        )

    def _equipment_transaction_town_owner_key(
        self, snapshot: Snapshot
    ) -> str | None:
        """Give a stripped transaction exclusive ownership of town decisions."""
        if not self._equipment_transaction_owned_items:
            return None
        if self._equipment_transaction_session is None:
            self._abandon_blocked_equipment_transaction(snapshot)
        if self._equipment_transaction_restore_terminal is not None:
            self.last_reason = self._equipment_transaction_restore_terminal
            return LEAVE_STORE_KEY if snapshot.store is not None else WAIT_KEY
        if snapshot.store is not None:
            if snapshot.store.store_type == STORE_HOME:
                key = self._equipment_transaction_home_key(snapshot)
                if key is not None:
                    return key
            self.last_reason = "equipment-transaction:owns-town-leave-store"
            return LEAVE_STORE_KEY
        key = self._equipment_transaction_town_key(snapshot)
        if key is not None:
            return key
        self._equipment_transaction_restore_terminal = (
            "equipment-transaction:restore-blocked-terminal"
        )
        self.last_reason = self._equipment_transaction_restore_terminal
        return WAIT_KEY

    def _equipment_transaction_home_key(self, snapshot: Snapshot) -> str | None:
        if self._release_stalled_equipment_transaction(snapshot):
            return LEAVE_STORE_KEY
        self._prepare_equipment_optimization(snapshot)
        session = self._equipment_transaction_session
        if session is None:
            return None
        if not session.executable:
            self._abandon_blocked_equipment_transaction(snapshot)
            self.last_reason = "equipment-transaction:abandon-blocked-home"
            return LEAVE_STORE_KEY
        if session.pending_action is not None:
            # The store command loop rejects the normal rest command ("5").
            # The dispatched transaction has already been processed by the time
            # this snapshot arrives, so leave Home and confirm it from town.
            self.last_reason = "equipment-transaction:await-confirmation-leave-home"
            return LEAVE_STORE_KEY
        if session.required_context == "outside_home":
            self.last_reason = "equipment-transaction:leave-home-to-equip"
            return LEAVE_STORE_KEY

        action = session.current_action
        store = snapshot.store
        if action is None or store is None or store.store_type != STORE_HOME:
            return None
        observation = observe_equipment_transactions(snapshot)
        if action.kind == "deposit":
            target = next(
                (
                    item
                    for item in snapshot.inventory
                    if item.is_equipment
                    and equipment_identity(item) == action.item_identity
                ),
                None,
            )
            if target is None:
                self._block_equipment_transaction(
                    f"deposit-item-missing:{action.item_id}"
                )
                self.last_reason = "equipment-transaction:deposit-missing"
                return LEAVE_STORE_KEY
            if self._retention_reservation(snapshot, target) > 0:
                # A transaction cached before a purchase or plan transition is
                # stale. Replan without ever dispatching its reserved deposit.
                self._abandon_blocked_equipment_transaction(snapshot)
                self.last_reason = "equipment-transaction:retain-reserved"
                return LEAVE_STORE_KEY
            if self._identification_flow_owns(target):
                # Identification owns this item until its hidden equipment
                # properties are known.  Discard the stale plan and let the
                # remaining Home handlers withdraw/identify it instead of
                # issuing the deposit that would restart the carousel.
                self._abandon_blocked_equipment_transaction(snapshot)
                self.last_reason = "equipment-transaction:defer-identification"
                return None
            if target.is_digging_tool and not self._is_surplus_digging_tool(
                snapshot, target
            ):
                # A plan computed before the fundraising withdrawal must not
                # put the newly acquired kit straight back on Home's shelf.
                self._abandon_blocked_equipment_transaction(snapshot)
                self.last_reason = "equipment-transaction:retain-digging-tool"
                return None
            main_hand = next(
                (item for item in snapshot.equipment if item.slot == "main_hand"),
                None,
            )
            if (
                target.is_melee_weapon
                and not target.is_digging_tool
                and (main_hand is None or main_hand.is_digging_tool)
            ):
                # The optimizer may shelve the combat weapon after the mining
                # tool has displaced it. Remember that identity before the Home
                # transaction so the re-arm pass retrieves the same weapon,
                # rather than blindly wielding the first pack weapon.
                self._normal_weapon_name = target.name
            key = SELL_KEY + target.slot + "\r"
            if not self._prepare_equipment_transaction_command(
                session,
                action,
                observation,
                key,
                (
                    "home", getattr(snapshot, "turn", 0), target.slot,
                    action.item_identity,
                ),
            ):
                self._block_equipment_transaction("deposit-dispatch-rejected")
                return LEAVE_STORE_KEY
            self.last_reason = "equipment-transaction:deposit"
            self._equipment_transaction_prepared_catalog_update = (
                "deposit",
                target,
                (
                    snapshot.turn,
                    target.slot,
                    self._item_signature(target),
                    target.count,
                    target.charges,
                    len(snapshot.inventory),
                ),
            )
            return key

        if action.kind == "withdraw":
            target_observed = any(
                item.is_equipment
                and equipment_identity(item) == action.item_identity
                for index, item in enumerate(self._home_knowledge_items)
                if index < self._home_knowledge_valid_before
            )
            if not target_observed:
                if (
                    self._open_home_page_is_complete(snapshot)
                    and any(
                        item.is_equipment
                        and equipment_identity(item) == action.item_identity
                        for item in snapshot.store.items
                    )
                ):
                    self._invalidate_home_observation()
                    self.last_reason = "equipment-transaction:await-fresh-knowledge"
                    return LEAVE_STORE_KEY
                self._block_equipment_transaction(
                    f"withdraw-item-missing:{action.item_id}"
                )
                self.last_reason = "equipment-transaction:withdraw-missing"
                return LEAVE_STORE_KEY
            if self._home_atomic_withdraw_pending is not None:
                self._equipment_atomic_withdraw_leave_count = 0
            if self._equipment_atomic_withdraw_leave_count >= 2:
                self._block_equipment_transaction("atomic-withdraw-unreachable")
                self.last_reason = "equipment-transaction:atomic-withdraw-unreachable"
                return LEAVE_STORE_KEY
            self._equipment_atomic_withdraw_leave_count += 1
            self.last_reason = "equipment-transaction:leave-for-atomic-withdraw"
            return LEAVE_STORE_KEY

        self._block_equipment_transaction(f"invalid-home-action:{action.kind}")
        return LEAVE_STORE_KEY

    def _equipment_transaction_town_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or snapshot.store is not None:
            return None
        if self._release_stalled_equipment_transaction(snapshot):
            return WAIT_KEY
        self._prepare_equipment_optimization(snapshot)
        session = self._equipment_transaction_session
        if session is None:
            return None
        if not session.executable:
            self._abandon_blocked_equipment_transaction(snapshot)
            self.last_reason = "equipment-transaction:abandon-blocked"
            return WAIT_KEY
        if session.pending_action is not None:
            self.last_reason = "equipment-transaction:await-confirmation"
            return WAIT_KEY
        if session.required_context == "home":
            if (
                self._store_visit is not None
                and self._store_visit.store_type != STORE_HOME
                and not self._store_visit.operation_posted
            ):
                # A foreign, non-progressing visit has no command to confirm and
                # cannot veto the equipment owner's required Home approach.
                self._close_store_visit("equipment-transaction-home-preempts-foreign")
            plan = self._town_errand_plan
            if (
                plan is None
                or plan.index >= len(plan.stops)
                or plan.stops[plan.index] != STORE_HOME
            ):
                self._town_errand_plan = TownErrandPlan([STORE_HOME])
            step = (
                self._shopping_approach_step(snapshot, STORE_HOME)
                if self._ensure_home_visit_request(snapshot)
                else None
            )
            if step is None or self._shopping_approach_store_type != STORE_HOME:
                self._block_equipment_transaction("home-route-unavailable")
                self.last_reason = "equipment-transaction:home-route-unavailable"
                return WAIT_KEY
            # Every issued approach is one attempt by this Home-owned work.
            # Charge it to the existing 300-pass ceiling before preserving the
            # route step. If movement never arrives, the 300th attempt blocks
            # Home and abandons the transaction, so the next public decision
            # reaches the named exhausted-route terminal. A normal arriving
            # route uses only its finite movement steps and remains unblocked.
            self._report_town_stop_pass(
                snapshot, STORE_HOME, goal_satisfied=False
            )
            self.last_reason = "equipment-transaction:approach-home"
            return self._shopping_approach_key(
                snapshot, step, "equipment-transaction:travel-home"
            )

        action = session.current_action
        if action is None:
            return None
        observation = observe_equipment_transactions(snapshot)
        if action.kind == "takeoff":
            slot_key = EQUIPMENT_SLOT_KEY.get(action.target_slot or "")
            if slot_key is None:
                self._block_equipment_transaction(
                    f"unknown-equipment-slot:{action.target_slot}"
                )
                return WAIT_KEY
            observed_identity = observation.equipped_identity(action.target_slot)
            if observed_identity != action.item_identity:
                self._invalidate_stale_equipment_transaction(
                    snapshot, action, observed_identity
                )
                return ""
            key = self._equipment_takeoff(snapshot, "transaction-apply", slot_key)
            if key is None:
                if not self.last_reason.startswith("posting-contract:"):
                    self.last_reason = "equipment-mutation:busy"
                return None
            if not self._prepare_equipment_transaction_command(
                session,
                action,
                observation,
                key,
                (
                    "town", getattr(snapshot, "turn", 0), action.target_slot,
                    action.item_identity,
                ),
            ):
                self._block_equipment_transaction("takeoff-dispatch-rejected")
                return WAIT_KEY
            self.last_reason = "equipment-transaction:takeoff"
            return key

        if action.kind in {"equip", "reposition"}:
            target = next(
                (
                    item
                    for item in snapshot.inventory
                    if item.is_equipment
                    and equipment_identity(item) == action.item_identity
                ),
                None,
            )
            if target is None:
                self._block_equipment_transaction(
                    f"equip-item-missing:{action.item_id}"
                )
                return WAIT_KEY
            macro = self._equipment_wield(
                snapshot, "transaction-apply", target, action.target_slot
            )
            if macro is None:
                refusal = getattr(self._equipment_mutation_result, "report", None)
                self._block_equipment_transaction(
                    refusal or f"unknown-equipment-slot:{action.target_slot}"
                )
                return WAIT_KEY
            if not self._prepare_equipment_transaction_command(
                session,
                action,
                observation,
                macro,
                (
                    "town", getattr(snapshot, "turn", 0), target.slot,
                    action.target_slot, action.item_identity,
                ),
            ):
                self._block_equipment_transaction("equip-dispatch-rejected")
                return WAIT_KEY
            self.last_reason = f"equipment-transaction:{action.kind}"
            return macro

        self._block_equipment_transaction(f"invalid-equip-action:{action.kind}")
        return WAIT_KEY

    def _equipment_departure_ready(self, snapshot: Snapshot) -> bool:
        """Permit completion now or a recorded loadout with no visit-local work."""
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR:
            return True
        cacheable = snapshot is self._map_predicate_snapshot
        if (
            cacheable
            and self._equipment_departure_cache_token == self._decision_sequence
        ):
            return self._equipment_departure_cache_value
        preparation = self._prepare_equipment_optimization(snapshot)
        complete_now = bool(
            preparation is not None
            and getattr(preparation, "ready", False)
            and preparation.transaction is not None
            and not preparation.transaction.actions
            and self._equipment_transaction_session is None
        )
        if complete_now:
            self._record_confirmed_loadout(snapshot)
        premise = bool(
            not complete_now
            and self._equipment_transaction_session is None
            and preparation is not None
            and getattr(preparation, "result", None) is not None
            and self._current_worn_loadout_confirmed(snapshot, preparation)
        )
        ready = complete_now
        if not ready and premise and preparation is not None:
            if (
                preparation.blockers
                and all(blocker.startswith("cursed-equipped:") for blocker in preparation.blockers)
                and (
                    any(item.is_cursed and self._curse_unremovable(item) for item in snapshot.equipment)
                    or not self._normal_remove_curse_actionable_this_visit(snapshot)
                )
            ):
                ready = True
            elif (
                "optimization-timeout" in preparation.blockers
            ):
                # The memo key proves that this timed-out search has exactly the
                # same semantic inputs as the earlier completed search.
                ready = True
            elif (
                "pending-random-teleport-suppression" in preparation.blockers
                and not self._random_teleport_suppression_actionable(snapshot, preparation)
            ):
                ready = True
            elif (
                preparation.blockers
                and all(blocker.startswith("pack-space-required:") for blocker in preparation.blockers)
                and self._town_pack_space_ready(snapshot)
            ):
                ready = True
            elif (
                "incomplete-equipment-catalog" in preparation.blockers
                and self._identification_need_unsatisfiable(snapshot)
            ):
                catalog = {owned.id: owned for owned in self._equipment_catalog.items}
                incomplete = [
                    catalog.get(item_id)
                    for item_id in preparation.result.incomplete_item_ids
                ]
                ready = bool(incomplete) and all(
                    owned is not None
                    and (
                        owned.origin != "equipped"
                        or self._item_signature(owned.item) in self._deferred_home_items
                    )
                    for owned in incomplete
                )
            elif self._equipment_failure_unexecutable_this_visit(
                snapshot, preparation
            ):
                ready = True
        if cacheable:
            self._equipment_departure_cache_token = self._decision_sequence
            self._equipment_departure_cache_value = ready
        return ready

    @staticmethod
    def _retained_ammo_slots(snapshot: Snapshot, ammo_tval: int) -> frozenset[str]:
        """Choose at most two dense stacks for the active ranged system.

        Count is the primary key because the purpose of this rule is pack-slot
        efficiency.  Damage and accuracy break ties so an equally dense,
        stronger recovered stack replaces a weaker one deterministically.
        """
        matching = [item for item in snapshot.inventory if item.tval == ammo_tval]
        matching.sort(
            key=lambda item: (
                item.count,
                item.to_d,
                item.to_h,
                int(item.is_artifact),
                int(item.is_ego),
                item.slot,
            ),
            reverse=True,
        )
        return frozenset(
            item.slot for item in matching[:AMMO_CARRY_STACK_LIMIT]
        )

    def _is_wanted_jewelry(self, snapshot: Snapshot, item: InventoryItem) -> bool:
        # Keep a ring / amulet in the pack (do NOT stash it at Home) while it could
        # still be identified and worn: an unidentified one heading for the identify
        # routine, or a known beneficial one for a slot with room. Otherwise found
        # jewelry is deposited unidentified and never equipped — the reason the
        # character reached deep floors with an empty neck slot.
        if item.tval == TVAL_AMULET:
            worn = any(it.tval == TVAL_AMULET for it in snapshot.equipment)
            return not worn and (not item.known or self._amulet_candidate(item))
        if item.tval == TVAL_RING:
            worn = sum(1 for it in snapshot.equipment if it.tval == TVAL_RING)
            return worn < 2 and (not item.known or self._ring_candidate(item))
        return False

    def _town_equipped_identification_key(self, snapshot: Snapshot) -> str | None:
        """Identify worn gear that the equipment optimizer counts incomplete.

        Two cases, mirroring OwnedEquipment.identification_incomplete in
        equipment_optimizer.py exactly so nothing it blocks departure for can be
        untouchable here: a worn item that is still entirely unidentified
        (known=False, and not merely pseudo-sensed "average") needs a plain
        Identify; a worn item already known but ego/artifact/dragon-armour
        (item_requires_full_identification) needs a *Identify* to reveal its
        combat traits. Without the first case, an equipped `known=false`
        weapon can sit blocking departure forever even while Identify scrolls
        are held unused in the pack (see the 2026-07-15 town deadlock, whose
        dominant blocker was exactly this: a worn, unidentified Bastard Sword).
        """
        if not snapshot.in_town or snapshot.store is not None:
            return None
        target = next(
            (
                item
                for item in snapshot.equipment
                if item.slot in EQUIPMENT_SLOT_KEY
                and self._item_signature(item) not in self._deferred_home_items
                and self._identification_flow_candidate(item)
            ),
            None,
        )
        if target is None:
            return None
        full = target.known
        source = self._find_identification_source(
            snapshot, full=full, reliable_only=True
        )
        if source is None:
            signature = self._item_signature(target)
            if full and STORE_ALCHEMIST in self._town_store_attempted:
                self._defer_full_identification(signature)
            else:
                self._identification_candidate = signature
                self._request_identification("full" if full else "normal")
            return None
        command, source_item = source
        self._identification_need = None
        self._identification_candidate = None
        self.last_reason = (
            "identify:full-equipped" if full else "identify:normal-equipped"
        )
        return (
            command
            + source_item.slot
            + "/"
            + EQUIPMENT_SLOT_KEY[target.slot]
            + (FULL_IDENTIFY_DISMISS_SUFFIX if full else "")
        )

    def _find_weapon_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        no_teleport = self._first_item(
            snapshot,
            lambda it: it.is_melee_weapon
            and self._blocks_teleport(it)
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )
        if no_teleport is not None:
            return no_teleport
        # Once an excellent-or-better weapon is wielded, the good/average spares
        # are redundant — sell them at the Weapon Smith instead of hoarding.
        if not self._equipped_weapon_high_grade(snapshot):
            return None
        wielded = next(
            (
                item for item in snapshot.equipment
                if item.slot == "main_hand" and item.is_melee_weapon
            ),
            None,
        )
        calibration = self._validated_character_calibration(snapshot)
        wielded_dps = (
            weapon_expected_dps(snapshot, wielded, 100, calibration)
            if wielded is not None
            else 0.0
        )

        def sale_quality_allows(item: InventoryItem) -> bool:
            # Without a calibration the DPS comparison is unknowable: fail
            # closed and keep the spare until the constants exist.
            candidate_dps = weapon_expected_dps(snapshot, item, 100, calibration)
            return (
                candidate_dps is not None
                and wielded_dps is not None
                and candidate_dps <= wielded_dps
            )

        return self._first_item(
            snapshot,
            lambda it: self._weapon_is_inferior(it)
            and sale_quality_allows(it)
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )

    @staticmethod
    def _equipment_slot_group(item: InventoryItem | StoreItem) -> str | None:
        groups = {
            20: "weapon",
            21: "weapon",
            22: "weapon",
            23: "weapon",
            30: "feet",
            31: "arms",
            32: "head",
            33: "head",
            34: "shield",
            35: "outer",
            36: "body",
            37: "body",
            38: "body",
        }
        return groups.get(item.tval)

    @staticmethod
    def _main_hand_dps(snapshot: Snapshot, weapon: InventoryItem) -> float:
        dice_average = (
            weapon.damage_dice_num * (weapon.damage_dice_sides + 1) / 2
        )
        damage = max(1.0, dice_average + snapshot.player.main_hand_to_d)
        hit_rate = melee_hit_chance(
            snapshot.player.melee_skill,
            snapshot.player.main_hand_to_h,
            weapon.to_h,
        )
        return snapshot.player.main_hand_blows * damage * hit_rate

    @staticmethod
    def _sub_hand_dps(snapshot: Snapshot, weapon: InventoryItem) -> float:
        dice_average = (
            weapon.damage_dice_num * (weapon.damage_dice_sides + 1) / 2
        )
        damage = max(1.0, dice_average + snapshot.player.sub_hand_to_d)
        hit_rate = melee_hit_chance(
            snapshot.player.melee_skill,
            snapshot.player.sub_hand_to_h,
            weapon.to_h,
        )
        return snapshot.player.sub_hand_blows * damage * hit_rate

    @staticmethod
    def _equipment_dominates(
        candidate: InventoryItem | StoreItem,
        current: InventoryItem | StoreItem,
    ) -> bool:
        # Armor comparison (this is only ever called for armour slots — the weapon
        # path uses a DPS trial). Rank by DEFENSE (base AC + magic AC) plus pval and
        # known flags, and DELIBERATELY ignore to_hit / to_dam: heavier armour carries
        # a to-hit PENALTY that must never veto a real AC gain. A Heavy Chain Mail
        # [16,+7] (23 AC, to-hit -2) is a clear upgrade over a Leather Scale Mail
        # [11,-5] (6 AC, to-hit -1) — to-hit/to-dam belong to the weapon, not here.
        candidate_defense = candidate.ac + candidate.to_a
        current_defense = current.ac + current.to_a
        no_worse = (
            candidate_defense >= current_defense
            and candidate.pval >= current.pval
            and candidate.known_flags.issuperset(current.known_flags)
        )
        strictly_better = (
            candidate_defense > current_defense
            or candidate.pval > current.pval
            or candidate.known_flags > current.known_flags
        )
        return no_worse and strictly_better

    def _is_disposable_dominated_launcher(
        self, snapshot: Snapshot, candidate: InventoryItem | StoreItem
    ) -> bool:
        """Return whether the equipped launcher strictly dominates this spare."""
        equipped = self._equipped_launcher(snapshot)
        if (
            snapshot.player.class_id != PLAYER_CLASS_WARRIOR
            or equipped is None
            or candidate is equipped
            or any(candidate is item for item in snapshot.equipment)
            or candidate.tval != TVAL_BOW
            or not candidate.known
            or candidate.is_cursed
            or candidate.is_broken
            or (
                item_requires_full_identification(candidate)
                and not candidate.fully_known
            )
            or self._equipment_disposal_reserved(snapshot, candidate)
        ):
            return False

        equipped_damage = self._launcher_average_damage(equipped)
        candidate_damage = self._launcher_average_damage(candidate)
        equipped_grade = (int(equipped.is_artifact), int(equipped.is_ego))
        candidate_grade = (int(candidate.is_artifact), int(candidate.is_ego))
        no_worse = (
            equipped_damage >= candidate_damage
            and equipped.to_h >= candidate.to_h
            and equipped.pval >= candidate.pval
            and equipped.known_flags.issuperset(candidate.known_flags)
            and equipped_grade >= candidate_grade
        )
        strictly_better = (
            equipped_damage > candidate_damage
            or equipped.to_h > candidate.to_h
            or equipped.pval > candidate.pval
            or equipped.known_flags > candidate.known_flags
            or equipped_grade > candidate_grade
        )
        return no_worse and strictly_better

    def _equipment_disposal_reserved(
        self, snapshot: Snapshot, item: InventoryItem | StoreItem
    ) -> bool:
        """Apply retention ownership without pretending Home wares are pack items."""
        if self._equipment_transaction_owns_item(item):
            return True
        if any(item is carried for carried in (*snapshot.inventory, *snapshot.equipment)):
            return self._retention_reservation(snapshot, item) > 0
        if self._item_signature(item) in self._town_visit_purchases:
            return True
        if item.is_torch:
            return True
        return bool(
            item.is_digging_tool
            and self._fundraising_mode in {"prepare", "mine", "scavenge"}
        )

    def _equipment_failure_unexecutable_this_visit(
        self,
        snapshot: Snapshot,
        preparation: object | None,
        *,
        require_confirmed: bool = True,
        include_launcher_enchant: bool = True,
    ) -> bool:
        """Prove a failed target has no owner or composable action this visit."""
        if tuple(getattr(preparation, "blockers", ())) != (
            "equipment-transaction-failed",
        ):
            return False
        if self._equipment_transaction_session is not None:
            return False
        if (
            require_confirmed
            and not self._current_worn_loadout_confirmed(snapshot, preparation)
        ):
            return False
        previous_include_launcher_enchant = getattr(
            self, "_town_need_evaluation_include_launcher_enchant", True
        )
        self._town_need_evaluation_include_launcher_enchant = (
            include_launcher_enchant
        )
        try:
            if self._home_owner_goal_pending(snapshot):
                return False
        finally:
            self._town_need_evaluation_include_launcher_enchant = (
                previous_include_launcher_enchant
            )
        if (
            STORE_HOME not in self._town_store_attempted
            and self._town_visit_ledger.unsatisfied_passes[STORE_HOME] == 0
            and self._town_visit_ledger.approach_fails[STORE_HOME] == 0
            and self._town_need_supplier_reachable(
                snapshot, TownNeed(STORE_HOME, "equipment-work", "home-first")
            )
        ):
            # ``_town_store_attempted`` records exhaustion, not first contact.
            # Once either ledger producer has observed a Home route attempt,
            # mere reachability is no longer evidence of executable work.
            return False
        # A last-source readmission is real required work, not a retireable
        # phantom.  Its visible terminal must remain closed to departure.
        if getattr(self, "_equipment_quarantine_readmitted_ids", ()):
            return False
        if self._equipment_quarantine_second_chance_ids:
            return False
        return True

    def _equipment_work_home_route_available(self) -> bool:
        """Return whether outstanding equipment work can still route to Home.

        Work suppresses a departure terminal only while Home remains a live
        route under the equipment-work bound.  A block installed by another
        bound has no authority over this work; already consumed passes still
        count, and exhaustion at this bound remains terminal.
        """
        limit = self._town_store_visit_limit(STORE_HOME)
        return (
            self._outstanding_equipment_work()
            and not self._town_store_blocked_under_applicable_bound(STORE_HOME)
            and self._town_visit_ledger.unsatisfied_passes[STORE_HOME] < limit
            and self._town_visit_ledger.approach_fails[STORE_HOME]
            < limit
        )

    @staticmethod
    def _home_rearm_weapon_score(item: StoreItem) -> tuple[int, int, float, int, int]:
        """Rank visible Home weapons for emergency post-mining re-arming."""
        average_dice = item.damage_dice_num * (item.damage_dice_sides + 1) / 2
        return (
            int(item.is_artifact),
            int(item.is_ego),
            average_dice + item.to_d,
            item.to_h,
            item.pval,
        )

    def _home_rearm_key(self, snapshot: Snapshot) -> str | None:
        """Search Home pages for a combat weapon before normal Home processing.

        A Home snapshot exposes only the current page. While a mining tool is
        equipped and no pack weapon exists, inspect that page, withdraw its best
        melee weapon, or advance with Space. A repeated page signature proves
        that the search wrapped, so give the normal weaponless backstop control
        instead of churning unrelated jewellery forever.
        """
        store = snapshot.store
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
        needs_replacement = (
            equipped_weapon is None and self._opening_q34_active(snapshot)
        ) or self._equipped_digging_tool(snapshot) is not None or (
            equipped_weapon is not None and self._blocks_teleport(equipped_weapon)
        ) or self._no_teleport_rearm_pending or (
            blocked_weapon_in_pack and not safe_weapon_equipped
        )
        needs_weapon = (
            store is not None
            and store.store_type == STORE_HOME
            and needs_replacement
            and not self._pack_has_safe_melee_weapon(snapshot)
            and (
                (
                    equipped_weapon is None
                    and self._opening_q34_active(snapshot)
                )
                or not self._combat_weapon_ready(snapshot)
            )
        )
        if not needs_weapon:
            self._home_rearm_seen_pages.clear()
            return None

        weapons = [
            item
            for item in store.items
            if item.is_melee_weapon
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and not self._blocks_teleport(item)
        ]
        if weapons:
            remembered = next(
                (
                    item
                    for item in weapons
                    if self._normal_weapon_name is not None
                    and item.name == self._normal_weapon_name
                ),
                None,
            )
            weapon = remembered or max(weapons, key=self._home_rearm_weapon_score)
            signature = self._item_signature(weapon)
            self._file_home_errand(
                snapshot,
                HomeErrandRequest(signature, 1, "home-page", "combat-weapon"),
                knowledge_current=self._home_knowledge_current,
            )
            self._home_rearm_seen_pages.clear()
            self._identification_candidate = None
            self._home_candidate_waiting = False
            self.last_reason = self._home_errand.reason("filed")
            return LEAVE_STORE_KEY

        page = tuple(
            (item.letter, item.name, item.tval, item.sval) for item in store.items
        )
        if page in self._home_rearm_seen_pages:
            self._home_rearm_seen_pages.clear()
            self._weapon_block_streak = WEAPON_BLOCK_LIMIT
            self.last_reason = "home:no-combat-weapon"
            return LEAVE_STORE_KEY

        self._home_rearm_seen_pages.add(page)
        self.last_reason = "home:seek-combat-weapon-page"
        return " "

    def _town_restore_weapon_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or self._calibration_active():
            return None
        current = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        if current is None or not current.is_digging_tool:
            restore = self._restore_mining_combat_hand_key(
                snapshot, "town:restore-combat-weapon"
            )
            if restore is not None:
                return restore
        replacing_no_teleport = current is not None and self._blocks_teleport(current)
        if replacing_no_teleport:
            if current.is_cursed:
                return None
            self._no_teleport_rearm_pending = True
            self.last_reason = "town:remove-no-teleport-weapon"
            return self._equipment_takeoff(
                snapshot, "replace-no-teleport", "a"
            )
        blocked_weapon_in_pack = any(
            item.is_melee_weapon and self._blocks_teleport(item)
            for item in snapshot.inventory
        )
        safe_weapon_equipped = (
            current is not None
            and current.is_melee_weapon
            and not self._blocks_teleport(current)
        )
        replacing_no_teleport = self._no_teleport_rearm_pending or (
            blocked_weapon_in_pack and not safe_weapon_equipped
        )
        if (
            self._equipped_digging_tool(snapshot) is None
            and not replacing_no_teleport
        ):
            return None
        # Swap the mining pickaxe back out for a real weapon BEFORE diving/recalling —
        # a digger is a feeble weapon and the next floor's monsters are not. Prefer the
        # exact weapon we swapped out (recorded when the digger went on); but a fresh bot
        # process that inherited an already-wielded digger has no such record, so fall
        # back to ANY melee weapon in the pack. Anything beats recalling on a pickaxe.
        weapon = None
        if self._normal_weapon_name is not None:
            weapon = self._first_item(
                snapshot,
                lambda it: it.is_equipment
                and not it.is_digging_tool
                and it.known
                and not it.is_cursed
                and not it.is_broken
                and not self._blocks_teleport(it)
                and it.name == self._normal_weapon_name,
            )
        if weapon is None:
            weapon = self._first_item(
                snapshot,
                lambda it: it.is_equipment
                and it.is_melee_weapon
                and it.known
                and not it.is_cursed
                and not it.is_broken
                and not self._blocks_teleport(it),
            )
        if weapon is None:
            # No combat weapon to restore — the pickaxe is our only weapon. Don't hang
            # the town routine WAITing for one that will never appear; carry on.
            return None
        reason = (
            "town:replace-no-teleport-weapon"
            if replacing_no_teleport
            else "town:restore-combat-weapon"
        )
        self.last_reason = reason
        key = self._wield_weapon_key(snapshot, weapon)
        if key is not None:
            self._equipment_mutation_post_commit = (key, "no-teleport-rearm")
        return key

    def _launcher_enchant_needed_svals(self, snapshot: Snapshot) -> tuple[int, ...]:
        launcher = self._equipped_launcher(snapshot)
        if launcher is None or not launcher.known or launcher.is_artifact:
            return ()
        needs: list[int] = []
        if (
            launcher.to_h <= 9
            and SV_SCROLL_ENCHANT_WEAPON_TO_HIT not in self._launcher_enchant_attempted
        ):
            needs.append(SV_SCROLL_ENCHANT_WEAPON_TO_HIT)
        if (
            launcher.to_d <= 9
            and SV_SCROLL_ENCHANT_WEAPON_TO_DAM not in self._launcher_enchant_attempted
        ):
            needs.append(SV_SCROLL_ENCHANT_WEAPON_TO_DAM)
        return tuple(needs)

    def _launcher_enchant_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if (
            store is None
            or store.store_type not in {STORE_ALCHEMIST, STORE_MAGIC}
        ):
            return None
        carried_svals = {
            item.sval
            for item in snapshot.inventory
            if item.is_scroll and item.aware
        }
        for sval in self._launcher_enchant_needed_svals(snapshot):
            if sval in carried_svals:
                continue
            scroll = next(
                (
                    item for item in store.items
                    if item.tval == TVAL_SCROLL
                    and item.sval == sval
                    and item.count > 0
                    and snapshot.player.gold - item.price >= FUNDRAISING_START_GOLD
                ),
                None,
            )
            if scroll is not None:
                return scroll
        return None

    def _town_enchant_launcher_key(self, snapshot: Snapshot) -> str | None:
        if (
            not snapshot.in_town
            or snapshot.store is not None
            or snapshot.player.blind
            or snapshot.player.confused
        ):
            return None
        launcher = self._equipped_launcher(snapshot)
        if launcher is None:
            return None
        slot_key = EQUIPMENT_SLOT_KEY.get(launcher.slot)
        if slot_key is None:
            return None
        for sval in self._launcher_enchant_needed_svals(snapshot):
            scroll = self._first_item(
                snapshot,
                lambda item: item.is_scroll and item.aware and item.sval == sval,
            )
            if scroll is None:
                continue
            previous_bonus = (
                launcher.to_h
                if sval == SV_SCROLL_ENCHANT_WEAPON_TO_HIT
                else launcher.to_d
            )
            self._launcher_enchant_attempted.add(sval)
            self._launcher_enchant_watch = (
                sval,
                self._item_signature(launcher),
                previous_bonus,
            )
            self.last_reason = (
                "town:enchant-launcher-tohit"
                if sval == SV_SCROLL_ENCHANT_WEAPON_TO_HIT
                else "town:enchant-launcher-todam"
            )
            return self._read_key(snapshot, scroll, "/" + slot_key)
        return None

    @staticmethod
    def _equipment_preparation_selected_ids(preparation) -> frozenset[str]:
        result = getattr(preparation, "result", None)
        best = getattr(result, "best", None)
        loadout = getattr(best, "loadout", None)
        selected_ids = getattr(loadout, "item_ids", frozenset())
        if not isinstance(selected_ids, (set, frozenset)):
            return frozenset()
        return frozenset(selected_ids)

    def _equipment_wield(
        self, snapshot: Snapshot, goal: str, item: InventoryItem,
        target_slot: str | None,
    ) -> str | None:
        if target_slot is None:
            return None
        result = self._equipment_mutation.request_wield(
            snapshot, goal, item, target_slot, EQUIPMENT_SLOT_KEY
        )
        if (
            self._equipment_mutation.observed_changes
            != self._equipment_mutation_observed_changes
        ):
            # A changed worn signature proves the preceding operation worked.
            # Only unchanged release cycles count toward the unwieldable exit.
            self._digger_wield_attempts = 0
            self._equipment_mutation_observed_changes = (
                self._equipment_mutation.observed_changes
            )
        self._equipment_mutation_result = result
        if result.key is not None:
            self._equipment_mutation.bind_post_snapshot(snapshot)
        elif result.report is not None:
            self.last_reason = result.report
            self._pending_mutation_report = result.report
        return result.key

    def _equipment_takeoff(
        self, snapshot: Snapshot, goal: str, slot_key: str
    ) -> str | None:
        result = self._equipment_mutation.request_takeoff(snapshot, goal, slot_key)
        if (
            self._equipment_mutation.observed_changes
            != self._equipment_mutation_observed_changes
        ):
            self._digger_wield_attempts = 0
            self._equipment_mutation_observed_changes = (
                self._equipment_mutation.observed_changes
            )
        self._equipment_mutation_result = result
        if result.key is not None:
            self._equipment_mutation.bind_post_snapshot(snapshot)
        elif result.report is not None:
            self.last_reason = result.report
            self._pending_mutation_report = result.report
        return result.key

    def _wield_weapon_key(self, snapshot: Snapshot, weapon: InventoryItem) -> str | None:
        """Wield a weapon in the main hand, preserving an occupied off hand."""
        macro = self._equipment_wield(snapshot, "combat-loadout", weapon, "main_hand")
        return macro

    def _wield_digging_tool_key(
        self, snapshot: Snapshot, reason: str
    ) -> str | None:
        """Build the mining-only loadout without ever mixing combat gear and diggers.

        ``do_cmd_wield`` changes its prompt chain with the occupied hands.  Strip
        observed combat hands first, then compose the complete source-derived
        prompt tail from the last observed hand state.
        """
        self._equipment_mutation_result = EquipmentMutationResult(None)
        main_hand = next(
            (it for it in snapshot.equipment if it.slot == "main_hand"), None
        )
        sub_hand = next(
            (it for it in snapshot.equipment if it.slot == "sub_hand"), None
        )
        if not self._mining_combat_loadout_remembered:
            preparation = self._equipment_optimization_preparation
            result = getattr(preparation, "result", None)
            best = getattr(result, "best", None)
            loadout = getattr(best, "loadout", None)
            optimal_main = (
                loadout.item_at("main_hand")
                if loadout is not None and hasattr(loadout, "item_at")
                else None
            )
            optimal_sub = (
                loadout.item_at("sub_hand")
                if loadout is not None and hasattr(loadout, "item_at")
                else None
            )
            # An optimizer winner makes an empty sub hand authoritative.  An
            # absent main-hand choice cannot: retain the observed weapon so a
            # cold/incomplete cache can never make the restore weaponless.
            if optimal_main is not None:
                self._normal_weapon_name = optimal_main.item.name
                self._normal_weapon_identity = equipment_identity(optimal_main.item)
                self._normal_weapon_is_optimal = True
            elif (
                main_hand is not None
                and not main_hand.is_digging_tool
            ):
                self._normal_weapon_name = main_hand.name
                self._normal_weapon_identity = equipment_identity(main_hand)
                self._normal_weapon_is_optimal = False
            if loadout is not None and hasattr(loadout, "item_at"):
                self._normal_sub_hand_name = (
                    optimal_sub.item.name if optimal_sub is not None else None
                )
                self._normal_sub_hand_identity = (
                    equipment_identity(optimal_sub.item)
                    if optimal_sub is not None
                    else None
                )
                self._normal_sub_hand_is_optimal = True
            elif sub_hand is not None and not sub_hand.is_digging_tool:
                self._normal_sub_hand_name = sub_hand.name
                self._normal_sub_hand_identity = equipment_identity(sub_hand)
                self._normal_sub_hand_is_optimal = False
            self._mining_combat_loadout_remembered = True
        combat_hands = [
            item
            for item in (main_hand, sub_hand)
            if item is not None and not item.is_digging_tool
        ]
        if combat_hands:
            blocked = next(
                (
                    item
                    for item in combat_hands
                    if item.is_cursed and self._curse_unremovable(item)
                ),
                None,
            )
            if blocked is not None:
                return None
            key = self._equipment_takeoff(
                snapshot, "mining-loadout", EQUIPMENT_SLOT_KEY[combat_hands[0].slot]
            )
            if key is not None:
                self._digger_wield_attempts += 1
                self.last_reason = reason
            elif self._equipment_mutation_result.report is not None:
                self._digger_wield_attempts += 1
            return key

        target_slot = "sub_hand" if main_hand is not None else "main_hand"
        tool = self._first_item(snapshot, lambda it: it.is_digging_tool)
        if tool is None:
            return None
        if (
            main_hand is not None
            and not main_hand.is_digging_tool
            and not self._normal_weapon_is_optimal
        ):
            self._normal_weapon_name = main_hand.name
        if (
            target_slot == "sub_hand"
            and sub_hand is not None
            and not sub_hand.is_digging_tool
            and not self._normal_sub_hand_is_optimal
        ):
            self._normal_sub_hand_name = sub_hand.name
        key = self._equipment_wield(snapshot, "mining-loadout", tool, target_slot)
        if key is not None:
            self._digger_wield_attempts += 1
            self.last_reason = reason
        elif self._equipment_mutation_result.report is not None:
            self._digger_wield_attempts += 1
        return key
