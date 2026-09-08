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


class QuestMixin:
    def _derived_home_visit_request(
        self, snapshot: Snapshot
    ) -> PhysicalHomeVisitRequest | None:
        """Translate every legacy Home producer into one immutable request."""
        keep_set = self._home_visit_keep_set(snapshot)
        session = self._equipment_transaction_session
        action = session.current_action if session is not None else None
        if action is not None and action.kind == "deposit":
            current = next((
                item for item in snapshot.inventory
                if item.is_equipment
                and equipment_identity(item) == action.item_identity
            ), None)
            if current is not None:
                identity = self._item_signature(current)
                if identity in keep_set:
                    return None
                return PhysicalHomeVisitRequest(
                    HomeVisitKind.EQUIPMENT_MUTATION,
                    "equipment-transaction",
                    identity,
                    keep_set=keep_set,
                    shelving_plan=(identity,),
                )
        if action is not None and action.kind == "withdraw":
            identity = next((
                self._item_signature(item)
                for item in self._home_knowledge_items
                if item.is_equipment
                and equipment_identity(item) == action.item_identity
            ), ("equipment-id", action.item_id, 0))
            return PhysicalHomeVisitRequest(
                HomeVisitKind.EQUIPMENT_MUTATION,
                "equipment-transaction",
                action.item_identity,
                address=identity,
                keep_set=keep_set,
                shelving_plan=tuple(
                    getattr(candidate, "item_identity", None)
                    for candidate in session.plan.actions
                ),
            )
        identity = self._home_pending_item or (
            self._home_pending_batch[0] if self._home_pending_batch else None
        )
        if identity is not None:
            return PhysicalHomeVisitRequest(
                HomeVisitKind.WITHDRAW,
                "legacy-withdrawal",
                identity,
                address=identity,
                quantity=self._home_pending_quantity or 1,
                keep_set=keep_set,
                batch=tuple(self._home_pending_batch),
            )
        if self._calibration_phase == "deposit":
            deposit = self._find_home_deposit(snapshot)
            if deposit is not None:
                identity = self._item_signature(deposit)
                return PhysicalHomeVisitRequest(
                    HomeVisitKind.CALIBRATION_RESTORE,
                    "calibration-deposit",
                    identity,
                    quantity=deposit.count,
                    keep_set=keep_set,
                    shelving_plan=(identity,),
                    batch=tuple(self._calibration_restore_signatures),
                )
        if self._calibration_restore_signatures:
            identity = self._calibration_restore_signatures[0]
            return PhysicalHomeVisitRequest(
                HomeVisitKind.CALIBRATION_RESTORE,
                "calibration-restore",
                identity,
                batch=tuple(self._calibration_restore_signatures),
                keep_set=keep_set,
            )
        if self._home_errand.active and self._home_errand.request is not None:
            errand = self._home_errand.request
            return PhysicalHomeVisitRequest(
                HomeVisitKind.WITHDRAW,
                f"home-errand:{errand.purpose}",
                errand.signature,
                address=errand.signature,
                quantity=errand.quantity,
                keep_set=keep_set,
            )
        deposit = self._find_home_deposit(snapshot)
        if deposit is not None:
            identity = self._item_signature(deposit)
            if identity not in keep_set:
                return PhysicalHomeVisitRequest(
                    HomeVisitKind.DEPOSIT,
                    "home-deposit",
                    identity,
                    quantity=max(1, self._retention_surplus(snapshot, deposit)),
                    keep_set=keep_set,
                    shelving_plan=(identity,),
                )
        if not self._home_knowledge_current:
            return PhysicalHomeVisitRequest(HomeVisitKind.SCAN, "home-scan")
        return PhysicalHomeVisitRequest(HomeVisitKind.RECOVERY, "home-recovery")

    def _opening_q34_active(self, snapshot: Snapshot) -> bool:
        """Whether the fresh-character Q34-first contract still owns town."""
        if (
            not snapshot.in_town
            or snapshot.town_id not in {-1, 0}
            or snapshot.player.class_id < 0
        ):
            return False
        quest = self._known_fixed_quests(snapshot).get(34)
        if (
            quest is None
            or quest.status not in {QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN}
            or (
                quest.status == QUEST_STATUS_UNTAKEN
                and (
                    snapshot.player.level != 1
                    or not self._fixed_quest_is_offered(snapshot, 34)
                )
            )
            or any(
                candidate.fixed
                and candidate.status == QUEST_STATUS_TAKEN
                and candidate.id != 34
                and candidate.id not in WIN_QUEST_IDS
                for candidate in snapshot.quests.values()
            )
        ):
            return False
        return self.approved_quest_strategy(34) is not None

    def _opening_q34_town_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Give the accepted Q34 opening sole non-emergency town ownership."""
        if not self._opening_q34_active(snapshot):
            return None

        if (self._town_blocked_reason or "").startswith(
            "equipment-transaction:withdraw-item-unobserved:"
        ):
            self._abandon_blocked_equipment_transaction(snapshot)
        if self._equipment_transaction_owned_items:
            return self._equipment_transaction_town_owner_key(snapshot) or WAIT_KEY

        if not any(item.slot == "main_hand" for item in snapshot.equipment):
            weapon = self._first_item(
                snapshot,
                lambda item: item.is_equipment
                and item.is_melee_weapon
                and item.known
                and not item.is_cursed
                and not item.is_broken
                and not self._blocks_teleport(item),
            )
            if weapon is not None:
                self.last_reason = "opening-q34:rearm"
                return self._wield_weapon_key(snapshot, weapon)

        restore_weapon = self._town_restore_weapon_key(snapshot)
        if restore_weapon is not None:
            return restore_weapon

        claims_active = self._town_claims_active(snapshot)
        if not claims_active:
            self._town_terminal_transitions(snapshot)
        if claims_active:
            step = self._shopping_approach_step(snapshot)
            if step is not None:
                self.last_reason = "shop:approach"
                return self._shopping_approach_key(snapshot, step, "shop:travel")

        readiness_before = self._fixed_quest_readiness
        fixed_quest = self._fixed_quest_key(snapshot, hostiles)
        if fixed_quest is not None:
            return fixed_quest
        if (
            self._town_restock_wait_until is not None
            and snapshot.turn < self._town_restock_wait_until
        ):
            self.last_reason = self._restock_wait_reason(snapshot)
            return WAIT_KEY
        # A false readiness verdict evaluated by this decision is work, not an
        # idle state.  The opening remains the sole owner: try its bounded shop
        # route regardless of whether the fundraising latch can start, then
        # expose the CLI-visible terminal only when neither route can advance.
        readiness = (
            self._fixed_quest_readiness
            if self._fixed_quest_readiness is not readiness_before
            else {}
        )
        failed = readiness.get("strategy_force", {}).get("failed", ())
        if failed:
            step = self._shopping_approach_step(snapshot)
            if step is not None:
                self.last_reason = "shop:approach"
                return self._shopping_approach_key(snapshot, step, "shop:travel")
            if self._start_fundraising(snapshot):
                step = self._shopping_approach_step(snapshot)
                if step is not None:
                    self.last_reason = "shop:approach"
                    return self._shopping_approach_key(snapshot, step, "shop:travel")
            self.last_reason = "livelock:exhausted"
            return WAIT_KEY
        self.last_reason = "livelock:exhausted" if failed else "opening-q34:wait"
        return WAIT_KEY

    def _opening_q34_torch_shortage(self, snapshot: Snapshot) -> int:
        """Return the mandatory torch shortage for a fresh Outpost warrior."""
        if not self._opening_q34_active(snapshot):
            return 0
        profile = self.approved_quest_strategy(34)
        if profile is None:
            return 0
        required = int(
            profile.required_force.get("throwing_items", {}).get("lit_torch", 0)
        )
        return max(0, required - self._count_throwing_torches(snapshot))

    def _quest_launcher_ammo(
        self, snapshot: Snapshot, force: dict
    ) -> int | None:
        launcher = force.get("launcher")
        if not isinstance(launcher, dict):
            return None
        ammo = str(launcher.get("ammo", ""))
        if ammo == "equipped":
            equipped = self._equipped_launcher(snapshot)
            return equipped.ammo_tval if equipped is not None else None
        return QUEST_AMMO_TVALS.get(ammo)

    @staticmethod
    def _quest_uses_selected_launcher(force: dict) -> bool:
        launcher = force.get("launcher")
        return isinstance(launcher, dict) and launcher.get("ammo") == "equipped"

    def _quest_launcher_meets_force(
        self, item: InventoryItem | StoreItem | None, force: dict
    ) -> bool:
        if item is None or item.tval != TVAL_BOW or item.ammo_tval is None:
            return False
        launcher = force.get("launcher")
        if not isinstance(launcher, dict):
            return False
        required_ammo = self._quest_launcher_ammo_from_item_or_force(item, force)
        ammo_matches = (
            self._quest_uses_selected_launcher(force)
            or item.ammo_tval == required_ammo
        )
        return ammo_matches and self._launcher_average_damage(item) >= float(
            launcher.get("min_average_damage", 0) or 0
        )

    def _quest_launcher_ammo_from_item_or_force(
        self, item: InventoryItem | StoreItem | None, force: dict
    ) -> int | None:
        if self._quest_uses_selected_launcher(force):
            return item.ammo_tval if item is not None else None
        launcher = force.get("launcher")
        if not isinstance(launcher, dict):
            return None
        return QUEST_AMMO_TVALS.get(str(launcher.get("ammo", "")))

    def _quest_named_item_count(
        self, snapshot: Snapshot, category: str, name: str
    ) -> int:
        if category == "throwing_items":
            if name == "lit_torch":
                return sum(
                    it.count for it in snapshot.inventory
                    if it.is_torch and it.fuel > 0
                )
            tval = (
                self._equipped_launcher(snapshot).ammo_tval
                if name == "launcher_ammo"
                and self._equipped_launcher(snapshot) is not None
                else QUEST_AMMO_TVALS.get(name)
            )
            return sum(it.count for it in snapshot.inventory if it.tval == tval)
        if category == "required_scrolls":
            sval = QUEST_SCROLL_SVALS.get(name)
            return sum(
                it.count
                for it in snapshot.inventory
                if it.tval == TVAL_SCROLL and it.sval == sval and it.aware
            )
        if category == "utility_tools" and name == "wall_breach":
            return sum(
                it.count
                for it in (*snapshot.inventory, *snapshot.equipment)
            if self._is_quest_wall_breach_item(it)
            )
        return 0

    def _quest_carry_status(
        self, snapshot: Snapshot, force: dict
    ) -> dict[str, dict[str, int | bool]]:
        status: dict[str, dict[str, int | bool]] = {}
        launcher_ammo = self._quest_launcher_ammo(snapshot, force)
        launcher_required = isinstance(force.get("launcher"), dict)
        if launcher_required:
            launcher = self._equipped_launcher(snapshot)
            ready = self._quest_launcher_meets_force(launcher, force)
            status["launcher"] = {
                "measured": int(ready), "required": 1, "ready": ready,
            }
            minimum_damage = float(
                force["launcher"].get("min_average_damage", 0) or 0
            )
            if minimum_damage > 0:
                measured_damage = self._launcher_average_damage(launcher)
                status["launcher.average_damage"] = {
                    "measured": measured_damage,
                    "required": minimum_damage,
                    "ready": measured_damage >= minimum_damage,
                }
        for category in ("throwing_items", "required_scrolls", "utility_tools"):
            requirements = force.get(category, {})
            if not isinstance(requirements, dict):
                continue
            for name, value in requirements.items():
                required = int(value)
                current = self._quest_named_item_count(
                    snapshot, category, str(name)
                )
                status[f"{category}.{name}"] = {
                    "measured": current,
                    "required": required,
                    "ready": current >= required,
                }
        return status

    @staticmethod
    def _quest_carry_suppliers(name: str) -> tuple[int, ...]:
        if name == "throwing_items.lit_torch":
            return (STORE_GENERAL,)
        if name.startswith("launcher") or name.startswith("throwing_items."):
            return (STORE_WEAPON,)
        if name.startswith("required_scrolls."):
            return (STORE_ALCHEMIST,)
        if name == "utility_tools.wall_breach":
            return (STORE_BLACK, STORE_GENERAL)
        return ()

    def _quest_carry_obtainability(
        self,
        snapshot: Snapshot,
        strategy: StrategyProfile,
        name: str,
        status: dict[str, int | bool],
    ) -> SupplyStatus:
        """Mirror SupplyLedger's per-visit evidence for one quest carry entry."""
        stores = self._quest_carry_suppliers(name)
        obtainable = False
        for current_supplier in stores:
            if self._quest_carry_remembered_affordable(
                snapshot, strategy, name, current_supplier
            ):
                obtainable = True
            if obtainable:
                break
            if current_supplier not in self._town_store_attempted:
                obtainable = True
                break
        if (
            name == "throwing_items.lit_torch"
            and self._home_procurement_candidate(
                (TVAL_LITE, SV_LITE_TORCH)
            ) is not None
        ):
            obtainable = True
        return SupplyStatus(
            name,
            int(status["measured"]),
            int(status["required"]),
            int(status["required"]),
            obtainable,
            stores,
        )

    def _quest_carry_remembered_affordable(
        self,
        snapshot: Snapshot,
        strategy: StrategyProfile,
        name: str,
        store_type: int,
    ) -> bool:
        """Return whether a remembered supplier page can satisfy one carry."""
        page = self._town_supplier_stock.get(store_type)
        if snapshot.store is not None and snapshot.store.store_type == store_type:
            page = snapshot.store
        if page is None:
            return False
        expected_target = (
            "launcher" if name.startswith("launcher") else name.partition(".")[2]
        )
        return any(
            item.price <= snapshot.player.gold
            and (target := self._quest_carry_target_for_item(
                snapshot, item, strategy.required_force
            )) is not None
            and target[0] == expected_target
            for item in page.items
        )

    def _quest_carry_target_for_item(
        self, snapshot: Snapshot, item: InventoryItem | StoreItem, force: dict
    ) -> tuple[str, int, int] | None:
        launcher_ammo = self._quest_launcher_ammo(snapshot, force)
        selected_launcher = self._quest_uses_selected_launcher(force)
        if item.tval == TVAL_BOW and (
            selected_launcher or item.ammo_tval == launcher_ammo
        ) and self._quest_launcher_meets_force(item, force):
            equipped = self._equipped_launcher(snapshot)
            current = int(
                self._quest_launcher_meets_force(equipped, force)
            )
            current += sum(
                it.count
                for it in snapshot.inventory
                if it.tval == TVAL_BOW
                and self._quest_launcher_meets_force(it, force)
            )
            return "launcher", current, 1
        throwing = force.get("throwing_items", {})
        if isinstance(throwing, dict):
            for name, value in throwing.items():
                matches = (
                    (item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH)
                    if name == "lit_torch"
                    else item.tval == (
                        launcher_ammo
                        if name == "launcher_ammo"
                        else QUEST_AMMO_TVALS.get(str(name))
                    )
                )
                if matches:
                    return str(name), self._quest_named_item_count(
                        snapshot, "throwing_items", str(name)
                    ), int(value)
        scrolls = force.get("required_scrolls", {})
        if isinstance(scrolls, dict):
            for name, value in scrolls.items():
                if item.tval == TVAL_SCROLL and item.sval == QUEST_SCROLL_SVALS.get(
                    str(name)
                ):
                    return str(name), self._quest_named_item_count(
                        snapshot, "required_scrolls", str(name)
                    ), int(value)
        tools = force.get("utility_tools", {})
        if (
            isinstance(tools, dict)
            and "wall_breach" in tools
            and self._is_quest_wall_breach_item(item)
        ):
            return "wall_breach", self._quest_named_item_count(
                snapshot, "utility_tools", "wall_breach"
            ), int(tools["wall_breach"])
        return None

    def _quest_sweep_pack_space_key(
        self, snapshot: Snapshot, floor_grid: GridState
    ) -> str | None:
        """Resolve a full pack before fixed-quest floor pickup.

        A loose light is not worth destroying an already-carried item for.  Mark
        that cell deferred so the sweep can continue.  For other loot, reuse the
        verified disposal path; if no carried item is safely disposable, defer
        the cell rather than retrying an impossible ``g`` forever.
        """
        if len(snapshot.inventory) < PACK_CAPACITY:
            return None
        if floor_grid.object_tvals and all(
            tval == TVAL_LITE for tval in floor_grid.object_tvals
        ):
            self._deferred_loot.add(floor_grid.position)
            self.last_reason = "quest:sweep:defer-full-pack-light"
            return WAIT_KEY
        destroy = self._full_pack_destroy_key(snapshot)
        if destroy is not None:
            self.last_reason = "quest:sweep:free-pack-slot"
            return destroy
        # Nothing carried is disposable yet — an all-unidentified pack hides its
        # junk. The standalone pack-pressure identify never runs mid-quest (the
        # quest sweep returns here before choose_key reaches it), so identify an
        # unknown in place: the disposal path can then judge it and free a slot
        # on a later pass instead of abandoning collectible quest loot.
        identify = self._pack_pressure_identify_key(snapshot)
        if identify is not None:
            self.last_reason = "quest:sweep:identify"
            return identify
        self._deferred_loot.add(floor_grid.position)
        self.last_reason = "quest:sweep:defer-full-pack-loot"
        return WAIT_KEY

    def _quest_equipment_entry_allowed(
        self, snapshot: Snapshot, quest_id: int
    ) -> bool:
        """Apply only the equipment boundary to a fixed quest entered on foot."""
        if (
            self._morivant_full_identify is not None
            and self._morivant_full_identify.temporary_deposits
        ):
            return False
        if self._opening_q34_active(snapshot) and quest_id == 34:
            ready = self._evaluate_fixed_quest_readiness(
                snapshot, quest_id, require_target_town=True
            )
            if not ready:
                reason = self._fixed_quest_readiness.get("reason", "unready")
                self.last_reason = f"quest:readiness:{reason}"
            return ready
        if self._equipment_departure_ready(snapshot):
            return True
        self._departure_block = self._departure_block_state(snapshot)
        self._departure_block_sequence = self._decision_sequence
        if not self._departure_block.get("failed"):
            self._departure_block["failed"] = ["equipment_departure_ready"]
        if self._town_blocked_reason is None:
            self._town_blocked_reason = "equipment-departure-incomplete"
        return False

    def _request_priority_body_rearm(self, snapshot: Snapshot) -> None:
        """Create the normal Home transaction when a safer body armour is idle."""
        if (
            not snapshot.in_town
            or snapshot.player.class_id != PLAYER_CLASS_WARRIOR
            or self._equipment_transaction_session is not None
            or self._calibration_active()
            or self._validated_character_calibration(snapshot) is None
            or not self._equipment_catalog.home_scan_complete
            or not self._home_knowledge_current
        ):
            return

        current = current_loadout(self._equipment_catalog.items)
        current_slots = dict(current.slots)
        worn = current_slots.get(SLOT_BODY)

        def armour_score(owned) -> tuple[int, int, int]:
            item = owned.item
            return (item.ac + item.to_a, item.to_a, item.ac)

        attempted_ids = getattr(self, "_priority_body_rearm_attempted_ids", None)
        if attempted_ids is None:
            attempted_ids = set()
            self._priority_body_rearm_attempted_ids = attempted_ids
        candidates = [
            owned
            for owned in self._equipment_catalog.items
            if owned.origin == "home"
            and slot_for(owned.item) == SLOT_BODY
            and owned.exploration_legal
            and owned.id not in attempted_ids
            and (
                worn is None
                or (
                    worn.flags.issubset(owned.flags)
                    and armour_score(owned) > armour_score(worn)
                )
            )
        ]
        if not candidates:
            return
        target_body = max(candidates, key=lambda owned: (armour_score(owned), owned.id))
        current_slots[SLOT_BODY] = target_body
        target = Loadout(tuple(sorted(current_slots.items())), current.hand_mode)
        preserve_pack = frozenset(
            owned.id
            for owned in self._equipment_catalog.items
            if owned.origin == "pack"
        )
        transaction = plan_equipment_transactions(
            self._equipment_catalog.items,
            current,
            target,
            current_pack_items=len(snapshot.inventory),
            home_scan_complete=True,
            preserve_pack_item_ids=preserve_pack,
        )
        if not transaction.actions or not transaction.executable:
            return
        attempted_ids.add(target_body.id)
        self._set_equipment_transaction_session(EquipmentTransactionSession(
            transaction,
            max_unconfirmed_observations=EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
        ))
        self._equipment_optimization_telemetry["priority_body_rearm"] = {
            "item_id": target_body.id,
            "empty_slot": worn is None,
            "armour_score": armour_score(target_body),
        }

    def _conquest_departure_ready(self, snapshot: Snapshot) -> bool:
        """Apply the ordinary recall departure gate, independent of fundraising."""
        fundraising_mode = self._fundraising_mode
        try:
            self._fundraising_mode = None
            return self._town_departure_ready(snapshot) and self._combat_weapon_ready(
                snapshot
            )
        finally:
            self._fundraising_mode = fundraising_mode

    def _morivant_home_item_key(self, snapshot: Snapshot) -> str | None:
        """Run the expedition's Home withdrawals and bounded restore ledger."""
        expedition = self._morivant_full_identify
        store = snapshot.store
        if (
            expedition is None
            or store is None
            or store.store_type != STORE_HOME
            or expedition.phase not in {"prepare-home", "return-home", "restore-home"}
        ):
            return None

        inflight = expedition.home_inflight
        if inflight is not None:
            action, signature, count, before_count = inflight
            after_count = self._inventory_signature_count(snapshot, signature)
            succeeded = after_count < before_count if action == "deposit" else after_count > before_count
            if succeeded:
                if action == "deposit":
                    expedition.temporary_deposits.append((signature, count))
                elif expedition.phase == "prepare-home":
                    if signature in self._home_pending_batch:
                        self._home_pending_batch.remove(signature)
                else:
                    restored_index = next(
                        (
                            index for index, entry
                            in enumerate(expedition.temporary_deposits)
                            if entry[0] == signature
                        ),
                        None,
                    )
                    if restored_index is not None:
                        expedition.temporary_deposits.pop(restored_index)
                expedition.home_inflight = None
                expedition.home_failures.pop((action, signature), None)
                expedition.seen_home_pages.clear()
            else:
                failure = (action, signature)
                expedition.home_failures[failure] += 1
                if expedition.home_failures[failure] < STORE_STUCK_LIMIT:
                    if action == "deposit":
                        carried = self._first_item(
                            snapshot,
                            lambda item: self._item_signature(item) == signature,
                        )
                        if carried is not None:
                            self.last_reason = "home:morivant-retry-temporary-deposit"
                            return self._home_deposit_key(
                                snapshot, carried, forced_count=count
                            )
                    else:
                        ware = next(
                            (
                                item for item in store.items
                                if self._item_signature(item) == signature
                            ),
                            None,
                        )
                        if ware is not None:
                            self._home_pending_item = signature
                            self._home_pending_quantity = count
                            expedition.home_inflight = None
                            self.last_reason = "home:morivant-withdraw-failed"
                            return LEAVE_STORE_KEY
                expedition.home_inflight = None
                if action == "withdraw" and expedition.phase == "prepare-home":
                    if signature in self._home_pending_batch:
                        self._home_pending_batch.remove(signature)
                    self.last_reason = "home:morivant-target-unavailable"
                elif action == "withdraw":
                    dropped_index = next(
                        (
                            index for index, entry
                            in enumerate(expedition.temporary_deposits)
                            if entry[0] == signature
                        ),
                        None,
                    )
                    if dropped_index is not None:
                        expedition.temporary_deposits.pop(dropped_index)
                    self.last_reason = "home:morivant-ledger-drop-unavailable"
                else:
                    self.last_reason = "home:morivant-space-deposit-rejected"
                    self._finish_morivant_full_identify()
                    return LEAVE_STORE_KEY

        if expedition.phase == "return-home":
            deposit = self._find_home_deposit(snapshot)
            if deposit is not None:
                return self._home_deposit_key(snapshot, deposit)
            expedition.phase = "restore-home"
            expedition.seen_home_pages.clear()

        if expedition.phase == "restore-home":
            if not expedition.temporary_deposits:
                self.last_reason = "home:morivant-ledger-restored"
                self._finish_morivant_full_identify()
                return LEAVE_STORE_KEY
            signature, count = expedition.temporary_deposits[0]
            ware = next(
                (item for item in store.items if self._item_signature(item) == signature),
                None,
            )
            if ware is not None and len(snapshot.inventory) < PACK_CAPACITY:
                expedition.home_inflight = (
                    "withdraw", signature, min(count, ware.count),
                    self._inventory_signature_count(snapshot, signature),
                )
                self.last_reason = "home:morivant-restore-temporary-deposit"
                quantity = min(count, ware.count)
                self._home_pending_item = signature
                self._home_pending_quantity = quantity
                return LEAVE_STORE_KEY

        if expedition.phase == "prepare-home":
            remaining = list(self._home_pending_batch)
            free_slots = PACK_CAPACITY - len(snapshot.inventory)
            if free_slots < len(remaining):
                protected = set(expedition.target_signatures)
                deposit = self._first_item(
                    snapshot,
                    lambda item: self._item_signature(item) not in protected
                    and self._retention_surplus(snapshot, item) == item.count,
                )
                if deposit is None:
                    deposit = self._first_item(
                        snapshot,
                        lambda item: self._item_signature(item) not in protected,
                    )
                if deposit is None:
                    self.last_reason = "home:morivant-no-space-source"
                    self._finish_morivant_full_identify()
                    return LEAVE_STORE_KEY
                signature = self._item_signature(deposit)
                expedition.home_inflight = (
                    "deposit", signature, deposit.count,
                    self._inventory_signature_count(snapshot, signature),
                )
                self.last_reason = "home:morivant-temporary-deposit"
                return self._home_deposit_key(
                    snapshot, deposit, forced_count=deposit.count
                )
            if not remaining:
                expedition.phase = "travel"
                expedition.seen_home_pages.clear()
                self._home_candidate_waiting = False
                self.last_reason = "home:morivant-targets-withdrawn"
                return LEAVE_STORE_KEY
            signature = remaining[0]
            ware = next(
                (item for item in store.items if self._item_signature(item) == signature),
                None,
            )
            if ware is not None:
                expedition.home_inflight = (
                    "withdraw", signature, 1,
                    self._inventory_signature_count(snapshot, signature),
                )
                self._home_pending_item = signature
                self.last_reason = "home:queue-batch-withdraw"
                return LEAVE_STORE_KEY

        page = tuple(self._item_signature(item) for item in store.items)
        if page not in expedition.seen_home_pages:
            expedition.seen_home_pages.add(page)
            self.last_reason = "home:morivant-seek-page"
            return " "
        if expedition.phase == "restore-home":
            signature, _ = expedition.temporary_deposits.pop(0)
            reason = "no-space" if ware is not None else "missing"
            self.last_reason = (
                f"home:morivant-ledger-drop-{reason}:{signature[0]}"
            )
            expedition.seen_home_pages.clear()
            return WAIT_KEY
        self.last_reason = "home:morivant-target-page-missing"
        self._finish_morivant_full_identify()
        return LEAVE_STORE_KEY

    def _morivant_full_identify_key(self, snapshot: Snapshot) -> str | None:
        """Batch carried *Identify* work through Morivant's Library."""
        if not snapshot.in_town or snapshot.store is not None:
            return None
        targets = self._carried_full_identify_targets(snapshot)
        home_targets = self._home_full_identify_targets()
        all_targets = [*targets, *home_targets]
        signatures = tuple(sorted(self._item_signature(item) for item in all_targets))
        expedition = self._morivant_full_identify
        if expedition is None:
            if (
                len(all_targets) < MORIVANT_FULL_IDENTIFY_THRESHOLD
                or (self._identification_need != "full" and not home_targets)
                or signatures in self._morivant_full_identify_attempted
                or self._find_identification_source(snapshot, full=True) is not None
                or snapshot.visited_town_ids is None
                or MORIVANT_TOWN_ID not in snapshot.visited_town_ids
                or snapshot.player.gold
                < MORIVANT_FULL_IDENTIFY_COST + 2 * TOWN_TELEPORT_COST
            ):
                return None
            home_signatures = tuple(
                sorted(self._item_signature(item) for item in home_targets)
            )
            expedition = MorivantFullIdentifyExpedition(
                self._effective_town_id(snapshot),
                signatures,
                home_target_signatures=home_signatures,
                phase="prepare-home" if home_signatures else "travel",
            )
            self._morivant_full_identify = expedition
            if home_signatures:
                self._home_pending_batch.extend(
                    signature for signature in home_signatures
                    if signature not in self._home_pending_batch
                )
                self._home_candidate_waiting = True
                self._identification_need = None

        if expedition.phase in {"prepare-home", "return-home", "restore-home"}:
            return None

        current = self._effective_town_id(snapshot)
        if current != MORIVANT_TOWN_ID:
            if expedition.returning and current == expedition.origin_town_id:
                if expedition.temporary_deposits or expedition.home_target_signatures:
                    expedition.phase = "return-home"
                    self._home_candidate_waiting = True
                    self._rearm_town_store_for_new_work(STORE_HOME)
                    return None
                self._finish_morivant_full_identify()
                return None
            destination = (
                expedition.origin_town_id
                if expedition.returning
                else MORIVANT_TOWN_ID
            )
            key = self._town_teleport_key(snapshot, destination)
            if key is not None:
                self.last_reason = f"town:morivant-full-identify:travel-{destination}"
                return key
            # A missing Inn route is terminal for this attempt, not a departure
            # claim.  Preserve today's deferral behavior and never spin here.
            self._finish_morivant_full_identify()
            return None

        affordable = max(
            0,
            (snapshot.player.gold - TOWN_TELEPORT_COST)
            // MORIVANT_FULL_IDENTIFY_COST,
        )
        chosen = targets[:affordable]
        if chosen:
            library_pos = (
                self._town_map.building_position(MORIVANT_LIBRARY_BUILDING_TYPE)
                if self._town_map_active(snapshot)
                else None
            )
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: grid.building_type
                == MORIVANT_LIBRARY_BUILDING_TYPE,
            )
            if step is None and library_pos is not None:
                step = self._town_map_goal_step(snapshot, library_pos)
            if step is not None:
                enters = step == library_pos or (
                    snapshot.grid_at(step) is not None
                    and snapshot.grid_at(step).building_type
                    == MORIVANT_LIBRARY_BUILDING_TYPE
                )
                self.last_reason = "town:morivant-full-identify:library"
                if enters:
                    selectors = "".join(
                        "a"
                        + (
                            item.slot
                            if item in snapshot.inventory
                            else "/" + EQUIPMENT_SLOT_KEY[item.slot]
                        )
                        + FULL_IDENTIFY_DISMISS_SUFFIX
                        for item in chosen
                    )
                    return self._step_toward(
                        snapshot, step, tail=selectors + LEAVE_STORE_KEY
                    )
                return self._step_toward(snapshot, step)

        # No affordable/remaining target or no Library route: return home if
        # possible; otherwise resolve this optional attempt immediately.
        if current != expedition.origin_town_id:
            expedition.returning = True
            key = self._town_teleport_key(snapshot, expedition.origin_town_id)
            if key is not None:
                self.last_reason = "town:morivant-full-identify:return"
                return key
        self._finish_morivant_full_identify()
        return None

    @staticmethod
    def _quest_launcher_quality(
        item: InventoryItem | StoreItem,
    ) -> tuple[int, int, int, int, int, int]:
        return (
            int(item.is_artifact),
            int(item.is_ego),
            item.to_h + item.to_d,
            item.to_d,
            item.to_h,
            item.pval,
        )

    def _quest_carry_purchase(
        self, snapshot: Snapshot, profile: StrategyProfile
    ) -> StoreItem | None:
        store = snapshot.store
        if store is None:
            return None
        force = profile.required_force
        tools = force.get("utility_tools", {})
        if (
            isinstance(tools, dict)
            and int(tools.get("wall_breach", 0)) > 0
            and self._quest_named_item_count(
                snapshot, "utility_tools", "wall_breach"
            ) < int(tools["wall_breach"])
        ):
            breach = [
                item for item in store.items
                if item.price <= snapshot.player.gold
                and self._is_quest_wall_breach_item(item)
            ]
            if breach:
                return min(
                    breach,
                    key=lambda item: (
                        item.tval != TVAL_WAND,
                        -item.pval if item.is_digging_tool else 0,
                        item.price,
                        item.letter,
                    ),
                )
        for item in store.items:
            if item.price > snapshot.player.gold:
                continue
            target = self._quest_carry_target_for_item(snapshot, item, force)
            if target is None:
                continue
            name, current, required = target
            if (
                name == "launcher"
                and self._preferred_home_quest_launcher(snapshot, profile)
                is not None
            ):
                continue
            if current < required:
                return item
        return None

    def _unique_sale_tag(
        self, snapshot: Snapshot, intended: InventoryItem
    ) -> str | None:
        """Reuse an unambiguous numeric tag, or allocate a fresh one."""
        existing = next(
            (digit for digit in "0123456789"
             if self._item_has_sale_tag(intended, digit)),
            None,
        )
        if existing is not None and self._sale_tag_is_unique(
            snapshot, intended, existing
        ):
            return existing
        used = {
            digit
            for item in snapshot.inventory
            if self._store_accepts_sale(snapshot.store.store_type, item)
            for digit in "0123456789"
            if self._item_has_sale_tag(item, digit)
        }
        return next((digit for digit in "0123456789" if digit not in used), None)

    def _conquest_loot_key(self, snapshot: Snapshot) -> str | None:
        # After killing a dungeon's final guardian, sweep its floor for the drop
        # BEFORE any return trigger (even the emergency latch) recalls us out — the
        # user flagged that conquest rewards were being left behind. Reached only
        # after the survival / combat steps above, so the floor is already safe.
        if self._victory_loot_dungeon is None or snapshot.in_town:
            return None
        if snapshot.floor_key[0] != self._victory_loot_dungeon:
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
            pickup_reason="conquest:pickup",
            trigger_reason="conquest:trigger-autodestroy",
        )
        if current_loot is not None:
            return current_loot
        step = self._loot_step(snapshot)
        if step is not None:
            self.last_reason = "conquest:seek-loot"
            return self._step_toward(snapshot, step)
        # Floor swept — release the latch so the normal return can proceed.
        # A conquered guardian floor has no progression goal left. Start the
        # return now instead of falling through to ordinary exploration.
        self._victory_loot_dungeon = None
        self._returning_to_town = True
        self._last_return_trigger = "conquest-complete"
        key = self._return_to_town_key(
            snapshot, self._strategic_hostiles(snapshot)
        )
        self._last_return_trigger = "conquest-complete"
        return key

    def _quest_never_move_races(self, profile: StrategyProfile) -> set[int]:
        return {
            race_id for race_id in profile.priority_targets
            if (
                (knowledge := self._monrace_knowledge.get(race_id)) is not None
                and "NEVER_MOVE" in knowledge.flags
            )
        }

    def _quest_strategy_emergency_hostiles(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile,
        hostiles: list[MonsterState],
    ) -> list[MonsterState]:
        """Exclude only distant stationary enemies owned by the quest plan."""
        controlled = {
            race_id
            for race_id in self._quest_never_move_races(profile)
            if (
                (knowledge := self._monrace_knowledge.get(race_id)) is not None
                and knowledge.max_ranged_damage <= 0
                and not knowledge.can_summon
                and not knowledge.can_multiply
                and "TELE_TO" not in knowledge.abilities
            )
        }
        return [
            monster
            for monster in hostiles
            if monster.race_id not in controlled
            or snapshot.player.position.distance_to(monster.position) <= 1
        ]

    def _quest_final_target_position(
        self, profile: StrategyProfile, never_move_races: set[int]
    ) -> Position | None:
        info = self._quest_knowledge.get(profile.quest_id)
        battlefield = info.battlefield if info is not None else None
        if battlefield is None:
            return None
        mobile_priorities = [
            race_id for race_id in profile.priority_targets
            if race_id not in never_move_races
        ]
        for race_id in mobile_priorities:
            placement = next(
                (position for position, placed_race in battlefield.monster_placements
                 if placed_race == race_id),
                None,
            )
            if placement is not None:
                return Position(*placement)
        return None

    def _quest_profile_ammo(
        self, snapshot: Snapshot, profile: StrategyProfile
    ) -> InventoryItem | None:
        ammo_tval = self._quest_launcher_ammo(snapshot, profile.required_force)
        launcher = self._equipped_launcher(snapshot)
        if launcher is None or launcher.ammo_tval != ammo_tval:
            return None
        return self._first_item(snapshot, lambda item: item.tval == ammo_tval)

    def _q2_ranged_core_key(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile,
        hostiles: list[MonsterState],
    ) -> str | None:
        if snapshot.player.blind or snapshot.player.confused:
            return None
        ammo = self._quest_profile_ammo(snapshot, profile)
        if ammo is None:
            return None
        ordered_races = (
            *profile.priority_targets,
            *sorted(
                {monster.race_id for monster in hostiles}
                - set(profile.priority_targets)
            ),
        )
        ordered_targets = [
            candidate
            for race_id in ordered_races
            for candidate in hostiles
            if candidate.race_id == race_id
        ]
        target = next(
            (
                candidate
                for race_id in ordered_races
                if (candidate := self._ranged_target(
                    snapshot,
                    [monster for monster in hostiles if monster.race_id == race_id],
                )) is not None
            ),
            None,
        )
        cursor_target = False
        if target is None:
            target = next(
                (
                    candidate
                    for candidate in ordered_targets
                    if 2
                    <= snapshot.player.position.distance_to(candidate.position)
                    <= RANGED_MAX_DISTANCE
                ),
                None,
            )
            cursor_target = target is not None
        if target is None:
            return None
        target_grid = snapshot.grid_at(target.position)
        light = self._first_item(
            snapshot,
            lambda item: item.tval == TVAL_SCROLL
            and item.sval == SV_SCROLL_LIGHT
            and item.aware,
        )
        light_key = (snapshot.floor_key, target.position)
        if (
            target_grid is not None
            and not target_grid.lit
            and light is not None
            and light_key not in self._quest_light_attempted
        ):
            self._quest_light_attempted.add(light_key)
            self.last_reason = (
                "quest-strategy:q2-light-area"
                if profile.quest_id == 2
                else "quest-strategy:ranged-light-area"
            )
            return self._read_key(snapshot, light)
        self.last_reason = (
            "quest-strategy:q2-fire"
            if profile.quest_id == 2
            else "quest-strategy:ranged-fire"
        )
        if cursor_target:
            if self._ranged_target_guard_position != snapshot.player.position:
                self._ranged_target_guard_position = snapshot.player.position
                self._ranged_target_attempts.clear()
                self._ranged_target_signatures.clear()
            previous_hp = self._ranged_target_signatures.get(target.index)
            if previous_hp is not None:
                if target.hp < previous_hp:
                    self._ranged_target_attempts[target.index] = 0
                else:
                    self._ranged_target_attempts[target.index] = (
                        self._ranged_target_attempts.get(target.index, 0) + 1
                    )
            if (
                self._ranged_target_attempts.get(target.index, 0)
                >= RANGED_TARGET_FAILURE_LIMIT
            ):
                return None
            aim = self._offset_fire_aim(
                snapshot, target, allow_direct_cursor=True
            )
            if aim is None:
                # Detection can expose a monster which has no clear projectile
                # path. Do not enter target mode in that state: `*t` leaves the
                # fire command waiting for a direction and repeats forever.
                # Returning None lets the Q2 placement route move to a reviewed
                # ranged-vantage cell instead.
                return None
            self._ranged_target_signatures[target.index] = target.hp
            return (
                FIRE_KEY
                + ammo.slot
                + "*p"
                + self._cursor_delta_keys(snapshot.player.position, aim)
                + "t5\x1b"
            )
        return (
            FIRE_KEY
            + ammo.slot
            + self._direction_key(snapshot.player.position, target.position)
        )

    def _q2_encounter_key(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        # Leaving an engaged breeder cluster fails Q2.  Once launcher
        # ammunition is exhausted, suppress the generic swarm reset and let
        # the caller's normal adjacent-melee path finish the breeders.
        melee_commit = (
            adjacent
            and all(monster.race_id == 202 for monster in adjacent)
            and self._quest_profile_ammo(snapshot, profile) is None
        )
        if not melee_commit and len(adjacent) >= SWARM_COUNT and not (
            snapshot.player.blind or snapshot.player.confused
        ):
            teleport = self._find_teleport_scroll(snapshot)
            if teleport is not None:
                self.last_reason = "quest-strategy:q2-teleport-reset"
                return self._read_key(snapshot, teleport)
        present = {monster.race_id for monster in hostiles}
        for race_id in (Q2_WERERAT_RACE, Q2_WHITE_CROCODILE_RACE):
            if race_id in present and race_id not in self._q2_speed_attempted:
                self._q2_speed_attempted.add(race_id)
                speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
                if speed is not None:
                    self._fixed_quest_speed_attempted = True
                    self.last_reason = "quest-strategy:q2-quaff-speed"
                    return QUAFF_KEY + speed.slot
        return None

    def _q2_breach_key(
        self, snapshot: Snapshot, navigator: QuestFloorNavigator
    ) -> str | None:
        # The live floor can contain already-dissolved cells which are walls in
        # the quest definition. Feed those confirmations back into static Q2
        # routing before approaching the dedicated firing point.
        navigator.opened.update(
            position
            for position, grid in snapshot.grids.items()
            if grid.enterable
            and navigator.battlefield.terrain.get((position.y, position.x)) == "wall"
        )
        corridor = [
            (position, snapshot.grid_at(position))
            for position in Q2_BREACH_CORRIDOR
        ]
        if all(grid is not None and grid.enterable for _, grid in corridor):
            navigator.opened.update(Q2_BREACH_CORRIDOR)
            self._q2_breach_complete = True
            return None

        # Tunnelling and stone-to-mud act on the first wall in the chosen
        # direction, not on the fixed far end of the corridor.  After each wall
        # opens, advance onto that cell before issuing the next command.  Staying
        # at the original firing point would target the newly opened floor and
        # repeat a zero-energy ``T2`` forever.
        breach_target = next(
            position
            for position, grid in corridor
            if grid is None or not grid.enterable
        )
        standing = Position(breach_target.y - 1, breach_target.x)
        if snapshot.player.position != standing:
            step = navigator.route_to_static_goals(
                snapshot.player.position, {standing}
            )
            if step is None:
                self.last_reason = "quest:blocked:q2-breach-route"
                return WAIT_KEY
            self.last_reason = "quest-strategy:q2-breach-approach"
            return self._step_toward(snapshot, step)

        if self._q2_breach_attempts >= Q2_BREACH_ATTEMPT_LIMIT:
            self.last_reason = "quest:blocked:q2-breach-attempts"
            return WAIT_KEY
        direction = "2"
        wand = self._first_item(
            snapshot,
            lambda item: item.tval == TVAL_WAND
            and item.sval == SV_WAND_STONE_TO_MUD
            and item.charges > 0,
        )
        if wand is not None:
            self._q2_breach_attempts += 1
            self.last_reason = "quest-strategy:q2-breach-wand"
            return AIM_WAND_KEY + wand.slot + direction

        equipped = self._equipped_digging_tool(snapshot)
        if equipped is None or equipped.pval < Q2_BREACH_MIN_DIGGING:
            strong = self._first_item(
                snapshot,
                lambda item: item.is_digging_tool
                and item.pval >= Q2_BREACH_MIN_DIGGING,
            )
            if strong is None:
                self.last_reason = "quest:blocked:q2-breach-tool"
                return WAIT_KEY
            main_hand = next(
                (item for item in snapshot.equipment if item.slot == "main_hand"),
                None,
            )
            if main_hand is not None and not main_hand.is_digging_tool:
                self._normal_weapon_name = main_hand.name
            self.last_reason = "quest-strategy:q2-breach-wield"
            return self._equipment_wield(
                snapshot, "q2-breach-loadout", strong, "main_hand"
            )

        self._q2_breach_attempts += 1
        self.last_reason = "quest-strategy:q2-breach-dig"
        return TUNNEL_KEY + direction

    def _q2_phase_key(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile,
        navigator: QuestFloorNavigator,
    ) -> str | None:
        info = self._quest_knowledge.get(2)
        battlefield = info.battlefield if info is not None else None
        if battlefield is None:
            return None

        navigator.opened.update(
            position
            for position, grid in snapshot.grids.items()
            if grid.enterable
            and battlefield.terrain.get((position.y, position.x)) == "wall"
        )

        current_kind = battlefield.terrain.get(
            (snapshot.player.position.y, snapshot.player.position.x)
        )
        navigator.allow_diagonal = True
        navigator.allow_deep_water = (
            252 not in self._q2_cleared_races
            or current_kind == "deep_water"
        )

        placements_by_race: dict[int, list[Position]] = {}
        for raw_position, race_id in battlefield.monster_placements:
            placements_by_race.setdefault(race_id, []).append(Position(*raw_position))

        visible_hostiles = [
            monster
            for monster in self._strategic_hostiles(snapshot)
            if monster.perception != "detected"
        ]
        uninterrupted_engagement = (
            self._visible_engagement_is_immobile_ranged_less(visible_hostiles)
        )
        if uninterrupted_engagement:
            ranged = self._q2_ranged_core_key(
                snapshot, profile, visible_hostiles
            )
            if ranged is not None:
                # Keep attacking from a usable firing cell.  Dry-ammo recovery
                # and a different target's static vantage set must not take this
                # decision away from the live engagement.
                return ranged
            adjacent_hostiles = [
                monster
                for monster in visible_hostiles
                if snapshot.player.position.distance_to(monster.position) <= 1
            ]
            if adjacent_hostiles and not snapshot.player.afraid:
                self.last_reason = "quest-strategy:melee"
                return self._direction_key(
                    snapshot.player.position,
                    self._weakest(adjacent_hostiles).position,
                )

        def recover_dry_ammo() -> str | None:
            if self._q2_ammo_recovery_floor != snapshot.floor_key:
                return None
            ammo_tval = self._quest_launcher_ammo(
                snapshot, profile.required_force
            )
            if ammo_tval is None:
                self.last_reason = "quest:blocked:q2-launcher-missing"
                return WAIT_KEY
            visible_corpses = [
                monster.position
                for monster in self._strategic_hostiles(snapshot)
                if monster.race_id == 202
            ]
            corpse_sources = {
                *placements_by_race.get(202, []),
                *visible_corpses,
            }
            corpse_buffer = {
                position
                for position in (
                    Position(y, x) for y, x in battlefield.terrain
                )
                if any(
                    position.distance_to(source) <= 1
                    for source in corpse_sources
                )
            }
            recovery_goals = {
                grid.position
                for grid in snapshot.grids.values()
                if grid.object_count > 0
                and ammo_tval in grid.object_tvals
                and grid.enterable
                and grid.position not in corpse_buffer
            }
            here = snapshot.grid_at(snapshot.player.position)
            if snapshot.player.position in recovery_goals and here is not None:
                self.last_reason = (
                    "quest-strategy:q2-recover-dry-ammo-candidate"
                )
                if here.object_count > 1:
                    return PICKUP_KEY + ("a" * here.object_count)
                return PICKUP_KEY
            # The corpse buffer can make the static route alternate across the
            # edge of a live corpse-mass cluster without ever getting closer to
            # the spent ammunition.  Recovery outranks residual-hostile combat,
            # so repeating that route would prevent us from engaging the very
            # cluster blocking it.  Drop the floor latch and let the caller's
            # ranged-then-melee residual handling take ownership.
            if recovery_goals and self._is_oscillating():
                self._q2_ammo_recovery_floor = None
                return None
            step = navigator.route_to_static_goals(
                snapshot.player.position,
                recovery_goals,
                blocked=corpse_buffer,
            )
            if step is not None:
                self.last_reason = (
                    "quest-strategy:q2-recover-dry-ammo-candidate"
                )
                return self._step_toward(snapshot, step)
            if self._quest_profile_ammo(snapshot, profile) is not None:
                self._q2_ammo_recovery_floor = None
                return None
            self.last_reason = "quest:blocked:q2-ammo-exhausted"
            return WAIT_KEY

        ammo_recovery = recover_dry_ammo()
        if ammo_recovery is not None:
            return ammo_recovery

        # Multipliers can survive away from their initial cells.  Once one is
        # visible, the live monster position outranks stale placement progress;
        # walking back to the entrance hold lets the group multiply unchecked.
        residual_hostiles = [
            monster
            for monster in self._strategic_hostiles(snapshot)
            if monster.race_id in Q2_BREEDER_RACES
        ]
        if residual_hostiles:
            target = min(
                residual_hostiles,
                key=lambda monster: snapshot.player.position.distance_to(
                    monster.position
                ),
            )
            self._q2_breeder_last_seen = target.position
            self._q2_breeder_last_seen_floor = snapshot.floor_key
            # A firing vantage is useful only while compatible ammunition is
            # actually available.  On the live Sewer cleanup, the launcher
            # spent its last bolt before the corpse masses finished
            # multiplying.  The phase router then treated its current cell as
            # a valid vantage and waited forever while seven stationary
            # breeders remained visible.  With no ammunition, close to a free
            # edge cell, then bump the breeder directly to commit the melee.
            if self._quest_profile_ammo(snapshot, profile) is None:
                adjacent_breeders = [
                    monster
                    for monster in residual_hostiles
                    if snapshot.player.position.distance_to(monster.position) == 1
                ]
                if adjacent_breeders:
                    melee_target = min(
                        adjacent_breeders,
                        key=lambda monster: snapshot.player.position.distance_to(
                            monster.position
                        ),
                    )
                    self.last_reason = "quest-strategy:q2-melee-corpse-attack"
                    return self._direction_key(
                        snapshot.player.position, melee_target.position
                    )
                occupied = {monster.position for monster in residual_hostiles}
                melee_goals = {
                    position
                    for position in (
                        Position(y, x) for y, x in battlefield.terrain
                    )
                    if position.distance_to(target.position) == 1
                    and navigator._static_walkable(position)
                    and position not in occupied
                }
                step = navigator.route_to_static_goals(
                    snapshot.player.position,
                    melee_goals,
                    blocked=occupied,
                )
                if step is not None:
                    self.last_reason = (
                        "quest-strategy:q2-close-residual-multiplier-no-ammo"
                    )
                    return self._step_toward(snapshot, step)
                self.last_reason = (
                    "quest-strategy:q2-close-residual-multiplier-no-ammo"
                )
                return self._direction_key(
                    snapshot.player.position, target.position
                )
            # A live multiplier must be pursued from a firing lane, never by
            # routing onto its occupied cell.  The old exact-cell route walked
            # into adjacency whenever a transient LOS failure prevented the
            # ranged block above from firing.  On the live Sewer final patrol,
            # one gremlin then multiplied around the player, consumed fourteen
            # teleport resets, and forced a quest-failing recall.
            ranged_vantages = {
                position
                for position in navigator.ranged_vantage_goals(
                    target.position, RANGED_MAX_DISTANCE
                )
                if position.distance_to(target.position) >= 2
            }
            breeder_buffer = {
                position
                for position in (
                    Position(y, x) for y, x in battlefield.terrain
                )
                if any(
                    position.distance_to(monster.position) <= 1
                    for monster in residual_hostiles
                )
            }
            breeder_buffer.discard(snapshot.player.position)
            ranged_vantages.difference_update(breeder_buffer)
            if snapshot.player.position in ranged_vantages:
                self.last_reason = "quest-strategy:q2-hold-residual-multiplier-vantage"
                return WAIT_KEY
            step = navigator.route_to_static_goals(
                snapshot.player.position,
                ranged_vantages,
                blocked=breeder_buffer,
            )
            if step is not None:
                self.last_reason = "quest-strategy:q2-approach-residual-multiplier"
                return self._step_toward(snapshot, step)
            self.last_reason = "quest:blocked:q2-residual-multiplier-vantage"
            return WAIT_KEY

        # Q2 progress lives in the explored map as well as in this process.  A
        # reconnect must not restart the ordered sewer sweep and walk back to
        # the opening rooms.  Reaching a later checkpoint is only possible
        # after the blue-jelly confirmation and bolt recovery in this strategy,
        # so restore every strictly earlier checkpoint monotonically.
        reached_post_blue = (
            [
                index
                for index, (_, _, placements) in enumerate(Q2_POST_BLUE_SEQUENCE)
                if any(
                    (grid := snapshot.grid_at(placement)) is not None and grid.known
                    for placement in placements
                )
            ]
            if self._q2_reconnect_recovery_floor == snapshot.floor_key
            else []
        )
        if reached_post_blue:
            reached_index = max(reached_post_blue)
            self._q2_breach_complete = True
            self._q2_cleared_races.update({86, 153, 252})
            self._q2_blue_recovery_complete = True
            for _, _, placements in Q2_POST_BLUE_SEQUENCE[:reached_index]:
                self._q2_surveyed_placements.update(placements)

            completed_post_blue_races = {
                race_id
                for _, race_id, placements in Q2_POST_BLUE_SEQUENCE
                if all(
                    placement in self._q2_surveyed_placements
                    for phase_label, phase_race, phase_placements
                    in Q2_POST_BLUE_SEQUENCE
                    if phase_race == race_id
                    for placement in phase_placements
                )
            }
            self._q2_cleared_races.update(completed_post_blue_races)

        # Illuminate the eastbound route immediately after the opening rats are
        # cleared. Waiting until the gremlin is visible is too late on this dark
        # floor, and one attempt per floor prevents consuming the whole reserve
        # if the read command is rejected.
        def light_after_opening() -> str | None:
            light_phase = (snapshot.floor_key, 153)
            in_cleared_opening_room = (
                snapshot.player.position.y <= 3
                and snapshot.player.position.x <= 7
            )
            if (
                86 not in self._q2_cleared_races
                and not in_cleared_opening_room
            ) or (
                153 in self._q2_cleared_races
                or light_phase in self._q2_phase_light_attempted
            ):
                return None
            light = self._first_item(
                snapshot,
                lambda item: item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_LIGHT
                and item.aware,
            )
            if light is not None:
                self._q2_phase_light_attempted.add(light_phase)
                self.last_reason = "quest-strategy:q2-light-after-opening"
                return self._read_key(snapshot, light)
            return None

        opening_light = light_after_opening()
        if opening_light is not None:
            return opening_light

        if (
            Q2_BREEDER_RACES <= self._q2_cleared_races
            and snapshot.player.hp < snapshot.player.max_hp
            and not self._physical_hostiles(snapshot)
        ):
            self.last_reason = "quest-strategy:q2-rest-between-engagements"
            return REST_MACRO

        def route_phase_placements(
            race_id: int,
            placements: list[Position] | tuple[Position, ...],
            reason: str,
        ) -> str | None:
            phase_key = (snapshot.floor_key, race_id)
            prior_move = self._q2_phase_last_move
            if prior_move is not None and prior_move[:2] == phase_key:
                _, _, origin, destination = prior_move
                failure_key = (*phase_key, origin, destination)
                if snapshot.player.position == origin:
                    self._q2_phase_step_failures[failure_key] += 1
                    if self._q2_phase_step_failures[failure_key] >= 3:
                        self._q2_phase_blocked_steps.setdefault(
                            phase_key, set()
                        ).add(destination)
                else:
                    self._q2_phase_step_failures.pop(failure_key, None)
                self._q2_phase_last_move = None

            blocked_steps = self._q2_phase_blocked_steps.get(phase_key, set())

            def phase_step(step: Position) -> str:
                self._q2_phase_last_move = (
                    snapshot.floor_key,
                    race_id,
                    snapshot.player.position,
                    step,
                )
                return self._step_toward(snapshot, step)

            for placement in placements:
                grid = snapshot.grid_at(placement)
                ranged_vantages = navigator.ranged_vantage_goals(
                    placement, RANGED_MAX_DISTANCE
                )
                observation_goals = ranged_vantages or navigator.observation_goals(
                    placement, RANGED_MAX_DISTANCE
                )
                if (
                    (
                        snapshot.player.position.distance_to(placement) <= 1
                        or grid is not None and grid.in_view
                    )
                    and grid is not None
                    and grid.known
                    and not grid.has_monster
                ):
                    self._q2_surveyed_placements.add(placement)
            unsurveyed = [
                placement for placement in placements
                if placement not in self._q2_surveyed_placements
            ]
            if not unsurveyed:
                return None

            for placement in unsurveyed:
                ranged_vantages = navigator.ranged_vantage_goals(
                    placement, RANGED_MAX_DISTANCE
                )
                placement_grid = snapshot.grid_at(placement)
                if (
                    snapshot.player.position in ranged_vantages
                    and (placement_grid is None or not placement_grid.in_view)
                ):
                    light_phase = (snapshot.floor_key, race_id, placement)
                    light = self._first_item(
                        snapshot,
                        lambda item: item.tval == TVAL_SCROLL
                        and item.sval == SV_SCROLL_LIGHT
                        and item.aware,
                    )
                    if (
                        light is not None
                        and light_phase not in self._q2_phase_light_attempted
                    ):
                        self._q2_phase_light_attempted.add(light_phase)
                        self.last_reason = f"quest-strategy:q2-light-phase-{race_id}"
                        return self._read_key(snapshot, light)

            goals: set[Position] = set()
            for placement in unsurveyed:
                phase_prefix = (snapshot.floor_key, race_id, placement)
                if navigator._static_walkable(placement):
                    goals.add(placement)
                ranged_vantages = navigator.ranged_vantage_goals(
                    placement, RANGED_MAX_DISTANCE
                )
                observation_goals = navigator.observation_goals(
                    placement, RANGED_MAX_DISTANCE
                )
                candidate_goals = ranged_vantages | observation_goals
                if navigator._static_walkable(placement):
                    candidate_goals.add(placement)
                if snapshot.player.position in candidate_goals:
                    self._q2_phase_visited_goals.add(
                        (*phase_prefix, snapshot.player.position)
                    )
                goals.update(
                    goal
                    for goal in candidate_goals
                    if (*phase_prefix, goal) not in self._q2_phase_visited_goals
                )
            goals.discard(snapshot.player.position)

            for placement in unsurveyed:
                route_key = (snapshot.floor_key, race_id, placement)
                route_target = self._q2_phase_route_targets.get(route_key)
                if route_target is None:
                    continue
                if snapshot.player.position == route_target:
                    self._q2_phase_route_targets.pop(route_key, None)
                    continue
                step = navigator.route_to_static_goals(
                    snapshot.player.position,
                    {route_target},
                    blocked=blocked_steps,
                )
                if step is not None:
                    self.last_reason = reason
                    return phase_step(step)
                self._q2_phase_route_targets.pop(route_key, None)

            goal_distances = {
                goal: min(goal.distance_to(placement) for placement in unsurveyed)
                for goal in goals
            }
            for distance in sorted(set(goal_distances.values())):
                path = navigator._static_path(
                    snapshot.player.position,
                    {goal for goal, rank in goal_distances.items() if rank == distance},
                    blocked=blocked_steps,
                )
                if len(path) > 1:
                    route_target = path[-1]
                    owner = min(
                        unsurveyed,
                        key=lambda placement: placement.distance_to(route_target),
                    )
                    self._q2_phase_route_targets[
                        (snapshot.floor_key, race_id, owner)
                    ] = route_target
                    self.last_reason = reason
                    return phase_step(path[1])
            self.last_reason = f"quest:blocked:{reason.removeprefix('quest-strategy:')}"
            return WAIT_KEY

        if (
            252 in self._q2_cleared_races
            and not self._q2_blue_recovery_complete
        ):
            posted = getattr(self, "_q2_blue_recovery_pickup_posted", None)
            if posted is not None:
                position, before = posted
                observed = snapshot.grid_at(position)
                after = (
                    (observed.object_count, observed.object_tvals)
                    if observed is not None else (0, ())
                )
                if after != before:
                    self._q2_blue_recovery_witnessed = True
                self._q2_blue_recovery_pickup_posted = None
            recovery_region = {
                position: grid
                for position, grid in snapshot.grids.items()
                if 7 <= position.y <= 13 and 45 <= position.x <= 49
            }
            recovery_cells = {
                position
                for position, grid in recovery_region.items()
                if grid.object_count > 0
                and TVAL_BOLT in grid.object_tvals
            }
            if snapshot.player.position in recovery_cells:
                self.last_reason = "quest-strategy:q2-blue-recover-bolts"
                here = snapshot.grid_at(snapshot.player.position)
                self._q2_blue_recovery_pickup_prepared = (
                    snapshot.player.position,
                    (here.object_count, here.object_tvals),
                )
                return PICKUP_KEY
            if recovery_cells:
                step = navigator.route_to_static_goals(
                    snapshot.player.position, recovery_cells
                )
                if step is None:
                    self.last_reason = "quest:blocked:q2-blue-recover-bolts"
                    return WAIT_KEY
                self.last_reason = "quest-strategy:q2-blue-recover-bolts"
                return self._step_toward(snapshot, step)
            if any(
                grid.object_count > 0 and not grid.object_tvals
                for grid in recovery_region.values()
            ):
                self.last_reason = "quest:blocked:q2-blue-recovery-unidentified-pile"
                return WAIT_KEY
            if not getattr(self, "_q2_blue_recovery_witnessed", False):
                self.last_reason = "quest:blocked:q2-blue-recovery-unwitnessed"
                return WAIT_KEY
            self._q2_blue_recovery_complete = True
            self.last_reason = "quest-strategy:q2-blue-recovery-complete"
            return WAIT_KEY

        if 252 in self._q2_cleared_races:
            for label, race_id, placements in Q2_POST_BLUE_SEQUENCE:
                action = route_phase_placements(
                    race_id,
                    placements,
                    f"quest-strategy:q2-post-blue-{label}",
                )
                if action is not None:
                    return action
                if all(
                    placement in self._q2_surveyed_placements
                    for _, phase_race, phase_placements in Q2_POST_BLUE_SEQUENCE
                    if phase_race == race_id
                    for placement in phase_placements
                ):
                    self._q2_cleared_races.add(race_id)

        breeder_target = self._q2_breeder_last_seen
        if (
            breeder_target is not None
            and self._q2_breeder_last_seen_floor == snapshot.floor_key
        ):
            target_grid = snapshot.grid_at(breeder_target)
            target_confirmed_clear = (
                target_grid is not None
                and target_grid.known
                and not target_grid.has_monster
                and (
                    target_grid.in_view
                    or snapshot.player.position.distance_to(breeder_target) <= 1
                )
            )
            if target_confirmed_clear:
                self._q2_breeder_last_seen = None
                self._q2_breeder_last_seen_floor = None
            else:
                step = navigator.route_to_static_goals(
                    snapshot.player.position, {breeder_target}
                )
                if step is not None:
                    self.last_reason = "quest-strategy:q2-breeder-recommit"
                    return self._step_toward(snapshot, step)
                self.last_reason = "quest:blocked:q2-breeder-recommit"
                return WAIT_KEY

        for race_id in profile.priority_targets:
            if race_id == 252 and not self._q2_breach_complete:
                breach_action = self._q2_breach_key(snapshot, navigator)
                if breach_action is not None:
                    return breach_action
            if race_id in self._q2_cleared_races:
                continue
            if race_id == 252:
                if snapshot.player.position != Q2_BLUE_CONFIRM_POSITION:
                    step = navigator.route_to_static_goals(
                        snapshot.player.position, {Q2_BLUE_CONFIRM_POSITION}
                    )
                    if step is None:
                        self.last_reason = "quest:blocked:q2-blue-confirm-route"
                        return WAIT_KEY
                    self.last_reason = "quest-strategy:q2-blue-confirm-approach"
                    return self._step_toward(snapshot, step)
                self._q2_cleared_races.add(252)
                navigator.allow_deep_water = False
                self.last_reason = "quest-strategy:q2-blue-clear-confirmed"
                return WAIT_KEY
            placements = placements_by_race.get(race_id, [])
            phase_action = route_phase_placements(
                race_id, placements, f"quest-strategy:q2-phase-{race_id}"
            )
            if phase_action is None:
                self._q2_cleared_races.add(race_id)
                if race_id == 86:
                    opening_light = light_after_opening()
                    if opening_light is not None:
                        return opening_light
                continue
            return phase_action

        # A placement sweep is not proof that a multiplying race is gone: its
        # descendants may now be outside the original cell's view. Revisit the
        # confirmed breeding areas after the ordered Q2 route completes.
        for race_id in Q2_RESIDUAL_SWEEP_RACES:
            if race_id in self._q2_residual_surveyed_races:
                continue
            placements = placements_by_race.get(race_id, [])
            unconfirmed: list[Position] = []
            for placement in placements:
                grid = snapshot.grid_at(placement)
                if not (
                    grid is not None
                    and grid.known
                    and not grid.has_monster
                    and (
                        grid.in_view
                        or snapshot.player.position.distance_to(placement) <= 1
                    )
                ):
                    unconfirmed.append(placement)
            if not unconfirmed:
                self._q2_residual_surveyed_races.add(race_id)
                self.last_reason = f"quest-strategy:q2-residual-{race_id}-clear"
                return WAIT_KEY

            goals: set[Position] = set()
            for placement in unconfirmed:
                residual_race = -race_id
                phase_prefix = (snapshot.floor_key, residual_race, placement)
                observation_goals = navigator.observation_goals(
                    placement, RANGED_MAX_DISTANCE
                )
                if snapshot.player.position in observation_goals:
                    self._q2_phase_visited_goals.add(
                        (*phase_prefix, snapshot.player.position)
                    )
                goals.update(
                    goal
                    for goal in observation_goals
                    if (*phase_prefix, goal) not in self._q2_phase_visited_goals
                )
            goals.discard(snapshot.player.position)
            residual_reason = f"quest-strategy:q2-residual-{race_id}-sweep"
            for placement in unconfirmed:
                route_key = (snapshot.floor_key, -race_id, placement)
                route_target = self._q2_phase_route_targets.get(route_key)
                if route_target is None:
                    continue
                if snapshot.player.position == route_target:
                    self._q2_phase_route_targets.pop(route_key, None)
                    continue
                step = navigator.route_to_static_goals(
                    snapshot.player.position, {route_target}
                )
                if step is not None:
                    self.last_reason = residual_reason
                    return self._step_toward(snapshot, step)
                self._q2_phase_route_targets.pop(route_key, None)

            goal_distances = {
                goal: min(goal.distance_to(placement) for placement in unconfirmed)
                for goal in goals
            }
            for distance in sorted(set(goal_distances.values())):
                path = navigator._static_path(
                    snapshot.player.position,
                    {goal for goal, rank in goal_distances.items() if rank == distance},
                )
                if len(path) <= 1:
                    continue
                route_target = path[-1]
                owner = min(
                    unconfirmed,
                    key=lambda placement: placement.distance_to(route_target),
                )
                self._q2_phase_route_targets[
                    (snapshot.floor_key, -race_id, owner)
                ] = route_target
                self.last_reason = residual_reason
                return self._step_toward(snapshot, path[1])
            self.last_reason = f"quest:blocked:q2-residual-{race_id}-sweep"
            return WAIT_KEY

        # Initial placement checks cannot find monsters that teleported or
        # wandered into another room. Record the cells actually visible during
        # a full-map patrol and route toward the nearest unseen walkable cell.
        # When every reachable cell has been viewed, begin another patrol until
        # the game reports quest completion.
        self._q2_final_patrol_visited.update(
            position
            for position, grid in snapshot.grids.items()
            if grid.in_view and navigator._static_walkable(position)
        )
        self._q2_final_patrol_visited.add(snapshot.player.position)
        target = self._q2_final_patrol_target
        if target is not None:
            if target in self._q2_final_patrol_visited:
                self._q2_final_patrol_target = None
            else:
                step = navigator.route_to_static_goals(
                    snapshot.player.position, {target}
                )
                if step is not None:
                    self.last_reason = "quest-strategy:q2-final-patrol"
                    return self._step_toward(snapshot, step)
                self._q2_final_patrol_target = None

        unseen = {
            Position(y, x)
            for (y, x) in battlefield.terrain
            if navigator._static_walkable(Position(y, x))
            and Position(y, x) not in self._q2_final_patrol_visited
        }
        path = navigator._static_path(snapshot.player.position, unseen)
        if len(path) > 1:
            self._q2_final_patrol_target = path[-1]
            self.last_reason = "quest-strategy:q2-final-patrol"
            return self._step_toward(snapshot, path[1])

        self._q2_final_patrol_visited.clear()
        self._q2_final_patrol_target = None
        self.last_reason = "quest-strategy:q2-final-patrol-round-complete"
        return WAIT_KEY

    def _quest_strategy_route_step(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile,
        goal: Position,
    ) -> Position | None:
        info = self._quest_knowledge.get(profile.quest_id)
        battlefield = info.battlefield if info is not None else None
        blocked = {
            Position(*raw)
            for raw in profile.engagement_plan.get("avoid_door_positions", ())
        }
        cleared_targets = self._quest_strategy_cleared_targets.get(
            profile.quest_id, set()
        )
        for plan in profile.engagement_plan.get("throwing_points", ()):
            target = Position(*plan["target"])
            target_key = (
                int(plan.get("race_id", 0)), target.y, target.x
            )
            if target_key not in cleared_targets:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        blocked.add(Position(target.y + dy, target.x + dx))
            recovery_cells = {
                Position(*raw) for raw in plan.get("recovery_cells", ())
            }
            if (
                target_key in cleared_targets
                and snapshot.player.position in recovery_cells
            ):
                blocked.difference_update(recovery_cells)
            if target_key not in cleared_targets and snapshot.player.position == target:
                # A restart can lose the durable cleared-target set while the
                # player is already standing on that target.  Its reviewed
                # recovery lane is then the only safe escape from its own halo.
                blocked.difference_update(recovery_cells)
        blocked.discard(snapshot.player.position)
        final_door_value = profile.engagement_plan.get("final_door")
        if final_door_value is not None:
            final_door = Position(*final_door_value)
            final_door_grid = snapshot.grid_at(final_door)
            if (
                final_door_grid is not None
                and final_door_grid.known
                and not final_door_grid.is_closed_door
            ):
                blocked.discard(final_door)
        blocked.discard(goal)
        if battlefield is not None:
            navigator = self._quest_navigators.setdefault(
                profile.quest_id,
                QuestFloorNavigator(profile.quest_id, battlefield),
            )
            step = navigator.route_to_static_goals(
                snapshot.player.position,
                {goal},
                blocked=blocked,
            )
            if step is not None:
                return step
        return self._town_map_goal_step(snapshot, goal, blocked=blocked)

    def _quest_execute_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        """Execute an approved profile only on its own quest floor."""
        profile = self.approved_quest_strategy(snapshot.floor_key[2])
        if profile is None:
            return None

        reposition = profile.engagement_plan.get("opening_reposition")
        if isinstance(reposition, dict):
            phase = self._quest_strategy_opening_phase.get(profile.quest_id, 0)
            goals = {
                Position(*raw) for raw in reposition.get("goal_points", ())
            }
            quest_info = self._quest_knowledge.get(profile.quest_id)
            opening_battlefield = (
                quest_info.battlefield if quest_info is not None else None
            )
            opening_start = (
                Position(*opening_battlefield.player_start)
                if opening_battlefield is not None
                and opening_battlefield.player_start is not None
                else (
                    Position(*opening_battlefield.entrance)
                    if opening_battlefield is not None
                    and opening_battlefield.entrance is not None
                    else None
                )
            )
            # Opening state is in-memory, but the game can remain on a quest
            # floor while the external bot is restarted.  An approved hold cell
            # is durable evidence that speed+teleport+reposition already ran;
            # reconstruct phase 3 instead of consuming both supplies again.
            if phase == 0 and snapshot.player.position in goals:
                self._quest_strategy_hold_positions[profile.quest_id] = (
                    snapshot.player.position
                )
                self._quest_strategy_opening_phase[profile.quest_id] = 3
                if profile.quest_id != 22:
                    self._fixed_quest_speed_attempted = True
                phase = 3
            elif phase == 0 and opening_start is not None and (
                snapshot.player.position != opening_start
            ):
                # A restart can occur one command after the logged position, so
                # exact hold matching is too narrow.  Anywhere off the fixed
                # player start proves that the opening consumables were already
                # sent.  Compare with the fixed P: player start rather than the
                # quest-exit stair: Q22 starts at (1,33), while its stair is at
                # (1,29).  Reconstruct phase 2 and finish routing to a reviewed
                # hold instead of spending Speed and Teleport again.
                self._quest_strategy_opening_phase[profile.quest_id] = 2
                if profile.quest_id != 22:
                    self._fixed_quest_speed_attempted = True
                if opening_battlefield is not None:
                    self._quest_navigators.setdefault(
                        profile.quest_id,
                        QuestFloorNavigator(profile.quest_id, opening_battlefield),
                    )
                phase = 2
            if phase == 0:
                self._quest_strategy_opening_phase[profile.quest_id] = 1
                speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
                if speed is not None:
                    if profile.quest_id != 22:
                        self._fixed_quest_speed_attempted = True
                    self.last_reason = (
                        "quest-strategy:q22-opening-speed"
                        if profile.quest_id == 22
                        else "quest-strategy:opening-speed"
                    )
                    return QUAFF_KEY + speed.slot
                phase = 1
            if phase == 1:
                self._quest_strategy_opening_phase[profile.quest_id] = 2
                teleport = self._find_teleport_scroll(snapshot)
                if teleport is not None:
                    self.last_reason = (
                        "quest-strategy:q22-opening-teleport"
                        if profile.quest_id == 22
                        else "quest-strategy:opening-teleport"
                    )
                    return self._read_key(snapshot, teleport)
                phase = 2
            if phase == 2:
                navigator = self._quest_navigators.get(profile.quest_id)
                if navigator is not None and goals:
                    hold = self._quest_strategy_hold_positions.get(profile.quest_id)
                    if hold is None:
                        routes = [
                            navigator._static_path(snapshot.player.position, {goal})
                            for goal in goals
                        ]
                        routes = [route for route in routes if route]
                        if routes:
                            route = min(
                                routes,
                                key=lambda candidate: (
                                    len(candidate), candidate[-1].y, candidate[-1].x
                                ),
                            )
                            hold = route[-1]
                            self._quest_strategy_hold_positions[profile.quest_id] = hold
                    if hold is not None and snapshot.player.position == hold:
                        self._quest_strategy_opening_phase[profile.quest_id] = 3
                    elif hold is not None and not adjacent:
                        blocked = {
                            monster.position for monster in hostiles
                        }
                        step = navigator.route_to_static_goals(
                            snapshot.player.position, {hold}, blocked=blocked
                        )
                        if step is not None:
                            self.last_reason = (
                                "quest-strategy:q22-opening-reposition"
                                if profile.quest_id == 22
                                else "quest-strategy:opening-reposition"
                            )
                            return self._step_toward(snapshot, step)

        # Fixed quest profiles may identify doors that are intentionally much
        # harder than ordinary doors. Keep every tactical route from treating
        # them as cheap enterable cells.
        for raw_position in profile.engagement_plan.get(
            "avoid_door_positions", ()
        ):
            self._door_t.discard(tuple(raw_position))

        abort = profile.abort_conditions
        if (
            bool(abort.get("allowed", False))
            and snapshot.player.hp_ratio <= float(abort.get("hp_ratio", 0))
        ):
            here = snapshot.grid_at(snapshot.player.position)
            if here is not None and here.has_up_stairs:
                self.last_reason = "quest-strategy:abort"
                return UP_STAIRS_KEY
            escape = self._escape_by_stairs(snapshot)
            if escape is not None:
                self.last_reason = "quest-strategy:abort"
                return escape
            if snapshot.floor_key[2] in FIXED_QUEST_ALLOWLIST:
                exit_key = self._fixed_quest_exit_key(snapshot, snapshot.floor_key[2])
                if exit_key is not None:
                    self.last_reason = "quest-strategy:abort"
                    return exit_key

        if profile.quest_id == 2:
            encounter = self._q2_encounter_key(
                snapshot, profile, hostiles, adjacent
            )
            if encounter is not None:
                return encounter

        # Q34 provides a brass lantern at the end of the safe outer-right
        # corridor.  Its radius-2 light is part of the approved fixed-target
        # contract: from a distance-2 throwing point, a torch cannot prove that
        # the target cell is empty.  Pick up and equip the lantern before any
        # door, combat, or fixed-target phase, and fail closed if it disappeared.
        opening_light = profile.engagement_plan.get("opening_light")
        if isinstance(opening_light, dict):
            equipped_lantern = next(
                (item for item in snapshot.equipment if item.is_lantern), None
            )
            if equipped_lantern is None:
                carried_lantern = self._first_item(
                    snapshot, lambda item: item.is_lantern
                )
                if carried_lantern is not None:
                    self.last_reason = "quest-strategy:equip-opening-lantern"
                    return self._equipment_wield(
                        snapshot, "quest-launcher", carried_lantern, "light"
                    )

                light_position = Position(*opening_light["position"])
                if snapshot.player.position == light_position:
                    here = snapshot.grid_at(light_position)
                    if here is not None and here.object_count > 0:
                        self.last_reason = "quest-strategy:pickup-opening-lantern"
                        return PICKUP_KEY
                    self.last_reason = "quest:blocked:opening-lantern-missing"
                    return WAIT_KEY

                step = self._quest_strategy_route_step(
                    snapshot, profile, light_position
                )
                if step is not None:
                    self.last_reason = "quest-strategy:approach-opening-lantern"
                    return self._step_toward(snapshot, step)
                self.last_reason = "quest:blocked:opening-lantern-unreachable"
                return WAIT_KEY

        opening_door = profile.engagement_plan.get("opening_door")
        opening_corner = profile.engagement_plan.get("opening_corner")
        opening_approach = profile.engagement_plan.get("opening_approach")
        if opening_door is not None and opening_approach is not None:
            door = Position(*opening_door)
            approach = Position(*opening_approach)
            door_grid = snapshot.grid_at(door)
            recovery_bounds = profile.engagement_plan.get("supply_recovery_bounds")
            inside_opened_area = False
            if recovery_bounds is not None:
                min_y, min_x, max_y, max_x = recovery_bounds
                inside_opened_area = (
                    min_y <= snapshot.player.position.y <= max_y
                    and min_x <= snapshot.player.position.x <= max_x
                )
            opening_complete = (
                inside_opened_area
                or (
                    door_grid is not None
                    and door_grid.known
                    and not door_grid.is_closed_door
                )
            )
            if not opening_complete:
                if snapshot.player.position != approach:
                    route_goal = approach
                    if opening_corner is not None:
                        corner = Position(*opening_corner)
                        if snapshot.player.position.x != corner.x:
                            route_goal = corner
                    step = self._quest_strategy_route_step(
                        snapshot, profile, route_goal
                    )
                    if step is None:
                        self.last_reason = "quest-strategy:opening-door-unreachable"
                        return WAIT_KEY
                    self.last_reason = "quest-strategy:approach-opening-door"
                    return self._step_toward(snapshot, step)
                if door_grid is None or not door_grid.known:
                    self.last_reason = "quest-strategy:search-opening-door"
                    return SEARCH_KEY
                self.last_reason = "quest-strategy:open-opening-door"
                return self._step_toward(snapshot, door)

        if (
            hostiles
            and not isinstance(reposition, dict)
            and not self._fixed_quest_speed_attempted
        ):
            threshold = float(
                profile.consumable_plan.get("speed_potion_use_when", {}).get(
                    "expected_damage_hp_ratio_min", 1.0
                )
            )
            projected = self.threat_prediction(snapshot, hostiles, turns=3)[
                "operational_total"
            ]
            if projected >= threshold * snapshot.player.hp:
                self._fixed_quest_speed_attempted = True
                speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
                if speed is not None:
                    self.last_reason = "quest-strategy:quaff-speed"
                    return QUAFF_KEY + speed.slot

        hold_value = profile.engagement_plan.get("hold_position")
        hold = self._quest_strategy_hold_positions.get(profile.quest_id)
        if hold is None and hold_value is not None:
            hold = Position(*hold_value)
        never_move_races = self._quest_never_move_races(profile)
        mobile_visible = any(
            monster.race_id not in never_move_races for monster in hostiles
        )
        initial_hold_budget = max(
            0, int(profile.engagement_plan.get("initial_hold_turns", 0))
        )
        post_wave_phase_started = (
            profile.quest_id in self._quest_strategy_post_wave_light_attempted
        )
        opening_hold_complete = (
            self._quest_strategy_initial_hold_turns.get(profile.quest_id, 0)
            >= initial_hold_budget
        )
        if mobile_visible and not (
            post_wave_phase_started or opening_hold_complete
        ):
            self._quest_strategy_initial_hold_turns[profile.quest_id] = 0
        initial_hold_complete = (
            post_wave_phase_started
            or opening_hold_complete
        )

        # Some fixed maps begin with a mobile wave that should be absorbed at a
        # chokepoint before illuminating the next area.  Once that quiet hold is
        # complete, let the placement-sweep route advance the configured number
        # of steps, then read Light before any newly revealed target is required.
        post_wave_light_configured = "post_wave_light_steps" in profile.engagement_plan
        post_wave_light_steps = max(
            0, int(profile.engagement_plan.get("post_wave_light_steps", 0))
        )
        if (
            initial_hold_complete
            and post_wave_light_configured
            and profile.quest_id
            not in self._quest_strategy_post_wave_light_attempted
            and hold is not None
            and snapshot.player.position.distance_to(hold)
            >= post_wave_light_steps
        ):
            # Reaching the reviewed reading point is durable phase evidence.
            # After an external-bot restart the scroll may already be gone
            # because it was read before the restart; latch the phase even when
            # there is no remaining scroll instead of restarting wave one.
            self._quest_strategy_post_wave_light_attempted.add(profile.quest_id)
            light = self._first_item(
                snapshot,
                lambda item: item.tval == TVAL_SCROLL
                and item.sval == SV_SCROLL_LIGHT
                and item.aware,
            )
            if light is not None:
                self.last_reason = "quest-strategy:post-wave-light"
                return self._read_key(snapshot, light)
        current_never_move = {
            monster.index for monster in hostiles
            if monster.race_id in never_move_races
        }
        previous_never_move = self._quest_strategy_visible_never_move.get(
            profile.quest_id, set()
        )
        defeated_never_move = self._quest_strategy_defeated_never_move.setdefault(
            profile.quest_id, set()
        )
        defeated_never_move.update(previous_never_move - current_never_move)
        self._quest_strategy_visible_never_move[profile.quest_id] = current_never_move
        current_targets = {
            (monster.race_id, monster.position.y, monster.position.x)
            for monster in hostiles
            if monster.race_id in never_move_races
        }
        previous_targets = self._quest_strategy_visible_targets.get(
            profile.quest_id, set()
        )
        throwing_points = profile.engagement_plan.get("throwing_points", ())
        # A stationary target disappearing from the visible-monster list is not
        # itself proof of death: changing light/FOV can hide a living target.
        # Confirm its known fixed cell is currently visible and empty before
        # unlocking torch recovery through the target's adjacent lane.
        newly_defeated_targets = {
            target
            for target in previous_targets - current_targets
            if (
                (target_grid := snapshot.grid_at(Position(target[1], target[2])))
                is not None
                and target_grid.known
                and target_grid.in_view
                and not target_grid.has_monster
                and (
                    profile.quest_id != 34
                    or any(
                        (
                            int(plan.get("race_id", 0)),
                            int(plan["target"][0]),
                            int(plan["target"][1]),
                        ) == target
                        and snapshot.player.position == Position(*plan["stand"])
                        for plan in throwing_points
                    )
                )
            )
        }
        self._quest_strategy_visible_targets[profile.quest_id] = current_targets
        cleared_targets = self._quest_strategy_cleared_targets.setdefault(
            profile.quest_id, set()
        )
        cleared_targets.update(newly_defeated_targets)
        recoverable_tvals = (
            {TVAL_LITE}
            if profile.quest_id == 34
            else {
                ammo_tval
                for ammo_tval in (
                    self._quest_launcher_ammo(snapshot, profile.required_force),
                )
                if ammo_tval is not None
            }
        )
        if (
            profile.quest_id == 31
            and profile.quest_id in self._quest_strategy_pending_recovery
            and not recoverable_tvals
            and initial_hold_complete
        ):
            self.last_reason = "quest:blocked:q31-recovery-no-launcher-ammo"
            return WAIT_KEY

        def recovery_substrate(cell_grid: GridState | None) -> bool:
            return bool(
                cell_grid is not None
                and cell_grid.object_count > 0
                and recoverable_tvals.intersection(cell_grid.object_tvals)
            )

        posted_pickup = self._quest_strategy_recovery_pickup_posted
        if posted_pickup is not None and posted_pickup[0] == profile.quest_id:
            _, posted_position, before = posted_pickup
            observed = snapshot.grid_at(posted_position)
            after = (
                (observed.object_count, observed.object_tvals)
                if observed is not None
                else (0, ())
            )
            claims = self._quest_strategy_recovery_claims.setdefault(
                profile.quest_id, set()
            )
            claim = (posted_position.y, posted_position.x, before)
            if after == before:
                claims.add(claim)
            else:
                claims.discard(claim)
            self._quest_strategy_recovery_pickup_posted = None
        claims = self._quest_strategy_recovery_claims.setdefault(
            profile.quest_id, set()
        )
        for claim in tuple(claims):
            y, x, claimed_state = claim
            observed = snapshot.grid_at(Position(y, x))
            if observed is not None and (
                observed.object_count, observed.object_tvals
            ) != claimed_state:
                claims.discard(claim)
        if profile.quest_id == 34:
            # Q34 progress must survive an external bot restart. Reaching one
            # of an ordered target's recovery cells with its entire recovery
            # lane visible and empty is durable evidence that the target and
            # every earlier target were killed and their torches collected.
            for index, plan in enumerate(throwing_points):
                recovery_cells = [
                    Position(*raw) for raw in plan.get("recovery_cells", ())
                ]
                if (
                    snapshot.player.position not in recovery_cells
                    or not recovery_cells
                    or not all(
                        (cell_grid := snapshot.grid_at(cell)) is not None
                        and cell_grid.known
                        and cell_grid.in_view
                        and not cell_grid.has_monster
                        and not recovery_substrate(cell_grid)
                        for cell in recovery_cells
                    )
                ):
                    continue
                for completed in throwing_points[: index + 1]:
                    target = Position(*completed["target"])
                    cleared_targets.add(
                        (int(completed.get("race_id", 0)), target.y, target.x)
                    )
                break
        if (
            newly_defeated_targets
            and profile.quest_id not in self._quest_strategy_pending_recovery
        ):
            recovery_plan = next(
                (
                    plan
                    for plan in profile.engagement_plan.get("throwing_points", ())
                    if (
                        int(plan.get("race_id", 0)),
                        int(plan["target"][0]),
                        int(plan["target"][1]),
                    ) in newly_defeated_targets
                ),
                None,
            )
            if recovery_plan is not None:
                self._quest_strategy_pending_recovery[profile.quest_id] = recovery_plan
        info = self._quest_knowledge.get(profile.quest_id)
        battlefield = info.battlefield if info is not None else None
        expected_never_move = sum(
            placed_race in never_move_races
            for _, placed_race in (
                battlefield.monster_placements if battlefield is not None else ()
            )
        )
        final_target_phase = (
            (
                len(cleared_targets) >= len(throwing_points)
                if throwing_points
                else (
                    expected_never_move > 0
                    and len(defeated_never_move) >= expected_never_move
                )
            )
            and not current_never_move
        )
        if final_target_phase and profile.quest_id != 2:
            survival = self._survival_gate_key(snapshot, hostiles)
            if survival is not None:
                return survival

        pending_recovery = self._quest_strategy_pending_recovery.get(
            profile.quest_id
        )
        recovery_is_safe = (
            profile.quest_id != 31
            or (initial_hold_complete and not mobile_visible)
        )
        if pending_recovery is not None and recovery_is_safe:
            recovery_target_key = (
                int(pending_recovery.get("race_id", 0)),
                int(pending_recovery["target"][0]),
                int(pending_recovery["target"][1]),
            )
            if recovery_target_key not in cleared_targets:
                # Recovery lanes intentionally enter the target's adjacent
                # cells.  Never unlock one from stale or inferred state.
                self._quest_strategy_pending_recovery.pop(profile.quest_id, None)
                self.last_reason = "quest:blocked:unconfirmed-target-recovery"
                return WAIT_KEY
            recovery_cells = {
                Position(*raw)
                for raw in pending_recovery.get("recovery_cells", ())
            }
            here = snapshot.grid_at(snapshot.player.position)
            if (
                snapshot.player.position in recovery_cells
                and here is not None
                and recovery_substrate(here)
                and (
                    snapshot.player.position.y,
                    snapshot.player.position.x,
                    (here.object_count, here.object_tvals),
                ) not in self._quest_strategy_recovery_claims.setdefault(
                    profile.quest_id, set()
                )
            ):
                self.last_reason = "quest-strategy:recover-defeated-target-torches"
                self._quest_strategy_recovery_pickup_prepared = (
                    profile.quest_id,
                    snapshot.player.position,
                    (here.object_count, here.object_tvals),
                )
                if here.object_count > 1:
                    key = PICKUP_KEY + ("a" * here.object_count)
                else:
                    key = PICKUP_KEY
                self._quest_strategy_recovery_pickup_prepared_key = key
                return key
            recovery_goals = sorted(
                (
                    candidate.position
                    for candidate in snapshot.grids.values()
                    if candidate.position in recovery_cells
                    and recovery_substrate(candidate)
                    and (
                        candidate.position.y,
                        candidate.position.x,
                        (candidate.object_count, candidate.object_tvals),
                    ) not in self._quest_strategy_recovery_claims.setdefault(
                        profile.quest_id, set()
                    )
                ),
                key=lambda position: (
                    snapshot.player.position.distance_to(position),
                    position.y,
                    position.x,
                ),
            )
            for recovery_goal in recovery_goals:
                pickup_step = self._quest_strategy_route_step(
                    snapshot, profile, recovery_goal
                )
                if pickup_step is not None:
                    self.last_reason = (
                        "quest-strategy:recover-defeated-target-torches"
                    )
                    return self._step_toward(snapshot, pickup_step)
            remaining_piles = any(
                candidate.position in recovery_cells
                and recovery_substrate(candidate)
                for candidate in snapshot.grids.values()
            )
            self._quest_strategy_pending_recovery.pop(profile.quest_id, None)
            self.last_reason = (
                "quest:blocked:q34-recovery-no-progress"
                if profile.quest_id == 34 and remaining_piles
                else "quest-strategy:recovery-complete"
            )
            return WAIT_KEY

        immediate_targets = self._immediate_quest_targets(profile, hostiles)
        combat_hostiles = immediate_targets or hostiles
        combat_indices = {monster.index for monster in combat_hostiles}
        mobile_adjacent = [
            monster for monster in adjacent
            if monster.index in combat_indices
            and monster.race_id not in never_move_races
        ]
        forced_adjacent = [
            monster for monster in adjacent
            if monster.index in combat_indices
            and profile.quest_id == 31
            and monster.race_id in never_move_races
        ]
        engage_adjacent = mobile_adjacent + forced_adjacent
        if engage_adjacent and not snapshot.player.afraid:
            ranked = sorted(
                engage_adjacent,
                key=lambda monster: (
                    profile.priority_targets.index(monster.race_id)
                    if monster.race_id in profile.priority_targets else len(profile.priority_targets),
                    monster.hp,
                ),
            )
            self.last_reason = "quest-strategy:melee"
            return self._direction_key(snapshot.player.position, ranked[0].position)

        if profile.required_force.get("launcher") and combat_hostiles:
            ranged = self._q2_ranged_core_key(snapshot, profile, combat_hostiles)
            if ranged is not None:
                return ranged

        # A priority summoner outside launcher range must be hunted now rather
        # than letting the ordered placement sweep advance to another race.
        # Once it enters range, the ranged block above takes over; once
        # adjacent, the melee block does. Lethal danger and an actual summoned
        # swarm still preempt this commitment in the emergency layer.
        if immediate_targets:
            target = min(
                immediate_targets,
                key=lambda monster: (
                    snapshot.player.position.distance_to(monster.position),
                    monster.hp,
                ),
            )
            step = self._quest_strategy_route_step(
                snapshot, profile, target.position
            )
            if step is not None:
                self.last_reason = (
                    f"quest-strategy:q2-hunt-priority-{target.race_id}"
                )
                return self._step_toward(snapshot, step)
            self.last_reason = (
                f"quest:blocked:q2-hunt-priority-{target.race_id}"
            )
            return WAIT_KEY

        if combat_hostiles:
            next_throw_plan = next(
                (
                    plan
                    for plan in throwing_points
                    if (
                        int(plan.get("race_id", 0)),
                        int(plan["target"][0]),
                        int(plan["target"][1]),
                    ) not in cleared_targets
                ),
                None,
            )
            if next_throw_plan is not None:
                planned_target = Position(*next_throw_plan["target"])
                targets = [
                    monster for monster in combat_hostiles
                    if monster.race_id == int(next_throw_plan["race_id"])
                    and monster.position == planned_target
                ]
                configured_targets_visible = any(
                    monster.race_id == int(plan.get("race_id", 0))
                    and monster.position == Position(*plan["target"])
                    for plan in throwing_points
                    for monster in combat_hostiles
                )
                if not targets and not configured_targets_visible:
                    present = {monster.race_id for monster in combat_hostiles}
                    active_race = next(
                        (
                            race_id
                            for race_id in profile.priority_targets
                            if race_id in present
                        ),
                        None,
                    )
                    targets = [
                        monster for monster in combat_hostiles
                        if monster.race_id == active_race
                    ]
            else:
                present = {monster.race_id for monster in combat_hostiles}
                active_race = next(
                    (
                        race_id
                        for race_id in profile.priority_targets
                        if race_id in present
                    ),
                    None,
                )
                targets = [
                    monster for monster in combat_hostiles
                    if monster.race_id == active_race
                ]
            torch = self._first_item(snapshot, lambda item: item.is_torch)
            throwing_points = profile.engagement_plan.get("throwing_points", ())
            planned_throw = next(
                (
                    (plan, monster)
                    for plan in throwing_points
                    for monster in targets
                    if int(plan.get("race_id", 0)) == monster.race_id
                    and Position(*plan["target"]) == monster.position
                ),
                None,
            )
            if planned_throw is not None:
                plan, target_monster = planned_throw
                stand = Position(*plan["stand"])
                if snapshot.player.position != stand:
                    step = self._quest_strategy_route_step(
                        snapshot, profile, stand
                    )
                    if step is None:
                        self.last_reason = (
                            "quest:blocked:q34-throw-point-unreachable"
                            if profile.quest_id == 34
                            else "quest-strategy:throw-point-unreachable"
                        )
                        return WAIT_KEY
                    self.last_reason = "quest-strategy:approach-throw-point"
                    return self._step_toward(snapshot, step)
                if torch is not None:
                    self.last_reason = "quest-strategy:throw-torch"
                    return (
                        THROW_KEY + torch.slot
                        + self._direction_key(
                            snapshot.player.position, target_monster.position
                        )
                    )
            if (
                profile.quest_id == 34
                and planned_throw is None
                and any(
                    monster.race_id in never_move_races for monster in targets
                )
            ):
                self.last_reason = "quest:blocked:throw-outside-approved-point"
                return WAIT_KEY
            if profile.quest_id != 34 and torch is not None and targets:
                target = self._ranged_target(snapshot, targets)
                if target is not None:
                    self.last_reason = "quest-strategy:throw-torch"
                    return (
                        THROW_KEY + torch.slot
                        + self._direction_key(snapshot.player.position, target.position)
                    )

        # Once the opening hold/light phase is complete, the placement sweep
        # owns movement.  A mobile enemy can flicker into view at the edge of
        # that route without a usable firing line; retreating all the way to the
        # original hold then makes the enemy disappear and creates a two-cell
        # sweep/retake cycle.  Close on that one observed mobile target locally.
        if post_wave_phase_started:
            mobile_targets = [
                monster for monster in combat_hostiles
                if monster.race_id not in never_move_races
            ]
            if mobile_targets:
                target = min(
                    mobile_targets,
                    key=lambda monster: (
                        profile.priority_targets.index(monster.race_id)
                        if monster.race_id in profile.priority_targets
                        else len(profile.priority_targets),
                        snapshot.player.position.distance_to(monster.position),
                        monster.hp,
                    ),
                )
                step = self._quest_strategy_route_step(
                    snapshot, profile, target.position
                )
                if step is not None:
                    self.last_reason = "quest-strategy:sweep-engage-mobile"
                    return self._step_toward(snapshot, step)

        # A restarted bot has no in-memory record of fixed targets killed
        # earlier in the same quest. Revisit the approved firing points in
        # order; from each point the target cell is directly observable, so an
        # empty cell safely reconstructs both defeat and recovery state.
        if throwing_points and not final_target_phase and initial_hold_complete:
            survey_plan = next(
                (
                    plan
                    for plan in throwing_points
                    if (
                        int(plan.get("race_id", 0)),
                        int(plan["target"][0]),
                        int(plan["target"][1]),
                    ) not in cleared_targets
                ),
                None,
            )
            if survey_plan is not None:
                stand = Position(*survey_plan["stand"])
                if snapshot.player.position != stand:
                    step = self._quest_strategy_route_step(
                        snapshot, profile, stand
                    )
                    if step is not None:
                        self.last_reason = "quest-strategy:survey-throw-point"
                        return self._step_toward(snapshot, step)
                    self.last_reason = (
                        "quest:blocked:q34-throw-point-unreachable"
                        if profile.quest_id == 34
                        else "quest-strategy:throw-point-unreachable"
                    )
                    return WAIT_KEY
                else:
                    target_key = (
                        int(survey_plan.get("race_id", 0)),
                        int(survey_plan["target"][0]),
                        int(survey_plan["target"][1]),
                    )
                    target_position = Position(*survey_plan["target"])
                    target_grid = snapshot.grid_at(target_position)
                    if profile.quest_id == 34:
                        # Q34 throws are allowed only from the reviewed stand and
                        # only while the corresponding target is visible.  Blind
                        # throws have a lower hit rate and are user-prohibited.
                        self.last_reason = "quest:blocked:fixed-target-not-visible"
                        return WAIT_KEY
                    if (
                        target_grid is not None
                        and target_grid.known
                        and target_grid.in_view
                        and not target_grid.has_monster
                    ):
                        cleared_targets.add(target_key)
                        self._quest_strategy_pending_recovery[
                            profile.quest_id
                        ] = survey_plan
                        self.last_reason = "quest-strategy:survey-target-cleared"
                        return WAIT_KEY
                    if profile.quest_id == 34:
                        self.last_reason = "quest:blocked:survey-target-not-visible"
                        return WAIT_KEY
                    self.last_reason = "quest-strategy:survey-target-unconfirmed"
                    return SEARCH_KEY

        if profile.quest_id == 2:
            navigator = self._quest_navigators.setdefault(
                2, QuestFloorNavigator(2, battlefield)
            ) if battlefield is not None else None
            if navigator is not None:
                phase_action = self._q2_phase_key(snapshot, profile, navigator)
                if phase_action is not None:
                    return phase_action

        if (
            profile.engagement_plan.get("placement_sweep")
            and battlefield is not None
            and not hostiles
            and initial_hold_complete
            and (
                profile.quest_id != 34
                or self._quest_final_target_position(
                    profile, never_move_races
                ) in self._quest_strategy_surveyed_placements.get(34, set())
            )
        ):
            navigator = self._quest_navigators.setdefault(
                profile.quest_id,
                QuestFloorNavigator(profile.quest_id, battlefield),
            )
            surveyed = self._quest_strategy_surveyed_placements.setdefault(
                profile.quest_id, set()
            )
            placements = {
                Position(*raw_position)
                for raw_position, _ in battlefield.monster_placements
            }
            sweep_scope = profile.engagement_plan.get(
                "placement_sweep_scope", "placements"
            )
            sweep_targets = (
                {
                    Position(y, x)
                    for (y, x) in battlefield.terrain
                    if navigator._static_walkable(Position(y, x))
                }
                if sweep_scope == "battlefield"
                else placements
            )
            for position in sweep_targets:
                candidate = snapshot.grid_at(position)
                if (
                    candidate is not None
                    and candidate.known
                    and not candidate.has_monster
                    and (
                        candidate.in_view
                        or snapshot.player.position.distance_to(position) <= 1
                    )
                ):
                    surveyed.add(position)
            unsurveyed = sweep_targets - surveyed
            if not unsurveyed:
                rounds = self._quest_strategy_sweep_rounds.get(profile.quest_id, 0) + 1
                self._quest_strategy_sweep_rounds[profile.quest_id] = rounds
                if rounds >= int(profile.engagement_plan.get("max_sweep_rounds", 3)):
                    # Every placement is confirmed empty but the quest is not
                    # complete: the targets are mobile (e.g. Q22's orcs) and have
                    # wandered off their placements. Waiting here just deadlocks
                    # until the loop guard stops the bot, so fall back to ordinary
                    # floor exploration to bring the strays into view. The sweep
                    # is gated on `not hostiles`, so combat/hold resumes the
                    # moment one is sighted; only a fully-explored floor with no
                    # frontier left degrades to the (loop-guarded) wait.
                    step = self._explore_step(snapshot)
                    if step is not None:
                        self.last_reason = "quest-strategy:placement-sweep-explore"
                        return self._step_toward(snapshot, step)
                    self.last_reason = "quest:blocked:placement-sweep-exhausted"
                    return WAIT_KEY
                surveyed.clear()
                self.last_reason = "quest-strategy:placement-sweep-repeat"
                return WAIT_KEY
            routes = [
                navigator._static_path(snapshot.player.position, {placement})
                for placement in unsurveyed
            ]
            routes = [route for route in routes if len(route) > 1]
            if routes:
                route = min(
                    routes,
                    key=lambda candidate: (
                        len(candidate), candidate[-1].y, candidate[-1].x
                    ),
                )
                self.last_reason = "quest-strategy:placement-sweep"
                return self._step_toward(snapshot, route[1])
            self.last_reason = "quest:blocked:placement-sweep-route"
            return WAIT_KEY

        if final_target_phase:
            mobile_targets = [
                monster for monster in hostiles
                if monster.race_id not in never_move_races
            ]
            # Mobile monsters do not remain at their source placement.  Once the
            # fixed targets are cleared, walking to an empty original placement
            # can cycle forever at the goal.  Chase only a currently observed
            # mobile target; otherwise fall through to the reviewed placement
            # sweep below and search the whole battlefield.
            target_position = (
                mobile_targets[0].position
                if mobile_targets
                else None
                if profile.quest_id == 31
                else self._quest_final_target_position(profile, never_move_races)
            )
            if target_position is not None:
                target_grid = snapshot.grid_at(target_position)
                if (
                    profile.quest_id == 34
                    and not mobile_targets
                    and target_grid is not None
                    and target_grid.known
                    and not target_grid.has_monster
                    and (
                        target_grid.in_view
                        or snapshot.player.position.distance_to(target_position) <= 1
                    )
                ):
                    self._quest_strategy_surveyed_placements.setdefault(
                        34, set()
                    ).add(target_position)
                    self.last_reason = "quest-strategy:final-source-cleared"
                    return WAIT_KEY
                final_door_value = profile.engagement_plan.get("final_door")
                final_approach_value = profile.engagement_plan.get(
                    "final_door_approach"
                )
                if final_door_value is not None and final_approach_value is not None:
                    final_door = Position(*final_door_value)
                    final_approach = Position(*final_approach_value)
                    final_door_grid = snapshot.grid_at(final_door)
                    final_door_open = (
                        final_door_grid is not None
                        and final_door_grid.known
                        and not final_door_grid.is_closed_door
                    )
                    if not final_door_open:
                        if snapshot.player.position == final_approach:
                            self.last_reason = "quest-strategy:open-final-door"
                            return OPEN_KEY + self._direction_key(
                                final_approach, final_door
                            )
                        step = self._quest_strategy_route_step(
                            snapshot, profile, final_approach
                        )
                        if step is not None:
                            self.last_reason = "quest-strategy:approach-final-door"
                            return self._step_toward(snapshot, step)
                step = self._quest_strategy_route_step(
                    snapshot, profile, target_position
                )
                if step is None:
                    step = self._nearest_goal_step(
                        snapshot,
                        lambda candidate: (
                            candidate.position.distance_to(target_position) <= 1
                        ),
                    )
                if step is not None:
                    self.last_reason = "quest-strategy:approach-final-target"
                    return self._step_toward(snapshot, step)

        # Thrown quest supplies can land between the player and the fixed hold.
        # Recover them before retaking the hold; otherwise normal loot routing
        # advances toward the object on one turn and this strategy immediately
        # walks back toward the hold on the next.
        required_torches = int(
            profile.required_force.get("throwing_items", {}).get("lit_torch", 0)
        )
        needs_supply_recovery = (
            required_torches > 0
            and self._count_throwing_torches(snapshot) < required_torches
        )
        recovery_bounds = profile.engagement_plan.get("supply_recovery_bounds")

        def recoverable_supply(candidate: GridState) -> bool:
            if (
                candidate.object_count <= 0
                or not needs_supply_recovery
                or TVAL_LITE not in candidate.object_tvals
            ):
                return False
            if recovery_bounds is None:
                return True
            min_y, min_x, max_y, max_x = recovery_bounds
            return (
                min_y <= candidate.position.y <= max_y
                and min_x <= candidate.position.x <= max_x
            )

        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and recoverable_supply(here):
            self.last_reason = "quest-strategy:recover-torch"
            return PICKUP_KEY
        pickup_step = self._nearest_goal_step(
            snapshot, recoverable_supply
        )
        if pickup_step is not None and not any(
            monster.race_id in never_move_races
            and pickup_step.distance_to(monster.position) <= 1
            for monster in hostiles
        ):
            self.last_reason = "quest-strategy:recover-torch"
            return self._step_toward(snapshot, pickup_step)

        if hold is not None and snapshot.player.position != hold:
            step = self._quest_strategy_route_step(snapshot, profile, hold)
            if step is not None:
                blocker = next((
                    monster for monster in hostiles
                    if monster.race_id in never_move_races
                    and step.distance_to(monster.position) <= 1
                ), None)
                if blocker is not None:
                    if profile.quest_id == 34:
                        self.last_reason = (
                            "quest:blocked:throw-outside-approved-point"
                        )
                        return WAIT_KEY
                    torch = self._first_item(snapshot, lambda item: item.is_torch)
                    if torch is not None:
                        self.last_reason = "quest-strategy:throw-never-move-blocker"
                        return (
                            THROW_KEY + torch.slot
                            + self._direction_key(snapshot.player.position, blocker.position)
                        )
                    self.last_reason = "quest-strategy:avoid-never-move"
                    return WAIT_KEY
                self.last_reason = "quest-strategy:retake-hold"
                return self._step_toward(snapshot, step)
            self.last_reason = "quest-strategy:hold-unreachable"
            return WAIT_KEY

        # Fixed-position profiles keep their post even between visible waves.
        # Falling through to generic exploration makes the bot step away, then
        # immediately retake the hold on the following turn.  This also keeps
        # Q34 away from its NEVER_MOVE targets and the bee alcove until its turn.
        if hold is not None:
            if not mobile_visible and initial_hold_budget > 0:
                self._quest_strategy_initial_hold_turns[profile.quest_id] = min(
                    initial_hold_budget,
                    self._quest_strategy_initial_hold_turns.get(profile.quest_id, 0)
                    + 1,
                )
            self.last_reason = "quest-strategy:hold"
            return WAIT_KEY
        return None

    def _quest_strategy_for_errand_or_floor(
        self, snapshot: Snapshot
    ) -> StrategyProfile | None:
        floor_profile = self.approved_quest_strategy(snapshot.floor_key[2])
        if floor_profile is not None:
            return floor_profile
        if not snapshot.in_town:
            return None
        # Errand retention is itself part of town-departure readiness.  Do not
        # ask _fixed_quest_target here: for a force-ready untaken quest that
        # evaluates readiness -> departure -> Home deposits -> retention and
        # recursively returns here.  Supplies belong to the earliest approved
        # pending/taken quest regardless of whether departure is ready yet.
        candidates = [
            quest for quest in self._known_fixed_quests(snapshot).values()
            if quest.id in FIXED_QUEST_ALLOWLIST
            and quest.status in {QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN}
            and self.approved_quest_strategy(quest.id) is not None
        ]
        if not candidates:
            return None
        quest = min(candidates, key=self._fixed_quest_order)
        return self.approved_quest_strategy(quest.id)

    def _fixed_quest_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if self._physical_adjacent_hostiles(snapshot):
            return None
        if snapshot.in_town:
            # A claimed floor reward is part of the quest transaction and must
            # finish before selecting or travelling to another fixed quest.
            # Reconstruct the in-memory latch after a bot/game restart from the
            # dedicated allowlisted tile when the quest is already rewarded.
            if self._fixed_quest_reward_pending is None:
                for reward_quest_id in FIXED_QUEST_REWARD_POSITIONS:
                    reward_quest = snapshot.quests.get(reward_quest_id)
                    if reward_quest is None or reward_quest.status not in {
                        QUEST_STATUS_REWARDED,
                        QUEST_STATUS_FINISHED,
                    }:
                        continue
                    if any(
                        (grid := snapshot.grid_at(position)) is not None
                        and grid.object_count > 0
                        for position in self._fixed_quest_reward_positions(
                            snapshot, reward_quest_id
                        )
                    ):
                        self._fixed_quest_reward_pending = reward_quest_id
                        break
            if self._fixed_quest_reward_pending is not None:
                reward_key = self._fixed_quest_reward_key(
                    snapshot, self._fixed_quest_reward_pending
                )
                if reward_key is not None:
                    return reward_key
                if self._fixed_quest_reward_pending is not None:
                    self.last_reason = "fixedquest:reward-wait"
                    return WAIT_KEY

            # Fixed-quest travel used to bypass ordinary town readiness entirely.
            # Let the town router shed weight at Home before accepting, claiming,
            # or travelling to another fixed quest.
            if self._inventory_overweight(snapshot):
                return None

            fixed_quest_candidates = [
                quest for quest in self._known_fixed_quests(snapshot).values()
                if quest.id in FIXED_QUEST_ALLOWLIST
                and quest.status in {
                    QUEST_STATUS_UNTAKEN,
                    QUEST_STATUS_TAKEN,
                    QUEST_STATUS_COMPLETED,
                }
                and self.approved_quest_strategy(quest.id) is not None
            ]
            fixed_quest_head = self._fixed_quest_head(snapshot)
            travel_quest = fixed_quest_head
            if (
                travel_quest is not None
                and (
                    self.approved_quest_strategy(travel_quest.id) is None
                    or (
                        travel_quest.status == QUEST_STATUS_UNTAKEN
                        and not self._fixed_quest_ready_for_travel(
                            snapshot, travel_quest.id
                        )
                    )
                )
            ):
                travel_quest = None
            current_town_id = self._effective_town_id(snapshot)
            if travel_quest is None and current_town_id == 1:
                key = self._town_teleport_key(snapshot, 0)
                if key is not None:
                    self.last_reason = (
                        "fixedquest:prepare-return"
                        if fixed_quest_head is not None
                        and fixed_quest_head.status == QUEST_STATUS_UNTAKEN
                        else "fixedquest:q2-teleport"
                    )
                return key
            if (
                travel_quest is None
                and current_town_id != 0
                and any(
                    quest.status == QUEST_STATUS_UNTAKEN
                    for quest in fixed_quest_candidates
                )
            ):
                # A previous process may already have travelled before the
                # reviewed preparation contract was complete.  Once no fixed
                # quest is ready here, return by inn to the base town instead
                # of dropping through to generic town wandering.
                key = self._town_teleport_key(snapshot, 0)
                if key is not None:
                    self.last_reason = "fixedquest:prepare-return"
                return key
            target_town = (
                FIXED_QUEST_TOWNS.get(travel_quest.id, 0)
                if travel_quest is not None else None
            )
            if target_town is not None and current_town_id != target_town:
                if (
                    snapshot.visited_town_ids is None
                    or target_town not in snapshot.visited_town_ids
                ):
                    self._town_travel_rumor_pending = target_town
                    # Process rumors now, before shopping or another town route
                    # can starve the unlock.  Never send the inn travel command
                    # until the destination appears in exported progress.
                    return self._town_special_key(snapshot)
                if self._town_travel_rumor_pending == target_town:
                    self._town_travel_rumor_pending = None
                if travel_quest is not None and travel_quest.id == 2:
                    self._telmora_q2_errand = True
                key = self._town_teleport_key(snapshot, target_town)
                if key is not None:
                    self.last_reason = f"fixedquest:q{travel_quest.id}-travel"
                return key
        quest_id = self._fixed_quest_target(snapshot)
        if quest_id is None:
            return None
        quest = self._known_fixed_quests(snapshot).get(quest_id)
        if quest is None:
            return None
        if quest_id == 2:
            travel = self._telmora_q2_travel_key(snapshot, quest)
            if travel is not None:
                return travel
        info = self._quest_knowledge.get(quest_id)
        if info is not None and info.type in {QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER}:
            if snapshot.in_town and self._fixed_quest_reward_pending == quest_id:
                return self._fixed_quest_reward_key(snapshot, quest_id)
            if quest.status == QUEST_STATUS_COMPLETED:
                if not snapshot.in_town:
                    self._returning_to_town = True
                    key = self._return_to_town_key(snapshot, hostiles)
                    if key is not None and self.last_reason != "return:wait-recall":
                        self.last_reason = "fixedquest:claim:return"
                    return key
                return self._fixed_quest_building_key(
                    snapshot,
                    quest_id,
                    "fixedquest:claim",
                    set_reward_pending=bool(FIXED_QUEST_REWARD_POSITIONS.get(quest_id)),
                )
            if quest.status == QUEST_STATUS_UNTAKEN:
                if (
                    not snapshot.in_town
                    or (quest_id == 2 and self.approved_quest_strategy(2) is None)
                    or quest_id not in EXECUTABLE_QUEST_STRATEGY_IDS
                    or not self._fixed_quest_ready(snapshot, quest_id)
                ):
                    return None
                return self._fixed_quest_building_key(
                    snapshot,
                    quest_id,
                    "fixedquest:request",
                    set_reward_pending=False,
                )
            if quest.status != QUEST_STATUS_TAKEN:
                return None
            # A taken kill quest uses ordinary entrance routing and stair descent.
            self._target_dungeon_id = info.dungeon
            return None
        if snapshot.floor_key[2] == quest_id:
            if quest.status == QUEST_STATUS_COMPLETED:
                return self._fixed_quest_exit_key(snapshot, quest_id)
            return None
        if not snapshot.in_town:
            return None
        if self._fixed_quest_reward_pending == quest_id:
            return self._fixed_quest_reward_key(snapshot, quest_id)
        if quest.status == QUEST_STATUS_COMPLETED:
            return self._fixed_quest_building_key(
                snapshot,
                quest_id,
                "fixedquest:claim",
                set_reward_pending=bool(FIXED_QUEST_REWARD_POSITIONS.get(quest_id)),
            )
        if quest.status == QUEST_STATUS_TAKEN:
            info = self._quest_knowledge.get(quest_id)
            if self.approved_quest_strategy(quest_id) is not None and info is not None and info.battlefield is not None:
                navigator = self._quest_navigators.setdefault(
                    quest_id, QuestFloorNavigator(quest_id, info.battlefield)
                )
                return navigator.enter_from_town(self, snapshot, quest_id)
            return self._fixed_quest_enter_key(snapshot, quest_id)
        if (
            quest.status == QUEST_STATUS_UNTAKEN
            and (quest_id != 2 or self.approved_quest_strategy(2) is not None)
            and quest_id in EXECUTABLE_QUEST_STRATEGY_IDS
            and self._fixed_quest_ready(snapshot, quest_id)
        ):
            return self._fixed_quest_building_key(
                snapshot, quest_id, "fixedquest:request", set_reward_pending=False
            )
        return None

    def _quest_target_race_id(self, quest: QuestState) -> int | None:
        """Join a fixed target from knowledge, otherwise use disclosed runtime data."""
        info = self._quest_knowledge.get(quest.id)
        if info is not None and info.monrace_id > 0:
            return info.monrace_id
        return quest.r_idx

    @staticmethod
    def _kill_quest_completion_target(
        quest: QuestState, info: QuestInfo | None
    ) -> int | None:
        """Return the counter that completes each supported kill-quest type."""
        quest_type = info.type if info is not None else quest.type
        if quest_type == QUEST_TYPE_KILL_LEVEL:
            # KILL_LEVEL advances cur_num until max_num; num_mon describes the
            # generated pack and is not necessarily the completion threshold.
            return (
                quest.max_num
                if quest.max_num is not None
                else (info.max_num if info is not None else None)
            )
        if quest_type == QUEST_TYPE_KILL_NUMBER:
            return (
                quest.num_mon
                if quest.num_mon is not None
                else (info.num_mon if info is not None else None)
            )
        if quest_type == QUEST_TYPE_RANDOM:
            return (
                quest.max_num
                if quest.max_num is not None
                else (info.max_num if info is not None else None)
            )
        return None

    def _kill_quest_exit_would_fail(self, snapshot: Snapshot) -> bool:
        quest_id = self._active_kill_quest_id(snapshot)
        if quest_id is None:
            return False
        if self._unviable_quest_floor == snapshot.floor_key:
            return False
        info = self._quest_knowledge.get(quest_id)
        return info is not None and (
            bool(info.flags & QUEST_FLAG_ONCE) or info.type == QUEST_TYPE_RANDOM
        )

    def _quest_floor_exit_locked(self, snapshot: Snapshot) -> bool:
        """Protect an incomplete kill attempt, with bounded survival releases."""
        if self._unviable_quest_floor == snapshot.floor_key:
            return False
        quest_id = self._active_kill_quest_id(snapshot)
        if quest_id is None:
            return False
        # A deepest-floor quest is not worth continuing after both usable
        # escape-scroll rungs are gone.  Release the lock so the ordinary
        # escape-kit return can read recall (or walk out).
        if self._deepest_floor_escape_kit_empty(snapshot):
            return False
        # Once relocation is exhausted, dying on the floor is worse than the
        # visible loss of even an ONCE/RANDOM quest.
        if snapshot.player.hp_ratio <= PANIC_HP_RATIO and self._escape_scroll(snapshot) is None:
            return False
        # Starvation kills through paralysis with HP untouched, so the panic
        # release above never sees it coming. Weak-or-worse with nothing edible
        # is the same "worse than losing the quest" call.
        if (
            snapshot.player.food_state in {"weak", "fainting"}
            and self._find_edible(snapshot) is None
        ):
            return False
        # Depth quests that Hengband does not fail on leave may regenerate a bad
        # floor after the ordinary stuck budget is exhausted. Runtime RANDOM
        # quests deliberately accept the loss at that same genuine-stall
        # boundary, independent of static quest knowledge.
        quest = snapshot.quests[quest_id]
        info = self._quest_knowledge.get(quest_id)
        runtime_random = (
            info.type if info is not None else quest.type
        ) == QUEST_TYPE_RANDOM
        if (
            (runtime_random or not self._kill_quest_exit_would_fail(snapshot))
            and self._stuck_escape_streak >= STUCK_ESCAPE_LIMIT
        ):
            return False
        return True

    def _quest_exit_would_fail(self, snapshot: Snapshot) -> bool:
        """Match Hengband's leave_quest_check for visible escape reasons."""
        active_fixed = self._active_fixed_quest_id(snapshot)
        return self._kill_quest_exit_would_fail(snapshot) or (
            active_fixed is not None and self._fixed_quest_is_once(active_fixed)
        )

    def _fixed_quest_target(self, snapshot: Snapshot) -> int | None:
        def supported(quest_id: int) -> bool:
            # TODO(tower): add quests 5/6/7 to the allowlist only with
            # direction-aware QUEST_UP/QUEST_DOWN progression across all three
            # linked floors.  The final floor is not shaped like 5 and 6.
            return quest_id in FIXED_QUEST_ALLOWLIST and not (
                quest_id == 2
                and (
                    snapshot.visited_town_ids is None
                    or 1 not in snapshot.visited_town_ids
                )
            )

        floor_quest = snapshot.floor_key[2]
        if supported(floor_quest):
            return floor_quest
        pending = self._fixed_quest_reward_pending
        if pending is not None and supported(pending):
            return pending

        quest = self._fixed_quest_head(snapshot)
        if quest is None or not supported(quest.id):
            return None
        if quest.status in {QUEST_STATUS_TAKEN, QUEST_STATUS_COMPLETED}:
            return quest.id
        if (
            quest.status == QUEST_STATUS_UNTAKEN
            and self._fixed_quest_is_offered(snapshot, quest.id)
            and self._fixed_quest_ready(snapshot, quest.id)
        ):
            return quest.id
        return None

    def _fixed_quest_head(self, snapshot: Snapshot) -> QuestState | None:
        """Select one transaction head before readiness or routing is tested."""
        cache = getattr(self, "_fixed_quest_head_cache", None)
        if cache is None:
            cache = {}
            self._fixed_quest_head_cache = cache
        identity = id(snapshot)
        cached = cache.get(identity)
        if cached is not None and cached[0] is snapshot:
            return cached[1]
        head = self._uncached_fixed_quest_head(snapshot)
        cache[identity] = (snapshot, head)
        return head

    def _uncached_fixed_quest_head(
        self, snapshot: Snapshot
    ) -> QuestState | None:
        def supported(quest: QuestState) -> bool:
            return quest.id in FIXED_QUEST_ALLOWLIST

        # Never accept or prepare another fixed quest while real work is in
        # flight. The birth-time win quests are the only intentional exception.
        known_quests = self._known_fixed_quests(snapshot)
        taken = [
            quest for quest in known_quests.values()
            if quest.fixed
            and quest.status == QUEST_STATUS_TAKEN
            and quest.id not in WIN_QUEST_IDS
        ]
        supported_taken = [quest for quest in taken if supported(quest)]
        if supported_taken:
            return min(supported_taken, key=self._fixed_quest_order)
        if taken:
            return None

        completed = [
            quest for quest in known_quests.values()
            if supported(quest) and quest.status == QUEST_STATUS_COMPLETED
        ]
        if completed:
            return min(completed, key=self._fixed_quest_order)

        # Q1 and Q34 are both level-five quests, so the generic (level, id)
        # ordering otherwise selects Q1 immediately after Q34's torches become
        # ready.  The reviewed birth route is explicitly Q34-first; retain that
        # transaction head from procurement through acceptance.
        if self._opening_q34_active(snapshot):
            opening_q34 = known_quests.get(34)
            if opening_q34 is not None and supported(opening_q34):
                return opening_q34

        untaken = [
            quest for quest in known_quests.values()
            if supported(quest)
            and quest.status == QUEST_STATUS_UNTAKEN
            and (
                quest.id in FIXED_QUEST_ALWAYS_OFFERED
                or self._fixed_quest_is_offered(snapshot, quest.id)
            )
        ]
        return min(untaken, key=self._fixed_quest_order) if untaken else None

    def _fixed_quest_order(self, quest: QuestState) -> tuple[int, int]:
        quest_id = quest.id
        info = self._quest_knowledge.get(quest_id)
        level = info.level if info is not None else quest.level
        return level, quest_id

    def _fixed_quest_is_once(self, quest_id: int) -> bool:
        info = self._quest_knowledge.get(quest_id)
        return info is None or bool(info.flags & QUEST_FLAG_ONCE)

    def _fixed_quest_ready(self, snapshot: Snapshot, quest_id: int) -> bool:
        return self._evaluate_fixed_quest_readiness(
            snapshot, quest_id, require_target_town=True
        )

    def _fixed_quest_ready_for_travel(
        self, snapshot: Snapshot, quest_id: int
    ) -> bool:
        """Check the quest contract before travelling to its acceptance town."""
        return self._evaluate_fixed_quest_readiness(
            snapshot, quest_id, require_target_town=False
        )

    def _evaluate_fixed_quest_readiness(
        self,
        snapshot: Snapshot,
        quest_id: int,
        *,
        require_target_town: bool,
    ) -> bool:
        telemetry = {
            "quest_id": quest_id,
            "roster_size": 0,
            "toughest_r_idx": None,
            "worst_adjacent": None,
            "hp_healing_budget": snapshot.player.max_hp,
            "hasted": False,
            "verdict": False,
        }
        self._fixed_quest_readiness = telemetry

        def reject(reason: str) -> bool:
            telemetry["reason"] = reason
            return False

        allowed_towns = {-1, FIXED_QUEST_TOWNS.get(quest_id, 0)}
        if (
            require_target_town
            and self._effective_town_id(snapshot) not in allowed_towns
        ):
            return reject("not-in-town")
        info = self._quest_knowledge.get(quest_id)
        if info is None:
            return reject("unknown-quest")
        telemetry["roster_size"] = info.threat_roster_count
        profile = self.approved_quest_strategy(quest_id)
        if profile is not None and not self._approved_strategy_force_ready(snapshot, profile):
            return reject("strategy-force")
        if snapshot.player.hp < snapshot.player.max_hp:
            return reject("not-full-hp")
        if not self._temporary_status_clear(snapshot):
            return reject("temporary-status")
        if not self._combat_weapon_ready(snapshot):
            return reject("combat-weapon")
        if PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS:
            return reject("pack-space")
        # Approved fixed quests own an explicit, reviewed preparation contract.
        # The ordinary dungeon departure gate additionally requires a complete
        # Home equipment scan and no pending Home deposit; those are town
        # administration, not quest-entry safety, and previously stranded a
        # fully prepared Q2 character in town. Keep the two universal inventory
        # hazards explicit while allowing the reviewed strategy to own supplies.
        if profile is not None and self._inventory_overweight(snapshot):
            return reject("overweight")
        if profile is not None and any(
            self._blocks_teleport(item)
            for item in (*snapshot.inventory, *snapshot.equipment)
        ):
            return reject("random-teleport")
        if (
            profile is None
            and not self._opening_q34_active(snapshot)
            and not self._town_departure_ready(snapshot)
        ):
            return reject("departure")
        if not info.threat_roster:
            return reject("empty-roster")

        # One potion consumes one player action.  Across the three-turn threat
        # window, no more than THREAT_TURNS doses are realizable; value the best
        # available doses first instead of crediting the entire carried stock.
        healing_doses = (
            [HEALING_POTION_HP]
            * self._exact_potion_count(snapshot, SV_POTION_HEALING)
            + [FIXED_QUEST_CURE_CRITICAL_HP]
            * self._exact_potion_count(snapshot, SV_POTION_CURE_CRITICAL)
        )
        speed_potion = self._find_exact_potion(snapshot, SV_POTION_SPEED)
        hasted = speed_potion is not None
        modeled_speed = snapshot.player.speed + (SPEED_POTION_BONUS if hasted else 0)
        telemetry["hasted"] = hasted

        candidates: list[tuple[int, int, MonsterState]] = []
        strategy_controlled_stationary: set[int] = set()
        if profile is not None:
            strategy_controlled_stationary = {
                r_idx
                for r_idx in self._quest_never_move_races(profile)
                if (
                    (knowledge := self._monrace_knowledge.get(r_idx)) is not None
                    and knowledge.max_ranged_damage <= 0
                    and not knowledge.can_summon
                    and not knowledge.can_multiply
                )
            }
        telemetry["strategy_controlled_stationary"] = sorted(
            strategy_controlled_stationary
        )
        # An approved profile may model a random-moving (RAND_25) enemy as
        # dealing only a fraction of its melee output: its 25% random step keeps
        # it out of contact part of the time, so full-contact damage overstates
        # the threat. Q14's Tier2 force gate was derived on exactly this basis
        # (Warg melee counted at half). Only a reviewed profile opts in.
        random_move_damage_factor = 1.0
        if profile is not None:
            random_move_damage_factor = float(
                profile.engagement_plan.get("random_move_damage_factor", 1.0)
            )
        telemetry["random_move_damage_factor"] = random_move_damage_factor
        player_pos = snapshot.player.position
        positions = [
            Position(player_pos.y + dy, player_pos.x + dx)
            for dy, dx in (
                (-1, -1), (-1, 0), (-1, 1), (0, -1),
                (0, 1), (1, -1), (1, 0), (1, 1),
            )
        ]
        combat_grids = dict(snapshot.grids)
        combat_grids[player_pos] = GridState(
            player_pos, True, True, False, False, False, False, False
        )
        for position in positions:
            combat_grids[position] = GridState(
                position, True, True, False, True, False, False, False
            )
        combat_snapshot = replace(
            snapshot,
            player=replace(snapshot.player, speed=modeled_speed),
            grids=combat_grids,
            store=None,
        )
        for r_idx, count_placed in info.threat_roster:
            knowledge = self._monrace_knowledge.get(r_idx)
            if knowledge is None:
                telemetry["toughest_r_idx"] = r_idx
                return reject("unknown-monster")
            hp = knowledge.average_hp or knowledge.max_hp
            modeled_melee_damage = knowledge.max_melee_damage
            if random_move_damage_factor != 1.0 and "RAND_25" in knowledge.flags:
                modeled_melee_damage = int(
                    round(knowledge.max_melee_damage * random_move_damage_factor)
                )
            monster = MonsterState(
                index=-r_idx,
                position=positions[0],
                hp=hp,
                max_hp=hp,
                distance=1,
                friendly=knowledge.friendly,
                pet=False,
                speed=knowledge.speed,
                name=f"fixedquest:{r_idx}",
                race_id=r_idx,
                can_summon=knowledge.can_summon,
                level=knowledge.level,
                max_melee_damage=modeled_melee_damage,
                max_ranged_damage=knowledge.max_ranged_damage,
                can_multiply=knowledge.can_multiply,
            )
            individual = self.threat_prediction(
                combat_snapshot, [monster], FIXED_QUEST_THREAT_TURNS
            )["operational_total"]
            candidates.extend((individual, r_idx, monster) for _ in range(count_placed))

        candidates.sort(key=lambda entry: (entry[0], entry[2].max_hp), reverse=True)
        _, toughest_r_idx, toughest = candidates[0]
        telemetry["toughest_r_idx"] = toughest_r_idx
        adjacent_candidates = [
            entry for entry in candidates
            if entry[1] not in strategy_controlled_stationary
        ]
        simultaneous_limit = FIXED_QUEST_SIMULTANEOUS_MONSTERS
        if profile is not None:
            simultaneous_limit = max(
                1,
                min(
                    FIXED_QUEST_SIMULTANEOUS_MONSTERS,
                    int(
                        profile.engagement_plan.get(
                            "max_simultaneous_melee", simultaneous_limit
                        )
                    ),
                ),
            )
        telemetry["simultaneous_melee"] = simultaneous_limit
        simultaneous = [
            replace(entry[2], index=-(index + 1), position=positions[index], distance=1)
            for index, entry in enumerate(
                adjacent_candidates[:simultaneous_limit]
            )
        ]
        worst_adjacent = self.threat_prediction(
            combat_snapshot, simultaneous, FIXED_QUEST_THREAT_TURNS
        )["operational_total"]
        telemetry["worst_adjacent"] = worst_adjacent
        per_turn_damage = self._predicted_damage(
            combat_snapshot, simultaneous, turns=1
        )
        healing_budget = sum(
            sorted(
                (
                    heal_amount
                    for heal_amount in healing_doses
                    if heal_amount >= per_turn_damage
                ),
                reverse=True,
            )[:FIXED_QUEST_THREAT_TURNS]
        )
        telemetry["hp_healing_budget"] = snapshot.player.max_hp + healing_budget
        max_damage_ratio = FIXED_QUEST_MAX_DAMAGE_RATIO
        if profile is not None:
            max_damage_ratio = float(
                profile.engagement_plan.get(
                    "max_damage_ratio", FIXED_QUEST_MAX_DAMAGE_RATIO
                )
            )
        telemetry["max_damage_ratio"] = max_damage_ratio
        if worst_adjacent >= telemetry["hp_healing_budget"] * max_damage_ratio:
            return reject("three-turn-threat")
        weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        sub_weapon = next(
            (
                item
                for item in snapshot.equipment
                if item.slot == "sub_hand" and item.is_melee_weapon
            ),
            None,
        )
        main_hand_output = (
            self._main_hand_dps(snapshot, weapon) if weapon is not None else 0.0
        )
        sub_hand_output = (
            self._sub_hand_dps(snapshot, sub_weapon)
            if sub_weapon is not None and snapshot.player.sub_hand_blows > 0
            else 0.0
        )
        melee_output = main_hand_output + sub_hand_output
        # Both hand-DPS values are damage per player action. Convert their sum
        # to output over baseline player turns so a carried Speed dose affects
        # both sides of the same readiness projection.
        speed_ratio = self._speed_energy(modeled_speed) / self._speed_energy(
            snapshot.player.speed
        )
        main_hand_output *= speed_ratio
        sub_hand_output *= speed_ratio
        melee_output *= speed_ratio
        telemetry["toughest_hp"] = toughest.max_hp
        telemetry["main_hand_melee_output"] = main_hand_output
        telemetry["sub_hand_melee_output"] = sub_hand_output
        telemetry["melee_output"] = melee_output
        if melee_output * FIXED_QUEST_TOUGHEST_KILL_TURNS < toughest.max_hp:
            return reject("toughest-kill-time")
        telemetry["verdict"] = True
        telemetry["reason"] = "ready"
        return True

    def _fixed_quest_building_positions(
        self, snapshot: Snapshot, quest_id: int
    ) -> frozenset[Position]:
        visible = frozenset(
            grid.position
            for grid in snapshot.grids.values()
            if grid.building_special == quest_id
        )
        if visible:
            return visible
        if self._town_map_active(snapshot):
            return self._town_map.quest_building_positions(quest_id)
        return frozenset()

    def _fixed_quest_is_offered(self, snapshot: Snapshot, quest_id: int) -> bool:
        """Whether an in-town building currently offers this untaken quest."""
        if not snapshot.in_town:
            return False
        # In-town emitter snapshots include the full memorized town map.  Once
        # it contains building specials, that live data is authoritative for
        # conditional offer chains (1 -> 14 -> 18, etc.).
        # Store snapshots deliberately omit the map.  That omission is not a
        # new observation that the visible offer disappeared: consult only the
        # terrain retained from the preceding player-turn snapshot.  Do not use
        # static quest data here; remembered building specials were emitted to
        # the player and preserve conditional offer chains fairly.
        cache = getattr(self, "_fixed_quest_offer_cache", None)
        if cache is None:
            cache = {}
            self._fixed_quest_offer_cache = cache
        identity = id(snapshot)
        cached = cache.get(identity)
        if cached is not None and cached[0] is snapshot:
            specials = cached[1]
        else:
            if (
                snapshot is self._map_predicate_snapshot
                or snapshot is self._decision_input_snapshot
            ):
                specials = self._fixed_quest_offers
            else:
                grids = snapshot.grids
                if snapshot.store is not None and not grids:
                    grids = self._remembered_grids
                specials = frozenset(
                    grid.building_special
                    for grid in grids.values()
                    if grid.building_special
                )
            cache[identity] = (snapshot, specials)
        if specials:
            return quest_id in specials
        if self._town_map_active(snapshot):
            return bool(self._town_map.quest_building_positions(quest_id))
        return False

    def _fixed_quest_entrance_positions(
        self, snapshot: Snapshot, quest_id: int
    ) -> frozenset[Position]:
        visible = frozenset(
            grid.position
            for grid in snapshot.grids.values()
            if grid.has_quest_enter and grid.quest_id == quest_id
        )
        if visible:
            return visible
        if self._town_map_active(snapshot):
            return self._town_map.quest_entrance_positions(quest_id)
        return frozenset()

    def _fixed_quest_building_key(
        self,
        snapshot: Snapshot,
        quest_id: int,
        reason: str,
        *,
        set_reward_pending: bool,
    ) -> str | None:
        positions = self._fixed_quest_building_positions(snapshot, quest_id)
        if not positions:
            return None
        if snapshot.player.position in positions:
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                self.last_reason = f"{reason}:step-off"
                return self._step_toward(snapshot, neighbors[0])
            return None
        step = self._nearest_goal_step(
            snapshot,
            lambda grid: grid.building_special == quest_id,
        )
        if step is None:
            step = min(
                (
                    candidate
                    for candidate in (
                        self._town_map_goal_step(snapshot, pos) for pos in positions
                    )
                    if candidate is not None
                ),
                key=lambda pos: snapshot.player.position.distance_to(pos),
                default=None,
            )
        if step is None:
            return None
        step_grid = snapshot.grid_at(step)
        if step in positions or (
            step_grid is not None and step_grid.building_special == quest_id
        ):
            if set_reward_pending:
                self._fixed_quest_reward_pending = quest_id
            self.last_reason = reason
            return self._step_toward(snapshot, step, tail="q" + LEAVE_STORE_KEY)
        owner = f"{reason}:approach"
        if not self._owner_may_select(snapshot, owner):
            return None
        self.last_reason = owner
        self._post_owner_expectation(snapshot, owner, "position", "floor")
        return self._step_toward(snapshot, step)

    def _fixed_quest_enter_key(self, snapshot: Snapshot, quest_id: int) -> str | None:
        positions = self._fixed_quest_entrance_positions(snapshot, quest_id)
        if not positions:
            return None
        if snapshot.player.position in positions:
            if not self._kill_quest_descent_allowed(snapshot):
                return None
            if not self._quest_equipment_entry_allowed(snapshot, quest_id):
                return None
            self.last_reason = "fixedquest:enter"
            return DOWN_STAIRS_KEY + "y"
        step = self._nearest_goal_step(
            snapshot,
            lambda grid: grid.has_quest_enter and grid.quest_id == quest_id,
        )
        if step is not None:
            # A shortest path through the fixed town map may begin with a
            # distance-increasing detour around a building.  Immediately after
            # accepting a quest that can route through a town monster which is
            # still outside view: combat then walks back to the starting cell
            # and the two priorities oscillate forever.  Prefer an available
            # step that makes monotonic progress toward the known entrance when
            # the BFS first step moves away from it.
            goal = min(positions, key=snapshot.player.position.distance_to)
            origin = snapshot.player.position
            moving_away = (
                (goal.y - origin.y) * (step.y - origin.y) < 0
                or (goal.x - origin.x) * (step.x - origin.x) < 0
            )
            if moving_away:
                def has_onward_route(start: Position) -> bool:
                    seen = {origin, start}
                    queue = deque([start])
                    while queue:
                        pos = queue.popleft()
                        if pos == goal:
                            return True
                        for neighbor in self._walkable_neighbors(snapshot, pos):
                            if neighbor not in seen:
                                seen.add(neighbor)
                                queue.append(neighbor)
                    return False

                monotonic = [
                    neighbor
                    for neighbor in self._walkable_neighbors(snapshot, origin)
                    if neighbor.distance_to(goal) < origin.distance_to(goal)
                    and self._visit_counts[neighbor] == 0
                    and (goal.y - origin.y) * (neighbor.y - origin.y) >= 0
                    and (goal.x - origin.x) * (neighbor.x - origin.x) >= 0
                    and has_onward_route(neighbor)
                ]
                if monotonic:
                    step = min(
                        monotonic,
                        key=lambda neighbor: (
                            neighbor.distance_to(goal),
                            -sum(
                                before != after
                                for before, after in (
                                    (origin.y, neighbor.y),
                                    (origin.x, neighbor.x),
                                )
                            ),
                            self._visit_counts[neighbor],
                        ),
                    )
        if step is None:
            step = min(
                (
                    candidate
                    for candidate in (
                        self._town_map_goal_step(snapshot, pos) for pos in positions
                    )
                    if candidate is not None
                ),
                key=lambda pos: snapshot.player.position.distance_to(pos),
                default=None,
            )
        if step is None:
            return None
        self.last_reason = "fixedquest:enter" if step in positions else "fixedquest:approach"
        suffix = "y" if step in positions else ""
        return self._step_toward(snapshot, step, tail=suffix)

    def _fixed_quest_exit_key(self, snapshot: Snapshot, quest_id: int) -> str | None:
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.has_quest_exit:
            self.last_reason = "fixedquest:exit"
            return UP_STAIRS_KEY
        step = self._nearest_goal_step(snapshot, lambda grid: grid.has_quest_exit)
        if step is not None:
            self.last_reason = "fixedquest:seek-exit"
            return self._step_toward(snapshot, step)
        return None

    def _fixed_quest_reward_positions(
        self, snapshot: Snapshot, quest_id: int
    ) -> frozenset[Position]:
        town_reward = FIXED_QUEST_REWARD_POSITIONS.get(quest_id)
        if town_reward is None:
            return frozenset()
        town_id, expected = town_reward
        if snapshot.town_id not in {-1, town_id}:
            return frozenset()
        if not self._town_map_active(snapshot):
            return expected
        # Static map metadata is the source of truth, restricted to the
        # allowlisted quest's reviewed coordinates so another reward glyph
        # cannot become an accidental quest-1 target.
        return self._town_map.reward_positions & expected

    def _fixed_quest_reward_key(self, snapshot: Snapshot, quest_id: int) -> str | None:
        if len(snapshot.inventory) >= PACK_CAPACITY:
            destroy = self._full_pack_destroy_key(snapshot)
            if destroy is not None:
                return destroy
            self.last_reason = "fixedquest:reward-pack-full"
            return WAIT_KEY
        positions = self._fixed_quest_reward_positions(snapshot, quest_id)
        here = snapshot.grid_at(snapshot.player.position)
        if (
            snapshot.player.position in positions
            and here is not None
            and here.object_count > 0
        ):
            # Fixed-quest rewards are mandatory and their coordinates are
            # allowlisted. Do not defer them or route them through the generic
            # auto-destroy trigger; retry an explicit pickup until they vanish.
            self._deferred_loot.discard(snapshot.player.position)
            self.last_reason = "fixedquest:reward-pickup"
            self._pending_loot_pickup = (
                snapshot.floor_key,
                here.position,
                here.object_count,
            )
            if here.object_count > 1:
                return PICKUP_KEY + ("a" * here.object_count)
            return PICKUP_KEY
        current = self._current_floor_item_key(
            snapshot,
            pickup_reason="fixedquest:reward-pickup",
            trigger_reason="fixedquest:reward-trigger-autodestroy",
        )
        if current is not None:
            return current
        visible_reward = [
            pos
            for pos in positions
            if (grid := snapshot.grid_at(pos)) is not None and grid.object_count > 0
        ]
        if snapshot.player.position in positions and not visible_reward:
            self._fixed_quest_reward_pending = None
            self.last_reason = "fixedquest:reward-complete"
            return None
        target_positions = visible_reward or list(positions)
        step = min(
            (
                candidate
                for candidate in (
                    self._town_map_goal_step(snapshot, pos) for pos in target_positions
                )
                if candidate is not None
            ),
            key=lambda pos: snapshot.player.position.distance_to(pos),
            default=None,
        )
        if step is None:
            if not positions:
                self._fixed_quest_reward_pending = None
            return None
        self.last_reason = "fixedquest:reward-approach"
        return self._step_toward(snapshot, step)

    def _guardian_fight_viable(
        self, snapshot: Snapshot, info: DungeonInfo
    ) -> bool:
        """Whether current gear and consumables can clear this final guardian."""
        if info.guardian_id <= 0:
            return True
        knowledge = self._monrace_knowledge.get(info.guardian_id)
        if knowledge is None:
            return False
        # Summoners are still viable conquest targets when the ordinary fight
        # projection fits the current kit. Runtime combat commits only in a
        # choke point and escapes an open summoning fight. Multipliers remain
        # unsuitable for a pre-planned guardian engagement.
        if knowledge.can_multiply:
            return False

        player_position = Position(10, 10)
        target_position = Position(10, 11)
        grids = {
            player_position: GridState(
                player_position, True, True, False, False, False, False, False
            ),
            target_position: GridState(
                target_position, True, True, False, True, False, False, False
            ),
        }
        guardian_hp = knowledge.average_hp or knowledge.max_hp
        guardian = MonsterState(
            index=-info.guardian_id,
            position=target_position,
            hp=guardian_hp,
            max_hp=guardian_hp,
            distance=1,
            friendly=knowledge.friendly,
            pet=False,
            speed=knowledge.speed,
            name=f"guardian:{info.guardian_id}",
            race_id=info.guardian_id,
            can_summon=knowledge.can_summon,
            level=knowledge.level,
            max_melee_damage=knowledge.max_melee_damage,
            max_ranged_damage=knowledge.max_ranged_damage,
            can_multiply=knowledge.can_multiply,
        )
        fight_snapshot = replace(
            snapshot,
            player=replace(
                snapshot.player,
                position=player_position,
                hp=snapshot.player.max_hp,
            ),
            grids=grids,
            visible_monsters=[guardian],
            store=None,
        )
        if (
            self._unique_fight_projection(
                fight_snapshot,
                [guardian],
                guardian,
                player_speed=fight_snapshot.player.speed,
            )
            is not None
        ):
            return True
        if self._find_exact_potion(fight_snapshot, SV_POTION_SPEED) is None:
            return False
        return (
            self._unique_fight_projection(
                fight_snapshot,
                [guardian],
                guardian,
                player_speed=fight_snapshot.player.speed + SPEED_POTION_BONUS,
                extra_turns=1,
            )
            is not None
        )

    def _conquest_target(self, snapshot: Snapshot) -> int | None:
        # The DEEPEST unconquered dungeon whose bottom floor is within the resistance
        # limit — one we can safely clear to kill the final guardian (its drop is the
        # best gear available to us). Fundraising may use Yeek Cave 1F, but once
        # its guardian is beatable the conquest target takes priority over that
        # utility role. This is the priority goal.
        #
        # Once chosen, the target is LATCHED (_conquest_committed): _guardian_fight_
        # viable depends on consumables (e.g. a Speed potion that only makes a fight
        # projection succeed while held), so re-deriving from scratch every observe
        # made the recall destination churn as potions were bought/used/stashed.
        # The latch only breaks on a STRUCTURAL change -- conquered, a resistance
        # regression past its max_depth, or it dropping out of the known/entered
        # set -- never on consumable possession.
        limit = self._resistance_depth_limit(snapshot)
        conquered = set(snapshot.conquered_dungeon_ids)
        committed = self._conquest_committed
        if committed is not None:
            info = self._dungeon_knowledge.get(committed)
            if (
                committed == DUNGEON_CHAMELEON_CAVE
                or committed in conquered
                or info is None
                or committed not in snapshot.entered_dungeon_ids
                or info.max_depth <= 0
                or info.max_depth > limit
            ):
                self._conquest_committed = None
            else:
                return committed

        best: DungeonInfo | None = None
        for did in snapshot.entered_dungeon_ids:
            info = self._dungeon_knowledge.get(did)
            if (
                info is None
                or did == DUNGEON_CHAMELEON_CAVE
                or did in conquered
                or (did == DUNGEON_YEEK_CAVE and info.guardian_id <= 0)
            ):
                continue
            if info.max_depth <= 0 or info.max_depth > limit:
                continue  # cannot safely reach its guardian floor
            if not self._guardian_fight_viable(snapshot, info):
                continue
            if best is None or info.max_depth > best.max_depth:
                best = info
        if best is not None:
            self._conquest_committed = best.id
        return best.id if best is not None else None

    def _unique_fight_projection(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        target: MonsterState,
        *,
        player_speed: int,
        extra_turns: int = 0,
    ) -> dict[str, int] | None:
        weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"),
            None,
        )
        if weapon is None or snapshot.player.main_hand_blows <= 0:
            return None
        damage_per_attack = self._main_hand_dps(snapshot, weapon)
        if damage_per_attack <= 0:
            return None
        attacks = max(1, ceil(target.hp / damage_per_attack))
        if attacks > UNIQUE_COMBAT_MAX_ATTACKS:
            return None

        healing_doses = sorted(
            (
                [HEALING_POTION_HP]
                * self._exact_potion_count(snapshot, SV_POTION_HEALING)
                + [FIXED_QUEST_CURE_CRITICAL_HP]
                * self._exact_potion_count(snapshot, SV_POTION_CURE_CRITICAL)
            ),
            reverse=True,
        )
        reserve = max(1, ceil(snapshot.player.max_hp * UNIQUE_COMBAT_HP_RESERVE_RATIO))
        speed_snapshot = replace(
            snapshot,
            player=replace(snapshot.player, speed=player_speed),
        )
        per_turn_damage = self._predicted_damage(
            speed_snapshot, hostiles, turns=1
        )
        healing_doses = [
            heal_amount
            for heal_amount in healing_doses
            if heal_amount >= per_turn_damage
        ]
        # Each dose costs a turn. As in the fixed-quest threat budget, value the
        # strongest realizable doses first and never credit more doses than the
        # fight's attack window.
        healing_doses = healing_doses[:attacks]
        for healing_uses in range(len(healing_doses) + 1):
            turns = attacks + healing_uses + extra_turns
            operational = self._predicted_damage(
                speed_snapshot, hostiles, turns=turns
            )
            capacity = snapshot.player.hp + sum(healing_doses[:healing_uses])
            if operational <= capacity - reserve:
                return {
                    "attacks": attacks,
                    "healing_uses": healing_uses,
                    "turns": turns,
                    "operational": operational,
                    "expected": self._predicted_damage(
                        speed_snapshot, hostiles, turns=turns, expected=True
                    ),
                    "reserve": reserve,
                }
        return None

    def _unique_combat_consumable(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        unique_hostiles = [
            monster
            for monster in hostiles
            if self._consumable_fight_target(snapshot, monster)
        ]
        adjacent_uniques = [
            monster for monster in unique_hostiles if monster.distance <= 1
        ]

        # Retain the speed baseline while approaching the same visible unique,
        # but discard encounter state once it is gone or a different one replaces it.
        tracked_race_id = unique_hostiles[0].race_id if len(unique_hostiles) == 1 else None
        if tracked_race_id != self._unique_speed_race_id:
            self._unique_speed_race_id = tracked_race_id
            self._unique_speed_baseline = (
                player.speed if tracked_race_id is not None else None
            )
            self._unique_speed_attempted = False
            self._unique_speed_was_active = False
            if tracked_race_id != self._unique_combat_committed_race_id:
                self._unique_combat_committed_race_id = None

        if self._unique_speed_baseline is not None:
            if player.speed > self._unique_speed_baseline:
                self._unique_speed_was_active = True
            elif self._unique_speed_was_active:
                # The prior dose expired during a long fight. A further dose is
                # permitted if the fresh projection still justifies it.
                self._unique_speed_attempted = False
                self._unique_speed_was_active = False

        if (
            len(adjacent_uniques) != 1
            or len(unique_hostiles) != 1
            or player.afraid
            or player.blind
            or player.confused
            or player.paralyzed
            or any(monster.can_multiply for monster in hostiles)
            or any(
                monster.can_summon and monster.index != adjacent_uniques[0].index
                for monster in hostiles
            )
        ):
            return None

        target = adjacent_uniques[0]
        normal_plan = self._unique_fight_projection(
            snapshot,
            hostiles,
            target,
            player_speed=player.speed,
        )
        healing_count = (
            self._exact_potion_count(snapshot, SV_POTION_HEALING)
            + self._exact_potion_count(snapshot, SV_POTION_CURE_CRITICAL)
        )
        speed_potion = self._find_exact_potion(snapshot, SV_POTION_SPEED)
        speed_plan = None
        if (
            speed_potion is not None
            and not self._unique_speed_attempted
            and not self._unique_speed_was_active
        ):
            speed_plan = self._unique_fight_projection(
                snapshot,
                hostiles,
                target,
                player_speed=player.speed + SPEED_POTION_BONUS,
                extra_turns=1,
            )

        # Speed potions are scarce. Spend one on a unique only when the normal
        # fight would consume a Potion of Healing and haste actually saves at
        # least one dose. A merely smaller damage projection is not enough.
        speed_is_material = speed_plan is not None and (
            (
                normal_plan is not None
                and normal_plan["healing_uses"] > 0
                and speed_plan["healing_uses"] < normal_plan["healing_uses"]
            )
            or (
                # The normal projection tried every realizable healing dose and
                # still failed; haste is worthwhile only if it makes the fight
                # viable while consuming fewer than that entire stock.
                normal_plan is None
                and healing_count > 0
                and speed_plan["healing_uses"] < healing_count
            )
        )
        chosen_plan = speed_plan if speed_is_material else normal_plan
        if chosen_plan is None:
            return None

        next_one = self._predicted_damage(snapshot, hostiles, turns=1)
        healing = next(
            (
                potion
                for potion in (
                    self._find_exact_potion(snapshot, SV_POTION_HEALING),
                    self._find_exact_potion(
                        snapshot, SV_POTION_CURE_CRITICAL
                    ),
                )
                if potion is not None
                and (
                    HEALING_POTION_HP
                    if potion.sval == SV_POTION_HEALING
                    else FIXED_QUEST_CURE_CRITICAL_HP
                )
                >= next_one
            ),
            None,
        )
        if chosen_plan["healing_uses"] > 0 and healing is not None:
            missing_hp = player.max_hp - player.hp
            heal_amount = min(
                (
                    HEALING_POTION_HP
                    if healing.sval == SV_POTION_HEALING
                    else FIXED_QUEST_CURE_CRITICAL_HP
                ),
                player.max_hp,
            )
            if (
                missing_hp > 0
                and (
                    next_one >= player.hp - chosen_plan["reserve"]
                    or missing_hp * 4 >= heal_amount * 3
                )
            ):
                self._unique_combat_committed_race_id = target.race_id
                self.last_reason = (
                    "unique:quaff-healing"
                    if healing.sval == SV_POTION_HEALING
                    else "unique:quaff-cure-critical"
                )
                return QUAFF_KEY + healing.slot

        if speed_is_material and speed_potion is not None:
            self._unique_speed_attempted = True
            self._unique_combat_committed_race_id = target.race_id
            self.last_reason = "unique:quaff-speed"
            return QUAFF_KEY + speed_potion.slot
        return None

    def _q31_opening_hold_is_controlled(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile | None,
        hostiles: list[MonsterState],
    ) -> bool:
        """Return whether Q31 is still inside its reviewed entrance defense."""
        if profile is None or profile.quest_id != 31 or not hostiles:
            return False
        hold_value = profile.engagement_plan.get("hold_position")
        if hold_value is None or snapshot.player.position != Position(*hold_value):
            return False
        initial_hold_budget = max(
            0, int(profile.engagement_plan.get("initial_hold_turns", 0))
        )
        opening_complete = (
            profile.quest_id in self._quest_strategy_post_wave_light_attempted
            or self._quest_strategy_initial_hold_turns.get(profile.quest_id, 0)
            >= initial_hold_budget
        )
        if opening_complete:
            return False
        player = snapshot.player
        if (
            player.afraid
            or player.blind
            or player.confused
            or player.paralyzed
            or any(monster.can_summon or monster.can_multiply for monster in hostiles)
        ):
            return False
        max_melee = max(
            0, int(profile.engagement_plan.get("max_simultaneous_melee", 0))
        )
        adjacent = sum(monster.distance <= 1 for monster in hostiles)
        return max_melee > 0 and adjacent <= max_melee

    def _q31_opening_hold_absorbs_threat(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile | None,
        hostiles: list[MonsterState],
    ) -> bool:
        """Keep Q31's reviewed opening defense at the entrance choke point.

        Q31 deliberately carries Speed and healing to thin the mobile opening
        wave from [18,1].  Applying the generic three-turn worst-case teleport
        there scatters the wave across the map and turns every attempted return
        into another surround.  The hold remains valid while no more than the
        reviewed number of enemies can melee and expected damage is survivable.
        """
        if not self._q31_opening_hold_is_controlled(snapshot, profile, hostiles):
            return False
        return self._predicted_damage(
            snapshot, hostiles, turns=3, expected=True
        ) < snapshot.player.hp

    def _q31_stationary_engagement_absorbs_threat(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile | None,
        hostiles: list[MonsterState],
    ) -> bool:
        """Do not abandon Q31 for a theoretical stationary-target surround.

        Willow and the Huorns are NEVER_MOVE fixed targets.  Their rare
        TELE_TO effects make the theoretical predictor place every visible
        target in melee over three turns, even though only the currently
        adjacent targets can attack normally.  Q31's reviewed sweep owns that
        risk until its explicit abort threshold is reached, provided the live
        expected projection remains survivable.
        """
        if profile is None or profile.quest_id != 31 or not hostiles:
            return False
        abort = profile.abort_conditions
        if (
            bool(abort.get("allowed", False))
            and snapshot.player.hp_ratio <= float(abort.get("hp_ratio", 0))
        ):
            return False
        controlled_races = self._quest_never_move_races(profile)
        if not controlled_races or any(
            monster.race_id not in controlled_races
            or monster.can_summon
            or monster.can_multiply
            for monster in hostiles
        ):
            return False
        player = snapshot.player
        if player.afraid or player.blind or player.confused or player.paralyzed:
            return False
        max_melee = max(
            0, int(profile.engagement_plan.get("max_simultaneous_melee", 0))
        )
        adjacent = sum(monster.distance <= 1 for monster in hostiles)
        if max_melee <= 0 or adjacent > max_melee:
            return False
        return self._predicted_damage(
            snapshot, hostiles, turns=3, expected=True
        ) < player.hp

    def _q31_opening_heal_before_escape(
        self,
        snapshot: Snapshot,
        profile: StrategyProfile | None,
        hostiles: list[MonsterState],
    ) -> InventoryItem | None:
        """Spend the reviewed Q31 heal before scattering the opening wave."""
        if not self._q31_opening_hold_is_controlled(snapshot, profile, hostiles):
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
        return self._find_heal_potion(
            snapshot, expected_damage=expected_damage
        )

    def _kill_quest_descent_allowed(self, snapshot: Snapshot) -> bool:
        """Central veto for every ordinary or quest-regeneration descent."""
        active = self._taken_dungeon_kill_level_quest(snapshot)
        return active is None or snapshot.dungeon_level < active[1].level

    def _kill_quest_floor_recovery_key(self, snapshot: Snapshot) -> str | None:
        """Recover an overshoot, or finish the downward half of regeneration."""
        active = self._taken_dungeon_kill_level_quest(snapshot)
        if active is None:
            self._quest_regen_id = None
            self._quest_regen_phase = None
            return None
        quest, info = active
        if quest.cur_num is None:
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if snapshot.dungeon_level > info.level:
            if here is not None and self._is_upstairs_target(here):
                self.last_reason = "quest:regen:ascend"
                return UP_STAIRS_KEY
            step = self._nearest_goal_step(snapshot, self._is_upstairs_target)
            if step is not None:
                self.last_reason = "quest:regen:ascend"
                return self._step_toward(snapshot, step)
            return None
        if (
            self._quest_regen_id == quest.id
            and self._quest_regen_phase == "descend"
            and snapshot.dungeon_level == info.level - 1
        ):
            destination_depth = snapshot.dungeon_level + 1
            if (
                here is not None
                and here.is_descent
                and not self._destination_depth_allowed(snapshot, destination_depth)
            ):
                return WAIT_KEY
            if here is not None and here.is_descent and self._kill_quest_descent_allowed(snapshot):
                self.last_reason = "quest:regen:descend"
                return DOWN_STAIRS_KEY
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: grid.is_descent and self._kill_quest_descent_allowed(snapshot),
            )
            if step is not None:
                self.last_reason = "quest:regen:descend"
                return self._step_toward(snapshot, step)
        return None
